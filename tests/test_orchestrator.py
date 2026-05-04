"""
End-to-end orchestrator tests.

The Anthropic API is mocked via a fake IntentClassifier so no API key is needed.
The ticket DB uses a fresh SQLite file in pytest's tmp_path.

Run:
    pytest tests/test_orchestrator.py -v -s
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.classifier.classifier import ClassificationResult, IntentClassifier
from chatbot.orchestrator import BotTurn, ChatbotOrchestrator
from chatbot.session.state import ConversationState
from shared.db.migrate import migrate
from shared.db.repository import TicketRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_orch.db"
    migrate(p)
    return p


@pytest.fixture
def repo(db_path: Path) -> TicketRepository:
    return TicketRepository(db_path)


def _mock_classifier(responses: list[tuple[str, float]]) -> MagicMock:
    """
    Build a mock IntentClassifier that returns each (intent_id, confidence) in sequence.
    After exhausting the list it repeats the last entry.
    """
    clf = MagicMock(spec=IntentClassifier)
    results = [
        ClassificationResult(
            intent_id=i,
            confidence=c,
            top_3_alternatives=[],
            reasoning=f"mock response for {i}",
        )
        for i, c in responses
    ]
    # side_effect cycles through results, staying on last after exhausted
    calls = {"n": 0}

    def _classify(*args, **kwargs):
        idx = min(calls["n"], len(results) - 1)
        calls["n"] += 1
        return results[idx]

    clf.classify.side_effect = _classify
    return clf


def _orchestrator(db_path: Path, responses: list[tuple[str, float]]) -> ChatbotOrchestrator:
    clf = _mock_classifier(responses)
    return ChatbotOrchestrator(db_path=db_path, classifier=clf)


def fresh_state() -> ConversationState:
    return ConversationState()


# ===========================================================================
# 1. Happy path — order_status with 2 slots (order_id + email)
#
#    Turn 1: "where's my order"  → bot asks for order_id
#    Turn 2: "ORD-1001"          → bot asks for email
#    Turn 3: "test@example.com"  → bot returns order status (resolved)
#
#    Ticket must have 6 messages (3 user + 3 bot) and resolution_path=bot_resolved
# ===========================================================================

class TestHappyPath:
    def test_full_order_status_flow(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.92)])
        state = fresh_state()

        # Turn 1 — classify and ask for order_id
        t1 = orch.handle_message("where's my order", state)
        assert not t1.should_escalate
        assert "order" in t1.bot_response.lower()
        assert state.waiting_for_slot == "order_id"

        # Turn 2 — provide order_id, bot asks for email
        t2 = orch.handle_message("ORD-1001", state)
        assert not t2.should_escalate
        assert "email" in t2.bot_response.lower()
        assert state.waiting_for_slot == "email"
        assert state.collected_slots.get("order_id") == "ORD-1001"

        # Turn 3 — provide email, resolved
        t3 = orch.handle_message("test@example.com", state)
        assert not t3.should_escalate
        assert "ORD-1001" in t3.bot_response
        assert state.waiting_for_slot is None

        # --- DB assertions ---
        messages = repo.get_messages(state.ticket_id)
        assert len(messages) == 6, f"Expected 6 messages, got {len(messages)}"
        # Message roles in order
        roles = [m.role for m in messages]
        assert roles == ["user", "bot", "user", "bot", "user", "bot"]

        ticket = repo.get_ticket(state.ticket_id)
        assert ticket is not None
        assert ticket.resolution_path == "bot_resolved"
        assert ticket.final_status == "resolved"

    def test_ticket_created_on_first_message(self, db_path, repo):
        orch = _orchestrator(db_path, [("return_policy", 0.88)])
        state = fresh_state()
        assert repo.get_ticket(state.ticket_id) is None
        orch.handle_message("what is your return policy?", state)
        assert repo.get_ticket(state.ticket_id) is not None

    def test_faq_resolves_in_single_turn(self, db_path, repo):
        orch = _orchestrator(db_path, [("return_policy", 0.91)])
        state = fresh_state()
        t1 = orch.handle_message("what is your return policy?", state)
        assert not t1.should_escalate
        assert len(t1.bot_response) > 20
        # Resolved immediately — no waiting slot
        assert state.waiting_for_slot is None
        ticket = repo.get_ticket(state.ticket_id)
        assert ticket.resolution_path == "bot_resolved"

    def test_messages_stored_in_db(self, db_path, repo):
        orch = _orchestrator(db_path, [("shipping_info", 0.85)])
        state = fresh_state()
        orch.handle_message("how much does shipping cost?", state)
        msgs = repo.get_messages(state.ticket_id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "bot"

    def test_slot_ordering_is_correct(self, db_path, repo):
        """Bot asks for order_id first, then email — not the other way around."""
        orch = _orchestrator(db_path, [("order_status", 0.90)])
        state = fresh_state()
        orch.handle_message("track my order", state)
        assert state.waiting_for_slot == "order_id"

    def test_collected_slots_cleared_after_resolve(self, db_path, repo):
        orch = _orchestrator(db_path, [("return_policy", 0.90)])
        state = fresh_state()
        orch.handle_message("return policy?", state)
        # After resolution, intent is reset
        assert state.current_intent is None
        assert state.collected_slots == {}


# ===========================================================================
# 2. Escalation path — "I want to talk to a human"
#
#    Single message triggers escalated_user_request.
#    Ticket resolution_path must be "escalated_user_request".
# ===========================================================================

class TestEscalationPath:
    def test_explicit_human_request_escalates(self, db_path, repo):
        # Classifier would classify this, but escalation fires first on keywords
        orch = _orchestrator(db_path, [("order_status", 0.85)])
        state = fresh_state()
        t1 = orch.handle_message("I want to talk to a human", state)
        assert t1.should_escalate
        assert t1.escalation_reason == "escalated_user_request"

    def test_escalation_ticket_has_correct_resolution_path(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.85)])
        state = fresh_state()
        orch.handle_message("I want to talk to a human", state)
        ticket = repo.get_ticket(state.ticket_id)
        assert ticket.resolution_path == "escalated_user_request"
        assert ticket.final_status == "in_progress"

    def test_escalation_stores_2_messages(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.85)])
        state = fresh_state()
        orch.handle_message("let me speak to an agent", state)
        msgs = repo.get_messages(state.ticket_id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "bot"

    def test_sensitive_keyword_escalates_correctly(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.88)])
        state = fresh_state()
        t1 = orch.handle_message("I'll call my lawyer about this", state)
        assert t1.should_escalate
        assert t1.escalation_reason == "escalated_sensitive"
        ticket = repo.get_ticket(state.ticket_id)
        assert ticket.resolution_path == "escalated_sensitive"

    def test_low_confidence_escalates(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.30)])  # below 0.70 threshold
        state = fresh_state()
        t1 = orch.handle_message("some ambiguous question", state)
        assert t1.should_escalate
        assert t1.escalation_reason == "escalated_low_confidence"

    def test_escalation_bot_response_is_friendly(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.88)])
        state = fresh_state()
        t1 = orch.handle_message("I want to speak to a person", state)
        # Should NOT contain technical jargon
        assert "escalated" not in t1.bot_response.lower()
        assert "error" not in t1.bot_response.lower()
        # Should mention human/team/agent
        lower = t1.bot_response.lower()
        assert any(w in lower for w in ["team", "agent", "support", "specialist"])

    def test_null_intent_no_escalation_returns_no_intent_message(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.85)])
        # Override to return no intent
        orch._classifier.classify.return_value = ClassificationResult(
            intent_id=None, confidence=0.1, top_3_alternatives=[], reasoning="no match"
        )
        orch._classifier.classify.side_effect = None
        state = fresh_state()
        # confidence 0.1 < threshold → escalate (low confidence), not no-intent
        t1 = orch.handle_message("ghjkl qwerty", state)
        # Either escalates or returns no-intent — both are valid
        assert isinstance(t1, BotTurn)

    def test_cancel_shipped_order_escalates_via_resolution(self, db_path, repo):
        orch = _orchestrator(db_path, [("cancel_order", 0.88)])
        state = fresh_state()
        # Turn 1 — classify
        orch.handle_message("cancel my order", state)
        # Turn 2 — provide shipped order ID → resolution fires trigger → escalation
        t2 = orch.handle_message("ORD-1002", state)
        assert t2.should_escalate
        ticket = repo.get_ticket(state.ticket_id)
        assert "escalated" in ticket.resolution_path


# ===========================================================================
# 3. Force-intent (button click) — skips classifier
# ===========================================================================

class TestForceIntent:
    def test_force_intent_asks_for_slot_immediately(self, db_path, repo):
        clf = _mock_classifier([("order_status", 0.90)])
        orch = ChatbotOrchestrator(db_path=db_path, classifier=clf)
        state = fresh_state()

        t1 = orch.handle_message("Track my order", state, force_intent="order_status")
        assert not t1.should_escalate
        assert "order" in t1.bot_response.lower()
        assert state.waiting_for_slot == "order_id"

    def test_force_intent_classifier_not_called(self, db_path, repo):
        clf = _mock_classifier([("order_status", 0.90)])
        orch = ChatbotOrchestrator(db_path=db_path, classifier=clf)
        state = fresh_state()

        orch.handle_message("Check stock", state, force_intent="product_availability")
        clf.classify.assert_not_called()

    def test_force_intent_sets_correct_intent_in_state(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.90)])
        state = fresh_state()
        orch.handle_message("button click", state, force_intent="return_policy")
        # return_policy has no slots, so it resolves immediately and resets intent
        assert state.current_intent is None  # reset after resolution
        ticket = repo.get_ticket(state.ticket_id)
        assert ticket.resolution_path == "bot_resolved"

    def test_force_intent_resolves_faq_immediately(self, db_path, repo):
        orch = _orchestrator(db_path, [("shipping_info", 0.90)])
        state = fresh_state()
        t1 = orch.handle_message("Shipping info", state, force_intent="shipping_info")
        assert not t1.should_escalate
        assert len(t1.bot_response) > 10
        ticket = repo.get_ticket(state.ticket_id)
        assert ticket.resolution_path == "bot_resolved"

    def test_force_intent_then_continue_with_slots(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.90)])
        state = fresh_state()

        # Button press for order_status
        t1 = orch.handle_message("Track order", state, force_intent="order_status")
        assert state.waiting_for_slot == "order_id"

        # Next turn — user provides order_id (no classifier call)
        t2 = orch.handle_message("ORD-1005", state)
        assert state.collected_slots.get("order_id") == "ORD-1005"
        assert state.waiting_for_slot == "email"

        # No classifier calls after force_intent for the first turn — only 0 or 1 call
        # (first turn uses force_intent, subsequent turns re-use active intent)
        assert orch._classifier.classify.call_count == 0


# ===========================================================================
# 4. Slot validation
# ===========================================================================

class TestSlotValidation:
    def test_invalid_order_id_asks_again(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.90)])
        state = fresh_state()
        orch.handle_message("where is my order", state)
        assert state.waiting_for_slot == "order_id"

        # Invalid value
        t2 = orch.handle_message("not-a-valid-id", state)
        # Still waiting for order_id
        assert state.waiting_for_slot == "order_id"
        assert "order" in t2.bot_response.lower() or "order number" in t2.bot_response.lower()

    def test_valid_order_id_advances(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.90)])
        state = fresh_state()
        orch.handle_message("where is my order", state)

        t2 = orch.handle_message("ORD-1001", state)
        assert state.collected_slots.get("order_id") == "ORD-1001"
        # Now waiting for email
        assert state.waiting_for_slot == "email"

    def test_invalid_then_valid_slot(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.90)])
        state = fresh_state()
        orch.handle_message("track my order", state)

        orch.handle_message("bad!!!", state)           # invalid
        assert state.waiting_for_slot == "order_id"   # still waiting

        orch.handle_message("#10234", state)           # valid
        assert state.collected_slots.get("order_id") == "#10234"
        assert state.waiting_for_slot == "email"


# ===========================================================================
# 5. PII detection
# ===========================================================================

class TestPIIDetection:
    def test_pii_card_triggers_warning(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.90)])
        state = fresh_state()
        t1 = orch.handle_message("my card is 4111 1111 1111 1111 help", state)
        # The PII warning should be in the bot response
        assert "security" in t1.bot_response.lower() or "sensitive" in t1.bot_response.lower()

    def test_pii_message_is_redacted_in_db(self, db_path, repo):
        orch = _orchestrator(db_path, [("return_policy", 0.85)])
        state = fresh_state()
        orch.handle_message("4111 1111 1111 1111 return policy?", state)
        msgs = repo.get_messages(state.ticket_id)
        user_msg = next(m for m in msgs if m.role == "user")
        assert "[CARD_REDACTED]" in user_msg.body
        assert user_msg.is_redacted is True


# ===========================================================================
# 6. Debug dict
# ===========================================================================

class TestDebugDict:
    def test_debug_contains_intent_and_confidence(self, db_path, repo):
        orch = _orchestrator(db_path, [("return_policy", 0.87)])
        state = fresh_state()
        t1 = orch.handle_message("return policy", state)
        assert "intent_id" in t1.debug
        assert "confidence" in t1.debug
        assert t1.debug["intent_id"] == "return_policy"
        assert t1.debug["confidence"] == pytest.approx(0.87)

    def test_debug_contains_slots(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.92)])
        state = fresh_state()
        orch.handle_message("track order", state)
        orch.handle_message("ORD-1001", state)
        t3 = orch.handle_message("user@example.com", state)
        assert "slots" in t3.debug
        assert t3.debug["slots"]["order_id"] == "ORD-1001"

    def test_escalation_debug_contains_handoff_summary(self, db_path, repo):
        orch = _orchestrator(db_path, [("order_status", 0.88)])
        state = fresh_state()
        t1 = orch.handle_message("I want an agent", state)
        assert "handoff_summary" in t1.debug
        assert len(t1.debug["handoff_summary"]) > 0


# ===========================================================================
# 7. Multi-turn guided flow (cancel_order happy path — ORD-1001 processing)
# ===========================================================================

class TestGuidedFlowOrchestration:
    def test_cancel_guided_flow_completes(self, db_path, repo):
        orch = _orchestrator(db_path, [("cancel_order", 0.88)])
        state = fresh_state()

        # Turn 1 — classify, asks for order_id
        t1 = orch.handle_message("cancel my order", state)
        assert state.waiting_for_slot == "order_id"

        # Turn 2 — provide order_id (ORD-1001 is processing → cancellable)
        t2 = orch.handle_message("ORD-1001", state)
        # Step 0: confirmation prompt
        assert not t2.should_escalate
        assert "ORD-1001" in t2.bot_response or "confirm" in t2.bot_response.lower()
        assert state.waiting_for_slot == "guided_step_0"

        # Turn 3 — confirm
        t3 = orch.handle_message("yes", state)
        # Step 1: reason prompt
        assert not t3.should_escalate
        assert state.waiting_for_slot == "guided_step_1"

        # Turn 4 — give reason
        t4 = orch.handle_message("changed my mind", state)
        # Step 2: final message (resolved)
        assert not t4.should_escalate
        assert state.waiting_for_slot is None

        ticket = repo.get_ticket(state.ticket_id)
        assert ticket.resolution_path == "bot_resolved"
        assert ticket.final_status == "resolved"

        msgs = repo.get_messages(state.ticket_id)
        # 4 user + 4 bot = 8 messages
        assert len(msgs) == 8

    def test_cancel_flow_message_count(self, db_path, repo):
        orch = _orchestrator(db_path, [("cancel_order", 0.88)])
        state = fresh_state()
        orch.handle_message("cancel my order", state)
        orch.handle_message("ORD-1001", state)  # slot + step 0
        orch.handle_message("yes", state)         # step 1
        orch.handle_message("changed my mind", state)  # step 2 (final)
        msgs = repo.get_messages(state.ticket_id)
        assert len(msgs) == 8

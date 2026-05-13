"""
Tests for ResolutionEngine — no LLM calls, mock backend is deterministic.

Run:
    pytest tests/test_resolution.py -v -s
"""

from __future__ import annotations

import sys

import pytest

from chatbot.resolution.engine import ResolutionEngine, ResolutionResult
from chatbot.session.state import ConversationState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    return ResolutionEngine()


def fresh_state(intent_id: str | None = None) -> ConversationState:
    state = ConversationState(ticket_id="test-ticket-001")
    if intent_id:
        state.set_intent(intent_id)
    return state


# ---------------------------------------------------------------------------
# Helper — print a conversation exchange (visible with pytest -s)
# ---------------------------------------------------------------------------

def _safe(text: str) -> str:
    """Replace non-ASCII characters so Windows cp1252 console (and capsys) never choke."""
    return text.encode("ascii", errors="replace").decode("ascii")


def _log(label: str, result: ResolutionResult) -> None:
    print(f"\n  [{label}]")
    print(f"    status       : {result.status}")
    print(f"    missing_slot : {result.missing_slot}")
    print(f"    bot_response : {_safe(result.bot_response[:120])}")
    if result.api_data:
        print(f"    api_data     : {result.api_data}")


# ===========================================================================
# 1. Slot collection — order_status with no slots → asks for order_id
# ===========================================================================

class TestSlotCollection:
    def test_no_slots_returns_needs_slot(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve("order_status", {}, state)
        assert result.status == "needs_slot"
        assert result.missing_slot == "order_id"

    def test_prompt_is_order_id_prompt(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve("order_status", {}, state)
        assert "order" in result.bot_response.lower()

    def test_partial_slots_asks_for_next(self, engine):
        state = fresh_state("order_status")
        # order_id provided but email still missing
        result = engine.resolve("order_status", {"order_id": "ORD-1001"}, state)
        assert result.status == "needs_slot"
        assert result.missing_slot == "email"

    def test_all_slots_present_does_not_return_needs_slot(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "ORD-1001", "email": "test@example.com"},
            state,
        )
        assert result.status != "needs_slot"

    def test_return_policy_has_no_slots(self, engine):
        state = fresh_state("return_policy")
        result = engine.resolve("return_policy", {}, state)
        # return_policy has no required slots, should resolve immediately
        assert result.status == "resolved"

    def test_product_availability_asks_for_product_name(self, engine):
        state = fresh_state("product_availability")
        result = engine.resolve("product_availability", {}, state)
        assert result.status == "needs_slot"
        assert result.missing_slot == "product_name"


# ===========================================================================
# 2. Successful order status resolution (ORD-1001 + email)
# ===========================================================================

class TestOrderStatusResolution:
    def test_known_order_resolves(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "ORD-1001", "email": "anyone@example.com"},
            state,
        )
        assert result.status == "resolved"

    def test_response_contains_order_id(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "ORD-1001", "email": "anyone@example.com"},
            state,
        )
        assert "ORD-1001" in result.bot_response

    def test_response_contains_status(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "ORD-1001", "email": "anyone@example.com"},
            state,
        )
        # ORD-1001 is in "processing" state
        assert "processing" in result.bot_response.lower()

    def test_api_data_returned(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "ORD-1001", "email": "x@y.com"},
            state,
        )
        assert result.api_data is not None
        assert "status" in result.api_data

    def test_unknown_order_returns_failed(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "ORD-9999", "email": "x@y.com"},
            state,
        )
        assert result.status == "failed"

    def test_unknown_order_fires_trigger(self, engine):
        state = fresh_state("order_status")
        engine.resolve(
            "order_status",
            {"order_id": "ORD-9999", "email": "x@y.com"},
            state,
        )
        assert "order_not_found" in state.escalation_triggers_fired

    def test_hash_prefixed_order_id_accepted(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "#1001", "email": "x@y.com"},
            state,
        )
        assert result.status == "resolved"

    def test_order_status_shipped_order(self, engine):
        state = fresh_state("order_status")
        result = engine.resolve(
            "order_status",
            {"order_id": "ORD-1002", "email": "x@y.com"},
            state,
        )
        assert result.status == "resolved"
        assert "shipped" in result.bot_response.lower()


# ===========================================================================
# 3. return_policy — pure FAQ answer
# ===========================================================================

class TestReturnPolicyFAQ:
    def test_status_is_resolved(self, engine):
        state = fresh_state("return_policy")
        result = engine.resolve("return_policy", {}, state)
        assert result.status == "resolved"

    def test_bot_response_is_non_empty(self, engine):
        state = fresh_state("return_policy")
        result = engine.resolve("return_policy", {}, state)
        assert len(result.bot_response) > 20

    def test_response_mentions_return(self, engine):
        state = fresh_state("return_policy")
        result = engine.resolve("return_policy", {}, state)
        assert "return" in result.bot_response.lower()

    def test_no_missing_slot(self, engine):
        state = fresh_state("return_policy")
        result = engine.resolve("return_policy", {}, state)
        assert result.missing_slot is None

    def test_api_data_is_none(self, engine):
        state = fresh_state("return_policy")
        result = engine.resolve("return_policy", {}, state)
        assert result.api_data is None

    def test_shipping_info_also_resolves_as_faq(self, engine):
        state = fresh_state("shipping_info")
        result = engine.resolve("shipping_info", {}, state)
        assert result.status == "resolved"
        assert len(result.bot_response) > 10


# ===========================================================================
# 4. cancel_order — already-shipped order fires escalation trigger
# ===========================================================================

class TestCancelOrderEscalation:
    def test_shipped_order_returns_failed(self, engine):
        state = fresh_state("cancel_order")
        result = engine.resolve(
            "cancel_order",
            {"order_id": "ORD-1002"},
            state,
        )
        assert result.status == "failed"

    def test_shipped_order_fires_trigger_in_state(self, engine):
        state = fresh_state("cancel_order")
        engine.resolve("cancel_order", {"order_id": "ORD-1002"}, state)
        assert "order_already_shipped" in state.escalation_triggers_fired

    def test_shipped_order_trigger_in_api_data(self, engine):
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {"order_id": "ORD-1002"}, state)
        assert result.api_data is not None
        assert result.api_data.get("escalation_trigger") == "order_already_shipped"

    def test_fulfilled_order_fires_order_fulfilled_trigger(self, engine):
        # ORD-1003 is delivered → cancel_escalation_trigger = order_fulfilled
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {"order_id": "ORD-1003"}, state)
        assert result.status == "failed"
        assert "order_fulfilled" in state.escalation_triggers_fired

    def test_failure_count_incremented(self, engine):
        state = fresh_state("cancel_order")
        engine.resolve("cancel_order", {"order_id": "ORD-1002"}, state)
        assert state.failure_count_per_intent.get("cancel_order", 0) >= 1

    def test_cancellable_order_does_not_fail(self, engine):
        # ORD-1001 is processing → can cancel
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        assert result.status != "failed"

    def test_unknown_order_for_cancel(self, engine):
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {"order_id": "ORD-9999"}, state)
        assert result.status == "failed"
        assert "order_not_found" in state.escalation_triggers_fired

    def test_cancel_no_slots_asks_for_order_id(self, engine):
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {}, state)
        assert result.status == "needs_slot"
        assert result.missing_slot == "order_id"


# ===========================================================================
# 5. Guided flow — cancel_order happy path (ORD-1001)
# ===========================================================================

class TestGuidedFlow:
    def test_step_0_returns_confirmation_prompt(self, engine):
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        # Step 0: confirmation
        assert result.status == "needs_slot"
        assert "confirm" in result.bot_response.lower() or "ORD-1001" in result.bot_response

    def test_step_1_returns_reason_prompt(self, engine):
        state = fresh_state("cancel_order")
        # Advance past step 0
        engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        result = engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        assert result.status == "needs_slot"
        assert "cancel" in result.bot_response.lower() or "why" in result.bot_response.lower()

    def test_step_2_final_resolves(self, engine):
        state = fresh_state("cancel_order")
        engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)  # step 0
        engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)  # step 1
        result = engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)  # step 2 (final)
        assert result.status == "resolved"

    def test_guided_flow_step_tracked_in_state(self, engine):
        state = fresh_state("cancel_order")
        assert state.guided_flow_step == 0
        engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        assert state.guided_flow_step == 1
        engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        assert state.guided_flow_step == 2

    def test_guided_flow_api_data_has_step(self, engine):
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        assert result.api_data is not None
        assert result.api_data.get("step") == 0

    def test_guided_flow_api_data_has_expected_input_type(self, engine):
        state = fresh_state("cancel_order")
        result = engine.resolve("cancel_order", {"order_id": "ORD-1001"}, state)
        assert result.api_data.get("expected_input_type") == "confirmation"


# ===========================================================================
# 6. Product availability
# ===========================================================================

class TestProductAvailability:
    def test_known_in_stock_product_resolves(self, engine):
        state = fresh_state("product_availability")
        result = engine.resolve("product_availability", {"product_name": "golden mirror"}, state)
        assert result.status == "resolved"
        assert "In Stock" in result.bot_response

    def test_out_of_stock_product_resolves(self, engine):
        state = fresh_state("product_availability")
        result = engine.resolve("product_availability", {"product_name": "ceramic vase"}, state)
        assert result.status == "resolved"
        assert "Out of Stock" in result.bot_response

    def test_product_name_in_response(self, engine):
        state = fresh_state("product_availability")
        result = engine.resolve("product_availability", {"product_name": "yoga mat"}, state)
        assert "yoga mat" in result.bot_response.lower()

    def test_unknown_product_fails(self, engine):
        state = fresh_state("product_availability")
        result = engine.resolve(
            "product_availability", {"product_name": "xxxx_nonexistent_xxxx"}, state
        )
        # product_not_found escalation trigger → failed
        assert result.status == "failed"


# ===========================================================================
# 7. Refund status
# ===========================================================================

class TestRefundStatus:
    def test_known_order_with_refund_resolves(self, engine):
        state = fresh_state("refund_status")
        # ORD-1003 has a pending refund
        result = engine.resolve("refund_status", {"order_id": "ORD-1003"}, state)
        assert result.status == "resolved"
        assert "Pending" in result.bot_response or "pending" in result.bot_response.lower()

    def test_order_with_no_refund_resolves_with_message(self, engine):
        state = fresh_state("refund_status")
        # ORD-1001 has no refund
        result = engine.resolve("refund_status", {"order_id": "ORD-1001"}, state)
        assert result.status == "resolved"
        assert "No refund" in result.bot_response or "no refund" in result.bot_response.lower()

    def test_unknown_order_refund_fails(self, engine):
        state = fresh_state("refund_status")
        result = engine.resolve("refund_status", {"order_id": "ORD-9999"}, state)
        assert result.status == "failed"


# ===========================================================================
# 8. Unknown intent
# ===========================================================================

class TestUnknownIntent:
    def test_unrecognised_intent_fails(self, engine):
        state = fresh_state()
        result = engine.resolve("nonexistent_intent_xyz", {}, state)
        assert result.status == "failed"


# ===========================================================================
# 9. ConversationState behaviour
# ===========================================================================

class TestConversationState:
    def test_set_intent_resets_slots(self):
        state = ConversationState()
        state.set_intent("order_status")
        state.collect_slot("order_id", "ORD-1001")
        state.set_intent("return_policy")
        assert state.collected_slots == {}

    def test_collect_slot_stores_value(self):
        state = ConversationState()
        state.collect_slot("order_id", "ORD-1005")
        assert state.collected_slots["order_id"] == "ORD-1005"

    def test_fire_trigger_deduplicates(self):
        state = ConversationState()
        state.fire_trigger("order_not_found")
        state.fire_trigger("order_not_found")
        assert state.escalation_triggers_fired.count("order_not_found") == 1

    def test_to_escalation_session_dict_shape(self):
        state = ConversationState()
        state.record_failure("order_status")
        state.fire_trigger("order_not_found")
        d = state.to_escalation_session_dict()
        assert "failure_counts" in d
        assert "escalation_triggers_fired" in d
        assert "sentiment_score" in d

    def test_advance_flow_step_increments(self):
        state = ConversationState()
        assert state.guided_flow_step == 0
        state.advance_flow_step()
        state.advance_flow_step()
        assert state.guided_flow_step == 2


# ===========================================================================
# 10. End-to-end sample flow (printed with pytest -s)
# ===========================================================================

class TestSampleFlow:
    def test_order_status_full_conversation(self, engine, capsys):
        """Full 3-turn exchange: slot × 2 then resolution. Printed to stdout."""
        print("\n" + "=" * 60)
        print("SAMPLE FLOW: Order Status - ORD-1010 (shipped)")
        print("=" * 60)

        state = ConversationState(ticket_id="demo-ticket")
        state.set_intent("order_status")

        # Turn 1 — user says nothing useful yet
        r1 = engine.resolve("order_status", {}, state)
        state.add_message("bot", r1.bot_response)
        _log("Turn 1 — no slots", r1)
        assert r1.status == "needs_slot"
        assert r1.missing_slot == "order_id"

        # User provides order_id
        state.collect_slot("order_id", "ORD-1010")
        state.add_message("user", "ORD-1010")

        # Turn 2 — order_id present but email missing
        r2 = engine.resolve("order_status", state.collected_slots, state)
        state.add_message("bot", r2.bot_response)
        _log("Turn 2 — order_id only", r2)
        assert r2.status == "needs_slot"
        assert r2.missing_slot == "email"

        # User provides email
        state.collect_slot("email", "joao.pereira@example.com")
        state.add_message("user", "joao.pereira@example.com")

        # Turn 3 — all slots present → resolve
        r3 = engine.resolve("order_status", state.collected_slots, state)
        state.add_message("bot", r3.bot_response)
        _log("Turn 3 — resolved", r3)
        assert r3.status == "resolved"
        assert "ORD-1010" in r3.bot_response

        print("\n  Full bot response:")
        print("  " + _safe(r3.bot_response.replace("\n", "\n  ")))
        print("=" * 60)

    def test_cancel_order_escalation_flow(self, engine, capsys):
        """cancel_order on a shipped order (ORD-1002) → escalation."""
        print("\n" + "=" * 60)
        print("SAMPLE FLOW: Cancel Order - ORD-1002 (already shipped)")
        print("=" * 60)

        state = ConversationState(ticket_id="demo-ticket-cancel")
        state.set_intent("cancel_order")

        # Turn 1 — no order_id yet
        r1 = engine.resolve("cancel_order", {}, state)
        _log("Turn 1 — no slots", r1)
        assert r1.status == "needs_slot"

        state.collect_slot("order_id", "ORD-1002")

        # Turn 2 — order is shipped → escalation
        r2 = engine.resolve("cancel_order", state.collected_slots, state)
        _log("Turn 2 — escalation fired", r2)
        assert r2.status == "failed"
        assert "order_already_shipped" in state.escalation_triggers_fired

        print(f"\n  Triggers fired : {state.escalation_triggers_fired}")
        print(f"  Bot response   : {_safe(r2.bot_response)}")
        print("=" * 60)

    def test_cancel_order_happy_path(self, engine, capsys):
        """Full 4-turn cancel flow for ORD-1001 (processing → cancellable)."""
        print("\n" + "=" * 60)
        print("SAMPLE FLOW: Cancel Order - ORD-1001 (processing, cancellable)")
        print("=" * 60)

        state = ConversationState(ticket_id="demo-happy-cancel")
        state.set_intent("cancel_order")

        r1 = engine.resolve("cancel_order", {}, state)
        _log("Turn 1 — needs order_id", r1)

        state.collect_slot("order_id", "ORD-1001")

        r2 = engine.resolve("cancel_order", state.collected_slots, state)
        _log("Turn 2 — step 0 (confirmation)", r2)
        assert r2.status == "needs_slot"
        assert r2.api_data["expected_input_type"] == "confirmation"

        r3 = engine.resolve("cancel_order", state.collected_slots, state)
        _log("Turn 3 — step 1 (reason choice)", r3)
        assert r3.status == "needs_slot"
        assert r3.api_data["expected_input_type"] == "choice"

        r4 = engine.resolve("cancel_order", state.collected_slots, state)
        _log("Turn 4 — step 2 (final/resolved)", r4)
        assert r4.status == "resolved"

        print("\n  Final message:")
        print("  " + _safe(r4.bot_response.replace("\n", "\n  ")))
        print("=" * 60)

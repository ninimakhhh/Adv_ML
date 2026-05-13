"""
ChatbotOrchestrator — the single entry point for one chatbot turn.

Wires together:  classifier → escalation → resolution → ticket storage

Usage:
    from chatbot.orchestrator import ChatbotOrchestrator, BotTurn
    from chatbot.session.state import ConversationState

    orchestrator = ChatbotOrchestrator()
    state = ConversationState()

    turn = orchestrator.handle_message("where is my order?", state)
    print(turn.bot_response)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.classifier.classifier import ClassificationResult, IntentClassifier
from chatbot.escalation.engine import EscalationDecision, EscalationEngine
from chatbot.prompts.system_persona import (
    ESCALATION_MESSAGES,
    NO_INTENT_RESPONSE,
    PII_WARNING,
    VALIDATION_RETRY_PREFIX,
)
from chatbot.registry.loader import load_intents
from chatbot.resolution.engine import ResolutionEngine, ResolutionResult
from chatbot.session.state import ConversationState
from shared.db.migrate import _DB_PATH
from shared.db.models import Ticket
from shared.db.repository import TicketRepository


@dataclass
class BotTurn:
    bot_response: str
    should_escalate: bool
    escalation_reason: Optional[str]
    ticket_id: str
    debug: dict = field(default_factory=dict)


# Synthetic ClassificationResult used when an intent is already active
def _active_intent_clf(intent_id: str) -> ClassificationResult:
    return ClassificationResult(
        intent_id=intent_id,
        confidence=1.0,
        top_3_alternatives=[],
        reasoning="Continuing active intent from previous turn.",
    )


def _forced_intent_clf(intent_id: str) -> ClassificationResult:
    return ClassificationResult(
        intent_id=intent_id,
        confidence=1.0,
        top_3_alternatives=[],
        reasoning="Intent forced via UI button click.",
    )


class ChatbotOrchestrator:
    def __init__(
        self,
        db_path: Path = _DB_PATH,
        classifier: Optional[IntentClassifier] = None,
    ) -> None:
        self._repo = TicketRepository(db_path)
        self._classifier = classifier or IntentClassifier()
        self._escalation = EscalationEngine()
        self._resolution = ResolutionEngine()
        self._intents = load_intents()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_message(
        self,
        user_message: str,
        state: ConversationState,
        force_intent: Optional[str] = None,
    ) -> BotTurn:

        # (a) Ensure ticket row exists in DB
        self._ensure_ticket(state)

        # (b) Persist user message (auto-redacts PII)
        user_msg_obj = self._repo.add_message(
            state.ticket_id, "user", user_message, apply_redaction=True
        )
        pii_detected = user_msg_obj.is_redacted
        state.add_message("user", user_message)

        # ------------------------------------------------------------------
        # Determine classification
        # ------------------------------------------------------------------

        if force_intent:
            # (3) Button click — jump straight to slot-filling
            state.set_intent(force_intent)
            state.waiting_for_slot = None
            clf = _forced_intent_clf(force_intent)

        elif state.waiting_for_slot is not None:
            # (c) Bot is waiting for a specific slot value or a guided-flow reply
            clf = _active_intent_clf(state.current_intent)
            slot_fill_error = self._handle_slot_input(user_message, state)
            if slot_fill_error:
                # Validation failed — ask again
                return self._emit_bot_turn(
                    slot_fill_error,
                    state,
                    pii_detected,
                    clf,
                    resolution_status="needs_slot",
                )

        else:
            # (d) New message — classify
            clf = self._classifier.classify(user_message, state.history[-6:])
            if clf.intent_id:
                state.set_intent(clf.intent_id)

        # ------------------------------------------------------------------
        # (e) Escalation check — runs before resolution
        # ------------------------------------------------------------------
        esc = self._escalation.decide(clf, user_message, state.to_escalation_session_dict())
        if esc.should_escalate:
            return self._handle_escalation(esc, clf, state, pii_detected)

        # ------------------------------------------------------------------
        # No intent → politely decline
        # ------------------------------------------------------------------
        if not clf.intent_id:
            return self._emit_bot_turn(
                NO_INTENT_RESPONSE,
                state,
                pii_detected,
                clf,
                resolution_status="no_intent",
            )

        # ------------------------------------------------------------------
        # (f) Resolution
        # ------------------------------------------------------------------
        result = self._resolution.resolve(clf.intent_id, state.collected_slots, state)

        # (f-post) Resolution returned failed → re-run escalation with updated triggers
        if result.status == "failed":
            esc2 = self._escalation.decide(clf, user_message, state.to_escalation_session_dict())
            if esc2.should_escalate:
                return self._handle_escalation(esc2, clf, state, pii_detected)
            # Failed without a clear escalation path — generic error
            return self._handle_escalation(
                EscalationDecision(
                    should_escalate=True,
                    reason="escalated_after_failure",
                    handoff_summary=result.bot_response,
                ),
                clf,
                state,
                pii_detected,
            )

        # ------------------------------------------------------------------
        # (g/h) Persist bot response; update ticket on resolve
        # ------------------------------------------------------------------
        bot_text = result.bot_response
        if pii_detected:
            bot_text += PII_WARNING

        self._repo.add_message(state.ticket_id, "bot", bot_text)
        state.add_message("bot", bot_text)

        # Snapshot slots before any reset so the debug dict always carries them
        final_slots = dict(state.collected_slots)

        # Track what slot/step the bot is now waiting for
        state.waiting_for_slot = result.missing_slot  # None when resolved

        if result.status == "resolved":
            self._repo.update_ticket(
                state.ticket_id,
                final_status="resolved",
                resolution_path="bot_resolved",
                resolved_at=datetime.utcnow().isoformat(),
            )
            state.reset_intent()

        return BotTurn(
            bot_response=bot_text,
            should_escalate=False,
            escalation_reason=None,
            ticket_id=state.ticket_id,
            debug={
                "intent_id": clf.intent_id,
                "confidence": clf.confidence,
                "reasoning": clf.reasoning,
                "alternatives": clf.top_3_alternatives,
                "slots": final_slots,
                "resolution_status": result.status,
                "missing_slot": result.missing_slot,
                "guided_flow_step": state.guided_flow_step,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_ticket(self, state: ConversationState) -> None:
        if state.ticket_created:
            return
        ticket = Ticket(
            ticket_id=state.ticket_id,
            channel="chat",
            final_status="open",
            resolution_path="pending",
            tags=[],
        )
        self._repo.create_ticket(ticket)
        state.ticket_created = True

    def _handle_slot_input(
        self, user_message: str, state: ConversationState
    ) -> Optional[str]:
        """
        Try to fill the current waiting_for_slot from user_message.
        Returns None on success, or an error prompt string on validation failure.
        """
        waiting = state.waiting_for_slot

        # Guided-flow step — no slot to fill, just acknowledge and advance
        if waiting and waiting.startswith("guided_step_"):
            state.waiting_for_slot = None
            return None

        # Required slot — find its definition and validate
        intent = self._intents.get(state.current_intent or "", {})
        slot_def = next(
            (s for s in intent.get("required_slots", []) if s["name"] == waiting),
            None,
        )
        if slot_def is None:
            # Unexpected state — just clear and continue
            state.waiting_for_slot = None
            return None

        regex = slot_def.get("validation_regex")
        value = user_message.strip()

        if regex and not re.match(regex, value):
            return VALIDATION_RETRY_PREFIX + slot_def["prompt"]

        state.collect_slot(waiting, value)
        state.waiting_for_slot = None
        return None

    def _handle_escalation(
        self,
        esc: EscalationDecision,
        clf: ClassificationResult,
        state: ConversationState,
        pii_detected: bool,
    ) -> BotTurn:
        reason = esc.reason
        bot_text = ESCALATION_MESSAGES.get(reason, ESCALATION_MESSAGES["default"])
        if pii_detected:
            bot_text += PII_WARNING

        self._repo.add_message(state.ticket_id, "bot", bot_text)
        state.add_message("bot", bot_text)

        self._repo.update_ticket(
            state.ticket_id,
            final_status="in_progress",
            resolution_path=reason,
        )

        return BotTurn(
            bot_response=bot_text,
            should_escalate=True,
            escalation_reason=reason,
            ticket_id=state.ticket_id,
            debug={
                "intent_id": clf.intent_id,
                "confidence": clf.confidence,
                "reasoning": clf.reasoning,
                "escalation_reason": reason,
                "handoff_summary": esc.handoff_summary,
                "slots": dict(state.collected_slots),
            },
        )

    def _emit_bot_turn(
        self,
        bot_text: str,
        state: ConversationState,
        pii_detected: bool,
        clf: ClassificationResult,
        resolution_status: str = "pending",
    ) -> BotTurn:
        """Persist bot message and return BotTurn without touching ticket status."""
        if pii_detected:
            bot_text += PII_WARNING
        self._repo.add_message(state.ticket_id, "bot", bot_text)
        state.add_message("bot", bot_text)
        return BotTurn(
            bot_response=bot_text,
            should_escalate=False,
            escalation_reason=None,
            ticket_id=state.ticket_id,
            debug={
                "intent_id": clf.intent_id,
                "confidence": clf.confidence,
                "resolution_status": resolution_status,
                "slots": dict(state.collected_slots),
            },
        )

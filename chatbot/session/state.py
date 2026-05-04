"""
ConversationState — framework-agnostic session tracker.

Stored in Streamlit via st.session_state["conv_state"] on the frontend,
or held in memory during testing.

Usage:
    from chatbot.session.state import ConversationState

    state = ConversationState(ticket_id="TKT-abc123")
    state.set_intent("order_status")
    state.collect_slot("order_id", "ORD-1001")
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationState:
    ticket_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Current intent being resolved
    current_intent: Optional[str] = None

    # Slots gathered so far for the current intent
    collected_slots: dict[str, str] = field(default_factory=dict)

    # Guided-flow position (0-based step index)
    guided_flow_step: int = 0

    # How many times the bot has failed to resolve each intent this session
    failure_count_per_intent: dict[str, int] = field(default_factory=dict)

    # Triggers that have fired (forwarded to EscalationEngine via session_state)
    escalation_triggers_fired: list[str] = field(default_factory=list)

    # Sentiment score hook (populated by Prompt 7 sentiment module)
    sentiment_score: Optional[float] = None

    # Message history for the current session (role, content)
    history: list[dict[str, str]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def set_intent(self, intent_id: str) -> None:
        if self.current_intent != intent_id:
            self.current_intent = intent_id
            self.collected_slots = {}
            self.guided_flow_step = 0

    def collect_slot(self, name: str, value: str) -> None:
        self.collected_slots[name] = value

    def advance_flow_step(self) -> None:
        self.guided_flow_step += 1

    def record_failure(self, intent_id: str) -> None:
        self.failure_count_per_intent[intent_id] = (
            self.failure_count_per_intent.get(intent_id, 0) + 1
        )

    def fire_trigger(self, trigger: str) -> None:
        if trigger not in self.escalation_triggers_fired:
            self.escalation_triggers_fired.append(trigger)

    def add_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def reset_intent(self) -> None:
        self.current_intent = None
        self.collected_slots = {}
        self.guided_flow_step = 0
        self.escalation_triggers_fired = []

    def to_escalation_session_dict(self) -> dict:
        """Produce the dict format expected by EscalationEngine.decide()."""
        return {
            "failure_counts": self.failure_count_per_intent,
            "escalation_triggers_fired": self.escalation_triggers_fired,
            "sentiment_score": self.sentiment_score,
        }

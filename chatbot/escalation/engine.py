"""
Escalation engine — decides whether a conversation should be routed to a human agent.

Usage:
    from chatbot.escalation.engine import EscalationEngine, EscalationDecision
    from chatbot.classifier.classifier import ClassificationResult

    engine = EscalationEngine()
    decision = engine.decide(classification, user_message, session_state)
    if decision.should_escalate:
        show_agent_handoff(decision.handoff_summary)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.classifier.classifier import ClassificationResult
from chatbot.registry.loader import load_intents

_DEFAULT_CONFIDENCE_THRESHOLD = 0.85

# Rule (b): user explicitly asks for a human
_HANDOFF_KEYWORDS: list[str] = [
    "human", "agent", "person", "real person",
    "speak to someone", "talk to a representative", "talk to someone",
    "live agent", "customer service rep", "real agent",
]

# Rule (c): legal / sensitive — always escalate
_SENSITIVE_KEYWORDS: list[str] = [
    "lawyer", "attorney", "fraud", "chargeback",
    "lawsuit", "sue", "court", "bbb", "consumer protection",
    "trading standards", "ombudsman",
]

_FAILURE_THRESHOLD = 2   # escalate after this many bot failures on same intent


@dataclass
class EscalationDecision:
    should_escalate: bool
    reason: str   # resolution_path enum value or "proceed"
    handoff_summary: str


class EscalationEngine:
    def __init__(self) -> None:
        self._intents = load_intents()

    def decide(
        self,
        classification: ClassificationResult,
        user_message: str,
        session_state: dict[str, Any] | None = None,
    ) -> EscalationDecision:
        state = session_state or {}
        msg_lower = user_message.lower()

        # ----------------------------------------------------------------
        # Rule (b): explicit human-handoff request (highest priority UX)
        # ----------------------------------------------------------------
        if _matches_any(msg_lower, _HANDOFF_KEYWORDS):
            return EscalationDecision(
                should_escalate=True,
                reason="escalated_user_request",
                handoff_summary=_build_summary(
                    classification, user_message, "User explicitly requested a human agent."
                ),
            )

        # ----------------------------------------------------------------
        # Rule (c): legal / sensitive keywords
        # ----------------------------------------------------------------
        if _matches_any(msg_lower, _SENSITIVE_KEYWORDS):
            matched = _first_match(msg_lower, _SENSITIVE_KEYWORDS)
            return EscalationDecision(
                should_escalate=True,
                reason="escalated_sensitive",
                handoff_summary=_build_summary(
                    classification,
                    user_message,
                    f"Sensitive keyword detected: '{matched}'. Requires specialist handling.",
                ),
            )

        # ----------------------------------------------------------------
        # Rule (a): low classification confidence
        # ----------------------------------------------------------------
        threshold = _DEFAULT_CONFIDENCE_THRESHOLD
        if classification.intent_id:
            intent = self._intents.get(classification.intent_id, {})
            threshold = intent.get("confidence_threshold", _DEFAULT_CONFIDENCE_THRESHOLD)

        if classification.confidence < threshold:
            return EscalationDecision(
                should_escalate=True,
                reason="escalated_low_confidence",
                handoff_summary=_build_summary(
                    classification,
                    user_message,
                    f"Classifier confidence {classification.confidence:.2f} is below "
                    f"threshold {threshold:.2f} for intent '{classification.intent_id}'.",
                ),
            )

        # ----------------------------------------------------------------
        # Rule (e): repeated bot failures on same intent in this session
        # ----------------------------------------------------------------
        failure_counts: dict[str, int] = state.get("failure_counts", {})
        if classification.intent_id:
            failures = failure_counts.get(classification.intent_id, 0)
            if failures >= _FAILURE_THRESHOLD:
                return EscalationDecision(
                    should_escalate=True,
                    reason="escalated_after_failure",
                    handoff_summary=_build_summary(
                        classification,
                        user_message,
                        f"Bot failed {failures} time(s) on intent '{classification.intent_id}' in this session.",
                    ),
                )

        # ----------------------------------------------------------------
        # Rule (d): escalation_triggers fired (caller passes fired triggers
        #           in session_state["escalation_triggers_fired"])
        # ----------------------------------------------------------------
        triggers_fired: list[str] = state.get("escalation_triggers_fired", [])
        if triggers_fired and classification.intent_id:
            intent = self._intents.get(classification.intent_id, {})
            registered = set(intent.get("escalation_triggers", []))
            fired_matches = [t for t in triggers_fired if t in registered]
            if fired_matches:
                return EscalationDecision(
                    should_escalate=True,
                    reason="escalated_after_failure",
                    handoff_summary=_build_summary(
                        classification,
                        user_message,
                        f"Escalation trigger(s) fired: {', '.join(fired_matches)}.",
                    ),
                )

        # ----------------------------------------------------------------
        # Rule (f): strongly negative sentiment hook (Prompt 7)
        # ----------------------------------------------------------------
        sentiment_score: float | None = state.get("sentiment_score")
        if sentiment_score is not None and sentiment_score < -0.7:
            return EscalationDecision(
                should_escalate=True,
                reason="escalated_user_request",
                handoff_summary=_build_summary(
                    classification,
                    user_message,
                    f"Strongly negative sentiment detected (score={sentiment_score:.2f}).",
                ),
            )

        # ----------------------------------------------------------------
        # All clear — proceed with bot resolution
        # ----------------------------------------------------------------
        return EscalationDecision(
            should_escalate=False,
            reason="proceed",
            handoff_summary="",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches_any(text: str, keywords: list[str]) -> bool:
    for kw in keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', text):
            return True
    return False


def _first_match(text: str, keywords: list[str]) -> str:
    for kw in keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', text):
            return kw
    return ""


def _build_summary(
    clf: ClassificationResult,
    user_message: str,
    escalation_note: str,
) -> str:
    lines = [
        f"Escalation reason: {escalation_note}",
        f"Last user message: \"{user_message}\"",
        f"Detected intent: {clf.intent_id or 'unknown'} "
        f"(confidence: {clf.confidence:.2f})",
        f"Classifier reasoning: {clf.reasoning}",
    ]
    if clf.top_3_alternatives:
        alts = ", ".join(f"{i} ({c:.2f})" for i, c in clf.top_3_alternatives)
        lines.append(f"Alternatives considered: {alts}")
    return "\n".join(lines)

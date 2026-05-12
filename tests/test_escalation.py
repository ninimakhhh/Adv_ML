"""
Tests for EscalationEngine — pure unit tests, no LLM calls.

Run:
    pytest tests/test_escalation.py -v
"""

from __future__ import annotations

import pytest

from chatbot.classifier.classifier import ClassificationResult
from chatbot.escalation.engine import EscalationDecision, EscalationEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    return EscalationEngine()


def _result(
    intent_id="order_status",
    confidence=0.90,
    alternatives=None,
    reasoning="test",
) -> ClassificationResult:
    return ClassificationResult(
        intent_id=intent_id,
        confidence=confidence,
        top_3_alternatives=alternatives or [],
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Rule (a) — Low confidence
# ---------------------------------------------------------------------------

class TestLowConfidence:
    def test_confidence_below_threshold_escalates(self, engine):
        clf = _result(intent_id="order_status", confidence=0.45)
        decision = engine.decide(clf, "uhh something about my order", {})
        assert decision.should_escalate is True
        assert decision.reason == "escalated_low_confidence"

    def test_confidence_exactly_at_threshold_does_not_escalate(self, engine):
        # order_status threshold is 0.70; 0.70 should NOT escalate (it's >= threshold)
        clf = _result(intent_id="order_status", confidence=0.70)
        decision = engine.decide(clf, "where is my order", {})
        assert decision.should_escalate is False

    def test_confidence_above_threshold_proceeds(self, engine):
        clf = _result(intent_id="order_status", confidence=0.92)
        decision = engine.decide(clf, "where is my order", {})
        assert decision.should_escalate is False
        assert decision.reason == "proceed"

    def test_none_intent_with_low_confidence_escalates(self, engine):
        clf = _result(intent_id=None, confidence=0.20)
        decision = engine.decide(clf, "something completely unclear", {})
        assert decision.should_escalate is True
        assert decision.reason == "escalated_low_confidence"

    def test_cancel_order_uses_its_own_threshold(self, engine):
        # cancel_order.json has confidence_threshold: 0.75
        clf = _result(intent_id="cancel_order", confidence=0.72)
        decision = engine.decide(clf, "cancel my order", {})
        assert decision.should_escalate is True
        assert decision.reason == "escalated_low_confidence"

    def test_cancel_order_above_own_threshold_proceeds(self, engine):
        clf = _result(intent_id="cancel_order", confidence=0.80)
        decision = engine.decide(clf, "cancel my order", {})
        assert decision.should_escalate is False


# ---------------------------------------------------------------------------
# Rule (b) — Explicit human-handoff keywords
# ---------------------------------------------------------------------------

class TestExplicitHumanRequest:
    @pytest.mark.parametrize("message", [
        "I want to speak to a human",
        "let me talk to a real person",
        "can I speak to an agent?",
        "I need a human",
        "connect me to a person please",
        "I want to talk to someone",
        "get me a live agent",
    ])
    def test_handoff_keywords_escalate_regardless_of_confidence(self, engine, message):
        # Even with high confidence, user request wins
        clf = _result(intent_id="order_status", confidence=0.99)
        decision = engine.decide(clf, message, {})
        assert decision.should_escalate is True
        assert decision.reason == "escalated_user_request"

    def test_handoff_in_compound_sentence(self, engine):
        clf = _result(intent_id="order_status", confidence=0.85)
        decision = engine.decide(clf, "my order is late and I want to talk to a human agent now", {})
        assert decision.should_escalate is True
        assert decision.reason == "escalated_user_request"

    def test_no_handoff_keyword_does_not_trigger(self, engine):
        clf = _result(intent_id="order_status", confidence=0.91)
        decision = engine.decide(clf, "where is my order #1234", {})
        assert decision.should_escalate is False


# ---------------------------------------------------------------------------
# Rule (c) — Legal / sensitive keywords
# ---------------------------------------------------------------------------

class TestSensitiveKeywords:
    @pytest.mark.parametrize("message,expected_kw", [
        ("I'll call my lawyer if this isn't resolved", "lawyer"),
        ("my attorney will be in touch", "attorney"),
        ("this is fraud, I'm reporting you", "fraud"),
        ("I'm filing a chargeback with my bank", "chargeback"),
        ("I'm going to sue this company", "sue"),
        ("I'll take this to court", "court"),
        ("I'm reporting this to the BBB", "bbb"),
        ("I'm contacting consumer protection", "consumer protection"),
    ])
    def test_sensitive_keyword_escalates(self, engine, message, expected_kw):
        clf = _result(intent_id="order_status", confidence=0.88)
        decision = engine.decide(clf, message, {})
        assert decision.should_escalate is True
        assert decision.reason == "escalated_sensitive"
        assert expected_kw in decision.handoff_summary.lower()

    def test_sensitive_escalation_overrides_high_confidence(self, engine):
        clf = _result(intent_id="return_policy", confidence=0.97)
        decision = engine.decide(clf, "I want a refund or I'm filing a lawsuit", {})
        assert decision.should_escalate is True
        assert decision.reason == "escalated_sensitive"

    def test_lawyer_in_different_contexts(self, engine):
        clf = _result(intent_id="order_status", confidence=0.91)
        decision = engine.decide(clf, "I'm talking to my lawyer about this situation", {})
        assert decision.should_escalate is True


# ---------------------------------------------------------------------------
# Rule (e) — Repeated bot failures
# ---------------------------------------------------------------------------

class TestRepeatedFailures:
    def test_two_failures_escalates(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"failure_counts": {"order_status": 2}}
        decision = engine.decide(clf, "where is my order", state)
        assert decision.should_escalate is True
        assert decision.reason == "escalated_after_failure"

    def test_one_failure_does_not_escalate(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"failure_counts": {"order_status": 1}}
        decision = engine.decide(clf, "where is my order", state)
        assert decision.should_escalate is False

    def test_zero_failures_does_not_escalate(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"failure_counts": {}}
        decision = engine.decide(clf, "where is my order", state)
        assert decision.should_escalate is False

    def test_failures_for_different_intent_not_counted(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"failure_counts": {"cancel_order": 5}}
        decision = engine.decide(clf, "where is my order", state)
        assert decision.should_escalate is False

    def test_three_failures_also_escalates(self, engine):
        clf = _result(intent_id="cancel_order", confidence=0.80)
        state = {"failure_counts": {"cancel_order": 3}}
        decision = engine.decide(clf, "cancel my order", state)
        assert decision.should_escalate is True
        assert decision.reason == "escalated_after_failure"

    def test_empty_session_state_defaults_to_zero_failures(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        decision = engine.decide(clf, "track my order", {})
        assert decision.should_escalate is False


# ---------------------------------------------------------------------------
# Rule (d) — Escalation triggers from intent registry
# ---------------------------------------------------------------------------

class TestEscalationTriggers:
    def test_registered_trigger_fired_escalates(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"escalation_triggers_fired": ["order_not_found"]}
        decision = engine.decide(clf, "where is my order", state)
        assert decision.should_escalate is True

    def test_unregistered_trigger_does_not_escalate(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"escalation_triggers_fired": ["some_random_trigger"]}
        decision = engine.decide(clf, "where is my order", state)
        assert decision.should_escalate is False

    def test_empty_triggers_list_does_not_escalate(self, engine):
        clf = _result(intent_id="cancel_order", confidence=0.82)
        state = {"escalation_triggers_fired": []}
        decision = engine.decide(clf, "cancel my order", state)
        assert decision.should_escalate is False


# ---------------------------------------------------------------------------
# Rule (f) — Sentiment hook
# ---------------------------------------------------------------------------

class TestSentimentHook:
    def test_strongly_negative_sentiment_escalates(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"sentiment_score": -0.85}
        decision = engine.decide(clf, "this is absolutely terrible", state)
        assert decision.should_escalate is True

    def test_mildly_negative_sentiment_does_not_escalate(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"sentiment_score": -0.50}
        decision = engine.decide(clf, "a bit frustrated", state)
        assert decision.should_escalate is False

    def test_none_sentiment_does_not_escalate(self, engine):
        clf = _result(intent_id="order_status", confidence=0.88)
        state = {"sentiment_score": None}
        decision = engine.decide(clf, "where is my order", state)
        assert decision.should_escalate is False


# ---------------------------------------------------------------------------
# Handoff summary content
# ---------------------------------------------------------------------------

class TestHandoffSummary:
    def test_summary_contains_user_message(self, engine):
        clf = _result(intent_id="order_status", confidence=0.30)
        decision = engine.decide(clf, "I'm confused about my purchase", {})
        assert "I'm confused about my purchase" in decision.handoff_summary

    def test_summary_contains_intent(self, engine):
        clf = _result(intent_id="order_status", confidence=0.30)
        decision = engine.decide(clf, "help", {})
        assert "order_status" in decision.handoff_summary

    def test_no_escalation_has_empty_summary(self, engine):
        clf = _result(intent_id="order_status", confidence=0.91)
        decision = engine.decide(clf, "where is my order", {})
        assert decision.handoff_summary == ""


# ---------------------------------------------------------------------------
# Priority ordering — ensure user_request beats low_confidence
# ---------------------------------------------------------------------------

class TestRulePriority:
    def test_user_request_beats_low_confidence(self, engine):
        clf = _result(intent_id="order_status", confidence=0.20)
        decision = engine.decide(clf, "I want to speak to a real agent please", {})
        assert decision.reason == "escalated_user_request"

    def test_sensitive_beats_low_confidence(self, engine):
        clf = _result(intent_id=None, confidence=0.10)
        decision = engine.decide(clf, "I'll call my lawyer and file a lawsuit", {})
        assert decision.reason == "escalated_sensitive"

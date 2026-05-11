"""
Tests for IntentClassifier — LLMClient is mocked throughout.

Run:
    pytest tests/test_classifier.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chatbot.classifier.classifier import (
    ClassificationResult,
    IntentClassifier,
    _parse_response,
)
from chatbot.registry.loader import load_intents


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm(intent_id, confidence, alternatives=None, reasoning="test") -> MagicMock:
    """Return a mock LLMClient whose .chat() returns a pre-built dict."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {
        "intent_id": intent_id,
        "confidence": confidence,
        "alternatives": alternatives or [],
        "reasoning": reasoning,
    }
    return mock_llm


def _set_reply(mock_llm, intent_id, confidence, alternatives=None, reasoning="test"):
    mock_llm.chat.return_value = {
        "intent_id": intent_id,
        "confidence": confidence,
        "alternatives": alternatives or [],
        "reasoning": reasoning,
    }


@pytest.fixture
def intents():
    return load_intents()


@pytest.fixture
def classifier():
    """IntentClassifier backed by a mock LLMClient — no real API calls."""
    mock_llm = MagicMock()
    clf = IntentClassifier(llm=mock_llm)
    clf._mock_llm = mock_llm
    return clf


# ---------------------------------------------------------------------------
# Basic classification
# ---------------------------------------------------------------------------

class TestClassifyOrderStatus:
    def test_clear_order_query_maps_to_order_status(self, classifier):
        _set_reply(classifier._mock_llm, "order_status", 0.95,
                   reasoning="Exact match to order tracking utterances.")
        result = classifier.classify("where is my order #1234")
        assert result.intent_id == "order_status"
        assert result.confidence > 0.70

    def test_result_is_classification_result(self, classifier):
        _set_reply(classifier._mock_llm, "order_status", 0.88)
        result = classifier.classify("track my package")
        assert isinstance(result, ClassificationResult)

    def test_confidence_is_clamped_between_0_and_1(self, classifier):
        _set_reply(classifier._mock_llm, "order_status", 1.5)
        result = classifier.classify("status of my delivery")
        assert 0.0 <= result.confidence <= 1.0

    def test_reasoning_is_non_empty_string(self, classifier):
        _set_reply(classifier._mock_llm, "order_status", 0.92,
                   reasoning="Matched order tracking examples.")
        result = classifier.classify("has my order shipped?")
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0


class TestVariedPhrasings:
    @pytest.mark.parametrize("message", [
        "track my package",
        "when will my stuff arrive",
        "where is my delivery",
        "what's the status of my shipment",
        "my order hasn't arrived yet, can you check",
    ])
    def test_order_status_phrasings(self, classifier, message):
        _set_reply(classifier._mock_llm, "order_status", 0.91)
        result = classifier.classify(message)
        assert result.intent_id == "order_status"
        assert result.confidence > 0.70


class TestGibberish:
    def test_gibberish_returns_low_confidence(self, classifier):
        _set_reply(classifier._mock_llm, None, 0.12,
                   reasoning="No recognisable intent.")
        result = classifier.classify("aslkdjflaksjdf zxcvqwer")
        assert result.confidence < 0.50

    def test_gibberish_intent_id_is_none(self, classifier):
        _set_reply(classifier._mock_llm, None, 0.08)
        result = classifier.classify("qwerty uiop 12345 !@#$")
        assert result.intent_id is None

    def test_unknown_domain_low_confidence(self, classifier):
        _set_reply(classifier._mock_llm, None, 0.15,
                   reasoning="Unrelated to e-commerce support.")
        result = classifier.classify("What is the capital of France?")
        assert result.confidence < 0.50
        assert result.intent_id is None


class TestAlternatives:
    def test_alternatives_are_valid_intent_ids(self, classifier, intents):
        alts = [
            {"intent_id": "refund_status", "confidence": 0.55},
            {"intent_id": "cancel_order", "confidence": 0.30},
        ]
        _set_reply(classifier._mock_llm, "order_status", 0.85, alternatives=alts)
        result = classifier.classify("I want to check on my purchase")
        for alt_id, alt_conf in result.top_3_alternatives:
            assert alt_id in intents
            assert 0.0 <= alt_conf <= 1.0

    def test_top_intent_not_in_alternatives(self, classifier):
        alts = [
            {"intent_id": "order_status", "confidence": 0.80},  # duplicate — should be dropped
            {"intent_id": "refund_status", "confidence": 0.55},
        ]
        _set_reply(classifier._mock_llm, "order_status", 0.90, alternatives=alts)
        result = classifier.classify("track my order")
        alt_ids = [a[0] for a in result.top_3_alternatives]
        assert "order_status" not in alt_ids


class TestInvalidModelResponse:
    def test_error_dict_returns_fallback(self, classifier):
        classifier._mock_llm.chat.return_value = {"error": "JSON parse failed", "raw": "bad"}
        result = classifier.classify("hello")
        assert result.intent_id is None
        assert result.confidence == 0.0
        assert "API error" in result.reasoning

    def test_unknown_intent_id_treated_as_none(self, classifier):
        _set_reply(classifier._mock_llm, "nonexistent_intent_xyz", 0.88)
        result = classifier.classify("some message")
        assert result.intent_id is None

    def test_api_exception_returns_fallback(self, classifier):
        classifier._mock_llm.chat.side_effect = RuntimeError("network error")
        result = classifier.classify("where is my order")
        assert result.intent_id is None
        assert result.confidence == 0.0
        assert "API error" in result.reasoning


class TestConversationContext:
    def test_context_does_not_crash_classifier(self, classifier):
        _set_reply(classifier._mock_llm, "order_status", 0.88)
        context = [
            {"role": "user", "content": "Hi"},
            {"role": "bot", "content": "Hello! How can I help?"},
        ]
        result = classifier.classify("track my order please",
                                     conversation_context=context)
        assert result.intent_id == "order_status"

    def test_empty_context_works(self, classifier):
        _set_reply(classifier._mock_llm, "shipping_info", 0.82)
        result = classifier.classify("how much is shipping?",
                                     conversation_context=[])
        assert result.intent_id == "shipping_info"


# ---------------------------------------------------------------------------
# _parse_response unit tests (no LLM call)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_dict_parsed_correctly(self, intents):
        data = {
            "intent_id": "return_policy",
            "confidence": 0.87,
            "alternatives": [{"intent_id": "refund_status", "confidence": 0.45}],
            "reasoning": "Matches return policy examples.",
        }
        result = _parse_response(data, intents)
        assert result.intent_id == "return_policy"
        assert result.confidence == pytest.approx(0.87)
        assert result.top_3_alternatives[0][0] == "refund_status"

    def test_null_intent_preserved(self, intents):
        data = {"intent_id": None, "confidence": 0.1, "alternatives": [],
                "reasoning": "no match"}
        result = _parse_response(data, intents)
        assert result.intent_id is None

    def test_error_dict_returns_api_error_reasoning(self, intents):
        data = {"error": "timeout", "raw": ""}
        result = _parse_response(data, intents)
        assert result.intent_id is None
        assert "API error" in result.reasoning

    def test_unknown_intent_id_becomes_none(self, intents):
        data = {"intent_id": "totally_fake", "confidence": 0.9,
                "alternatives": [], "reasoning": "fake"}
        result = _parse_response(data, intents)
        assert result.intent_id is None

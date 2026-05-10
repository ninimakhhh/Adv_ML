"""
Tests for IntentClassifier — Gemini API is mocked throughout.

Run:
    pytest tests/test_classifier.py -v
"""

from __future__ import annotations

import json
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

def _mock_response(intent_id, confidence, alternatives=None, reasoning="test"):
    """Build a fake Gemini response object."""
    payload = {
        "intent_id": intent_id,
        "confidence": confidence,
        "alternatives": alternatives or [],
        "reasoning": reasoning,
    }
    response = MagicMock()
    response.text = json.dumps(payload)
    return response


@pytest.fixture
def intents():
    return load_intents()


@pytest.fixture
def classifier():
    """IntentClassifier with a mocked Gemini client."""
    with patch("chatbot.classifier.classifier.genai.Client") as MockClientClass:
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client
        clf = IntentClassifier(api_key="fake-key")
        clf._mock_client = mock_client
        yield clf


def _set_reply(classifier, intent_id, confidence, alternatives=None, reasoning="test"):
    """Configure what the mock Gemini client will return for the next call."""
    classifier._mock_client.models.generate_content.return_value = _mock_response(
        intent_id, confidence, alternatives, reasoning
    )


# ---------------------------------------------------------------------------
# Basic classification
# ---------------------------------------------------------------------------

class TestClassifyOrderStatus:
    def test_clear_order_query_maps_to_order_status(self, classifier):
        _set_reply(classifier, "order_status", 0.95, reasoning="Exact match to order tracking utterances.")
        result = classifier.classify("where is my order #1234")
        assert result.intent_id == "order_status"
        assert result.confidence > 0.70

    def test_result_is_classification_result(self, classifier):
        _set_reply(classifier, "order_status", 0.88)
        result = classifier.classify("track my package")
        assert isinstance(result, ClassificationResult)

    def test_confidence_is_clamped_between_0_and_1(self, classifier):
        _set_reply(classifier, "order_status", 1.5)
        result = classifier.classify("status of my delivery")
        assert 0.0 <= result.confidence <= 1.0

    def test_reasoning_is_non_empty_string(self, classifier):
        _set_reply(classifier, "order_status", 0.92, reasoning="Matched order tracking examples.")
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
        _set_reply(classifier, "order_status", 0.91)
        result = classifier.classify(message)
        assert result.intent_id == "order_status"
        assert result.confidence > 0.70


class TestGibberish:
    def test_gibberish_returns_low_confidence(self, classifier):
        _set_reply(classifier, None, 0.12, reasoning="No recognisable intent.")
        result = classifier.classify("aslkdjflaksjdf zxcvqwer")
        assert result.confidence < 0.50

    def test_gibberish_intent_id_is_none(self, classifier):
        _set_reply(classifier, None, 0.08)
        result = classifier.classify("qwerty uiop 12345 !@#$")
        assert result.intent_id is None

    def test_unknown_domain_low_confidence(self, classifier):
        _set_reply(classifier, None, 0.15, reasoning="Unrelated to e-commerce support.")
        result = classifier.classify("What is the capital of France?")
        assert result.confidence < 0.50
        assert result.intent_id is None


class TestAlternatives:
    def test_alternatives_are_valid_intent_ids(self, classifier, intents):
        alts = [
            {"intent_id": "refund_status", "confidence": 0.55},
            {"intent_id": "cancel_order", "confidence": 0.30},
        ]
        _set_reply(classifier, "order_status", 0.85, alternatives=alts)
        result = classifier.classify("I want to check on my purchase")
        for alt_id, alt_conf in result.top_3_alternatives:
            assert alt_id in intents
            assert 0.0 <= alt_conf <= 1.0

    def test_top_intent_not_in_alternatives(self, classifier):
        alts = [
            {"intent_id": "order_status", "confidence": 0.80},  # same as top — should be dropped
            {"intent_id": "refund_status", "confidence": 0.55},
        ]
        _set_reply(classifier, "order_status", 0.90, alternatives=alts)
        result = classifier.classify("track my order")
        alt_ids = [a[0] for a in result.top_3_alternatives]
        assert "order_status" not in alt_ids


class TestInvalidModelResponse:
    def test_json_parse_failure_returns_fallback(self, classifier):
        bad_response = MagicMock()
        bad_response.text = "not json at all"
        classifier._mock_client.models.generate_content.return_value = bad_response
        result = classifier.classify("hello")
        assert result.intent_id is None
        assert result.confidence == 0.0

    def test_unknown_intent_id_in_response_treated_as_none(self, classifier):
        _set_reply(classifier, "nonexistent_intent_xyz", 0.88)
        result = classifier.classify("some message")
        assert result.intent_id is None

    def test_api_exception_returns_fallback(self, classifier):
        classifier._mock_client.models.generate_content.side_effect = RuntimeError("network error")
        result = classifier.classify("where is my order")
        assert result.intent_id is None
        assert result.confidence == 0.0
        assert "API error" in result.reasoning


class TestConversationContext:
    def test_context_does_not_crash_classifier(self, classifier):
        _set_reply(classifier, "order_status", 0.88)
        context = [
            {"role": "user", "content": "Hi"},
            {"role": "bot", "content": "Hello! How can I help?"},
        ]
        result = classifier.classify("track my order please", conversation_context=context)
        assert result.intent_id == "order_status"

    def test_empty_context_works(self, classifier):
        _set_reply(classifier, "shipping_info", 0.82)
        result = classifier.classify("how much is shipping?", conversation_context=[])
        assert result.intent_id == "shipping_info"


# ---------------------------------------------------------------------------
# _parse_response unit tests (no API call needed)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json_parsed_correctly(self, intents):
        raw = json.dumps({
            "intent_id": "return_policy",
            "confidence": 0.87,
            "alternatives": [{"intent_id": "refund_status", "confidence": 0.45}],
            "reasoning": "Matches return policy examples.",
        })
        result = _parse_response(raw, intents)
        assert result.intent_id == "return_policy"
        assert result.confidence == pytest.approx(0.87)
        assert result.top_3_alternatives[0][0] == "refund_status"

    def test_markdown_fences_stripped(self, intents):
        raw = "```json\n{\"intent_id\": \"cancel_order\", \"confidence\": 0.91, \"alternatives\": [], \"reasoning\": \"ok\"}\n```"
        result = _parse_response(raw, intents)
        assert result.intent_id == "cancel_order"

    def test_null_intent_preserved(self, intents):
        raw = json.dumps({"intent_id": None, "confidence": 0.1, "alternatives": [], "reasoning": "no match"})
        result = _parse_response(raw, intents)
        assert result.intent_id is None

    def test_invalid_json_returns_fallback(self, intents):
        result = _parse_response("{broken json", intents)
        assert result.intent_id is None
        assert result.confidence == 0.0

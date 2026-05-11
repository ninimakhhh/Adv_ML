"""Unit tests for ticket_routing/classifier.py"""

import pytest
from unittest.mock import patch, MagicMock

from ticket_routing.classifier import classify_ticket, TicketClassification, CATEGORY_TO_QUEUE


class TestClassifyTicket:
    """Test the classify_ticket function with mocked Claude API."""

    def _create_mock_response(self, category, sentiment, urgency, confidence=85, reasoning="Test"):
        """Helper to create mock API response."""
        mock_response = MagicMock()
        
        # Create a tool_use block
        tool_use = MagicMock()
        tool_use.type = "tool_use"
        tool_use.input = {
            "category": category,
            "sentiment": sentiment,
            "urgency": urgency,
            "confidence": confidence,
            "reasoning": reasoning,
        }
        
        mock_response.content = [tool_use]
        mock_response.stop_reason = "tool_use"
        
        return mock_response

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_shipping_issue(self, mock_client):
        """Test classifying a shipping issue ticket."""
        mock_response = self._create_mock_response(
            category="Shipping",
            sentiment="Negative",
            urgency="High",
            confidence=92,
            reasoning="Customer reports delayed delivery with urgency"
        )
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = classify_ticket(
            subject="Order not arrived",
            raw_text="I ordered yesterday and it still hasn't arrived. This is urgent!"
        )
        
        assert isinstance(result, TicketClassification)
        assert result.category == "Shipping"
        assert result.sentiment == "Negative"
        assert result.urgency == "High"
        assert result.confidence == 92
        assert result.assigned_queue == "Logistics"

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_bug_report(self, mock_client):
        """Test classifying a bug report ticket."""
        mock_response = self._create_mock_response(
            category="Bug",
            sentiment="Negative",
            urgency="High",
            confidence=88,
            reasoning="Application crash reported"
        )
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = classify_ticket(
            subject="App crashes on startup",
            raw_text="The app crashes immediately when I open it"
        )
        
        assert result.category == "Bug"
        assert result.assigned_queue == "Technical Support"
        assert result.urgency == "High"

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_return_request(self, mock_client):
        """Test classifying a return request."""
        mock_response = self._create_mock_response(
            category="Returns",
            sentiment="Neutral",
            urgency="Medium",
            confidence=90,
            reasoning="Customer requesting return of item"
        )
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = classify_ticket(
            subject="Want to return my order",
            raw_text="I received the wrong item and would like to return it"
        )
        
        assert result.category == "Returns"
        assert result.assigned_queue == "Returns"
        assert result.sentiment == "Neutral"

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_payment_issue(self, mock_client):
        """Test classifying a payment issue."""
        mock_response = self._create_mock_response(
            category="Payments",
            sentiment="Negative",
            urgency="High",
            confidence=87,
            reasoning="Customer reporting card decline"
        )
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = classify_ticket(
            subject="Payment declined",
            raw_text="My card keeps getting declined but I have funds"
        )
        
        assert result.category == "Payments"
        assert result.assigned_queue == "Payments"
        assert result.urgency == "High"

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_generic_query(self, mock_client):
        """Test classifying a generic query."""
        mock_response = self._create_mock_response(
            category="Other",
            sentiment="Positive",
            urgency="Low",
            confidence=75,
            reasoning="General inquiry without specific category"
        )
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = classify_ticket(
            subject="Question about store hours",
            raw_text="What are your store hours?"
        )
        
        assert result.category == "Other"
        assert result.assigned_queue == "General"
        assert result.sentiment == "Positive"

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_no_tool_call(self, mock_client):
        """Test error handling when model doesn't call tool."""
        mock_response = MagicMock()
        mock_response.content = []  # No tool_use block
        mock_response.stop_reason = "end_turn"
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        with pytest.raises(RuntimeError, match="did not call the classify_ticket tool"):
            classify_ticket("Subject", "Raw text")

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_high_confidence(self, mock_client):
        """Test classification with high confidence."""
        mock_response = self._create_mock_response(
            category="Shipping",
            sentiment="Negative",
            urgency="High",
            confidence=99,
            reasoning="Clear shipping delay"
        )
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = classify_ticket("No delivery", "Haven't received my order")
        
        assert result.confidence == 99

    @patch("ticket_routing.classifier.get_anthropic_client")
    def test_classify_low_confidence(self, mock_client):
        """Test classification with low confidence."""
        mock_response = self._create_mock_response(
            category="Other",
            sentiment="Neutral",
            urgency="Low",
            confidence=45,
            reasoning="Ambiguous ticket"
        )
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = classify_ticket("Unclear", "Some unclear message")
        
        assert result.confidence == 45


class TestTicketClassificationDataclass:
    """Test the TicketClassification dataclass."""

    def test_dataclass_creation(self):
        """Test creating a TicketClassification instance."""
        result = TicketClassification(
            category="Bug",
            confidence=90,
            sentiment="Negative",
            urgency="High",
            assigned_queue="Technical Support",
            reasoning="App crash"
        )
        
        assert result.category == "Bug"
        assert result.confidence == 90
        assert result.sentiment == "Negative"
        assert result.urgency == "High"

    def test_category_to_queue_mapping(self):
        """Test that all categories map to valid queues."""
        for category, queue in CATEGORY_TO_QUEUE.items():
            assert isinstance(queue, str)
            assert len(queue) > 0

    def test_all_categories_have_queues(self):
        """Test that all CATEGORIES have queue mappings."""
        from ticket_routing.classifier import CATEGORIES
        
        for category in CATEGORIES:
            assert category in CATEGORY_TO_QUEUE


class TestCategoryToQueueMapping:
    """Test CATEGORY_TO_QUEUE constant."""

    def test_bug_maps_to_technical_support(self):
        """Test Bug category mapping."""
        assert CATEGORY_TO_QUEUE["Bug"] == "Technical Support"

    def test_shipping_maps_to_logistics(self):
        """Test Shipping category mapping."""
        assert CATEGORY_TO_QUEUE["Shipping"] == "Logistics"

    def test_returns_maps_to_returns(self):
        """Test Returns category mapping."""
        assert CATEGORY_TO_QUEUE["Returns"] == "Returns"

    def test_payments_maps_to_payments(self):
        """Test Payments category mapping."""
        assert CATEGORY_TO_QUEUE["Payments"] == "Payments"

    def test_other_maps_to_general(self):
        """Test Other category mapping."""
        assert CATEGORY_TO_QUEUE["Other"] == "General"

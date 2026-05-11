"""Unit tests for sentiment_analysis/analyzer.py"""

import json
import pytest
from unittest.mock import patch, MagicMock

from sentiment_analysis.analyzer import analyse_text, AspectSentiment


class TestAnalyseText:
    """Test the analyse_text function with mocked DeepSeek API."""

    @patch("sentiment_analysis.analyzer.get_deepseek_client")
    def test_valid_response(self, mock_client):
        """Test with valid JSON response from API."""
        # Mock the API response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "delivery": 0.5,
            "quality": 0.8,
            "accuracy": -0.3,
            "packaging": 0.2,
            "customer_service": 0.6,
            "value": -0.1,
            "dominant_problem": "none",
            "overall_sentiment": "Positive",
            "severity": "low",
            "summary": "Good product overall",
            "confidence": 85
        })
        
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        # Call the function
        result = analyse_text("Great product!")
        
        # Assert
        assert isinstance(result, AspectSentiment)
        assert result.overall_sentiment == "Positive"
        assert result.delivery == 0.5
        assert result.quality == 0.8
        assert result.confidence == 85

    @patch("sentiment_analysis.analyzer.get_deepseek_client")
    def test_negative_sentiment(self, mock_client):
        """Test with negative sentiment response."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "delivery": -0.9,
            "quality": -0.7,
            "accuracy": 0.0,
            "packaging": -0.5,
            "customer_service": -0.8,
            "value": -0.9,
            "dominant_problem": "poor_quality",
            "overall_sentiment": "Negative",
            "severity": "high",
            "summary": "Product broke after one week",
            "confidence": 92
        })
        
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = analyse_text("This product is broken")
        
        assert result.overall_sentiment == "Negative"
        assert result.severity == "high"
        assert result.dominant_problem == "poor_quality"
        assert result.delivery == -0.9

    @patch("sentiment_analysis.analyzer.get_deepseek_client")
    def test_invalid_json_response(self, mock_client):
        """Test error handling for invalid JSON response."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "This is not valid JSON"
        
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Model did not return valid JSON"):
            analyse_text("Some text")

    @patch("sentiment_analysis.analyzer.get_deepseek_client")
    def test_api_call_failure(self, mock_client):
        """Test error handling for API call failure."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.side_effect = Exception("API Error")
        mock_client.return_value = mock_client_instance

        # Should raise the exception
        with pytest.raises(Exception, match="API Error"):
            analyse_text("Some text")

    @patch("sentiment_analysis.analyzer.get_deepseek_client")
    def test_neutral_sentiment(self, mock_client):
        """Test with neutral sentiment response."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "delivery": 0.0,
            "quality": 0.1,
            "accuracy": -0.1,
            "packaging": 0.0,
            "customer_service": 0.05,
            "value": 0.0,
            "dominant_problem": "none",
            "overall_sentiment": "Neutral",
            "severity": "low",
            "summary": "Product is okay, nothing special",
            "confidence": 70
        })
        
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = analyse_text("It works I guess")
        
        assert result.overall_sentiment == "Neutral"
        assert result.confidence == 70

    @patch("sentiment_analysis.analyzer.get_deepseek_client")
    def test_aspect_scores_can_be_none(self, mock_client):
        """Test that aspect scores can be None when not mentioned."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "delivery": None,
            "quality": 0.8,
            "accuracy": None,
            "packaging": None,
            "customer_service": 0.5,
            "value": 0.3,
            "dominant_problem": "none",
            "overall_sentiment": "Positive",
            "severity": "low",
            "summary": "Good quality",
            "confidence": 80
        })
        
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = analyse_text("Good quality product")
        
        assert result.delivery is None
        assert result.quality == 0.8
        assert result.accuracy is None
        assert result.customer_service == 0.5


class TestAspectSentimentDataclass:
    """Test the AspectSentiment dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = AspectSentiment(
            delivery=0.5,
            quality=0.8,
            accuracy=-0.3,
            packaging=0.2,
            customer_service=0.6,
            value=-0.1,
            dominant_problem="none",
            overall_sentiment="Positive",
            severity="low",
            summary="Good product",
            confidence=85
        )
        
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["delivery"] == 0.5
        assert d["overall_sentiment"] == "Positive"
        assert d["confidence"] == 85

    def test_dataclass_fields(self):
        """Test that all required fields are present."""
        result = AspectSentiment(
            delivery=0.5,
            quality=0.8,
            accuracy=-0.3,
            packaging=0.2,
            customer_service=0.6,
            value=-0.1,
            dominant_problem="poor_quality",
            overall_sentiment="Negative",
            severity="high",
            summary="Bad product",
            confidence=90
        )
        
        assert hasattr(result, "delivery")
        assert hasattr(result, "quality")
        assert hasattr(result, "accuracy")
        assert hasattr(result, "packaging")
        assert hasattr(result, "customer_service")
        assert hasattr(result, "value")
        assert hasattr(result, "dominant_problem")
        assert hasattr(result, "overall_sentiment")
        assert hasattr(result, "severity")
        assert hasattr(result, "summary")
        assert hasattr(result, "confidence")

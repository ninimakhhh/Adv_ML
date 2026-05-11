"""Unit tests for sentiment_analysis/aggregator.py"""

from datetime import datetime, timedelta, timezone
import pytest

from sentiment_analysis.aggregator import (
    aspect_heatmap,
    top_problem_products,
    problem_frequency,
    sentiment_trend,
    cross_reference_alerts,
    category_sentiment,
    load_events,
    _parse_datetime,
)


# ── Fixture data ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_events():
    """Fixture providing sample sentiment events for testing."""
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    
    return [
        {
            "event_id": "sa_review_1",
            "source": "review",
            "source_id": "rev_1",
            "product_id": "prod_a",
            "category_id": "cat_beauty",
            "ticket_category": None,
            "timestamp": now.isoformat(),
            "raw_text": "Great product!",
            "delivery": 0.8,
            "quality": 0.9,
            "accuracy": None,
            "packaging": 0.7,
            "customer_service": None,
            "value": 0.8,
            "dominant_problem": "none",
            "overall_sentiment": "Positive",
            "severity": "low",
            "summary": "Excellent quality",
            "confidence": 95,
        },
        {
            "event_id": "sa_review_2",
            "source": "review",
            "source_id": "rev_2",
            "product_id": "prod_b",
            "category_id": "cat_beauty",
            "ticket_category": None,
            "timestamp": yesterday.isoformat(),
            "raw_text": "Product broke quickly",
            "delivery": 0.5,
            "quality": -0.9,
            "accuracy": None,
            "packaging": -0.7,
            "customer_service": -0.6,
            "value": -0.8,
            "dominant_problem": "poor_quality",
            "overall_sentiment": "Negative",
            "severity": "high",
            "summary": "Poor quality, broke in a week",
            "confidence": 90,
        },
        {
            "event_id": "sa_review_3",
            "source": "review",
            "source_id": "rev_3",
            "product_id": "prod_a",
            "category_id": "cat_fashion",
            "ticket_category": None,
            "timestamp": week_ago.isoformat(),
            "raw_text": "Okay product",
            "delivery": 0.0,
            "quality": 0.1,
            "accuracy": 0.0,
            "packaging": 0.0,
            "customer_service": 0.0,
            "value": 0.0,
            "dominant_problem": "none",
            "overall_sentiment": "Neutral",
            "severity": "low",
            "summary": "Average product",
            "confidence": 70,
        },
        {
            "event_id": "sa_ticket_1",
            "source": "ticket",
            "source_id": "tck_1",
            "product_id": None,
            "category_id": None,
            "ticket_category": "Shipping",
            "timestamp": now.isoformat(),
            "raw_text": "Order not arrived",
            "delivery": -0.9,
            "quality": None,
            "accuracy": None,
            "packaging": None,
            "customer_service": -0.5,
            "value": None,
            "dominant_problem": "late_delivery",
            "overall_sentiment": "Negative",
            "severity": "high",
            "summary": "Order delayed",
            "confidence": 88,
        },
        {
            "event_id": "sa_review_4",
            "source": "review",
            "source_id": "rev_4",
            "product_id": "prod_b",
            "category_id": "cat_beauty",
            "ticket_category": None,
            "timestamp": now.isoformat(),
            "raw_text": "Another negative review for prod_b",
            "delivery": -0.8,
            "quality": -0.8,
            "accuracy": None,
            "packaging": None,
            "customer_service": None,
            "value": -0.9,
            "dominant_problem": "poor_quality",
            "overall_sentiment": "Negative",
            "severity": "medium",
            "summary": "Not worth the price",
            "confidence": 85,
        },
    ]


# ── Tests ────────────────────────────────────────────────────────────────────

class TestAspectHeatmap:
    """Test aspect_heatmap query function."""

    def test_aspect_heatmap_basic(self, sample_events):
        """Test basic heatmap generation."""
        result = aspect_heatmap(sample_events)
        
        assert isinstance(result, dict)
        assert "cat_beauty" in result
        assert "cat_fashion" in result
        assert "delivery" in result["cat_beauty"]

    def test_aspect_heatmap_scoring(self, sample_events):
        """Test that heatmap correctly calculates mean scores."""
        result = aspect_heatmap(sample_events)
        
        # cat_beauty has prod_a (0.8), prod_b (0.5), prod_b (-0.8)
        # delivery mean = (0.8 + 0.5 + -0.8) / 3 ≈ 0.167
        beauty_delivery = result["cat_beauty"]["delivery"]
        assert beauty_delivery is not None
        assert 0.1 < beauty_delivery < 0.3

    def test_aspect_heatmap_none_handling(self, sample_events):
        """Test that None aspects are handled correctly."""
        result = aspect_heatmap(sample_events)
        
        # cat_fashion should have None for aspects not in prod_a review
        fashion_result = result.get("cat_fashion", {})
        assert fashion_result["delivery"] == 0.0  # only one review with value 0.0


class TestTopProblemProducts:
    """Test top_problem_products query function."""

    def test_top_problem_products_basic(self, sample_events):
        """Test basic problem products ranking."""
        result = top_problem_products(sample_events, n=5, window_days=30)
        
        assert isinstance(result, list)
        # prod_b should be ranked higher (2 negative reviews)
        assert len(result) > 0
        if len(result) >= 1:
            assert result[0]["product_id"] == "prod_b"
            assert result[0]["negative_count"] == 2

    def test_top_problem_products_window(self, sample_events):
        """Test that window_days filter works."""
        # With 0 days window, should exclude older reviews
        result = top_problem_products(sample_events, n=10, window_days=0)
        
        # Only recent events (within 0 days = today only)
        for product in result:
            assert product["negative_count"] > 0

    def test_top_problem_products_n_limit(self, sample_events):
        """Test that n parameter limits results."""
        result = top_problem_products(sample_events, n=1, window_days=30)
        
        assert len(result) <= 1


class TestProblemFrequency:
    """Test problem_frequency query function."""

    def test_problem_frequency_basic(self, sample_events):
        """Test basic problem frequency counting."""
        result = problem_frequency(sample_events)
        
        assert isinstance(result, list)
        assert len(result) > 0
        # "poor_quality" should be most frequent (2 occurrences)
        assert result[0]["problem"] == "poor_quality"
        assert result[0]["count"] == 2

    def test_problem_frequency_source_filter(self, sample_events):
        """Test source filtering in problem_frequency."""
        # Filter by review source only
        reviews_only = problem_frequency(sample_events, source="review")
        
        # Should only count review problems
        assert len(reviews_only) > 0
        assert all(e["problem"] != "late_delivery" for e in reviews_only)

    def test_problem_frequency_percentages(self, sample_events):
        """Test that percentages sum to 100."""
        result = problem_frequency(sample_events)
        
        total_pct = sum(item["pct"] for item in result)
        # Allow for rounding errors
        assert 99.5 < total_pct <= 100.1


class TestSentimentTrend:
    """Test sentiment_trend query function."""

    def test_sentiment_trend_basic(self, sample_events):
        """Test basic trend generation."""
        result = sentiment_trend(sample_events, days=30)
        
        assert isinstance(result, list)
        # Should have at least one day with data
        assert len(result) > 0
        assert "date" in result[0]
        assert "Positive" in result[0]
        assert "Neutral" in result[0]
        assert "Negative" in result[0]

    def test_sentiment_trend_source_filter(self, sample_events):
        """Test source filtering in sentiment trend."""
        reviews_trend = sentiment_trend(sample_events, source="review", days=30)
        tickets_trend = sentiment_trend(sample_events, source="ticket", days=30)
        
        # Both should have data but may have different counts
        assert len(reviews_trend) > 0
        assert len(tickets_trend) > 0


class TestCrossReferenceAlerts:
    """Test cross_reference_alerts query function."""

    def test_cross_reference_alerts_basic(self, sample_events):
        """Test basic alert generation."""
        result = cross_reference_alerts(sample_events, window_days=30)
        
        # Should return list of products with both review and ticket issues
        assert isinstance(result, list)
        # prod_b has negative reviews, but no tickets, so might not appear
        # This depends on the fixture setup


class TestCategorySentiment:
    """Test category_sentiment query function."""

    def test_category_sentiment_basic(self, sample_events):
        """Test basic category sentiment calculation."""
        result = category_sentiment(sample_events)
        
        assert isinstance(result, list)
        assert len(result) > 0
        
        for item in result:
            assert "category_id" in item
            assert "mean_sentiment_score" in item
            assert "positive" in item
            assert "negative" in item

    def test_category_sentiment_scores(self, sample_events):
        """Test that sentiment scores are within valid range."""
        result = category_sentiment(sample_events)
        
        for item in result:
            score = item.get("mean_sentiment_score")
            if score is not None:
                assert -1 <= score <= 1


class TestParseDatetime:
    """Test _parse_datetime helper function."""

    def test_parse_iso_format(self):
        """Test parsing ISO format timestamps."""
        ts_iso = datetime.now(timezone.utc).isoformat()
        result = _parse_datetime(ts_iso)
        
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_z_format(self):
        """Test parsing timestamps with Z suffix."""
        ts = "2024-05-11T12:30:45Z"
        result = _parse_datetime(ts)
        
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_naive_timestamp(self):
        """Test parsing naive timestamps (no timezone)."""
        ts = "2024-05-11T12:30:45"
        result = _parse_datetime(ts)
        
        assert result is not None
        # Should be converted to UTC
        assert result.tzinfo is not None

    def test_parse_invalid_timestamp(self):
        """Test parsing invalid timestamp."""
        result = _parse_datetime("not a timestamp")
        
        assert result is None

    def test_parse_empty_timestamp(self):
        """Test parsing empty timestamp."""
        result = _parse_datetime("")
        
        assert result is None

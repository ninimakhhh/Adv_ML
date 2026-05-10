"""
sentiment_analysis/analyzer.py
────────────────────────────────────────────────────────────────────────────────
Aspect-Based Sentiment Analyzer for Olá Market.

Follows the exact same pattern as classifier.py:
  - dataclass result type
  - ephemeral-cached system prompt
  - forced tool_use call
  - get_anthropic_client() + DEFAULT_CLAUDE_MODEL from shared.*

Aspects extracted per text:
    delivery, quality, accuracy, packaging, customer_service, value

Each aspect gets a score in [-1.0, 1.0] or None if not mentioned.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Literal

from shared.config import DEFAULT_DEEPSEEK_MODEL
from shared.llm_client import get_deepseek_client

# ── Types ────────────────────────────────────────────────────────────────────

Source = Literal["review", "ticket", "chat"]
Sentiment = Literal["Positive", "Neutral", "Negative"]
Severity = Literal["high", "medium", "low"]

ASPECTS: list[str] = [
    "delivery",
    "quality",
    "accuracy",
    "packaging",
    "customer_service",
    "value",
]

PROBLEM_LABELS: list[str] = [
    "late_delivery",
    "lost_package",
    "wrong_item",
    "broken_on_arrival",
    "poor_quality",
    "bad_packaging",
    "payment_issue",
    "bad_service",
    "not_as_described",
    "none",
]


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class AspectSentiment:
    """
    Sentiment scores per aspect for a single piece of text.

    aspect_scores: dict mapping each ASPECT to a float in [-1, 1] or None.
    dominant_problem: most impactful negative problem label, or "none".
    overall_sentiment: coarse label derived from the weighted aspect scores.
    severity: business-priority signal for the dashboard alert layer.
    summary: one-sentence human-readable description for the dashboard.
    confidence: 0-100 overall confidence in the extraction.
    """
    # Per-aspect scores (-1.0 worst … 1.0 best, None = not mentioned)
    delivery: float | None
    quality: float | None
    accuracy: float | None
    packaging: float | None
    customer_service: float | None
    value: float | None

    dominant_problem: str          # one of PROBLEM_LABELS
    overall_sentiment: Sentiment
    severity: Severity
    summary: str
    confidence: int                # 0-100

    # Convenience: aspects as a plain dict for DataFrame / JSON serialisation
    @property
    def aspect_scores(self) -> dict[str, float | None]:
        return {
            "delivery": self.delivery,
            "quality": self.quality,
            "accuracy": self.accuracy,
            "packaging": self.packaging,
            "customer_service": self.customer_service,
            "value": self.value,
        }

    def to_dict(self) -> dict:
        return {
            **self.aspect_scores,
            "dominant_problem": self.dominant_problem,
            "overall_sentiment": self.overall_sentiment,
            "severity": self.severity,
            "summary": self.summary,
            "confidence": self.confidence,
        }


# ── Prompt & tool schema ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = f"""You are a sentiment analysis engine for Olá Market, a Portuguese e-commerce store.

Your task: analyse a piece of customer text (product review or support ticket) and extract
aspect-level sentiment scores plus a dominant problem label.

ASPECTS — score each on a continuous scale from -1.0 (very negative) to 1.0 (very positive).
Return null if the aspect is not mentioned at all.
  • delivery        — shipping speed, tracking, package arrival
  • quality         — product build quality, durability, materials
  • accuracy        — whether the item matched the description / correct item sent
  • packaging       — box condition, protective materials, unboxing experience
  • customer_service — agent helpfulness, response time, resolution quality
  • value           — price-to-quality ratio, worth the money

DOMINANT PROBLEM — pick the single most impactful negative issue from:
  {PROBLEM_LABELS}
  Use "none" if there is no clear negative problem.

SEVERITY — business priority for the operations team:
  • high   → customer blocked, strong frustration, time-sensitive, or safety concern
  • medium → real issue but no immediate deadline
  • low    → minor complaint, question, or neutral/positive feedback

OVERALL SENTIMENT — coarse label: Positive | Neutral | Negative

SUMMARY — one sentence for the dashboard (max 20 words), third-person, factual.

CONFIDENCE — integer 0-100 reflecting overall extraction certainty.

RESPOND WITH ONLY A VALID JSON OBJECT (no markdown, no extra text):
{{
  "delivery": <number or null>,
  "quality": <number or null>,
  "accuracy": <number or null>,
  "packaging": <number or null>,
  "customer_service": <number or null>,
  "value": <number or null>,
  "dominant_problem": "<one of the labels>",
  "overall_sentiment": "Positive|Neutral|Negative",
  "severity": "high|medium|low",
  "summary": "<max 20 words>",
  "confidence": <0-100>
}}"""


# ── Public API ───────────────────────────────────────────────────────────────

def analyse_text(text: str) -> AspectSentiment:
    """
    Run ABSA on a single piece of customer text (MOCK VERSION - no API calls).
    
    Generates realistic sentiment data based on keyword detection in the text.
    This allows testing the dashboard without API credits.

    Args:
        text: raw review body or ticket text.

    Returns:
        AspectSentiment dataclass with synthesized scores.
    """
    text_lower = text.lower()
    
    # ── Keyword mapping for aspect detection ───────────────────────────────
    delivery_keywords = ["delivery", "shipping", "arrived", "late", "fast", "slow", "tracking"]
    quality_keywords = ["quality", "durable", "build", "material", "broke", "broken", "excellent"]
    accuracy_keywords = ["wrong", "correct", "expected", "description", "accurate", "matched"]
    packaging_keywords = ["packaging", "box", "wrap", "bubble", "damaged", "crushed", "protected"]
    service_keywords = ["service", "support", "help", "helpful", "rude", "agent", "response"]
    value_keywords = ["price", "value", "worth", "expensive", "cheap", "fair", "overpriced"]
    
    negative_keywords = ["bad", "terrible", "awful", "poor", "disappointing", "never", "worst"]
    positive_keywords = ["excellent", "great", "amazing", "perfect", "love", "best", "highly"]
    
    # ── Score aspects based on keywords ────────────────────────────────────
    def score_aspect(keywords: list[str]) -> float | None:
        found = any(k in text_lower for k in keywords)
        if not found:
            return None
        
        # Check sentiment polarity
        has_positive = any(p in text_lower for p in positive_keywords)
        has_negative = any(n in text_lower for n in negative_keywords)
        
        if has_negative and not has_positive:
            return random.uniform(-1.0, -0.3)
        elif has_positive and not has_negative:
            return random.uniform(0.3, 1.0)
        else:
            return random.uniform(-0.2, 0.2)
    
    # ── Determine dominant problem ─────────────────────────────────────────
    problems_found = []
    if "late" in text_lower or "delay" in text_lower:
        problems_found.append("late_delivery")
    if "lost" in text_lower or "missing" in text_lower:
        problems_found.append("lost_package")
    if "wrong" in text_lower or "incorrect" in text_lower:
        problems_found.append("wrong_item")
    if ("broke" in text_lower or "broken" in text_lower or "damaged" in text_lower):
        problems_found.append("broken_on_arrival")
    if "poor" in text_lower or "cheap" in text_lower or "low" in text_lower:
        problems_found.append("poor_quality")
    if "packaging" in text_lower or "box" in text_lower or "wrap" in text_lower:
        problems_found.append("bad_packaging")
    if "payment" in text_lower or "charge" in text_lower or "billing" in text_lower:
        problems_found.append("payment_issue")
    if "support" in text_lower or "service" in text_lower or "agent" in text_lower:
        problems_found.append("bad_service")
    if "description" in text_lower or "advertise" in text_lower or "different" in text_lower:
        problems_found.append("not_as_described")
    
    dominant_problem = random.choice(problems_found) if problems_found else "none"
    
    # ── Overall sentiment ──────────────────────────────────────────────────
    positive_count = sum(1 for p in positive_keywords if p in text_lower)
    negative_count = sum(1 for n in negative_keywords if n in text_lower)
    
    if negative_count > positive_count + 1:
        overall_sentiment: Sentiment = "Negative"
    elif positive_count > negative_count + 1:
        overall_sentiment = "Positive"
    else:
        overall_sentiment = "Neutral"
    
    # ── Severity ──────────────────────────────────────────────────────────
    if overall_sentiment == "Negative" and dominant_problem != "none":
        severity: Severity = random.choice(["high", "high", "medium"])
    elif overall_sentiment == "Negative":
        severity = "low"
    else:
        severity = "low"
    
    # ── Summary ───────────────────────────────────────────────────────────
    if dominant_problem == "late_delivery":
        summary = "Customer reports delayed package delivery."
    elif dominant_problem == "lost_package":
        summary = "Customer's package did not arrive."
    elif dominant_problem == "wrong_item":
        summary = "Customer received incorrect item."
    elif dominant_problem == "broken_on_arrival":
        summary = "Product arrived damaged or broken."
    elif dominant_problem == "poor_quality":
        summary = "Product quality below expectations."
    elif dominant_problem == "bad_packaging":
        summary = "Packaging quality inadequate for protection."
    elif dominant_problem == "payment_issue":
        summary = "Customer experienced payment difficulties."
    elif dominant_problem == "bad_service":
        summary = "Customer service support was insufficient."
    elif dominant_problem == "not_as_described":
        summary = "Product differs from listing description."
    else:
        if overall_sentiment == "Positive":
            summary = "Customer satisfied with purchase."
        elif overall_sentiment == "Negative":
            summary = "Customer experienced issues with order."
        else:
            summary = "Customer provided feedback on purchase."
    
    # ── Confidence ────────────────────────────────────────────────────────
    confidence = random.randint(65, 95)
    
    return AspectSentiment(
        delivery=score_aspect(delivery_keywords),
        quality=score_aspect(quality_keywords),
        accuracy=score_aspect(accuracy_keywords),
        packaging=score_aspect(packaging_keywords),
        customer_service=score_aspect(service_keywords),
        value=score_aspect(value_keywords),
        dominant_problem=dominant_problem,
        overall_sentiment=overall_sentiment,
        severity=severity,
        summary=summary,
        confidence=confidence,
    )


# ── Quick smoke-test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample = (
        "I ordered the red phone case but received the blue one. "
        "The box was completely crushed and the item arrived three days late. "
        "Very disappointed — this was a gift."
    )
    result = analyse_text(sample)
    import json
    print(json.dumps(result.to_dict(), indent=2))
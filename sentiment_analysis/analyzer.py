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
from dataclasses import dataclass
from typing import Literal

from shared.config import DEFAULT_DEEPSEEK_MODEL
from shared.llm_client import get_deepseek_client
from shared.logger import get_logger

logger = get_logger(__name__)

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
    Run ABSA on a single piece of customer text using DeepSeek API.

    Args:
        text: raw review body or ticket text.

    Returns:
        AspectSentiment dataclass with all aspect scores and metadata.

    Raises:
        RuntimeError: if the API call fails or returns invalid JSON.
    """
    logger.debug(f"Analyzing text: {text[:100]}...")
    
    client = get_deepseek_client()

    try:
        response = client.chat.completions.create(
            model=DEFAULT_DEEPSEEK_MODEL,
            max_tokens=512,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        logger.debug(f"API response received for text: {text[:50]}...")
    except Exception as e:
        logger.error(f"API call failed: {str(e)}")
        raise

    # Extract the JSON response
    content = response.choices[0].message.content.strip()
    
    # Try to parse JSON
    try:
        payload = json.loads(content)
        logger.debug(f"JSON parsed successfully: sentiment={payload.get('overall_sentiment')}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode failed. Response: {content[:200]}")
        raise RuntimeError(
            f"Model did not return valid JSON. Response: {content[:200]}"
        ) from e

    result = AspectSentiment(
        delivery=payload.get("delivery"),
        quality=payload.get("quality"),
        accuracy=payload.get("accuracy"),
        packaging=payload.get("packaging"),
        customer_service=payload.get("customer_service"),
        value=payload.get("value"),
        dominant_problem=payload.get("dominant_problem", "none"),
        overall_sentiment=payload.get("overall_sentiment", "Neutral"),
        severity=payload.get("severity", "low"),
        summary=payload.get("summary", ""),
        confidence=int(payload.get("confidence", 0)),
    )
    
    logger.info(f"Analyzed text: sentiment={result.overall_sentiment}, severity={result.severity}")
    return result


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
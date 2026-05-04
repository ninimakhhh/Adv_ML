"""
Intent classifier — maps a user message to a registry intent via Claude.

Usage:
    from chatbot.classifier.classifier import IntentClassifier

    clf = IntentClassifier()
    result = clf.classify("where is my order #12345")
    print(result.intent_id, result.confidence)
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import anthropic

from chatbot.registry.loader import load_intents

_MODEL = "claude-sonnet-4-6"
_MAX_CONTEXT_TURNS = 6  # last N conversation turns included in prompt


@dataclass
class ClassificationResult:
    intent_id: Optional[str]
    confidence: float                              # 0.0 – 1.0
    top_3_alternatives: list[tuple[str, float]]   # [(intent_id, confidence), ...]
    reasoning: str                                 # one-sentence debug string


_FALLBACK = ClassificationResult(
    intent_id=None,
    confidence=0.0,
    top_3_alternatives=[],
    reasoning="Classification failed — could not parse model response.",
)


def _build_intent_list(intents: dict[str, dict]) -> str:
    lines = []
    for intent_id, intent in intents.items():
        examples = "; ".join(f'"{u}"' for u in intent.get("example_utterances", [])[:5])
        lines.append(f"  - {intent_id}: {examples}")
    return "\n".join(lines)


def _build_prompt(
    intents: dict[str, dict],
    user_message: str,
    conversation_context: list[dict],
) -> str:
    intent_list = _build_intent_list(intents)
    intent_ids = ", ".join(f'"{k}"' for k in intents)

    ctx_lines = ""
    if conversation_context:
        recent = conversation_context[-_MAX_CONTEXT_TURNS:]
        ctx_lines = "\n".join(
            f"  [{t.get('role','?')}]: {t.get('content','')}"
            for t in recent
        )
        ctx_section = f"\nConversation context (most recent turns first):\n{ctx_lines}\n"
    else:
        ctx_section = ""

    return f"""You are an intent classifier for a customer service chatbot for a Portuguese e-commerce store.

Available intents and representative example phrases:
{intent_list}

Valid intent IDs: {intent_ids}
{ctx_section}
Latest user message: "{user_message}"

Your task: classify the user message into the single best matching intent.

Respond with ONLY valid JSON — no markdown fences, no extra text:
{{
  "intent_id": "<one of the valid intent IDs, or null if nothing fits>",
  "confidence": <float 0.00–1.00>,
  "alternatives": [
    {{"intent_id": "<second best>", "confidence": <float>}},
    {{"intent_id": "<third best>", "confidence": <float>}}
  ],
  "reasoning": "<one sentence: why this intent was chosen>"
}}

Rules:
- intent_id must be exactly one of the valid IDs listed above, or null.
- Set intent_id to null and confidence below 0.40 if no intent fits.
- alternatives must be from the valid IDs; never repeat the chosen intent.
- Calibrate confidence honestly — do not always return 0.99.
- reasoning is for internal debugging only; keep it concise."""


class IntentClassifier:
    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._client = anthropic.Anthropic(api_key=key)
        self._intents = load_intents()

    def classify(
        self,
        user_message: str,
        conversation_context: list[dict] | None = None,
    ) -> ClassificationResult:
        context = conversation_context or []
        prompt = _build_prompt(self._intents, user_message, context)

        try:
            response = self._client.messages.create(
                model=_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
        except Exception as exc:
            return ClassificationResult(
                intent_id=None,
                confidence=0.0,
                top_3_alternatives=[],
                reasoning=f"API error: {exc}",
            )

        return _parse_response(raw, self._intents)


def _parse_response(raw: str, intents: dict[str, dict]) -> ClassificationResult:
    try:
        # Strip optional markdown fences the model might still emit
        text = raw
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return _FALLBACK

    valid_ids = set(intents.keys())

    intent_id = data.get("intent_id")
    if intent_id not in valid_ids:
        intent_id = None

    confidence = float(data.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    alts_raw = data.get("alternatives", [])
    alternatives: list[tuple[str, float]] = []
    for alt in alts_raw[:3]:
        alt_id = alt.get("intent_id")
        alt_conf = float(alt.get("confidence", 0.0))
        if alt_id in valid_ids and alt_id != intent_id:
            alternatives.append((alt_id, max(0.0, min(1.0, alt_conf))))

    reasoning = str(data.get("reasoning", ""))

    return ClassificationResult(
        intent_id=intent_id,
        confidence=confidence,
        top_3_alternatives=alternatives,
        reasoning=reasoning,
    )

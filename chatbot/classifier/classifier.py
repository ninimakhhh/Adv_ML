"""
Intent classifier — maps a user message to a registry intent via LLMClient (DeepSeek).

Usage:
    from chatbot.classifier.classifier import IntentClassifier

    clf = IntentClassifier()
    result = clf.classify("where is my order #12345")
    print(result.intent_id, result.confidence)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.llm_client import LLMClient
from chatbot.registry.loader import load_intents

_MAX_CONTEXT_TURNS = 6


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


def _build_messages(
    intents: dict[str, dict],
    user_message: str,
    conversation_context: list[dict],
) -> list[dict[str, str]]:
    intent_list = _build_intent_list(intents)
    intent_ids = ", ".join(f'"{k}"' for k in intents)

    if conversation_context:
        recent = conversation_context[-_MAX_CONTEXT_TURNS:]
        ctx_lines = "\n".join(
            f"  [{t.get('role','?')}]: {t.get('content','')}" for t in recent
        )
        ctx_section = f"\nConversation context (most recent turns first):\n{ctx_lines}\n"
    else:
        ctx_section = ""

    system_prompt = f"""You are an intent classifier for a customer service chatbot for a Portuguese e-commerce store.

Available intents and representative example phrases:
{intent_list}

Valid intent IDs: {intent_ids}

Rules:
- intent_id must be exactly one of the valid IDs listed above, or null.
- Set intent_id to null and confidence below 0.40 if no intent fits.
- alternatives must be from the valid IDs; never repeat the chosen intent.
- Calibrate confidence honestly — do not always return 0.99.
- reasoning is for internal debugging only; keep it concise.

Respond with ONLY valid JSON matching this exact shape:
{{
  "intent_id": "<one of the valid intent IDs, or null>",
  "confidence": <float 0.00-1.00>,
  "alternatives": [
    {{"intent_id": "<second best>", "confidence": <float>}},
    {{"intent_id": "<third best>", "confidence": <float>}}
  ],
  "reasoning": "<one sentence>"
}}"""

    user_content = f"{ctx_section}Latest user message: \"{user_message}\""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _parse_response(data: dict, intents: dict[str, dict]) -> ClassificationResult:
    """Convert a parsed JSON dict into a ClassificationResult, validating all fields."""
    if "error" in data:
        return ClassificationResult(
            intent_id=None,
            confidence=0.0,
            top_3_alternatives=[],
            reasoning=f"API error: {data.get('error')}",
        )

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

    return ClassificationResult(
        intent_id=intent_id,
        confidence=confidence,
        top_3_alternatives=alternatives,
        reasoning=str(data.get("reasoning", "")),
    )


class IntentClassifier:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or LLMClient()
        self._intents = load_intents()

    def classify(
        self,
        user_message: str,
        conversation_context: list[dict] | None = None,
    ) -> ClassificationResult:
        messages = _build_messages(self._intents, user_message, conversation_context or [])

        try:
            data = self._llm.chat(messages, response_format="json")
        except Exception as exc:
            return ClassificationResult(
                intent_id=None,
                confidence=0.0,
                top_3_alternatives=[],
                reasoning=f"API error: {exc}",
            )

        return _parse_response(data, self._intents)

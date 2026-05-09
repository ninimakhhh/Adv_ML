from dataclasses import dataclass
from typing import Literal

from shared.config import DEFAULT_CLAUDE_MODEL
from shared.llm_client import get_anthropic_client

CATEGORIES: list[str] = ["Bug", "Shipping", "Returns", "Payments", "Other"]
SENTIMENTS: list[str] = ["Positive", "Neutral", "Negative"]
URGENCIES: list[str] = ["High", "Medium", "Low"]

CATEGORY_TO_QUEUE: dict[str, str] = {
    "Bug": "Technical Support",
    "Shipping": "Logistics",
    "Returns": "Returns",
    "Payments": "Payments",
    "Other": "General",
}

Category = Literal["Bug", "Shipping", "Returns", "Payments", "Other"]
Sentiment = Literal["Positive", "Neutral", "Negative"]
Urgency = Literal["High", "Medium", "Low"]


@dataclass
class TicketClassification:
    category: Category
    confidence: int
    sentiment: Sentiment
    urgency: Urgency
    assigned_queue: str
    reasoning: str | None = None


_SYSTEM_PROMPT = f"""You are a customer support triage assistant for a Portuguese e-commerce store (Olá Market).

Your job is to read a single support ticket (subject + body) and classify it along three axes:

1. **category** — one of {CATEGORIES}
   - Bug: software defects, malfunctioning products, app crashes, features not working
   - Shipping: delivery delays, lost packages, tracking issues, address problems
   - Returns: refund requests, wrong item received, return-policy questions, exchanges
   - Payments: card declined, billing errors, charge disputes, payment-method issues
   - Other: compliments, generic questions, or anything that doesn't fit the four above

2. **sentiment** — one of {SENTIMENTS}
   - The customer's emotional tone in the message itself.

3. **urgency** — one of {URGENCIES}
   - High: customer is blocked, time-sensitive (gift, deadline), or expressing strong frustration
   - Medium: real problem but no immediate deadline
   - Low: question, feedback, or compliment with no action required

Always also produce a short **reasoning** (one sentence) and a **confidence** integer 0–100
that reflects how certain you are about the category.

Use the `classify_ticket` tool. Do not respond with prose."""


_TOOL_SCHEMA = {
    "name": "classify_ticket",
    "description": "Return the classification of a single support ticket.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "confidence": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Confidence in the chosen category, 0-100.",
            },
            "sentiment": {"type": "string", "enum": SENTIMENTS},
            "urgency": {"type": "string", "enum": URGENCIES},
            "reasoning": {
                "type": "string",
                "description": "One short sentence explaining the choice.",
            },
        },
        "required": ["category", "confidence", "sentiment", "urgency", "reasoning"],
    },
}


def classify_ticket(subject: str, raw_text: str) -> TicketClassification:
    client = get_anthropic_client()

    response = client.messages.create(
        model=DEFAULT_CLAUDE_MODEL,
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "classify_ticket"},
        messages=[
            {
                "role": "user",
                "content": f"Subject: {subject}\n\nBody:\n{raw_text}",
            }
        ],
    )

    tool_use = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_use is None:
        raise RuntimeError(
            "Model did not call the classify_ticket tool. "
            f"stop_reason={response.stop_reason}"
        )

    payload = tool_use.input
    category = payload["category"]
    return TicketClassification(
        category=category,
        confidence=int(payload["confidence"]),
        sentiment=payload["sentiment"],
        urgency=payload["urgency"],
        assigned_queue=CATEGORY_TO_QUEUE[category],
        reasoning=payload.get("reasoning"),
    )


if __name__ == "__main__":
    import json
    from pathlib import Path

    tickets_path = Path(__file__).resolve().parents[1] / "data" / "mock" / "recent_tickets.json"
    with open(tickets_path, encoding="utf-8") as f:
        data = json.load(f)

    sample = data["to_review"][0]
    print(f"Classifying {sample['id']}: {sample['subject']!r}\n")
    result = classify_ticket(sample["subject"], sample["raw_text"])
    print(result)

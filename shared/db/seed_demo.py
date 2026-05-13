"""
Seed 30 realistic demo tickets into data/tickets.db.

Usage:
    python shared/db/seed_demo.py
"""

from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.db.migrate import migrate
from shared.db.models import Ticket
from shared.db.repository import TicketRepository

random.seed(42)

_INTENTS = [
    "order_status",
    "return_policy",
    "refund_status",
    "shipping_info",
    "product_availability",
    "cancel_order",
]

_AGENTS = ["agent_ana", "agent_joao", "agent_marta", "agent_luis"]

_USERS = [f"user_{i:03d}" for i in range(1, 51)]

_CHANNELS = ["chat", "chat", "chat", "email", "web"]


def _rand_dt(days_ago_max: int = 30) -> datetime:
    return datetime.utcnow() - timedelta(
        days=random.randint(0, days_ago_max),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )


def _make_ticket(
    *,
    resolution_path: str,
    final_status: str,
    intent: str | None = None,
    csat: int | None = None,
    agent: bool = False,
    tags: list[str] | None = None,
    sentiment: str | None = None,
    confidence: float | None = None,
) -> Ticket:
    created = _rand_dt()
    resolved = (
        created + timedelta(minutes=random.randint(3, 180))
        if final_status in ("resolved", "closed")
        else None
    )
    return Ticket(
        ticket_id=str(uuid.uuid4()),
        user_id=random.choice(_USERS),
        created_at=created,
        resolved_at=resolved,
        channel=random.choice(_CHANNELS),
        classified_intent=intent or random.choice(_INTENTS),
        classification_confidence=confidence if confidence is not None else round(random.uniform(0.70, 0.99), 2),
        resolution_path=resolution_path,
        final_status=final_status,
        csat_score=csat,
        agent_id=random.choice(_AGENTS) if agent else None,
        tags=tags or [],
        sentiment=sentiment or random.choice(["positive", "neutral", "negative"]),
    )


# ------------------------------------------------------------------
# Conversation fixtures per intent
# ------------------------------------------------------------------

_CONVOS: dict[str, list[tuple[str, str]]] = {
    "order_status": [
        ("user", "Hi, I need to check my order status"),
        ("bot", "Of course! Could you share your order number (e.g. #10234)?"),
        ("user", "It's #98712"),
        ("bot", "Order #98712 is currently **In Transit** and expected by Thursday. Is there anything else?"),
        ("user", "No, thanks!"),
    ],
    "return_policy": [
        ("user", "What is your return policy?"),
        ("bot", "You can return most items within 30 days of delivery. Items must be unused and in original packaging. Start a return at My Orders > Return Item."),
        ("user", "Great, thank you"),
    ],
    "refund_status": [
        ("user", "When will I get my refund for order #54321?"),
        ("bot", "Your refund of €49.99 was processed on 2026-04-28. It should appear in 5-7 business days."),
        ("user", "Perfect, cheers"),
    ],
    "shipping_info": [
        ("user", "How much does shipping cost?"),
        ("bot", "Standard shipping (3-5 days) is €3.99, free over €40. Express (1-2 days) is €7.99."),
        ("user", "Ok got it"),
    ],
    "product_availability": [
        ("user", "Is the Golden Mirror in stock?"),
        ("bot", "Checking availability for Golden Mirror... It shows **In Stock** — 8 units remaining."),
        ("user", "Awesome, adding to cart"),
    ],
    "cancel_order": [
        ("user", "I want to cancel order #77001"),
        ("bot", "I found order #77001. Do you confirm you want to cancel the entire order? Reply yes or no."),
        ("user", "Yes please"),
        ("bot", "Cancellation submitted. You'll receive an email within 10 minutes. Refund in 5-7 days."),
    ],
}

_ESCALATION_CONVOS: dict[str, list[tuple[str, str]]] = {
    "escalated_low_confidence": [
        ("user", "I have a really complicated problem with my subscription and billing"),
        ("bot", "I'm not entirely sure I understand the issue. Let me connect you with a human agent."),
        ("agent", "Hello! I'm Ana from the support team. How can I help?"),
        ("user", "I was charged twice for the same month"),
        ("agent", "I can see the duplicate charge. I'll issue a full refund now — you'll see it in 3-5 days."),
    ],
    "escalated_user_request": [
        ("user", "Can I speak to a real person please?"),
        ("bot", "Of course! Connecting you now..."),
        ("agent", "Hi, I'm Joao. What can I help you with today?"),
        ("user", "I have an issue with my return that isn't resolved"),
        ("agent", "Let me look into your case right away."),
    ],
    "escalated_after_failure": [
        ("user", "My order #45600 is stuck since last week"),
        ("bot", "Let me check order #45600... I'm having trouble retrieving this order. Let me get you an agent."),
        ("agent", "Hi! I'm Marta. I can see order #45600 had a warehouse delay. It ships today."),
        ("user", "Finally! Thank you"),
    ],
    "escalated_sensitive": [
        ("user", "I think someone hacked into my account"),
        ("bot", "For account security issues I'm connecting you to a specialist immediately."),
        ("agent", "Hi, this is Luis from our security team. Can you tell me what you noticed?"),
        ("user", "There were two orders I didn't place"),
        ("agent", "I'm locking the account now and will email you reset instructions."),
    ],
}


def seed(db_path=None):
    from shared.db.migrate import _DB_PATH
    path = db_path or _DB_PATH
    migrate(path)
    repo = TicketRepository(path)

    tickets = []

    # --- 12 bot_resolved (closed, CSAT 3-5) ---
    intents_cycle = _INTENTS * 4
    for i in range(12):
        intent = intents_cycle[i % len(intents_cycle)]
        t = _make_ticket(
            resolution_path="bot_resolved",
            final_status="closed",
            intent=intent,
            csat=random.choice([3, 4, 4, 5, 5]),
            sentiment=random.choice(["positive", "positive", "neutral"]),
            confidence=round(random.uniform(0.80, 0.99), 2),
        )
        tickets.append((t, intent))

    # --- 8 escalated (in_progress or resolved) ---
    esc_paths = [
        ("escalated_low_confidence", "in_progress"),
        ("escalated_user_request", "resolved"),
        ("escalated_after_failure", "resolved"),
        ("escalated_sensitive", "in_progress"),
        ("escalated_low_confidence", "resolved"),
        ("escalated_user_request", "in_progress"),
        ("escalated_after_failure", "resolved"),
        ("escalated_sensitive", "resolved"),
    ]
    esc_intents = [
        "order_status", "return_policy", "cancel_order", "order_status",
        "refund_status", "shipping_info", "product_availability", "cancel_order",
    ]
    for i, (epath, estatus) in enumerate(esc_paths):
        intent = esc_intents[i]
        t = _make_ticket(
            resolution_path=epath,
            final_status=estatus,
            intent=intent,
            agent=True,
            csat=random.choice([None, 2, 3, 4]) if estatus in ("resolved", "closed") else None,
            sentiment=random.choice(["negative", "neutral", "positive"]),
            confidence=round(random.uniform(0.30, 0.68), 2),
        )
        tickets.append((t, epath))

    # --- 5 in_progress ---
    for i in range(5):
        intent = random.choice(_INTENTS)
        t = _make_ticket(
            resolution_path="pending",
            final_status="in_progress",
            intent=intent,
            agent=True,
            sentiment=random.choice(["neutral", "negative"]),
        )
        tickets.append((t, intent))

    # --- 5 open/pending ---
    for i in range(5):
        intent = random.choice(_INTENTS)
        t = _make_ticket(
            resolution_path="pending",
            final_status=random.choice(["open", "open", "open"]),
            intent=intent,
            sentiment="neutral",
        )
        tickets.append((t, intent))

    # Persist tickets + messages
    for ticket, key in tickets:
        repo.create_ticket(ticket)

        # Pick conversation template
        if ticket.resolution_path.startswith("escalated"):
            convo_key = ticket.resolution_path if ticket.resolution_path in _ESCALATION_CONVOS else "escalated_low_confidence"
            convo = _ESCALATION_CONVOS[convo_key]
        else:
            intent_key = ticket.classified_intent if ticket.classified_intent in _CONVOS else "order_status"
            convo = _CONVOS[intent_key]

        for role, body in convo:
            repo.add_message(ticket.ticket_id, role, body, apply_redaction=True)

    # Stats
    m = repo.get_metrics()
    print(f"\n[OK] Seeded 30 tickets into {path}")
    print(f"     Total:              {m['total_tickets']}")
    print(f"     Bot resolved:       {m['bot_resolved']}  ({m['bot_resolution_rate_pct']}%)")
    print(f"     Escalated:          {m['escalated']}  ({m['escalation_rate_pct']}%)")
    print(f"     Avg CSAT:           {m['avg_csat']}")
    print(f"     By status:          {m['by_status']}")
    print(f"     Top intents:        {m['top_intents']}")


if __name__ == "__main__":
    seed()

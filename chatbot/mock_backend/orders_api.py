"""Mock Shopify orders API."""

from __future__ import annotations

import re

from chatbot.mock_backend.mock_data import ORDERS


def _normalise_order_id(raw: str) -> str:
    """Accept 'ORD-1001', '#1001', '1001' — always return 'ORD-XXXX'."""
    raw = raw.strip().upper()
    # Already in canonical form
    if raw.startswith("ORD-"):
        return raw
    # Strip leading # or whitespace, then prepend
    digits = re.sub(r"[^0-9]", "", raw)
    if digits:
        return f"ORD-{digits}"
    return raw


def get_order(order_id: str, email: str = "") -> dict:
    """
    Return order status data or an error dict.

    The mock accepts any non-empty email for a known order_id.
    """
    oid = _normalise_order_id(order_id)
    order = ORDERS.get(oid)

    if order is None:
        return {"error": "order_not_found", "escalation_trigger": "order_not_found"}

    # Email presence check only (mock never stores real emails)
    if email and "@" not in email:
        return {"error": "invalid_email"}

    return {
        "order_id": oid,
        "status": order["status"],
        "status_detail": order["status_detail"],
        "estimated_delivery": order["estimated_delivery"],
        "tracking_url": order["tracking_url"],
    }


def cancel_check(order_id: str) -> dict:
    """
    Return whether an order is eligible for cancellation.

    Returns:
      {"cancellable": True}
      {"cancellable": False, "escalation_trigger": "<trigger>"}
    """
    oid = _normalise_order_id(order_id)
    order = ORDERS.get(oid)

    if order is None:
        return {"cancellable": False, "escalation_trigger": "order_not_found"}

    if order["can_cancel"]:
        return {"cancellable": True}

    trigger = order.get("cancel_escalation_trigger") or "order_already_shipped"
    return {"cancellable": False, "escalation_trigger": trigger}

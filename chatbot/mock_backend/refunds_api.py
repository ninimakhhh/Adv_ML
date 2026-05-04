"""Mock Shopify refunds API."""

from __future__ import annotations

import re

from chatbot.mock_backend.mock_data import ORDERS


def _normalise_order_id(raw: str) -> str:
    raw = raw.strip().upper()
    if raw.startswith("ORD-"):
        return raw
    digits = re.sub(r"[^0-9]", "", raw)
    return f"ORD-{digits}" if digits else raw


def get_refund_status(order_id: str) -> dict:
    """
    Return refund status for an order.

    Template placeholders produced:
      refund_status, refund_amount, refund_eta, refund_detail
    """
    oid = _normalise_order_id(order_id)
    order = ORDERS.get(oid)

    if order is None:
        return {
            "error": "order_not_found",
            "escalation_trigger": "order_not_found",
            "refund_status": "Unknown",
            "refund_amount": "N/A",
            "refund_eta": "N/A",
            "refund_detail": "We could not find that order. Please double-check your order number.",
        }

    status = order.get("refund_status")
    if status is None:
        return {
            "refund_status": "No refund on file",
            "refund_amount": "N/A",
            "refund_eta": "N/A",
            "refund_detail": "There is no active refund request for this order.",
        }

    amount = order.get("refund_amount") or "N/A"
    eta = order.get("refund_eta") or "N/A"
    detail = order.get("refund_detail") or ""

    # Flag over-14-day pending refunds for escalation
    if status == "pending" and _is_overdue(eta):
        return {
            "refund_status": status.title(),
            "refund_amount": amount,
            "refund_eta": eta,
            "refund_detail": detail,
            "escalation_trigger": "refund_pending_over_14_days",
        }

    return {
        "refund_status": status.title(),
        "refund_amount": amount,
        "refund_eta": eta,
        "refund_detail": detail,
    }


def _is_overdue(eta_str: str) -> bool:
    """Return True if the ETA is more than 14 days in the past."""
    try:
        from datetime import datetime
        eta = datetime.strptime(eta_str, "%Y-%m-%d")
        return (datetime.utcnow() - eta).days > 14
    except Exception:
        return False

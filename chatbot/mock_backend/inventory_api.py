"""Mock Shopify inventory / product availability API."""

from __future__ import annotations

from chatbot.mock_backend.mock_data import PRODUCTS


def _find_product(product_name: str) -> dict | None:
    """Case-insensitive substring match. Returns first hit or None."""
    needle = product_name.lower().strip()
    # Exact match first
    for p in PRODUCTS:
        if p["name"] == needle:
            return p
    # Partial word match
    for p in PRODUCTS:
        if needle in p["name"] or any(w in p["name"] for w in needle.split()):
            return p
    return None


def check_availability(product_name: str) -> dict:
    """
    Return availability info for a product.

    Template placeholders produced:
      availability_status, availability_detail, restock_message
    """
    product = _find_product(product_name)

    if product is None:
        return {
            "error": "product_not_found",
            "escalation_trigger": "product_not_found",
            "availability_status": "Unknown",
            "availability_detail": "We could not find that product in our catalogue.",
            "restock_message": "Try searching by the exact product name from the product page.",
        }

    if product["in_stock"]:
        count = product["stock_count"]
        if count <= 10:
            detail = f"Only **{count} units** left — order soon!"
        else:
            detail = f"**{count} units** available — ready to ship."
        return {
            "availability_status": "In Stock",
            "availability_detail": detail,
            "restock_message": "",
        }
    else:
        restock = product.get("restock_message") or "Restock date not yet confirmed."
        return {
            "availability_status": "Out of Stock",
            "availability_detail": "This item is currently unavailable.",
            "restock_message": restock,
        }

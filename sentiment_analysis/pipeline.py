"""
sentiment_analysis/pipeline.py
────────────────────────────────────────────────────────────────────────────────
Batch pipeline: loads reviews + tickets, runs ABSA on each, and writes a
unified sentiment event store to  data/mock/sentiment_events.json.

Run from project root:
    python -m sentiment_analysis.pipeline

Design decisions:
  • Incremental: skips source_ids already present in the event store.
  • Writes after every item so partial runs are safe to resume.
  • Keeps the full AspectSentiment payload alongside source metadata,
    giving the dashboard a single flat file to query.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sentiment_analysis.analyzer import analyse_text, AspectSentiment
from shared.logger import get_logger

logger = get_logger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data" / "mock"

REVIEWS_PATH  = _DATA / "reviews.json"
TICKETS_PATH  = _DATA / "recent_tickets.json"
EVENTS_PATH   = _DATA / "sentiment_events.json"

# ── Unified event schema ─────────────────────────────────────────────────────
#
# {
#   "event_id":          str,          # "sa_{source}_{source_id}"
#   "source":            str,          # "review" | "ticket"
#   "source_id":         str,          # original id field
#   "product_id":        str | None,   # from review; None for tickets
#   "category_id":       str | None,   # from review product; None for tickets
#   "ticket_category":   str | None,   # Bug/Shipping/etc.; None for reviews
#   "timestamp":         str,          # ISO-8601
#   "raw_text":          str,
#   # --- ABSA output ---
#   "delivery":          float | None,
#   "quality":           float | None,
#   "accuracy":          float | None,
#   "packaging":         float | None,
#   "customer_service":  float | None,
#   "value":             float | None,
#   "dominant_problem":  str,
#   "overall_sentiment": str,
#   "severity":          str,
#   "summary":           str,
#   "confidence":        int,
# }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_events() -> dict[str, dict]:
    """Return existing events keyed by event_id for fast dedup lookup."""
    if not EVENTS_PATH.exists():
        return {}
    with open(EVENTS_PATH, encoding="utf-8") as f:
        events: list[dict] = json.load(f)
    return {e["event_id"]: e for e in events}


def _save_events(events: dict[str, dict]) -> None:
    with open(EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(list(events.values()), f, ensure_ascii=False, indent=2)


def _make_event(
    source: str,
    source_id: str,
    raw_text: str,
    result: AspectSentiment,
    *,
    product_id: str | None = None,
    category_id: str | None = None,
    ticket_category: str | None = None,
    timestamp: str | None = None,
) -> dict:
    return {
        "event_id": f"sa_{source}_{source_id}",
        "source": source,
        "source_id": source_id,
        "product_id": product_id,
        "category_id": category_id,
        "ticket_category": ticket_category,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "raw_text": raw_text,
        **result.to_dict(),
    }


# ── Review iterator ──────────────────────────────────────────────────────────

def _iter_reviews() -> Iterator[tuple[str, str, dict]]:
    """Yield (source_id, raw_text, meta) for every review."""
    if not REVIEWS_PATH.exists():
        return

    # Build product_id → category_id lookup
    products_path = _DATA / "products.json"
    product_meta: dict[str, str] = {}
    if products_path.exists():
        with open(products_path, encoding="utf-8") as f:
            products = json.load(f)
        product_meta = {p["id"]: p["category_id"] for p in products}

    with open(REVIEWS_PATH, encoding="utf-8") as f:
        reviews = json.load(f)

    for r in reviews:
        text = f"{r.get('title', '')}. {r.get('body', '')}".strip()
        meta = {
            "product_id": r.get("product_id"),
            "category_id": product_meta.get(r.get("product_id", ""), None),
            "timestamp": r.get("date", None),
        }
        yield r["id"], text, meta


# ── Ticket iterator ──────────────────────────────────────────────────────────

def _iter_tickets() -> Iterator[tuple[str, str, dict]]:
    """Yield (source_id, raw_text, meta) for every ticket in both buckets."""
    if not TICKETS_PATH.exists():
        return

    with open(TICKETS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    all_tickets = data.get("to_review", []) + data.get("classified", [])

    for t in all_tickets:
        raw = t.get("raw_text") or t.get("subject", "")
        meta = {
            "ticket_category": t.get("category") or t.get("suggested_category"),
            "timestamp": t.get("created_at"),
        }
        yield t["id"], raw, meta


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(
    *,
    max_reviews: int | None = None,
    max_tickets: int | None = None,
    delay_seconds: float = 0.2,
    verbose: bool = True,
) -> list[dict]:
    """
    Run the incremental ABSA pipeline.

    Args:
        max_reviews:    cap on reviews to process (None = all). Useful for dev.
        max_tickets:    cap on tickets to process (None = all).
        delay_seconds:  polite pause between API calls.
        verbose:        print progress to stdout.

    Returns:
        List of all events (existing + newly created).
    """
    logger.info(f"Starting pipeline: max_reviews={max_reviews}, max_tickets={max_tickets}")
    
    events = _load_events()
    initial_count = len(events)
    logger.info(f"Loaded {initial_count} existing events")

    def _process(source: str, source_id: str, text: str, meta: dict) -> None:
        event_id = f"sa_{source}_{source_id}"
        if event_id in events:
            if verbose:
                print(f"  skip  {event_id} (already processed)")
            logger.debug(f"Skipping {event_id}: already processed")
            return

        if verbose:
            print(f"  analyse {event_id[:60]}…", end=" ", flush=True)

        try:
            result = analyse_text(text)
            event = _make_event(
                source=source,
                source_id=source_id,
                raw_text=text,
                result=result,
                product_id=meta.get("product_id"),
                category_id=meta.get("category_id"),
                ticket_category=meta.get("ticket_category"),
                timestamp=meta.get("timestamp"),
            )
            events[event_id] = event
            _save_events(events)  # write-through after each item
            if verbose:
                print(f"✓  [{result.overall_sentiment}] {result.summary[:50]}")
            logger.info(f"Processed {event_id}: {result.overall_sentiment}")
        except Exception as exc:
            if verbose:
                print(f"✗  ERROR: {exc}")
            logger.error(f"Failed to process {event_id}: {exc}", exc_info=True)

        time.sleep(delay_seconds)

    # --- Reviews ---
    review_count = 0
    for source_id, text, meta in _iter_reviews():
        if max_reviews is not None and review_count >= max_reviews:
            break
        _process("review", source_id, text, meta)
        review_count += 1
    logger.info(f"Processed {review_count} reviews")

    # --- Tickets ---
    ticket_count = 0
    for source_id, text, meta in _iter_tickets():
        if max_tickets is not None and ticket_count >= max_tickets:
            break
        _process("ticket", source_id, text, meta)
        ticket_count += 1
    logger.info(f"Processed {ticket_count} tickets")

    new_count = len(events) - initial_count
    if verbose:
        print(f"\nDone. {new_count} new events written. Total: {len(events)}.")
    logger.info(f"Pipeline complete: {new_count} new events, {len(events)} total")

    return list(events.values())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run ABSA pipeline for Olá Market.")
    parser.add_argument("--max-reviews", type=int, default=None)
    parser.add_argument("--max-tickets", type=int, default=None)
    parser.add_argument("--delay",       type=float, default=0.2)
    args = parser.parse_args()

    run(
        max_reviews=args.max_reviews,
        max_tickets=args.max_tickets,
        delay_seconds=args.delay,
    )
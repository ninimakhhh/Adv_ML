"""Compress all review dates into a skewed-recent 6-month window.

Run from the project root:
    python scripts/redistribute_review_dates.py

Reads:  data/mock/reviews.json
        data/mock/sentiment_events.json   (optional — synced if present)
Writes: data/mock/reviews.json            (dates rewritten in place)
        data/mock/sentiment_events.json   (timestamps re-aligned to new dates)

Target distribution over the 1,214 reviews (last 6 months from TODAY):
    Last 7 days     :   ~8%  ( ~ 97 reviews)
    8-30 days ago   :  ~29%  ( ~352 reviews)   ← intentionally > 3-6 months
    31-90 days ago  :  ~41%  ( ~498 reviews)
    91-180 days ago :  ~22%  ( ~267 reviews)

Within each bucket, dates are drawn uniformly. All other review fields
(id, body, rating, author, helpful_count, …) stay untouched.

Deterministic given SEED.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS_PATH = ROOT / "data" / "mock" / "reviews.json"
EVENTS_PATH = ROOT / "data" / "mock" / "sentiment_events.json"

SEED = 23
TODAY = date(2026, 5, 12)

# (lower_inclusive, upper_inclusive, share)
BUCKETS = [
    ("Last 7 days",      0,   7,  0.08),
    ("8-30 days ago",    8,  30,  0.29),
    ("31-90 days ago",  31,  90,  0.41),
    ("91-180 days ago", 91, 180,  0.22),
]


def main() -> None:
    rng = random.Random(SEED)

    with open(REVIEWS_PATH, encoding="utf-8") as f:
        reviews = json.load(f)

    total = len(reviews)
    # Compute per-bucket counts, rounding then fixing drift on the biggest one.
    bucket_counts: list[int] = [round(b[3] * total) for b in BUCKETS]
    drift = total - sum(bucket_counts)
    if drift != 0:
        biggest_idx = max(range(len(bucket_counts)), key=bucket_counts.__getitem__)
        bucket_counts[biggest_idx] += drift

    # Build a flat list of (lo, hi) pairs, one per review, then shuffle reviews
    # so the bucket assignment is uncorrelated with id/product.
    bucket_ranges: list[tuple[int, int]] = []
    for (label, lo, hi, _), count in zip(BUCKETS, bucket_counts):
        bucket_ranges.extend([(lo, hi)] * count)
    assert len(bucket_ranges) == total

    indices = list(range(total))
    rng.shuffle(indices)

    # id -> new date, used later to sync sentiment_events.json
    id_to_date: dict[str, str] = {}

    for review_idx, (lo, hi) in zip(indices, bucket_ranges):
        days_ago = rng.randint(lo, hi)
        new_date = (TODAY - timedelta(days=days_ago)).isoformat()
        reviews[review_idx]["date"] = new_date
        id_to_date[reviews[review_idx]["id"]] = new_date

    with open(REVIEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

    # Sync sentiment_events.json timestamps (review events only).
    synced = 0
    if EVENTS_PATH.exists():
        with open(EVENTS_PATH, encoding="utf-8") as f:
            events = json.load(f)
        for event in events:
            if event.get("source") != "review":
                continue
            source_id = event.get("source_id")
            new_date = id_to_date.get(source_id)
            if new_date and event.get("timestamp") != new_date:
                event["timestamp"] = new_date
                synced += 1
        with open(EVENTS_PATH, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

    # Report.
    from collections import Counter
    age_counter = Counter()
    for r in reviews:
        y, m, d = map(int, r["date"].split("-"))
        age = (TODAY - date(y, m, d)).days
        for label, lo, hi, _ in BUCKETS:
            if lo <= age <= hi:
                age_counter[label] += 1
                break

    print(f"Reviews redistributed:  {total}")
    print(f"Window:                 {TODAY - timedelta(days=180)} -> {TODAY}")
    for label, _, _, share in BUCKETS:
        count = age_counter[label]
        pct = count / total * 100
        bar = "#" * int(pct / 2)
        print(f"  {label:18s} {count:5d}  ({pct:5.1f}%)  {bar}")
    print(f"Sentiment events synced: {synced}")


if __name__ == "__main__":
    main()

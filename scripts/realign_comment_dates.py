"""Realign 25 review dates to the last 7 days for the Comments admin tab.

Run from the project root:
    python scripts/realign_comment_dates.py

Reads:  data/mock/sentiment_events.json
        data/mock/reviews.json
Writes: data/mock/reviews.json            (25 review dates rewritten in place)
        data/mock/sentiment_events.json   (20 review event timestamps re-synced)

Logic:
  1. The 20 reviews whose id is the source_id of an event with source=="review"
     in sentiment_events.json become the "classified" bucket.
  2. 5 additional reviews are selected at random (seed fixed) from reviews.json
     among those NOT in the classified bucket; they become the "pending" bucket.
  3. All 25 reviews get a fresh `date` chosen uniformly within the last 7 days.
  4. The 20 event `timestamp` values in sentiment_events.json are updated to
     match the new `date` of their corresponding review.

The other ~1,189 reviews are left untouched. Deterministic given SEED.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS_PATH = ROOT / "data" / "mock" / "reviews.json"
EVENTS_PATH = ROOT / "data" / "mock" / "sentiment_events.json"

SEED = 31
TODAY = date(2026, 5, 12)
WINDOW_DAYS = 7


def main() -> None:
    rng = random.Random(SEED)

    with open(REVIEWS_PATH, encoding="utf-8") as f:
        reviews = json.load(f)
    with open(EVENTS_PATH, encoding="utf-8") as f:
        events = json.load(f)

    # 1. Identify the 20 review-source events and their target review ids.
    classified_ids: list[str] = []
    for e in events:
        if e.get("source") == "review":
            sid = e.get("source_id")
            if sid:
                classified_ids.append(sid)

    classified_id_set = set(classified_ids)

    reviews_by_id = {r["id"]: r for r in reviews}
    missing = [rid for rid in classified_ids if rid not in reviews_by_id]
    if missing:
        raise SystemExit(
            f"ERROR: {len(missing)} review ids referenced by sentiment_events.json "
            f"are not present in reviews.json: {missing[:3]}"
        )

    # 2. Select 5 pending reviews from those NOT already classified.
    candidate_pool = [r for r in reviews if r["id"] not in classified_id_set]
    rng.shuffle(candidate_pool)
    pending_reviews = candidate_pool[:5]
    pending_ids = [r["id"] for r in pending_reviews]

    target_ids = classified_ids + pending_ids
    assert len(target_ids) == 25, f"expected 25 target ids, got {len(target_ids)}"

    # 3. Reassign dates uniformly in the last 7 days.
    new_dates: dict[str, str] = {}
    for rid in target_ids:
        days_ago = rng.randint(0, WINDOW_DAYS)
        new_dates[rid] = (TODAY - timedelta(days=days_ago)).isoformat()

    for r in reviews:
        if r["id"] in new_dates:
            r["date"] = new_dates[r["id"]]

    # 4. Sync event timestamps for the 20 classified ones.
    synced = 0
    for e in events:
        if e.get("source") != "review":
            continue
        sid = e.get("source_id")
        if sid in new_dates:
            e["timestamp"] = new_dates[sid]
            synced += 1

    # Write back.
    with open(REVIEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    with open(EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    # Report.
    print(f"Today:                          {TODAY}")
    print(f"Window:                         last {WINDOW_DAYS} days")
    print(f"Classified reviews (from events): {len(classified_ids)}")
    print(f"Pending reviews (newly picked):   {len(pending_ids)}")
    print(f"Total reviews with new dates:     {len(target_ids)}")
    print(f"Event timestamps synced:          {synced}")
    print()
    print("Classified bucket:")
    for rid in classified_ids:
        r = reviews_by_id[rid]
        print(f"  {rid:24s}  {new_dates[rid]}  rating={r['rating']}  {r['product_id']}")
    print()
    print("Pending bucket:")
    for r in pending_reviews:
        rid = r["id"]
        print(f"  {rid:24s}  {new_dates[rid]}  rating={r['rating']}  {r['product_id']}")


if __name__ == "__main__":
    main()

"""
sentiment_analysis/aggregator.py
────────────────────────────────────────────────────────────────────────────────
Pure-query layer over sentiment_events.json.

All functions return plain dicts / lists — no Streamlit or plotting imports here.
The dashboard (llm_dashboard.py) calls these and decides how to visualise.

Key queries:
  • aspect_heatmap()          — category × aspect mean scores
  • top_problem_products()    — products ranked by negative review velocity
  • problem_frequency()       — ranked count of dominant_problem labels
  • sentiment_trend()         — daily overall_sentiment counts over N days
  • cross_reference_alerts()  — products with both negative reviews AND tickets
  • category_sentiment()      — mean overall sentiment score per category
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

# ── Paths ────────────────────────────────────────────────────────────────────

_ROOT  = Path(__file__).resolve().parents[1]
_DATA  = _ROOT / "data" / "mock"
EVENTS_PATH   = _DATA / "sentiment_events.json"
PRODUCTS_PATH = _DATA / "products.json"


# ── Loader ───────────────────────────────────────────────────────────────────

def load_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    with open(EVENTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_product_map() -> dict[str, dict]:
    """Return {product_id: product_dict}."""
    if not PRODUCTS_PATH.exists():
        return {}
    with open(PRODUCTS_PATH, encoding="utf-8") as f:
        products = json.load(f)
    return {p["id"]: p for p in products}


def _parse_datetime(ts: str) -> datetime | None:
    """Parse timestamp string, ensuring timezone-aware result (UTC default)."""
    if not ts:
        return None
    try:
        # Try to parse with timezone first
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # If result is naive, add UTC timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


ASPECTS = ["delivery", "quality", "accuracy", "packaging", "customer_service", "value"]
SENTIMENT_SCORE = {"Positive": 1, "Neutral": 0, "Negative": -1}


# ── 1. Aspect heatmap ─────────────────────────────────────────────────────────

def aspect_heatmap(events: list[dict] | None = None) -> dict[str, dict[str, float | None]]:
    """
    Returns: {category_id: {aspect: mean_score_or_None}}

    Only includes review events that have a category_id.
    Mean is None when no event mentions the aspect for that category.
    """
    events = events or load_events()
    # {category: {aspect: [scores]}}
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for e in events:
        cat = e.get("category_id")
        if not cat:
            continue
        for asp in ASPECTS:
            score = e.get(asp)
            if score is not None:
                buckets[cat][asp].append(score)

    result: dict[str, dict[str, float | None]] = {}
    for cat, asp_map in buckets.items():
        result[cat] = {
            asp: round(mean(asp_map[asp]), 3) if asp_map.get(asp) else None
            for asp in ASPECTS
        }
    return result


# ── 2. Top problem products ───────────────────────────────────────────────────

def top_problem_products(
    events: list[dict] | None = None,
    n: int = 10,
    window_days: int = 30,
) -> list[dict]:
    """
    Products ranked by negative-review velocity (count of Negative events
    within `window_days`), enriched with product name and category.

    Returns list of dicts sorted descending by negative_count:
      {product_id, product_name, category_id, negative_count,
       dominant_problems, avg_severity_score, avg_aspect_scores}
    """
    events   = events or load_events()
    products = load_product_map()
    cutoff   = datetime.now(timezone.utc) - timedelta(days=window_days)

    # Filter to negative review events within window
    neg: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if e.get("source") != "review":
            continue
        if e.get("overall_sentiment") != "Negative":
            continue
        pid = e.get("product_id")
        if not pid:
            continue
        ts = e.get("timestamp")
        dt = _parse_datetime(ts)
        if dt and dt < cutoff:
            continue
        neg[pid].append(e)

    severity_weight = {"high": 3, "medium": 2, "low": 1}

    rows = []
    for pid, evts in neg.items():
        product = products.get(pid, {})
        problems = [e["dominant_problem"] for e in evts if e.get("dominant_problem") != "none"]
        avg_severity = mean(severity_weight.get(e.get("severity", "low"), 1) for e in evts)

        # Mean aspect scores across this product's negative reviews
        avg_aspects: dict[str, float | None] = {}
        for asp in ASPECTS:
            scores = [e[asp] for e in evts if e.get(asp) is not None]
            avg_aspects[asp] = round(mean(scores), 3) if scores else None

        rows.append({
            "product_id":        pid,
            "product_name":      product.get("name", pid),
            "category_id":       product.get("category_id", ""),
            "negative_count":    len(evts),
            "dominant_problems": _top_n_counts(problems, 3),
            "avg_severity_score": round(avg_severity, 2),
            "avg_aspect_scores": avg_aspects,
        })

    rows.sort(key=lambda r: r["negative_count"], reverse=True)
    return rows[:n]


# ── 3. Problem frequency ──────────────────────────────────────────────────────

def problem_frequency(
    events: list[dict] | None = None,
    source: str | None = None,       # "review" | "ticket" | None = both
) -> list[dict]:
    """
    Ranked list of {problem_label, count, pct} across all events.
    Excludes "none".
    """
    events = events or load_events()
    counts: dict[str, int] = defaultdict(int)

    for e in events:
        if source and e.get("source") != source:
            continue
        prob = e.get("dominant_problem", "none")
        if prob != "none":
            counts[prob] += 1

    total = sum(counts.values()) or 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [
        {"problem": p, "count": c, "pct": round(c / total * 100, 1)}
        for p, c in ranked
    ]


# ── 4. Sentiment trend ────────────────────────────────────────────────────────

def sentiment_trend(
    events: list[dict] | None = None,
    days: int = 30,
    source: str | None = None,
) -> list[dict]:
    """
    Daily counts of Positive / Neutral / Negative events for the past `days` days.

    Returns list of {date, Positive, Neutral, Negative} sorted ascending by date.
    """
    events = events or load_events()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"Positive": 0, "Neutral": 0, "Negative": 0})

    for e in events:
        if source and e.get("source") != source:
            continue
        ts = e.get("timestamp")
        if not ts:
            continue
        dt = _parse_datetime(ts)
        if not dt or dt < cutoff:
            continue
        day = dt.date().isoformat()
        sentiment = e.get("overall_sentiment", "Neutral")
        if sentiment in daily[day]:
            daily[day][sentiment] += 1

    return [{"date": d, **counts} for d, counts in sorted(daily.items())]


# ── 5. Cross-reference alerts ─────────────────────────────────────────────────

def cross_reference_alerts(
    events: list[dict] | None = None,
    window_days: int = 14,
) -> list[dict]:
    """
    Products that appear in BOTH negative reviews AND tickets within `window_days`.
    These are confirmed systemic issues, not random noise.

    Returns list of {product_id, product_name, negative_review_count,
                     ticket_count, dominant_problems, suggested_action}
    """
    events   = events or load_events()
    products = load_product_map()
    cutoff   = datetime.now(timezone.utc) - timedelta(days=window_days)

    rev_neg:   dict[str, list[dict]] = defaultdict(list)  # product_id → negative reviews
    tick_neg:  dict[str, list[dict]] = defaultdict(list)  # product_id → related tickets

    for e in events:
        ts = e.get("timestamp")
        dt = _parse_datetime(ts)
        if dt and dt < cutoff:
            continue

        pid = e.get("product_id")
        if e["source"] == "review" and e.get("overall_sentiment") == "Negative" and pid:
            rev_neg[pid].append(e)
        elif e["source"] == "ticket" and e.get("overall_sentiment") == "Negative" and pid:
            tick_neg[pid].append(e)

    # Intersection
    confirmed = set(rev_neg) & set(tick_neg)
    rows = []
    for pid in confirmed:
        problems = [
            e["dominant_problem"]
            for e in rev_neg[pid] + tick_neg[pid]
            if e.get("dominant_problem") != "none"
        ]
        product = products.get(pid, {})
        rows.append({
            "product_id":            pid,
            "product_name":          product.get("name", pid),
            "negative_review_count": len(rev_neg[pid]),
            "ticket_count":          len(tick_neg[pid]),
            "dominant_problems":     _top_n_counts(problems, 3),
            "suggested_action":      _suggest_action(problems),
        })

    rows.sort(key=lambda r: r["negative_review_count"] + r["ticket_count"], reverse=True)
    return rows


# ── 6. Category sentiment summary ─────────────────────────────────────────────

def category_sentiment(events: list[dict] | None = None) -> list[dict]:
    """
    Per-category mean sentiment score (Positive=1, Neutral=0, Negative=-1).
    Also includes breakdown counts and the worst aspect for that category.

    Returns list sorted ascending by mean_score (worst categories first).
    """
    events = events or load_events()
    heatmap = aspect_heatmap(events)

    buckets: dict[str, list[int]] = defaultdict(list)
    for e in events:
        cat = e.get("category_id")
        if not cat:
            continue
        score = SENTIMENT_SCORE.get(e.get("overall_sentiment", "Neutral"), 0)
        buckets[cat].append(score)

    rows = []
    for cat, scores in buckets.items():
        asp_scores = heatmap.get(cat, {})
        # Find the worst aspect (lowest score that isn't None)
        worst_asp = min(
            ((asp, s) for asp, s in asp_scores.items() if s is not None),
            key=lambda x: x[1],
            default=(None, None),
        )
        pos = scores.count(1)
        neu = scores.count(0)
        neg = scores.count(-1)
        rows.append({
            "category_id":  cat,
            "mean_score":   round(mean(scores), 3),
            "total_events": len(scores),
            "positive":     pos,
            "neutral":      neu,
            "negative":     neg,
            "worst_aspect": worst_asp[0],
            "worst_aspect_score": worst_asp[1],
        })

    rows.sort(key=lambda r: r["mean_score"])
    return rows


# ── Utility ───────────────────────────────────────────────────────────────────

def _top_n_counts(items: list[str], n: int) -> list[dict]:
    """Return [{label, count}] for the top-n most frequent items."""
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item] += 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [{"label": label, "count": count} for label, count in ranked[:n]]


def _suggest_action(problems: list[str]) -> str:
    """Map the most common problem label to a plain-English suggested action."""
    if not problems:
        return "Investigate customer reports."
    top = max(set(problems), key=problems.count)
    actions = {
        "late_delivery":    "Escalate to logistics; review carrier SLAs.",
        "lost_package":     "Open carrier claim; proactively contact affected customers.",
        "wrong_item":       "Audit warehouse pick-pack for this SKU.",
        "broken_on_arrival":"Inspect packaging spec; consider upgraded box.",
        "poor_quality":     "Flag to QA and supplier; consider product review.",
        "bad_packaging":    "Upgrade protective materials for this SKU.",
        "payment_issue":    "Check payment gateway logs; notify engineering.",
        "bad_service":      "Flag to CS team lead for coaching.",
        "not_as_described": "Review product listing accuracy and photos.",
    }
    return actions.get(top, "Review product and support tickets.")
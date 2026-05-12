"""
chatbot/feedback/analyzer.py — Weekly review report for the feedback loop.

Produces a structured report that surfaces bot failures so they can be
turned into training data, new intents, or improved responses.

Usage:
    from chatbot.feedback.analyzer import weekly_review
    report = weekly_review()                    # uses production DB
    report = weekly_review(db_path=Path("...")) # custom path (tests)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_DB = _ROOT / "data" / "tickets.db"

# Thumbs-down CSAT score set by ui_adapter.submit_feedback("down")
_THUMBS_DOWN_SCORE = 2
_LOW_CONFIDENCE_THRESHOLD = 0.70


def weekly_review(db_path: Path = _DEFAULT_DB) -> dict:
    """
    Run all four analyses and return a JSON-serialisable report dict.

    Keys:
        generated_at              ISO timestamp
        low_confidence_messages   list[dict]  — top 10, conf < 0.7
        attempted_but_escalated   list[dict]  — top 5 intents by escalation rate
        thumbs_down               list[dict]  — top 5 thumbs-down tickets
        no_intent_messages        list[dict]  — all messages with no matched intent
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    try:
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "low_confidence_messages": _low_confidence(con),
            "attempted_but_escalated": _attempted_but_escalated(con),
            "thumbs_down": _thumbs_down(con),
            "no_intent_messages": _no_intent(con),
        }
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Individual queries
# ---------------------------------------------------------------------------

def _first_user_message_subquery() -> str:
    return (
        "(SELECT MIN(sent_at) FROM messages "
        " WHERE ticket_id = t.ticket_id AND role = 'user')"
    )


def _last_bot_message_subquery() -> str:
    return (
        "(SELECT MAX(sent_at) FROM messages "
        " WHERE ticket_id = t.ticket_id AND role = 'bot')"
    )


def _low_confidence(con: sqlite3.Connection) -> list[dict]:
    """Top 10 messages where classifier confidence was below threshold."""
    rows = con.execute(
        f"""
        SELECT t.ticket_id,
               t.classified_intent,
               t.classification_confidence,
               t.resolution_path,
               t.created_at,
               mu.body AS user_message
        FROM   tickets t
        JOIN   messages mu
               ON  mu.ticket_id = t.ticket_id
               AND mu.role      = 'user'
               AND mu.sent_at   = {_first_user_message_subquery()}
        WHERE  t.classification_confidence IS NOT NULL
          AND  t.classification_confidence < {_LOW_CONFIDENCE_THRESHOLD}
        ORDER  BY t.classification_confidence ASC
        LIMIT  10
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _attempted_but_escalated(con: sqlite3.Connection) -> list[dict]:
    """
    Intents where the bot had a classified intent but the conversation still
    escalated to a human — i.e. the bot attempted a resolution and failed.
    Returns top 5 by escalation rate (%).
    """
    rows = con.execute(
        """
        WITH totals AS (
            SELECT classified_intent, COUNT(*) AS total
            FROM   tickets
            WHERE  classified_intent IS NOT NULL
            GROUP  BY classified_intent
        ),
        escalated AS (
            SELECT classified_intent, COUNT(*) AS esc_count
            FROM   tickets
            WHERE  classified_intent IS NOT NULL
              AND  resolution_path LIKE 'escalated%'
            GROUP  BY classified_intent
        )
        SELECT  e.classified_intent  AS intent_id,
                e.esc_count,
                t.total,
                ROUND(e.esc_count * 100.0 / t.total, 1) AS escalation_rate_pct
        FROM    escalated e
        JOIN    totals    t ON t.classified_intent = e.classified_intent
        ORDER   BY escalation_rate_pct DESC
        LIMIT   5
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _thumbs_down(con: sqlite3.Connection) -> list[dict]:
    """Top 5 thumbs-down tickets (csat_score = 2), with user message + bot response."""
    rows = con.execute(
        f"""
        SELECT  t.ticket_id,
                t.classified_intent,
                t.csat_score,
                t.resolution_path,
                mu.body AS user_message,
                mb.body AS bot_response
        FROM    tickets t
        JOIN    messages mu
                ON  mu.ticket_id = t.ticket_id
                AND mu.role      = 'user'
                AND mu.sent_at   = {_first_user_message_subquery()}
        JOIN    messages mb
                ON  mb.ticket_id = t.ticket_id
                AND mb.role      = 'bot'
                AND mb.sent_at   = {_last_bot_message_subquery()}
        WHERE   t.csat_score = {_THUMBS_DOWN_SCORE}
        ORDER   BY t.created_at DESC
        LIMIT   5
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _no_intent(con: sqlite3.Connection) -> list[dict]:
    """All tickets where no intent was matched — raw user messages."""
    rows = con.execute(
        f"""
        SELECT  t.ticket_id,
                t.created_at,
                mu.body AS user_message
        FROM    tickets t
        JOIN    messages mu
                ON  mu.ticket_id = t.ticket_id
                AND mu.role      = 'user'
                AND mu.sent_at   = {_first_user_message_subquery()}
        WHERE   t.classified_intent IS NULL
        ORDER   BY t.created_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def export_labeled_jsonl(db_path: Path = _DEFAULT_DB) -> str:
    """
    Export human-verified tickets as a fine-tuning-ready JSONL string.

    Each line: {"user_message": "...", "correct_intent": "...",
                "confidence": 1.0, "bot_response": "...", "ticket_id": "..."}

    Only includes tickets where human_verified = 1 (admin has confirmed the
    classification), making the labels trustworthy training signal.
    """
    import json

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    try:
        rows = con.execute(
            f"""
            SELECT  t.ticket_id,
                    t.classified_intent,
                    t.classification_confidence,
                    t.resolution_path,
                    mu.body AS user_message,
                    mb.body AS bot_response
            FROM    tickets t
            JOIN    messages mu
                    ON  mu.ticket_id = t.ticket_id
                    AND mu.role      = 'user'
                    AND mu.sent_at   = {_first_user_message_subquery()}
            LEFT JOIN messages mb
                    ON  mb.ticket_id = t.ticket_id
                    AND mb.role      = 'bot'
                    AND mb.sent_at   = {_last_bot_message_subquery()}
            WHERE   t.human_verified = 1
              AND   t.classified_intent IS NOT NULL
            ORDER   BY t.created_at ASC
            """
        ).fetchall()
    finally:
        con.close()

    lines = []
    for r in rows:
        record = {
            "ticket_id":       r["ticket_id"],
            "user_message":    r["user_message"],
            "correct_intent":  r["classified_intent"],
            "confidence":      r["classification_confidence"] or 1.0,
            "resolution_path": r["resolution_path"],
            "bot_response":    r["bot_response"] or "",
        }
        lines.append(json.dumps(record, ensure_ascii=False))

    return "\n".join(lines)

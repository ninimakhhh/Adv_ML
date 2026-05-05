"""
TicketRepository — all DB access for tickets and messages.

Usage:
    from shared.db.repository import TicketRepository

    repo = TicketRepository()           # uses default data/tickets.db
    repo = TicketRepository(db_path)    # custom path (useful in tests)

    with repo:                          # optional context manager
        repo.create_ticket(ticket)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.db.models import Message, Ticket
from shared.utils.redaction import redact

_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_DB = _ROOT / "data" / "tickets.db"


def _row_to_ticket(row: sqlite3.Row) -> Ticket:
    d = dict(row)
    return Ticket(**d)


def _row_to_message(row: sqlite3.Row) -> Message:
    d = dict(row)
    d["is_redacted"] = bool(d["is_redacted"])
    return Message(**d)


class TicketRepository:
    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._con: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "TicketRepository":
        self._con = self._connect()
        return self

    def __exit__(self, *_) -> None:
        if self._con:
            self._con.close()
            self._con = None

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _conn(self) -> sqlite3.Connection:
        if self._con:
            return self._con
        return self._connect()

    # ------------------------------------------------------------------
    # 1. create_ticket
    # ------------------------------------------------------------------

    def create_ticket(self, ticket: Ticket) -> Ticket:
        con = self._conn()
        con.execute(
            """
            INSERT INTO tickets
                (ticket_id, user_id, created_at, resolved_at, channel,
                 classified_intent, classification_confidence, resolution_path,
                 final_status, csat_score, agent_id, tags, sentiment)
            VALUES
                (:ticket_id, :user_id, :created_at, :resolved_at, :channel,
                 :classified_intent, :classification_confidence, :resolution_path,
                 :final_status, :csat_score, :agent_id, :tags, :sentiment)
            """,
            {
                **ticket.model_dump(),
                "created_at": ticket.created_at.isoformat(),
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
                "tags": ticket.tags_as_json(),
            },
        )
        con.commit()
        return ticket

    # ------------------------------------------------------------------
    # 2. get_ticket
    # ------------------------------------------------------------------

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        con = self._conn()
        row = con.execute(
            "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
        return _row_to_ticket(row) if row else None

    # ------------------------------------------------------------------
    # 3. list_tickets
    # ------------------------------------------------------------------

    def list_tickets(
        self,
        *,
        status: Optional[str] = None,
        intent: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Ticket]:
        where, params = [], []
        if status:
            where.append("final_status = ?")
            params.append(status)
        if intent:
            where.append("classified_intent = ?")
            params.append(intent)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        params += [limit, offset]
        con = self._conn()
        rows = con.execute(
            f"SELECT * FROM tickets {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [_row_to_ticket(r) for r in rows]

    # ------------------------------------------------------------------
    # 4. update_ticket
    # ------------------------------------------------------------------

    def update_ticket(self, ticket_id: str, **fields) -> Optional[Ticket]:
        if not fields:
            return self.get_ticket(ticket_id)
        if "tags" in fields and isinstance(fields["tags"], list):
            fields["tags"] = json.dumps(fields["tags"])
        if "resolved_at" in fields and isinstance(fields["resolved_at"], datetime):
            fields["resolved_at"] = fields["resolved_at"].isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [ticket_id]
        con = self._conn()
        con.execute(
            f"UPDATE tickets SET {set_clause} WHERE ticket_id = ?", values
        )
        con.commit()
        return self.get_ticket(ticket_id)

    # ------------------------------------------------------------------
    # 5. add_message  (auto-redacts body)
    # ------------------------------------------------------------------

    def add_message(
        self,
        ticket_id: str,
        role: str,
        body: str,
        *,
        apply_redaction: bool = True,
    ) -> Message:
        is_redacted = False
        if apply_redaction:
            body, events = redact(body)
            is_redacted = len(events) > 0

        msg = Message(
            message_id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            role=role,
            body=body,
            is_redacted=is_redacted,
        )
        con = self._conn()
        con.execute(
            """
            INSERT INTO messages (message_id, ticket_id, role, body, sent_at, is_redacted)
            VALUES (:message_id, :ticket_id, :role, :body, :sent_at, :is_redacted)
            """,
            {
                **msg.model_dump(),
                "sent_at": msg.sent_at.isoformat(),
                "is_redacted": int(msg.is_redacted),
            },
        )
        con.commit()
        return msg

    # ------------------------------------------------------------------
    # 6. get_messages
    # ------------------------------------------------------------------

    def get_messages(self, ticket_id: str) -> list[Message]:
        con = self._conn()
        rows = con.execute(
            "SELECT * FROM messages WHERE ticket_id = ? ORDER BY sent_at ASC",
            (ticket_id,),
        ).fetchall()
        return [_row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # 7. close_ticket
    # ------------------------------------------------------------------

    def close_ticket(
        self,
        ticket_id: str,
        *,
        csat_score: Optional[int] = None,
        resolution_path: Optional[str] = None,
    ) -> Optional[Ticket]:
        updates: dict = {
            "final_status": "closed",
            "resolved_at": datetime.utcnow().isoformat(),
        }
        if csat_score is not None:
            updates["csat_score"] = csat_score
        if resolution_path is not None:
            updates["resolution_path"] = resolution_path
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [ticket_id]
        con = self._conn()
        con.execute(f"UPDATE tickets SET {set_clause} WHERE ticket_id = ?", values)
        con.commit()
        return self.get_ticket(ticket_id)

    # ------------------------------------------------------------------
    # 8. delete_ticket
    # ------------------------------------------------------------------

    def delete_ticket(self, ticket_id: str) -> bool:
        con = self._conn()
        cur = con.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))
        con.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # 9. get_metrics
    # ------------------------------------------------------------------

    def list_pending_escalations(self) -> list[Ticket]:
        """Escalated tickets that have not yet been human-verified."""
        con = self._conn()
        rows = con.execute(
            "SELECT * FROM tickets "
            "WHERE resolution_path LIKE 'escalated%' AND human_verified = 0 "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_ticket(r) for r in rows]

    def list_auto_classified(
        self,
        *,
        status: Optional[str] = None,
        intent: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 200,
    ) -> list[Ticket]:
        """All tickets with optional filters; no intent restriction so all tickets appear."""
        where, params = [], []
        if status:
            where.append("final_status = ?")
            params.append(status)
        if intent:
            where.append("classified_intent = ?")
            params.append(intent)
        if days:
            where.append("created_at >= DATETIME('now', ?)")
            params.append(f"-{days} days")
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        con = self._conn()
        rows = con.execute(
            f"SELECT * FROM tickets {clause} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [_row_to_ticket(r) for r in rows]

    def update_classification(
        self,
        ticket_id: str,
        intent_id: str,
        confidence: float = 1.0,
    ) -> Optional[Ticket]:
        """Human-override a ticket's classification and mark it as verified."""
        return self.update_ticket(
            ticket_id,
            classified_intent=intent_id,
            classification_confidence=confidence,
            human_verified=1,
        )

    def get_daily_counts(self, days: int = 30) -> list[dict]:
        """Return [{date, created, resolved}] for the last *days* calendar days."""
        con = self._conn()
        created_rows = con.execute(
            "SELECT DATE(created_at) AS d, COUNT(*) AS cnt FROM tickets "
            "WHERE created_at >= DATETIME('now', ?) GROUP BY DATE(created_at)",
            (f"-{days} days",),
        ).fetchall()
        resolved_rows = con.execute(
            "SELECT DATE(resolved_at) AS d, COUNT(*) AS cnt FROM tickets "
            "WHERE resolved_at IS NOT NULL AND resolved_at >= DATETIME('now', ?) "
            "GROUP BY DATE(resolved_at)",
            (f"-{days} days",),
        ).fetchall()
        created_map = {r["d"]: r["cnt"] for r in created_rows}
        resolved_map = {r["d"]: r["cnt"] for r in resolved_rows}
        all_dates = sorted(set(created_map) | set(resolved_map))
        return [
            {"date": d, "created": created_map.get(d, 0), "resolved": resolved_map.get(d, 0)}
            for d in all_dates
        ]

    def get_escalation_insight(self) -> Optional[dict]:
        """
        Find the intent with the largest week-over-week escalation increase.
        Returns {intent_id, this_week, last_week, change_pct, insight_text} or None.
        """
        con = self._conn()
        rows = con.execute(
            """
            SELECT classified_intent,
                   SUM(CASE WHEN created_at >= DATETIME('now','-7 days') THEN 1 ELSE 0 END)  AS this_week,
                   SUM(CASE WHEN created_at >= DATETIME('now','-14 days')
                             AND created_at <  DATETIME('now','-7 days') THEN 1 ELSE 0 END) AS last_week
            FROM tickets
            WHERE resolution_path LIKE 'escalated%'
              AND classified_intent IS NOT NULL
              AND created_at >= DATETIME('now','-14 days')
            GROUP BY classified_intent
            """,
        ).fetchall()
        if not rows:
            return None
        best = max(rows, key=lambda r: r["this_week"] - r["last_week"])
        this_w, last_w = best["this_week"], best["last_week"]
        change_pct = round((this_w - last_w) / max(last_w, 1) * 100)
        intent_label = (best["classified_intent"] or "unknown").replace("_", " ").title()
        if change_pct > 0:
            text = (
                f"**{intent_label}** escalated {change_pct}% more this week vs last "
                f"({this_w} vs {last_w} escalations) — consider reviewing the bot's responses for this category."
            )
        else:
            text = (
                f"**{intent_label}** is your most-escalated intent this week ({this_w} escalations). "
                f"Review bot responses to reduce handoffs."
            )
        return {
            "intent_id": best["classified_intent"],
            "intent_label": intent_label,
            "this_week": this_w,
            "last_week": last_w,
            "change_pct": change_pct,
            "insight_text": text,
        }

    def get_metrics(self) -> dict:
        con = self._conn()

        total = con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        by_status = {
            r["final_status"]: r["cnt"]
            for r in con.execute(
                "SELECT final_status, COUNT(*) AS cnt FROM tickets GROUP BY final_status"
            ).fetchall()
        }
        by_intent = {
            r["classified_intent"]: r["cnt"]
            for r in con.execute(
                "SELECT classified_intent, COUNT(*) AS cnt FROM tickets "
                "WHERE classified_intent IS NOT NULL GROUP BY classified_intent "
                "ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
        }
        by_channel = {
            r["channel"]: r["cnt"]
            for r in con.execute(
                "SELECT channel, COUNT(*) AS cnt FROM tickets GROUP BY channel"
            ).fetchall()
        }
        by_sentiment = {
            r["sentiment"]: r["cnt"]
            for r in con.execute(
                "SELECT sentiment, COUNT(*) AS cnt FROM tickets "
                "WHERE sentiment IS NOT NULL GROUP BY sentiment"
            ).fetchall()
        }
        avg_csat = con.execute(
            "SELECT AVG(csat_score) FROM tickets WHERE csat_score IS NOT NULL"
        ).fetchone()[0]
        escalated = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE resolution_path LIKE 'escalated%'"
        ).fetchone()[0]
        bot_resolved = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE resolution_path = 'bot_resolved'"
        ).fetchone()[0]
        classified_total = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE classified_intent IS NOT NULL"
        ).fetchone()[0]
        human_verified_count = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE human_verified = 1"
        ).fetchone()[0]

        # Avg first reply time (minutes): time from first user msg to first bot msg
        reply_row = con.execute(
            """
            SELECT AVG((julianday(bot_first) - julianday(user_first)) * 24 * 60) AS avg_min
            FROM (
                SELECT
                    MIN(CASE WHEN role = 'user' THEN sent_at END) AS user_first,
                    MIN(CASE WHEN role = 'bot'  THEN sent_at END) AS bot_first
                FROM messages GROUP BY ticket_id
            ) WHERE user_first IS NOT NULL AND bot_first IS NOT NULL
            """
        ).fetchone()[0]

        # Avg resolution time (hours): from first user msg to resolved_at
        resolution_row = con.execute(
            """
            SELECT AVG((julianday(t.resolved_at) - julianday(m.user_first)) * 24) AS avg_hrs
            FROM tickets t
            JOIN (
                SELECT ticket_id, MIN(sent_at) AS user_first
                FROM messages WHERE role = 'user' GROUP BY ticket_id
            ) m ON m.ticket_id = t.ticket_id
            WHERE t.resolved_at IS NOT NULL
            """
        ).fetchone()[0]

        ai_accuracy_pct = (
            round((classified_total - human_verified_count) / classified_total * 100, 1)
            if classified_total else 0.0
        )

        return {
            "total_tickets": total,
            "by_status": by_status,
            "top_intents": by_intent,
            "by_channel": by_channel,
            "by_sentiment": by_sentiment,
            "avg_csat": round(avg_csat, 2) if avg_csat else None,
            "escalated": escalated,
            "bot_resolved": bot_resolved,
            "classified_total": classified_total,
            "human_verified_count": human_verified_count,
            "escalation_rate_pct": round(escalated / total * 100, 1) if total else 0.0,
            "bot_resolution_rate_pct": round(bot_resolved / total * 100, 1) if total else 0.0,
            "ai_accuracy_pct": ai_accuracy_pct,
            "avg_first_reply_min": round(reply_row, 1) if reply_row else 0.0,
            "avg_resolution_hours": max(0.0, round(resolution_row, 2)) if resolution_row else 0.0,
        }

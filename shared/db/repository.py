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
        avg_csat = con.execute(
            "SELECT AVG(csat_score) FROM tickets WHERE csat_score IS NOT NULL"
        ).fetchone()[0]
        escalation_rate_row = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE resolution_path LIKE 'escalated%'"
        ).fetchone()[0]
        bot_resolved = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE resolution_path = 'bot_resolved'"
        ).fetchone()[0]

        return {
            "total_tickets": total,
            "by_status": by_status,
            "top_intents": by_intent,
            "avg_csat": round(avg_csat, 2) if avg_csat else None,
            "escalated": escalation_rate_row,
            "bot_resolved": bot_resolved,
            "escalation_rate_pct": (
                round(escalation_rate_row / total * 100, 1) if total else 0.0
            ),
            "bot_resolution_rate_pct": (
                round(bot_resolved / total * 100, 1) if total else 0.0
            ),
        }

"""
Tests for TicketRepository and PII redaction.

Run:
    pytest tests/test_repository.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest

from shared.db.migrate import migrate
from shared.db.models import Ticket
from shared.db.repository import TicketRepository
from shared.utils.redaction import redact


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_tickets.db"
    migrate(p)
    return p


@pytest.fixture
def repo(db_path: Path) -> TicketRepository:
    return TicketRepository(db_path)


def _new_ticket(**overrides) -> Ticket:
    defaults = dict(
        ticket_id=str(uuid.uuid4()),
        channel="chat",
        classified_intent="order_status",
        classification_confidence=0.92,
        resolution_path="pending",
        final_status="open",
        tags=["test"],
        user_id="u_test_001",
    )
    defaults.update(overrides)
    return Ticket(**defaults)


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

class TestCreateAndGet:
    def test_create_and_retrieve(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        fetched = repo.get_ticket(t.ticket_id)
        assert fetched is not None
        assert fetched.ticket_id == t.ticket_id
        assert fetched.channel == "chat"

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get_ticket("no-such-id") is None

    def test_tags_roundtrip(self, repo):
        t = _new_ticket(tags=["foo", "bar", "baz"])
        repo.create_ticket(t)
        fetched = repo.get_ticket(t.ticket_id)
        assert fetched.tags == ["foo", "bar", "baz"]


class TestListTickets:
    def test_list_all(self, repo):
        for _ in range(5):
            repo.create_ticket(_new_ticket())
        assert len(repo.list_tickets()) == 5

    def test_filter_by_status(self, repo):
        repo.create_ticket(_new_ticket(final_status="open"))
        repo.create_ticket(_new_ticket(final_status="resolved"))
        repo.create_ticket(_new_ticket(final_status="resolved"))
        assert len(repo.list_tickets(status="resolved")) == 2
        assert len(repo.list_tickets(status="open")) == 1

    def test_filter_by_intent(self, repo):
        repo.create_ticket(_new_ticket(classified_intent="cancel_order"))
        repo.create_ticket(_new_ticket(classified_intent="return_policy"))
        assert len(repo.list_tickets(intent="cancel_order")) == 1

    def test_limit_offset(self, repo):
        for _ in range(10):
            repo.create_ticket(_new_ticket())
        page1 = repo.list_tickets(limit=4, offset=0)
        page2 = repo.list_tickets(limit=4, offset=4)
        assert len(page1) == 4
        assert len(page2) == 4
        ids1 = {t.ticket_id for t in page1}
        ids2 = {t.ticket_id for t in page2}
        assert ids1.isdisjoint(ids2)


class TestUpdateTicket:
    def test_update_status(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        updated = repo.update_ticket(t.ticket_id, final_status="in_progress")
        assert updated.final_status == "in_progress"

    def test_update_tags(self, repo):
        t = _new_ticket(tags=[])
        repo.create_ticket(t)
        repo.update_ticket(t.ticket_id, tags=["urgent", "vip"])
        fetched = repo.get_ticket(t.ticket_id)
        assert fetched.tags == ["urgent", "vip"]


class TestMessages:
    def test_add_and_get_messages(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        repo.add_message(t.ticket_id, "user", "Hello, I need help.")
        repo.add_message(t.ticket_id, "bot", "Sure! What's your order number?")
        msgs = repo.get_messages(t.ticket_id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "bot"

    def test_messages_ordered_by_sent_at(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        for i in range(5):
            repo.add_message(t.ticket_id, "user", f"Message {i}")
        msgs = repo.get_messages(t.ticket_id)
        times = [m.sent_at for m in msgs]
        assert times == sorted(times)


class TestCloseTicket:
    def test_close_sets_status_and_resolved_at(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        closed = repo.close_ticket(t.ticket_id, csat_score=5, resolution_path="bot_resolved")
        assert closed.final_status == "closed"
        assert closed.csat_score == 5
        assert closed.resolved_at is not None
        assert closed.resolution_path == "bot_resolved"


class TestDeleteTicket:
    def test_delete_existing(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        assert repo.delete_ticket(t.ticket_id) is True
        assert repo.get_ticket(t.ticket_id) is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete_ticket("ghost-id") is False


class TestGetMetrics:
    def test_metrics_structure(self, repo):
        for i in range(3):
            repo.create_ticket(_new_ticket(resolution_path="bot_resolved", final_status="closed", csat_score=4))
        for i in range(2):
            repo.create_ticket(_new_ticket(resolution_path="escalated_low_confidence", final_status="in_progress"))
        m = repo.get_metrics()
        assert m["total_tickets"] == 5
        assert m["bot_resolved"] == 3
        assert m["escalated"] == 2
        assert m["escalation_rate_pct"] == 40.0
        assert m["bot_resolution_rate_pct"] == 60.0
        assert m["avg_csat"] == 4.0

    def test_metrics_empty_db(self, repo):
        m = repo.get_metrics()
        assert m["total_tickets"] == 0
        assert m["avg_csat"] is None
        assert m["escalation_rate_pct"] == 0.0


class TestContextManager:
    def test_context_manager(self, db_path):
        t = _new_ticket()
        with TicketRepository(db_path) as repo:
            repo.create_ticket(t)
            fetched = repo.get_ticket(t.ticket_id)
        assert fetched.ticket_id == t.ticket_id


# ---------------------------------------------------------------------------
# PII Redaction tests
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_luhn_valid_visa_test_card(self):
        text = "My card number is 4111 1111 1111 1111 please charge it"
        clean, events = redact(text)
        assert "[CARD_REDACTED]" in clean
        assert "4111 1111 1111 1111" not in clean
        assert any(e.kind == "CARD" for e in events)

    def test_luhn_invalid_card_not_redacted(self):
        text = "Invalid card 1234 5678 9012 3456"
        clean, events = redact(text)
        assert "1234 5678 9012 3456" in clean
        assert not any(e.kind == "CARD" for e in events)

    def test_card_with_hyphens(self):
        clean, events = redact("Card: 4111-1111-1111-1111")
        assert "[CARD_REDACTED]" in clean

    def test_card_no_separators(self):
        clean, events = redact("number 4111111111111111 thanks")
        assert "[CARD_REDACTED]" in clean

    def test_ssn_redacted(self):
        clean, events = redact("SSN: 123-45-6789")
        assert "[SSN_REDACTED]" in clean
        assert "123-45-6789" not in clean
        assert any(e.kind == "SSN" for e in events)

    def test_password_redacted(self):
        clean, events = redact("My password: SuperSecret123!")
        assert "[PASSWORD_REDACTED]" in clean
        assert "SuperSecret123!" not in clean
        assert any(e.kind == "PASSWORD" for e in events)

    def test_pwd_keyword(self):
        clean, events = redact("pwd=hunter2 is my pwd")
        assert "[PASSWORD_REDACTED]" in clean

    def test_cvv_redacted(self):
        clean, events = redact("CVV: 456 on the back of the card")
        assert "[CVV_REDACTED]" in clean
        assert any(e.kind == "CVV" for e in events)

    def test_iban_redacted(self):
        clean, events = redact("IBAN PT50000201231234567890154")
        assert "[IBAN_REDACTED]" in clean
        assert any(e.kind == "IBAN" for e in events)

    def test_clean_text_unchanged(self):
        text = "I need help tracking my order #12345"
        clean, events = redact(text)
        assert clean == text
        assert len(events) == 0

    def test_multiple_pii_in_one_message(self):
        text = "Card 4111 1111 1111 1111, SSN 111-22-3333, password: abc123"
        clean, events = redact(text)
        assert "[CARD_REDACTED]" in clean
        assert "[SSN_REDACTED]" in clean
        assert "[PASSWORD_REDACTED]" in clean
        kinds = {e.kind for e in events}
        assert kinds == {"CARD", "SSN", "PASSWORD"}

    def test_message_flagged_as_redacted(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        msg = repo.add_message(t.ticket_id, "user", "card 4111 1111 1111 1111 please")
        assert msg.is_redacted is True
        assert "[CARD_REDACTED]" in msg.body

    def test_clean_message_not_flagged(self, repo):
        t = _new_ticket()
        repo.create_ticket(t)
        msg = repo.add_message(t.ticket_id, "user", "Where is my order?")
        assert msg.is_redacted is False

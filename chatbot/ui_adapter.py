"""
ui_adapter.py — Bridge between Streamlit session_state and ConversationState.

All chatbot UI code goes through these four functions instead of touching
the orchestrator or ConversationState directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from chatbot.orchestrator import BotTurn, ChatbotOrchestrator
from chatbot.session.state import ConversationState
from chatbot.registry.loader import load_intents


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _orchestrator() -> ChatbotOrchestrator:
    if "chatbot_orchestrator" not in st.session_state:
        st.session_state.chatbot_orchestrator = ChatbotOrchestrator()
    return st.session_state.chatbot_orchestrator


def _state() -> ConversationState:
    if "conv_state" not in st.session_state:
        st.session_state.conv_state = ConversationState()
    return st.session_state.conv_state


def _messages() -> list[dict]:
    """Persistent list of {role, content, message_id, csat_done} dicts."""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    return st.session_state.chat_messages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_or_create_session() -> ConversationState:
    """Return (creating if needed) the ConversationState for this browser session."""
    return _state()


def send_user_message(text: str) -> BotTurn:
    """
    Send a typed user message through the orchestrator.
    Appends both sides to chat_messages and returns the BotTurn.
    """
    msgs = _messages()
    msgs.append({"role": "user", "content": text})

    turn = _orchestrator().handle_message(text, _state())

    msgs.append({
        "role": "bot",
        "content": turn.bot_response,
        "message_id": f"msg_{len(msgs)}",
        "escalated": turn.should_escalate,
        "csat_done": False,
        "resolved": turn.debug.get("resolution_status") == "resolved",
    })
    return turn


def send_button_action(intent_id: str) -> BotTurn:
    """
    Trigger an intent via a quick-action button (skips classifier).
    The button label is shown as the user message.
    """
    intents = load_intents()
    display_name = intents.get(intent_id, {}).get("display_name", intent_id)

    msgs = _messages()
    msgs.append({"role": "user", "content": display_name})

    turn = _orchestrator().handle_message(
        display_name, _state(), force_intent=intent_id
    )

    msgs.append({
        "role": "bot",
        "content": turn.bot_response,
        "message_id": f"msg_{len(msgs)}",
        "escalated": turn.should_escalate,
        "csat_done": False,
        "resolved": turn.debug.get("resolution_status") == "resolved",
    })
    return turn


def submit_feedback(message_id: str, thumbs: str) -> None:
    """
    Record thumbs-up/down CSAT on the ticket.
    thumbs: "up" → score 5, "down" → score 2
    """
    from shared.db.repository import TicketRepository
    from shared.db.migrate import _DB_PATH

    score = 5 if thumbs == "up" else 2
    state = _state()
    repo = TicketRepository(_DB_PATH)
    repo.update_ticket(state.ticket_id, csat_score=score)

    # Mark done so the prompt disappears
    for msg in _messages():
        if msg.get("message_id") == message_id:
            msg["csat_done"] = True
            break


def get_button_intents() -> list[dict]:
    """Return intents where is_button_visible=True, sorted by display_name."""
    intents = load_intents()
    visible = [
        {"intent_id": iid, "display_name": data["display_name"]}
        for iid, data in intents.items()
        if data.get("is_button_visible")
    ]
    return sorted(visible, key=lambda x: x["display_name"])


def reset_chat() -> None:
    """Clear chat state (start a new conversation)."""
    for key in ("conv_state", "chat_messages", "chatbot_orchestrator"):
        st.session_state.pop(key, None)

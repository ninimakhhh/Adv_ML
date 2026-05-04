"""
Intent registry loader.

Usage in the codebase:
    from chatbot.registry.loader import load_intents, get_visible_buttons

    intents = load_intents()          # dict[intent_id, intent_dict]
    buttons = get_visible_buttons()   # list of intents with is_button_visible=True
"""

import json
from functools import lru_cache
from pathlib import Path

_INTENTS_DIR = Path(__file__).parent / "intents"


@lru_cache(maxsize=None)
def load_intents() -> dict[str, dict]:
    """
    Load every *.json file in registry/intents/ and return a dict keyed by intent_id.
    Results are cached for the lifetime of the process — call load_intents.cache_clear()
    in tests or after a hot-reload to force a fresh read.
    """
    intents: dict[str, dict] = {}
    for path in sorted(_INTENTS_DIR.glob("*.json")):
        data: dict = json.loads(path.read_text(encoding="utf-8"))
        intent_id: str = data["intent_id"]
        intents[intent_id] = data
    return intents


def get_visible_buttons() -> list[dict]:
    """Return intents that should appear as quick-action buttons on chatbot open."""
    return [i for i in load_intents().values() if i.get("is_button_visible")]


def get_intents_by_category(category: str) -> list[dict]:
    """Return all intents belonging to a given category."""
    return [i for i in load_intents().values() if i.get("category") == category]


def get_intent(intent_id: str) -> dict | None:
    """Look up a single intent by id. Returns None if not found."""
    return load_intents().get(intent_id)

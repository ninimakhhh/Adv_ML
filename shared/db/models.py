"""Pydantic v2 models matching the tickets / messages schema."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Ticket(BaseModel):
    ticket_id: str
    user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    channel: str  # chat | email | web
    classified_intent: Optional[str] = None
    classification_confidence: Optional[float] = None
    resolution_path: str = "pending"
    final_status: str = "open"
    csat_score: Optional[int] = None
    agent_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    human_verified: bool = False

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("human_verified", mode="before")
    @classmethod
    def _parse_human_verified(cls, v):
        return bool(v)

    def tags_as_json(self) -> str:
        return json.dumps(self.tags)


class Message(BaseModel):
    message_id: str
    ticket_id: str
    role: str  # user | bot | agent
    body: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    is_redacted: bool = False

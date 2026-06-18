"""Pydantic request/response models for the API."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field

from .config import APPLICATION_MODES, TRAINING_CATEGORIES


class TwinCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner: str = Field(default="", max_length=120)
    tagline: str = Field(default="", max_length=280)


class SampleCreate(BaseModel):
    category: str
    content: str = Field(min_length=1)

    def validate_category(self) -> None:
        if self.category not in TRAINING_CATEGORIES:
            raise ValueError(
                f"category must be one of {TRAINING_CATEGORIES}, got {self.category!r}"
            )


class SampleOut(BaseModel):
    id: int
    category: str
    content: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class TwinSummary(BaseModel):
    id: int
    name: str
    owner: str
    tagline: str
    sample_count: int
    trained: bool
    persona_updated_at: Optional[dt.datetime]
    created_at: dt.datetime


class TwinDetail(TwinSummary):
    persona: Optional[dict] = None
    samples_by_category: dict[str, list[SampleOut]] = {}


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    mode: str = "conversation"
    messages: list[ChatMessage]

    def validate_mode(self) -> None:
        if self.mode not in APPLICATION_MODES:
            raise ValueError(
                f"mode must be one of {APPLICATION_MODES}, got {self.mode!r}"
            )

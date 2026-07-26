"""Shared enumerations used across models and schemas."""

from enum import StrEnum


class ConversationMode(StrEnum):
    """Privacy mode for rooms and matches (PRD §7).

    Normal and Incognito are a hard partition — users only ever interact with
    others in the same mode.
    """

    normal = "normal"
    incognito = "incognito"


class RoomKind(StrEnum):
    """Shape of a room. A 1-on-1 is just a room that seats two.

    Group and 1-on-1 share a single model — ``kind`` is the only thing that
    distinguishes them, so matching, transcripts, and AI all reuse one code path.
    """

    group = "group"
    one_on_one = "one_on_one"


class PlanTier(StrEnum):
    """Subscription plan a user is on (PRD §8.11)."""

    free = "free"
    premium = "premium"


class DocumentKind(StrEnum):
    """Type of admin learning content attached to a topic (PRD §8.2).

    Surfaced as a topic's "related documents" and used as trusted content the AI
    coach can draw on (the RAG source).
    """

    explanation = "explanation"
    example = "example"
    vocabulary = "vocabulary"
    mistake = "mistake"
    tip = "tip"
    sample_answer = "sample_answer"

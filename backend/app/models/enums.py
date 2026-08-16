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


class ContentStatus(StrEnum):
    """Publication state of admin-authored content (topics, docs — PRD §8.1/§8.2).

    Only ``published`` content is shown to learners; ``draft`` is work in progress
    and ``archived`` is retired but kept for reference.
    """

    draft = "draft"
    published = "published"
    archived = "archived"


class DocSectionType(StrEnum):
    """Kind of block inside a topic's documentation (PRD §8.2).

    The type decides both what a section holds and how the UI renders it:
    ``vocabulary``/``phrases`` hold ``doc_items``, ``questions`` holds
    ``questions`` (each with answer templates), and ``tips``/``text`` are
    free-form ``body`` prose.
    """

    vocabulary = "vocabulary"
    phrases = "phrases"
    questions = "questions"
    tips = "tips"
    text = "text"

    @property
    def holds_items(self) -> bool:
        """True when this section's content lives in ``doc_items``."""
        return self in (DocSectionType.vocabulary, DocSectionType.phrases)

    @property
    def holds_questions(self) -> bool:
        """True when this section's content lives in ``questions``."""
        return self is DocSectionType.questions

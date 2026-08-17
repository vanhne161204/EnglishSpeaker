"""SentenceNote model — useful sentences a user saves (PRD §8.7).

Note: no ``user_id`` yet — that arrives with the auth slice. For the first demo
notes are global.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SentenceNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved sentence. One row covers both kinds of note a learner keeps:

    * a **correction** — ``original_text`` (what they said) plus ``improved_text``
      (the better version from the AI coach or a partner);
    * a **translation pair** — ``original_text`` in ``source_lang`` plus
      ``translated_text`` in ``target_lang``, saved straight from the in-room
      translator so the learner builds their own English/Vietnamese wordbook
      (PRD §8.7, §8.10).

    The language columns are what tell the two apart, so the UI can label each
    side instead of showing a translation as if it were a mistake.
    """

    __tablename__ = "sentence_notes"

    original_text: Mapped[str | None] = mapped_column(Text, default=None)
    improved_text: Mapped[str | None] = mapped_column(Text, default=None)
    # Translation pair (PRD §8.10). Empty on a plain correction note.
    translated_text: Mapped[str | None] = mapped_column(Text, default=None)
    # BCP-47-ish short codes, e.g. "en", "vi" — matched to the translator's list.
    source_lang: Mapped[str | None] = mapped_column(String(10), default=None)
    target_lang: Mapped[str | None] = mapped_column(String(10), default=None)
    source: Mapped[str] = mapped_column(String(20), default="self", server_default="self")
    topic: Mapped[str | None] = mapped_column(String(120), default=None)

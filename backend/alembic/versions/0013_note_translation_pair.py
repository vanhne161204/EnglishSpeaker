"""save translation pairs in sentence notes

Lets a learner keep an English/Vietnamese wordbook: the in-room translator can
save its result straight into notes (PRD §8.7, §8.10).

``original_text`` already holds the source text, so only the other half and the
two language codes are new. Existing correction notes are untouched — their new
columns stay NULL, which is exactly what "this is not a translation" means.

Revision ID: 0013_note_translation_pair
Revises: 0012_categories_and_topic_docs
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_note_translation_pair"
down_revision: str | None = "0012_categories_and_topic_docs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sentence_notes", sa.Column("translated_text", sa.Text(), nullable=True))
    op.add_column("sentence_notes", sa.Column("source_lang", sa.String(length=10), nullable=True))
    op.add_column("sentence_notes", sa.Column("target_lang", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("sentence_notes", "target_lang")
    op.drop_column("sentence_notes", "source_lang")
    op.drop_column("sentence_notes", "translated_text")

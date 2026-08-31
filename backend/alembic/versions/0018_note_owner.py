"""give every sentence note an owner

Adds ``sentence_notes.user_id`` (docs/11_Security.md §11.4). Notes previously had
no owner at all, so every learner could read, edit and delete every other
learner's saved sentences.

**Existing rows are deleted, not backfilled.** There is genuinely no way to know
who saved them — the column that would say never existed. Assigning them to an
arbitrary user would show one learner somebody else's private notes, which is
the exact problem this migration closes. They are demo-era rows; losing them is
the correct trade.

The column is added nullable, rows are cleared, then it is made NOT NULL, so the
sequence works on both SQLite (dev) and Postgres (production).

Revision ID: 0018_note_owner
Revises: 0017_session_reports
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_note_owner"
down_revision: str | None = "0017_session_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sentence_notes", sa.Column("user_id", sa.Uuid(), nullable=True))

    # Ownerless rows cannot be attributed. See the module docstring.
    op.execute(sa.text("DELETE FROM sentence_notes WHERE user_id IS NULL"))

    with op.batch_alter_table("sentence_notes") as batch:
        batch.alter_column("user_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_foreign_key(
            "fk_sentence_notes_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
    op.create_index("ix_sentence_notes_user_id", "sentence_notes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_sentence_notes_user_id", table_name="sentence_notes")
    with op.batch_alter_table("sentence_notes") as batch:
        batch.drop_constraint("fk_sentence_notes_user_id", type_="foreignkey")
    op.drop_column("sentence_notes", "user_id")

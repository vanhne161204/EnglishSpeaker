"""topic sample questions for Warm-up

Revision ID: 0007_topic_sample_questions
Revises: 0006_user_plan
Create Date: 2026-07-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_topic_sample_questions"
down_revision: str | None = "0006_user_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # JSON list of admin-authored Warm-up questions (PRD §8.1). server_default
    # '[]' backfills existing rows; new rows get their list from the ORM/API.
    op.add_column(
        "topics",
        sa.Column(
            "sample_questions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("topics", "sample_questions")

"""store IELTS band reports

Creates ``session_reports`` — Coach Report layer 2 (docs §10.3.7, §10.4).

Bands are ``NUMERIC(2, 1)``, not float. They are exact half steps, and 6.5 stored
as a float comes back as 6.4999998 in something a student may screenshot.

``band_pronunciation`` is nullable and stays NULL for now: no Claude or GPT model
accepts audio, so it cannot be scored from a transcript (§10.3.11).
``overall_is_estimate`` records that the overall averages only three criteria, so
the UI can label the number honestly.

Revision ID: 0017_session_reports
Revises: 0016_sentence_feedback
Create Date: 2026-08-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_session_reports"
down_revision: str | None = "0016_sentence_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BAND = sa.Numeric(2, 1)


def upgrade() -> None:
    op.create_table(
        "session_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(length=20), server_default="conversation", nullable=False),
        sa.Column("band_fluency", _BAND, nullable=False),
        sa.Column("band_lexical", _BAND, nullable=False),
        sa.Column("band_grammar", _BAND, nullable=False),
        sa.Column("band_pronunciation", _BAND, nullable=True),
        sa.Column("band_overall", _BAND, nullable=False),
        sa.Column("pronunciation_assessed", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("overall_is_estimate", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_band", _BAND, nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=True),
        sa.Column("blockers", sa.JSON(), nullable=True),
        sa.Column("drills", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("quotes_removed", sa.Numeric(4, 0), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_reports_user_id", "session_reports", ["user_id"])
    op.create_index("ix_session_reports_room_id", "session_reports", ["room_id"])
    op.create_index("ix_report_user_created", "session_reports", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_report_user_created", table_name="session_reports")
    op.drop_index("ix_session_reports_room_id", table_name="session_reports")
    op.drop_index("ix_session_reports_user_id", table_name="session_reports")
    op.drop_table("session_reports")

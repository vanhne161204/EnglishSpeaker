"""admin panel: suspensions, persisted bans, abuse reports, audit log

Four changes, all in service of an admin panel that can actually run the product
(docs/11_Security.md §11.9):

* ``users.suspended_at`` / ``suspended_reason`` — an account can be switched off
  without deleting the person's practice history.
* ``room_bans`` — replaces a process-local Python dict. Bans previously vanished
  on every deploy, never expired, and could not be lifted by anyone.
* ``abuse_reports`` — there was no way for a learner to report what happened in a
  voice call with a stranger.
* ``admin_audit_log`` — append-only record of every privileged action.

Nothing here is destructive: no existing row is modified or removed. The old
in-memory bans are simply not carried over, because they only ever existed in the
memory of a process that has since restarted.

Revision ID: 0019_admin_panel
Revises: 0018_note_owner
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_admin_panel"
down_revision: str | None = "0018_note_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- account suspension ------------------------------------------------
    op.add_column("users", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("suspended_reason", sa.String(length=200), nullable=True))

    # --- bans that survive a deploy and can expire --------------------------
    op.create_table(
        "room_bans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("banned_by", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["banned_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_room_bans_room_user"),
    )
    op.create_index("ix_room_bans_room_user", "room_bans", ["room_id", "user_id"])
    op.create_index("ix_room_bans_created_at", "room_bans", ["created_at"])
    op.create_index("ix_room_bans_expires_at", "room_bans", ["expires_at"])

    # --- abuse reports ------------------------------------------------------
    op.create_table(
        "abuse_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reporter_id", sa.Uuid(), nullable=True),
        sa.Column("target_user_id", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("reporter_name", sa.String(length=80), server_default="", nullable=False),
        sa.Column("target_name", sa.String(length=80), server_default="", nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_abuse_reports_status_created", "abuse_reports", ["status", "created_at"]
    )
    op.create_index("ix_abuse_reports_target", "abuse_reports", ["target_user_id"])

    # --- admin audit log ----------------------------------------------------
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=80), server_default="", nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("target_type", sa.String(length=24), server_default="", nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("target_name", sa.String(length=80), server_default="", nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.create_index("ix_admin_audit_created_at", "admin_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

    op.drop_index("ix_abuse_reports_target", table_name="abuse_reports")
    op.drop_index("ix_abuse_reports_status_created", table_name="abuse_reports")
    op.drop_table("abuse_reports")

    op.drop_index("ix_room_bans_expires_at", table_name="room_bans")
    op.drop_index("ix_room_bans_created_at", table_name="room_bans")
    op.drop_index("ix_room_bans_room_user", table_name="room_bans")
    op.drop_table("room_bans")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("suspended_reason")
        batch.drop_column("suspended_at")

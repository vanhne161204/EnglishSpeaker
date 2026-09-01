"""replace users.is_admin with users.role

Admin was a boolean that got re-derived from an ``ADMIN_USERNAMES`` allowlist on
every login. Two separate problems, both fixed here:

* **Authority came from a username.** Registering with the name on the list made
  you an admin; the column was decoration. It is now the only authority, and
  nothing in the codebase reads a username to decide permissions.
* **A boolean cannot grow.** A third role — a moderator who can clear the report
  queue but not touch billing — would have meant a second boolean and a rewrite
  of every call site. ``role`` makes that a one-line migration.

Existing admins are preserved: ``is_admin = true`` becomes ``role = 'admin'``.
Nobody gains or loses access.

The downgrade is exact in the other direction (``role = 'admin'`` becomes
``is_admin = true``), so rolling back does not strand an administrator.

Revision ID: 0020_user_role
Revises: 0019_admin_panel
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_user_role"
down_revision: str | None = "0019_admin_panel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
    )
    # Carry every existing admin across before the old column disappears.
    op.execute(sa.text("UPDATE users SET role = 'admin' WHERE is_admin"))

    # batch mode so the column drop also works on SQLite (dev).
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_admin")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(sa.text("UPDATE users SET is_admin = true WHERE role = 'admin'"))

    with op.batch_alter_table("users") as batch:
        batch.drop_column("role")

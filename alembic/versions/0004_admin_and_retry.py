"""admin_users, audit_log, lead retry/manager_status fields

Revision ID: 0004_admin_and_retry
Revises: 0003_catalog
Create Date: 2026-09-19

Sprint 4. Не сеет ни одного admin_users — учётка первого администратора
создаётся отдельно скриптом scripts/create_admin.py, а не миграцией:
пароль администратора не должен появляться нигде в истории миграций/git.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_admin_and_retry"
down_revision = "0003_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("telegram_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("leads", sa.Column("telegram_last_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("leads", sa.Column("manager_status", sa.String(length=20), nullable=False, server_default="new"))

    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("username", sa.String(length=100), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="manager"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("admin_username", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("admin_users")
    op.drop_column("leads", "manager_status")
    op.drop_column("leads", "telegram_last_attempt_at")
    op.drop_column("leads", "telegram_attempts")

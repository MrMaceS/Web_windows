"""initial: leads table

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="hero_form"),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=False, index=True),
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("window_type", sa.String(length=100), nullable=True),
        sa.Column("profile_type", sa.String(length=100), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("calculated_price", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=100), nullable=True),
        sa.Column("telegram_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("telegram_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("leads")

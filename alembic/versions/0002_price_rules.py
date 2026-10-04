"""price_rules table + leads.calculator_config_json

Revision ID: 0002_price_rules
Revises: 0001_initial
Create Date: 2026-09-18
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0002_price_rules"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


WINDOW_TYPE_RULES = [
    ("window", "Окно", 8500),
    ("balcony", "Балкон", 24000),
    ("loggia", "Лоджия", 32000),
    ("vitrage", "Витраж", 45000),
]

PROFILE_RULES = [
    ("econom", "Эконом (58 мм)", 1.0),
    ("standard", "Стандарт (70 мм)", 1.3),
    ("premium", "Премиум (82 мм)", 1.7),
]


def upgrade() -> None:
    op.create_table(
        "price_rules",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("category", "code", name="uq_price_rules_category_code"),
    )

    op.add_column("leads", sa.Column("calculator_config_json", sa.Text(), nullable=True))

    price_rules_table = sa.table(
        "price_rules",
        sa.column("category", sa.String),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("value", sa.Float),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    now = datetime.now(timezone.utc)
    rows = []
    for i, (code, label, value) in enumerate(WINDOW_TYPE_RULES):
        rows.append({
            "category": "window_type", "code": code, "label": label, "value": value,
            "is_active": True, "sort_order": i, "created_at": now, "updated_at": now,
        })
    for i, (code, label, value) in enumerate(PROFILE_RULES):
        rows.append({
            "category": "profile", "code": code, "label": label, "value": value,
            "is_active": True, "sort_order": i, "created_at": now, "updated_at": now,
        })

    op.bulk_insert(price_rules_table, rows)


def downgrade() -> None:
    op.drop_column("leads", "calculator_config_json")
    op.drop_table("price_rules")

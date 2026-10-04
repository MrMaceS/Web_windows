"""catalog: categories, products, product_options, product_images

Revision ID: 0003_catalog
Revises: 0002_price_rules
Create Date: 2026-09-19

Sprint 3.

ВАЖНО (отличие от 0002_price_rules): сид-данные каталога импортируются из
catalog_seed_data.py, а не продублированы литералами в этом файле. Для
небольшого справочника цен (price_rules) дублирование в "застывшей"
миграции было оправдано; для контентного каталога, который будет активно
редактироваться через будущую админку (Sprint 4) и уже сейчас занимает
сотни строк текста, единый источник данных практичнее и не даёт двум
копиям разойтись. Если это станет проблемой при последующих миграциях
схемы (catalog_seed_data.py изменится несовместимо), сид можно будет
"заморозить" отдельной data-миграцией.
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_catalog"
down_revision = "0002_price_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True, index=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("short_description", sa.String(length=300), nullable=True),
        sa.Column("description_html", sa.Text(), nullable=True),
        sa.Column("meta_title", sa.String(length=200), nullable=True),
        sa.Column("meta_description", sa.String(length=300), nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("faq_json", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False, index=True),
        sa.Column("slug", sa.String(length=150), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short_description", sa.String(length=300), nullable=True),
        sa.Column("description_html", sa.Text(), nullable=True),
        sa.Column("calculator_window_type", sa.String(length=100), nullable=True),
        sa.Column("calculator_profile_type", sa.String(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "product_options",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("group_label", sa.String(length=100), nullable=False),
        sa.Column("value_label", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("image_path", sa.String(length=255), nullable=False),
        sa.Column("alt_text", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    _seed_catalog()


def _seed_catalog() -> None:
    import json
    from datetime import datetime, timezone

    from catalog_seed_data import CATEGORIES, PRODUCTS

    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    categories_table = sa.table(
        "categories",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("parent_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("short_description", sa.String),
        sa.column("description_html", sa.Text),
        sa.column("meta_title", sa.String),
        sa.column("meta_description", sa.String),
        sa.column("image_path", sa.String),
        sa.column("faq_json", sa.Text),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    products_table = sa.table(
        "products",
        sa.column("id", sa.Integer),
        sa.column("category_id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("short_description", sa.String),
        sa.column("description_html", sa.Text),
        sa.column("calculator_window_type", sa.String),
        sa.column("calculator_profile_type", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    options_table = sa.table(
        "product_options",
        sa.column("id", sa.Integer),
        sa.column("product_id", sa.Integer),
        sa.column("group_label", sa.String),
        sa.column("value_label", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    images_table = sa.table(
        "product_images",
        sa.column("id", sa.Integer),
        sa.column("product_id", sa.Integer),
        sa.column("image_path", sa.String),
        sa.column("alt_text", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_primary", sa.Boolean),
    )

    slug_to_id: dict[str, int] = {}
    for cat in CATEGORIES:
        parent_id = slug_to_id[cat["parent_slug"]] if cat["parent_slug"] else None
        bind.execute(
            categories_table.insert().values(
                slug=cat["slug"],
                parent_id=parent_id,
                name=cat["name"],
                short_description=cat["short_description"],
                description_html=cat["description_html"],
                meta_title=cat.get("meta_title"),
                meta_description=cat.get("meta_description"),
                image_path=cat.get("image_path"),
                faq_json=json.dumps(cat.get("faq", []), ensure_ascii=False),
                sort_order=cat.get("sort_order", 0),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        new_id = bind.execute(
            sa.select(categories_table.c.id).where(categories_table.c.slug == cat["slug"])
        ).scalar_one()
        slug_to_id[cat["slug"]] = new_id

    for i, (slug, category_slug, name, short_desc, desc_html, win_type, profile_type, options, images) in enumerate(PRODUCTS):
        bind.execute(
            products_table.insert().values(
                category_id=slug_to_id[category_slug],
                slug=slug,
                name=name,
                short_description=short_desc,
                description_html=desc_html,
                calculator_window_type=win_type,
                calculator_profile_type=profile_type,
                sort_order=i,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        product_id = bind.execute(
            sa.select(products_table.c.id).where(products_table.c.slug == slug)
        ).scalar_one()

        for j, (group_label, value_label) in enumerate(options):
            bind.execute(
                options_table.insert().values(
                    product_id=product_id, group_label=group_label, value_label=value_label, sort_order=j,
                )
            )
        for j, (filename, alt_text) in enumerate(images):
            bind.execute(
                images_table.insert().values(
                    product_id=product_id,
                    image_path=f"/static/images/catalog/{filename}",
                    alt_text=alt_text,
                    sort_order=j,
                    is_primary=(j == 0),
                )
            )


def downgrade() -> None:
    op.drop_table("product_images")
    op.drop_table("product_options")
    op.drop_table("products")
    op.drop_table("categories")

"""
database.py
SQLAlchemy-модели и настройка сессии.
"""

from datetime import datetime, timezone

import json

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, backref

from config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Lead(Base):
    """
    Единая таблица для ВСЕХ источников заявок (hero-форма, калькулятор,
    модальное окно обратного звонка). Поле `source` — откуда пришёл лид,
    нужно маркетингу для расчёта конверсии каждого блока страницы отдельно.
    """

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)

    source = Column(String(50), nullable=False, default="hero_form")

    name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=False, index=True)

    consent_given = Column(Boolean, nullable=False, default=False)

    window_type = Column(String(100), nullable=True)
    profile_type = Column(String(100), nullable=True)
    width_mm = Column(Integer, nullable=True)
    height_mm = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=True, default=1)

    calculated_price = Column(Float, nullable=True)
    calculator_config_json = Column(Text, nullable=True)

    comment = Column(Text, nullable=True)

    utm_source = Column(String(100), nullable=True)
    utm_medium = Column(String(100), nullable=True)
    utm_campaign = Column(String(100), nullable=True)

    telegram_status = Column(String(20), nullable=False, default="pending")
    telegram_error = Column(Text, nullable=True)
    telegram_attempts = Column(Integer, nullable=False, default=0)
    telegram_last_attempt_at = Column(DateTime, nullable=True)

    manager_status = Column(String(20), nullable=False, default="new")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class PriceRule(Base):
    """
    Sprint 2: управляемые цены калькулятора вместо хардкода в JS.

    Одна таблица на два вида правил (различаются `category`):
      - category="window_type": `value` — базовая цена за м² (руб.)
      - category="profile":     `value` — коэффициент профиля (например, 1.3)

    `label` — ТОЧНО тот текст, который фронтенд отправляет в полях
    window_type/profile_type (см. schemas.CalculatorLead) — так контракт
    формы не меняется, а PricingService резолвит цену по label.
    `code` — стабильный технический слаг для будущей админки (Sprint 4),
    в резолвинге цены текущим фронтендом не участвует.
    """

    __tablename__ = "price_rules"
    __table_args__ = (UniqueConstraint("category", "code", name="uq_price_rules_category_code"),)

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(20), nullable=False)
    code = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Category(Base):
    """
    Sprint 3: категория каталога, поддерживает один уровень вложенности
    (parent_id) — этого достаточно для схемы /okna/odnostvorchatye/.
    Категория с children — это "хаб" (список подкатегорий), категория без
    children — "лист", который выводит связанные с ней Product как карточки
    вариантов прямо на своей странице (см. catalog_repository.py и
    templates/pages/catalog_product.html) — отдельного URL на каждый
    товар в этой схеме нет, поэтому Product не хранит собственные
    meta_title/meta_description: индексируемая единица — именно категория.
    """

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    name = Column(String(150), nullable=False)
    short_description = Column(String(300), nullable=True)
    description_html = Column(Text, nullable=True)

    meta_title = Column(String(200), nullable=True)
    meta_description = Column(String(300), nullable=True)
    image_path = Column(String(255), nullable=True)

    faq_json = Column(Text, nullable=True)

    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    children = relationship(
        "Category",
        backref=backref("parent", remote_side=[id]),
        order_by="Category.sort_order",
    )
    products = relationship(
        "Product", back_populates="category", order_by="Product.sort_order"
    )

    def faq_items(self) -> list[dict]:
        if not self.faq_json:
            return []
        return json.loads(self.faq_json)


class Product(Base):
    """
    Sprint 3: товар/вариант внутри "листовой" категории.

    calculator_window_type/calculator_profile_type — ТОЧНО те же label'ы,
    что в price_rules (Sprint 2). Если оба заданы, "цена от" считается
    вживую через PricingService в момент рендера страницы — она НЕ хранится
    в этой таблице, чтобы каталог не мог разойтись с ценами калькулятора.
    Если поля пустые (двери, готовые окна), карточка честно показывает
    "цена по расчёту" вместо выдуманного числа.
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    slug = Column(String(150), nullable=False, unique=True, index=True)

    name = Column(String(200), nullable=False)
    short_description = Column(String(300), nullable=True)
    description_html = Column(Text, nullable=True)

    calculator_window_type = Column(String(100), nullable=True)
    calculator_profile_type = Column(String(100), nullable=True)

    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    category = relationship("Category", back_populates="products")
    options = relationship(
        "ProductOption", back_populates="product", order_by="ProductOption.sort_order",
        cascade="all, delete-orphan",
    )
    images = relationship(
        "ProductImage", back_populates="product", order_by="ProductImage.sort_order",
        cascade="all, delete-orphan",
    )

    @property
    def has_calculator_pricing(self) -> bool:
        return bool(self.calculator_window_type and self.calculator_profile_type)


class ProductOption(Base):
    """Строка характеристики товара, например ('Профиль', '70 мм, 5 камер')."""

    __tablename__ = "product_options"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    group_label = Column(String(100), nullable=False)
    value_label = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="options")


class ProductImage(Base):
    """Фото товара для галереи. Пути — плейсхолдеры вида
    /static/images/catalog/<file>.webp, реальные файлы загружаются отдельно."""

    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    image_path = Column(String(255), nullable=False)
    alt_text = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)

    product = relationship("Product", back_populates="images")


def seed_catalog_if_empty(db) -> None:
    """Сеет CATEGORIES/PRODUCTS из catalog_seed_data.py, если таблица
    категорий пуста. Единый источник данных для Alembic-миграции 0003 и
    для dev/тестового bootstrap (см. docstring catalog_seed_data.py)."""
    if db.query(Category).first() is not None:
        return

    from catalog_seed_data import CATEGORIES, PRODUCTS

    slug_to_category = {}
    for cat in CATEGORIES:
        parent_id = slug_to_category[cat["parent_slug"]].id if cat["parent_slug"] else None
        row = Category(
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
        )
        db.add(row)
        db.flush()
        slug_to_category[cat["slug"]] = row

    for i, (slug, category_slug, name, short_desc, desc_html, win_type, profile_type, options, images) in enumerate(PRODUCTS):
        product = Product(
            category_id=slug_to_category[category_slug].id,
            slug=slug,
            name=name,
            short_description=short_desc,
            description_html=desc_html,
            calculator_window_type=win_type,
            calculator_profile_type=profile_type,
            sort_order=i,
        )
        db.add(product)
        db.flush()

        for j, (group_label, value_label) in enumerate(options):
            db.add(ProductOption(product_id=product.id, group_label=group_label, value_label=value_label, sort_order=j))
        for j, (filename, alt_text) in enumerate(images):
            db.add(ProductImage(
                product_id=product.id,
                image_path=f"/static/images/catalog/{filename}",
                alt_text=alt_text,
                sort_order=j,
                is_primary=(j == 0),
            ))

    db.commit()


_DEFAULT_WINDOW_TYPE_RULES = [
    ("window", "Окно", 8500),
    ("balcony", "Балкон", 24000),
    ("loggia", "Лоджия", 32000),
    ("vitrage", "Витраж", 45000),
]
_DEFAULT_PROFILE_RULES = [
    ("econom", "Эконом (58 мм)", 1.0),
    ("standard", "Стандарт (70 мм)", 1.3),
    ("premium", "Премиум (82 мм)", 1.7),
]


def seed_default_price_rules(db) -> None:
    """
    Публичная версия — принимает произвольную Session, поэтому её можно
    переиспользовать и для продового движка (через _seed_default_price_rules_if_empty),
    и для изолированной тестовой БД (см. tests/conftest.py), где init_db()
    сеет данные в другой (не тестовый) движок и тестам не помогает.
    """
    if db.query(PriceRule).first() is not None:
        return
    rows = []
    for i, (code, label, value) in enumerate(_DEFAULT_WINDOW_TYPE_RULES):
        rows.append(PriceRule(category="window_type", code=code, label=label, value=value, sort_order=i))
    for i, (code, label, value) in enumerate(_DEFAULT_PROFILE_RULES):
        rows.append(PriceRule(category="profile", code=code, label=label, value=value, sort_order=i))
    db.add_all(rows)
    db.commit()


def _seed_default_price_rules_if_empty() -> None:
    db = SessionLocal()
    try:
        seed_default_price_rules(db)
    finally:
        db.close()


def init_db() -> None:
    """
    Создаёт таблицы напрямую из моделей и досевает базовые price_rules,
    если таблица пуста.
    Используется как fallback для локального быстрого старта (например,
    в тестах на SQLite). На реальном проде схему разворачивает Alembic
    (см. README → раздел "Миграции") — эта функция не заменяет миграции,
    а лишь даёт рабочее состояние "из коробки" для dev/тестов.
    """
    Base.metadata.create_all(bind=engine)
    _seed_default_price_rules_if_empty()
    _seed_catalog_if_empty()


def _seed_catalog_if_empty() -> None:
    db = SessionLocal()
    try:
        seed_catalog_if_empty(db)
    finally:
        db.close()


class AdminUser(Base):
    """
    Sprint 4: пользователь админ-панели.

    Роли (простой RBAC, без отдельной таблицы прав — двух ролей достаточно
    для текущего объёма функций):
      - "admin"   — полный доступ, включая управление пользователями и ценами
      - "manager" — только заявки (просмотр, смена статуса, ретрай Telegram)

    Пароль хранится только как PBKDF2-хеш (security.py), сам пароль
    нигде не логируется и не сохраняется в открытом виде.
    """

    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="manager")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    """
    Sprint 4: журнал действий администраторов над ценами/каталогом/лидами.
    before_json/after_json — снимки состояния до/после (только изменяемые
    поля), не полный дамп строки — чтобы не раздувать таблицу и не хранить
    в аудите персональные данные лида сверх необходимого (телефон/имя не
    дублируются в аудит отдельно, если действие их не меняло).
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    admin_username = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=True)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def get_db():
    """FastAPI dependency: одна сессия на запрос, гарантированно закрывается."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

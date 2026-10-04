"""
catalog_repository.py
Sprint 3: слой доступа к данным каталога — отделяет запросы к БД от
роутов в main.py. Роуты вызывают функции отсюда и работают с готовыми
объектами/структурами, не строя запросы сами.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from database import Category, Product
from pricing_service import PricingService, PricingError, MIN_BILLABLE_AREA_M2


def category_url(category: Category) -> str:
    if category.parent_id and category.parent:
        return f"/{category.parent.slug}/{category.slug}/"
    return f"/{category.slug}/"


def get_root_categories(db: Session) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.parent_id.is_(None), Category.is_active.is_(True))
        .order_by(Category.sort_order)
        .all()
    )


def resolve_category_by_path(db: Session, slug: str, child_slug: Optional[str] = None) -> Optional[Category]:
    """Резолвит /{slug}/ или /{slug}/{child_slug}/ в объект Category.
    Возвращает None, если путь не соответствует ни одной активной категории —
    роут в main.py превращает это в 404."""
    root = (
        db.query(Category)
        .options(joinedload(Category.children))
        .filter(Category.slug == slug, Category.parent_id.is_(None), Category.is_active.is_(True))
        .first()
    )
    if root is None:
        return None

    if child_slug is None:
        return root

    for child in root.children:
        if child.slug == child_slug and child.is_active:
            return child
    return None


def get_breadcrumbs(category: Category) -> list[tuple[str, Optional[str]]]:
    """[(label, url), ...] — от главной до текущей страницы включительно.
    URL текущей (последней) страницы — None, см. partials/breadcrumbs.html."""
    chain: list[Category] = []
    node: Optional[Category] = category
    while node is not None:
        chain.append(node)
        node = node.parent

    chain.reverse()
    items: list[tuple[str, Optional[str]]] = [("Главная", "/")]
    for i, cat in enumerate(chain):
        is_last = i == len(chain) - 1
        items.append((cat.name, None if is_last else category_url(cat)))
    return items


def get_similar_categories(db: Session, category: Category, limit: int = 3) -> list[Category]:
    """'Похожие решения': для дочерней категории — соседние категории
    того же родителя; для категории верхнего уровня — другие категории
    верхнего уровня. Всегда исключает саму себя."""
    if category.parent_id:
        query = db.query(Category).filter(
            Category.parent_id == category.parent_id,
            Category.id != category.id,
            Category.is_active.is_(True),
        )
    else:
        query = db.query(Category).filter(
            Category.parent_id.is_(None),
            Category.id != category.id,
            Category.is_active.is_(True),
        )
    return query.order_by(Category.sort_order).limit(limit).all()


def get_products_for_category(db: Session, category: Category) -> list[Product]:
    return (
        db.query(Product)
        .options(joinedload(Product.options), joinedload(Product.images))
        .filter(Product.category_id == category.id, Product.is_active.is_(True))
        .order_by(Product.sort_order)
        .all()
    )


@dataclass(frozen=True)
class ProductPriceFrom:
    available: bool
    total_price: Optional[float] = None


def get_product_price_from(db: Session, product: Product, discount_percent: int) -> ProductPriceFrom:
    """
    Считает "цену от" ЖИВЬЁМ через PricingService на минимальной
    тарифицируемой площади (MIN_BILLABLE_AREA_M2, т.е. 1×1 м) и количестве 1.
    Это НЕ хранимое значение — каталог физически не может разойтись с
    актуальными price_rules/скидкой из Sprint 2.

    Если у товара не заданы calculator_window_type/profile_type (двери,
    готовые окна — вне модели цен Sprint 2) или соответствующее правило
    отключено/удалено, возвращает available=False — шаблон показывает
    "цена по расчёту" вместо выдуманного числа.
    """
    if not product.has_calculator_pricing:
        return ProductPriceFrom(available=False)

    side_mm = int((MIN_BILLABLE_AREA_M2 ** 0.5) * 1000)
    pricing = PricingService(db, discount_percent=discount_percent)
    try:
        breakdown = pricing.estimate(
            window_type=product.calculator_window_type,
            profile_type=product.calculator_profile_type,
            width_mm=side_mm,
            height_mm=side_mm,
            quantity=1,
        )
    except PricingError:
        return ProductPriceFrom(available=False)

    return ProductPriceFrom(available=True, total_price=breakdown.total_price)


def get_all_active_categories(db: Session) -> list[Category]:
    """Для sitemap.xml — все активные категории (и хабы, и листья)."""
    return (
        db.query(Category)
        .options(joinedload(Category.parent))
        .filter(Category.is_active.is_(True))
        .order_by(Category.sort_order)
        .all()
    )

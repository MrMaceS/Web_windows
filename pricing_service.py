"""
pricing_service.py
Sprint 2: единственный источник истины по цене калькулятора.
"""

from dataclasses import dataclass, asdict
import json

from sqlalchemy.orm import Session

from database import PriceRule

MIN_BILLABLE_AREA_M2 = 1.0


class PricingError(ValueError):
    """Ошибка расчёта: неизвестная опция калькулятора или недоступное правило цены."""


@dataclass(frozen=True)
class PricingBreakdown:
    window_type: str
    profile_type: str
    width_mm: int
    height_mm: int
    quantity: int
    area_m2: float
    base_price: float
    multiplier: float
    subtotal: float
    discount_percent: int
    discount_amount: float
    total_price: float
    currency: str = "RUB"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class PricingService:
    def __init__(self, db: Session, discount_percent: int):
        self.db = db
        self.discount_percent = discount_percent

    def _get_rule_value(self, category: str, label: str) -> float:
        rule = (
            self.db.query(PriceRule)
            .filter(
                PriceRule.category == category,
                PriceRule.label == label,
                PriceRule.is_active.is_(True),
            )
            .first()
        )
        if rule is None:
            raise PricingError(f"Неизвестный вариант калькулятора: {label!r}")
        return rule.value

    def estimate(
        self,
        window_type: str,
        profile_type: str,
        width_mm: int,
        height_mm: int,
        quantity: int,
    ) -> PricingBreakdown:
        if not (200 <= width_mm <= 4000) or not (200 <= height_mm <= 4000):
            raise PricingError("Размер должен быть от 200 до 4000 мм")
        if not (1 <= quantity <= 50):
            raise PricingError("Количество должно быть от 1 до 50")

        base_price = self._get_rule_value("window_type", window_type)
        multiplier = self._get_rule_value("profile", profile_type)

        area_m2 = max((width_mm * height_mm) / 1_000_000, MIN_BILLABLE_AREA_M2)
        subtotal = base_price * multiplier * area_m2 * quantity

        discount_amount = subtotal * (self.discount_percent / 100)
        total_price = round(subtotal - discount_amount)

        return PricingBreakdown(
            window_type=window_type,
            profile_type=profile_type,
            width_mm=width_mm,
            height_mm=height_mm,
            quantity=quantity,
            area_m2=round(area_m2, 3),
            base_price=base_price,
            multiplier=multiplier,
            subtotal=round(subtotal, 2),
            discount_percent=self.discount_percent,
            discount_amount=round(discount_amount, 2),
            total_price=total_price,
        )

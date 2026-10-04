"""
schemas.py
Pydantic-схемы валидации.
"""

import re
from typing import Optional

from pydantic import BaseModel, field_validator

ALLOWED_HERO_SOURCES = {"hero_form", "callback_widget"}


PHONE_RAW_RE = re.compile(r"^\+?[0-9\s\-\(\)]{10,18}$")


def normalize_phone(raw: str) -> str:
    """
    Приводит телефон к единому формату +7XXXXXXXXXX.
    Так лид всегда сохраняется в БД и уходит в Telegram в одном виде,
    независимо от того, как пользователь его ввёл (с скобками, пробелами,
    с 8 или +7 в начале).
    """
    digits = re.sub(r"\D", "", raw)

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits

    if len(digits) != 11 or not digits.startswith("7"):
        raise ValueError("Некорректный формат телефона")

    return "+" + digits


class LeadBase(BaseModel):
    name: Optional[str] = None
    phone: str
    comment: Optional[str] = None

    consent: bool

    website: Optional[str] = ""

    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not PHONE_RAW_RE.match(v.strip()):
            raise ValueError("Некорректный формат телефона")
        return normalize_phone(v)

    @field_validator("consent")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Необходимо согласие на обработку персональных данных")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 100:
            raise ValueError("Слишком длинное имя")
        return v


class HeroFormLead(LeadBase):
    """
    Заявка из формы первого экрана, модалки 'Вызвать замерщика' или
    'Заказать звонок'. Поле `source` позволяет маркетингу отдельно считать
    конверсию каждого из этих трёх мест на странице — сам источник задаёт
    фронтенд (data-source на форме), но ограничен строгим allow-list,
    чтобы клиент не мог подставить произвольную строку.
    """
    source: str = "hero_form"

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in ALLOWED_HERO_SOURCES:
            return "hero_form"
        return v


class DimensionsMixin(BaseModel):
    """
    Общая валидация размеров/количества — используется и в заявке
    калькулятора (CalculatorLead), и в эндпоинте предварительного расчёта
    (CalculatorEstimateRequest), чтобы не дублировать пределы в двух местах.
    Те же границы дополнительно проверяются в PricingService — это
    осознанное дублирование (defense in depth): Pydantic отвечает за формат
    запроса, PricingService — источник истины для самого расчёта.
    """
    width_mm: int
    height_mm: int
    quantity: int = 1

    @field_validator("width_mm", "height_mm")
    @classmethod
    def validate_dimensions(cls, v: int) -> int:
        if not (200 <= v <= 4000):
            raise ValueError("Размер должен быть от 200 до 4000 мм")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("Некорректное количество")
        return v


class CalculatorEstimateRequest(DimensionsMixin):
    """
    Sprint 2. Тело запроса POST /api/v1/calculator/estimate — предварительный
    расчёт БЕЗ создания заявки (шаг 3 → 4 калькулятора на фронте).
    window_type/profile_type — те же строки-лейблы, что видит пользователь
    в UI (см. templates/partials/calculator.html, data-value), они же
    хранятся как PriceRule.label в БД.
    """
    window_type: str
    profile_type: str


class CalculatorEstimateResponse(BaseModel):
    """Полная расшифровка расчёта — фронт показывает total_price,
    остальное пригодится для будущей детализации ('из чего складывается цена')."""
    area_m2: float
    base_price: float
    multiplier: float
    subtotal: float
    discount_percent: int
    discount_amount: float
    total_price: float
    currency: str = "RUB"


class CalculatorLead(LeadBase, DimensionsMixin):
    """
    Заявка из финального шага калькулятора.

    Sprint 2: calculated_price от клиента БОЛЬШЕ НЕ ЯВЛЯЕТСЯ источником
    истины — сервер всегда пересчитывает цену через PricingService по
    window_type/profile_type/width_mm/height_mm/quantity (см. main.py).
    Поле оставлено Optional только для обратной совместимости формата
    запроса старых клиентов — если оно пришло, оно тихо игнорируется при
    сохранении и используется лишь для лога расхождений (см. main.py).
    """
    window_type: str
    profile_type: str
    calculated_price: Optional[float] = None


class LeadResponse(BaseModel):
    """Ответ клиенту после успешной отправки заявки."""
    success: bool
    message: str
    lead_id: int

"""tests/test_pricing.py — юнит-тесты pricing_service.PricingService."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, seed_default_price_rules
from pricing_service import PricingService, PricingError


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    seed_default_price_rules(session)
    try:
        yield session
    finally:
        session.close()


def test_estimate_basic_formula(db_session):
    service = PricingService(db_session, discount_percent=15)
    result = service.estimate(
        window_type="Окно",
        profile_type="Стандарт (70 мм)",
        width_mm=1300,
        height_mm=1400,
        quantity=1,
    )
    area = 1.3 * 1.4
    expected_subtotal = 8500 * 1.3 * area
    expected_total = round(expected_subtotal * 0.85)

    assert result.area_m2 == round(area, 3)
    assert result.base_price == 8500
    assert result.multiplier == 1.3
    assert result.total_price == expected_total
    assert result.discount_percent == 15


def test_estimate_enforces_minimum_billable_area(db_session):
    """Маленькая форточка (меньше 1 м²) всё равно тарифицируется как 1 м² —
    это защита от того, что монтажный выезд на форточку станет дешевле выезда."""
    service = PricingService(db_session, discount_percent=0)
    result = service.estimate(
        window_type="Окно",
        profile_type="Эконом (58 мм)",
        width_mm=400,
        height_mm=400,
        quantity=1,
    )
    assert result.area_m2 == 1.0
    assert result.total_price == round(8500 * 1.0 * 1.0)


def test_estimate_quantity_multiplies_total(db_session):
    service = PricingService(db_session, discount_percent=0)
    one = service.estimate("Окно", "Эконом (58 мм)", 1300, 1400, 1)
    three = service.estimate("Окно", "Эконом (58 мм)", 1300, 1400, 3)
    assert three.total_price == round(one.subtotal * 3)


def test_estimate_discount_zero_means_no_discount(db_session):
    service = PricingService(db_session, discount_percent=0)
    result = service.estimate("Окно", "Стандарт (70 мм)", 1300, 1400, 1)
    assert result.discount_amount == 0
    assert result.total_price == round(result.subtotal)


def test_estimate_unknown_window_type_raises(db_session):
    service = PricingService(db_session, discount_percent=15)
    with pytest.raises(PricingError):
        service.estimate("НЛО", "Стандарт (70 мм)", 1300, 1400, 1)


def test_estimate_unknown_profile_raises(db_session):
    service = PricingService(db_session, discount_percent=15)
    with pytest.raises(PricingError):
        service.estimate("Окно", "Алмазный", 1300, 1400, 1)


def test_estimate_inactive_rule_is_treated_as_unknown(db_session):
    from database import PriceRule

    rule = (
        db_session.query(PriceRule)
        .filter(PriceRule.category == "window_type", PriceRule.label == "Витраж")
        .first()
    )
    rule.is_active = False
    db_session.commit()

    service = PricingService(db_session, discount_percent=15)
    with pytest.raises(PricingError):
        service.estimate("Витраж", "Стандарт (70 мм)", 1300, 1400, 1)


@pytest.mark.parametrize("width,height", [(100, 1400), (1300, 100), (5000, 1400), (1300, 5000)])
def test_estimate_rejects_out_of_range_dimensions(db_session, width, height):
    service = PricingService(db_session, discount_percent=15)
    with pytest.raises(PricingError):
        service.estimate("Окно", "Стандарт (70 мм)", width, height, 1)


@pytest.mark.parametrize("quantity", [0, -1, 51, 1000])
def test_estimate_rejects_out_of_range_quantity(db_session, quantity):
    service = PricingService(db_session, discount_percent=15)
    with pytest.raises(PricingError):
        service.estimate("Окно", "Стандарт (70 мм)", 1300, 1400, quantity)


def test_breakdown_to_json_roundtrip(db_session):
    import json

    service = PricingService(db_session, discount_percent=15)
    result = service.estimate("Окно", "Стандарт (70 мм)", 1300, 1400, 1)
    parsed = json.loads(result.to_json())
    assert parsed["total_price"] == result.total_price
    assert parsed["window_type"] == "Окно"

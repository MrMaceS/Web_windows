"""tests/test_phone.py — юнит-тесты нормализации телефона (schemas.normalize_phone)."""

import pytest

from schemas import normalize_phone, HeroFormLead


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+7 900 123-45-67", "+79001234567"),
        ("89001234567", "+79001234567"),
        ("79001234567", "+79001234567"),
        ("9001234567", "+79001234567"),
        ("+7 (900) 123 45 67", "+79001234567"),
    ],
)
def test_normalize_phone_variants(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_phone_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_phone("123")


def test_hero_form_lead_normalizes_phone_end_to_end():
    lead = HeroFormLead(phone="8 (900) 123-45-67", consent=True)
    assert lead.phone == "+79001234567"


def test_hero_form_lead_requires_true_consent():
    with pytest.raises(ValueError):
        HeroFormLead(phone="+79001234567", consent=False)


def test_hero_form_lead_rejects_invalid_source():
    lead = HeroFormLead(phone="+79001234567", consent=True, source="something_weird")
    assert lead.source == "hero_form"

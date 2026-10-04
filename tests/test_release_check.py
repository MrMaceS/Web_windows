"""
tests/test_release_check.py — release_check.py не даёт опубликовать сайт с демо-данными
и не шумит, когда всё заполнено.
"""

import pytest

import release_check
from config import Settings

GOOD = dict(
    environment="production",
    company_name="ООО Окна Плюс",
    company_phone="+7 (495) 123-45-67",
    company_address="г. Казань, ул. Баумана, 10",
    domain="https://okna-plus.ru",
    calculator_discount_percent=7,
    admin_session_secret="x" * 40,
    database_url="postgresql+psycopg2://app:S0me-Str0ng-pass@db:5432/app",
    allowed_origins="https://okna-plus.ru",
    legal_entity_name="ООО «Окна Плюс», ИНН 0000000000",
    telegram_bot_token="t",
    telegram_chat_id="c",
    redis_url="redis://redis:6379/0",
    yandex_metrika_id="12345678",
)


def make(**over):
    # _env_file=None: тест не должен зависеть от локального .env разработчика
    return Settings(_env_file=None, **{**GOOD, **over})


@pytest.fixture()
def no_todos(monkeypatch):
    monkeypatch.setattr(release_check, "visible_todos", lambda: [])
    monkeypatch.setattr(release_check, "has_og_image", lambda: True)


def test_fully_configured_site_has_no_blockers_or_warnings(no_todos):
    blockers, warnings = release_check.check(make())
    assert blockers == [] and warnings == []


@pytest.mark.parametrize(
    "field", ["company_name", "company_phone", "company_address", "domain", "calculator_discount_percent"]
)
def test_business_field_left_at_demo_default_is_a_blocker(no_todos, field):
    kwargs = {**GOOD}
    kwargs.pop(field)  # поле не передано => берётся демо-значение из config.py
    blockers, _ = release_check.check(Settings(_env_file=None, **kwargs))
    assert any(field.upper() in b for b in blockers), blockers


def test_discount_is_flagged_even_though_default_value_is_valid_looking(no_todos):
    """15% — правдоподобное число, поэтому сравнением значений его не поймать: нужна явная заданность."""
    kwargs = {k: v for k, v in GOOD.items() if k != "calculator_discount_percent"}
    s = Settings(_env_file=None, **kwargs)
    assert s.calculator_discount_percent == 15
    assert any("CALCULATOR_DISCOUNT_PERCENT" in b for b in release_check.check(s)[0])


def test_explicitly_setting_default_looking_value_is_accepted(no_todos):
    """Владелец подтвердил, что скидка действительно 15% — это его осознанное решение."""
    blockers, _ = release_check.check(make(calculator_discount_percent=15))
    assert blockers == []


@pytest.mark.parametrize("domain", ["https://example.com", "http://okna-plus.ru", "https://okna-plus.ru/", "okna-plus.ru"])
def test_bad_domain_is_a_blocker(no_todos, domain):
    blockers, _ = release_check.check(make(domain=domain, allowed_origins=domain))
    assert any("DOMAIN" in b for b in blockers), blockers


def test_short_phone_is_a_blocker(no_todos):
    assert any("COMPANY_PHONE" in b for b in release_check.check(make(company_phone="+7 (900)"))[0])


@pytest.mark.parametrize(
    "over, needle",
    [
        ({"environment": "development"}, "ENVIRONMENT"),
        ({"admin_session_secret": "dev-insecure-secret-change-me"}, "ADMIN_SESSION_SECRET"),
        ({"admin_session_secret": "short"}, "ADMIN_SESSION_SECRET"),
        ({"database_url": "postgresql://u:window_pass@db/x"}, "DATABASE_URL"),
        ({"allowed_origins": "http://localhost:8000"}, "ALLOWED_ORIGINS"),
    ],
)
def test_insecure_settings_are_blockers(no_todos, over, needle):
    assert any(needle in b for b in release_check.check(make(**over))[0])


def test_missing_optional_things_are_warnings_not_blockers(no_todos):
    blockers, warnings = release_check.check(make(legal_entity_name="", telegram_bot_token="", redis_url="", yandex_metrika_id=""))
    assert blockers == []
    text = " ".join(warnings)
    for needle in ("LEGAL_ENTITY_NAME", "TELEGRAM", "REDIS_URL", "YANDEX_METRIKA_ID"):
        assert needle in text


def test_visible_todos_ignore_comments_and_admin(tmp_path, monkeypatch):
    (tmp_path / "pages").mkdir()
    (tmp_path / "admin").mkdir()
    (tmp_path / "pages" / "ok.html").write_text(
        "{# TODO: комментарий Jinja #}\n<!-- TODO: html-комментарий -->\n<p>Текст</p>", encoding="utf-8"
    )
    (tmp_path / "admin" / "x.html").write_text("<p>TODO в админке не считается</p>", encoding="utf-8")
    (tmp_path / "pages" / "bad.html").write_text("<p>TODO: заполнить</p>", encoding="utf-8")
    monkeypatch.setattr(release_check, "TEMPLATES", tmp_path)
    monkeypatch.setattr(release_check, "ROOT", tmp_path)
    found = release_check.visible_todos()
    assert len(found) == 1 and "bad.html" in found[0]


def test_main_exit_code_reflects_blockers(monkeypatch, capsys, no_todos):
    import config

    monkeypatch.setattr(config, "settings", make(environment="development"))
    assert release_check.main() == 1
    assert "БЛОКЕР" in capsys.readouterr().out
    monkeypatch.setattr(config, "settings", make())
    assert release_check.main() == 0


@pytest.mark.parametrize(
    "field, demo",
    [("company_name", "OknoPro"), ("company_phone", "+7 (900) 000-00-00"), ("company_address", "г. Москва, ул. Примерная, 1")],
)
def test_explicit_but_demo_value_is_a_blocker(no_todos, field, demo):
    """cp .env.example .env раньше делал поле «явно заданным» с демо-значением и обманывал проверку."""
    blockers, _ = release_check.check(make(**{field: demo}))
    assert any(field.upper() in b and "демо" in b for b in blockers), blockers


def test_env_example_does_not_hide_placeholders():
    """В .env.example ключевые бизнес-поля закомментированы, иначе cp .env.example .env маскирует плейсхолдеры."""
    from pathlib import Path

    active = {
        line.split("=", 1)[0]
        for line in (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    must_be_commented = {"COMPANY_NAME", "COMPANY_PHONE", "COMPANY_ADDRESS", "DOMAIN", "CALCULATOR_DISCOUNT_PERCENT"}
    assert not (active & must_be_commented), f"раскомментированы в .env.example: {active & must_be_commented}"

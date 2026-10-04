"""tests/test_leads.py — тесты эндпоинтов /api/lead и /api/calculator-lead."""

from database import Lead


def test_hero_lead_requires_consent(client):
    response = client.post("/api/lead", json={"phone": "+79001234567"})
    assert response.status_code == 422


def test_hero_lead_success(client):
    response = client.post("/api/lead", json={"phone": "+79001234567", "consent": True, "name": "Иван"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["lead_id"] > 0


def test_hero_lead_honeypot_is_silently_dropped(client):
    response = client.post(
        "/api/lead",
        json={"phone": "+79001234567", "consent": True, "website": "http://spam.example"},
    )
    assert response.status_code == 200
    assert response.json()["lead_id"] == 0


def test_calculator_lead_success(client):
    payload = {
        "phone": "+79001234567",
        "consent": True,
        "window_type": "Окно",
        "profile_type": "Стандарт (70 мм)",
        "width_mm": 1300,
        "height_mm": 1400,
        "quantity": 1,
        "calculated_price": 12000,
    }
    response = client.post("/api/calculator-lead", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_calculator_lead_rejects_out_of_range_dimensions(client):
    payload = {
        "phone": "+79001234567",
        "consent": True,
        "window_type": "Окно",
        "profile_type": "Стандарт (70 мм)",
        "width_mm": 50,
        "height_mm": 1400,
        "quantity": 1,
        "calculated_price": 12000,
    }
    response = client.post("/api/calculator-lead", json=payload)
    assert response.status_code == 422


def test_calculator_lead_ignores_tampered_client_price(client):
    """Sprint 2: клиент присылает заведомо неверную цену — сервер должен
    её проигнорировать и сохранить собственный расчёт."""
    import database
    import main

    payload = {
        "phone": "+79001234567",
        "consent": True,
        "window_type": "Окно",
        "profile_type": "Стандарт (70 мм)",
        "width_mm": 1300,
        "height_mm": 1400,
        "quantity": 1,
        "calculated_price": 1,
    }
    response = client.post("/api/calculator-lead", json=payload)
    assert response.status_code == 200
    lead_id = response.json()["lead_id"]

    area = 1.3 * 1.4
    expected_subtotal = 8500 * 1.3 * area
    expected_total = round(expected_subtotal * 0.85)

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        assert lead.calculated_price == expected_total
        assert lead.calculated_price != 1
        assert lead.calculator_config_json is not None
    finally:
        db.close()


def test_calculator_lead_rejects_unknown_window_type(client):
    payload = {
        "phone": "+79001234567",
        "consent": True,
        "window_type": "Летающая тарелка",
        "profile_type": "Стандарт (70 мм)",
        "width_mm": 1300,
        "height_mm": 1400,
        "quantity": 1,
    }
    response = client.post("/api/calculator-lead", json=payload)
    assert response.status_code == 422


def test_calculator_estimate_endpoint_success(client):
    payload = {
        "window_type": "Балкон",
        "profile_type": "Премиум (82 мм)",
        "width_mm": 2000,
        "height_mm": 1400,
        "quantity": 2,
    }
    response = client.post("/api/v1/calculator/estimate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["base_price"] == 24000
    assert data["multiplier"] == 1.7
    assert data["total_price"] > 0
    assert "lead_id" not in data


def test_calculator_estimate_endpoint_rejects_unknown_profile(client):
    payload = {
        "window_type": "Окно",
        "profile_type": "Золотой (999 мм)",
        "width_mm": 1300,
        "height_mm": 1400,
        "quantity": 1,
    }
    response = client.post("/api/v1/calculator/estimate", json=payload)
    assert response.status_code == 422


def test_calculator_estimate_endpoint_rejects_bad_dimensions(client):
    payload = {
        "window_type": "Окно",
        "profile_type": "Стандарт (70 мм)",
        "width_mm": 10,
        "height_mm": 1400,
        "quantity": 1,
    }
    response = client.post("/api/v1/calculator/estimate", json=payload)
    assert response.status_code == 422


def test_lead_persisted_with_correct_source(client):
    import database
    import main

    response = client.post(
        "/api/lead",
        json={"phone": "+79007654321", "consent": True, "source": "callback_widget"},
    )
    assert response.status_code == 200
    lead_id = response.json()["lead_id"]

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        assert lead is not None
        assert lead.source == "callback_widget"
        assert lead.phone == "+79007654321"
        assert lead.consent_given is True
    finally:
        db.close()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_rate_limit_blocks_after_threshold(client):
    for i in range(5):
        response = client.post("/api/lead", json={"phone": f"+7900000000{i}", "consent": True})
        assert response.status_code == 200

    response = client.post("/api/lead", json={"phone": "+79000000009", "consent": True})
    assert response.status_code == 429


def test_get_db_dependency_yields_and_closes_session():
    from database import get_db

    gen = get_db()
    db = next(gen)
    assert db.query(Lead).count() >= 0
    gen.close()

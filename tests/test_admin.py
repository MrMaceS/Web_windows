"""tests/test_admin.py — Sprint 4: аутентификация, RBAC, CRUD, аудит."""


def test_dashboard_requires_login(client):
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_login_with_wrong_password_returns_401(client, admin_user):
    response = client.post("/admin/login", data={"username": "test-admin", "password": "wrong"})
    assert response.status_code == 401
    assert "Неверный логин или пароль" in response.text


def test_login_with_unknown_username_returns_401(client):
    response = client.post("/admin/login", data={"username": "nobody", "password": "whatever"})
    assert response.status_code == 401


def test_login_success_grants_dashboard_access(admin_client):
    response = admin_client.get("/admin/")
    assert response.status_code == 200
    assert "Дашборд" in response.text


def test_logout_revokes_access(admin_client):
    response = admin_client.post("/admin/logout", follow_redirects=False)
    assert response.status_code == 303
    response = admin_client.get("/admin/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_manager_cannot_access_price_rules(manager_client):
    response = manager_client.get("/admin/price-rules")
    assert response.status_code == 403


def test_manager_cannot_access_catalog(manager_client):
    response = manager_client.get("/admin/catalog/categories")
    assert response.status_code == 403


def test_manager_cannot_access_users(manager_client):
    response = manager_client.get("/admin/users")
    assert response.status_code == 403


def test_manager_can_access_leads(manager_client):
    response = manager_client.get("/admin/leads")
    assert response.status_code == 200


def test_admin_can_access_everything(admin_client):
    for path in ["/admin/", "/admin/leads", "/admin/price-rules", "/admin/catalog/categories", "/admin/users", "/admin/audit"]:
        response = admin_client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"


def test_price_rule_update_changes_calculator_result(admin_client):
    """Изменение цены в админке должно немедленно влиять на публичный
    /api/v1/calculator/estimate — иначе управление ценами бесполезно."""
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        rule = db.query(database.PriceRule).filter_by(category="window_type", label="Окно").first()
        rule_id = rule.id
    finally:
        db.close()

    before = admin_client.post(
        "/api/v1/calculator/estimate",
        json={"window_type": "Окно", "profile_type": "Стандарт (70 мм)", "width_mm": 1300, "height_mm": 1400, "quantity": 1},
    ).json()

    response = admin_client.post(f"/admin/price-rules/{rule_id}", data={"value": "99999", "is_active": "on"}, follow_redirects=False)
    assert response.status_code == 303

    after = admin_client.post(
        "/api/v1/calculator/estimate",
        json={"window_type": "Окно", "profile_type": "Стандарт (70 мм)", "width_mm": 1300, "height_mm": 1400, "quantity": 1},
    ).json()

    assert after["base_price"] == 99999
    assert after["total_price"] > before["total_price"]


def test_price_rule_update_is_audited(admin_client):
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        rule = db.query(database.PriceRule).filter_by(category="profile", label="Эконом (58 мм)").first()
        rule_id = rule.id
    finally:
        db.close()

    admin_client.post(f"/admin/price-rules/{rule_id}", data={"value": "1.5", "is_active": "on"})

    response = admin_client.get("/admin/audit")
    assert "price_rule.update" in response.text


def test_category_edit_updates_public_page(admin_client):
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        category = db.query(database.Category).filter_by(slug="plastikovye-dveri").first()
        category_id = category.id
    finally:
        db.close()

    response = admin_client.post(
        f"/admin/catalog/categories/{category_id}",
        data={
            "name": "Двери ПВХ (обновлено)",
            "short_description": "Новое короткое описание",
            "description_html": "<p>Новый текст</p>",
            "meta_title": "",
            "meta_description": "",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    public_page = admin_client.get("/plastikovye-dveri/")
    assert "Двери ПВХ (обновлено)" in public_page.text


def test_product_edit_updates_calculator_mapping(admin_client):
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        product = db.query(database.Product).filter_by(slug="dver-vhodnaya-pvh").first()
        product_id = product.id
        assert product.calculator_window_type is None
    finally:
        db.close()

    response = admin_client.post(
        f"/admin/catalog/products/{product_id}",
        data={
            "name": product.name if False else "Входная дверь ПВХ",
            "short_description": "",
            "description_html": "",
            "calculator_window_type": "Окно",
            "calculator_profile_type": "Стандарт (70 мм)",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    public_page = admin_client.get("/plastikovye-dveri/")
    assert "Цена от" in public_page.text


def test_product_option_add_and_delete(admin_client):
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        product = db.query(database.Product).filter_by(slug="dver-vhodnaya-pvh").first()
        product_id = product.id
    finally:
        db.close()

    admin_client.post(
        f"/admin/catalog/products/{product_id}/options/add",
        data={"group_label": "Цвет", "value_label": "Белый"},
    )
    page = admin_client.get(f"/admin/catalog/products/{product_id}")
    assert "Цвет: Белый" in page.text

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        option = db.query(database.ProductOption).filter_by(product_id=product_id, group_label="Цвет").first()
        option_id = option.id
    finally:
        db.close()

    admin_client.post(f"/admin/catalog/products/{product_id}/options/{option_id}/delete")
    page = admin_client.get(f"/admin/catalog/products/{product_id}")
    assert "Цвет: Белый" not in page.text


def test_lead_status_change_and_audit(admin_client):
    lead_response = admin_client.post(
        "/api/lead", json={"phone": "+79001234567", "consent": True},
    )
    lead_id = lead_response.json()["lead_id"]

    response = admin_client.post(f"/admin/leads/{lead_id}/status", data={"manager_status": "contacted"}, follow_redirects=False)
    assert response.status_code == 303

    detail = admin_client.get(f"/admin/leads/{lead_id}")
    assert 'value="contacted" selected' in detail.text

    audit = admin_client.get("/admin/audit")
    assert "lead.status_change" in audit.text


def test_lead_retry_telegram_increments_attempts(admin_client):
    lead_response = admin_client.post("/api/lead", json={"phone": "+79001234567", "consent": True})
    lead_id = lead_response.json()["lead_id"]

    detail_before = admin_client.get(f"/admin/leads/{lead_id}")
    assert "Попыток: 1" in detail_before.text

    admin_client.post(f"/admin/leads/{lead_id}/retry-telegram")

    detail_after = admin_client.get(f"/admin/leads/{lead_id}")
    assert "Попыток: 2" in detail_after.text


def test_admin_user_create_and_deactivate(admin_client):
    response = admin_client.post(
        "/admin/users/create",
        data={"username": "new-manager", "password": "somepassword1", "role": "manager"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    users_page = admin_client.get("/admin/users")
    assert "new-manager" in users_page.text

    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        user = db.query(database.AdminUser).filter_by(username="new-manager").first()
        user_id = user.id
    finally:
        db.close()

    admin_client.post(f"/admin/users/{user_id}/deactivate")
    users_page = admin_client.get("/admin/users")
    assert "new-manager" in users_page.text


def test_admin_cannot_deactivate_self(admin_client, admin_user):
    response = admin_client.post(f"/admin/users/{admin_user.id}/deactivate", follow_redirects=False)
    assert response.status_code == 303
    dashboard = admin_client.get("/admin/")
    assert dashboard.status_code == 200


def test_deactivated_admin_loses_access(admin_client):
    """Деактивированный пользователь не должен попадать в систему даже
    с валидной старой сессией/логином."""
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        user = db.query(database.AdminUser).filter_by(username="test-admin").first()
        user.is_active = False
        db.commit()
    finally:
        db.close()

    response = admin_client.get("/admin/", follow_redirects=False)
    assert response.status_code == 303


def test_csrf_rejected_with_wrong_token(admin_client):
    """admin_client-wrapper подставляет csrf_token, только если его нет в data —
    передаём заведомо неверный явно, чтобы проверить, что защита реально работает."""
    response = admin_client.post(
        "/admin/leads/1/retry-telegram",
        data={"csrf_token": "definitely-not-the-real-token"},
    )
    assert response.status_code == 403


def test_csrf_rejected_with_missing_token(client, admin_user):
    """Сырой POST без обёртки-фикстуры и вообще без csrf_token в форме —
    ровно то, что попытался бы сделать сторонний сайт при CSRF-атаке.
    Поле csrf_token обязательно (Form(...)), поэтому при его полном
    отсутствии FastAPI отклоняет запрос на этапе валидации (422), до того
    как выполнится verify_csrf() — тоже отказ в обработке, просто раньше."""
    client.post("/admin/login", data={"username": "test-admin", "password": "test-password-123"})
    response = client.post("/admin/users/create", data={"username": "hacker", "password": "x", "role": "admin"})
    assert response.status_code == 422

    import database
    import main
    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        assert db.query(database.AdminUser).filter_by(username="hacker").first() is None
    finally:
        db.close()


def test_login_already_authenticated_redirects_to_dashboard(admin_client):
    response = admin_client.get("/admin/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/"


def test_lead_detail_not_found_shows_inline_error(admin_client):
    response = admin_client.get("/admin/leads/999999")
    assert response.status_code == 200
    assert "Заявка не найдена" in response.text


def test_leads_list_filters_by_source(admin_client):
    response = admin_client.get("/admin/leads", params={"source": "calculator"})
    assert response.status_code == 200


def test_lead_detail_survives_malformed_calculator_config_json(admin_client):
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        lead = database.Lead(source="calculator", phone="+79000000000", consent_given=True, calculator_config_json="{not valid json")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
    finally:
        db.close()

    response = admin_client.get(f"/admin/leads/{lead_id}")
    assert response.status_code == 200


def test_category_edit_not_found_redirects(admin_client):
    response = admin_client.get("/admin/catalog/categories/999999", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/catalog/categories"


def test_products_list_filters_by_category(admin_client):
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        category = db.query(database.Category).filter_by(slug="plastikovye-dveri").first()
        category_id = category.id
    finally:
        db.close()

    response = admin_client.get("/admin/catalog/products", params={"category_id": category_id})
    assert response.status_code == 200
    assert "Входная дверь ПВХ" in response.text


def test_product_edit_not_found_redirects(admin_client):
    response = admin_client.get("/admin/catalog/products/999999", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/catalog/products"


def test_product_image_add_and_delete(admin_client):
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        product = db.query(database.Product).filter_by(slug="dver-vhodnaya-pvh").first()
        product_id = product.id
    finally:
        db.close()

    admin_client.post(
        f"/admin/catalog/products/{product_id}/images/add",
        data={"image_path": "/static/images/catalog/test-door.webp", "alt_text": "Тестовая дверь"},
    )
    page = admin_client.get(f"/admin/catalog/products/{product_id}")
    assert "test-door.webp" in page.text

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        image = db.query(database.ProductImage).filter_by(product_id=product_id, image_path="/static/images/catalog/test-door.webp").first()
        image_id = image.id
    finally:
        db.close()

    admin_client.post(f"/admin/catalog/products/{product_id}/images/{image_id}/delete")
    page = admin_client.get(f"/admin/catalog/products/{product_id}")
    assert "test-door.webp" not in page.text


def test_admin_user_create_duplicate_username_shows_error(admin_client):
    admin_client.post("/admin/users/create", data={"username": "dup-user", "password": "somepass123", "role": "manager"})
    response = admin_client.post("/admin/users/create", data={"username": "dup-user", "password": "somepass123", "role": "manager"})
    assert response.status_code == 200
    assert "уже существует" in response.text

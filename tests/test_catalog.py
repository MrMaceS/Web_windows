"""tests/test_catalog.py — тесты каталога (Sprint 3)."""


def test_hub_category_lists_children(client):
    response = client.get("/okna/")
    assert response.status_code == 200
    html = response.text
    assert "Одностворчатые окна" in html
    assert "Двухстворчатые окна" in html
    assert "Трёхстворчатые окна" in html


def test_leaf_category_shows_product_variants_and_price(client):
    response = client.get("/okna/odnostvorchatye/")
    assert response.status_code == 200
    html = response.text
    assert "Одностворчатое окно, профиль Эконом" in html
    assert "Одностворчатое окно, профиль Стандарт" in html
    assert "Цена от" in html


def test_leaf_category_without_calculator_pricing_shows_honest_fallback(client):
    """Двери вне модели цен Sprint 2 — не должно быть выдуманной цифры."""
    response = client.get("/plastikovye-dveri/")
    assert response.status_code == 200
    html = response.text
    assert "Входная дверь ПВХ" in html
    assert "цена по индивидуальному расчёту" in html.lower()


def test_unknown_top_level_category_returns_404(client):
    response = client.get("/nesuschestvuyuschaya-kategoriya/")
    assert response.status_code == 404


def test_unknown_child_category_returns_404(client):
    response = client.get("/okna/nesuschestvuyuschaya-podkategoriya/")
    assert response.status_code == 404


def test_child_slug_under_wrong_parent_returns_404(client):
    """odnostvorchatye — ребёнок okna, а не balkonnye-bloki — по чужому
    родителю резолвиться не должен (иначе получится дублирующий URL
    на тот же контент)."""
    response = client.get("/balkonnye-bloki/odnostvorchatye/")
    assert response.status_code == 404


def test_breadcrumbs_present_on_leaf_page(client):
    response = client.get("/okna/odnostvorchatye/")
    html = response.text
    assert "Главная" in html
    assert "BreadcrumbList" in html


def test_each_catalog_page_has_distinct_title_and_h1(client):
    """Грубая защита от дублирующегося SEO-контента: разные страницы должны
    иметь разные <title> и разные H1."""
    paths = [
        "/okna/", "/okna/odnostvorchatye/", "/okna/dvuhstvorchatye/",
        "/okna/trehstvorchatye/", "/balkonnye-bloki/", "/osteklenie-balkonov/",
        "/plastikovye-dveri/", "/gotovye-okna/",
    ]
    titles = []
    h1s = []
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        html = response.text
        title_start = html.index("<title>") + len("<title>")
        title_end = html.index("</title>")
        titles.append(html[title_start:title_end])

        h1_start = html.index("<h1")
        h1_content_start = html.index(">", h1_start) + 1
        h1_end = html.index("</h1>", h1_content_start)
        h1s.append(html[h1_content_start:h1_end].strip())

    assert len(titles) == len(set(titles)), f"Найдены одинаковые <title>: {titles}"
    assert len(h1s) == len(set(h1s)), f"Найдены одинаковые H1: {h1s}"


def test_sitemap_contains_all_catalog_urls(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    body = response.text
    assert "<loc>" in body
    assert "/okna/</loc>" in body
    assert "/okna/odnostvorchatye/</loc>" in body
    assert "/plastikovye-dveri/</loc>" in body


def test_robots_txt_references_sitemap(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Sitemap:" in response.text
    assert "sitemap.xml" in response.text


def test_calculator_link_prefill_uses_product_labels(client):
    """Карточка товара с ценой должна вести на калькулятор с теми же
    label'ами, что заведены в price_rules (Sprint 2), а не выдуманными."""
    response = client.get("/okna/odnostvorchatye/")
    html = response.text
    assert "window_type=" in html
    assert "profile_type=" in html


def test_measurer_modal_available_on_catalog_page(client):
    """Sprint 3 фиксит баг: модалка 'Вызвать замерщика' должна быть на
    любой странице, не только на главной."""
    response = client.get("/gotovye-okna/")
    assert 'id="measurer-modal"' in response.text

from apps.api.main import app, WEB_STATIC_DIR


def test_product_detail_deep_link_route_precedes_static_mount():
    route_paths = [getattr(route, "path", None) for route in app.router.routes]

    assert route_paths.index("/ui/demo") < route_paths.index("/ui")
    assert route_paths.index("/ui/ops") < route_paths.index("/ui")
    assert route_paths.index("/ui/product/{product_id}") < route_paths.index("/ui")


def test_ui_shell_uses_absolute_static_asset_paths():
    html = (WEB_STATIC_DIR / "index.html").read_text()

    assert 'href="/ui/styles.css"' in html
    assert 'src="/ui/app.js"' in html


def test_ui_shell_includes_crawl_status_panel():
    html = (WEB_STATIC_DIR / "index.html").read_text()

    assert 'id="crawl-status"' in html
    assert 'id="run-materiel-crawl"' in html
    assert 'id="run-ldlc-crawl"' in html
    assert 'data-crawl-merchant="materiel"' in html
    assert 'data-crawl-merchant="ldlc"' in html
    assert 'href="/ui/ops"' in html


def test_ui_crawl_trigger_uses_admin_token_header():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "electronicstar.opsAdminToken" in js
    assert '"X-Admin-Token"' in js
    assert "async function triggerCrawlRun" in js
    assert "/ops/crawl-runs/" in js


def test_ui_ops_route_has_dashboard_renderer():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "function isOpsRoute()" in js
    assert "async function loadOpsRoute()" in js
    assert "function renderOpsDashboard" in js
    assert "ops-change-token-button" in js
    assert "function changeOpsAdminToken()" in js
    assert "CRAWL_MERCHANTS" in js


def test_ui_product_detail_includes_csv_exports():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "/offers.csv" in js
    assert "/price-history.csv" in js


def test_ui_ops_route_links_raw_documents_endpoint():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "/documents?limit=8" in js
    assert "Documents bruts" in js


def test_ui_ops_route_lists_offer_audit():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "/ops/offers/audit?limit=8" in js
    assert "/ops/offers/audit.csv?limit=500" in js
    assert "Audit prix" in js
    assert "function renderOpsOfferAudit" in js
    assert "function exportOpsOfferAuditCsv" in js
    assert "function priceWarningLabel" in js
    assert "price-warning-badge" in js
    assert "ops-export-audit-csv-button" in js


def test_ui_ops_route_lists_stale_offers():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "/ops/offers/stale?limit=8" in js
    assert "Offres a rafraichir" in js
    assert "function renderOpsStaleOffers" in js


def test_ui_offer_cards_link_source_documents():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "data-offer-source-id" in js
    assert "/source-document" in js
    assert "Source crawl" in js
    assert "Crawl ancien" in js


def test_ui_styles_include_responsive_ops_polish():
    css = (WEB_STATIC_DIR / "styles.css").read_text()

    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 760px)" in css
    assert ".ops-detail-row" in css
    assert ".detail-actions" in css
    assert ".price-warning-badge" in css

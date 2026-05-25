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
    assert 'href="/ui/ops"' in html


def test_ui_crawl_trigger_uses_admin_token_header():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "electronicstar.opsAdminToken" in js
    assert '"X-Admin-Token"' in js


def test_ui_ops_route_has_dashboard_renderer():
    js = (WEB_STATIC_DIR / "app.js").read_text()

    assert "function isOpsRoute()" in js
    assert "async function loadOpsRoute()" in js
    assert "function renderOpsDashboard" in js

# tests/test_smoke.py
# Smoke tests: confirm the app boots, every public landing page renders, and
# the security headers we rely on are present. These aren't feature tests —
# they catch the "I broke the app factory" / "I broke a blueprint" class of
# regressions. Real per-feature tests land in Phase 3 of MCP_SUBMISSION_PLAN.
import pytest


def test_app_factory_boots(app):
    assert app is not None
    assert app.name == "app"


@pytest.mark.parametrize(
    "path",
    ["/", "/summarizer", "/translator", "/redactor", "/vision", "/about", "/pricing"],
)
def test_landing_pages_return_200(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}"
    # Every page renders the layout — sanity-check that we got HTML, not an
    # error page that happens to be 200.
    assert b"<html" in resp.data.lower() or b"<!doctype" in resp.data.lower()


# Submission-required public pages. Each asserts the hero heading is present —
# this catches "partial got renamed but route still points at the old one" silently
# returning the layout shell with no body content.
@pytest.mark.parametrize(
    "path,hero",
    [
        ("/docs", b"Synzo MCP Server"),
        ("/privacy", b"Privacy Policy"),
        ("/support", b"Synzo Support"),
        ("/security", b"Security Disclosure"),
    ],
)
def test_submission_pages_render_with_hero(client, path, hero):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}"
    assert hero in resp.data, f"{path} did not contain hero heading {hero!r}"


def test_global_footer_links_present_on_homepage(client):
    """Every public page renders the global footer with the four submission-form
    links. If a deploy ever drops the footer (e.g. a layout.html refactor), the
    form-listed URLs become unreachable for navigation and reviewers notice."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data
    assert b'href="/docs"' in body
    assert b'href="/privacy"' in body
    assert b'href="/support"' in body
    assert b'href="/security"' in body


def test_sitemap_and_robots(client):
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert b"<urlset" in sitemap.data

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert b"User-agent" in robots.data


def test_security_headers_present(client):
    """Talisman should be applying CSP, frame-options, and content-type sniffing
    protection on every response. HSTS is intentionally omitted: Talisman only
    sets it on HTTPS responses, and the test client speaks plain HTTP."""
    resp = client.get("/")
    headers = {k.lower(): v for k, v in resp.headers.items()}
    assert "content-security-policy" in headers
    assert headers.get("x-frame-options", "").upper() in {"DENY", "SAMEORIGIN"}
    assert "x-content-type-options" in headers


def test_unknown_feature_falls_back_to_welcome(client):
    """/feature/<bad-key> should not 500 — main_routes falls back to welcome."""
    resp = client.get("/feature/does-not-exist")
    assert resp.status_code == 200


def test_db_extension_registered_and_tables_known(app):
    """db.init_app() ran and the four billing tables exist in metadata."""
    from db import db

    assert "sqlalchemy" in app.extensions
    expected = {"orgs", "api_keys", "quotas", "usage_events", "users", "org_memberships"}
    assert expected.issubset(set(db.metadata.tables.keys()))


def test_405_on_post_to_get_only_route(client):
    """Sitemap is GET-only; POSTing should be rejected, not crash."""
    resp = client.post("/sitemap.xml")
    assert resp.status_code in (405, 404)

"""Browser regressions for Mission Control (run against a live stack: make e2e)."""
import os
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

BASE = os.getenv("SUITE_URL", "http://api:8000")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def open_page(browser, **ctx):
    context = browser.new_context(**ctx)
    page = context.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: (errors.append(f"dialog: {d.message}"), d.dismiss()))
    response = page.goto(BASE + "/")
    page.wait_for_selector("#status-text:not(:text('Connecting…'))", timeout=10000)
    return page, response, errors


def test_loads_clean_with_strict_csp(browser):
    page, response, errors = open_page(browser)
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert page.title() == "Mission Control · Checkmate"
    page.wait_for_timeout(2500)
    assert errors == []


def test_request_path_cannot_inject_html(browser):
    page, _, errors = open_page(browser)
    try:
        urllib.request.urlopen(BASE + "/%3Cimg%20src=x%20onerror=alert(1)%3E")
    except Exception:
        pass  # 404 is expected
    # Locators, not wait_for_function: the page's CSP (rightly) blocks string eval.
    page.locator("#logs .log-msg", has_text="<img src=x").first.wait_for(timeout=10000)
    assert page.locator("#logs img").count() == 0
    assert not any("dialog" in e for e in errors)


def test_wrong_chaos_token_relocks(browser):
    page, _, _ = open_page(browser)
    page.fill("#chaos-token", "definitely-not-the-token")
    page.press("#chaos-token", "Enter")
    page.click(".chaos[data-value='500']")
    page.locator("#chaos-msg", has_text="Token rejected").wait_for()
    assert page.locator(".chaos").first.is_disabled()


def test_ai_engine_disabled_without_key(browser):
    page, _, _ = open_page(browser)
    page.wait_for_timeout(500)
    if os.getenv("EXPECT_AI") != "1":
        assert page.locator("#engine-ai").is_disabled()


@pytest.mark.parametrize("width", [390, 768])
def test_no_horizontal_scroll_on_small_screens(browser, width):
    page, _, _ = open_page(browser, viewport={"width": width, "height": 844})
    page.wait_for_timeout(2500)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0, f"page scrolls sideways by {overflow}px at {width}px"
    os.makedirs("tests/e2e/screenshots", exist_ok=True)
    page.screenshot(path=f"tests/e2e/screenshots/mission-control-{width}.png", full_page=True)

"""Playwright smoke test for the Settings and ASR management pages.

Requires a running local Docker deployment. The script never reads or prints
credential values; it only verifies the password field's visibility state.
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


BASE_URL = os.environ.get("VID2NOTE_E2E_BASE_URL", "http://127.0.0.1:8761").rstrip("/")
SCREENSHOT_DIR = Path(
    os.environ.get("VID2NOTE_E2E_SCREENSHOT_DIR", "/tmp/vid2note-ui-verification")
)


def _open(page: Page, path: str, ready_selector: str) -> None:
    page.goto(f"{BASE_URL}{path}", wait_until="networkidle")
    page.wait_for_selector(ready_selector, timeout=20_000)


def _assert_no_page_overflow(page: Page) -> None:
    has_overflow = page.evaluate(
        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert not has_overflow, "页面产生了横向溢出"


def run() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
            _open(desktop, "/settings", "#settings-tab-general")
            assert desktop.locator('[role="tab"]').count() == 6

            general_tab = desktop.locator("#settings-tab-general")
            general_tab.focus()
            general_tab.press("ArrowRight")
            assert (
                desktop.locator("#settings-tab-llm").get_attribute("aria-selected")
                == "true"
            )

            assert desktop.locator(".provider-item").count() == 9
            assert desktop.locator(".provider-item", has_text="自定义").count() == 1

            password_input = desktop.locator(".provider-editor .password-input")
            password_eye = desktop.locator(".provider-editor .password-eye")
            if password_eye.is_enabled():
                assert password_input.get_attribute("type") == "password"
                password_eye.click()
                desktop.wait_for_function(
                    "() => document.querySelector('.provider-editor .password-input')?.type === 'text'"
                )
                assert password_input.get_attribute("type") == "text"
                password_eye.click()
                assert password_input.get_attribute("type") == "password"

            desktop.locator(".provider-item", has_text="自定义").click()
            desktop.wait_for_timeout(100)
            desktop.screenshot(
                path=str(SCREENSHOT_DIR / "settings-llm-custom-desktop.png"),
                full_page=True,
            )

            desktop.locator("#settings-tab-note").click()
            desktop.locator("#settings-tab-note[aria-selected='true']").wait_for()
            assert desktop.locator(".detail-option").count() == 4
            assert desktop.locator(".detail-option.active").count() == 1
            desktop.wait_for_timeout(100)
            desktop.screenshot(
                path=str(SCREENSHOT_DIR / "settings-note-desktop.png"),
                full_page=True,
            )
            _assert_no_page_overflow(desktop)

            _open(desktop, "/asr", "#asr-tab-engines")
            assert desktop.locator('[role="tab"]').count() == 4
            assert desktop.locator(".engine-option").count() == 3
            desktop.screenshot(
                path=str(SCREENSHOT_DIR / "asr-engines-desktop.png"),
                full_page=True,
            )
            desktop.locator("#asr-tab-whisper").click()
            assert desktop.locator("#asr-panel-whisper").is_visible()
            desktop.locator("#asr-tab-external").click()
            assert desktop.locator("#asr-panel-external").is_visible()
            desktop.locator("#asr-tab-strategy").click()
            assert desktop.locator("#asr-panel-strategy").is_visible()
            _assert_no_page_overflow(desktop)

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            _open(mobile, "/settings", "#settings-tab-general")
            _assert_no_page_overflow(mobile)
            mobile.locator("#settings-tab-llm").click()
            assert mobile.locator(".provider-item").count() == 9
            _assert_no_page_overflow(mobile)
            mobile.locator("#settings-tab-note").click()
            mobile.locator("#settings-tab-note[aria-selected='true']").wait_for()
            assert mobile.locator(".detail-option").count() == 4
            mobile.wait_for_timeout(100)
            mobile.screenshot(
                path=str(SCREENSHOT_DIR / "settings-note-mobile.png"),
                full_page=True,
            )
            _assert_no_page_overflow(mobile)
        finally:
            browser.close()

    print(
        "Settings/ASR UI verification passed: "
        "6 settings tabs, 9 providers, password eye, 4 detail levels, "
        "4 ASR tabs, desktop/mobile overflow checks."
    )


if __name__ == "__main__":
    run()

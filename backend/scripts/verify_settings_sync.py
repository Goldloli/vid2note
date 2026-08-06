"""回归验证：设置保存后应立即同步到外观与新建任务表单。

需要本地 Docker 服务运行在 ``VID2NOTE_E2E_BASE_URL``（默认
``http://127.0.0.1:8761``）。脚本会临时切换若干非敏感设置，并在退出前
恢复原值；不会读取、打印或修改任何密钥。
"""
from __future__ import annotations

import os

from playwright.sync_api import Page, sync_playwright


BASE_URL = os.environ.get("VID2NOTE_E2E_BASE_URL", "http://127.0.0.1:8761").rstrip("/")
SETTING_KEYS = (
    "ui.background",
    "note.extract_images",
    "note.detail_level",
    "note.output_language",
    "llm.provider",
    "llm.model",
    "asr.engine",
)
BACKGROUND_VALUES = ("mesh", "static", "plain")
DETAIL_VALUES = ("concise", "balanced", "detailed", "exhaustive")
LANGUAGE_VALUES = ("zh", "en")
ASR_VALUES = ("bcut", "whisper_cpp", "external")


def _open(page: Page, path: str, ready_selector: str) -> None:
    page.goto(f"{BASE_URL}{path}", wait_until="networkidle")
    page.wait_for_selector(ready_selector, timeout=20_000)


def _alternate(current: str, values: tuple[str, ...]) -> str:
    return next(value for value in values if value != current)


def _record(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _configured_provider_ids(document: dict) -> list[str]:
    profiles = document.get("profiles", {})
    credentials = document.get("credentials", {})
    configured: list[str] = []
    for provider in document.get("providers", []):
        provider_id = provider.get("id", "")
        profile = profiles.get(provider_id, {})
        if not str(profile.get("model", "")).strip() or not str(
            profile.get("base_url", "")
        ).strip():
            continue
        required_fields = [
            field.get("id")
            for field in provider.get("credential_fields", [])
            if field.get("required")
        ]
        if all(
            credentials.get(provider_id, {}).get(field_id, {}).get("configured")
            for field_id in required_fields
        ):
            configured.append(provider_id)
    return configured


def run() -> None:
    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        original_response = page.request.get(f"{BASE_URL}/api/v1/settings")
        assert original_response.ok, "无法读取原始设置"
        original_document = original_response.json()
        original = original_document["settings"]
        restore_payload = {
            key: original[key] for key in SETTING_KEYS if key in original
        }

        target_background = _alternate(
            str(original.get("ui.background", "plain")), BACKGROUND_VALUES
        )
        target_extract_images = (
            str(original.get("note.extract_images", "false")).lower() != "true"
        )
        target_detail = _alternate(
            str(original.get("note.detail_level", "balanced")), DETAIL_VALUES
        )
        target_language = _alternate(
            str(original.get("note.output_language", "zh")), LANGUAGE_VALUES
        )
        target_asr = _alternate(
            str(original.get("asr.engine", "bcut")), ASR_VALUES
        )

        try:
            _open(page, "/settings", "#settings-tab-general")

            # 三种背景都必须真正作用到内容区；mesh 还应有动画。
            background_buttons = (
                page.locator("#settings-panel-general .settings-section")
                .first.locator(".setting-field")
                .nth(2)
                .locator(".chip")
            )
            assert background_buttons.count() == 3
            background_styles: dict[str, dict[str, str | None]] = {}
            for index, value in enumerate(BACKGROUND_VALUES):
                background_buttons.nth(index).click()
                background_styles[value] = page.evaluate(
                    """() => {
                      const content = document.querySelector('.content')
                      const style = getComputedStyle(content)
                      return {
                        value: document.documentElement.dataset.background,
                        image: style.backgroundImage,
                        animation: style.animationName,
                      }
                    }"""
                )
            _record(
                failures,
                background_styles["plain"]["value"] == "plain"
                and background_styles["plain"]["image"] == "none",
                "纯色背景未应用到内容区",
            )
            _record(
                failures,
                background_styles["static"]["value"] == "static"
                and background_styles["static"]["image"] != "none",
                "静态背景未应用到内容区",
            )
            _record(
                failures,
                background_styles["mesh"]["value"] == "mesh"
                and background_styles["mesh"]["animation"] != "none",
                "动态 mesh 背景未应用动画",
            )
            background_buttons.nth(BACKGROUND_VALUES.index(target_background)).click()

            page.locator("#settings-tab-note").click()
            note_panel = page.locator("#settings-panel-note")
            screenshot_switch = note_panel.get_by_role("switch")
            if screenshot_switch.get_attribute("aria-checked") != str(
                target_extract_images
            ).lower():
                screenshot_switch.click()
            note_panel.locator(".detail-option").nth(
                DETAIL_VALUES.index(target_detail)
            ).click()
            note_panel.locator(".setting-field").first.locator(".chip").nth(
                LANGUAGE_VALUES.index(target_language)
            ).click()

            page.locator("#settings-tab-llm").click()
            provider_ids = [
                item["id"] for item in original_document.get("providers", [])
            ]
            current_provider = str(original.get("llm.provider", "deepseek"))
            target_provider = next(
                provider_id
                for provider_id in _configured_provider_ids(original_document)
                if provider_id != current_provider
            )
            target_model = original_document["profiles"][target_provider]["model"]
            page.locator(".provider-item").nth(provider_ids.index(target_provider)).click()
            page.locator(".provider-heading-actions .btn").first.click()

            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/settings")
                and response.request.method == "PUT"
            ) as save_response:
                page.locator(".page-header-actions .btn-primary").click()
            assert save_response.value.ok, "设置保存失败"

            # 必须使用 SPA 导航，才能覆盖“后端已保存、Pinia 仍是旧快照”的回归。
            page.locator('.nav-item[href="/"]').click()
            page.wait_for_selector(".console", timeout=20_000)
            page.locator(".advanced-toggle").click()
            _record(
                failures,
                page.get_by_test_id("task-extract-images").get_attribute(
                    "aria-pressed"
                )
                == str(target_extract_images).lower(),
                "截图设置保存后未同步到主页",
            )
            _record(
                failures,
                page.get_by_test_id("task-detail-level").input_value() == target_detail,
                "笔记详细程度保存后未同步到主页",
            )
            _record(
                failures,
                page.get_by_test_id("task-llm-provider").input_value()
                == target_provider,
                "默认 LLM 保存后未同步到主页",
            )
            _record(
                failures,
                page.locator('[data-testid="sidebar-llm"]').get_attribute("data-model")
                == target_model,
                "默认 LLM 保存后未同步到侧栏摘要",
            )
            _record(
                failures,
                "active"
                in page.locator(
                    f'[data-testid="task-output-language"]'
                    f'[data-language="{target_language}"]'
                )
                .get_attribute("class")
                .split(),
                "输出语言保存后未同步到主页",
            )

            # ASR 页面原先也维护独立快照；保存后主页应立刻看到新默认值。
            page.locator('.nav-item[href="/asr"]').click()
            page.wait_for_selector("#asr-panel-engines", timeout=20_000)
            target_engine = page.locator(".engine-option").nth(
                ASR_VALUES.index(target_asr)
            )
            target_engine.locator(".engine-option-actions .btn").nth(1).click()
            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/settings")
                and response.request.method == "PUT"
            ) as asr_save_response:
                page.locator(".page-header-actions .btn-primary").click()
            assert asr_save_response.value.ok, "ASR 设置保存失败"
            page.locator('.nav-item[href="/"]').click()
            page.wait_for_selector(".console", timeout=20_000)
            _record(
                failures,
                "active"
                in page.locator(
                    f'[data-testid="task-asr-engine"][data-engine="{target_asr}"]'
                )
                .get_attribute("class")
                .split(),
                "ASR 默认引擎保存后未同步到主页",
            )
            _record(
                failures,
                page.locator('[data-testid="sidebar-asr"]').get_attribute("data-engine")
                == target_asr,
                "ASR 默认引擎保存后未同步到侧栏摘要",
            )
        finally:
            restore_ok = page.request.put(
                f"{BASE_URL}/api/v1/settings", data=restore_payload
            ).ok
            browser.close()
            assert restore_ok, "测试结束后恢复原始设置失败"

    assert not failures, "\n".join(failures)
    print("设置同步回归验证通过：外观、笔记、LLM、ASR 均与主页保持一致。")


if __name__ == "__main__":
    run()

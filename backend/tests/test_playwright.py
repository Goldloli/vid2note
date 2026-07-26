"""vid2note 端到端测试(playwright):主控台粘 B站链接 → 流水线 → 验证笔记产物。

用法(容器已 up):
  cd backend && .venv/bin/python tests/test_playwright.py
"""
import sys
import time

import requests
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8761"
TEST_URL = "https://www.bilibili.com/video/BV1fj6vBfEnu"
TIMEOUT_S = 600  # 单任务最多等 10 分钟


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        # 1. 打开主控台
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("input[placeholder*='视频链接']", timeout=20000)
        print("[1] 主控台加载 OK")
        # 2. 粘链接 + 提交
        page.fill("input[placeholder*='视频链接']", TEST_URL)
        page.click("button[type='submit']")
        # 3. 跳转任务详情
        page.wait_for_url("**/task/**", timeout=20000)
        tid = page.url.rstrip("/").split("/")[-1]
        print(f"[2] 任务已创建,跳转详情,id={tid}")
        # 4. 轮询任务状态 until 终态
        status, task = None, {}
        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline:
            task = requests.get(f"{BASE}/api/v1/tasks/{tid}", timeout=20).json()
            status = task.get("status")
            nodes = task.get("node_statuses") or {}
            cur = [k for k, v in nodes.items() if isinstance(v, dict) and v.get("status") == "running"]
            print(f"  status={status} progress={task.get('progress')} running={cur} err={task.get('error') or ''}")
            if status in ("completed", "failed", "cancelled"):
                break
            time.sleep(5)
        assert status == "completed", f"任务未完成: status={status}, error={task.get('error')}"
        # 5. 验证产物
        assert task.get("note_path"), "无 note_path 产物"
        assert task.get("srt_path"), "无 srt_path 产物"
        print(f"[3] 流水线完成: note={task['note_path']} srt={task['srt_path']}")
        # 6. 笔记内容非空
        note_text = requests.get(f"{BASE}/api/v1/tasks/{tid}/products/note", timeout=20).text
        assert len(note_text) > 80, f"笔记内容过短({len(note_text)} 字符)"
        print(f"[4] 笔记内容长度 {len(note_text)} 字符,前 60 字:{note_text[:60]!r}")
        # 7. 笔记页能渲染
        page.goto(f"{BASE}/note/{tid}", wait_until="domcontentloaded")
        page.wait_for_selector(".note-md", timeout=20000)
        rendered = page.text_content(".note-md") or ""
        assert len(rendered) > 50, "笔记页渲染内容过短"
        print(f"[5] 笔记页渲染 OK,长度 {len(rendered)}")
        browser.close()
    print("\n✅ 端到端测试全部通过(B站链接 → 笔记产物 + 页面渲染)")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {type(e).__name__}: {e}")
        sys.exit(2)

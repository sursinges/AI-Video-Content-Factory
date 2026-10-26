"""Vheer.com browser adapter (owner decision 2026-09-12): the site has no API
but offers free generation; clean-room Playwright automation ("if there is no
API — build one", per the project guide). Headless Chromium, ezoic cookie
banner removed, aspect ratio chosen from payload width/height, result image
downloaded via the page's own request context. cfg["proxy"] is honored."""

import math
import time
from pathlib import Path

from core.providers.router import Provider, ProviderError

_GENERATE_TIMEOUT = 240  # sec, free queue can be slow
_cooldown_until = 0.0  # circuit breaker: after a failure skip vheer for 15 min
_COOLDOWN = 900


def _ratio_label(w: int, h: int) -> str | None:
    known = ["21:9", "16:9", "4:5", "5:4", "4:3", "3:4", "3:2", "2:3", "2:1", "1:2", "9:16", "9:21", "1:1"]
    g = math.gcd(w, h)
    label = f"{w // g}:{h // g}"
    return label if label in known else None


def _set_cooldown():
    global _cooldown_until
    _cooldown_until = time.time() + _COOLDOWN


class VheerBrowserProvider(Provider):
    adapter = "vheer_browser"

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("vheer_browser: payload must contain out_path")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        prompt = payload.get("prompt") or ""
        if not prompt:
            raise ProviderError("vheer_browser: empty prompt")
        if time.time() < _cooldown_until:
            raise ProviderError("vheer_browser: cooldown after recent failure "
                                f"({int(_cooldown_until - time.time())}s left) — use fallback")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ProviderError("vheer_browser: playwright is not installed") from e

        url = self.cfg.get("url", "https://vheer.com/app/text-to-image")
        try:
            with sync_playwright() as pw:
                launch_kwargs = {"headless": bool(self.cfg.get("headless", True))}
                if self.cfg.get("proxy"):
                    launch_kwargs["proxy"] = {"server": self.cfg["proxy"]}
                browser = pw.chromium.launch(**launch_kwargs)
                ctx_kwargs = {"viewport": {"width": 1440, "height": 900}}
                if self.cfg.get("user_data_dir"):
                    ctx_kwargs["user_data_dir"] = self.cfg["user_data_dir"]
                context = browser.new_context(**ctx_kwargs)
                page = context.new_page()
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                # ezoic cookie/CMP banner intercepts clicks — remove it
                page.evaluate("""() => {
                    for (const id of ['ez-cmpv2-container', 'ez-cookie-dialog-wrapper'])
                        document.getElementById(id)?.remove();
                }""")
                page.locator("textarea").first.fill(prompt)
                # aspect ratio from requested size (e.g. 1920x1080 -> "16:9")
                w, h = payload.get("width"), payload.get("height")
                if w and h:
                    label = _ratio_label(int(w), int(h))
                    if label:
                        row = page.locator("div:has(> p:text-is('Aspect Ratio'))").first
                        row.locator("button").first.click()
                        page.wait_for_timeout(800)
                        page.get_by_text(label, exact=True).last.click()
                        page.wait_for_timeout(500)
                existing_srcs = {
                    im.get_attribute("src") for im in page.locator("img").all() if im.get_attribute("src")
                }
                page.locator("button:has(span:text-is('Generate'))").first.click()

                src, deadline = None, time.time() + _GENERATE_TIMEOUT
                while time.time() < deadline:
                    for im in page.locator("img").all():
                        s = im.get_attribute("src") or ""
                        box = im.bounding_box()
                        if (
                            s
                            and s not in existing_srcs
                            and "logo" not in s.lower()
                            and "icon" not in s.lower()
                            and "placeholder" not in s.lower()
                            and box
                            and box["width"] > 250
                        ):
                            src = s
                            break
                    if src:
                        break
                    page.wait_for_timeout(2000)
                if not src:
                    raise ProviderError("vheer_browser: no result image within "
                                        f"{_GENERATE_TIMEOUT}s (site may be rate-limiting)")
                data = page.request.get(src).body()
                if out.suffix.lower() not in (".jpg", ".jpeg") and src.lower().endswith(".jpg"):
                    out = out.with_suffix(".jpg")
                out.write_bytes(data)
                browser.close()
                return {"image_path": str(out)}
        except ProviderError:
            _set_cooldown()
            raise
        except Exception as e:  # noqa: BLE001
            _set_cooldown()
            raise ProviderError(f"vheer_browser: {e}") from e

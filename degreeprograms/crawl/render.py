"""Optional JavaScript rendering for the crawler.

Uses Playwright when installed and enabled; otherwise it is a safe no-op. This
lets us reach JS-rendered course-search pages and, where possible, wait out
anti-bot interstitials.

Note: Cloudflare-style challenges are an arms race. This module waits politely
for an interstitial to clear and, if it does not, returns the interstitial so the
crawler records the page as BLOCKED rather than looping forever.
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional

_BLOCK_MARKERS = re.compile(
    r"just a moment|enable javascript|checking your browser|cf-chl|attention required|"
    r"access denied|verify you are human|captcha",
    re.IGNORECASE,
)


def is_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except Exception:
        return False


def needs_render(status: Optional[int], text: Optional[str]) -> bool:
    """Whether a response looks like a JS interstitial / blocked page."""
    if status in (401, 403, 429, 503):
        return True
    body = text or ""
    if len(body) < 400:
        return True
    return bool(_BLOCK_MARKERS.search(body[:6000]))


class Renderer:
    """Playwright-backed renderer (lazy browser, one per process)."""

    def __init__(
        self,
        timeout_ms: int = 20000,
        challenge_wait_ms: int = 10000,
        channel: Optional[str] = None,
        headless: bool = True,
    ) -> None:
        if not is_available():
            raise RuntimeError("playwright is not installed")
        self.timeout_ms = timeout_ms
        self.challenge_wait_ms = challenge_wait_ms
        self.channel = channel
        self.headless = headless
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            launch_kwargs = {"headless": self.headless}
            if self.channel:
                launch_kwargs["channel"] = self.channel
            try:
                self._browser = self._playwright.chromium.launch(**launch_kwargs)
            except Exception:
                # Fall back to bundled Chromium if the requested channel is absent.
                self._browser = self._playwright.chromium.launch(headless=self.headless)
        return self._browser

    @staticmethod
    def _is_interstitial(html: str) -> bool:
        return bool(_BLOCK_MARKERS.search((html or "")[:6000]))

    def render(self, url: str) -> Optional[str]:
        try:
            browser = self._ensure_browser()
            page = browser.new_page()
            try:
                page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                deadline = time.time() + self.challenge_wait_ms / 1000.0
                html = page.content()
                while self._is_interstitial(html) and time.time() < deadline:
                    page.wait_for_timeout(500)
                    html = page.content()
                if self._is_interstitial(html):
                    return None  # still blocked; crawler records it as BLOCKED
                try:
                    page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass
                return page.content()
            finally:
                page.close()
        except Exception:
            return None

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._playwright = None


def make_renderer(enabled: bool, timeout_ms: int = 20000) -> Optional[Renderer]:
    if not enabled or not is_available():
        return None
    channel = os.environ.get("INTEL_RENDER_CHANNEL") or None
    challenge_wait = int(os.environ.get("INTEL_RENDER_CHALLENGE_WAIT_MS", "10000"))
    try:
        return Renderer(timeout_ms=timeout_ms, challenge_wait_ms=challenge_wait, channel=channel)
    except Exception:
        return None

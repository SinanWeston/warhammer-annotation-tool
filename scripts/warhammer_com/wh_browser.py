#!/usr/bin/env python3
"""
Shared Playwright browser wrapper for warhammer.com scraping.

Uses a **persistent** browser profile so cookies / AWS WAF tokens survive
across script runs: the first run may require a human to pass the
"Human Verification" (goku / AWS WAF) challenge; subsequent runs reuse
the same profile and stay authenticated.

Applies `playwright_stealth` evasions to reduce webdriver fingerprint
leaks that trigger the WAF in the first place.

Model reference: scripts/scrape_ebay.py::EbayBrowser.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

BASE = "https://www.warhammer.com"
DEFAULT_PROFILE_DIR = Path(__file__).resolve().parent / "recon" / ".browser_profile"

# Substring fingerprints of the AWS WAF "goku" challenge page.
# NOTE: "awswaf" was removed — normal GW pages embed <script src=…awswaf.com…>
# for token management, which produced false positives that hung the scraper
# on a 5-minute challenge-wait loop for every product page.
WAF_CHALLENGE_MARKERS = (
    "<title>Human Verification</title>",
    "window.gokuProps",
    "awsWafCookieDomainList",
)


def is_waf_challenge(html: str) -> bool:
    if not html:
        return False
    return any(m in html for m in WAF_CHALLENGE_MARKERS)


class WhBrowser:
    """Playwright Chromium session pinned to warhammer.com, stealth-patched, persistent."""

    def __init__(
        self,
        headless: bool = False,
        capture_requests: bool = False,
        profile_dir: Path | None = None,
        user_agent: str | None = None,
    ):
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth

        self._pw = sync_playwright().start()
        self._stealth = Stealth()
        self._stealth.hook_playwright_context(self._pw)

        profile_dir = profile_dir or DEFAULT_PROFILE_DIR
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile_dir = profile_dir

        ua = user_agent or random.choice(USER_AGENTS)
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        # launch_persistent_context opens one default page; reuse it.
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()

        self._captured_requests: list[dict] = []
        if capture_requests:
            self._page.on("request", self._on_request)
            self._page.on("response", self._on_response)

        print(f"  Browser ready (profile: {profile_dir})", flush=True)

    # ── context manager ──
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── navigation + challenge-handling ──
    def goto(
        self,
        url: str,
        wait_ms: int = 3000,
        wait_until: str = "networkidle",
        timeout: int = 45000,
        solve_challenge_interactive: bool = True,
    ) -> str:
        """Navigate, return rendered HTML. Pauses on WAF challenge if interactive."""
        try:
            self._page.goto(url, wait_until=wait_until, timeout=timeout)
            self._page.wait_for_timeout(wait_ms)
        except Exception as e:
            print(f"    goto {url[:80]}… failed: {e}", flush=True)
            return ""
        html = self._page.content()

        if is_waf_challenge(html) and solve_challenge_interactive:
            print("\n" + "=" * 60, flush=True)
            print("  ⚠ AWS WAF challenge detected.", flush=True)
            print("  A browser window is open — solve the challenge there.", flush=True)
            print("  Polling page content; will resume automatically.", flush=True)
            print("=" * 60, flush=True)
            deadline = time.time() + 300  # 5-minute wall-clock budget
            last_html_len = len(html)
            while time.time() < deadline:
                time.sleep(2)
                try:
                    html = self._page.content()
                except Exception:
                    continue
                if not is_waf_challenge(html):
                    print(f"  Challenge cleared after {int(300 - (deadline - time.time()))}s. "
                          f"Cookies saved to profile.", flush=True)
                    # Let the real page finish hydrating.
                    self._page.wait_for_timeout(wait_ms)
                    html = self._page.content()
                    return html
                if len(html) != last_html_len:
                    print(f"  page content changed ({last_html_len} → {len(html)} bytes), "
                          f"still a challenge page", flush=True)
                    last_html_len = len(html)
            print("  ⚠ 5-minute WAF wait expired; returning challenge HTML.", flush=True)
        return html

    def current_content(self) -> str:
        try:
            return self._page.content()
        except Exception:
            return ""

    # ── DOM evaluation helpers ──
    def eval_js(self, js: str):
        try:
            return self._page.evaluate(js)
        except Exception as e:
            print(f"    eval_js failed: {e}", flush=True)
            return None

    def eval_img_urls(self) -> list[str]:
        js = """() => {
            const out = [];
            document.querySelectorAll('img, source').forEach(el => {
                const srcset = el.srcset || el.getAttribute('data-srcset') || '';
                const direct = el.src || el.getAttribute('data-src') || '';
                if (direct) out.push(direct);
                srcset.split(',').forEach(s => {
                    const u = s.trim().split(/\\s+/)[0];
                    if (u) out.push(u);
                });
            });
            return Array.from(new Set(out));
        }"""
        return self.eval_js(js) or []

    def eval_next_data(self):
        return self.eval_js("() => window.__NEXT_DATA__ || null")

    def eval_window_keys(self) -> list[str]:
        return self.eval_js(
            "() => Object.keys(window).filter(k => /algolia|instant|search|state|__NEXT/i.test(k))"
        ) or []

    def eval_breadcrumb(self) -> list[str]:
        js = """() => {
            const sel = 'nav[aria-label*=breadcrumb i] a, nav[aria-label*=breadcrumb i] span, ol.breadcrumb a, [data-test*=breadcrumb] a, [data-test*=breadcrumb] span';
            const nodes = Array.from(document.querySelectorAll(sel));
            return nodes.map(n => n.textContent.trim()).filter(Boolean);
        }"""
        return self.eval_js(js) or []

    def eval_title(self) -> str:
        return self.eval_js(
            "() => document.querySelector('h1')?.textContent?.trim() || document.title"
        ) or ""

    def click_carousel_next(self, max_clicks: int = 20) -> int:
        js_click_once = """() => {
            const btn = document.querySelector(
                'button[aria-label*="next" i], button[data-test*="next" i], ' +
                'button[class*="next" i]:not([disabled]), .swiper-button-next:not(.swiper-button-disabled)'
            );
            if (!btn || btn.disabled) return false;
            btn.click();
            return true;
        }"""
        clicks = 0
        for _ in range(max_clicks):
            if not self.eval_js(js_click_once):
                break
            self._page.wait_for_timeout(400)
            clicks += 1
        return clicks

    # ── network capture ──
    def _on_request(self, request):
        url = request.url
        if any(s in url for s in ("algolia.net", "algolianet.com", "/search", "/api/")):
            self._captured_requests.append({
                "kind": "request",
                "url": url,
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data,
            })

    def _on_response(self, response):
        url = response.url
        if any(s in url for s in ("algolia.net", "algolianet.com")):
            try:
                body = response.text()
            except Exception:
                body = None
            self._captured_requests.append({
                "kind": "response",
                "url": url,
                "status": response.status,
                # Full body — callers need the complete Algolia result set for discovery.
                "body": body,
            })

    def captured_requests(self) -> list[dict]:
        return list(self._captured_requests)

    def clear_captured_requests(self):
        self._captured_requests.clear()

    def close(self):
        try:
            self._context.close()
            self._pw.stop()
        except Exception:
            pass

    # ── cookie-sharing HTTP fetch ──
    def fetch_bytes(self, url: str, timeout_ms: int = 30000) -> bytes | None:
        """
        GET `url` through Playwright's request context — reuses the persistent
        profile's cookies (including AWS WAF tokens). Returns raw body bytes or
        None on failure. Used for image downloads where requests.get would have
        to juggle cookies manually.
        """
        try:
            resp = self._context.request.get(url, timeout=timeout_ms)
            if not resp.ok:
                return None
            return resp.body()
        except Exception as e:
            print(f"    fetch_bytes {url[:80]}… failed: {e}", flush=True)
            return None

    def harvest_links(self, selector: str = "a[href]") -> list[str]:
        """Return all hrefs currently in the DOM matching the selector."""
        js = f"""() => Array.from(document.querySelectorAll({selector!r}))
                 .map(a => a.getAttribute('href'))
                 .filter(Boolean)"""
        return self.eval_js(js) or []

    def scroll_to_bottom(self, max_rounds: int = 30, pause_ms: int = 1500) -> int:
        """
        Scroll the page to the bottom repeatedly until height stops increasing.
        Returns the number of scroll rounds performed. Triggers lazy-loading of
        product tiles / infinite-scroll listings.
        """
        rounds = 0
        last_height = 0
        for _ in range(max_rounds):
            new_height = self.eval_js(
                "() => { window.scrollTo(0, document.body.scrollHeight); "
                "return document.body.scrollHeight; }"
            ) or 0
            self._page.wait_for_timeout(pause_ms)
            rounds += 1
            if new_height == last_height:
                break
            last_height = new_height
        return rounds


def rand_delay(lo: float = 3.0, hi: float = 6.0):
    time.sleep(random.uniform(lo, hi))

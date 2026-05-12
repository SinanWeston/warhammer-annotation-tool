#!/usr/bin/env python3
"""
Shared Playwright browser wrapper for coolminiornot.com.

CMON sits behind Cloudflare behavioral blocking. Strategy: persistent Chromium
profile + stealth evasions. The user solves the Cloudflare challenge once in
the visible browser window; the resulting `cf_clearance` cookie persists in
the profile and is reused across runs.

Any time a challenge is re-issued mid-scrape (either on a page navigation or
on a cookie-shared HTTP fetch), `solve_challenge_interactive` pauses, rings
the terminal bell, navigates the visible page to the challenged URL, and
polls until the challenge HTML disappears — then resumes automatically.

Model: scripts/warhammer_com/wh_browser.py::WhBrowser.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

BASE = "https://www.coolminiornot.com"
DEFAULT_PROFILE_DIR = Path(__file__).resolve().parent / "state" / ".browser_profile"

# Cloudflare challenge fingerprints. Any one substring in the response body
# means Cloudflare is interposing. We purposely avoid matching ordinary
# `__cf_bm` cookies or turnstile widgets embedded in regular pages.
CF_CHALLENGE_MARKERS = (
    "<title>Just a moment...</title>",
    'id="challenge-running"',
    'id="cf-challenge-running"',
    "cdn-cgi/challenge-platform/h/",
    "window._cf_chl_opt",
    "cf-mitigated",
)


def is_cf_challenge(html: str) -> bool:
    if not html:
        return False
    return any(m in html for m in CF_CHALLENGE_MARKERS)


class CmonBrowser:
    """Playwright Chromium session pinned to coolminiornot.com, stealth-patched, persistent."""

    def __init__(
        self,
        headless: bool = False,
        capture_requests: bool = False,
        profile_dir: Path | None = None,
        user_agent: str | None = None,
        challenge_wait_seconds: int = 600,
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
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()

        self._challenge_wait_seconds = challenge_wait_seconds

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

    # ── challenge handling ──
    def _alert_user(self, url: str):
        # Terminal bell + banner. The browser window is already the
        # challenged page, so the user can solve it directly.
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass
        print("\n" + "=" * 60, flush=True)
        print("  ⚠ Cloudflare challenge detected.", flush=True)
        print(f"  URL: {url[:120]}", flush=True)
        print("  The browser window should be showing the challenge.", flush=True)
        print("  Solve it manually (checkbox / puzzle) — this script will", flush=True)
        print("  auto-resume the moment the challenge clears.", flush=True)
        print("=" * 60, flush=True)

    def _poll_until_cleared(self, target_url: str) -> str:
        """Poll the visible page until is_cf_challenge is False. Returns final HTML."""
        deadline = time.time() + self._challenge_wait_seconds
        last_len = -1
        while time.time() < deadline:
            time.sleep(2)
            try:
                html = self._page.content()
            except Exception:
                continue
            if not is_cf_challenge(html):
                elapsed = int(self._challenge_wait_seconds - (deadline - time.time()))
                print(f"  Challenge cleared after {elapsed}s. Cookies saved to profile.",
                      flush=True)
                # Let the real page finish rendering.
                try:
                    self._page.wait_for_timeout(2000)
                    html = self._page.content()
                except Exception:
                    pass
                return html
            if len(html) != last_len:
                print(f"  … still on challenge page ({len(html)} bytes)", flush=True)
                last_len = len(html)
        print(f"  ⚠ {self._challenge_wait_seconds}s challenge wait expired; giving up.",
              flush=True)
        try:
            return self._page.content()
        except Exception:
            return ""

    def solve_challenge_interactive(self, target_url: str) -> str:
        """
        Bring the visible page to `target_url` (if it isn't already on a challenge
        for that URL) and wait for the user to solve. Used when a cookie-shared
        HTTP fetch returned challenge HTML but the page itself is elsewhere.
        """
        current = ""
        try:
            current = self._page.url
        except Exception:
            pass
        # If the browser page isn't already on the challenged URL, navigate so
        # the user has something to interact with.
        need_nav = not current or not current.startswith(target_url.split("?", 1)[0])
        if need_nav:
            try:
                self._page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"    solve_challenge: goto {target_url[:80]}… failed: {e}",
                      flush=True)
        self._alert_user(target_url)
        return self._poll_until_cleared(target_url)

    # ── navigation ──
    def goto(
        self,
        url: str,
        wait_ms: int = 3000,
        wait_until: str = "networkidle",
        timeout: int = 45000,
        solve_challenge: bool = True,
    ) -> str:
        """Navigate, return rendered HTML. Pauses on CF challenge if solve_challenge."""
        try:
            self._page.goto(url, wait_until=wait_until, timeout=timeout)
            self._page.wait_for_timeout(wait_ms)
        except Exception as e:
            print(f"    goto {url[:80]}… failed: {e}", flush=True)
            return ""
        html = self._page.content()
        if is_cf_challenge(html) and solve_challenge:
            self._alert_user(url)
            return self._poll_until_cleared(url)
        return html

    def current_content(self) -> str:
        try:
            return self._page.content()
        except Exception:
            return ""

    def current_url(self) -> str:
        try:
            return self._page.url
        except Exception:
            return ""

    # ── DOM helpers ──
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

    def harvest_links(self, selector: str = "a[href]") -> list[str]:
        js = f"""() => Array.from(document.querySelectorAll({selector!r}))
                 .map(a => a.getAttribute('href'))
                 .filter(Boolean)"""
        return self.eval_js(js) or []

    def eval_title(self) -> str:
        return self.eval_js(
            "() => document.querySelector('h1')?.textContent?.trim() || document.title"
        ) or ""

    def eval_text(self, selector: str) -> str | None:
        js = f"""() => {{
            const el = document.querySelector({selector!r});
            return el ? el.textContent.trim() : null;
        }}"""
        return self.eval_js(js)

    def scroll_to_bottom(self, max_rounds: int = 30, pause_ms: int = 1500) -> int:
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

    # ── network capture ──
    # Capture any same-origin non-asset request. Drops obvious static files
    # (images, CSS, fonts, JS bundles) so the dump stays readable while still
    # catching XHR/fetch endpoints like /browse/raw.
    _CAPTURE_SKIP_EXT = (
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
        ".css", ".js", ".mjs", ".woff", ".woff2", ".ttf", ".otf",
        ".mp4", ".webm", ".m3u8",
    )

    def _should_capture(self, url: str) -> bool:
        if "coolminiornot.com" not in url:
            return False
        path = url.split("?", 1)[0].lower()
        return not any(path.endswith(ext) for ext in self._CAPTURE_SKIP_EXT)

    def _on_request(self, request):
        url = request.url
        if not self._should_capture(url):
            return
        self._captured_requests.append({
            "kind": "request",
            "url": url,
            "method": request.method,
            "headers": dict(request.headers),
            "post_data": request.post_data,
        })

    def _on_response(self, response):
        url = response.url
        if not self._should_capture(url):
            return
        try:
            ct = response.headers.get("content-type", "")
            body = response.text() if ("json" in ct or "text" in ct or "html" in ct) else None
        except Exception:
            body = None
        # Truncate huge bodies so recon JSON stays manageable.
        if body and len(body) > 200_000:
            body = body[:200_000] + f"\n…[truncated, original {len(body)}B]"
        self._captured_requests.append({
            "kind": "response",
            "url": url,
            "status": response.status,
            "content_type": response.headers.get("content-type", ""),
            "body": body,
        })

    def captured_requests(self) -> list[dict]:
        return list(self._captured_requests)

    def clear_captured_requests(self):
        self._captured_requests.clear()

    # ── HTML fetch via the browser page ──
    # Request-context calls (`_context.request.get`) get blocked by Cloudflare
    # on CMON even with shared cookies — CF's bot check keys on the request's
    # fingerprint, which the request-context doesn't provide. So for every
    # HTML fetch we navigate the visible page; it's slower (one page load per
    # URL) but inherits the full CF-cleared browser context.
    def fetch_html(
        self,
        url: str,
        wait_ms: int = 1500,
        wait_until: str = "domcontentloaded",
        timeout: int = 45000,
    ) -> str:
        return self.goto(url, wait_ms=wait_ms, wait_until=wait_until,
                         timeout=timeout, solve_challenge=True)

    # ── XHR fetch inside the browser JS context ──
    # CMON's /browse/raw/N endpoint is intended as an infinite-scroll XHR
    # (it expects X-Requested-With: XMLHttpRequest + a Referer from /browse).
    # Top-level `goto()` navigation to those URLs produces a 403. Calling
    # fetch() from inside the page inherits cookies, Referer, same-origin
    # treatment, and lets us add the XHR header.
    def fetch_xhr_text(
        self,
        url: str,
        headers: dict | None = None,
        timeout_ms: int = 30000,
    ) -> str:
        # Must be on a same-origin page for this to work.
        current = self.current_url()
        if "coolminiornot.com" not in current:
            self.goto(f"{BASE}/browse", wait_ms=1500)

        merged_headers = {"X-Requested-With": "XMLHttpRequest"}
        if headers:
            merged_headers.update(headers)

        js = """async ({url, headers}) => {
            try {
                const r = await fetch(url, {
                    method: 'GET',
                    credentials: 'include',
                    headers,
                });
                return {ok: r.ok, status: r.status, text: await r.text()};
            } catch (e) {
                return {ok: false, status: 0, text: '', error: String(e)};
            }
        }"""
        try:
            result = self._page.evaluate(js, {"url": url, "headers": merged_headers})
        except Exception as e:
            print(f"    fetch_xhr eval failed for {url[:80]}…: {e}", flush=True)
            return ""
        if not result:
            return ""
        if not result.get("ok"):
            print(f"    fetch_xhr status={result.get('status')} url={url[:120]}",
                  flush=True)
            return ""
        return result.get("text") or ""

    def fetch_xhr_bytes(
        self,
        url: str,
        headers: dict | None = None,
    ) -> bytes | None:
        """
        Binary fetch inside the page's JS context. Returns raw bytes or None.
        CMON blocks Playwright's request-context for images (same reason as
        HTML), so we fetch through fetch() + arrayBuffer, base64-encode on
        the JS side, and decode here.
        """
        import base64

        current = self.current_url()
        if "coolminiornot.com" not in current:
            self.goto(f"{BASE}/browse", wait_ms=1500)

        merged_headers = dict(headers or {})
        js = """async ({url, headers}) => {
            try {
                const r = await fetch(url, {
                    method: 'GET',
                    credentials: 'include',
                    headers,
                });
                if (!r.ok) return {ok: false, status: r.status};
                const ab = await r.arrayBuffer();
                const bytes = new Uint8Array(ab);
                let binary = '';
                const CHUNK = 0x8000;
                for (let i = 0; i < bytes.length; i += CHUNK) {
                    binary += String.fromCharCode.apply(
                        null, bytes.subarray(i, i + CHUNK)
                    );
                }
                return {ok: true, status: r.status, b64: btoa(binary),
                        bytes: bytes.length};
            } catch (e) {
                return {ok: false, status: 0, error: String(e)};
            }
        }"""
        try:
            result = self._page.evaluate(js,
                                         {"url": url, "headers": merged_headers})
        except Exception as e:
            print(f"    fetch_xhr_bytes eval failed {url[:80]}…: {e}", flush=True)
            return None
        if not result:
            return None
        if not result.get("ok"):
            print(f"    fetch_xhr_bytes status={result.get('status')} url={url[:120]}",
                  flush=True)
            return None
        try:
            return base64.b64decode(result["b64"])
        except Exception as e:
            print(f"    fetch_xhr_bytes b64 decode failed: {e}", flush=True)
            return None

    # ── session warm-up ──
    _session_warmed = False

    def warm_session(self, url: str | None = None, force: bool = False) -> bool:
        """
        Navigate to `url` (default: CMON /browse) to establish a valid session
        cookie + Referer chain. CMON's server returns 403 for filtered /browse
        URLs when the client hits them cold (no prior /browse visit). Subsequent
        navigations then succeed because they carry a Referer from /browse.

        Idempotent within a CmonBrowser instance — noop after first successful
        warm unless force=True.

        Returns True if the warm-up landed on a non-challenge, non-error page.
        """
        if self._session_warmed and not force:
            return True
        url = url or f"{BASE}/browse"
        print(f"  warming session via {url}", flush=True)
        html = self.goto(url, wait_ms=2000)
        ok = bool(html) and "403" not in (self.eval_title() or "") \
            and not is_cf_challenge(html)
        if ok:
            self._session_warmed = True
            print("  session warmed OK", flush=True)
        else:
            print("  ⚠ warm-up did not land on a clean page", flush=True)
        return ok

    # ── cookie-sharing HTTP fetch (used for image downloads only) ──
    def fetch_bytes(
        self,
        url: str,
        timeout_ms: int = 30000,
        retry_on_challenge: bool = True,
    ) -> bytes | None:
        """
        GET `url` through Playwright's request context — reuses the persistent
        profile's cookies (including cf_clearance). Returns raw body bytes or
        None on failure.

        If Cloudflare re-challenges the request context, we detect the challenge
        body, pause interactively (bringing the visible page to the URL so the
        user can solve), and retry once.
        """
        try:
            resp = self._context.request.get(url, timeout=timeout_ms)
        except Exception as e:
            print(f"    fetch_bytes {url[:80]}… failed: {e}", flush=True)
            return None

        body = None
        try:
            body = resp.body()
        except Exception as e:
            print(f"    fetch_bytes body() {url[:80]}… failed: {e}", flush=True)

        if not resp.ok:
            print(f"    fetch_bytes status={resp.status} len={len(body) if body else 0} "
                  f"url={url[:120]}", flush=True)
            sample = body[:4096].decode("utf-8", "ignore") if body else ""
            if is_cf_challenge(sample) and retry_on_challenge:
                print(f"    fetch_bytes: CF challenge on {url[:80]}…", flush=True)
                self.solve_challenge_interactive(url)
                return self.fetch_bytes(url, timeout_ms=timeout_ms,
                                        retry_on_challenge=False)
            return None

        # 200 OK but the body is actually a challenge — rare for images (binary
        # bodies won't match), but possible when `url` points at HTML.
        if body and retry_on_challenge:
            sample = body[:4096].decode("utf-8", "ignore")
            if is_cf_challenge(sample):
                print(f"    fetch_bytes: CF challenge body on {url[:80]}…", flush=True)
                self.solve_challenge_interactive(url)
                return self.fetch_bytes(url, timeout_ms=timeout_ms,
                                        retry_on_challenge=False)

        return body

    def fetch_text(
        self,
        url: str,
        timeout_ms: int = 30000,
        retry_on_challenge: bool = True,
    ) -> str | None:
        data = self.fetch_bytes(url, timeout_ms=timeout_ms,
                                retry_on_challenge=retry_on_challenge)
        if data is None:
            return None
        try:
            return data.decode("utf-8", "replace")
        except Exception:
            return None

    def close(self):
        try:
            self._context.close()
            self._pw.stop()
        except Exception:
            pass


def rand_delay(lo: float = 2.0, hi: float = 5.0):
    time.sleep(random.uniform(lo, hi))

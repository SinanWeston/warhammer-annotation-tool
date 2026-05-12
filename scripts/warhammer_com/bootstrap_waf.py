#!/usr/bin/env python3
"""
One-shot WAF bootstrap — opens the warhammer.com 40K landing page in a headed
Chromium, waits for the human to solve the AWS WAF CAPTCHA, and persists the
auth cookies to the shared browser profile so subsequent (headless) runs skip
the challenge.

Usage:
    yolo_env/bin/python3 scripts/warhammer_com/bootstrap_waf.py

After a successful run, cookies live under scripts/warhammer_com/recon/.browser_profile/
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gw_shop_constants import LANDING_40K, PROFILE_DIR  # noqa: E402
from wh_browser import WhBrowser, is_waf_challenge  # noqa: E402


def main() -> int:
    print(f"Opening {LANDING_40K} (headed).")
    print(f"Browser profile:  {PROFILE_DIR}")
    print("If a captcha appears, solve it in the browser window that opens.")
    print("Polling for success; will exit automatically.\n")

    with WhBrowser(headless=False, capture_requests=False, profile_dir=PROFILE_DIR) as b:
        html = b.goto(LANDING_40K, wait_ms=4000)
        if is_waf_challenge(html):
            # goto() already polls for up to 5 minutes; if still challenged, fail loudly.
            print("✖ WAF challenge still present after polling. Re-run and try again.",
                  file=sys.stderr)
            return 1
        if not html:
            print("✖ Landing page returned empty HTML.", file=sys.stderr)
            return 1
        size_kb = len(html) // 1024
        print(f"✓ Landing page loaded ({size_kb} KB). Cookies persisted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

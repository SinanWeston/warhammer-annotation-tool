#!/usr/bin/env python3
"""Tests for is_cf_challenge — ensures marker-based detection stays specific."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from cmon_browser import is_cf_challenge  # noqa: E402


def test_detects_just_a_moment_title():
    html = '<html><head><title>Just a moment...</title></head><body></body></html>'
    assert is_cf_challenge(html) is True


def test_detects_challenge_running_div():
    assert is_cf_challenge('<div id="challenge-running"></div>') is True
    assert is_cf_challenge('<div id="cf-challenge-running"></div>') is True


def test_detects_cf_chl_opt_script():
    assert is_cf_challenge('<script>window._cf_chl_opt = {r:1};</script>') is True


def test_detects_challenge_platform_url():
    html = '<script src="/cdn-cgi/challenge-platform/h/b/jsd"></script>'
    assert is_cf_challenge(html) is True


def test_detects_cf_mitigated_header_echo():
    assert is_cf_challenge('<body>cf-mitigated: challenge</body>') is True


def test_ignores_ordinary_page():
    html = (
        '<html><head><title>CoolMiniOrNot - Gallery</title></head>'
        '<body><h1>WH40K</h1><a href="/vault/123">Entry</a></body></html>'
    )
    assert is_cf_challenge(html) is False


def test_ignores_empty_and_none():
    assert is_cf_challenge("") is False
    assert is_cf_challenge(None) is False

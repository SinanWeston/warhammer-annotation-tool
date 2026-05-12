#!/usr/bin/env python3
"""
Pure-HTML parsers for CMON listing tiles and entry detail pages.

Decoupled from the browser so they can be unit-tested against recon fixtures
without spinning up Playwright.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from bs4 import BeautifulSoup


BASE = "https://www.coolminiornot.com"


@dataclass
class Tile:
    id: str                   # numeric artwork id, as string
    title: str                # descriptive title from the anchor's `title` attr
    artist: str               # "by {artist}" tail of the title
    thumb_url: str            # /filestorage/images/3/... thumbnail, absolute

    def to_jsonable(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "thumb_url": self.thumb_url,
        }


@dataclass
class EntryDetail:
    id: str
    url: str
    title: str = ""           # og:title
    description: str = ""     # og:description
    artist: str = ""          # extracted from header / title suffix
    score: float | None = None          # .regaverage
    votes: int | None = None            # count from .votes-and-views
    views: str = ""                     # raw view count text (e.g. "179.9k")
    tags: list[str] = field(default_factory=list)  # clickable tag chips
    image_urls: list[str] = field(default_factory=list)   # hi-res /o/ URLs, absolute
    og_image: str = ""                  # primary image

    def to_jsonable(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "artist": self.artist,
            "score": self.score,
            "votes": self.votes,
            "views": self.views,
            "tags": self.tags,
            "image_urls": self.image_urls,
            "og_image": self.og_image,
        }


# ── tiles ─────────────────────────────────────────────────────────────────

_TILE_TITLE_SPLIT = re.compile(r"\s+by\s+", re.I)


def _abs(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE + url
    return url


def parse_tiles(html_fragment: str) -> list[Tile]:
    """
    Parse `<a class="artwork ..." data-artwork-id="...">` anchors from either
    the full /browse page or a /browse/raw/N fragment. Deduplicates by id
    (each entry appears twice as t1+t2 variants in the DOM).
    """
    if not html_fragment or not html_fragment.strip():
        return []
    soup = BeautifulSoup(html_fragment, "html.parser")
    seen: dict[str, Tile] = {}
    for a in soup.find_all("a", attrs={"data-artwork-id": True}):
        aid = (a.get("data-artwork-id") or "").strip()
        if not aid or aid in seen:
            continue
        title_attr = (a.get("title") or "").strip()
        if _TILE_TITLE_SPLIT.search(title_attr):
            title, artist = _TILE_TITLE_SPLIT.split(title_attr, 1)
        else:
            title, artist = title_attr, ""
        img = a.find("img")
        thumb = _abs((img.get("src") or img.get("data-src") or "") if img else "")
        seen[aid] = Tile(id=aid, title=title.strip(), artist=artist.strip(),
                         thumb_url=thumb)
    return list(seen.values())


def _text_or_empty(el) -> str:
    if el is None:
        return ""
    return el.get_text(" ", strip=True)


_VOTES_RE = re.compile(r"([\d,]+)\s*Votes", re.I)


def parse_entry_detail(html: str, entry_id: str, url: str) -> EntryDetail:
    soup = BeautifulSoup(html or "", "html.parser")
    d = EntryDetail(id=entry_id, url=url)

    # OpenGraph — primary authoritative source for title/description/image
    for m in soup.find_all("meta"):
        p = m.get("property") or m.get("name") or ""
        c = m.get("content") or ""
        if p == "og:title":
            d.title = c.strip()
        elif p == "og:description":
            d.description = c.strip()
        elif p == "og:image":
            d.og_image = _abs(c.strip())

    # Score
    score_el = soup.find(class_="regaverage")
    if score_el:
        t = _text_or_empty(score_el)
        try:
            d.score = float(t)
        except ValueError:
            d.score = None

    # Votes + views — both share the votes-and-views class
    vv_els = soup.find_all(class_="votes-and-views")
    for el in vv_els:
        t = _text_or_empty(el)
        m = _VOTES_RE.search(t)
        if m:
            try:
                d.votes = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        if "view" in t.lower() and not d.views:
            # strip the "Views" tail and commas
            d.views = re.sub(r"\s*Views?\s*$", "", t, flags=re.I).strip()

    # Clickable tags (category, manufacturer, scale, setting, type)
    for tag in soup.select("div.tag.clickable"):
        t = _text_or_empty(tag)
        if t and t not in d.tags:
            d.tags.append(t)

    # Hi-res /o/ image URLs — filter specifically to the main artwork block.
    # `img.artwork.mw-100` is the detail-page gallery; other `.w-100` images
    # are the sidebar's "more from this artist" thumbnails.
    for img in soup.select("img.artwork.mw-100"):
        src = img.get("src") or img.get("data-src") or ""
        if "/filestorage/images/o/" in src:
            url_abs = _abs(src)
            if url_abs not in d.image_urls:
                d.image_urls.append(url_abs)

    # Fallback: if the detail-page selector missed, use og:image.
    if not d.image_urls and d.og_image:
        d.image_urls.append(d.og_image)

    # Artist — CMON entry pages render the artist name as the first <h1 class="h1">,
    # with the descriptive entry title as a second <h1 class="h1 mb-0">.
    for h1 in soup.find_all("h1", class_="h1"):
        classes = h1.get("class", [])
        if "mb-0" in classes:
            continue  # this h1 is the entry title, not the artist
        d.artist = _text_or_empty(h1)
        break

    return d

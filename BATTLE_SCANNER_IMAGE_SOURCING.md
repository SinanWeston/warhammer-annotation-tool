# Battle Scanner — Image Acquisition Plan

**Goal.** Assemble the largest possible corpus of Warhammer miniature images for the annotator/training pipeline — optimised for *coverage and realism*, not raw count. Maximise two things: (1) **per-unit depth** (many reference images per unit across paint schemes/angles/lighting — the lever that gates retrieval accuracy) and (2) **deployment realism** (cluttered, multi-model, phone-shot tabletop scenes that match real use). Every image is ingested with provenance metadata so the pile can be deduped, sliced, and later split into product-safe vs research-only subsets.

**Scope (locked):**
- **Subjects:** painted **+ primed + bare plastic/resin** (assembled *and* on-sprue), plus partially-painted. Box art, official 3D renders, and 3D-printed proxies are also collected but **tagged off-distribution** (`tier1_only` / `proxy`) so they're filterable.
- **Posture:** **maximise volume now, sort legality later.** Nothing is pre-filtered on licensing; everything is captured with full provenance and flagged `product_safe = false` by default. The legality sort is deferred, not skipped (see end).

---

# PART A — COLLECTION CRITERIA

## A1. What counts as a target image
Contains at least one Warhammer (or, for the detector only, any ~28–32 mm wargame) miniature, in any finish state above. For **unit recognition** it must be a real GW unit; for **Tier-1 detection** any humanoid miniature helps the model generalise (tag accordingly).

## A2. The four things that actually matter (priority order)
Collect against these, in this order — this *is* the goal expressed as collection priorities:
1. **Per-unit depth** — target **≥5 images per unit**, spanning **≥3 paint schemes** and **multiple angles**. This is the single lever that failed in v0 (78% of units had 1 crop).
2. **Deployment realism** — cluttered, multi-mini, phone-shot, mixed-lighting tabletop scenes (Tier T2 below). This closes the train/serve gap.
3. **Breadth** — cover as much of the taxonomy (`units.json`) as possible, but never at the expense of (1) for supported units.
4. **Intra-unit diversity** — variety of paint/angle/lighting/background/model-state within each unit.

## A3. Realism tiers (tag every image)
| Tier | Definition | Value | Collection weight |
|---|---|---|---|
| **T0** | Official/studio: single mini, clean white/black bg, pro lighting | Exact labels, great for gallery + weak-label seeding; **off-distribution** for the product | Grab all (cheap), don't over-rely |
| **T1** | Hobby showcase: single/few minis, plain-ish bg, decent photo | Good gallery depth + paint variety | High |
| **T2** | In-the-wild: cluttered table, multi-mini, phone, terrain, real lighting | **Matches deployment — highest value, scarcest** | **Highest — actively hunt** |

## A4. Diversity axes to deliberately cover (per-unit checklist)
Paint scheme (official, custom, unpainted) · angle (front/side/back/3-4/top-down) · lighting (studio/natural/indoor/flash) · background (plain/battlemat/terrain/clutter) · scale context (single/squad/army/dense table) · model state (assembled/on-sprue/primed/converted/magnetised) · photo quality (pro → potato). Track coverage so you can target the holes, not collect more of what you already have.

## A5. Hard negatives & non-targets to collect
For unknown-rejection (Tier 3) and Tier-1 false-positive reduction, deliberately collect:
- **Look-alike minis that aren't GW:** D&D/Pathfinder minis, board-game minis (Zombicide, Marvel Crisis Protocol, Star Wars Legion), historical/toy soldiers, other wargame ranges (Infinity, Warmachine). → `is_negative`, `not_gw`.
- **Scene clutter:** terrain pieces, dice, tokens, templates, rulers, paint pots, empty battlemats. → `is_negative`.
- **Bare/ambiguous:** sprues, unassembled bits.

**Exclude (look like 40K but aren't miniatures):** video-game screenshots (Space Marine 2, Total War: Warhammer, Dawn of War, Mechanicus), concept art/illustrations, Black Library covers, cosplay, full-size statues. Tag `exclude` if scraped incidentally so they never reach training.

## A6. Quality floor & what to skip
Keep: anything with the mini ≳200–300 px on its longest side. Keep low-res too (phone crops vary), but flag `low_res`. **Skip / drop:** exact duplicates, watermarked stock thumbnails, tiny aggregator thumbnails when a larger source exists, illustrations-as-minis, NSFW/irrelevant.

## A7. Source-evaluation criteria (how to triage any source)
Score each source on: **volume** · **realism tier** · **label availability** (exact / weak-title / weak-hashtag / none) · **per-unit-query support** (can you search by unit name?) · **access friction** (open API / scrape-tool / manual / paid API / login-gated) · **dupe risk** (retailers reuse GW studio shots) · **license posture** (CC/open → product-safe candidate; seller/forum/unknown → research-only) · **cost** · **block-aggressiveness**.

## A8. Metadata schema (the sidecar — this is what makes "sort later" possible)
Write one JSON record per image at acquisition time. **Without this, "maximise now, sort legality later" is impossible.**
```json
{
  "image_id": "uuid",
  "source": "ebay | reddit:r/minipainting | instagram | warhammer_com | youtube:<channel> | roboflow:<ds> | own | ...",
  "source_url": "permalink",
  "scrape_date": "ISO-8601",
  "uploader": "seller/handle if available",
  "caption_title": "original text (feeds weak labels)",
  "faction": "weak label | null",
  "unit": "weak label | null",
  "label_source": "official | title | hashtag | inferred | reverse_search | none",
  "label_confidence": 0.0,
  "finish_state": "painted | primed | bare | partial | onsprue | unknown",
  "realism_tier": "T0 | T1 | T2",
  "num_minis_est": null,            // filled by detector pass
  "is_negative": false,
  "not_gw": false,
  "phash": "perceptual hash for dedup",
  "resolution": [w, h],
  "license_status": "official_gw | marketplace_seller | cc_by | cc0 | forum_user | unknown",
  "product_safe": false             // DEFAULT false; promoted later
}
```

---

# PART B — SOURCE CATALOG (every source)

Tables score each source qualitatively. **Labels:** Exact / Title (from listing/post title) / Hashtag / None. **Access:** API / Tool (named in Part C) / Manual / Download.

## B1. Official / first-party — *canonical labels + gallery seed (T0)*
| Source | Volume | Tier | Labels | Access | Notes |
|---|---|---|---|---|---|
| warhammer.com webstore | High | T0 | **Exact** (unit = product page) | Tool/scrape | The reference-gallery backbone; multi-angle official shots, perfectly named |
| Warhammer Community (articles/previews/Golden Demon) | High | T0–T1 | Title | Tool/scrape | Showcases, painted variety |
| Forge World store | Medium | T0 | **Exact** | Tool | Resin units, often missing elsewhere |
| Warhammer+ (Citadel Masterclass, battle reports, animations) | Medium | T1–T2 | Title | Manual/frames | Paid; battle reports = T2 scenes |
| GW official IG / YouTube / FB | Medium | T0–T1 | Title/Hashtag | Tool/frames | Clean, named |
| Wahapedia / BattleScribe-adjacent / New Recruit | Low–Med | T0 | **Exact** | Manual | Some unit images; mainly for the points/rules layer |

## B2. Marketplaces & classifieds — *huge volume + finish-state variety (T1–T2)*
| Source | Volume | Tier | Labels | Access | Notes |
|---|---|---|---|---|---|
| **eBay** (active **+ sold/completed**) | **Very high** | T1–T2 | Title | API (eBay Browse) / Apify | Sold listings = free historical archive; lots of "primed", "NoS", "pro-painted" |
| Kleinanzeigen.de | High | T1–T2 | Title | Tool | **DE — your region**; big second-hand mini market |
| Ricardo.ch / Tutti.ch / Anibis.ch | Medium | T1–T2 | Title | Tool | **CH — local**; realistic amateur photos |
| Vinted | High | T1–T2 | Title | Apify/Tool | Big EU second-hand; phone photos |
| Facebook Marketplace + buy/sell/trade groups | **Very high** | T2 | Title | Apify (login) | Hard to access, gold for realism |
| r/miniswap (+ for-sale threads) | Medium | T1–T2 | Title/flair | PRAW | Hobbyist sale photos, often painted |
| Mercari / Depop / Wallapop / Leboncoin / Marktplaats | High | T1–T2 | Title | Tool/Apify | Regional second-hand |
| Etsy | Medium | T1 | Title | Tool | Commission-painted **and** 3D proxies (tag `proxy`) |
| Catawiki / hobby auction sites | Low–Med | T1 | Title | Manual | Painted army lots |
| Used sections: Frontline Gaming, Troll Trader, Wayland used | Low–Med | T1 | Title | Tool | Curated second-hand |

## B3. Reddit & forums — *weak labels + realism gold (T1–T2)*
| Source | Volume | Tier | Labels | Access | Notes |
|---|---|---|---|---|---|
| **r/minipainting** | **Very high** | T1 | Title | PRAW/gallery-dl | Huge, high-quality painted, often named in title/comments |
| Faction subs: r/spacemarines, r/Necrons, r/Tyranids, r/deathguard, r/orks, r/Eldar, r/Tau, r/AdeptaSororitas, r/Custodes, r/GreyKnights, r/imperialknights, r/ChaosSpaceMarines … | High | T1–T2 | Title + **faction known** | PRAW | Faction is implied by the sub → free weak faction label |
| **r/Warhammercompetitive / battle-report posts** | Medium | **T2** | Title | PRAW | Real tournament/table scenes — deployment realism |
| r/Warhammer40k, r/Warhammer, r/WarhammerArmies, r/Wargaming, r/printedminis | High | T1–T2 | Title | PRAW | Mixed; r/printedminis → `proxy` |
| **DakkaDakka** (galleries, P&M blogs, battle reports) | High | T1–T2 | Title | gallery-dl/scrape | You used it; mine army-showcase + battle-report threads for T2 |
| **Bolter & Chainsword** (painting logs, Hall of Honour) | Medium | T1 | Title | scrape | Space-Marine-heavy, named |
| Goonhammer / BoLS / Spikey Bits / Tabletop Gaming News galleries | Medium | T1 | Title | scrape | News-site showcase galleries |
| imgur painting albums; 1d4chan archives | Medium | T1 | None/Title | gallery-dl | Often linked from Reddit |

## B4. Social media — *massive + hashtag weak labels (T1–T2)*
| Source | Volume | Tier | Labels | Access | Notes |
|---|---|---|---|---|---|
| **Instagram** (#warhammer40k, #paintingwarhammer, #<faction>, #<unit>, painter accounts) | **Very high** | T1–T2 | **Hashtag** | Instaloader / Apify / gallery-dl | Hashtags = weak unit/faction labels at scale |
| Pinterest ("X painted" boards) | High | T1 | Title | gallery-dl | Aggregates other sources (dupe risk) |
| **Flickr** (Warhammer pools/groups) | Medium | T1 | Tag | API/gallery-dl | **Often CC-licensed → product-safe candidate** |
| DeviantArt / ArtStation (mini photography) | Medium | T1 | Title | gallery-dl | Filter out illustration |
| Twitter/X, Tumblr, Bluesky, Mastodon | Medium | T1–T2 | Hashtag | gallery-dl/API | Emerging hobby communities |
| VK (Russian painting scene) | Medium | T1 | Title | scrape | Large, under-tapped |
| TikTok (#warhammer painting clips) | Medium | T2 | Hashtag | yt-dlp + frames | Extract frames |

## B5. Video → frames — *underused; T2 realism + multi-angle + paint progression*
| Source | Volume | Tier | Labels | Access | Notes |
|---|---|---|---|---|---|
| **Battle-report channels** (Tabletop Tactics, MiniWarGaming, Play On Tabletop, Vanguard Tactics, Guerrilla Miniature Games, Winters SEO) | **Very high** (frames) | **T2** | Channel/episode | yt-dlp + ffmpeg | Full tables, many angles, real lighting — the best T2 source you're not using |
| **Painting tutorials** ("how to paint X") | High | T1 | Title (unit) | yt-dlp + ffmpeg | Same unit at primed → basecoat → finished = **paint variance within one unit** for invariance training |
| Unboxing / build videos | Medium | T1 | Title | yt-dlp | Bare plastic + on-sprue + primed |
| Twitch painting/40K VODs | Medium | T1–T2 | Channel | yt-dlp (VOD) | Long, frame-extract sparsely |

*Frame-extraction tip: sample ~1 frame/2–5 s, then embedding-dedup hard (consecutive frames are near-identical).*

## B6. Painting showcase & commission studios — *named units, multi-angle, pro photos (T1)*
| Source | Volume | Tier | Labels | Access | Notes |
|---|---|---|---|---|---|
| **CMON (CoolMiniOrNot)** | High | T1 | Title | scrape | You used it; named, rated |
| **Putty&Paint** | Medium | T1 | Title | scrape | High-end, named units |
| Golden Demon / Crystal Brush galleries | Medium | T1 | Title | scrape | Competition pieces |
| Commission painter portfolios (Siege Studios, Den of Imagination, Awesome Paint Job, Brush4Hire, etc.) | Medium | T1 | Title | scrape | Many named units, multiple clean angles per unit — **excellent per-unit depth** |

## B7. Retailers — *mostly GW-studio dupes + some own/used (T0)*
Element Games, Wayland Games, Goblin Gaming, Miniature Market, Noble Knight Games, Frontline Gaming, Chaos Cards, Magic Madhouse, Firestorm, Zatu, 365 Games, local FLGS sites. **High dupe risk** (they reuse warhammer.com photos) → ingest then aggressively pHash-dedupe against the official set; keep only own/used-section photos.

## B8. 3D model / printing — *renders + proxy minis (tag `not_gw` / `tier1_only`)*
MyMiniFactory, Cults3D, Thingiverse, Printables, Thangs, Yeggi (3D search), Patreon sculptors (Artisan Guild, Titan Forge, etc.), Etsy printed minis. Useful **only** for Tier-1 detector generalisation and as negatives for unit recognition (they aren't GW units). Renders also help the detector see clean silhouettes. Tag clearly so they never pollute the gallery.

## B9. Image search & SERP APIs — *broad sweep + the query-by-taxonomy engine*
| Source | Volume | Labels | Access | Notes |
|---|---|---|---|---|
| Google Images via **SerpApi** | Very high | Query→weak | API (100 free/mo, paid beyond) | Structured JSON results for any unit query |
| **Google Custom Search JSON API** (Programmable Search, image mode) | High | Query→weak | API (100/day free) | Cheapest live first-party option |
| **Yandex Images** | High | Query→weak | scrape/API | **Best reverse-image search** — key for depth expansion |
| Brave Search API | Medium | Query→weak | API (~1k/mo free) | Live alternative |
| ScrapeGraphAI / Firecrawl / Olostep | — | — | API | General page→structured scraping for sites without APIs |
| ~~Bing Image / Visual Search API~~ | — | — | **DEAD** | **Retired Aug 11 2025 — do not use** |
| **Reverse-image expansion** (SerpApi Google Lens, **TinEye API**, Yandex) | — | — | API | Feed a known-unit crop → find more instances of the *same* unit → multiplies per-unit depth |

## B10. Existing datasets — *instant labeled volume (some product-safe)*
| Source | Volume | Labels | License | Notes |
|---|---|---|---|---|
| **Roboflow Universe** Warhammer sets (e.g. Puopolo ~97 img: plague_marine/hellblaster/captain_gravis; Krüger ~35 img: Intercessors/Hearthkyn) | Small | **Bbox** | **CC-BY-4.0** | Tiny but free, labeled, **clean-licensed** → product-safe seed; download via Roboflow API |
| Roboflow Universe miniature / figurine / toy-soldier / tabletop sets | Med | Bbox/class | mixed | Tier-1 generalisation + negatives |
| **Re-LAION** (filter captions for unit/faction names → image URLs) | Massive (weak) | Caption→weak | research | Note: LAION-5B was withdrawn; **Re-LAION** is the current cleaned release — use that |
| Hugging Face Datasets / Kaggle / GitHub repos ("warhammer", "miniatures") | Med | mixed | mixed | Check for prior scrapes |
| Open Images (figurine/toy classes) | Med | Bbox | CC | Negatives + Tier-1 background diversity |

## B11. Your own + in-the-wild capture — *ground truth, full control, product-safe (T2)*
| Source | Volume | Tier | Labels | Notes |
|---|---|---|---|---|
| **Your own collection** (you paint 40K) | Med | T0–T2 | **Exact** | Shoot painted/primed/bare/on-sprue, single + on-table, multiple lightings/angles. **Highest value per image** and **product-safe** |
| Club / FLGS / tournament tables (with permission) | Med | **T2** | partial | Real deployment scenes; ask stores/event organisers |
| Friends' / opponents' armies | Med | T1–T2 | Exact | Different schemes, free |

This is the only source that is simultaneously realistic, perfectly labeled, and cleanly licensed. Spend real effort here.

## B12. Synthetic & augmentation — *multiply what you have (esp. Tier-1)*
- **Copy-paste augmentation (highest ROI):** SAM-cut segmented minis → composite onto varied tabletop/terrain backgrounds → unlimited cluttered scenes with **free, exact bounding boxes + controllable occlusion**. Directly attacks the occlusion/clustering problem.
- **3D render + domain randomisation** (if you have STLs): BlenderProc / NVIDIA Omniverse Replicator / Kubric → labeled detector data with randomised pose/light/bg.
- **Generative (low priority, tag `synthetic`):** diffusion "warhammer miniature" images — hallucinated, not real units; Tier-1 only at most. Mostly skip.

---

# PART C — ACQUISITION METHODS & TOOLING

## C1. The query-by-taxonomy engine (core method for per-unit depth)
Drive collection off `units.json`. For each unit × finish term × source, issue queries and tag results with the queried unit as a weak label. This is what builds the gallery-depth lever *and* labels for free.
```
for faction in v1_factions:
  for unit in taxonomy.units(faction):
    for finish in ["painted", "primed", "unpainted", ""]:
      q = f"{unit} {finish} miniature warhammer"
      results = search(source, q)        # SerpApi / Google CSE / gallery-dl site search / Reddit / IG hashtag
      ingest(results, weak_unit=unit, weak_faction=faction, label_source="query")
    track_depth(unit)                     # stop when depth target hit; else escalate sources
```
Run it widest for v1 factions first; let the depth tracker tell you which units are still thin and need reverse-image expansion or manual capture.

## C2. Reverse-image expansion
For any unit still below depth target, take your best 1–2 confirmed crops and run reverse search (Yandex / SerpApi Google Lens / TinEye) → harvest more instances of the *same* unit. Cheap way to deepen the long tail.

## C3. Tooling (all current/live)
| Tool | Use |
|---|---|
| **gallery-dl** | One tool for Reddit, Instagram, Twitter/X, Flickr, DeviantArt, Pinterest, imgur, ArtStation, Tumblr, booru-style — bulk image pull with metadata |
| **yt-dlp + ffmpeg** | YouTube/Twitch/TikTok download → frame extraction |
| **PRAW** | Reddit (posts, comments, flairs) — moderate volume; Reddit API is paid above free limits, Pushshift is restricted |
| **Instaloader** | Instagram by hashtag/account |
| **Apify** (actors) | eBay, Facebook Marketplace, Vinted, Instagram, generic — handles login/anti-bot for the hard marketplaces |
| **SerpApi / Google Custom Search JSON API** | Programmatic image-search results |
| **Firecrawl / ScrapeGraphAI / Olostep** | Page→structured scraping for sites without APIs |
| **Scrapy / Playwright** | Custom crawlers for forums (DakkaDakka, B&C) and retailer catalogs |
| **Roboflow SDK / HF `datasets`** | Pull existing labeled datasets |

## C3.1 Implemented scrapers — exactly how & where (operational state, 2026-06-06)

The repo's actual scrapers, their run command, what they need, reliability, and current
state. **Active env: `fiftyone_env`** (needs `playwright` + `playwright-stealth` for the
browser ones; `requests`/`beautifulsoup4` for the HTTP ones).

| Source | Script | Run | Creds | Reliability | State |
|---|---|---|---|---|---|
| **Warhammer Community** | `scripts/warhammer_community/scraper.py` | `… scraper.py --limit N` (omit for all) | none | ✅ HTTP, **robots-allowed**, reliable unattended | NEW — first run 2026-06-06 (GW hobby-article studio minis, faction-labeled) |
| **CMON** | `scripts/cmon/cmon_scrape.py` | `… cmon_scrape.py single` (types: single/squad/bust/diorama) | none | ⚠️ headed browser (Playwright+stealth) — **flaky unattended** (browser dies after warming); supervise | 2.9k ingested; `single` run ~20/533 done — more needs babysitting |
| **GW shop** | `scripts/warhammer_com/gw_shop_cli.py` | `… gw_shop_cli.py scrape --factions X` (discover done) | WAF cookies (`gw_shop_cli.py bootstrap` once — solve AWS WAF CAPTCHA) | ⚠️ headed browser + WAF | 3k ingested; ~92 DG product shots on disk (per-unit dirs) |
| **dakkadakka** | `scripts/scrape_dakkadakka.py` | `--faction X` / `--all --limit N` | none | ✅ pure HTTP (requests+BS4); **small community site — bound it, don't blast** | 14.3k ingested |
| **eBay** | `scripts/scrape_ebay.py` | (Playwright) | none | ⚠️ aggressive anti-bot, **ban risk** | 7.3k ingested |
| **Reddit** | `scripts/reddit_collector.py` | `--all --limit N` | `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` (PRAW app) | API | 11k already ingested; **fresh pull blocked on creds** |
| **Flickr** | `scripts/flickr_collector.py` | — | `FLICKR_API_KEY` | API (CC-licensed → product-safe) | **blocked (no key)** |
| **YouTube** | `scripts/youtube_collector.py` | `--all-channels` | yt-dlp | frame-extract | not run; low gallery value |
| **Google/SERP** (Wave 1 depth engine) | per-unit query-by-taxonomy (C1) | — | `SERPAPI_KEY` or Google CSE | API | **blocked (no key)** — the per-unit depth lever |
| **Roboflow** | `scripts/curation/acquire_roboflow.py` | — | `ROBOFLOW_API_KEY` ✅ | API | done (314 CC-BY) |
| **Lexicanum** | *not built* | MediaWiki API (`/api.php`, category→images) | none | ✅ API, polite | **mostly lore artwork, low mini-photo yield** — low priority |
| **Bluesky** | *not built* | public AT-protocol API (no auth) | none | ✅ API | candidate new source (hobby painted minis) |

**Ingest path (every source):** scraper writes `images/{faction}/{unit_or_slug}/` →
add to `wh40k_pile` (faction/unit from the dir path, source + provenance sidecar) →
**embed with frozen dinov2-large** (CLS, L2-norm) → dedup → pool. Examples:
`scripts/curation/ingest_gw_shop_backlog.py`, `ingest_new_cmon_dg.py`,
`seed_dg_gallery.py`. **Embedding is the bottleneck** — CPU ≈ 1–2 h per 1k images;
batch on Colab GPU (`scripts/curation/embed_colab.ipynb`) for anything large.

### Hard-won lessons (read before scraping anything)
1. **Check disk before scraping — ingestion ≠ acquisition.** Repeatedly (DG gallery,
   gw_shop, CMON) the "need to scrape" was actually "already scraped, never ingested."
   `grep`/`glob` the `scripts/*/images/` dirs and compare basenames to `wh40k_pile`
   *first*. The DG gallery (0→189, best-retrieving v1 faction) needed **zero** scraping.
2. **Browser scrapers (CMON, eBay) are flaky unattended** — supervise them; don't fire-
   and-forget. HTTP scrapers (warhammer_community, dakka) run reliably unattended.
3. **An image isn't usable until it's embedded** (gallery retrieval + dedup need the
   DINOv2 vector). Scrape → ingest → **Colab embed batch**.
4. **The credential signups are the real volume unlock** — a Reddit script-app + a
   SerpApi/CSE key (5 min each) open the two biggest fresh painted-mini firehoses; the
   scrapers already exist. Until then, no-cred reliable = warhammer_community + dakka(bounded).

## C4. Operational practicalities (not legal advice)
Respect rate limits and cache aggressively (never re-download); back off and rotate on the marketplaces; don't hammer GW/community/forum servers; dedupe *before* storing to save space; log failures for retry. Keep raw images + sidecar JSON immutable; do all processing on copies.

## C5. Ingest & dedup pipeline (feeds the build plan)
```
download ──▶ write sidecar JSON ──▶ FiftyOne ingest
   ──▶ pHash + embedding dedup (CROSS-SOURCE: kill retailer/GW + Pinterest re-posts)
   ──▶ SAM 3 / detector pass  → fill num_minis_est, drop junk/non-mini, flag negatives
   ──▶ heuristic realism-tier tag (num_minis + bg complexity)
   ──▶ route to pools: detection_pool (T2, multi-mini) | gallery_pool (T0/T1 single) | eval (frozen, T2)
```
Cross-source dedup is non-negotiable — retailers reuse GW photos, Pinterest/forums repost everything, and consecutive video frames are near-identical.

---

# PART D — PRIORITISED EXECUTION (ROI order)

**Wave 0 — Instant wins (hours).** Pull the Roboflow Universe Warhammer + miniature/figurine/negative datasets; scrape warhammer.com + Warhammer Community for the **canonical T0 gallery with exact labels**; re-ingest your existing corpus under the new metadata schema. → Baseline + the cleanest labels you'll get.

**Wave 1 — Per-unit depth (the lever).** Run the **query-by-taxonomy engine** across Google (SerpApi/CSE), Reddit faction subs + r/minipainting, Instagram hashtags, CMON, Putty&Paint, and commission-painter portfolios — **for the v1 factions only**. Reverse-image-expand thin units. Target **≥5 images/unit** across ≥3 schemes for every supported unit.

**Wave 2 — Deployment realism (the gap).** Extract frames from battle-report channels (Tabletop Tactics, MWG, Play On Tabletop, etc.); **shoot your own table**; capture FLGS/tournament scenes with permission. Target several hundred **T2** multi-mini scenes. This is also your frozen eval set.

**Wave 3 — Volume + finish-state variety.** Marketplaces at scale: eBay sold listings + Kleinanzeigen + Ricardo/Tutti + Vinted + r/miniswap. Harvests primed/bare/painted variety and pads the long tail.

**Wave 4 — Negatives + Tier-1 generalisation.** Proxy/3D-print sources + other-brand minis + **copy-paste synthetic** cluttered scenes. Strengthens detection and unknown-rejection.

**Ongoing.** Incremental scrape + dedupe; depth tracker drives where effort goes; periodically **promote** CC/own/official-permitted images to `product_safe = true`.

---

# Legality note (deferred, not skipped)
Everything is ingested `product_safe = false` with full provenance, so the product-safe subset — **your own photos + CC-licensed Flickr/Roboflow-CC + anything GW explicitly permits** — can be filtered out later with a single query, no re-collection. Two separate things must be cleared before any public ship: (1) licensing of the *training images* themselves, and (2) commercially recognising GW's trademarked IP. The metadata schema in §A8 is exactly what lets you defer that decision without it becoming a redo. (Same IP point flagged in the architecture review — it doesn't block research, it blocks launch.)

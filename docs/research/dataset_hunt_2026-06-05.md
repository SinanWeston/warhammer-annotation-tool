# Dataset hunt — pre-existing WH40K miniature CV data

**Date:** 2026-06-05 · **Method:** deep-research harness (6 angles, 18 sources fetched,
43 claims extracted, 3-vote adversarial verification → 6 surviving findings) · **Scope:**
everything (hubs, academic, code, 3D/synthetic, adjacent-transfer), both licenses split.

## Bottom line

**No shortcut dataset exists.** Across HuggingFace, Roboflow Universe, Kaggle, and arXiv,
the only real WH40K *image* datasets are the **two tiny Roboflow sets the team already
has** — and neither aligns with our taxonomy (Necrons + Tyranids entirely absent). Academic
WH40K CV is still **greenfield**. The one large asset pool is **Cults3D (~10.9k tagged
STLs)** for *synthetic* rendering, but it is **not cleanly commercial-safe** and sits under
**Games Workshop IP** regardless of per-asset license. **The team's own scraping + synthetic
effort is justified — there is no dataset to buy our way out of the work.**

## Ranked findings (all verified unless noted)

| # | Source | Type | Size | License | Faction coverage | Commercial? | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | [Roboflow · Puopolo](https://universe.roboflow.com/davide-puopolo-9xomj/warhammer-40.000-miniature) | detection bbox | **97 img / 6 classes** | **CC BY 4.0** ✓ | SM + Death Guard only; **no Necron/Tyranid** | ✅ yes (w/ attribution) | Already have it. Classes are ad-hoc (base/wargear/unit mix), not faction/unit taxonomy. Marginal. |
| 2 | [Roboflow · Kruger](https://universe.roboflow.com/jonas-krger/warhammer-40k-minins) | detection bbox | **35 img / 2 classes** | *unconfirmed* (NOT verified CC BY) | Hearthkyn + Primaris only | ❓ unknown | Already have it. Tiny. |
| 3 | [Cults3D `warhammer_40k`](https://cults3d.com/en/tags/warhammer_40k) | **3D STL/OBJ** | ~10.9k tagged files* | per-model, **default non-commercial** | broad (unverified per-faction) | ❌ not clean + **GW IP** | The one large pool — for **synthetic rendering only**. See caveats. |
| 4 | [Chess pieces](https://public.roboflow.com/object-detection/chess-full) | detection bbox | 292 img / 2,894 boxes | **CC0** ✓ | n/a (chess) | ✅ yes | Transfer to minis **refuted** — chess ≠ painted multi-part minis. Skip. |
| — | HuggingFace / Kaggle / arXiv | — | — | — | — | — | **Nothing.** All WH40K hits are lore-text, game-stats, or SD LoRAs. Not vision datasets. |

\* "~10.9k" is an **unfiltered keyword aggregate** (includes terrain / bits / bases), **not**
10,900 distinct printable miniatures. Per-faction subtag counts could not be verified.

## "Ingest now" shortlist

**Commercial-safe:**
- *(nothing new)* — Puopolo (97 img, CC BY 4.0) is the only commercial-safe WH40K image set
  and we already have it. The CC0 chess set is commercial-safe but its transfer value to
  miniatures was **refuted** — not worth ingesting.

**Research-only (offline training / pseudo-label use):**
- **Cults3D STLs → BlenderProc synthetic** — the only meaningful new asset, and only as a
  *synthetic-render source*, not a redistributable dataset. Validated approach (peer-reviewed
  domain-randomization work trains real-object detectors from renders), but gated on the
  legal caveat below and on filtering ~10.9k tagged files down to distinct minis.

## Gaps — what genuinely does not exist (justifies our own effort)

- **No faction-labeled WH40K dataset.** Nothing maps to a ~20-class faction scheme.
- **No unit-labeled WH40K dataset.** Nothing approaches the ~900-unit tier.
- **No real-tabletop detection dataset at scale.** The 97+35 images are studio-ish and tiny.
- **No Necron or Tyranid labeled data anywhere.** Two of our four v1 factions have *zero*
  pre-existing coverage.
- **No academic WH40K CV work** (greenfield confirmed — caveat: proof is strong but not
  exhaustive).
- **No usable generic-miniature transfer set** — chess is the closest and it doesn't transfer.

## Refuted / corrected during verification (don't repeat these)

- ❌ "Both Roboflow sets are CC BY 4.0" → **only Puopolo** is confirmed CC BY 4.0; Kruger's
  license is unconfirmed.
- ❌ "Synthetic augmentation reaches 99% mAP" → overreach, killed.
- ❌ "Cults3D has necron ~1.2k / tyranid 622 subtags" → unverified, killed.
- ❌ "Chess game-piece boxes transfer to WH40K minis" → killed (visually unlike).

## ⚠️ The binding legal question (out of scope of the search, flagged for you)

Every WH40K 3D model and image depicts **Games Workshop IP**. GW's copyright/trademark is a
**separate risk layer on top of** any per-asset CC/CC0/Cults license — none of the
"commercial-safe" flags above clear the GW-IP question. For a *commercial* product this is
the real constraint; for *offline* training/pseudo-labeling (our actual use of these assets)
it's lower-risk, consistent with STRATEGY's license stack (gated models OK offline, ship only
Apache-2.0 weights). **Decision for you, not the search.**

## Open questions worth a follow-up (if we pursue synthetic)

- Actual Cults3D per-faction counts + distinct-mini vs terrain/bits ratio (needs API/rendered
  page) — determines real Necron/Tyranid synthetic coverage.
- **Commercial STL studios** the search didn't individually verify — MyMiniFactory Tribes,
  Patreon studios (Titan Forge, Artisan Guild) offering *proxy* 40K-style units with explicit
  render/derivative rights. These could be a cleaner synthetic source than Cults3D's
  GW-IP-laden meshes.

## Sources (18 fetched)
Roboflow Universe (Puopolo, Kruger), public.roboflow.com/chess-full, HuggingFace Datasets
API (warhammer, miniature), Kaggle (cjblue83 model-stats), arXiv cs.CV listings,
arXiv:2509.25644 + 2509.15045 (synthetic-render validation), Cults3D tag + license pages,
creativecommons.org (CC BY 4.0 / CC0 terms).

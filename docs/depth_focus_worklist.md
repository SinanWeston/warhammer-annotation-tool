# Phase 3a.1 — depth-focus worklist

Generated from `scripts/phase3/labels.csv` (target gallery depth = 3).

**26 target unit(s) across 13 faction(s) — 42 bbox(es) to label.**

Each bbox below means: find an image in the corpus that contains an instance of this unit, draw a tight bbox around it, and set `unit_slug` to the listed slug. Re-run `extract_from_corpus.py → auto_split.py → build_gallery.py → embed_gallery.py → eval_scoped_retrieval.py` after the sprint to see the lift.

Reference crops are the existing gallery exemplar(s) — open the paths in any image viewer to eyeball what the unit looks like, then go hunting in the annotator with the matching faction filter set.

---

## Faction routing

| Faction | Units | Bboxes | Suggested annotator filter |
|---|---:|---:|---|
| chaos_daemons | 4 | 6 | `faction=chaos_daemons` + status=Pending |
| aeldari | 2 | 4 | `faction=aeldari` + status=Pending |
| astra_militarum | 3 | 4 | `faction=astra_militarum` + status=Pending |
| harlequins | 3 | 4 | `faction=harlequins` + status=Pending |
| orks | 2 | 4 | `faction=orks` + status=Pending |
| space_marines | 2 | 4 | `faction=space_marines` + status=Pending |
| ynnari | 2 | 4 | `faction=ynnari` + status=Pending |
| chaos_space_marines | 2 | 3 | `faction=chaos_space_marines` + status=Pending |
| tau_empire | 2 | 3 | `faction=tau_empire` + status=Pending |
| drukhari | 1 | 2 | `faction=drukhari` + status=Pending |
| tyranids | 1 | 2 | `faction=tyranids` + status=Pending |
| adeptus_mechanicus | 1 | 1 | `faction=adeptus_mechanicus` + status=Pending |
| necrons | 1 | 1 | `faction=necrons` + status=Pending |

---

## adeptus_mechanicus — 1 unit(s), 1 bbox(es)

### `tech_priest`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/adeptus_mechanicus/18972_70bd55985ed8__00.jpg`
  - `scripts/phase3/crops/adeptus_mechanicus/19665_5cd02e2bf5a5__02.jpg`

---

## aeldari — 2 unit(s), 4 bbox(es)

### `shining_spears`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/eldar/120212_39f0e76af687__01.jpg`

### `wraithguard`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/eldar/138026_dd546ecdb510__00.jpg`

---

## astra_militarum — 3 unit(s), 4 bbox(es)

### `kasrkin`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/imperial_guard/12gas6q_e2afd66dbaec__09.jpg`

### `armoured_sentinel`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/imperial_guard/1051t49_234b4ed96c1a__00.jpg`
  - `scripts/phase3/crops/imperial_guard/12fouwo_1c5512305f35__01.jpg`

### `death_korps_of_krieg`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/imperial_guard/11t2alq_15adda0a7fce__03.jpg`
  - `scripts/phase3/crops/imperial_guard/11t2alq_15adda0a7fce__05.jpg`

---

## chaos_daemons — 4 unit(s), 6 bbox(es)

### `daemonettes`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/chaos_daemons/dakka_1028257__00.jpg`

### `great_unclean_one`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/chaos_daemons/dakka_155472__00.jpg`

### `bloodthirster`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/chaos_daemons/1cmdxlw_15517a2bac3b__00.jpg`
  - `scripts/phase3/crops/chaos_daemons/1cmdxlw_94e9127ff1a5__00.jpg`

### `daemon_prince`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/chaos_daemons/dakka_1217981__01.jpg`
  - `scripts/phase3/crops/chaos_daemons/dakka_138190__00.jpg`

---

## chaos_space_marines — 2 unit(s), 3 bbox(es)

### `exalted_sorcerer`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/thousand_sons/146088_874f7d3cf742__00.jpg`

### `rubric_marines`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 2  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase1/crops/chaos_space_marines/13164_2ebfe221cced__00.jpg`
  - `scripts/phase3/crops/thousand_sons/13164_2ebfe221cced__01.jpg`

---

## drukhari — 1 unit(s), 2 bbox(es)

### `drukhari_warriors`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/drukhari/10655_89682d0e5a24__05.jpg`

---

## harlequins — 3 unit(s), 4 bbox(es)

### `shadowseer`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/harlequins/dakka_1116770__00.jpg`

### `death_jester`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/harlequins/dakka_1116781__01.jpg`
  - `scripts/phase3/crops/harlequins/dakka_115952__00.jpg`

### `solitaire`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/harlequins/dakka_1116780__02.jpg`
  - `scripts/phase3/crops/harlequins/dakka_1116781__00.jpg`

---

## necrons — 1 unit(s), 1 bbox(es)

### `canoptek_wraiths`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/necrons/11xiqtl_e4d4a2329d65__00.jpg`
  - `scripts/phase3/crops/necrons/128ijpx_4ca827421e5d__33.jpg`

---

## orks — 2 unit(s), 4 bbox(es)

### `boyz`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/orks/106422_32a253181cce__05.jpg`

### `warboss`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/orks/11332_bbff314e5c4a__00.jpg`

---

## space_marines — 2 unit(s), 4 bbox(es)

### `chaplain`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/deathwatch/1fkh5cg_269a1cea45dc__11.jpg`

### `cypher`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/deathwatch/1fkh5cg_269a1cea45dc__10.jpg`

---

## tau_empire — 2 unit(s), 3 bbox(es)

### `riptide_battlesuit`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/tau_empire/dakka_1051131__00.jpg`

### `ghostkeel_battlesuit`   🟧 NEAR-TARGET (depth=2 → +1)

- Current gallery depth: **2**  ·  query crops: 1  ·  **bboxes needed: 1**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/tau_empire/dakka_1075399__00.jpg`
  - `scripts/phase3/crops/tau_empire/dakka_1171063__00.jpg`

---

## tyranids — 1 unit(s), 2 bbox(es)

### `gargoyles`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/tyranids/12chle6_1b9e5bbdf7aa__08.jpg`

---

## ynnari — 2 unit(s), 4 bbox(es)

### `falcon`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/ynnari/12ljebr_0126d16dabec__00.jpg`

### `guardian_defenders`   🟥 SINGLETON (depth=1 → +2)

- Current gallery depth: **1**  ·  query crops: 1  ·  **bboxes needed: 2**
- Reference crop(s) — open to see the unit:
  - `scripts/phase3/crops/ynnari/12k8x12_65d4aab31663__09.jpg`

---

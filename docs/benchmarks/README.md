# Benchmarks

Canonical record of CV model evaluations. Every phase gate in `../../STRATEGY.md` produces at least one entry here.

## Naming

`YYYY-MM-DD-<short-slug>.md` — date of the run, not the commit. Multiple runs on the same day append a short disambiguator (`-b`, `-c`).

## What a benchmark entry contains

See `.claude/agents/bench-runner.md` for the full template. Headline:

1. **Setup** — model path, threshold, eval set, commit SHA.
2. **Metrics** — the canonical KPI set from STRATEGY.md §8: faction top-1, unit top-1/top-3, "unknown" recall, detection recall@IoU0.5. Not every KPI applies to every model; mark N/A explicitly.
3. **Delta vs previous baseline** — numbers are useless without comparison.
4. **Qualitative notes** — failure modes, surprises.
5. **Reproduction command** — exact CLI.

## What goes here vs elsewhere

- **Here**: one file per evaluation run. Lives forever.
- **`../../STRATEGY.md` Status table**: updated only when an evaluation closes a phase's exit criteria.
- **Training run artefacts** (`runs/<name>/`): not versioned; local to the machine that trained. Benchmarks reference a training run by its weights path + date.

## Current baselines

Populated in order as phases close their exit criteria.

| Date | Model / config | Phase | File |
|---|---|---|---|
| 2026-04-13 | YOLO11x Run 2 (15-class faction detector) | Phase 0 | `2026-04-13-phase0-baseline.md` |
| 2026-04-13 | OWLv2 + DINOv2-base retrieval | Phase 1 | `2026-04-13-phase1-prototype.md` |
| 2026-04-14 | OWLv2 + DINOv2-base + Tier 2 KNN-vote + gating sweep | Phase 2 | `2026-04-14-phase2-scoped.md` |

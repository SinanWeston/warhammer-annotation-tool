---
name: bench
description: Run or review model benchmarks per STRATEGY.md §8. Invokes the bench-runner agent for actual runs; without args, lists past benchmarks.
argument-hint: "[model-name | list]"
---

Run or review CV model benchmarks for the Warhammer 40K project.

## No arguments → list past benchmarks

1. List files in `docs/benchmarks/` (may not exist yet — create it if missing).
2. Show each with date, model name, phase, and the three headline metrics (faction top-1, unit top-1, unit top-3).
3. Flag any phase that doesn't yet have a benchmark but should per STRATEGY.md Status table.

## With a model argument → delegate to `bench-runner` agent

Use the `bench-runner` subagent (see `.claude/agents/bench-runner.md`) to execute the run and record results. Pass through the model name / weights path as context.

## Notes

- Don't invent metrics — use the exact KPI set from STRATEGY.md §8.
- Don't run training here. Benchmarks are eval-only.
- If `yolo_env/bin/python3` isn't available, tell the user to set up the venv before running.

$ARGUMENTS

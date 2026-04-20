# Phase C — Frozen scene benchmark

**Do not train on these images.** Every model evaluation (detection mAP, faction top-1, unit top-3) is scored against this set. If you retrain and these image IDs end up in the training split, every downstream number is meaningless.

The manifest (`eval_200.json`) is the source of truth — pin against its `imageId` list, not filesystem globs.

See `STRATEGY.md` §3.1 step 1 and the Phase C row in the Status table for context.

## Generated summary

```
Total: 200  (seed=42)

By bucket:
  single    60  (target 60)
  sparse    50  (target 50)
  medium    50  (target 50)
  crowded   40  (target 40)

By source:
  dakkadakka   136
  reddit        59
  cmon           5

Bucket × source:
  single   dakkadakka=41, reddit=17, cmon=2
  sparse   dakkadakka=37, reddit=11, cmon=2
  medium   dakkadakka=36, reddit=13, cmon=1
  crowded  dakkadakka=22, reddit=18

Factions covered: 22
Top 5: custodes=19, eldar=18, tyranids=18, chaos_space_marines=14, adeptus_mechanicus=13
```

## Regenerating

Rerun `yolo_env/bin/python scripts/phaseC/freeze_eval_set.py`. Output is deterministic (seed=42) — re-running will not change the list unless the underlying annotation corpus gains or loses images in the sampled buckets. If that happens intentionally (e.g., new crowded images annotated), bump the `version` field and publish a migration note.

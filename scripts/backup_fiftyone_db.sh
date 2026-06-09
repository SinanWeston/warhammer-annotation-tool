#!/usr/bin/env bash
# Snapshot FiftyOne's MongoDB (the wh40k_pile curation state) to pCloud.
# The DB is NOT in git and is otherwise unrecoverable without a full re-ingest
# + re-embed (Colab GPU days). Run weekly via cron, or manually before risky
# curation work.
#
#   bash scripts/backup_fiftyone_db.sh
set -euo pipefail

DB_DIR="$HOME/.fiftyone/var/lib/mongo"
DEST_DIR="$HOME/pCloudDrive/10-19 Projects/15 Photoanalyzer/backups"
KEEP=4

if pgrep -x mongod >/dev/null; then
  echo "mongod is running (FiftyOne session open) — refusing to copy live"
  echo "WiredTiger files. Close the FiftyOne app/session and re-run." >&2
  exit 1
fi

[ -d "$DB_DIR" ] || { echo "no FiftyOne DB at $DB_DIR" >&2; exit 1; }
mountpoint -q "$HOME/pCloudDrive" 2>/dev/null || [ -d "$HOME/pCloudDrive/10-19 Projects" ] \
  || { echo "pCloudDrive not mounted" >&2; exit 1; }

mkdir -p "$DEST_DIR"
STAMP=$(date +%Y-%m-%d)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# Stage locally first — tar straight onto the pCloud FUSE mount is slow/fragile.
tar -czf "$STAGE/fiftyone_mongo_$STAMP.tar.gz" -C "$(dirname "$DB_DIR")" "$(basename "$DB_DIR")"
mv "$STAGE/fiftyone_mongo_$STAMP.tar.gz" "$DEST_DIR/"
echo "wrote $DEST_DIR/fiftyone_mongo_$STAMP.tar.gz ($(du -h "$DEST_DIR/fiftyone_mongo_$STAMP.tar.gz" | cut -f1))"

# Keep only the newest $KEEP snapshots.
ls -1t "$DEST_DIR"/fiftyone_mongo_*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$old" && echo "pruned $old"
done

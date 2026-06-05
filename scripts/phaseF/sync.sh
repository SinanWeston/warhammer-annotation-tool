#!/usr/bin/env bash
# Phase F1 Drive sync helper. Push the bundle up, trigger Colab manually
# (browser), pull results down. Replaces the drag-and-drop dance.
#
# One-time setup (do once, ever):
#   rclone config
#     n              # new remote
#     gdrive         # name (must match RCLONE_REMOTE below)
#     <pick> drive   # Google Drive
#     <enter>        # client_id (blank → use rclone's shared one)
#     <enter>        # client_secret (blank)
#     scope: 1       # full access
#     <enter>        # service_account_file (blank)
#     edit advanced: n
#     auto config: y → opens browser, OAuth, done
#     team drive: n
#     y to confirm, q to quit
#
# Then any time:
#   bash scripts/phaseF/sync.sh push    # upload bundle, clear stale outputs
#   <click Run All in Colab>
#   bash scripts/phaseF/sync.sh pull    # download + extract + show report
#
# Or in one go after Colab finishes:
#   bash scripts/phaseF/sync.sh roundtrip  # push → wait for you → pull
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# yolo_env was retired (2026-05); the active env is fiftyone_env. Both python and
# rclone are overridable. rclone is a standalone binary — install it (system or
# `fiftyone_env/bin/pip install`-style) since it no longer ships in any env here.
PYBIN="${PYBIN:-$REPO_ROOT/fiftyone_env/bin/python}"
RCLONE="${RCLONE:-$(command -v rclone || echo "$REPO_ROOT/fiftyone_env/bin/rclone")}"
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"     # remote name from `rclone config`
DRIVE_DIR="${DRIVE_DIR:-}"                   # optional subfolder under MyDrive
BUNDLE_PATH="$HOME/Downloads/photoanalyzer_f1_bundle.tar"
NOTEBOOK_PATH="$REPO_ROOT/scripts/phaseF/autolabel_colab.ipynb"
OUTPUTS_LOCAL="$HOME/Downloads/f1_outputs.tar"
DRIVE_OUTPUTS="${DRIVE_DIR:+$DRIVE_DIR/}f1_outputs.tar"
DRIVE_BUNDLE="${DRIVE_DIR:+$DRIVE_DIR/}photoanalyzer_f1_bundle.tar"
DRIVE_NOTEBOOK="${DRIVE_DIR:+$DRIVE_DIR/}autolabel_colab.ipynb"

cmd="${1:-help}"

require_remote() {
    if ! "$RCLONE" listremotes | grep -q "^${RCLONE_REMOTE}:"; then
        echo "rclone remote '${RCLONE_REMOTE}' not configured." >&2
        echo "Run: rclone config  (install rclone first; it no longer ships in any env)" >&2
        echo "(see scripts/phaseF/sync.sh header for the steps)" >&2
        exit 1
    fi
}

case "$cmd" in
    push)
        require_remote
        if [[ ! -f "$BUNDLE_PATH" ]]; then
            echo "Bundle missing at $BUNDLE_PATH"
            echo "Build it first: $PYBIN scripts/phaseF/prepare_colab_bundle.py --phase-c --phase-c-limit 50"
            exit 1
        fi
        echo "==> Deleting stale outputs from Drive (so Colab cell 11 sees a clean slate)"
        "$RCLONE" delete --quiet "${RCLONE_REMOTE}:${DRIVE_OUTPUTS}" 2>/dev/null || true
        echo "==> Uploading bundle ($(du -h "$BUNDLE_PATH" | cut -f1))"
        "$RCLONE" copy --progress "$BUNDLE_PATH" "${RCLONE_REMOTE}:${DRIVE_DIR:-/}"
        echo "==> Uploading notebook"
        "$RCLONE" copy --progress "$NOTEBOOK_PATH" "${RCLONE_REMOTE}:${DRIVE_DIR:-/}"
        echo
        echo "Drive contents now:"
        "$RCLONE" ls "${RCLONE_REMOTE}:${DRIVE_DIR:-/}" --max-depth 1 | head -10
        echo
        echo "Next: open the notebook in Colab (Drive → right-click → Open with Colab)"
        echo "      → Runtime → Run all"
        echo "      → when finished, run: bash scripts/phaseF/sync.sh pull"
        ;;

    pull)
        require_remote
        echo "==> Checking for f1_outputs.tar on Drive"
        if ! "$RCLONE" lsf "${RCLONE_REMOTE}:${DRIVE_OUTPUTS}" 2>/dev/null | grep -q f1_outputs.tar; then
            echo "f1_outputs.tar not on Drive yet. Has the Colab run finished?"
            exit 1
        fi
        echo "==> Downloading"
        rm -f "$OUTPUTS_LOCAL"
        "$RCLONE" copy --progress "${RCLONE_REMOTE}:${DRIVE_OUTPUTS}" "$HOME/Downloads/"
        echo "==> Extracting into repo root"
        cd "$REPO_ROOT"
        tar -xf "$OUTPUTS_LOCAL"
        echo
        latest_md=$(ls -t docs/benchmarks/*.md 2>/dev/null | head -1 || true)
        if [[ -n "$latest_md" ]]; then
            echo "==> Bench report: $latest_md"
            echo
            cat "$latest_md"
        else
            echo "No markdown report in outputs — extracted to data/pseudo_labels/"
            ls data/pseudo_labels/ | head
        fi
        ;;

    roundtrip)
        bash "$0" push
        echo
        echo "Now click Run All in Colab. Press Enter here when the run is done."
        read -r
        bash "$0" pull
        ;;

    full)
        # End-to-end: build a fresh Phase C bundle, push, watch for outputs,
        # auto-pull + extract + show the report. One command per bench run.
        # Optional first arg: number of images (default 50).
        require_remote
        N="${2:-50}"
        echo "==> [1/4] Building Phase C bundle (limit=${N})"
        rm -f "$BUNDLE_PATH"
        cd "$REPO_ROOT"
        "$PYBIN" scripts/phaseF/prepare_colab_bundle.py \
            --phase-c --phase-c-limit "$N" 2>&1 | tail -3
        if [[ ! -f "$BUNDLE_PATH" ]]; then
            echo "Bundle build failed."
            exit 1
        fi

        echo
        echo "==> [2/4] Pushing to Drive (clears stale outputs)"
        bash "$0" push

        echo
        echo "==> [3/4] Open the notebook in Colab and click Runtime → Run all."
        echo "         I'll watch Drive and pull as soon as f1_outputs.tar appears."
        echo "         (Polling every 30s. Ctrl-C to abort if you change your mind.)"
        echo

        start=$(date +%s)
        last_log=$start
        while true; do
            if "$RCLONE" lsf "${RCLONE_REMOTE}:${DRIVE_OUTPUTS}" 2>/dev/null | grep -q f1_outputs.tar; then
                break
            fi
            now=$(date +%s)
            if (( now - last_log >= 60 )); then
                mins=$(( (now - start) / 60 ))
                echo "  still waiting (${mins} min elapsed) — Run All in Colab if you haven't yet"
                last_log=$now
            fi
            # Bail out after 2 hours to avoid spinning forever on a forgotten run.
            if (( now - start >= 7200 )); then
                echo "  timed out after 2 hours. Run \`bash scripts/phaseF/sync.sh pull\` manually."
                exit 1
            fi
            sleep 30
        done
        echo "==> [4/4] Outputs detected on Drive — pulling now"
        bash "$0" pull
        ;;

    status)
        require_remote
        echo "==> Drive contents at remote root:"
        "$RCLONE" ls "${RCLONE_REMOTE}:${DRIVE_DIR:-/}" --max-depth 1
        ;;

    help|--help|-h|*)
        cat <<EOF
Phase F1 Drive sync — replaces drag-and-drop file shuffling.

Usage:
    bash scripts/phaseF/sync.sh full [N]    # build + push + auto-watch + pull. ONE COMMAND.
                                            # N = images (default 50)
    bash scripts/phaseF/sync.sh push        # bundle + notebook → Drive (clears stale outputs)
    bash scripts/phaseF/sync.sh pull        # outputs → local + extract + show report
    bash scripts/phaseF/sync.sh roundtrip   # push, wait for you to press Enter, pull
    bash scripts/phaseF/sync.sh status      # what's on Drive

Typical flow:
    bash scripts/phaseF/sync.sh full 50
    # ↳ builds bundle, pushes to Drive, prints a "click Run All" reminder,
    #   then polls Drive until outputs appear, pulls, extracts, shows report.

One-time: install rclone, run \`rclone config\` and set up a remote named \`gdrive\`.
See the header comment of this script for OAuth steps.
EOF
        ;;
esac

#!/bin/bash
# Status line — shows branch, strategy phase, dirty count, context budget.
# Reads JSON from stdin (session/model/context_window/cost info).

INPUT=$(cat)
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

BRANCH=$(git branch --show-current 2>/dev/null)
DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
CTX_PCT=$(echo "$INPUT" | jq -r '.context_window.used_percentage // empty' 2>/dev/null)

# Parse current strategy phase name only (not the full description).
PHASE=""
if [[ -f STRATEGY.md ]]; then
  PHASE=$(awk -F'|' '
    /^\| [0-9] · / {
      status = $3
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", status)
      if (status !~ /Not started|Deferred/) {
        name = $2
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
        sub(/^[0-9]+ · /, "", name)
        print name
        exit
      }
    }
  ' STRATEGY.md)
fi
[[ -z "$PHASE" ]] && PHASE="Phase 0"

# Compose. Keep short; status lines get truncated.
PARTS=()
[[ -n "$BRANCH" ]] && PARTS+=("⎇ $BRANCH")
PARTS+=("◈ $PHASE")
[[ "$DIRTY" -gt 0 ]] && PARTS+=("●$DIRTY")
[[ -n "$CTX_PCT" ]] && PARTS+=("$(printf '%.0f%%' "$CTX_PCT")ctx")

IFS=' · ' ; echo "${PARTS[*]}"

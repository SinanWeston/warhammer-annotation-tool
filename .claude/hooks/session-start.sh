#!/bin/bash
# SessionStart — prints a compact project snapshot so Claude has current
# context without having to re-read the repo. Silent on empty / missing data.
#
# Output goes to stdout as additionalContext via JSON so Claude sees it.

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

BRANCH=$(git branch --show-current 2>/dev/null || echo "?")
COMMITS_AHEAD=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo 0)
DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
LAST_COMMIT=$(git log -1 --format='%h %s' 2>/dev/null || echo "?")

# Extract current strategy phase from STRATEGY.md status table.
# Looks for the first row whose status cell isn't "☐ Not started" or "☐ Deferred".
PHASE="not started"
if [[ -f STRATEGY.md ]]; then
  # First row starting with `| N ·` where the status is not "Not started"/"Deferred".
  CURRENT=$(awk -F'|' '
    /^\| [0-9] · / {
      status = $3
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", status)
      if (status !~ /Not started|Deferred/) {
        name = $2
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
        print name " — " status
        exit
      }
    }
  ' STRATEGY.md)
  [[ -n "$CURRENT" ]] && PHASE="$CURRENT"
fi

# Annotation progress (cheap check).
ANN_COUNT=0
if [[ -d backend/training_data_annotations ]]; then
  ANN_COUNT=$(find backend/training_data_annotations -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
fi

# Emit as additionalContext so Claude reads it as part of session start.
CONTEXT=$(cat <<EOF
## Project snapshot (SessionStart hook)

- **Branch**: \`$BRANCH\` (${COMMITS_AHEAD} ahead, ${DIRTY} dirty file(s))
- **Last commit**: $LAST_COMMIT
- **Strategy phase**: $PHASE
- **Annotations on disk**: $ANN_COUNT JSON files

Consult \`STRATEGY.md\` before proposing modelling changes. Consult \`TODO.md\` for
tiered task list. Consult \`SPEC.md\` for architecture.
EOF
)

jq -n --arg ctx "$CONTEXT" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'

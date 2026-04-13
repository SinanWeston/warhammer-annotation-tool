#!/bin/bash
# PostToolUse(Edit|Write) — when a .ts / .tsx file is edited, typecheck
# just that workspace (backend/frontend/consumer/annotator-mobile).
# Non-blocking: errors surface as additionalContext; won't veto the edit.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Bail quickly if not TS/TSX.
[[ "$FILE_PATH" =~ \.(ts|tsx)$ ]] || { echo "{}"; exit 0; }

# Figure out which workspace the file lives in.
WORKSPACE=""
case "$FILE_PATH" in
  */backend/*)          WORKSPACE="backend" ;;
  */frontend/*)         WORKSPACE="frontend" ;;
  */consumer/*)         WORKSPACE="consumer" ;;
  */annotator-mobile/*) WORKSPACE="annotator-mobile" ;;
  *) echo "{}"; exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}/$WORKSPACE" || { echo "{}"; exit 0; }

# Typecheck with a hard timeout so a stuck compiler never blocks Claude.
ERRORS=$(timeout 30s npx tsc --noEmit 2>&1 | head -20)

if [[ -z "$ERRORS" ]]; then
  echo "{}"
  exit 0
fi

# Emit as additionalContext so Claude sees the errors and can react.
jq -n --arg workspace "$WORKSPACE" --arg errors "$ERRORS" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: ("TypeScript errors in " + $workspace + ":\n```\n" + $errors + "\n```")
  }
}'

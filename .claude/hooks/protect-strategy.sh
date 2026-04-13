#!/bin/bash
# PreToolUse(Edit|Write) — flag modifications to STRATEGY.md so Claude
# pauses to reason about whether the edit is a deliberate strategy update
# vs drift. Non-blocking: adds a notice, doesn't veto.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

case "$FILE_PATH" in
  */STRATEGY.md|STRATEGY.md)
    jq -n '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "allow",
        additionalContext: "⚠ STRATEGY.md edit. This is the guiding-star document. Ensure the change is a deliberate strategy update, not drift — if it contradicts the existing direction, flag explicitly."
      }
    }'
    ;;
  *)
    echo "{}"
    ;;
esac

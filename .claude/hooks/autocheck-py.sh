#!/bin/bash
# PostToolUse(Edit|Write) — quick syntax check on edited Python files.
# Uses py_compile (no imports executed) so it's safe for scripts that
# depend on the yolo_env venv.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

[[ "$FILE_PATH" =~ \.py$ ]] || { echo "{}"; exit 0; }
[[ -f "$FILE_PATH" ]] || { echo "{}"; exit 0; }

# Prefer the project venv if it exists (matches module versions); fall back
# to system python3.
PY="${CLAUDE_PROJECT_DIR:-.}/yolo_env/bin/python3"
[[ -x "$PY" ]] || PY="python3"

ERRORS=$("$PY" -m py_compile "$FILE_PATH" 2>&1)

if [[ -z "$ERRORS" ]]; then
  echo "{}"
  exit 0
fi

jq -n --arg file "$FILE_PATH" --arg errors "$ERRORS" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: ("Python syntax error in " + $file + ":\n```\n" + $errors + "\n```")
  }
}'

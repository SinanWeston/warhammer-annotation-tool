#!/bin/bash
INPUT=$(cat)
command=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

if echo "$command" | grep -qE 'git add (-A|\.\s*$)'; then
  echo "BLOCKED: Never use 'git add -A' or 'git add .' in photoanalyzer. Stage specific files to avoid committing ~50GB of training images." >&2
  exit 2
fi

if echo "$command" | grep -qE 'git add.*(images/|runs/|\.pt\b|\.pth\b|\.onnx\b)'; then
  echo "BLOCKED: Cannot stage training images or model files. Too large for git." >&2
  exit 2
fi

exit 0

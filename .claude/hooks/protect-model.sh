#!/bin/bash
INPUT=$(cat)
file_path=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // ""')

if echo "$file_path" | grep -qE '\.(pt|pth|onnx)$'; then
  echo "BLOCKED: Cannot modify trained model files. These are read-only artifacts." >&2
  exit 2
fi

exit 0

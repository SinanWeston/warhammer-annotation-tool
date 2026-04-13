#!/bin/bash
# PreToolUse(Bash) — blocks blanket-staging commands that could sweep in
# training images, model weights, or anything else that shouldn't be in git.
#
# IMPORTANT: parse the actual tool_input via jq rather than grepping the raw
# JSON. Grepping the raw input catches commit messages that MENTION these
# patterns as text (hit in practice on 2026-04-13).

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Split on '&&', ';', '|' and check each subcommand so that
# `echo foo && git add -A` is still caught.
IFS=$'\n' read -r -d '' -a SUBCOMMANDS < <(printf '%s' "$COMMAND" | tr '&|;' '\n' && printf '\0')

for sub in "${SUBCOMMANDS[@]}"; do
  # Trim leading/trailing whitespace.
  trimmed="$(echo -n "$sub" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')"

  # Look only at the actual git subcommand, not arguments to other programs.
  # Matches: `git add -A`, `git add --all`, `git add .`, `git add -u`
  # Does NOT match: `echo "git add -A"`, heredocs containing the text.
  if [[ "$trimmed" =~ ^git[[:space:]]+add[[:space:]]+(-A|--all|-u|\.)([[:space:]]|$) ]]; then
    echo "BLOCKED: blanket git-add detected. Stage specific files to avoid sweeping in ~50GB of training images." >&2
    echo "Command: $trimmed" >&2
    exit 2
  fi

  # Block explicit staging of big/binary paths.
  if [[ "$trimmed" =~ ^git[[:space:]]+add.*(images/|runs/|backend/training_data/|backend/yolo_dataset/|\.pt[[:space:]]|\.pth[[:space:]]|\.onnx[[:space:]]|\.safetensors[[:space:]]) ]]; then
    echo "BLOCKED: cannot stage training images / model weights. Too large for git." >&2
    echo "Command: $trimmed" >&2
    exit 2
  fi
done

exit 0

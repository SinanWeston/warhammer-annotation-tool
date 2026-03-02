#!/usr/bin/env python3
"""
Claude Code PostToolUse hook — appends every tool action to timeline.md
Receives JSON on stdin: { tool_name, tool_input, tool_response, ... }
"""
import sys
import json
from datetime import datetime

TIMELINE = '/home/sinan/Active/Projects/photoanalyzer/timeline.md'

try:
    data = json.load(sys.stdin)
    tool = data.get('tool_name', 'unknown')
    inp  = data.get('tool_input', {})

    # Build a human-readable summary of what was done
    if tool == 'Edit':
        detail = f"Edited `{inp.get('file_path', '?')}`"
    elif tool == 'Write':
        detail = f"Wrote `{inp.get('file_path', '?')}`"
    elif tool == 'Bash':
        cmd = inp.get('command', '?').strip().replace('\n', ' ')[:120]
        detail = f"Ran `{cmd}`"
    elif tool == 'Read':
        detail = f"Read `{inp.get('file_path', '?')}`"
    elif tool == 'Glob':
        detail = f"Searched for `{inp.get('pattern', '?')}`"
    elif tool == 'Grep':
        detail = f"Searched `{inp.get('pattern', '?')}` in `{inp.get('path', '.')}`"
    elif tool == 'Task':
        detail = f"Spawned agent: {inp.get('description', '?')}"
    else:
        detail = tool

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"- **{ts}** `{tool}` — {detail}\n"

    with open(TIMELINE, 'a') as f:
        f.write(line)

except Exception:
    pass  # Never block Claude on a hook failure

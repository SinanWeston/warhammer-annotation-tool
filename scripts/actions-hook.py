#!/usr/bin/env python3
"""
Claude Code PostToolUse hook — appends every tool action to ACTIONS.md
with both WHAT was done and WHY (using the description field where available).

Receives JSON on stdin: { tool_name, tool_input, tool_response, session_id, ... }
"""
import sys
import json
from datetime import datetime

PROJECT = '/home/sinan/Active/Projects/photoanalyzer'
ACTIONS = f'{PROJECT}/ACTIONS.md'

def short_path(p):
    """Strip project root from path for readability."""
    return p.replace(f'{PROJECT}/', '').replace('/home/sinan/', '~/')

try:
    data = json.load(sys.stdin)
    tool = data.get('tool_name', 'unknown')
    inp  = data.get('tool_input', {})
    ts   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    what = ''
    why  = ''

    if tool == 'Edit':
        what = f"Edited `{short_path(inp.get('file_path', '?'))}`"
        # Show a snippet of what changed
        old = (inp.get('old_string') or '').strip().replace('\n', ' ')[:60]
        new = (inp.get('new_string') or '').strip().replace('\n', ' ')[:60]
        if old or new:
            why = f"`{old}` → `{new}`" if old else f"Inserted: `{new}`"

    elif tool == 'Write':
        what = f"Wrote `{short_path(inp.get('file_path', '?'))}`"

    elif tool == 'Bash':
        cmd  = (inp.get('command') or '').strip().replace('\n', ' ')[:120]
        desc = (inp.get('description') or '').strip()
        what = f"Ran `{cmd}`"
        why  = desc  # This is Claude's explicit reasoning for the command

    elif tool == 'Read':
        what = f"Read `{short_path(inp.get('file_path', '?'))}`"

    elif tool == 'Glob':
        what = f"Searched for files matching `{inp.get('pattern', '?')}`"

    elif tool == 'Grep':
        path = inp.get('path', '.')
        what = f"Searched `{inp.get('pattern', '?')}` in `{short_path(path)}`"

    elif tool == 'Agent':
        what = f"Spawned agent: {inp.get('description', '?')}"
        prompt = (inp.get('prompt') or '')[:100].replace('\n', ' ')
        why = prompt

    elif tool == 'AskUserQuestion':
        questions = inp.get('questions', [])
        q_texts = [q.get('question', '') for q in questions]
        what = f"Asked user: {'; '.join(q_texts)[:120]}"

    else:
        what = f"`{tool}`"

    # Format the entry
    if why:
        line = f"- **{ts}** `{tool}` — {what}\n  - _Why: {why}_\n"
    else:
        line = f"- **{ts}** `{tool}` — {what}\n"

    with open(ACTIONS, 'a') as f:
        f.write(line)

except Exception:
    pass  # Never block Claude on a hook failure

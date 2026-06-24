#!/usr/bin/env python3
"""Claude Code PreToolUse hook -> CafresoHQ ApprovalTray bridge.

How it works:
  1. Claude Code invokes this script before any tool call.
  2. Script reads the hook payload (JSON on stdin) — tool name, inputs, cwd.
  3. POSTs the request to the local CafresoHQ server at /approvals/external.
  4. Long-polls /approvals/external/wait?id=... until the boss clicks
     APPROVE or REJECT in the HQ corner ApprovalTray.
  5. Prints the matching hook output JSON ("permissionDecision": allow|deny)
     and exits 0.

Wire it up in your settings.json:

  {
    "hooks": {
      "PreToolUse": [
        {
          "matcher": "*",
          "hooks": [
            { "type": "command",
              "command": "python <repo-root>/claude_approval_hook.py" }
          ]
        }
      ]
    }
  }

Env knobs:
  CAFRESOHQ_HQ_URL    base URL (default http://127.0.0.1:8787)
  CAFRESOHQ_HQ_TIMEOUT  total seconds to wait before auto-deny (default 1800)
  CAFRESOHQ_HQ_FAILOPEN if "1", allow when the HQ server is unreachable
                       (default deny — fail closed).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request


HQ_URL    = os.environ.get('CAFRESOHQ_HQ_URL', 'http://127.0.0.1:8787').rstrip('/')
TIMEOUT_S = int(os.environ.get('CAFRESOHQ_HQ_TIMEOUT', '1800'))
FAIL_OPEN = os.environ.get('CAFRESOHQ_HQ_FAILOPEN', '0') == '1'
POLL_S    = 25  # per long-poll round; server caps at 55


def _emit(decision: str, reason: str):
    """Print Claude Code's PreToolUse hook output JSON and exit."""
    out = {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': decision,        # 'allow' | 'deny' | 'ask'
            'permissionDecisionReason': reason,
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    sys.exit(0)


def _short_summary(tool: str, tool_input) -> str:
    """One-line preview of what the tool wants to do, for the tray row."""
    if not isinstance(tool_input, dict):
        return ''
    if tool == 'Bash':
        cmd = str(tool_input.get('command', ''))[:200]
        return cmd
    if tool in ('Edit', 'Write', 'NotebookEdit'):
        return str(tool_input.get('file_path', ''))[:200]
    if tool == 'Read':
        return str(tool_input.get('file_path', ''))[:200]
    if tool == 'Grep':
        return f'pattern={tool_input.get("pattern", "")!r}'[:200]
    if tool == 'Glob':
        return str(tool_input.get('pattern', ''))[:200]
    if tool == 'WebFetch':
        return str(tool_input.get('url', ''))[:200]
    # Generic fallback — show the first string-ish field.
    for k, v in tool_input.items():
        if isinstance(v, (str, int, float)):
            return f'{k}={str(v)[:160]}'
    return ''


def _post(path: str, body: dict, timeout: int = 10):
    req = urllib.request.Request(
        HQ_URL + path,
        data=json.dumps(body).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8') or '{}')


def _get(path: str, timeout: int = 60):
    req = urllib.request.Request(HQ_URL + path, method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8') or '{}')


def main():
    raw = sys.stdin.read() or '{}'
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        _emit('deny', 'approval-hook: bad input JSON')

    tool       = payload.get('tool_name') or ''
    tool_input = payload.get('tool_input') or {}
    cwd        = payload.get('cwd') or ''
    session_id = payload.get('session_id') or ''
    summary    = _short_summary(tool, tool_input)

    # Submit the request to HQ.
    try:
        sub = _post('/approvals/external', {
            'tool': tool,
            'input': tool_input,
            'cwd': cwd,
            'agent': 'claude-code',
            'sessionId': session_id,
            'summary': summary,
        })
    except (urllib.error.URLError, OSError) as e:
        if FAIL_OPEN:
            _emit('allow', f'approval-hook: HQ unreachable ({e}) — fail-open')
        _emit('deny', f'approval-hook: HQ unreachable ({e}) — fail-closed')

    aid = sub.get('id')
    if not aid:
        _emit('deny', 'approval-hook: HQ rejected submission')

    # Long-poll until decision or overall timeout.
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        try:
            res = _get(f'/approvals/external/wait?id={aid}&timeout={POLL_S}',
                       timeout=POLL_S + 10)
        except (urllib.error.URLError, OSError) as e:
            if FAIL_OPEN:
                _emit('allow', f'approval-hook: lost HQ during wait ({e})')
            _emit('deny', f'approval-hook: lost HQ during wait ({e})')
        if res.get('pending'):
            continue
        decision = res.get('decision') or 'deny'
        reason = res.get('reason') or ''
        _emit(decision if decision in ('allow', 'deny', 'ask') else 'deny',
              reason or f'boss said {decision}')

    _emit('deny', f'approval-hook: timed out after {TIMEOUT_S}s')


if __name__ == '__main__':
    main()

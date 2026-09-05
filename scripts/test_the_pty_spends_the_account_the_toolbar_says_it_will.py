#!/usr/bin/env python3
"""The PTY must honour the ⚡Subscription / 🔑API Key selector (views/terminal.jsx).

The Terminal's toolbar selector is a promise about whose money runs the
session: '⚡ Subscription' means "use the CLI's own Pro/Max (or Google)
login", '🔑 API Key' means "use my stored, metered BYOK key". It is the
default for claude and gemini, and its own tooltip says
"Using Claude Pro/Max subscription via CLI login".

Chat honoured it. claude-client.jsx's terminalStream() sends
`authMethod: 'subscription'` and withholds the key entirely, and
pty_server.py's /terminal/stream then pops ANTHROPIC_API_KEY /
GEMINI_API_KEY out of the child env so the CLI falls through to its OAuth
credentials.

The PTY tab did not. EmbeddedTerminal's `ws.onopen` built its init frame
unconditionally:

    ak = await oc.getAgentKey('anthropic').catch(() => '');
    ...
    ws.send(JSON.stringify({ type: 'init',
      ...(ak ? { anthropic_key: ak } : {}), ... }));

— no auth_method, and every stored key shipped on every connect. On the
server, pty_server.py's init handler reads
`_pty_auth = (_init_msg.get('auth_method') or '')` and only pops
ANTHROPIC_API_KEY when it equals 'subscription'; with the field never sent
that branch was unreachable dead code, and the `elif _ak and not
agent_env.get('ANTHROPIC_API_KEY')` arm ran instead. So a boss with a
stored Anthropic key who left the selector on its "⚡ Subscription"
default got ANTHROPIC_API_KEY injected into the PTY shell anyway — Claude
Code prefers the key over the OAuth login, so the in-app terminal silently
billed the metered API account while the toolbar said it was on the
subscription. Same shape for gemini via GEMINI_API_KEY/GOOGLE_API_KEY.
The control lied about which account it was spending.

Fix: EmbeddedTerminal takes the `authMethod` prop (TerminalSession already
owns and persists it), mirrors it into a ref (the selector lives in the
Chat tab while the PTY stays mounted, so the value at CONNECT time is what
counts), sends `auth_method` in the init frame, and does not fetch or ship
THIS cli's provider key when the choice is 'subscription'.

Run: python3 scripts/test_the_pty_spends_the_account_the_toolbar_says_it_will.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'terminal.jsx'
PTY = ROOT / 'pty_server.py'

failures = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        failures.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_braced(src, head_re):
    """Brace-balanced extraction from the first match of head_re (which must
    end at an opening '{') through its matching close."""
    m = re.search(head_re, src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


print('Terminal PTY — the auth selector must reach the shell env')

if not SRC.is_file():
    print(f'  FAIL  missing {SRC}')
    raise SystemExit(1)
src = SRC.read_text(encoding='utf-8')

# ── The premise: the server still has the branch that reads auth_method ──
if PTY.is_file():
    pty_src = PTY.read_text(encoding='utf-8')
    check("pty_server.py's init frame still reads auth_method",
          re.search(r"_init_msg\.get\(\s*'auth_method'\s*\)", pty_src) is not None,
          'premise changed — the server no longer honours the field')
    check("pty_server.py still strips ANTHROPIC_API_KEY on 'subscription'",
          re.search(r"_pty_auth\s*==\s*'subscription'", pty_src) is not None)

body = extract_braced(src, r'function\s+EmbeddedTerminal\s*\([^)]*\)\s*\{')
check('EmbeddedTerminal extracted from views/terminal.jsx', body is not None)
if body is None:
    print('\nFAILED: %s' % failures)
    raise SystemExit(1)

# 1. The component accepts the choice at all.
sig = re.search(r'function\s+EmbeddedTerminal\s*\(\s*\{([^}]*)\}', src)
check('EmbeddedTerminal destructures an `authMethod` prop',
      sig is not None and re.search(r'\bauthMethod\b', sig.group(1)) is not None,
      'the PTY cannot honour a choice it is never handed')

# 2. TerminalSession — which owns/persists authMethod — actually passes it.
sess = extract_braced(src, r'function\s+TerminalSession\s*\([^)]*\)\s*\{')
check('TerminalSession extracted', sess is not None)
if sess is not None:
    tag = re.search(r'<EmbeddedTerminal\b[^>]*>', sess)
    check('TerminalSession renders <EmbeddedTerminal> with authMethod={…}',
          tag is not None and re.search(r'authMethod\s*=\s*\{\s*authMethod\s*\}', tag.group(0)) is not None,
          'found: ' + (tag.group(0) if tag else '(no <EmbeddedTerminal>)'))

# 3. The init frame names the auth method.
onopen = extract_braced(body, r'ws\.onopen\s*=\s*async\s*\(\)\s*=>\s*\{')
check('ws.onopen (the init-frame builder) extracted', onopen is not None)
if onopen is None:
    print('\nFAILED: %s' % failures)
    raise SystemExit(1)

init_send = re.search(r"ws\.send\(JSON\.stringify\(\{[^;]*?'init'[^;]*?\}\)\)", onopen, re.S)
check('the init frame is still sent from ws.onopen', init_send is not None)
if init_send is not None:
    check("the init frame carries an `auth_method` field",
          re.search(r'auth_method\s*:', init_send.group(0)) is not None,
          'without it pty_server\'s subscription branch is unreachable')

# 4. The value is read from a ref, not a stale effect closure — the selector
#    lives in the Chat tab and the PTY stays mounted across the switch.
check('the auth choice is mirrored into a ref for connect time',
      re.search(r'authRef\s*=\s*React\.useRef\(', body) is not None
      and re.search(r'authRef\.current\s*=\s*authMethod', body) is not None)
check('ws.onopen reads the ref (not the captured prop)',
      re.search(r'authRef\.current', onopen) is not None)

# 5. On 'subscription', this cli's OWN provider key must not be shipped.
#    (Passing an unrelated provider's key through is harmless.)
ak = re.search(r'\bak\s*=\s*await\s+oc\.getAgentKey\(\s*[\'"]anthropic[\'"]', onopen)
gk = re.search(r'\bgk\s*=\s*await\s+oc\.getAgentKey\(\s*[\'"]google[\'"]', onopen)
check('the anthropic key fetch is still present in ws.onopen', ak is not None)
check('the google key fetch is still present in ws.onopen', gk is not None)


def guarded(m, whole, provider):
    """The fetch must sit behind a same-line/preceding condition that mentions
    both the subscription state and this cli."""
    if m is None:
        return False
    line_start = whole.rfind('\n', 0, m.start()) + 1
    prefix = whole[line_start:m.start()]
    return ('if' in prefix
            and ('_sub' in prefix or 'subscription' in prefix)
            and provider in prefix)


check("the anthropic key is NOT fetched/sent when claude is on subscription",
      guarded(ak, onopen, "'claude'") or guarded(ak, onopen, '"claude"'),
      'unconditional fetch — the subscription session still gets a metered key')
check("the gemini key is NOT fetched/sent when gemini is on subscription",
      guarded(gk, onopen, "'gemini'") or guarded(gk, onopen, '"gemini"'),
      'unconditional fetch — the subscription session still gets a metered key')

# 6. Codex (whose default is 'apikey') must keep working — the openai key
#    fetch stays unconditional.
oq = re.search(r'\bok\s*=\s*await\s+oc\.getAgentKey\(\s*[\'"]openai[\'"]', onopen)
check('the openai key is still fetched unconditionally (codex is BYOK)',
      oq is not None and not guarded(oq, onopen, "'codex'"))

print()
if failures:
    print('FAIL:')
    for f in failures:
        print(' - ' + f)
    raise SystemExit(1)
print('ALL PASS')

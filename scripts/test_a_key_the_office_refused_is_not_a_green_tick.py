#!/usr/bin/env python3
"""The tour's key step told a beginner they were ready when they were not.

The onboarding step that asks for an OpenRouter key had exactly one branch
for everything short of success, and it was worded as a success:

    setSaved(r && r.serverStored ? 'ok' : 'local');
    …
    {saved === 'local' && '✓ Key saved. (Stored in this browser — your
                            container will pick it up.)'}

`hermesSetOpenRouterKey` never throws and never returns ok:false. That is a
deliberate contract, not a defect: a non-2xx comes back as
`{ok: true, serverStored: false, detail: 'server 400: invalid OpenRouter
key'}` and an unreachable office comes back as `{ok: true, serverStored:
false, detail: 'offline — saved locally'}`. Which makes `serverStored` the
only field in the whole reply that means the key landed, and makes its
falsehood the error case — the one thing the step read it as never being.
So a truncated paste, a key with a stray space, a container that was not
answering: all three drew a green tick and the words "your container will
pick it up", when there was nothing anywhere to pick up. The `'err'` branch
sitting right below it was unreachable, because the only thing that could
have reached it was a throw.

Settings → Connections has read the same reply correctly since it was
written (`saveKey` in modals/providers.jsx: `else if (r && r.serverStored)`
… `else setProbeResult({ ok: false, detail: r.detail })`). The two surfaces
call one function and disagreed about what its answer meant, and the one
that disagreed was the one a first-time user sees first.

The second half, which the same reply already carried the evidence for.
`POST /hermes/provider` writes the key, then calls `gateway_restart` — a
best-effort `subprocess.Popen(['hermes', …])` in a try/except. On a box with
no `hermes` binary that raises, is swallowed, and comes back False, and the
handler still answers `200 {ok: true, restarted: False, note: 'gateway
reloading; allow ~10s'}`. The note is a lie in that case and the `restarted`
field beside it is the correction; nothing read it. The tester was told
they were ready, and then every message failed with "couldn't reach that
brain — it looks offline from here", a sentence that is true and names
neither Hermes, nor a gateway, nor Start-CafresoHQ.sh — the script that
would have started one.

What this pins:
- serverStored false is an error state on the tour step, not a tick.
- the server's own detail reaches the reader, so "invalid OpenRouter key"
  is a thing they can act on rather than a generic retry.
- restarted === false gets its own line, naming Hermes and the way out.
- no success copy is left reachable from a falsy serverStored.

Run: python3 scripts/test_a_key_the_office_refused_is_not_a_green_tick.py
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import (  # noqa: E402
    brace_lift, run_js, strip_comments)

ONB = ROOT / 'ui' / 'onboarding.jsx'
PROVIDERS = ROOT / 'modals' / 'providers.jsx'
CLIENT = ROOT / 'claude-client.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('a key the office refused is not a green tick')
    raw = ONB.read_text(encoding='utf-8')
    # Comments stripped first, always. The fix for this bug is explained in
    # a comment that quotes the old broken line verbatim, so every grep
    # below would otherwise find the bug in its own obituary.
    bare = strip_comments(raw)

    # ── 1. the contract this all rests on is still the contract ──────────
    client = strip_comments(CLIENT.read_text(encoding='utf-8'))
    check('the client still reports failure as ok:true + serverStored:false',
          re.search(r"return \{ ok: true, serverStored: false, detail: `server \$\{r\.status\}",
                    client),
          'if hermesSetProvider ever starts throwing or returning ok:false, '
          'this whole test is measuring the wrong field and the step should '
          'be rewritten against the new contract rather than left as is')
    check('...and the server still hands back whether it restarted',
          re.search(r"'restarted': d\['restarted'\]",
                    (ROOT / 'serve.py').read_text(encoding='utf-8')),
          'the gateway-down line below has nothing to read without it')

    # ── 2. the step reads it the way its sibling does ────────────────────
    save = brace_lift(bare, 'const save = async () =>')
    check('a falsy serverStored is the error state',
          re.search(r"if \(!\(r && r\.serverStored\)\) \{[\s\S]{0,120}setSaved\('err'\)", save),
          'this is the whole bug: it used to be the cheerful state')
    check('...and no success state is reachable from it',
          not re.search(r"r\.serverStored \? 'ok' : '\w+'", save),
          "the original `setSaved(r && r.serverStored ? 'ok' : 'local')` "
          'made every server refusal indistinguishable from a save')
    check('the server\'s own words reach the reader',
          "r.detail" in save and re.search(r'setSaveDetail', save),
          '"check the key and try again" alone hides the fact that the '
          'container said exactly what was wrong with it')
    check('a gateway that never started gets its own state',
          re.search(r"r\.restarted === false", save)
          and re.search(r"setSaved\('gw'\)", save),
          'the 200 says "gateway reloading" even when the restart threw')
    check('the sibling in Settings still reads serverStored the same way',
          re.search(r'else if \(r && r\.serverStored\)', PROVIDERS.read_text(encoding='utf-8')),
          'modals/providers.jsx is the surface this fix was modelled on; '
          'if it drifts, the two disagree again')

    # ── 3. what the reader is actually shown ─────────────────────────────
    check('the dead "stored in this browser" tick is gone',
          'your container will pick it up' not in bare,
          'nothing picks it up — the key was never sent anywhere')
    check('the gateway line names Hermes, the port and the way out',
          all(s in bare for s in ('Hermes gateway', '127.0.0.1:8642',
                                  'Start-CafresoHQ.sh')),
          '"couldn\'t reach that brain" is what the boss gets instead, and '
          'it names none of the three')
    check('...and is not coloured as a success',
          re.search(r"saved === 'gw' \? 'var\(--warn", bare),
          'the key really did save; it is a warning, not a tick and not a '
          'failure')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    # ── 4. run the real `save`, on the real replies ──────────────────────
    # Lifted verbatim from the step, with the hooks stubbed. Every reply
    # below is one the shipped client actually produces.
    cases = {
        # A key the container's regex refused. THE bug.
        'refused': {'ok': True, 'serverStored': False,
                    'detail': 'server 400: {"error": "invalid OpenRouter key"}'},
        # Browser could not reach the office at all.
        'offline': {'ok': True, 'serverStored': False,
                    'detail': 'offline — saved locally'},
        # Saved, and the gateway came up.
        'good': {'ok': True, 'serverStored': True, 'restarted': True},
        # Saved, and `hermes` is not on this box.
        'no_gateway': {'ok': True, 'serverStored': True, 'restarted': False},
        # An older container that answers without the field at all: absent
        # is not false, same rule the coworker cards follow. Claiming the
        # gateway is down because a 2023 image did not mention it would
        # send a working office to go and run a script it does not need.
        'no_field': {'ok': True, 'serverStored': True},
    }
    js = ('const useState = () => [null, () => {}];\n'
          + 'const R = {};\n'
          + 'for (const [name, reply] of Object.entries(%s)) {\n' % json.dumps(cases)
          + '  let saving = false, key = "sk-or-v1-x", state = "UNSET", det = "UNSET";\n'
            '  const setSaving = v => { saving = v; };\n'
            '  const setSaved = v => { state = v; };\n'
            '  const setSaveDetail = v => { det = v; };\n'
            '  const C = { hermesSetOpenRouterKey: async () => reply };\n'
          + save + ';\n'
            '  await save();\n'
            '  R[name] = { state, det };\n'
            '}\n'
            'console.log(JSON.stringify(R));')
    r = run_js(js)

    check('a refused key says so, in the container\'s words',
          r['refused']['state'] == 'err'
          and 'invalid OpenRouter key' in r['refused']['det'],
          f"{r['refused']} — measured before this fix as state 'local', "
          'rendering "✓ Key saved… your container will pick it up"')
    check('an unreachable office is a failure too, not a local save',
          r['offline']['state'] == 'err',
          f"{r['offline']} — the key is in this browser and nowhere else; "
          'calling that saved is the same lie with a softer cause')
    check('a key that landed on a live gateway is a tick',
          r['good']['state'] == 'ok',
          f"{r['good']} — the fix must not turn the working path red")
    check('a key that landed with no gateway behind it warns',
          r['no_gateway']['state'] == 'gw',
          f"{r['no_gateway']} — this is the tester who is told they are "
          'ready and then cannot send a single message')
    check('...and a reply that never mentions restarting is still a tick',
          r['no_field']['state'] == 'ok',
          f"{r['no_field']} — absent is not false; an older container that "
          'omits the field must not be reported as a dead gateway')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

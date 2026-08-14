#!/usr/bin/env python3
"""A CLI that ran and crashed was reported as needing a sign-in.

`probe_cli_version` spawned `<bin> --version` and returned
`stdout or stderr` without ever looking at the return code. So a CLI that
started, failed, and printed its failure had that failure recorded as its
version — and detect() is what every surface downstream reads as proof the
runtime is fine.

Measured on this machine, not imagined: the Codex shim was on PATH, its
vendored binary was gone, and

    $ codex --version ; echo $?
    Error: spawn /Users/…/@openai/codex/vendor/aarch64-apple-darwin/codex/codex ENOENT
    1

The front desk — the first screen a new user sees, before they have any
model of what this product is — offered a card reading

    Codex                                   [FOUND]
    We found your Codex subscription on this machine.
    Needs a sign-in before their first task.

under a header promising "found on this machine, ready to join". Settings
agreed: "found · needs a sign-in before its first task", "● sign in".

Every word of that is a confident diagnosis of a problem the person does
not have. They go and sign in. Signing in works. The card still says sign
in. Nothing in the office tells them the program is broken, and the north
star's "no expertise required" half means they have no way to find out.
Not knowing is honest; guessing wrong out loud is not (§7).

So: probe the return code, keep the CLI listed (a failing `--version` is
not proof `codex exec` fails, and §4's rule is that detection is a hint,
not a verdict), and say the thing that was actually observed.

Run: python3 scripts/test_a_broken_cli_says_so.py
"""
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = ROOT / 'modals' / 'hire.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def load_base():
    spec = importlib.util.spec_from_file_location(
        'hq_drivers_base', ROOT / 'drivers' / 'base.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_bin(tmp, name, body):
    p = Path(tmp) / name
    p.write_text('#!/bin/sh\n' + body + '\n', encoding='utf-8')
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


def run_js(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def lift_const(src, name):
    """The real `const <name> = …;` statement, to the semicolon that ends it
    rather than the first one inside a ternary or object. Returns '' when the
    declaration is gone, so deleting one yields a named failure instead of a
    traceback."""
    m = re.search(r'(?m)^\s*const\s+' + re.escape(name) + r'\s*=', src)
    if not m:
        return ''
    i, d, k = m.start(), 0, m.end()
    while k < len(src):
        c = src[k]
        if c in '([{':
            d += 1
        elif c in ')]}':
            d -= 1
        elif c == ';' and d == 0:
            break
        k += 1
    return src[i:k + 1].strip()


def lift_object_after(src, marker):
    """Brace-match the object literal that starts at `marker`."""
    i = src.find(marker)
    if i < 0:
        return ''
    j = src.index('{', i)
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return src[j:k + 1]


def main():
    print('a CLI that will not start has to say so, not ask for a sign-in')
    base = load_base()
    observed = []       # every `problem` a real probe actually produced

    # ── 1. the probe looks at the return code ───────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        good = fake_bin(tmp, 'goodcli', 'echo "1.2.3 (Good CLI)"')
        v, prob, det = base.probe_cli(good)
        check('a CLI that works still reports its version',
              (v, prob) == ('1.2.3 (Good CLI)', ''), (v, prob, det))

        # The measured shape: exit 1, diagnosis on stderr, nothing on stdout.
        bad = fake_bin(tmp, 'badcli',
                       'echo "Error: spawn /x/y/codex ENOENT" >&2; exit 1')
        v, prob, det = base.probe_cli(bad)
        observed.append(prob)
        check('a CLI that ran and failed reports no version',
              v == '',
              f'{v!r} — this is the whole defect: the crash text became the '
              'version, and a non-empty version is what every surface reads '
              'as "this runtime is fine"')
        check('...it reports the failure instead', prob == 'will not start',
              f'{prob!r}')
        check('...and keeps the wire text for the tooltip, not the sentence',
              det.startswith('Error: spawn') and 'ENOENT' not in prob,
              f'{det!r} / {prob!r} — §6: the person who can fix this needs '
              'something to search for, and it does not belong in the '
              'sentence a non-technical boss reads')

        # exit 0 with output on stderr is a version, not a failure: several
        # CLIs print their banner there.
        v, prob, _ = base.probe_cli(
            fake_bin(tmp, 'stderrcli', 'echo "9.9.9" >&2; exit 0'))
        check('output on stderr with a clean exit is still a version',
              (v, prob) == ('9.9.9', ''), (v, prob))

        v, prob, _ = base.probe_cli(fake_bin(tmp, 'slowcli', 'sleep 5'), timeout=1)
        observed.append(prob)
        check('a CLI that hangs is distinguished from one that crashes',
              (v, prob) == ('', 'did not respond'), (v, prob))

        v, prob, det = base.probe_cli(str(Path(tmp) / 'no-such-binary'))
        observed.append(prob)
        check('a binary that cannot be spawned at all is a failure too',
              v == '' and prob == 'will not start' and det, (v, prob, det))

    check('nothing to probe is not a failure',
          base.probe_cli('') == ('', '', ''), base.probe_cli(''))

    # ── 2. `problem` is a predicate, not a sentence ─────────────────────
    # It gets a subject and a contrast from each caller. The first draft
    # embedded both here and the front desk rendered "Codex is on this
    # machine, but it is installed but will not start". These run over what
    # the probes above actually RETURNED, not over phrases spelled out in
    # this file — a check that asserts its own literals cannot fail, which
    # is exactly what the first version of this section did.
    check('the probe produced more than one kind of failure to inspect',
          len(set(observed)) >= 2, observed)
    for phrase in sorted(set(observed)):
        sentence = f'Codex is on this machine, but it {phrase}.'
        check(f'"{phrase}" survives being conjugated into a sentence',
              phrase and not phrase.startswith('it ')
              and 'installed' not in phrase and ' but ' not in sentence[28:],
              f'{sentence!r} — two callers each supply their own subject and '
              'contrast; a string that tries to be a whole sentence stutters '
              'in at least one of them')

    # ── 3. every CLI driver carries it through detect() ─────────────────
    for name in ('claude_code', 'codex', 'gemini_cli'):
        src = (ROOT / 'drivers' / f'{name}.py').read_text(encoding='utf-8')
        check(f'{name}.detect() hands the probe result up',
              "'probeError':" in src and "'probeDetail':" in src,
              'detect() is the ONLY thing the surfaces see; a failure the '
              'driver noticed and dropped is a failure the office cannot '
              'report')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — UI checks skipped')
        return 1 if FAILS else 0

    hire = HIRE.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')

    # ── 4. the front desk stops saying "sign in" ────────────────────────
    card = lift_object_after(hire, 'return { ...def, driverId: d.id,')
    check('the front desk still builds a card for a detected runtime',
          bool(card), 'modals/hire.jsx')
    # The card object closes over `found`, which is no longer just def.found:
    # a local daemon detected across the network names its host instead of
    # claiming this machine. Lift that computation rather than stubbing the
    # variable, so this file keeps running the real card builder.
    bits = [re.search(r'const LOOPBACK = /.*?/i;', hire),
            re.search(r'const hostOf = \(u\) => \{.*?\};', hire, re.S),
            re.search(r"const host = localDaemon \? hostOf\(det\.detail\) : '';\n"
                      r'\s*const found = .*?: def\.found;', hire, re.S)]
    check('...and still chooses the found line from the detected address',
          all(bits), 'modals/hire.jsx')
    if card and all(bits):
        SCOPE = """
const def = { id:'codex', name:'Codex', role:'Engineer', cloud:false,
              found:'We found your Codex subscription on this machine.' };
const d = { id:'codex' };
const localDaemon = false;
""" + bits[0].group(0) + '\n' + bits[1].group(0) + '\n'
        FOUND = '\n' + bits[2].group(0) + '\n'
        broken = run_js(SCOPE + "const det = { installed:true, authenticated:false,"
                                " probeError:'will not start',"
                                " probeDetail:'Error: spawn /x/y ENOENT' };"
                                + FOUND +
                                f'console.log(JSON.stringify({card}));')
        check('a broken CLI is NOT diagnosed as needing a sign-in',
              broken.get('needsLogin') is False,
              'needsLogin is true — the boss is sent to a login screen for a '
              'program that cannot start, and signing in successfully will '
              'not change the card')
        check('...and the card carries what was actually observed',
              broken.get('probeError') == 'will not start'
              and 'ENOENT' in (broken.get('probeDetail') or ''), broken)

        signin = run_js(SCOPE + "const det = { installed:true, authenticated:false,"
                                " probeError:'', probeDetail:'' };"
                                + FOUND +
                                f'console.log(JSON.stringify({card}));')
        check('a CLI that works but is signed out still asks for a sign-in',
              signin.get('needsLogin') is True,
              'the fix must not swallow the real sign-in case — that is the '
              'state this copy was written for')

    note = hire[hire.find('frontdesk-note'):][:800]
    check('the note reads the probe before the stock copy',
          'c.probeError' in note and note.find('c.probeError')
          < note.find('Needs a sign-in'),
          note[:250])
    check('...and it does not promise a sign-in will help',
          'Signing in will not fix that' in note,
          'the boss has already been told the opposite by every other cue on '
          'the card; saying nothing leaves the wrong guess standing')
    check('...with the raw error one hover away',
          'title={c.probeDetail' in note, note[:250])
    check("the badge stops claiming FOUND for something that won't run",
          "WON'T START" in hire, 'modals/hire.jsx')
    check('the header stops promising the whole desk is ready to join',
          'deskCards.some(c => c.probeError)' in hire,
          '"ready to join" is a claim about every card under it')

    # ── 5. Settings tells the same story ────────────────────────────────
    lifted = '\n'.join(lift_const(settings, n)
                       for n in ('broken', 'live', 'offText'))
    check('Settings still computes a live/off state per runtime',
          'broken' in lifted and 'offText' in lifted, 'modals/settings.jsx')
    if lifted:
        S = ("const id='codex'; const isDaemon=false; const det="
             "{installed:true,authenticated:false,version:'',"
             "probeError:'will not start',probeDetail:'Error: spawn'};\n")
        got = run_js(S + lifted
                     + 'console.log(JSON.stringify({broken,live,offText}));')
        check('Settings does not call a broken CLI live',
              got['live'] is False,
              '`live` drives both the sentence and the dot; while it is true '
              'the row reads "found · needs a sign-in" and "● sign in"')
        check('...and its sentence is the observation, not a guess',
              'will not start' in got['offText']
              and 'needs a sign-in' not in got['offText'], got['offText'])
        check('...and it does not read as absent either',
              'not found on this machine' not in got['offText'],
              'the program IS on the machine — telling someone to install '
              'what they already installed is the mirror of the same lie')

        ok = run_js(S.replace("probeError:'will not start'", "probeError:''")
                    + lifted + 'console.log(JSON.stringify({broken,live}));')
        check('a working CLI is still live in Settings', ok['live'] is True, ok)

    # The driver-row block: from the list of runtimes it maps over to the
    # start of the next panel. Bounded by what the code IS rather than by a
    # magic character count or the spelling of the expression under test —
    # the first version anchored on the exact ternary, an unrelated edit to
    # that same ternary moved it, `str.find` returned -1, and the slice
    # quietly became the last character of the file.
    _i = settings.find("['claude-code'")
    _e = settings.find('cb-panel', _i) if _i >= 0 else -1
    rows = settings[_i:_e] if _i >= 0 and _e > _i else ''
    check('the Settings driver rows are still there', bool(rows),
          'modals/settings.jsx')
    check('the status dot has a word for broken',
          "'○ broken'" in rows,
          '"○ absent" is the wrong word for a program that is present')

    print()
    if FAILS:
        print(f'broken-cli: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('broken-cli: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

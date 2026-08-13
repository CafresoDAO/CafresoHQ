#!/usr/bin/env python3
"""One classifier, three shapes — and the noun has to match what failed.

`SNAG_CAUSES` was written for coworker dispatch, so every sentence in it names
a BRAIN. Census of the call sites found TWELVE passing failures that have
nothing to do with a brain: every file operation and publish in
views/projects.jsx, all three vault paths, app/storage.jsx, the delivery
share, and the post-approval publish in app.jsx. A vault delete failing
offline announced "couldn't reach that brain — it looks offline from here".

Part of that was self-inflicted the same day: widening the connectivity
pattern so an offline vault delete stopped leaking "NetworkError when
attempting to fetch resource" verbatim ALSO taught it to blame a brain. One
fix, two subjects, and only one was checked.

hq-runtime.jsx already carried this lesson for BROWSER_FETCH — "a page is not
a brain", snagCause applied and then deliberately taken back out — and nobody
had generalised it.

So:
  snagCause   — a brain is the subject   ("that brain isn't signed in yet")
  officeCause — the OFFICE is            ("the office isn't answering")
  cleanCause  — nothing nameable         (sanitised first line, no diagnosis)

officeCause is not a downgrade: the PATTERNS were always right, only the noun
was wrong, so the useful diagnosis survives with the correct subject.

Run: python3 scripts/test_cause_subject.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = ROOT / 'app' / 'floor.jsx'

FAILS = []

# Where the subject is the office itself: files, the vault, publishing.
OFFICE_FILES = ['views/projects.jsx', 'views/vault.jsx',
                'modals/delivery.jsx', 'views/ide.jsx']
# Where a brain really is the subject and snagCause must STAY.
#
# `app/storage.jsx` sat in the list above for a while, and it was the one
# entry the census got wrong. The sweep went file by file over everything
# that had been passing file and vault failures through snagCause; this
# file was on that list because it was touched, not because its subject
# was the office. It has exactly ONE cause call — chatErrorText — and all
# three of chatErrorText's call sites are agent runs (dispatch, delegate,
# task). So the fix for a misdiagnosis was applied to the one surface that
# had been diagnosing correctly, and this test then held it there.
#
# Cost, measured live against a coworker pinned to a model that was not
# installed: the floor and the inbox said "that brain isn't installed on
# this machine — pick another coworker, or install it and try again"; the
# chat bubble, in the same instant, said "the office couldn't find that —
# it may have been moved or renamed". OFFICE_CAUSES has no rule for a
# missing model, because installing models is not something an office
# does, so a missing key fell through to cleanCause and printed
# `Ollama 401: no api key` — a vendor name, an HTTP code and a §6-banned
# word, in the surface whose own comment says it stopped improvising.
BRAIN_FILES = ['features.jsx', 'missions.jsx', 'ui/chat.jsx', 'app/storage.jsx']


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(cases):
    text = FLOOR.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('cause subject — the noun must match the thing that actually failed')
    if not FLOOR.is_file():
        print('  FAIL  missing app/floor.jsx')
        return 1
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    out = run_js(r'''
const R = {};
const CONNECTIVITY = ['Failed to fetch', 'NetworkError when attempting to fetch resource',
                      'Load failed', 'ECONNREFUSED'];
R.officeConnectivity = CONNECTIVITY.map(officeCause);
R.brainConnectivity  = CONNECTIVITY.map(snagCause);
R.officeTimeout = officeCause('ETIMEDOUT');
R.officeFiveXX  = officeCause('HTTP 503 service unavailable');
R.officeMissing = officeCause('ENOENT: no such file or directory');
R.officePerms   = officeCause('EACCES: permission denied');
R.officeDisk    = officeCause('ENOSPC: no space left on device');
R.officeUnknown = officeCause('a thing nobody has a pattern for');
R.cleanUnknown  = cleanCause('a thing nobody has a pattern for');
// A brain-only diagnosis must NOT leak into the office wording.
R.officeNoKey   = officeCause('401 no api key');
R.brainNoKey    = snagCause('401 no api key');
R.officeSanitises = officeCause('POST https://x.com/y failed {"a":1}\nsecond line');
console.log(JSON.stringify(R));
''')

    # ── officeCause keeps the diagnosis, changes the noun ───────────────
    check('every browser wording of "offline" maps to the OFFICE, not a brain',
          all(o == out['officeConnectivity'][0] for o in out['officeConnectivity'])
          and 'brain' not in out['officeConnectivity'][0].lower()
          and 'office' in out['officeConnectivity'][0].lower(),
          f"{out['officeConnectivity']!r} — Chrome, Firefox, Safari and node all word "
          'a dead connection differently and all three must land here')
    check('...while the brain wording is unchanged for brain failures',
          all('brain' in b.lower() for b in out['brainConnectivity']),
          f"{out['brainConnectivity']!r} — splitting these must not defang dispatch")
    check('the useful diagnoses survive with the right subject',
          'too long' in out['officeTimeout']
          and 'not something you did' in out['officeFiveXX']
          and 'moved or renamed' in out['officeMissing']
          and "isn't allowed" in out['officePerms']
          and 'disk space' in out['officeDisk'],
          f"{[out['officeTimeout'], out['officeFiveXX'], out['officeMissing'], out['officePerms'], out['officeDisk']]!r} "
          '— officeCause must not be a bare sanitiser; the patterns were always '
          'right, only the noun was wrong')
    check('a brain-only diagnosis never appears in office wording',
          'signed in' not in out['officeNoKey'] and 'signed in' in out['brainNoKey'],
          f"office={out['officeNoKey']!r} brain={out['brainNoKey']!r} — a vault write "
          'does not have an API key')
    check('an unrecognised failure falls through to the sanitiser, not a guess',
          out['officeUnknown'] == out['cleanUnknown'],
          f"{out['officeUnknown']!r} vs {out['cleanUnknown']!r}")
    check('...and is still sanitised (no URLs, JSON or extra lines)',
          'https://' not in out['officeSanitises'] and '{' not in out['officeSanitises']
          and '\n' not in out['officeSanitises'],
          f"{out['officeSanitises']!r} — §7 applies whatever the subject")

    # ── The call sites, by subject ──────────────────────────────────────
    for rel in OFFICE_FILES:
        f = ROOT / rel
        if not f.is_file():
            check(f'{rel} exists', False, 'file moved?')
            continue
        s = f.read_text(encoding='utf-8')
        stray = re.findall(r'\bsnagCause\s*\(', s)
        check(f'{rel} blames the office, not a brain',
              not stray,
              f'{len(stray)} snagCause call(s) — a file, the vault and a publish are '
              'not brains')
        # Both halves, because the absence check alone is not the rule.
        check(f'{rel} still NAMES the cause',
              re.search(r'\bofficeCause\s*\(', s) is not None,
              'no officeCause call — "not a brain" was only half of it. views/ide.jsx '
              'passed the stray-snagCause check for a day on cleanCause, which is '
              'silent about the subject rather than right about it, so an ENOENT on '
              'the file tree printed "ENOENT: no such file or directory" where the '
              'office table had a sentence ready')

    for rel in BRAIN_FILES:
        f = ROOT / rel
        s = f.read_text(encoding='utf-8')
        check(f'{rel} still uses the brain wording',
              re.search(r'snag(?:Cause|Sentence|Opener)\s*\(', s) is not None,
              'this is coworker dispatch — the brain sentences belong here, and a '
              'sweep that converted everything would have removed them')

    check('officeCause is exported',
          re.search(r'export \{[^}]*\bofficeCause\b', FLOOR.read_text(encoding='utf-8')) is not None,
          'app/floor.jsx')

    # ── the chat bubble, specifically ───────────────────────────────────
    # The membership lists above are a coarse instrument: they ask whether
    # a file mentions a classifier, and app/storage.jsx has exactly one
    # cause call, so "mentions snagCause" and "chatErrorText uses
    # snagCause" happen to coincide today. Pin the thing that actually
    # matters, so adding a second, genuinely office-subject call to this
    # file later cannot quietly satisfy the list check while the bubble
    # goes back to describing a lost file.
    stor = (ROOT / 'app' / 'storage.jsx').read_text(encoding='utf-8')
    fn = re.search(r'const chatErrorText = \([\s\S]*?\n\};', stor)
    check('chatErrorText is still there to check', bool(fn), 'app/storage.jsx')
    body = fn.group(0) if fn else ''
    check('the chat bubble classifies a failed run as a BRAIN failure',
          re.search(r'\bsnag(?:Cause|Opener)\s*\(\s*raw\s*\)', body)
          and 'officeCause(' not in body,
          'app/storage.jsx: this bubble is a coworker speaking about their own '
          'failed run — all three call sites are agent dispatches. officeCause '
          'here sends the boss to check the office, which is the one thing on '
          'their screen that is demonstrably fine')

    # And the difference is not cosmetic — these are the three failures a
    # coworker can actually have, verbatim off a live office.
    diff = run_js('''
      const R = {};
      const REAL = [
        'TypeError: Failed to fetch',
        'Ollama 404: model "mistral-nemo:12b" not found',
        'Ollama 401: no api key',
      ];
      R.brain  = REAL.map(snagCause);
      R.office = REAL.map(officeCause);
      console.log(JSON.stringify(R));
    ''')
    check('...and the two tables really do disagree about every one of them',
          all(b != o for b, o in zip(diff['brain'], diff['office'])),
          'if these ever agree, this whole test has stopped measuring anything')
    check('a model that is not installed says so, and says what to do',
          'installed on this machine' in diff['brain'][1],
          repr(diff['brain'][1]))
    check('a missing key never reaches the boss as vendor shrapnel',
          not re.search(r'ollama|\b40\d\b|api key', diff['brain'][2], re.I),
          repr(diff['brain'][2]) + ' — §7 bans raw dumps and §6 bans "api key"; '
          'the office table has no rule for either, so both fall through to '
          'cleanCause and print the error itself')

    print()
    if FAILS:
        print(f'cause subject: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('cause subject: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

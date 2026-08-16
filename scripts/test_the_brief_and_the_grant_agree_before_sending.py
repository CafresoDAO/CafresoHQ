#!/usr/bin/env python3
"""A system prompt may not order a tool the same prompt forbids.

`agentStream` writes one prompt out of two halves that had never been
compared: the brief (the office's default rules, or the JOB DESCRIPTION
the boss typed) and the grant (`toolsForAgent`, stated as "ONLY invoke
these exact tools"). When the brief names a marker the grant withheld, the
coworker is ordered to do something and forbidden from doing it in the same
breath — and the round trip is spent either way.

Measured 2026-08-16 on office 9261, canned brain on 9236. Both halves,
both wrong, on a HEALTHY vault:

  Kip, tools ['web','vault'], no Brave key. Shipped persona: "Use [SEARCH]
  to gather sources, then synthesize into a research note saved to
  Research/<topic>.md via [VAULT_NEW]." Granted: BROWSER_FETCH, ACK,
  SPAWN_SUBAGENT, HIRE_AGENT, HIRE_ASSISTANT, REQUEST_ELEVATION, DM_TO,
  PEER_JOURNAL, MEMORY_*, VAULT_*, EXPORT_*. SEARCH is not in it.

  Otto, hired through the NEW HIRE form with JOB DESCRIPTION cleared so
  the office's own default applies, no vault box: "FILE-DELIVERY RULE: Any
  deliverable longer than ~200 words … MUST be saved to the vault using
  [VAULT_NEW: <path>]…[/VAULT_NEW] or [VAULT_APPEND: <path>]…" Granted:
  neither. That MUST is the office's own sentence, not the boss's.

Two fixes, because the two halves are owned by different people. The
office's rule is conditional now — it asks for the same restraint with no
vault, minus the order. The boss's half is left exactly as typed and
reconciled afterwards, computed from the assembled text, because JOB
DESCRIPTION is a free-text field and a fix that only knew Kip's sentence
would not survive the first custom hire.

Guards:
  · the reconciler reads real tool names only, and only ungranted ones
  · it runs on the ASSEMBLED brief, so it covers both halves at once
  · it lands after the granted list, where it reads as a correction
  · the office's own MUST is not issued without the tool behind it
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import brace_lift  # noqa: E402

RUNTIME = ROOT / 'hq-runtime.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the brief and the grant agree before sending')
    code = RUNTIME.read_text(encoding='utf-8')
    fn = brace_lift(code, 'function orderedButNotGranted(text, known, granted) {')

    # ── 1. it is fed the whole brief, and the real catalog ───────────────
    call = re.search(r'const ordered = orderedButNotGranted\(\s*([\s\S]{0,240}?)\);', code)
    check('the reconciler is called on the assembled brief',
          call and re.match(r'\s*base\s*,', call.group(1)),
          [call.group(1) if call else None,
           '— the office half and the boss half are one string by then; '
           'running it on either alone leaves the other unchecked'])
    if call:
        check('...against every tool the registry knows',
              'TOOL_REGISTRY' in call.group(1),
              'a hand-kept list of "tools worth checking" is the drift this '
              'whole file keeps paying for')
        check('...and against what this session actually granted',
              'enabledTools.map(t => t.name)' in call.group(1),
              call.group(1))
    check('the names come in as parameters, not off the module',
          'TOOL_REGISTRY' not in fn,
          'the suites lift this function into node; a module-level const '
          'inside it is a ReferenceError, per openedMarkers above it')

    # ── 2. it lands where it reads as a correction ───────────────────────
    sysline = re.search(r'const sys = \[base \+ ([^,]+),', code)
    check('the correction is in the prompt at all',
          sysline and 'orderedNote' in sysline.group(1),
          [sysline.group(1) if sysline else None,
           '— computed and never sent is the same as not computed'])
    if sysline:
        parts = sysline.group(1)
        check('...after the granted list, not before it',
              parts.index('toolsNote') < parts.index('orderedNote'),
              [parts, '— before the list it is a third opinion; after it, it '
               'is the office resolving its own contradiction'])

    # ── 3. the office does not issue a MUST it cannot honour ─────────────
    head = code[code.index('async function agentStream('):]
    head = head[:head.index('const toolsNote')]
    check("the office's own file rule is conditional",
          re.search(r'const canFile = enabledTools\.some\(t => t\.name === '
                    r"'VAULT_NEW'\)", head) is not None,
          'MUST save to the vault, with no VAULT_NEW granted, is the office '
          'writing the contradiction itself')
    nov = re.search(r'const fileDelivery = canFile\s*\n\s*\?[\s\S]*?\n\s*: (`[\s\S]*?`);', head)
    check('...and the no-vault form orders no marker',
          nov and 'VAULT_NEW' not in nov.group(1),
          nov.group(1)[:300] if nov else '— the two-armed form is gone')

    # ── 4. drive it ──────────────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
    else:
        js = fn + r'''
const KNOWN = ['SEARCH','BROWSER_FETCH','VAULT_NEW','VAULT_APPEND','VAULT_READ',
               'GENERATE_IMAGE','FILE_WRITE','BASH','MEMORY_WRITE','DM_TO'];
const KIP = "You are Kip, the Deep Research specialist. Use [SEARCH] to gather"
  + " sources, then synthesize into a research note saved to Research/<topic>.md"
  + " via [VAULT_NEW]. In chat, return ONLY a 2-4 sentence executive summary.";
const OTTO = "FILE-DELIVERY RULE: Any deliverable longer than ~200 words MUST be"
  + " saved to the vault using [VAULT_NEW: <path>]…[/VAULT_NEW] or"
  + " [VAULT_APPEND: <path>]…[/VAULT_APPEND].";
const R = {
  // The two reproductions, verbatim shapes.
  kip:      orderedButNotGranted(KIP, KNOWN, ['BROWSER_FETCH','VAULT_NEW','VAULT_APPEND']),
  otto:     orderedButNotGranted(OTTO, KNOWN, ['MEMORY_WRITE','DM_TO']),
  // Everything ordered is granted: nothing to say.
  healthy:  orderedButNotGranted(KIP, KNOWN, ['SEARCH','VAULT_NEW']),
  // A closing marker is the same order as its opener, once.
  closer:   orderedButNotGranted("[VAULT_NEW: a.md]\n x \n[/VAULT_NEW]", KNOWN, []),
  // A job description is prose. Wikilinks, shouty asides and a literal
  // TODO are not tool orders, and naming them would teach the boss that
  // the correction is noise.
  prose:    orderedButNotGranted("See [[Research/Index]] and [TODO: ask Kim]."
                                 + " Mark it [URGENT] and cc [Ops].", KNOWN, []),
  // Repeats collapse — Atlas names VAULT_NEW twice in one persona.
  dupes:    orderedButNotGranted("[VAULT_NEW: a] and [VAULT_NEW: b]", KNOWN, []),
  // Order is the order they appear, so the sentence reads like the brief.
  order:    orderedButNotGranted("[BASH] then [SEARCH] then [FILE_WRITE]", KNOWN, []),
  empty:    orderedButNotGranted('', KNOWN, []),
  nullish:  orderedButNotGranted(null, null, null),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '--input-type=module', '-e', js],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr[-1500:], file=sys.stderr)
            raise SystemExit('node harness failed on source lifted from hq-runtime')
        R = json.loads(p.stdout.strip().split('\n')[-1])

        check("Kip's ordered-but-missing search is caught",
              R['kip'] == ['SEARCH'], R['kip'])
        check("...and the vault he DOES have is not mentioned",
              'VAULT_NEW' not in R['kip'],
              'correcting a brief that was right is how a real correction '
              'gets skimmed past')
        check("the office's own MUST is caught the same way",
              R['otto'] == ['VAULT_NEW', 'VAULT_APPEND'], R['otto'])
        check('a brief the session can honour says nothing',
              R['healthy'] == [], R['healthy'])
        check('a closing marker is not a second order',
              R['closer'] == ['VAULT_NEW'], R['closer'])
        check('prose brackets are not tool orders',
              R['prose'] == [], R['prose'])
        check('...nor is the same order twice', R['dupes'] == ['VAULT_NEW'], R['dupes'])
        check('the list reads in the order the brief does',
              R['order'] == ['BASH', 'SEARCH', 'FILE_WRITE'], R['order'])
        check('an empty brief is not a contradiction', R['empty'] == [], R['empty'])
        check('...and neither is a missing one', R['nullish'] == [], R['nullish'])

        # The sentence itself. Lifted separately: it is built inline in
        # agentStream, so this rebuilds it from the same source text rather
        # than hand-copying a boss-facing string into the suite.
        m = re.search(r'const orderedNote = ordered\.length\s*\n\s*\? (`[\s\S]*?`)\s*\n\s*: \'\';',
                      code)
        check('the correction sentence is still built here', m is not None)
        if m:
            js2 = ("const ordered = %s; const plural = ordered.length > 1;\n"
                   "console.log(JSON.stringify({ one: %s }));"
                   % (json.dumps(['SEARCH']), m.group(1)))
            js3 = ("const ordered = %s; const plural = ordered.length > 1;\n"
                   "console.log(JSON.stringify({ two: %s }));"
                   % (json.dumps(['VAULT_NEW', 'VAULT_APPEND']), m.group(1)))
            one = json.loads(subprocess.run(
                ['node', '--input-type=module', '-e', js2], cwd=ROOT,
                capture_output=True, text=True, timeout=60).stdout)['one']
            two = json.loads(subprocess.run(
                ['node', '--input-type=module', '-e', js3], cwd=ROOT,
                capture_output=True, text=True, timeout=60).stdout)['two']
            check('the correction names the tool it is about',
                  'SEARCH' in one and 'VAULT_APPEND' in two, [one, two])
            check('...tells them not to emit it',
                  'not emit the marker' in one and 'markers' in two, [one, two])
            # §7 in the model's direction: an instruction to stop with no
            # instruction on what to do instead gets improvised around, and
            # improvising is exactly what produced the path with no file.
            check('...and says what to do instead',
                  'say so plainly' in one, one)
            check('...and agrees with itself about how many there are',
                  'that is NOT' in one and 'those are NOT' in two, [one, two])

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

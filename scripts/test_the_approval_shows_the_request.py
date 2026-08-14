#!/usr/bin/env python3
"""The gate against a misleading summary was only wired to one of two doors.

The approval tray renders `p.detail` under a comment that states the rule
exactly right:

    The actual thing being authorised, verbatim. The title above is the
    REQUESTER's summary of its own request — this gate exists to catch a
    summary that doesn't match the action, so the boss has to be able to
    see both.

`detail` was set by exactly one caller: the external bridge that surfaces
Claude Code's tool-use requests. Every approval HQ raises itself passed no
`detail` at all, so the gate rendered nothing for any of them — including
the highest privilege in the product. A coworker asking for file and shell
access produced a card reading:

    🛡 Give Nova file and shell access: needs to read the CSVs
    by Nova · grant-elevation · coworker waiting on your call

and that was the whole card. The boss granted the run of the filesystem off
an eighty-character summary the requester wrote about itself, while its
verbatim request — up to 1200 characters, already stored — sat unread.

The same held for both hire kinds: `rationale` was collected, truncated to
1200 characters, stored, and never shown. "Hire: Kip (Specialist)" was the
entire case for adding an AI to the office.

Worse, the elevation request gathers a provenance snapshot under the
comment "Snapshot context for the boss to review", and none of it was
reviewable. The case that matters is the one the boss cannot otherwise
detect: a TRANSIENT helper — spawned by another coworker mid-run, never
hired, gone at the end of the run — asking for shell access, rendered
identically to a request from somebody the boss hired.

Run: python3 scripts/test_the_approval_shows_the_request.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def literals(src):
    """Every `onApprovalRequest({…})` argument, brace-matched. Evaluated for
    real below rather than pattern-matched, so the check is about the object
    the tray actually receives."""
    out = []
    for m in re.finditer(r'onApprovalRequest\(\{', src):
        j = src.index('{', m.end() - 1)
        d, k = 0, j
        while k < len(src):
            if src[k] == '{':
                d += 1
            elif src[k] == '}':
                d -= 1
                if d == 0:
                    break
            k += 1
        out.append(src[j:k + 1])
    return out


def main():
    print('an approval has to show what is being approved')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    feats = FEATURES.read_text(encoding='utf-8')
    lits = literals(app)

    def pick(kind):
        for L in lits:
            if re.search(r"kind:\s*'" + re.escape(kind) + r"'", L):
                return L
        return None

    # ── 1. every request that collected a body now hands it over ────────
    WITH_BODY = ['grant-elevation', 'hire-agent', 'hire-assistant']
    SCOPE = """
const agent = { id:'a_nova', name:'Nova', tools:['vault','browser'],
                assistant:false, transient:true, reportsTo:'a_kip',
                model:'ollama:llama3.1:latest', color:'sky' };
const senior = { id:'a_kip', name:'Kip' };
const reason = 'needs to read the CSVs';
/* Long on purpose. A short fixture cannot see the regression that
   matters here — the card and the record drifting apart because one of
   them got sliced — since any truncation of a 13-character string is that
   string again. Sized past the 1200 the writers cap at. */
const verbatim = 'VERBATIM-BODY ' + 'abcdefghij'.repeat(140);
const hireRationale = verbatim;
const assistantRationale = verbatim;
const proposedName = 'Kip';
const proposedRole = 'Specialist';
const proposalSummary = `Hire: ${proposedName} (${proposedRole})`;
"""
    for kind in WITH_BODY:
        L = pick(kind)
        if not L:
            check(f'{kind} still raises an approval', False, 'not found in app.jsx')
            continue
        obj = run(SCOPE + f'console.log(JSON.stringify({L}));')
        BODY = 'VERBATIM-BODY ' + 'abcdefghij' * 140
        got = obj.get('detail')
        check(f'{kind} hands the tray the verbatim request',
              got == BODY,
              f"detail is {len(got) if got else got} chars, not {len(BODY)} "
              "— the tray's `detail` gate is the "
              'only place the boss sees anything but the requester\'s own '
              'summary; without it this card is a title and two buttons')
        stored = (obj.get('elevationRequest') or obj.get('hireProposal')
                  or obj.get('assistantProposal') or {})
        copy = stored.get('details') or stored.get('rationale')
        check(f'...the same string it stored, not a second version',
              copy == got,
              f'record is {len(copy) if copy else copy} chars, card is '
              f'{len(got) if got else got} — two slices of the same '
              'body are free to drift, and then the card and the record '
              'disagree about what was authorised')

    # ── 2. the elevation card's provenance, resolved where the roster is ─
    ev = run(SCOPE + f'console.log(JSON.stringify({pick("grant-elevation")}));')
    er = ev.get('elevationRequest', {})
    check('the elevation request names the senior, not an id',
          er.get('reportsToName') == 'Kip',
          f"{er.get('reportsToName')!r} — the tray has no agents list, and "
          '"reports to a_kip" is not a fact a boss can act on')
    check('...and still carries the transient flag the card leans on',
          er.get('isTransient') is True and 'currentTools' in er, er)
    check('the title no longer carries its own shield',
          not str(ev.get('title', '')).startswith('🛡'),
          f"{ev.get('title')!r} — the tray prepends one for elevated rows, "
          'and the two together rendered as "🛡 🛡 Give Nova…"')

    # ── 3. the tray reads all of it ─────────────────────────────────────
    check('the tray still renders the verbatim body', 'p.detail &&' in feats,
          'features.jsx')
    check("...and softens its hazard rule for the kinds that aren't one",
          re.search(r'p\.elevated \? undefined : \{ borderLeftColor', feats)
          is not None,
          'the red left rule is tuned for a shell command about to run; a '
          'hire proposal is somebody making a case, and colouring it like a '
          'hazard points the boss at the wrong thing (§5)')

    i = feats.find("p.kind === 'grant-elevation' && p.elevationRequest")
    check('the tray renders the provenance block at all', i > 0,
          'features.jsx: the snapshot was collected "for the boss to review" '
          'and never reviewed')
    prov = feats[i:i + 1400] if i > 0 else ''
    check('a transient helper is called out as one',
          'er.isTransient' in prov and 'did not hire' in prov,
          'the one case the boss cannot detect any other way: a sub-agent '
          'another coworker spawned mid-run, asking for the filesystem')
    check('...and it is the first branch, not a footnote',
          prov.find('isTransient') < prov.find('isAssistant'), prov[:300])
    check('an assistant is distinguished from someone the boss hired',
          'er.isAssistant' in prov and 'someone you hired' in prov, prov[:300])
    check('the card says what they already have',
          'currentTools' in prov and 'no tools yet' in prov,
          'an empty toolset has to read as a fact, not as a blank')

    print()
    if FAILS:
        print(f'approvals: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('approvals: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

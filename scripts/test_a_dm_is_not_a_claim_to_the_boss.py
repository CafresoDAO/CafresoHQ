#!/usr/bin/env python3
"""A path in a private message drew a cabinet warning.

Measured on office 9261, 2026-08-15, the task path, canned brain. Vera's
whole reply was:

    On it.
    [DM_TO: Kip]
    Please check Research/plan.md for the vendor summary.
    [/DM_TO]

The block was stripped and delivered — Kip got the DM, the boss's bubble
read "On it." — and beneath that bubble the office printed:

    _(`Research/plan.md` is named above, but nothing was written to the
    cabinet on this run, so that file is not there.)_

No such name was above. The path lived only in teammate-directed text the
boss never sees, and naming a file to a colleague is not promising it to
the boss. The DONE card was worse: it stored that sentence as the head of
its result while its own artifact line showed Deliveries/dm-relay.md —
written to the cabinet, on this run, two lines down.

The cause was an input seam: honestyNotes ran its two SURFACE-claim
guards (unfiledPath "is named above", unverifiedSources "this names
sources") on the RAW buffer, while the bubble those notes render under
shows the CLEANED body. The strip chain existed in exactly one place —
visibleReply — so the guards' "above" and the bubble's "above" were two
different texts. The fix extracts the chain as shownBody(text, selfName)
and feeds it to exactly those two guards. The marker guards (unsent
blocks, orphaned hand-offs, acks) keep reading raw — markers only exist
there; feeding them the shown body would blind them.

A consequence pinned on purpose: a path inside a stripped tool MARKER no
longer draws this note either (probe-measured before the fix: a failed
[VAULT_READ: Research/ghost.md] fired it). The marker is not on the
boss's surface — the failed-visit row is, rendered from structured visit
data, and that row already tells the boss the trip failed. One story,
told by the surface that owns it.

Run: python3 scripts/test_a_dm_is_not_a_claim_to_the_boss.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []

sys.path.insert(0, str(ROOT / 'scripts'))
from test_artifacts import pure_source  # noqa: E402


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def const_lift(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i) + len(end_marker)
    return src[i:j]


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a DM is not a claim to the boss')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    runtime = RUNTIME.read_text(encoding='utf-8')

    # ---- behavior: the real composition, lifted ----
    js = pure_source() + '\n'
    # ORPHAN_TAG_RE and friends: stripOrphanTags' vocabulary. Raw-string end
    # marker — the source line carries doubled backslashes a plain literal
    # would collapse (fire85's lesson, now a habit).
    js += const_lift(runtime, 'const ORPHAN_TAG_NAMES =',
                     r"+ ORPHAN_TAG_CORE + '[ \\t]*$', 'gim');") + '\n'
    for header in ['function stripSelfLabel(', 'function stripAcks(',
                   'function stripOrphanTags(', 'function stripBlocks(',
                   'function shownBody(', 'function unverifiedSources(',
                   'function unfiledPath(']:
        js += brace_lift(runtime, header) + '\n'

    CASES = {
        # The measured lie: path only inside a delivered DM block.
        'dm_body': {
            'raw': 'On it.\n[DM_TO: Kip]\nPlease check Research/plan.md '
                   'for the vendor summary.\n[/DM_TO]',
            'visits': [], 'self': 'Vera',
        },
        # #50's direction must survive: a promise in prose still warns.
        'prose_claim': {
            'raw': 'Saved the briefing to Drafts/briefing.md for you.',
            'visits': [], 'self': 'Vera',
        },
        # #82's direction must survive: a written path stays silent.
        'prose_written': {
            'raw': 'Saved the briefing to Drafts/briefing.md for you.',
            'visits': [{'name': 'VAULT_NEW', 'arg': 'Drafts/briefing.md'}],
            'self': 'Vera',
        },
        # Pinned consequence: a stripped marker's path is the visit row's
        # story, not this note's — even when the trip failed.
        'marker_failed': {
            'raw': 'I checked the vendor list '
                   '[VAULT_READ: Research/ghost.md]\nB wins on cost.',
            'visits': [{'name': 'VAULT_READ', 'arg': 'Research/ghost.md',
                        'failed': True}],
            'self': 'Kip',
        },
        # The sibling guard shared the seam: a source cited to a TEAMMATE
        # is not a citation to the boss.
        'dm_source': {
            'raw': 'On it.\n[DM_TO: Kip]\nPer Gartner 2025. Source: '
                   'https://gartner.com/report\n[/DM_TO]',
            'visits': [], 'self': 'Vera',
        },
        # ...and a source cited in prose still draws the caveat.
        'prose_source': {
            'raw': 'Per Gartner 2025. Source: https://gartner.com/report',
            'visits': [], 'self': 'Vera',
        },
        # Mixed reply: the note names the promised path the boss can see,
        # and not the one that went to a teammate.
        'mixed': {
            'raw': 'Saved it to Drafts/plan.md.\n[DM_TO: Kip]\nAlso see '
                   'Research/other.md when you get a chance.\n[/DM_TO]',
            'visits': [], 'self': 'Vera',
        },
    }

    js += '''
const CASES = %s;
const out = {};
for (const [k, c] of Object.entries(CASES)) {
  const shown = shownBody(c.raw, c.self);
  out[k] = { shown: shown,
             unfiled: unfiledPath(shown, c.visits),
             sources: unverifiedSources(shown, c.visits) };
}
console.log(JSON.stringify(out));
''' % json.dumps(CASES)

    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted composition runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    got = json.loads(p.stdout.strip().split('\n')[-1])

    check('the boss\'s surface for the measured reply is just "On it."',
          got['dm_body']['shown'] == 'On it.', got['dm_body'])
    check('a path named only in a DM draws no cabinet warning',
          got['dm_body']['unfiled'] is None, got['dm_body'])
    check('a promise in prose still warns (#50 kept)',
          got['prose_claim']['unfiled'] is not None
          and 'Drafts/briefing.md' in got['prose_claim']['unfiled'],
          got['prose_claim'])
    check('a written path stays silent (#82 kept)',
          got['prose_written']['unfiled'] is None, got['prose_written'])
    check('a stripped marker\'s path is the visit row\'s story, not this note\'s',
          got['marker_failed']['unfiled'] is None
          and 'ghost' not in got['marker_failed']['shown'],
          got['marker_failed'])
    check('a source cited to a teammate draws no caveat',
          got['dm_source']['sources'] is None, got['dm_source'])
    check('a source cited in prose still draws the caveat',
          got['prose_source']['sources'] is not None, got['prose_source'])
    check('a mixed reply warns about the visible promise only',
          got['mixed']['unfiled'] is not None
          and 'Drafts/plan.md' in got['mixed']['unfiled']
          and 'Research/other.md' not in got['mixed']['unfiled'],
          got['mixed'])

    # ---- structure: the seam is wired in CODE, in one place ----
    code = strip_comments(runtime)
    notes = brace_lift(code, 'function honestyNotes(')
    check('honestyNotes derives the shown body from the reply and speaker',
          re.search(r'const shown = shownBody\(raw,\s*o\.self\)', notes)
          is not None)
    check('the cabinet-path guard reads the shown body',
          'unfiledPath(shown, o.visits)' in notes)
    check('the sources guard reads the shown body',
          'unverifiedSources(shown, o.visits)' in notes)
    check('the marker guards still read raw',
          'unsentBlocks(raw' in notes and 'fabricatedRelay(raw' in notes)
    vis = brace_lift(code, 'function visibleReply(')
    check('the bubble reads the same shownBody',
          re.search(r'const cleaned = shownBody\(raw,\s*selfName\)', vis)
          is not None)
    check('the strip chain exists in exactly one place',
          code.count('stripOrphanTags(stripAcks(stripBlocks(stripSelfLabel(')
          == 1)

    print('FAIL' if FAILS else 'PASS')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

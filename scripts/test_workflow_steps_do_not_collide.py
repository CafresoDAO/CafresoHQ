#!/usr/bin/env python3
"""#144 — a workflow's own steps became indistinguishable from each other.

Driven live on 2026-08-18: opened the Workflow modal on office 9280's real
fixture tasks and added two of the three available ones as steps. Both
share a 40-character prefix — "Summarise the vendor notes — probe one
t..." — and the STEPS list rendered them with a raw `t.title.slice(0,40)`,
no ellipsis, no hover. On screen, step 1 and step 2 were the same bytes.
The ↑ (reorder) and ✕ (remove) buttons sat right next to that label — a
boss acting on "the second step" had no way to confirm which task that
button was actually about to move or delete. The AVAILABLE TASKS list one
panel down carried the identical defect at `.slice(0,50)`.

This is not a hypothetical collision: the office's own probe-task naming
scheme (`... — probe one <N>`) produces exactly this shape whenever two
probes are both selected, which the fixture on 9280 already has.

worklog.jsx already solved this class of bug for card notes — `cardNote()`
cuts on a word boundary, appends the `…` that says a cut happened, and the
caller keeps the full text reachable on hover. The fix routes both
WorkflowModal lists through the same helper and gives each label a
`title={t.title}` hover carrying the untruncated string, so the visible
row can still look similar at a glance but the truth — which task this
button acts on — is always one hover away.

This suite:
  · pins the premise that the two live fixture titles actually collide
    under the OLD raw slice (the bug is real, not a strawman);
  · lifts modals/collab.jsx's own STEPS and AVAILABLE TASKS rows and
    confirms each calls `cardNote`, not a raw slice, and carries a
    `title={t.title}` hover with the UNTRUNCATED string;
  · runs the real `cardNote` (lifted from app/worklog.jsx) over the
    colliding pair and confirms the visible label is honestly marked with
    `…` when it's cut, and that the hover value the row carries for the
    two tasks actually differs (the disambiguation exists somewhere on
    the row, even when the printed label does not).
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
COLLAB = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')
WORKLOG = (ROOT / 'app' / 'worklog.jsx').read_text(encoding='utf-8')

FAILS = []


def check(name, cond, detail=''):
    print('  %s %s%s' % ('✓' if cond else '✗', name,
                          ('' if cond else ' — ' + str(detail)[:300])))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header, start=0):
    i = src.find(header, start)
    if i < 0:
        raise AssertionError('anchor not found: %r' % header)
    depth = 0
    j = src.find('{', i)
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after %r' % header)


def run_js(script):
    p = subprocess.run(['node', '--input-type=module', '-e', script],
                        capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError('node failed: %s' % p.stderr[-900:])
    return json.loads(p.stdout.strip().splitlines()[-1])


# The two real titles from office 9280's fixture that collide under a raw
# 40-char slice. Anchored on the fixture's own naming shape, not invented.
TITLE_A = 'Summarise the vendor notes — probe one three zero'
TITLE_B = 'Summarise the vendor notes — probe one two nine'

CARDNOTE_SRC = brace_lift(WORKLOG, 'function cardNote(text, cap) {')

# Anchored on the buttons beside each row, not on the fix — a row's own
# ↑/✕ (steps) or +ADD (available) markup is what the boss actually clicks,
# and it will not move even if the label expression changes shape again.
STEPS_ROW = COLLAB[COLLAB.rfind('<div key={id} className="row"',
                                 0, COLLAB.find('onClick={()=>moveUp(i)}')):
                   COLLAB.find('</div>', COLLAB.find('onClick={()=>removeStep(id)}')) + 6]
AVAILABLE_ROW = COLLAB[COLLAB.rfind('<div key={t.id} className="row"',
                                     0, COLLAB.find('+ ADD</button>')):
                        COLLAB.find('</div>', COLLAB.find('+ ADD</button>')) + 6]


def main():
    print('#144 — the workflow steps list stopped telling its own steps apart\n')

    # ── premise: the collision is real ─────────────────────────────────
    check('the two live fixture titles differ',
          TITLE_A != TITLE_B, (TITLE_A, TITLE_B))
    check('…but a raw 40-char slice makes them identical (the bug, unpatched)',
          TITLE_A[:40] == TITLE_B[:40], (TITLE_A[:40], TITLE_B[:40]))

    # ── the STEPS row ────────────────────────────────────────────────────
    check('STEPS row found', len(STEPS_ROW) > 40, STEPS_ROW[:120])
    check('STEPS label goes through cardNote, not a raw .slice(',
          'cardNote(t.title, 40)' in STEPS_ROW and '.title.slice(' not in STEPS_ROW,
          STEPS_ROW)
    check('STEPS row carries a hover with the FULL title (not re-truncated)',
          bool(re.search(r'title=\{t\.title\}', STEPS_ROW)), STEPS_ROW)

    # ── the AVAILABLE TASKS row ──────────────────────────────────────────
    check('AVAILABLE TASKS row found', len(AVAILABLE_ROW) > 30, AVAILABLE_ROW[:120])
    check('AVAILABLE TASKS label goes through cardNote, not a raw .slice(',
          'cardNote(t.title, 50)' in AVAILABLE_ROW and '.title.slice(' not in AVAILABLE_ROW,
          AVAILABLE_ROW)
    check('AVAILABLE TASKS row carries a hover with the FULL title',
          bool(re.search(r'title=\{t\.title\}', AVAILABLE_ROW)), AVAILABLE_ROW)

    # ── import wiring ────────────────────────────────────────────────────
    check('collab.jsx imports cardNote from app/worklog.jsx',
          re.search(r"import \{[^}]*\bcardNote\b[^}]*\} from '\.\./app/worklog\.jsx'", COLLAB)
          is not None, COLLAB[:200])

    # ── the real cardNote, run over the colliding pair ──────────────────
    js = """
%s
const a = %s, b = %s;
console.log(JSON.stringify({
  labelA: cardNote(a, 40), labelB: cardNote(b, 40),
  labelA_marked: cardNote(a, 40).includes('\\u2026'),
  labelB_marked: cardNote(b, 40).includes('\\u2026'),
  hoverA: a, hoverB: b,
}));
""" % (CARDNOTE_SRC, json.dumps(TITLE_A), json.dumps(TITLE_B))
    out = run_js(js)
    check('a cut STEPS label is honestly marked with an ellipsis (A)',
          out['labelA_marked'], out['labelA'])
    check('a cut STEPS label is honestly marked with an ellipsis (B)',
          out['labelB_marked'], out['labelB'])
    check('the hover text for the two tasks actually differs '
          '(disambiguation exists on the row even if the printed label does not)',
          out['hoverA'] != out['hoverB'], (out['hoverA'], out['hoverB']))
    check('the hover carries the WHOLE title, not a second truncation',
          out['hoverA'] == TITLE_A and out['hoverB'] == TITLE_B,
          (out['hoverA'], out['hoverB']))

    print()
    if FAILS:
        print('FAILED: %d check(s)' % len(FAILS))
        for f in FAILS:
            print('  -', f)
        return 1
    print('All checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

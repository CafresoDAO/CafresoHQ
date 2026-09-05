#!/usr/bin/env python3
"""HIRE ✓ on a fresh form did nothing at all — no error, no hint, no dialog.

Onboarding step 2 opens BRING IN A HELPER on the NEW HIRE form with every
box empty, so HIRE ✓ is very plausibly the first button a beta tester ever
presses. `submit()` opened with

    if (!name.trim()) return;

over a `<button className="px-btn primary" onClick={submit}>` that carried
no `disabled` state, and nothing anywhere on the screen said a name was
wanted. The click was taken and swallowed: the dialog stayed open, unchanged
and silent. A live button is a promise that it can do the thing, so the only
reading left for the boss is that the app is broken — the #299 shape (🌙
SCHEDULE and ▶ RUN NOW live over an office with nobody in it), one worse,
because #299 at least answered with `topic + agent required`.

`hireNeedsNote(name)` is one sentence carrying the reason AND the route, and
it is read by BOTH the button's `disabled` state and the footer hint the
boss can see without hovering — the same single-source shape as
`noCrewNote(agents)` (#299) and `inboxEmptyNote(...)` (#306), so the two can
never drift apart. It names the field by the label printed above the box
(NAME), not by the variable.

The form's second silent early return is ★ SAVE AS TEMPLATE. `hqPrompt`
resolves `string | null` (ui/feedback.jsx) and the handler collapsed both
answers with `|| ''`, so OK on a blank box did nothing and said nothing.
Cancel must STAY silent — the boss just said no — so only the unusable
answer gets a sentence.

Run: python3 scripts/test_the_hire_button_says_what_it_is_waiting_for.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = ROOT / 'modals' / 'hire.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Comments first — this fix's own comments quote the bad shape."""
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


def main():
    print('the hire button says what it is waiting for')
    src = HIRE.read_text(encoding='utf-8')
    bare = strip_comments(src)

    # ── §1 the helper exists, is pure, and is module-level ──────────────
    # #324 widened this helper: the roster now arrives as a SECOND argument
    # so the same one sentence can also refuse a name somebody already
    # answers to. The old assertion pinned the arity at exactly `(name)`,
    # which was never what it was testing for — it was testing that the
    # helper is module-level and closes over no component state. Pinning the
    # arity ENCODED the gap: the only way to teach this door about the
    # roster was to break this line. It is widened here, not weakened —
    # `currentAgents` must be a declared parameter (a prop read from a
    # closure would still be impure and still unliftable), and §2 below now
    # additionally demands every call site actually pass it.
    # #356 widened it again, for the same reason and in the same way: the
    # BRAIN is now a third declared parameter, so the one sentence can also
    # refuse the brainless hire a bare first run actually produces. Pinning
    # the arity at two would have encoded THAT gap exactly as pinning it at
    # one encoded #324's.
    check('one helper answers "why can HIRE ✓ not go through"',
          re.search(r'^function hireNeedsNote\(name, currentAgents, model\)',
                    bare, re.M) is not None,
          'hireNeedsNote must be module-level and must not close over '
          'component state, or it cannot be driven here')

    # ── §2 both the control and the visible hint read that one helper ───
    hire_btn = re.search(r'<button[^>]*onClick=\{submit\}[\s\S]{0,400}?HIRE ✓',
                         bare)
    check('the HIRE ✓ button is still there to be found', hire_btn is not None)
    btn = hire_btn.group(0) if hire_btn else ''
    check('HIRE ✓ goes dark while the note stands',
          'disabled={!!hireNeedsNote(name, currentAgents, model)}' in btn,
          'a live button is a promise it can do the thing: ' + btn[:200])
    check('…and carries the note as its tooltip',
          'title={hireNeedsNote(name, currentAgents, model) || undefined}' in btn,
          btn[:200])
    check('…and the note is also VISIBLE, not hover-only',
          re.search(r'className="hint"[\s\S]{0,120}'
                    r'hireNeedsNote\(name, currentAgents, model\)', bare)
          is not None,
          'a tooltip alone is unreachable on a touch screen and invisible to '
          'anyone not hunting for it')

    # The bare guard is what the bug was. It may stay as a backstop, but the
    # handler must not be the ONLY thing standing between the click and
    # nothing happening — §2 above is what proves that.
    # A call site that forgets the roster is a door that silently stops
    # asking the #324 question, so no call site may drop it.
    check('every reader of the note hands it the roster',
          re.search(r'hireNeedsNote\((?!name, currentAgents, model\))', bare)
          is None,
          'a hireNeedsNote(name) call site cannot see who already works here')

    check('submit no longer opens with the anonymous name check',
          'if (!name.trim()) return;' not in bare,
          'the silent early return is back in modals/hire.jsx')

    # ── §3 the second silent return: ★ SAVE AS TEMPLATE ────────────────
    tpl = lift(bare, 'const saveAsTemplate', 'const deleteTpl')
    check('a cancelled template prompt is still silent',
          re.search(r'if \(answer == null\) return;', tpl) is not None,
          'the boss said no; that is not an error: ' + tpl[:200])
    check('…but an unusable answer is answered out loud',
          'window.hqConfirm' in tpl and 'hideCancel: true' in tpl,
          'blank OK still closes the box and does nothing: ' + tpl[:300])
    check('…and the old collapse of null and "" is gone',
          "hqPrompt(" in tpl and "|| '').trim()" not in tpl,
          'cancel and blank must not be the same event')

    # ── §4 drive the real helper ───────────────────────────────────────
    if not shutil.which('node'):
        print('SKIP (node) — source checks above still ran')
        if FAILS:
            print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
            return 1
        print('PASS')
        return 0

    fn = lift(bare, 'function hireNeedsNote', 'const FRONT_DESK')
    js = ('const SRC = ' + json.dumps(fn) + ';\n' + r'''
const raw = new Function(SRC + ' return hireNeedsNote;')();
/* A brain, so the NAME answers are what is under test here — #356 taught
   the same door to refuse a hire with no brain at all, and that refusal
   has its own suite. */
const BRAIN = 'ollama:llama3.1:latest';
const hireNeedsNote = (name, roster = [], model = BRAIN) => raw(name, roster, model);
console.log(JSON.stringify({
  fresh:   hireNeedsNote(''),
  spaces:  hireNeedsNote('   '),
  tabs:    hireNeedsNote('\t\n '),
  typed:   hireNeedsNote('Nova'),
  padded:  hireNeedsNote('  Nova  '),
  // The form seeds `name` from a template or a prefill, and a state that
  // has not been set yet must not crash the render of the whole dialog.
  missing: hireNeedsNote(undefined),
  nulled:  hireNeedsNote(null),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted helper runs', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    note = r['fresh']
    check('the form exactly as it opens has a reason to give',
          bool(note), 'an empty note means HIRE ✓ is live and silent again')
    check('…and it is a sentence, not shorthand',
          len(note) > 30 and note.rstrip().endswith('.')
          and 'required' not in note.lower(),
          note)
    check('…that names the field by the label printed above the box',
          'NAME' in note, note)
    check('…and says what to do about it, not only what is wrong',
          'type' in note.lower(), note)
    check('whitespace is not a name',
          bool(r['spaces']) and bool(r['tabs']), [r['spaces'], r['tabs']])
    check('an absent name reads the same as an empty one',
          r['missing'] == note and r['nulled'] == note,
          'an unset state must not throw inside the render')
    check('a typed name clears the note and lets the button live',
          r['typed'] == '' and r['padded'] == '',
          [r['typed'], r['padded']])

    print()
    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())

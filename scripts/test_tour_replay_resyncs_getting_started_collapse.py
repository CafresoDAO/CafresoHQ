#!/usr/bin/env python3
"""Replaying the tour un-collapsed the checklist but left the pill-guard
believing it was still a pill — the exact collision the mobile fix chased.

Reproduced live (port 8914, fresh office, one hire so the 'chat' coach mark
had something to say): collapse the Getting Started checklist to its pill
("–" button — gsCollapsed=true, forwarded up via onCollapsedChange). Open
"Replay onboarding tour" from the command palette, then Skip. The checklist
card comes back FULLY EXPANDED — read_page showed a "Collapse" button, i.e.
the un-collapsed state — while the coach-mark pill ("Your first hire is at
their desk…", "Open chat", "Dismiss tip") was ALSO present in the same
read_page dump. Both surfaces on screen at once is precisely what
test_mobile_onboarding_layout.py's fix (2026-08-1x) was written to prevent,
reached here through a second door that fix didn't cover.

The mechanism: app.jsx renders <GettingStarted> conditionally —
`{!gsDismissed && !tourOpen && (<GettingStarted ... onCollapsedChange=
{setGsCollapsed} />)}` — so opening the tour (`tourOpen=true`) actually
UNMOUNTS the checklist, not just hides it. GettingStarted's own collapsed
flag is a plain `useState(false)` (ui/onboarding.jsx) with no memory of
what it was before, so the remount when the tour closes always comes back
EXPANDED. `gsCollapsed`, app.jsx's mirror of that flag — the one thing the
coach-mark guard `!tourOpen && coachMark && !(!gsDismissed && !gsCollapsed)`
actually reads — has no way to learn about that remount unless something
tells it, and nothing did: the tour's `onClose` only flipped `tourOpen` and
`tourSeen`. A boss who had collapsed the checklist, then replayed the tour
from the command palette and skipped it, got the fully expanded checklist
AND the coach-mark pill fighting for the same strip of screen — the mobile
fix's 155px collision, or the ~72-173px desktop clip at common widths,
neither of which needed a phone to reach anymore.

The fix: app.jsx's `onClose` on <OnboardingTour> now also calls
`setGsCollapsed(false)` — the one place that ends the unmount is the one
place that can make the mirror agree with what the child is about to look
like, since the child always remounts expanded regardless of what the
mirror last said.

This suite pulls the real guard expressions and the real onClose handler
out of app.jsx by their exact source text (not a hand-copied restatement)
and drives a small state-machine simulation through the measured timeline —
collapse, open tour, close tour — checking the two guards can never agree
to show both surfaces at once. It also confirms the premise the fix leans
on (GettingStarted always remounts at collapsed=false) still holds, and
that onCollapsedChange still forwards what it reports.

Run: python3 scripts/test_tour_replay_resyncs_getting_started_collapse.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
ONB = ROOT / 'ui' / 'onboarding.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def js_bool_eval(expr, env):
    """Mechanical JS-boolean -> Python-boolean translator: `&&`/`||`/`!`
    become `and`/`or`/`not`, then eval() against `env`. Only handles the
    subset these two guards actually use (no ternaries, no ==); this is a
    syntax transform of the REAL extracted expression, not a restatement
    of its logic — the operators, nesting and variable names all come
    from the source text being tested."""
    py = expr
    py = py.replace('&&', ' and ').replace('||', ' or ')
    py = re.sub(r'!(?!=)', ' not ', py)
    return bool(eval(py, {'__builtins__': {}}, dict(env)))


def extract_between(src, start_marker, end_marker, start_from=0):
    i = src.index(start_marker, start_from)
    j = src.index(end_marker, i + len(start_marker))
    return src[i + len(start_marker):j], i


def main():
    for p in (APP, ONB):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    app = APP.read_text(encoding='utf-8')
    onb = ONB.read_text(encoding='utf-8')

    print('tour replay vs. the Getting Started collapse mirror')

    # ── extract the two real JSX guards, verbatim ──────────────────────────
    # The guard's exact text is also quoted, verbatim, inside the explanatory
    # doc-comment above gsCollapsed's declaration (for a human reader) — a
    # bare whole-file substring search can't tell that comment apart from the
    # real render guard, and keeps passing even if the real guard changes
    # (measured: dropping `!tourOpen` from the real JSX left a naive
    # `marker in app` check green, because the comment alone still satisfied
    # it). Anchor on the actual JSX invocation instead: `<GettingStarted`
    # immediately followed by a newline only happens at the real multi-line
    # render site; the comment's abbreviated single-line `<GettingStarted
    # .../>` form never breaks there, so this can't match the comment.
    gs_m = re.search(r'\{(!gsDismissed[^\n]*)\(\s*\n\s*<GettingStarted\r?\n', app)
    check('found the GettingStarted mount guard at its real render site '
          '(not just the doc-comment quoting it)', bool(gs_m))
    mount_expr = gs_m.group(1).rstrip() if gs_m else '!gsDismissed'
    if mount_expr.endswith('&&'):
        mount_expr = mount_expr[:-2].strip()

    coach_marker = '{!tourOpen && coachMark && !(!gsDismissed && !gsCollapsed) && ('
    check('found the coach-mark visibility guard, unchanged',
          coach_marker in app,
          'app.jsx: this exact guard is what the fix leans on staying put')
    # Derived from the marker just checked, not retyped — if the guard in
    # app.jsx ever drifts from `coach_marker`, the check above fails first
    # and this stays byte-identical to what the marker declares.
    coach_expr = coach_marker[1:coach_marker.rindex('&& (')].strip()

    # ── extract the real onClose handler on <OnboardingTour> ──────────────
    tour_idx = app.index('<OnboardingTour')
    m = re.search(r'onClose=\{\(\) => \{([^}]*)\}\}', app[tour_idx:tour_idx + 2000])
    check('found a single-statement-block onClose on <OnboardingTour>', bool(m))
    onclose_body = m.group(1) if m else ''

    calls = re.findall(r'(set\w+)\((true|false|Date\.now\(\))\)', onclose_body)
    setters = {name: val for name, val in calls}
    check('onClose still closes the tour (setTourOpen(false))',
          setters.get('setTourOpen') == 'false')
    check('onClose still marks the tour seen (setTourSeen(true))',
          setters.get('setTourSeen') == 'true')
    # The fix under test.
    check('onClose resyncs the collapse mirror (setGsCollapsed(false))',
          setters.get('setGsCollapsed') == 'false',
          'app.jsx: without this, gsCollapsed survives the remount stale — '
          'see the state-machine checks below')

    # ── confirm the premise the fix depends on: the child always remounts
    #    expanded, and still reports every change it makes upward ──────────
    coll_m = re.search(r'const \[collapsed, \w+\] = useState\((true|false)\)', onb)
    check('GettingStarted still starts collapsed=false on every mount',
          bool(coll_m) and coll_m.group(1) == 'false',
          'ui/onboarding.jsx: the fix assumes a fresh mount is always '
          'expanded — if this ever seeds from a persisted/controlled '
          'value, onClose resetting gsCollapsed unconditionally would be '
          'the wrong fix')
    setcoll_body, _ = extract_between(onb, 'const setCollapsed = (v) => {', '};')
    # Drop `//` line-comments first — the literal statement text can survive
    # untouched inside a commented-out line (measured: prefixing the real
    # line with `//` left this exact substring in place and the check below
    # kept passing over dead code).
    setcoll_live = '\n'.join(
        ln for ln in setcoll_body.splitlines() if not ln.strip().startswith('//')
    )
    check('GettingStarted still forwards every collapse change upward',
          'if (onCollapsedChange) onCollapsedChange(v);' in setcoll_live,
          'ui/onboarding.jsx: without this the mirror never learns about '
          'a real collapse either, not just the remount case')

    # ── drive the actual measured timeline through the extracted rules ────
    def simulate(onclose_setters):
        """gsDismissed=false throughout (this bug is about a live checklist).
        Returns (checklist_expanded_on_screen, coach_pill_shown) after:
        collapse -> open tour -> Skip (onClose fires)."""
        state = {'gsDismissed': False, 'tourOpen': False, 'gsCollapsed': False}

        def child_mounted():
            return js_bool_eval(mount_expr, state)

        assert child_mounted()
        child_collapsed = False        # the checklist's OWN state while alive

        # 1. boss collapses it to a pill
        child_collapsed = True
        state['gsCollapsed'] = True    # onCollapsedChange(true), confirmed above

        # 2. boss opens "Replay onboarding tour" (a plain setTourOpen(true)
        #    elsewhere in app.jsx — not part of this fix, just the trigger)
        state['tourOpen'] = True
        assert not child_mounted()
        child_collapsed = None         # no checklist on screen to have a state

        # 3. boss hits Skip -> the REAL extracted onClose fires
        for name, val in onclose_setters.items():
            if name == 'setTourOpen':
                state['tourOpen'] = (val == 'true')
            elif name == 'setGsCollapsed':
                state['gsCollapsed'] = (val == 'true')
            # setTourSeen doesn't feed either guard; ignored here on purpose

        # 4. the checklist remounts — always expanded (confirmed above)
        assert child_mounted()
        child_collapsed = False

        checklist_expanded_on_screen = child_mounted() and not child_collapsed
        coach_pill_shown = js_bool_eval(coach_expr, {
            'tourOpen': state['tourOpen'],
            'coachMark': True,           # a real pending nudge, e.g. 'chat'
            'gsDismissed': state['gsDismissed'],
            'gsCollapsed': state['gsCollapsed'],
        })
        return checklist_expanded_on_screen, coach_pill_shown

    def safe_simulate(name, onclose_setters):
        """A source edit can break an assumption the state machine itself
        relies on (e.g. onClose no longer closing the tour at all) — that
        should read as a normal named failure, not an uncaught traceback
        that aborts every check still queued behind it."""
        try:
            return simulate(onclose_setters)
        except AssertionError as e:
            check(name, False, f'state-machine assumption violated: {e or "assert failed"}')
            return None, None

    expanded, pill = safe_simulate('the real onClose leaves the checklist reachably mounted', setters)
    if expanded is not None:
        check('after collapse -> replay -> Skip, the two surfaces never both show',
              not (expanded and pill),
              f'checklist_expanded={expanded}, coach_pill_shown={pill} — this is '
              'the exact collision measured live before the fix')

    # A run with the fix REMOVED must reproduce the measured bug — proves the
    # simulation isn't vacuously true regardless of what onClose does.
    broken_expanded, broken_pill = safe_simulate(
        'the no-fix timeline stays simulable', {'setTourOpen': 'false'})  # no setGsCollapsed
    if broken_expanded is not None:
        check('...and the simulation actually reproduces the bug without the fix',
              broken_expanded and broken_pill,
              'if this does not fail, the check above is not testing anything')

    # Sanity: replaying the tour while the checklist was NEVER collapsed
    # must stay harmless either way (gsCollapsed was already false).
    already_expanded, already_pill = safe_simulate(
        'the already-expanded timeline stays simulable',
        {'setTourOpen': 'false', 'setGsCollapsed': 'false'})
    if already_expanded is not None:
        check('replaying with the checklist already expanded stays harmless',
              already_expanded and not already_pill)

    print()
    if FAILS:
        print(f'tour replay vs. collapse mirror: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('tour replay vs. collapse mirror: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

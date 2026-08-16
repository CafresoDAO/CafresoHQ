#!/usr/bin/env python3
"""Every "click X in Y" sentence has to name a control the office renders.

Reproduced 2026-08-16 on a live office (127.0.0.1:9265, three coworkers
hired). The chat panel's RESEARCH thread is read-only — no composer — and
its two boss-facing sentences were:

    empty state : "No research yet. Click 🔬 RESEARCH in the topbar to
                   start a long-running research mission."
    banner      : "🔬 research feed — start or manage missions from the
                   topbar"

The topbar, read off the same page in the same second:

    LIVE · 0 WORKING · 3 HIRED · 📬 INBOX · ⌗ ROOMS ▾ · 🔔12

There is no 🔬 RESEARCH. The missions door is one level down, inside the
ROOMS menu, as "🔬 Research missions". A read-only thread whose only
instruction names a button nobody has is a dead end with directions
printed on it.

Same class, worse surface: the LAST step of the mobile first-run tour
said "Tap + HIRE in the topbar", targeting `.topbar .px-btn.primary`.
"+ HIRE" is a real label — it is printed inside every vacant desk — but
it has never been in the topbar, and that selector matched nothing.
`document.querySelector` returning null is not a no-op here: the tour's
spotlight only ever gets *set*, never cleared, when a step declares a
target, so the ring stayed exactly where the previous step left it.
Measured: step 'palette' put the spotlight at 315,632 (56×56, the
command-palette FAB) and step 'hire' rendered with the identical rect
while its card pointed at the top of the screen.

So this suite holds three things:

  1. no boss-facing sentence claims a control the topbar does not render
  2. the research thread hands over the door itself, not directions
  3. a tour step whose target cannot be resolved clears the spotlight
     rather than inheriting the last one

§5 (a wrong door is worse than a locked one) and §7 (an honest sentence
still needs a way forward).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
ONB = (ROOT / 'ui' / 'onboarding.jsx').read_text(encoding='utf-8')

FAILS = []


def check(label, ok, detail=''):
    if ok:
        print(f'  ok    {label}')
    else:
        FAILS.append(label)
        print(f'  FAIL  {label}' + (f'  — {detail}' if detail else ''))


def strip_jsx_comments(src):
    """Comments explain the fix; they are not what the boss reads.

    One pattern, not two. A first cut also matched `\\{\\s*/\\*.*?\\*/\\s*\\}`
    to take the braces off `{/* … */}` — and a bare comment sitting inside
    an ordinary `{` expression opened that match, whose closing `*/}` was
    then found twenty-three lines later at the end of a completely
    different comment. Everything between, including the markup this suite
    checks, vanished, and the check reported the banner missing when it was
    right there. Stripping only the comment bodies leaves a stray `{}`
    behind, which nothing here reads.
    """
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'(?m)^\s*//.*$', '', src)
    return src


def section(src, start, end):
    """A slice between two markers, or '' if either is missing."""
    a = src.find(start)
    if a < 0:
        return ''
    b = src.find(end, a)
    return src[a:b] if b > a else ''


print('the office points at controls it has')

# ── 1. what the topbar actually renders ──────────────────────────────────
# Read off the source rather than hardcoded, so this check keeps telling
# the truth when the topbar changes. The strip is everything between the
# LIVE/OFFLINE chip and the pinned cluster's comment banner.
topbar = section(APP, "{backendDown ? 'OFFLINE' : 'LIVE'}", '── Pinned. Never scrolls.')
check('the topbar strip is findable in app.jsx', bool(topbar),
      '— every check below reads it; a missing slice would pass them all')

TOPBAR_CLAIMS = [
    ('🔬 RESEARCH', 'the missions door is ⌗ ROOMS ▾ → 🔬 Research missions'),
    ('+ HIRE',      'the + HIRE label lives on a vacant desk, not up here'),
]
for label, why in TOPBAR_CLAIMS:
    present = label in topbar
    # Reading it the other way round: if some future round DOES put the
    # control in the topbar, the sentence naming it stops being a lie and
    # this check should stop objecting to it. So each pair is checked as
    # "claimed ⇒ rendered", not as a blanket ban on the words.
    claimed_in = []
    for name, src in (('ui/chat.jsx', CHAT), ('app.jsx', APP)):
        body = strip_jsx_comments(src)
        for m in re.finditer(re.escape(label), body):
            window = body[max(0, m.start() - 160):m.start() + 160]
            if 'topbar' in window:
                claimed_in.append(name)
                break
    check(f'nothing tells the boss to press "{label}" in the topbar',
          present or not claimed_in,
          f'— claimed in {sorted(set(claimed_in))} and the topbar renders '
          f'{"" if present else "no such control"}: {why}')

# ── 2. the research thread hands over the door ───────────────────────────
chat_body = strip_jsx_comments(CHAT)
check('ChatPanel takes the missions door as a prop',
      'onOpenResearch' in section(chat_body, 'function ChatPanel({', ') {'),
      '— without it the panel can only describe the way, and describing it '
      'is what went wrong')
# Scoped to the ChatPanel mount, not to the file. `onOpenResearch` is also
# passed to the mobile tab bar 460 lines further down, so a file-wide
# search answers yes even with the chat panel's copy deleted — the check
# would have been reading a different component's wiring.
shared_panel = section(APP, 'const sharedChatPanel = (', '/>')
check('...and app.jsx hands it in',
      'onOpenResearch={() => setMissionsOpen(true)}' in shared_panel,
      '— a prop nobody passes is the Roster checkbox all over again')

empty = section(chat_body, "activeThread === 'research' &&", "activeRoom && activeRoom.kind === 'project'")
check('the empty research thread renders the door, not directions to it',
      'onClick={onOpenResearch}' in empty,
      '— this thread has no composer, so a boss who cannot find the '
      'control has no second way to try')
check('...and still names the real path when the door was not handed in',
      '⌗ ROOMS' in empty,
      '— the fallback has to be a place that exists, not the old sentence')

banner = section(chat_body, "className=\"thread-readonly\"", '</div>')
check('the read-only banner offers the door too',
      'onOpenResearch' in banner and '⌗ ROOMS' in banner,
      '— it replaces the composer, so it is the only thing in the way')

# ── 3. an unfindable target stops pointing ───────────────────────────────
# Pinned to the shape, not to the presence of the call. A first cut asked
# whether `setSpotlight(null)` appeared anywhere below the retry line, and
# an arm that left the call sitting there behind an unconditional `return`
# passed it — the guard was present, unreachable, and reported healthy.
# Bounded to compute() as well. There is a second, legitimate
# `setSpotlight(null)` in the no-target `else` branch below this function,
# and an arm that deleted the give-up call reached forward and matched
# THAT one — a check satisfied by a line in a different code path.
compute_body = section(ONB, 'const compute = () => {', '\n      };')
give_up = re.search(
    r'if \(\+\+attempts < \d+\) \{ setTimeout\(compute, \d+\); return; \}(.*?)setSpotlight\(null\);',
    compute_body, re.S)
between = strip_jsx_comments(give_up.group(1)) if give_up else 'return'
check('a tour target that never resolves clears the spotlight',
      give_up is not None and 'return' not in between,
      '— falling out of the retry loop used to leave the ring where the '
      'PREVIOUS step put it: measured at 315,632 on the palette FAB while '
      'the card described a button in the topbar')

# Sliced from the `if (step.target)` arm, not from the whole effect: the
# no-target `else` two lines up also clears the spotlight, and a check
# reading the wider slice passed with the entry clear deleted.
entry = section(ONB, 'if (step.target) {', 'const compute')
check('...and a step with a target drops the old ring before resolving',
      'setSpotlight(null);' in entry,
      '— timed on the mobile first-run: the palette ring stayed put for '
      '~1s after the card had already changed to the hire step, because '
      'the spotlight was only ever replaced, never cleared on entry')
check('...with a retry budget long enough for a view to mount',
      re.search(r'\+\+attempts < (\d+)\) \{ setTimeout\(compute, (\d+)\)', ONB)
      is not None
      and (lambda m: int(m.group(1)) * int(m.group(2)) >= 2000)(
          re.search(r'\+\+attempts < (\d+)\) \{ setTimeout\(compute, (\d+)\)', ONB)),
      '— the floor took ~1.4s to render .mas-plus; six 80ms tries gave up '
      'at 0.5s, and now that the ring is cleared on entry, giving up early '
      'means no ring at all')

# Comments stripped first. The step carries a note explaining which
# selectors are real, and a check reading the raw slice found `.mas-plus`
# in that note and passed while the live target was the dead one.
hire_step = section(strip_jsx_comments(APP), "id: 'hire',", '];')
check('the mobile hire step targets a control that is rendered',
      '.mas-plus' in hire_step,
      '— .mas-plus is the mobile agent strip\'s +, rendered unconditionally; '
      '.topbar .px-btn.primary matched nothing on any viewport')
check('...and its words name the same control',
      'coworker strip' in hire_step or 'empty desk' in hire_step,
      '— a spotlight on one control and a sentence about another is the '
      'same wrong door with a ring around it')
check('...and the control it names exists on the floor',
      "className=\"mas-plus\"" in (ROOT / 'ui' / 'office.jsx').read_text(encoding='utf-8'),
      '— checked against the floor, not against the tour\'s own belief')

print()
if FAILS:
    print(f'FAILED {len(FAILS)} check(s):')
    for f in FAILS:
        print('  · ' + f)
    sys.exit(1)
print('all checks passed')

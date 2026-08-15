#!/usr/bin/env python3
"""Every record got the clean reply. The chat got the raw one.

Measured on a fresh office (port 9250, one hire, a brain answering "Here is
the answer." followed by a dangling harmony commentary block). Reading
localStorage afterwards:

    cafresohq_hq_v1:activity  detail: "Here is the answer."
    cafresohq_hq_v1:chat      text:   "Here is the answer.\\n\\n
                                       <|channel|>commentary
                                       to=functions.bash<|constrain|>json
                                       <|message|>{"command":"ls -la"}
                                       <|call|>"

The chat was the only key in the entire store holding a harmony token — the
one surface the boss actually reads.

Cause: four dispatch paths, four hand-written spellings of "clean this
reply", and on two of them the strongest spelling was not the one the
bubble got.

    @mention   bubble ← visibleReply(buf)                      ← weakest
               records ← cleanHarmony(visibleReply(stripToolEcho(buf, …)))
    delegate   both    ← cleanHarmony(visibleReply(buf))        ← no echo strip
    task       both    ← cleanHarmony(visibleReply(stripToolEcho(buf, …)))

The @mention path computed BOTH, two hundred lines apart, and handed the
weaker one to the chat. Its sibling's comment already names the shape —
"every record got cleanBuf, the bubble did not" — because the delegate path
had the same split and it was fixed there; this one was left, and it is the
busiest route in the app.

Two sources, one rule. The @mention path now has a single `dress()` that
both readers call, and every visibleReply in app.jsx goes through the same
three strips in the same order: echoes out, markers out, harmony out.

Run: python3 scripts/test_the_bubble_gets_the_same_clean.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
APP = ROOT / 'app.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


# The exact bytes the canned brain streamed back on the run above.
MEASURED = ('Here is the answer.\n\n<|channel|>commentary to=functions.bash'
            '<|constrain|>json<|message|>{"command":"ls -la"}<|call|>')
# A coworker parroting the tool's own output back at the boss. `echo` is
# what the tool runner recorded; the reply repeats it verbatim.
# The blank-line gap is deliberate: visibleReply collapses \n{3,}, so an
# echo run through it first no longer matches the string the tool runner
# recorded. That is why stripToolEcho has to go first, and this is the
# shape that proves it rather than asserting it.
ECHO = 'total 8\n\n\ndrwxr-xr-x  2 you  staff   64 Aug 14 10:00 .'
PARROT = 'I ran it. Here is what came back:\n\n' + ECHO + '\n\nSo the folder is empty.'


def main():
    print('the bubble is cleaned with the same recipe as the records')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = RUNTIME.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    artifacts = ARTIFACTS.read_text(encoding='utf-8')

    # ── 1. the composed recipe, run for real ────────────────────────────
    # Lifted from the real files rather than restated, so a rewrite of any
    # of these is measured here instead of quietly diverging.
    js = re.search(r'^const PLACEHOLDER_ARG\s*=.*?;$', src, re.M).group(0) + '\n'
    # Every ORPHAN_TAG_* const, in file order so dependencies resolve. A
    # prefix sweep, not a pinned literal shape: this lift used to match
    # `const ORPHAN_TAG_RE =\n  /.../gim;` exactly, and #81 split that literal
    # into a shared vocabulary plus two anchorings, which crashed this suite
    # on a NoneType instead of reporting. Whatever the next split looks like,
    # it keeps the prefix.
    orphan = [c.group(0) for c in
              re.finditer(r'^const ORPHAN_TAG_\w+\s*=[\s\S]*?;$', src, re.M)]
    if not orphan:
        raise SystemExit('could not find any ORPHAN_TAG_* const')
    js += '\n'.join(orphan) + '\n'
    # placeholderRefusal and unsentBlocks are only reached when the reply
    # cleans down to nothing — which is exactly the case a bad strip
    # produces, so leaving them out made the harness crash instead of
    # report on the one input that matters most. Found by fire-testing.
    for fn in ('extractAcks', 'stripAcks', 'stripOrphanTags', 'stripBlocks',
               'stripSelfLabel', 'extractAllDMs', 'isHandoffPlaceholder',
               'placeholderRefusal', 'unsentBlocks', 'extractApproval',
               'shownBody', 'visibleReply', 'cleanHarmony'):
        js += brace_lift(src, 'function ' + fn + '(') + '\n'
    js += brace_lift(artifacts, 'function stripToolEcho(') + '\n'
    js += r'''
/* The recipe as app.jsx spells it, in app.jsx's order. */
const dress = (t, echoes, self) =>
  cleanHarmony(visibleReply(stripToolEcho(t, echoes), self));
console.log(JSON.stringify({
  measured:  dress(%s, [], 'Local Brain'),
  parrot:    dress(%s, [%s], 'Local Brain'),
  /* The echo strip moved to the outside, which is where it reads as the
     more natural spelling and where it silently stops working. */
  echoLast:  stripToolEcho(cleanHarmony(visibleReply(%s, 'Local Brain')), [%s]),
  plain:     dress('Yellow.', [], 'Local Brain'),
}));
''' % (json.dumps(MEASURED), json.dumps(PARROT), json.dumps(ECHO),
       json.dumps(PARROT), json.dumps(ECHO))
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr[-1600:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    R = json.loads(proc.stdout.strip().split('\n')[-1])

    check('the measured reply loses its harmony block',
          '<|' not in R['measured'],
          repr(R['measured']) + ' — these are the exact bytes that reached '
          'the boss on port 9250')
    check('...and keeps the sentence the coworker actually wrote',
          R['measured'].strip() == 'Here is the answer.',
          repr(R['measured']) + ' — cleaning is not the same as deleting; if '
          'this fires the strip has eaten the reply')
    check('a parroted tool result is taken back out',
          'drwxr-xr-x' not in R['parrot'],
          repr(R['parrot']) + ' — the visit block already shows the boss '
          'where the coworker went and what came back')
    check('...and what they said about it survives',
          'So the folder is empty.' in R['parrot'], repr(R['parrot']))
    # Written backwards the first time, and the miss is worth keeping: the
    # literal ECHO is NOT in `echoLast` either, because visibleReply
    # collapsed the blank line inside it. The string is gone; the tool
    # output is still on the screen. What proves the ordering is the
    # CONTENT surviving, not the exact bytes — an equality test here would
    # have reported the broken order as fixed.
    check('...which is why the echo strip has to run first',
          'drwxr-xr-x' in R['echoLast'] and 'drwxr-xr-x' not in R['parrot'],
          repr(R['echoLast']) + ' — stripToolEcho matches the exact string '
          'the tool runner recorded, so anything that reformats the reply '
          'first (visibleReply collapses \\n{3,}) leaves it matching '
          'nothing and removing nothing')
    check('an ordinary reply passes through untouched',
          R['plain'].strip() == 'Yellow.', repr(R['plain'])
          + ' — the overwhelming majority of replies have nothing to strip, '
            'and a recipe that damages those is worse than the leak')

    # ── 2. one recipe, every reader ─────────────────────────────────────
    calls = [m.start() for m in re.finditer(r'HQ\.visibleReply\(', app)]
    check('the sweep found the dispatch paths at all', len(calls) >= 3,
          f'{len(calls)} visibleReply call(s) in app.jsx — if this drops the '
          'checks below pass by measuring nothing')

    naked_harmony, naked_echo = [], []
    for i in calls:
        line = app[:i].count('\n') + 1
        before = app[max(0, i - 200):i]
        after = app[i:i + 200]
        if 'HQ.cleanHarmony(' not in before:
            naked_harmony.append(line)
        if 'stripToolEcho(' not in after:
            naked_echo.append(line)
    check('every reply the boss reads has the harmony taken off it',
          not naked_harmony,
          f'app.jsx lines {naked_harmony} call visibleReply with no '
          'cleanHarmony around it — this is the measured defect')
    check('...and the tool echoes too, stripped first',
          not naked_echo,
          f'app.jsx lines {naked_echo} skip stripToolEcho — it has to be '
          'INSIDE visibleReply, because the echo is what makes an otherwise '
          'empty reply look like an answer')

    # The @mention path is the one that computed the recipe twice at two
    # different strengths. It now has one, and both readers call it.
    dress = re.search(r'const dress = \(t\) =>[\s\S]{0,300}?\);', app)
    check('the @mention path spells the recipe once',
          dress is not None,
          'the two readers on that path — the bubble and cleanBuf — used to '
          'be written out separately, which is how they came to disagree')
    check('...and both of its readers go through it',
          len(re.findall(r'\bdress\(buf\)', app)) >= 2,
          f"{len(re.findall(r'dress[(]buf[)]', app))} reader(s) call it — the "
          'bubble and the records both have to, or the split is back')

    # ── 3. the records are still getting theirs ─────────────────────────
    # The fix moves the bubble UP to the records' recipe. If it ever moves
    # the records DOWN instead, every check above still passes.
    # Counted, not merely present. Three dispatch paths feed the desk
    # monitor, and an existence test stayed green while one of them was
    # handed the raw buffer — the arm that levels the records DOWN to the
    # bubble is precisely the regression this section exists to catch.
    for name, anchor, want in (
            ('desk monitor', r'screen\.done\(cleanBuf\)', 3),
            ('journal', r'appendJournal\([^)]*cleanBuf', 1)):
        n = len(re.findall(anchor, app))
        check(f'the {name} still reads the cleaned reply on every path',
              n >= want,
              f'{n} of {want} sites match {anchor!r} — levelling the two '
              'recipes must level them UP')

    print()
    if FAILS:
        print(f'same clean: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('same clean: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

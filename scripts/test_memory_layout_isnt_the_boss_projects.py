#!/usr/bin/env python3
""""projects/" meant two different folders, and the office taught both.

Drove the checklist's step 5 to its promise — "your coworkers build docs,
decks, code & sites here" — on a live office: added a real local project
called "Site Check", put Nova on it from the Workspace's own Agents panel,
and asked, in the chat:

    @Nova Please create a file called index.html in the Site Check project
    folder — a simple one-page site …

Nova answered:

    The index.html file has been created in the projects/Site%20Check/
    folder with the requested content.

A file really was written. Not there. It landed in

    vault/Agents/Nova/projects/Site%20Check/index.html

— the coworker's own private notes — and the boss's project folder stayed
empty, as did the Workspace Files tab they were looking at while it
happened. The office's activity ledger recorded the whole thing as
"finished and reported back ✓".

The cause is the office's own vocabulary, not the model's judgement. The
memory prompt suggested a layout — "decisions/<topic>.md, references/…,
preferences.md, projects/<slug>.md" — and `projects/` is the one word in
that list the product had already spent: the Projects view, the folder you
add in Add Project, the Workspace you watch. Told to put a file in the
project folder, the coworker used the layout the office had just handed it,
slugged "Site Check" the way a URL would, and filed it privately. Every
step of that is the office's instruction being followed.

So the suggestion is "work/<slug>.md" now, which collides with nothing, and
the empty-memory note says outright that these are the coworker's own notes
and that a file the boss asked for goes to the project via FILE_WRITE.

What this does NOT claim to fix: whether an 8B-class model reliably picks
FILE_WRITE at all. The ledger already records that ceiling, measured
separately. This removes a trap the office set, which is the half that was
ours.

Run: python3 scripts/test_memory_layout_isnt_the_boss_projects.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RT = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


src = RT.read_text(encoding='utf-8')
print('memory layout — a coworker\'s notes are not the boss\'s Projects')

# Comments are stripped first: both fixes are explained in comments that
# quote the old string, and a guard that trips on its own rationale is a
# guard the next person deletes. (Same reasoning as
# test_delegate_says_only_what_was_asked.py.)
code = re.sub(r'/\*[\s\S]*?\*/', '', src)
code = re.sub(r'(?m)^\s*//.*$', '', code)

# ── 1. the collision is gone from every live suggestion ─────────────────
hits = re.findall(r'projects/<slug>', code)
check('no suggested memory path starts with the boss\'s word for a project',
      not hits,
      f'{len(hits)} live occurrence(s) of "projects/<slug>" in hq-runtime.jsx — '
      'this string is read by a coworker with an empty memory, so it is the '
      'layout every first write follows')

# ── 2. …and something is still suggested ────────────────────────────────
# Deleting the layout entirely would pass the check above and leave a
# coworker with no shape at all for its notes.
for label, pat in (('the MEMORY_WRITE doc', r'Examples of good memory:[^\']*work/<slug>\.md'),
                   ('the empty-memory note', r'Suggested layout:[^`]*work/<slug>\.md')):
    check(f'{label} still offers a layout, under a neutral word',
          re.search(pat, code) is not None,
          'hq-runtime.jsx: the fix is a RENAME, not a deletion — a coworker '
          'with no suggested shape files notes wherever it guesses')

# ── 3. the distinction is stated, not just implied ──────────────────────
# The rename alone stops the office POINTING at the wrong folder; it does
# not tell a coworker which folder the boss meant. That sentence is what
# makes "in the Site Check project folder" resolvable.
note = re.search(r'Save the first note with[^`]*', code)
check('the empty-memory note exists to check', bool(note), 'hq-runtime.jsx')
body = note.group(0) if note else ''
check('...and says these notes are not the boss\'s Projects',
      re.search(r"your OWN notes, not the boss's Projects", body),
      repr(body[-200:]) + ' — without this, "put it in the project folder" '
      'still has two readings and only one of them is visible to the boss')
check('...and names the marker that reaches the project',
      'FILE_WRITE' in body,
      'hq-runtime.jsx: naming the wrong destination without naming the right '
      'one leaves the coworker to guess again')

# ── 4. nothing else quietly reintroduced it ─────────────────────────────
# The prompt is assembled from several strings; a later one adding
# "projects/" back would restore the trap without touching the two above.
stray = [m for m in re.findall(r'"[^"\n]*projects/[^"\n]*"|`[^`\n]*projects/[^`\n]*`', code)
         if 'FILE_WRITE' not in m]
check('no other live prompt string points a coworker at "projects/"',
      not stray, f'{stray[:2]} — hq-runtime.jsx')

print()
if FAILS:
    print(f'memory layout: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
    sys.exit(1)
print('memory layout: all checks passed')

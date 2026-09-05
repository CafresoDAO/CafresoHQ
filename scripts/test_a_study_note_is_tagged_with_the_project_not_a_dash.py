#!/usr/bin/env python3
"""A project study note is tagged with the project, not with a bare dash.

`#279` fixed the Latin-only slug in modals/starter.jsx; `#285` found its twin
in app/artifacts.jsx and missions.jsx `topicSlug`. This is the THIRD site of
the same class, and it survived both passes because it names a TAG rather
than a path — nothing about it looked like filing.

The mission brief told every studying coworker to stamp its notes with
`tags: [project-study, <project>]`, building that second tag by the same
`[^a-z0-9]` deletion. A project named in Japanese, Russian, Greek, Hebrew,
Arabic or Korean has no character that survives, so the whole name collapsed
to the single character `-`: every note, of every project, in every
non-English office, carrying one identical tag. The tag index is how a note
is found again months later; one shared tag across all projects is the same
as no tag at all — and unlike the path bugs, nothing on screen looks wrong.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails = []


def ok(label, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + label
          + (('  — ' + str(detail)) if detail and not cond else ''))
    if not cond:
        fails.append(label)


raw = (ROOT / 'missions.jsx').read_text()
# Strip comments first. Both this fix and #285's explain the old bad slug in
# prose directly above the good code, so a check that reads the raw file
# finds `[^a-z0-9]` in a comment and calls a fixed file broken. Measure the
# code, never the commentary about it.
src = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
src = '\n'.join(re.sub(r'(^|\s)//.*$', '', l) for l in src.split('\n'))

# --- The brief must not build the tag with the Latin-only slug ------------
tag_line = next((l for l in src.split('\n') if 'tags: [project-study' in l), '')
ok('the brief still stamps a project-study tag', bool(tag_line))
ok('...and does NOT build it by deleting every non-Latin character',
   '[^a-z0-9]' not in tag_line, tag_line.strip())
ok('...it asks topicSlug, the function that answers this correctly',
   'topicSlug(' in tag_line, tag_line.strip())

# No Latin-only slug is left anywhere in this file.
ok('no [^a-z0-9] slug survives anywhere in missions.jsx',
   '[^a-z0-9]' not in src,
   [l.strip() for l in src.split('\n') if '[^a-z0-9]' in l])

# --- topicSlug itself keeps the properties the path fixes depended on -----
m = re.search(r'function topicSlug\(topic\) \{(.*?)\n\}', src, re.S)
ok('topicSlug is present', bool(m))
body = m.group(1) if m else ''
ok('topicSlug matches letters and numbers in any script',
   r'\p{L}' in body and r'\p{N}' in body, body)
ok('...with the unicode flag, or the property escapes are inert',
   re.search(r'/gu\b|/ug\b', body) is not None, body)

# --- Behaviour: drive the real function under node ------------------------
import json
import subprocess
import tempfile

harness = '''
%s
const out = [];
for (const name of %s) out.push([name, topicSlug(name)]);
console.log(JSON.stringify(out));
''' % (m.group(0) if m else 'function topicSlug(){return ""}',
       json.dumps(['顧客への提案メール', 'Стратегия', 'Ελληνικά',
                   'מיזם', 'مشروع', '프로젝트', 'Billing Service']))

with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as fh:
    fh.write(harness)
    path = fh.name
try:
    res = subprocess.run(['node', path], capture_output=True, text=True, timeout=30)
    rows = json.loads(res.stdout.strip().split('\n')[-1]) if res.returncode == 0 else []
except Exception as e:                                    # node absent, etc.
    rows = []
    print('  note  could not run node (%s) — source checks only' % e)

if rows:
    slugs = [s for _n, s in rows]
    ok('no project name collapses to a bare dash',
       '-' not in slugs and '' not in slugs, rows)
    ok('...and the non-Latin names do not all collide',
       len(set(slugs)) == len(slugs), rows)
    for name, slug in rows:
        ok('%r keeps something of itself (%r)' % (name, slug),
           slug not in ('-', '', 'untitled'), (name, slug))

print()
if fails:
    print('FAILED %d check(s): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('a study note is tagged with the project, not a dash: all checks passed')

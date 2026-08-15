#!/usr/bin/env python3
"""The board went green over a sentence in the future tense.

Measured on a fresh office, first task, the LAN brain, cabinet configured
and working. Brief: "Write a 400-word briefing on why sourdough starters
need feeding, and file it in the vault." The board marked it DONE, and the
whole deliverable was:

    I will write a 400-word briefing explaining the necessity of feeding
    sourdough starters and save it to the vault under
    `Drafts/Sourdough_Feeding_Briefing.md`.

No such file. The filed sheet carried that sentence as the deliverable and
then, eight lines below, its own Working record said "Nothing opened, saved
or looked up for this one." Two true records of one run, disagreeing, and
neither pointing at the other — the exact inverse of 6cf5957, where the
footer was the false one.

The office is NOT asked whether prose is "only an intention". That is
judging the writing, and §4 says detection is a hint, not a verdict. It is
asked something it knows exactly: a path was named, and nothing was written
to the cabinet. Those two facts contradict each other on their face, the
same way a citation dated next year is arithmetic rather than an accusation.

So the detector reads a SHAPE, never a meaning: folder, slash, document
extension. What that buys and what it costs are both pinned below, because
the cost is the interesting half — a miss loses the caveat, a false alarm
calls an honest coworker a liar, and the second is the expensive one.

The other half of this is reach. 0a3e586 is the tick where a caveat that
lived on one surface out of four was found not to be a caveat at all, and
unverifiedSources' own comment records the same lesson twice more. This one
goes into `honestyNotes`, which is the function whose whole job is being the
single copy, so chat, the activity row and the task card get it from one
push; the filed sheet needs its own line because it is built somewhere else
entirely. Four surfaces, two call sites, and this test checks both.

Run: python3 scripts/test_a_promised_file_was_never_written.py
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_artifacts import pure_source, run_js  # noqa: E402

RUNTIME = ROOT / 'hq-runtime.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'
APP = ROOT / 'app.jsx'
FAILS = []


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


def main():
    print('a promised file that was never written')
    runtime = RUNTIME.read_text(encoding='utf-8')
    artifacts = ARTIFACTS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    # ── one copy, and it is the shared one ───────────────────────────────
    check('the note is pushed from honestyNotes',
          re.search(r'push\(unfiledPath\(raw, o\.visits\)\);', runtime),
          'a guard wired into one dispatch path out of three is the defect '
          'unverifiedSources was moved here to stop repeating')
    sites = re.findall(r'HQ\.honestyNotes\(raw, \{', app)
    check('...which all three dispatch paths still call', len(sites) == 3,
          f'{len(sites)} of 3 — @mention, Delegate and a task run; if one '
          'stopped calling it, this note silently covers two surfaces')
    check('...and every one of them still hands over the visits',
          len(re.findall(r'visits: toolVisits', app)) >= 3,
          'unfiledPath returns null on a non-array, so a path that forgot '
          'to pass visits would go quiet rather than fail loudly')
    # The sheet still says it in its own words — the WORDING is per-surface,
    # because the sheet is talking about itself and the chat note is not. The
    # DETECTION is not: #82 found both doors carrying their own copy of it and
    # both copies asking the same half-question, so they now share one
    # function. See scripts/test_a_file_it_just_opened.py.
    check('the filed sheet gets its own line',
          re.search(r'const promised = unwrittenPaths\(body, visits\);', artifacts),
          'buildDelivery runs in another file and shares no code with the '
          'chat path — the sheet is the record that outlives the session')
    check('...and reads the same detection the chat note does',
          re.search(r'function unwrittenPaths\(text, visits\)', artifacts)
          and 'unwrittenPaths' in re.search(r'^import .*artifacts\.jsx.;', runtime,
                                            re.M).group(0),
          'agentFiledPath answers "what was written", claimedPaths "what was '
          'named" and unwrittenPaths the difference; two copies of that '
          'subtraction is what #82 was')
    check('...and comes in as a parameter, not a closure over the import',
          re.search(r'function unfiledPath\(text, visits, unwrittenFn\)', runtime)
          and re.search(r'\(unwrittenFn \|\| unwrittenPaths\)\(text, visits\)', runtime),
          'test_reply_hygiene lifts these functions out to run under node, '
          'and a lifted function that calls an import is a ReferenceError')

    # The comment that said this was undetectable is gone. It was half right
    # for two months, and the wrong half is why nothing was built.
    check('the sheet no longer claims the office cannot detect this',
          'The office cannot\n       detect the claim' not in artifacts
          and 'guessing which sentences are claims' in artifacts,
          'the old comment reasoned from "guessing which SENTENCES are '
          'claims would be editing" to "so nothing can be done" — the '
          'premise is right and the conclusion never followed')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    # ── what the shape does and does not catch ───────────────────────────
    # run_js already prepends floor.jsx + artifacts.jsx; only the runtime
    # half needs lifting in, or every shared helper gets declared twice.
    scope = brace_lift(runtime, 'function unfiledPath(')
    MEASURED = ('I will write a 400-word briefing explaining the necessity of '
                'feeding sourdough starters and save it to the vault under '
                '`Drafts/Sourdough_Feeding_Briefing.md`.')
    cases = {
        # Verbatim from the run that produced this test.
        'measured':   (MEASURED, []),
        # The same claim on a run that DID file something. Two names for one
        # file is indistinguishable from filing twice, so we say nothing.
        'filed':      (MEASURED, [{'name': 'VAULT_NEW', 'arg': 'Drafts/x.md'}]),
        # A cabinet write under a different marker still counts.
        'exported':   (MEASURED, [{'name': 'EXPORT_DOCX', 'arg': 'Docs/x.docx'}]),
        # A run that opened things but wrote nothing is still a promise.
        'read_only':  (MEASURED, [{'name': 'BROWSER_FETCH', 'arg': 'https://x.dev'}]),
        # MEMORY_WRITE is the coworker's own notes folder, not the cabinet.
        'memo_only':  (MEASURED, [{'name': 'MEMORY_WRITE', 'arg': 'Agents/L/n.md'}]),
        # No path named at all — nothing to contradict.
        'no_path':    ('Yellow.', []),
        # A folder with no file is not a filing claim.
        'folder':     ('I saved it in the Drafts folder for you.', []),
        # A URL is a page it read, not a file it filed.
        'url':        ('See https://example.com/docs/report.md for detail.', []),
        # ...including a bare host with no scheme.
        'bare_host':  ('Pulled it from example.com/report.md this morning.', []),
        # Unknowable: a path that never counted its visits accuses nobody.
        'no_visits':  (MEASURED, None),
        # Two promises get one sentence, both named. Worth its own case
        # because a segment that admitted spaces matched the whole phrase
        # as ONE path and quoted the boss a filename nobody ever wrote.
        'two':        ('Filed to Research/a.md and also Reports/b.md.', []),
        # A space in a segment is a deliberate miss, not a mismatch: the
        # caveat is lost, and nothing false is printed in its place.
        'spaced':     ('Saved to Research/My Notes.md for you.', []),
    }
    js = 'const R = {};\n' + '\n'.join(
        'R[%s] = unfiledPath(%s, %s);' % (json.dumps(k), json.dumps(v[0]), json.dumps(v[1]))
        for k, v in cases.items()) + '\nconsole.log(JSON.stringify(R));'
    r = run_js(scope + '\n' + js)

    check('the measured reply is contradicted',
          r['measured'] and 'Drafts/Sourdough_Feeding_Briefing.md' in r['measured']
          and 'not there' in r['measured'],
          f"{r['measured']} — this is the exact text the board called DONE")
    check('...and the note names the file rather than scolding',
          r['measured'] and 'nothing was written to the cabinet' in r['measured']
          and 'claim' not in r['measured'].lower(),
          f"{r['measured']} — §7 wants the fact, not a verdict on the writer")
    check('a run that filed something says nothing', r['filed'] is None,
          f"{r['filed']} — the office cannot tell a second name for one file "
          'from a coworker filing twice, and only one of those is a defect')
    check('...under any cabinet marker, not just VAULT_NEW', r['exported'] is None,
          f"{r['exported']} — EXPORT_DOCX lands a real file in the cabinet")
    check('reading is not filing', r['read_only'] is not None,
          f"{r['read_only']} — a busy visit log is not a written file, and "
          'this is the run where the promise is easiest to believe')
    check('the private notes folder is not the cabinet', r['memo_only'] is not None,
          f"{r['memo_only']} — MEMORY_WRITE is Agents/<name>/, deliberately "
          'excluded from CABINET_WRITE for the same reason')
    check('no path named, nothing said', r['no_path'] is None,
          f"{r['no_path']} — most replies name no file and must stay silent")
    check('a folder alone is not a filing claim', r['folder'] is None,
          f"{r['folder']} — the shape needs a slash and an extension so that "
          'ordinary sentences about the vault cost nothing')
    check('a URL is a page it read, not a file it filed', r['url'] is None,
          f"{r['url']} — calling this a false filing would be the §7 failure "
          'pointed at an honest coworker')
    check('...including one with no scheme', r['bare_host'] is None,
          f"{r['bare_host']} — the dot in the first segment is what tells "
          'example.com/report.md from Drafts/report.md')
    check('a path that counted no visits accuses nobody', r['no_visits'] is None,
          f"{r['no_visits']} — absent is not empty; this is the same rule "
          'unverifiedSources states and for the same reason')
    check('two promises are named in one sentence',
          r['two'] and 'Research/a.md' in r['two'] and 'Reports/b.md' in r['two']
          and ' are named above' in r['two'],
          f"{r['two']} — and the verb agrees, because a note that reads as "
          'machine output gets ignored like machine output')
    check('a path with a space is missed rather than mangled',
          r['spaced'] is None,
          f"{r['spaced']} — losing the caveat is the cheap failure; quoting "
          'a filename that was never written is the expensive one')

    # ── the sheet says it too, and says it differently ───────────────────
    build = ('const T = { title: "Brief" }, A = { name: "Local Brain" };\n'
             'const R = {};\n'
             'R.promise = buildDelivery(T, A, %s, []).content;\n'
             'R.filed = buildDelivery(T, A, %s, [{name:"VAULT_NEW",arg:"Drafts/x.md"}]).content;\n'
             'console.log(JSON.stringify(R));' % (json.dumps(MEASURED), json.dumps(MEASURED)))
    b = run_js(build)
    check('the filed sheet contradicts the promise in its own record',
          '`Drafts/Sourdough_Feeding_Briefing.md` is named above' in b['promise'],
          'this is the sheet that carried the promise and the empty Working '
          'record together, and it is the copy that outlives the session')
    check('...and says which file the boss actually got',
          'this sheet is the only file it produced' in b['promise'],
          'a delivery sheet WAS written, so "nothing was filed" would be its '
          'own false statement — §7 wants the way forward, not just the no')
    check('...and stays quiet when the coworker really filed',
          'is named above' not in b['filed'],
          'the same reply on a run that wrote the file is not a defect')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

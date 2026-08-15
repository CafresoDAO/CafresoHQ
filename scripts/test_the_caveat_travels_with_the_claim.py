#!/usr/bin/env python3
"""The office spotted invented sources and told exactly one surface.

Measured on a fresh office, first task, local Llama, no search key. The
starter brief asks in so many words: "Say where each finding came from —
if you searched, name the source; if it came from what you already know,
say so plainly. Never invent a citation." What came back cited CB
Insights, Gartner and Clarity. Nothing had been opened; the run made zero
tool calls.

The office knew. `buildDelivery` in app/artifacts.jsx pairs an empty
Working record with `citesOutside(body)` and writes the caveat into the
filed note — "nothing was opened or searched while it was written — treat
those as recalled, not checked" — directly beneath the claim. It was
there, correct, in the .md.

It was in nothing else. The chat bubble the boss reads first: citations
alone. The task card in DONE, which they open days later when chat has
scrolled and the ticker has rolled over: citations alone. The activity
row's detail: citations alone. Three surfaces out of four showed a
confident sourced-looking brief, and the only one that told the truth is
the one you have to go looking for.

The fix moves the judgement into `honestyNotes`, whose own comment is a
record of this exact failure happening twice before ("Three dispatch paths
each grew their own copy of this block … copies drift"). From there chat
gets it through `flush.note` and the activity row through
`honesty.join(' ')`, on all three paths, and the task card is patched
alongside the row that already carried it.

Two things this pins that are easy to get wrong later:

- No visits list is not an empty visits list. A path that does not track
  what it opened knows nothing about whether anything was opened, and
  accusing a coworker of inventing sources on that basis is §7 pointed the
  wrong way. Unknowable → say nothing.
- The detector stays narrow. `citesOutside` deliberately ignores prose
  citations, and a real second run proved why that is load-bearing: Llama
  wrote "a 2020 study by Gajendran & Harrison" with no Source: tag and the
  guard correctly stayed quiet. Widening it to catch that shape would
  start flagging ordinary sentences.

Run: python3 scripts/test_the_caveat_travels_with_the_claim.py
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

CAVEAT = 'recalled, not checked'


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


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)//.*$', '', src)


def main():
    print('a caveat that stays in the filing cabinet is not a caveat')
    runtime = RUNTIME.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    artifacts = ARTIFACTS.read_text(encoding='utf-8')

    # ── 1. the guard lives with the other guards, not on one path ────────
    check('the sources guard is a guard, in the one place guards live',
          'function unverifiedSources(' in runtime,
          'honestyNotes exists so these checks have exactly one copy')
    notes = brace_lift(runtime, 'function honestyNotes(raw, opts) {')
    check('...and honestyNotes actually calls it',
          re.search(r'push\(unverifiedSources\(shown,\s*o\.visits\)\)', notes),
          notes)

    # ── 2. all three dispatch paths hand it the run's visits ─────────────
    # Derived, not hardcoded: every honestyNotes call site must pass visits.
    sites = re.findall(r'HQ\.honestyNotes\(raw, \{[^}]*\}', app)
    check('every dispatch path was found', len(sites) == 3,
          f'{len(sites)} honestyNotes call sites in app.jsx, expected 3')
    for i, s in enumerate(sites):
        check(f'dispatch path {i + 1} passes the run\'s visits',
              'visits:' in s,
              s.replace('\n', ' ')[:120] + ' — without this the guard '
              'cannot fire on this path, silently')

    # Each path's own body must both declare a visit list and fill it. The
    # delegate path had neither before this fix, so `visits:` would have
    # handed the guard an undefined and it would have gone quiet forever.
    bounds = [m.start() for m in re.finditer(r'HQ\.honestyNotes\(raw, \{', app)] + [len(app)]
    for i in range(len(bounds) - 1):
        # The declaration sits above the call site on two of the three paths
        # and below it on the third, so look both ways — but never past a
        # neighbouring path, or one path's array vouches for another's.
        lo = max(bounds[i] - 2500, (bounds[i - 1] + 1) if i else 0)
        body = app[lo:min(bounds[i + 1], bounds[i] + 14000)]
        check(f'dispatch path {i + 1} declares a visit list',
              'const toolVisits = [' in body,
              '`visits: toolVisits` with no such array is a ReferenceError '
              'or, worse, a silently undefined guard')
        check(f'dispatch path {i + 1} fills it as tools come back',
              'toolVisits.push(' in body,
              'onTool fires but nothing collects the visit, so the guard '
              'sees an empty list and accuses a coworker who did work')

    # ── 3. unknowable is not the same as zero ────────────────────────────
    guard = brace_lift(runtime, 'function unverifiedSources(text, visits, citesFn, workingFn) {')
    check('a path that does not count visits is never accused',
          'if (!Array.isArray(visits)) return null;' in guard,
          'undefined visits must mean "no idea", not "opened nothing" — '
          'the same do-not-promise rule pointed the other way')

    # ── 4. all four surfaces, derived from the task path itself ──────────
    task_start = app.index('skipKinds: deliveryFiled')
    done = app[app.index('honesty = honestyFor(buf);', task_start):]
    done = done[:done.index('} catch (err) {')]
    plain = strip_comments(done)
    check('the activity row carries the notes',
          re.search(r'detail:\s*honestyText', plain), plain[:200])
    check('the task card in DONE carries them too',
          re.search(r'result:\s*honestyText \+ cleanBuf', plain),
          'the card outlives the chat and the ticker; it stored the body '
          'alone')
    check('...and both use the same text, not two spellings of it',
          plain.count('honestyText') >= 3, plain.count('honestyText'))
    check('chat still gets them through flush.note',
          re.search(r'for \(const n of honesty\) if \(flush && flush\.note\) flush\.note\(n\)', app),
          'the fourth surface, and the first one the boss reads')

    # ── 5. run the real thing ────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arm')
        return 1 if FAILS else 0

    # The guard and the real detector, lifted verbatim -- reimplementing
    # `citesOutside` here would let this pass while the app is broken, and
    # it is the subtle half: OWN_HEAD is what keeps the office from flagging
    # the compliant answer.
    #
    # `workingNotes` is injected instead of lifted. It reaches down into the
    # floor's whole visit vocabulary (visitLine -> visitSubject -> ...), and
    # the only thing this guard asks of it is empty or not, which a two-line
    # stand-in answers exactly as well. `workingFn` exists for this.
    #
    # 2026-08-14: `citesOutside` grew a third shape (author-year, after it
    # missed four "(Gartner, 2027)"s on an empty record) and started closing
    # over two more module constants. This scope went undefined and the
    # harness died before printing a single FAIL, which reads as "not
    # pinned". Lift them, don't stub them -- MONTH is the guard that keeps
    # "(January, 2026)" from being read as a source, and a stand-in for it
    # would let this pass while the app cried wolf at a date.
    lifts = [
        ('OWN_HEAD', re.search(r"const OWN_HEAD = new RegExp\(.*?'i'\);", artifacts, re.S)),
        ('MONTH', re.search(r'^const MONTH = .*$', artifacts, re.M)),
        ('AUTHOR_YEAR', re.search(r'^const AUTHOR_YEAR = .*$', artifacts, re.M)),
    ]
    for label, hit in lifts:
        check(f'{label} is still where the detector keeps it', bool(hit),
              'citesOutside closes over it; a rename here kills the node '
              'harness instead of failing a check')
    if not all(hit for _, hit in lifts):
        print()
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    scope = '\n'.join([
        *(hit.group(0) for _, hit in lifts),
        brace_lift(artifacts, 'function citesOutside(text) {'),
        'const workingStub = (visits) => (visits || []).map(v => "- " + v.name);',
        brace_lift(runtime, 'function unverifiedSources(text, visits, citesFn, workingFn) {'),
    ])
    cited = 'Teams start low (Source: "Pricing for Startups" by Clarity).'
    prose = 'A 2020 study by Gajendran & Harrison found remote work helps.'
    cases = {
        'cited_no_visits': (cited, '[]'),
        'cited_own_head': ('Teams start low (Source: what I already know).', '[]'),
        'cited_with_visits': (cited, '[{name:"BROWSER_FETCH",arg:"https://x.com",echo:""}]'),
        'cited_visits_unknown': (cited, 'undefined'),
        'prose_no_visits': (prose, '[]'),
        'url_no_visits': ('See https://example.com/report for detail.', '[]'),
        'plain_no_visits': ('Three reasons, from what I already know.', '[]'),
    }
    js = scope + '\nconst R = {};\n' + '\n'.join(
        'R[%s] = unverifiedSources(%s, %s, citesOutside, workingStub);' % (json.dumps(k), json.dumps(v[0]), v[1])
        for k, v in cases.items()) + '\nconsole.log(JSON.stringify(R));'
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1200:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])

    fires = lambda k: bool(r[k]) and CAVEAT in r[k]
    check('a tagged source with nothing opened is called out',
          fires('cited_no_visits'), r['cited_no_visits'])
    check('a URL with nothing opened is called out',
          fires('url_no_visits'), r['url_no_visits'])
    check('"Source: what I already know" is left alone',
          r['cited_own_head'] is None,
          'the brief invites exactly this phrasing; flagging it punishes '
          'the compliant answer')
    check('a run that really opened something is left alone',
          r['cited_with_visits'] is None, r['cited_with_visits'])
    check('a path with no visit list is left alone',
          r['cited_visits_unknown'] is None, r['cited_visits_unknown'])
    check('a prose citation is left alone',
          r['prose_no_visits'] is None,
          'measured on a real second run — widening to catch this shape '
          'would fire on ordinary sentences')
    check('an honest reply is left alone',
          r['plain_no_visits'] is None, r['plain_no_visits'])

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

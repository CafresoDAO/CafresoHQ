#!/usr/bin/env python3
"""A publish REQUEST was filed as a published site.

`PUBLISH_SITE` does not publish. It queues an approval and returns, on
every path:

    Asked the boss to publish "index.html" — waiting for the stamp.
    Nothing is public yet.

Its own doc says NOTHING is public until they stamp it, and the real
publish happens later, in the approval handler, which reads `r.mode` and
is careful about what it claims (#61).

The captions were not. Measured live, office 9262, 2026-08-15, with
nothing public and the stamp not given:

    🌍 Published index.html
    Asked the boss to publish "index.html" — waiting for the stamp.
    Nothing is public yet.

The heading and the line under it describe the same event and disagree,
and the heading is the half a boss skims. The same verb went to the
corkboard as finished work and into the receipts tray, which is the
permanent record:

    { title: "Published index.html", kind: "deliverable",
      decision: "executed" }

— and `anchorWorkReceipt` writes that title on-chain, where it cannot be
taken back. Meanwhile the publish that DOES happen, on approval, files no
receipt at all, so the record held the thing that did not happen and not
the thing that did.

Both caption tables modelled three outcomes — doing, did, failed. This is
a fourth: succeeded at ASKING. The sweep at the bottom is the part meant
to outlive the ticket: it reads the tool registry, finds every tool whose
own result says nothing has happened yet, and requires its caption to
agree — so a second request-shaped tool is covered without anyone
remembering this.

Run: python3 scripts/test_a_request_is_not_the_act.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_RAW = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FLOOR_RAW = (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8')
APP_RAW = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The comments written with this fix quote the old caption and the
    receipt object verbatim."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, start, end_marker):
    i = src.index(start)
    j = src.index(end_marker, i)
    return src[i:j + len(end_marker)]


def brace_lift(src, opener):
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


# Every tool in the registry, read out of the source rather than listed, so
# a tool added later is swept without anyone coming back here.
#
# Bounded by brace-matching the tool's own object, NOT by "up to the next
# `name:`". The first draft did the latter, which gives the LAST tool in the
# registry everything to the end of the file — HANDOFF_TO duly came back
# carrying PUBLISH_SITE's sentences and was reported as request-shaped.
def tool_blocks(src):
    out = {}
    for m in re.finditer(r"^\s{4}name: '([A-Z0-9_]+)',", src, re.M):
        depth = 0
        open_at = None
        for k in range(m.start(), -1, -1):          # back to our own `{`
            if src[k] == '}':
                depth += 1
            elif src[k] == '{':
                if depth == 0:
                    open_at = k
                    break
                depth -= 1
        if open_at is None:
            continue
        depth = 0
        for k in range(open_at, len(src)):
            if src[k] == '{':
                depth += 1
            elif src[k] == '}':
                depth -= 1
                if depth == 0:
                    out[m.group(1)] = src[open_at:k + 1]
                    break
    return out


# A tool whose own result says the thing has NOT happened yet.
PENDING = re.compile(r'waiting for the stamp|Nothing is public yet'
                     r'|Asked the boss to', re.I)
# A caption that claims the act is done.
DID_IT = re.compile(r'^(?:Published|Shipped|Deployed|Made|Wrote|Sent|Exported)\b')


def main():
    print('a request is not the act')
    runtime = strip_comments(RUNTIME_RAW)
    floor = strip_comments(FLOOR_RAW)
    app = strip_comments(APP_RAW)

    blocks = tool_blocks(runtime)
    check('the registry has tools to sweep', len(blocks) > 25, len(blocks))

    # ── 1. the fact both captions have to match ─────────────────────────
    pub = blocks.get('PUBLISH_SITE', '')
    check('PUBLISH_SITE still only ever asks',
          PENDING.search(pub) and 'Nothing is public yet' in pub,
          '— if it ever starts publishing for real, the verbs below are '
          'wrong in the other direction and this suite must be revisited')
    check('...and the real publish is somewhere else',
          'cafresohq:publishRequest' in pub
          and "ap.kind === 'publish'" in app,
          '— run() queues an approval; the approval handler does the work')

    # The registry entry is not what an agent is handed. `toolsForAgent`
    # re-binds PUBLISH_SITE with a run() that knows who is calling, and THAT
    # is the one that produces the sentence under the heading. Checking only
    # the registry would leave the live path free to drift.
    override = re.search(r'\.\.\.TOOL_REGISTRY\.publish_site,[\s\S]*?\n    \}\);',
                         runtime)
    check('the agent-bound PUBLISH_SITE only ever asks too',
          override and PENDING.search(override.group(0))
          and 'Nothing is public yet' in override.group(0),
          '— toolsForAgent overrides run(); the registry copy is not the '
          'one the coworker gets')

    # ── 2. the caption tables ───────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the caption checks need it')
        return 1 if FAILS else 0

    js = lift(floor, 'const VISIT_WORDS = [', '];') + '\n'
    js += lift(floor, 'const VISIT_DEFAULT = ', ';') + '\n'
    js += brace_lift(floor, 'function visitWords(') + '\n'
    js += brace_lift(app, 'const deliverableVerb = (name) =>').rstrip() + '\n'

    # Names swept by both tables, and the pending ones among them.
    #
    # `deliverableVerb` is only ever CALLED for the deliverable set, so the
    # sweep asks it only about those. Reading its answer for a tool that
    # never reaches it reports the fallback ('Wrote') as though it were a
    # caption the boss could see — which is a finding about nothing.
    names = sorted(blocks)
    pending = sorted(n for n in names if PENDING.search(blocks[n]))
    dm = re.search(r'const DELIVERABLE_TOOLS = \[([\s\S]*?)\];', app)
    deliverables = re.findall(r"'([A-Z0-9_]+)'", dm.group(1)) if dm else []
    check('the deliverable set was found', len(deliverables) > 5, deliverables)
    js += 'const NAMES = ' + json.dumps(names) + ';\n'
    js += 'const PENDING = ' + json.dumps(pending) + ';\n'
    js += ('const PENDING_DELIV = '
           + json.dumps(sorted(set(pending) & set(deliverables))) + ';\n')
    js += r'''
const visit = {}, deliv = {};
for (const n of NAMES) { visit[n] = visitWords(n); deliv[n] = deliverableVerb(n); }
console.log(JSON.stringify({
  pending: PENDING,
  pendingVisit: PENDING.map(n => [n, visit[n].past, visit[n].now, visit[n].fail]),
  pendingDeliv: PENDING_DELIV.map(n => [n, deliv[n]]),
  // The four that really do finish the job must not have been softened.
  stillDid: {
    VAULT_NEW:     [visitWords('VAULT_NEW').past, deliverableVerb('VAULT_NEW')],
    VAULT_APPEND:  [visitWords('VAULT_APPEND').past, deliverableVerb('VAULT_APPEND')],
    EXPORT_PPTX:   [visitWords('EXPORT_PPTX').past, deliverableVerb('EXPORT_PPTX')],
    GENERATE_IMAGE:[visitWords('GENERATE_IMAGE').past, deliverableVerb('GENERATE_IMAGE')],
    FILE_WRITE:    [visitWords('FILE_WRITE').past, deliverableVerb('FILE_WRITE')],
  },
  publishIcon: visitWords('PUBLISH_SITE').icon,
}));
'''
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if p.returncode != 0:
        check('the caption harness runs', False, p.stderr.strip()[:500])
    else:
        R = json.loads(p.stdout)

        check('the sweep found the request-shaped tool(s)',
              'PUBLISH_SITE' in R['pending'], R['pending'])

        # ── the reported defect, on both surfaces ───────────────────────
        bad_visit = [row for row in R['pendingVisit']
                     if re.match(DID_IT, str(row[1]))]
        check('no tool that only ASKED is captioned as having done it',
              not bad_visit,
              [bad_visit, '— "🌍 Published index.html" sat one line above '
               '"Nothing is public yet"'])
        bad_deliv = [row for row in R['pendingDeliv']
                     if re.match(DID_IT, str(row[1]))]
        check('...and none is FILED as having done it',
              not bad_deliv,
              [bad_deliv, '— the receipts tray is the permanent record and '
               'anchorWorkReceipt writes the title on-chain'])

        # Both captions describe the same event, so they must agree.
        check('the heading and the receipt say the same thing',
              all('ask' in str(v[1]).lower() for v in R['pendingVisit'])
              and all('ask' in str(d[1]).lower() for d in R['pendingDeliv']),
              [R['pendingVisit'], R['pendingDeliv']])

        # The in-flight caption is about asking too — it used to say the
        # coworker was "publishing" while it was queueing an approval.
        check('the live caption is about asking as well',
              all('ask' in str(v[2]).lower() for v in R['pendingVisit']),
              [R['pendingVisit'], '— "publishing index.html" while the boss '
               'has not been asked yet'])

        # A failed ask is a failed ask, not a failed publish.
        check('a failed ask does not claim a failed publish',
              all('ask' in str(v[3]).lower() for v in R['pendingVisit']),
              [R['pendingVisit'],
               '— run() fails with "Couldn\'t queue that publish"'])

        # ── the tools that DO finish must keep their past tense ─────────
        did = R['stillDid']
        check('the tools that really do the job still say so',
              did['VAULT_NEW'] == ['Saved', 'Wrote']
              and did['VAULT_APPEND'] == ['Saved', 'Appended']
              and did['EXPORT_PPTX'] == ['Made', 'Exported']
              and did['GENERATE_IMAGE'] == ['Made', 'Generated']
              and did['FILE_WRITE'] == ['Saved', 'Wrote'],
              [did, '— softening every verb would trade this defect for its '
               'mirror image, where finished work reads as a maybe'])

        check('the publish icon is unchanged',
              R['publishIcon'] == '🌍',
              [R['publishIcon'], '— the verb was the wrong part, not the '
               'icon; a boss skims icons first (#44, VISIT_FAIL_ICON)'])

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

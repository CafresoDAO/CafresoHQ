#!/usr/bin/env python3
"""#143 — the stand-up filed a synthesis that never happened.

Driven live on 2026-08-18: a stand-up ran, the coworker reported, and
HQ.ceoStream could not reach the CEO brain. The modal said "DONE — ARCHIVE
OR COPY" and offered to file it; the card that landed on the board said
"End-of-day team stand-up." and carried:

    ## Synthesis (CafresoHQ)
    ⚠ hit a snag — couldn't reach that brain — it looks offline from here

A heading naming an act, over a sentence saying the act never happened —
#89's shape one surface over, and worse here because the filed report is
the part of a stand-up that outlives the modal.

This suite lifts StandupModal's own `fullText`, `reported` and `detail`
builders into node and runs them over real report shapes. It pins:
  · a failed synthesis is never headed "Synthesis (CafresoHQ)", and the
    section that replaces it carries the reason and says what the record IS;
  · a boss-stopped synthesis says stopped, not failed — different move;
  · a synthesis that LANDED still gets the plain heading (the fix must not
    make every stand-up hedge);
  · the card's own detail line counts who actually reported;
  · the failure is carried as STATE from the catch that saw it, not sniffed
    back out of the summary string;
  · the modal's subtitle and footer stop saying an unqualified "done", and
    the footer names RE-RUN — a door that is really in that footer.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FEAT = (ROOT / 'features.jsx').read_text(encoding='utf-8')

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


# Anchored on the DECLARATIONS, never on the fix.
REPORTED = brace_lift(FEAT, '  const reported = () =>').split('\n')[0] \
    if False else None
FULLTEXT = brace_lift(FEAT, '  const fullText = () => {')
ARCHIVE = brace_lift(FEAT, '  const archive = () => {')

# `reported` is a one-line arrow, not a braced block — lift it by line.
# `timedOut` is its sibling (##323): the detail expression names the rows the
# watchdog killed, so the harness must carry both or the lift won't run.
_rep_line = [l for l in FEAT.splitlines()
             if l.strip().startswith('const reported = ()')
             or l.strip().startswith('const timedOut = ()')]


def harness(reports, summary, summary_fail):
    """Run the real fullText/detail builders over one run's state."""
    detail_expr = re.search(
        r'detail: (`End-of-day team stand-up[\s\S]*?),\n', ARCHIVE)
    if not detail_expr:
        raise AssertionError('detail expression not found in archive()')
    js = """
const reports = %s, summary = %s, summaryFail = %s;
%s
%s
const out = { text: fullText(), detail: %s, reported: reported() };
console.log(JSON.stringify(out));
""" % (json.dumps(reports), json.dumps(summary), json.dumps(summary_fail),
       '\n'.join(_rep_line), FULLTEXT, detail_expr.group(1))
    return run_js(js)


# `outcome` (##323) is how the row ENDED. These fixtures used to carry only
# `text` + `error`, which is exactly the two-ending shorthand ##323 found the
# count relying on — a row that timed out has text and no error and is
# neither of these two. Every real row now gets stamped with its ending, so
# the fixtures state it too.
ONE_GOOD = [{'agentId': 'a1', 'name': 'Local Brain', 'role': 'Generalist',
             'text': 'TODAY: vendor list\nBLOCKED: nothing\nTOMORROW: numbers',
             'streaming': False, 'error': False, 'outcome': 'reported'}]
ONE_ERR = [{'agentId': 'a1', 'name': 'Local Brain', 'role': 'Generalist',
            'text': '⚠ hit a snag — couldn\'t reach that brain',
            'streaming': False, 'error': True, 'outcome': 'error'}]
SNAG = "hit a snag — couldn't reach that brain — it looks offline from here"


def main():
    print('#143 — the stand-up files only what happened')

    print('\n[the failed synthesis]')
    r = harness(ONE_GOOD, '⚠ ' + SNAG, SNAG)
    t = r['text']
    check('never headed "Synthesis (CafresoHQ)"',
          '## Synthesis (CafresoHQ)' not in t, t[-260:])
    check('the heading says it was not written',
          '## Synthesis — not written' in t, t[-260:])
    check('the reason survives into the filed record', SNAG in t)
    check('the record says what it IS (reports, unsummarised)',
          'The reports above are the whole record' in t)
    check('no run-on: the reason is punctuated before the next sentence',
          'from here The reports' not in t and 'from here. The reports' in t,
          t[-200:])
    check('the coworker report itself is still filed',
          'TODAY: vendor list' in t)
    check('card detail names the missing summary',
          r['detail'] == 'End-of-day team stand-up — 1 of 1 reported; '
                         'no closing summary.', r['detail'])

    print('\n[the boss stopped it — a different move]')
    r = harness(ONE_GOOD, 'half a summ', 'stopped')
    t = r['text']
    check('says stopped, not failed',
          '## Synthesis — stopped part-way' in t and 'not written' not in t, t[-260:])
    check('the partial summary is kept, not discarded', 'half a summ' in t)
    check('card detail says the boss stopped it',
          'you stopped it before the summary.' in r['detail'], r['detail'])
    r2 = harness(ONE_GOOD, '', 'stopped')
    check('stopped before it started → no orphan empty section',
          'CafresoHQ started the closing summary' in r2['text'], r2['text'][-200:])

    print('\n[a synthesis that actually landed]')
    r = harness(ONE_GOOD, 'Vendor work is on track; chase the numbers.', '')
    t = r['text']
    check('keeps the plain heading — the fix does not make every day hedge',
          '## Synthesis (CafresoHQ)' in t and 'not written' not in t, t[-220:])
    check('the real summary is filed verbatim',
          'Vendor work is on track; chase the numbers.' in t)
    check('card detail is unqualified when nothing is missing',
          r['detail'] == 'End-of-day team stand-up — 1 of 1 reported.',
          r['detail'])

    print('\n[who actually reported]')
    r = harness(ONE_ERR, '', SNAG)
    check('an error row is not counted as a report', r['reported'] == 0, r)
    check('card detail counts 0 of 1',
          r['detail'].startswith('End-of-day team stand-up — 0 of 1 reported'),
          r['detail'])
    check('the errored row is still FILED — who was asked is part of the record',
          '## Local Brain (Generalist)' in r['text'])
    r = harness(ONE_GOOD + ONE_ERR, 'ok', '')
    check('mixed run counts only the answers', r['reported'] == 1, r)

    print('\n[the failure is state, not a string sniffed back out]')
    check('the catch that sees the failure records it',
          "setSummaryFail(stopped ? 'stopped' : snag);" in FEAT)
    check('start() clears it', "setSummaryFail('');" in FEAT)
    check('nothing infers the failure from the summary text',
          not re.search(r"summary\.(startsWith|includes)\(\s*['\"]⚠", FEAT))

    print('\n[the modal stops saying an unqualified "done"]')
    check('subtitle names the missing summary',
          "summaryFail ? 'reports in — no closing summary'" in FEAT)
    check('footer hint offers RE-RUN when the summary is missing',
          'RE-RUN to try again, or ARCHIVE the reports as they are' in FEAT)
    check('RE-RUN is really a button in that footer',
          re.search(r'onClick=\{start\}>RE-RUN<', FEAT) is not None)
    check('the plain "tap ARCHIVE" line survives for a clean run',
          'tap ARCHIVE to keep this on your task board' in FEAT)

    print('\n%s' % ('ALL CHECKS PASSED' if not FAILS
                    else 'FAILED: %d check(s): %s' % (len(FAILS), FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

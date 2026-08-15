#!/usr/bin/env python3
"""The audit trail recorded the stamp and never what the stamp did.

For most approval kinds a stamp is only a decision — the act happens
elsewhere, later, and the receipt has nothing to say about it. `publish`
is the exception: `onApprove` performs the publish INLINE, right there in
the handler, and it has three endings.

    shipped      → live on the Internet Computer
    preview      → a link that opens on this machine only
    failed       → nothing went anywhere

The receipt was written at the moment of the decision and never touched
again, so all three left the identical row — green ✓, kind `publish`:

    ✓  publish "site/" to the public internet
       by Mika · publish · Aug 15

Measured live 2026-08-15, office 9262, stamping a real agent-requested
publish. Chat said the honest thing:

    ⚠ The publish didn't make it out — Path outside allowed
      directories: 'site/'

and the tray — whose own subtitle reads "stamped approvals · audit
trail" — said only that the boss approved it. Chat is scrollback. The
tray is the record, and the record was of a decision, not an event.

Fix: the outcome lands back on the SAME receipt (one decision, one row),
and the two surfaces that read receipts — the tray and the bell — say it.

The durable part is the sweep: any approval branch in `onApprove` that
performs its act inline must settle its receipt on every exit. A second
inline-acting approval kind is covered without anyone reading this file.

Run: python3 scripts/test_the_stamp_records_what_it_did.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_RAW = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FEAT_RAW = (ROOT / 'features.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """The comments written with this fix quote the measured chat line and
    the row the tray showed, so a bare substring search would find its own
    documentation."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """The body of a function/branch, by matching its own braces."""
    i = src.index(opener)
    depth = 0
    started = False
    for k in range(i, len(src)):
        if src[k] == '{':
            depth += 1
            started = True
        elif src[k] == '}':
            depth -= 1
            if started and depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


APP = strip_comments(APP_RAW)
FEAT = strip_comments(FEAT_RAW)


def main():
    print('the stamp records what it did')

    # ── 1. the receipt has to be reachable after it is written ──────────
    rec = brace_lift(APP, 'const recordReceipt = (ap, decision) =>')
    check('recordReceipt hands back the id it minted',
          re.search(r'return r\.id;', rec),
          '— nothing downstream can amend a receipt it cannot name')

    approve = brace_lift(APP, 'const onApprove = (id) =>')
    check('onApprove keeps the id',
          re.search(r'const rcId = recordReceipt\(ap, .approved.\)', approve),
          '— the id is minted and dropped on the floor')

    # ── 2. the amendment must MERGE, not replace ────────────────────────
    settle = brace_lift(APP, 'const settleReceipt = (rcId, outcome, text) =>')
    check('settleReceipt amends one receipt and leaves the rest alone',
          '.map(' in settle and 'r.id === rcId' in settle
          and '...r,' in settle and ': r' in settle,
          [settle, '— an audit trail that loses rows when one settles is '
           'worse than one that never settles'])
    check('...and it is a no-op without an id',
          re.search(r'if \(!rcId\) return;', settle),
          '— every other approval kind calls recordReceipt too')

    # ── 3. THE SWEEP: an approval that acts inline must settle ──────────
    #
    # Not "check the publish branch": find every branch of onApprove that
    # performs its own act — `await CafresoHQClient.<something>` inside the
    # handler — and require it to write the outcome down. Approvals whose
    # act happens elsewhere (bash re-dispatch, hire, spend) are advisory and
    # are deliberately NOT swept: they have no outcome to report here.
    inline = []
    for m in re.finditer(r"if \(ap\.kind === '(\w+)'[^)]*\) \{", approve):
        body = brace_lift(approve[m.start():], 'if (ap.kind ===')
        if 'await CafresoHQClient.' in body:
            inline.append((m.group(1), body))
    check('the sweep found the approval(s) whose stamp is also the act',
          [k for k, _ in inline] == ['publish'],
          [[k for k, _ in inline], '— if a second kind starts acting inline '
           'it is swept from here on; if publish stopped, this suite is moot'])

    for kind, body in inline:
        # Every sentence the boss is told in the moment must also be written
        # down. Count the announcements, count the settlements, require
        # parity — a fourth ending added later cannot slip through silent.
        told = len(re.findall(r"from: 'system', name: 'HQ'", body))
        wrote = len(re.findall(r'settleReceipt\(rcId,', body))
        check("every ending the %s stamp announces is also filed" % kind,
              told > 0 and told == wrote,
              '— %d announced, %d filed' % (told, wrote))
        check('...on the success path and the failure path both',
              'catch (err)' in body
              and 'settleReceipt' in body.split('catch (err)')[1]
              and 'settleReceipt' in body.split('catch (err)')[0],
              '— a publish that throws is the case that most needs a record')

    # ── 4. the outcome words agree with what chat said in the moment ────
    pub = inline[0][1] if inline else ''
    check('a canister publish is filed as shipped',
          re.search(r"settleReceipt\(rcId, wentPublic \? 'shipped' : 'preview'", pub),
          '— the outcome is read off r.mode, same as the headline (#61)')
    check('a preview is filed as never having gone public',
          re.search(r'Preview only — never went public', pub),
          [pub[-600:], '— "Preview only" is the headline #61 established; '
           'the tray is read a week later, with no headline above it'])
    check('a failure is filed in the words chat used',
          re.search(r"settleReceipt\(rcId, 'failed',\s*\n?\s*`Didn't make it out", pub),
          '— chat says "didn\'t make it out"; the tray must not invent a '
          'second vocabulary for the same event (ledger §6)')
    # `.split(…)[1]` raises when the call is gone, which crashes the harness
    # and proves nothing — the same lesson fire56 taught about `.index()`.
    after_fail = pub.split("settleReceipt(rcId, 'failed'")
    check('the filed failure carries the reason, not just the fact',
          len(after_fail) > 1 and 'officeCause(' in after_fail[1][:200],
          '— "Path outside allowed directories" is the whole value of the row')

    # ── 5. the tray shows it, and invents nothing when it is absent ─────
    card = FEAT[FEAT.index('function ReceiptsModal('):]
    card = card[:card.index('\n}')]
    # The block the outcome actually renders from — everything below is read
    # out of THIS, not out of the whole modal. Searching the modal for
    # `r.outcomeText` matched the interpolation inside a block the first
    # draft had let go dead: `{false && ( … {r.outcomeText} … )}` kept every
    # string a substring check was looking for while rendering nothing.
    guard = re.search(r'\{r\.outcomeText && \(([\s\S]*?)\n {14}\)\}', card)
    block = guard.group(1) if guard else ''
    check('the tray renders the outcome',
          bool(guard) and '{r.outcomeText}' in block,
          '— filed and never shown is the same as never filed')
    check('...only when there is one',
          bool(guard),
          '— receipts stamped before this carry no outcome; guessing one '
          'for them is the defect pointing the other way')
    check('a failed outcome does not render as ordinary body text',
          re.search(r"r\.outcome === 'failed'", block),
          '— it sits under a green ✓ and has to be legible as the exception')

    # The boss's stamp is NOT the thing that was wrong. It was given, and the
    # column that shows it must keep saying so — recolouring the ✓ would
    # make the tray misreport the one fact it always had right.
    stamp = re.search(r'const stampFor = \(r\) =>[^;]+;', FEAT)
    check('the stamp column still reports the decision, not the outcome',
          stamp and 'r.outcome' not in stamp.group(0),
          [stamp.group(0) if stamp else None,
           '— the boss did approve it; that stays true in all three endings'])

    # ── 6. the bell reads the same receipt ──────────────────────────────
    # Anchored on the bell entry's own id line. `kind: 'receipt'` alone also
    # matches the corkboard pin built from a tool event, several hundred
    # lines earlier — which lifted the wrong block entirely and reported it
    # as the bell.
    bell = APP[APP.index("id: 'r-' + r.id,"):]
    bell = bell[:bell.index('});')]
    check('the bell tells the same story as the tray',
          "r.outcome === 'failed'" in bell and "r.outcome === 'preview'" in bell,
          [bell, '— one event, one story, on every surface (#44)'])

    # ── 7. the merge actually behaves ───────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the reducer check needs it')
        return 1 if FAILS else 0

    # Lift the real updater body out of source rather than restating it.
    # brace_lift returned the whole arrow function, so the tail carries that
    # function's own closing `}` — leaving it in put the harness's `return`
    # at top level, which node rejects outright.
    body = settle[settle.index('setReceipts('):].rstrip()
    assert body.endswith('}'), body[-40:]
    body = body[:-1].rstrip()
    js = ('const now = 1;\n'
          'function settle(list, rcId, outcome, text) {\n'
          '  let out = list;\n'
          '  const setReceipts = (fn) => { out = fn(list); };\n'
          '  const Date = { now: () => now };\n'
          '  if (!rcId) return out;\n'
          + '  ' + body.replace('Date.now()', 'now') + '\n'
          '  return out;\n'
          '}\n')
    js += r'''
const before = [
  { id: 'rc_a', title: 'publish "site/" to the public internet', decision: 'approved' },
  { id: 'rc_b', title: 'Wrote site/index.html', decision: 'executed' },
];
const after = settle(before, 'rc_a', 'failed', "Didn't make it out — nope");
const untouched = settle(before, 'rc_zz', 'failed', 'x');
console.log(JSON.stringify({
  kept:      after.length === before.length,
  merged:    after[0].title === before[0].title && after[0].decision === 'approved',
  outcome:   after[0].outcome,
  text:      after[0].outcomeText,
  neighbour: JSON.stringify(after[1]) === JSON.stringify(before[1]),
  // A miss must not silently blank the tray.
  missKeeps: untouched.length === before.length
             && untouched.every(r => r.outcome === undefined),
}));
'''
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if p.returncode != 0:
        check('the reducer harness runs', False, p.stderr.strip()[:400])
    else:
        R = json.loads(p.stdout)
        check('settling keeps every row', R['kept'], R)
        check('...and every field the row already had', R['merged'], R)
        check('...and writes the outcome onto it',
              R['outcome'] == 'failed' and "Didn't make it out" in (R['text'] or ''),
              R)
        check('...and does not touch its neighbours', R['neighbour'], R)
        check('an id that matches nothing changes nothing', R['missKeeps'], R)

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

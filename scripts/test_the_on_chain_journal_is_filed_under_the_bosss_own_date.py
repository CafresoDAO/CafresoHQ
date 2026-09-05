#!/usr/bin/env python3
"""The Gazette's on-chain journal digest is keyed by the boss's local day.

When the boss comes back after >4h away, app.jsx aggregates a Morning
Report and best-effort drops a `journal/<date>` digest on-chain through
CafresoHQChain.docs.put. That name is the whole identity of the record:
the state canister's putDoc is `tOps.put(docs, name, doc)` -- keyed by
name, overwriting whatever was there. Two writes under one name is not a
duplicate, it is a deletion.

`toISOString()` stamps UTC. West of Greenwich, an evening gazette
therefore filed itself under TOMORROW's name -- and the next day's real
gazette then landed on that same name and silently replaced it. The
office already knows this: `officeDate()` in app/artifacts.jsx exists
because a delivery filed at 8pm in New York was dated tomorrow in its
own header, and app.jsx line ~2215 already uses it for the activity
row's date.

This test lifts the REAL journal-drop block out of app.jsx and runs it
under node against a stub chain and a pinned clock, so what is asserted
is the shipped code rather than a paraphrase of it.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def journal_block():
    """The real `if (chain && ... docs.put) { ... }` block from app.jsx."""
    src = APP.read_text(encoding='utf-8')
    i = src.find('chain.docs && chain.docs.put')
    if i == -1:
        raise SystemExit('journal drop block not found in app.jsx')
    start = src.rfind('if (', 0, i)
    j = src.find('{', i)
    depth, k, started = 0, j, False
    while k < len(src):
        if src[k] == '{':
            depth += 1
            started = True
        elif src[k] == '}':
            depth -= 1
            if started and depth == 0:
                k += 1
                break
        k += 1
    return src[start:k]


def office_date_source():
    """The real officeDate() out of app/artifacts.jsx (it is pure)."""
    src = ARTIFACTS.read_text(encoding='utf-8')
    i = src.find('function officeDate(')
    if i == -1:
        raise SystemExit('officeDate not found in app/artifacts.jsx')
    j = src.find('{', i)
    depth, k, started = 0, j, False
    while k < len(src):
        if src[k] == '{':
            depth += 1
            started = True
        elif src[k] == '}':
            depth -= 1
            if started and depth == 0:
                k += 1
                break
        k += 1
    return src[i:k]


HARNESS = """
%(officeDate)s

// A clock the office cannot tell from the real one, pinned to a wall time
// in the ambient TZ. `new Date()` with no args is the only thing the block
// under test reads, so that is all we override.
function pinClock(y, mo, d, h, mi) {
  const Real = Date;
  const fixed = new Real(y, mo, d, h, mi, 0, 0);
  class Pinned extends Real {
    constructor(...a) { if (a.length === 0) { super(fixed.getTime()); } else { super(...a); } }
    static now() { return fixed.getTime(); }
  }
  globalThis.Date = Pinned;
  return () => { globalThis.Date = Real; };
}

function dropJournal(y, mo, d, h, mi) {
  const puts = [];
  const CafresoHQChain = {
    isAvailable: () => true,
    docs: { put: (name, body) => { puts.push({ name, body }); return Promise.resolve(); } },
  };
  const prevSeen = 0;
  const acts = [{ ts: 1, agentName: 'Ada', action: 'artifact', text: 'filed a brief' }];
  const unpin = pinClock(y, mo, d, h, mi);
  try {
    const chain = CafresoHQChain;
%(block)s
  } finally { unpin(); }
  return puts;
}

const R = {};
// 8pm in a UTC-6 office: UTC has already rolled to the next day.
R.evening = dropJournal(2026, 8, 5, 20, 30).map(p => p.name);
// The next morning's genuine gazette, same office.
R.nextMorning = dropJournal(2026, 8, 6, 9, 0).map(p => p.name);
// Early hours east of Greenwich: UTC is still on the previous day.
R.earlyAm = dropJournal(2026, 8, 6, 1, 15).map(p => p.name);
// Midday is the case where UTC and local agree, so it must not regress.
R.midday = dropJournal(2026, 8, 6, 12, 0).map(p => p.name);
R.body = JSON.parse(dropJournal(2026, 8, 5, 20, 30)[0].body);
console.log(JSON.stringify(R));
"""


def run(tz):
    script = HARNESS % {'officeDate': office_date_source(), 'block': journal_block()}
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=ROOT, capture_output=True, text=True, timeout=60,
                          env={**os.environ, 'TZ': tz})
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('The on-chain journal is filed under the boss\'s own date\n')

    print('a UTC-6 office (America/El_Salvador)')
    w = run('America/El_Salvador')
    check('8pm on the 5th files journal/2026-09-05, not the 6th',
          w['evening'] == ['journal/2026-09-05'], repr(w['evening']))
    check('the next morning files a DIFFERENT name, so nothing is overwritten',
          w['evening'][0] != w['nextMorning'][0],
          f"{w['evening']} vs {w['nextMorning']}")
    check('that next morning is journal/2026-09-06',
          w['nextMorning'] == ['journal/2026-09-06'], repr(w['nextMorning']))
    check('midday, where UTC and local agree, is unchanged',
          w['midday'] == ['journal/2026-09-06'], repr(w['midday']))
    check('the digest body still carries the entries it always did',
          isinstance(w['body'].get('entries'), list) and w['body']['entries']
          and w['body']['entries'][0]['agent'] == 'Ada', repr(w['body'])[:200])

    print('\nan office east of Greenwich (Europe/Berlin)')
    e = run('Europe/Berlin')
    check('1:15am on the 6th files journal/2026-09-06, not the 5th',
          e['earlyAm'] == ['journal/2026-09-06'], repr(e['earlyAm']))
    check('8:30pm on the 5th still files journal/2026-09-05',
          e['evening'] == ['journal/2026-09-05'], repr(e['evening']))

    print('\nUTC itself, where the two spellings coincide')
    u = run('UTC')
    check('evening is journal/2026-09-05', u['evening'] == ['journal/2026-09-05'], repr(u['evening']))
    check('early am is journal/2026-09-06', u['earlyAm'] == ['journal/2026-09-06'], repr(u['earlyAm']))

    print()
    if FAILS:
        print(f'{len(FAILS)} failed: ' + ', '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

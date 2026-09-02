#!/usr/bin/env python3
"""Search results went stale behind every refresh.

Hits are sticky state: leave the Library, come back, tap ↻ — the old
result list still stood, made from a Library that no longer exists.
A matching new note never appeared, and after a drag-move the hit
rows kept their PRE-move paths, so clicking one opened nothing at
all. The graph, the tree and the files list all refreshed; the one
pane the boss was actually looking at did not.

Now refresh() re-runs the standing query — hitQ, the query the hits
were MADE with — against the fresh Library, on both the bridge and
the server arm, after the file list lands. No standing search means
no extra round-trip; a failed re-run keeps the hits we have, because
a refresh must never turn a result list into an error screen.
Verified live: with "remote startups" results showing, a matching
note was added server-side and ↻ grew the list from 2 rows to 3.

Run: python3 scripts/test_a_standing_search_stays_fresh.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


# _refreshHits lifted alone: the decision logic (when to re-run, which
# query, what failure does) lives entirely inside it.
HARNESS = r'''
const calls = [];
let hitsState = %s;
const hits = hitsState, hitQ = %s;
const setHits = (v) => { calls.push(['set', v]); };
const _bridge = %s;
const bridgeSearch = async (q2) => { calls.push(['bridge', q2]); return ['B']; };
const CafresoHQClient = { vaultSearch: async (q2) => { calls.push(['server', q2]);
  if (q2 === 'boom') throw new Error('down'); return ['S']; } };

%s

(async () => {
  await _refreshHits();
  console.log(JSON.stringify(calls));
})();
'''


def run(fn, hits, hitq, bridge):
    js = HARNESS % (hits, hitq, bridge, fn)
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a standing search stays fresh')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    fn = brace_lift(vault, 'const _refreshHits = async () => {')

    check('a standing server search is re-run with the query it was made with',
          run(fn, '["old"]', '"remote"', 'null')
          == [['server', 'remote'], ['set', ['S']]])
    check('the bridge arm re-runs through the bridge',
          run(fn, '["old"]', '"remote"', '({})')
          == [['bridge', 'remote'], ['set', ['B']]])
    check('no standing search means no extra round-trip',
          run(fn, 'null', '"remote"', 'null') == [])
    check('an empty query never re-runs (hits without hitQ are legacy state)',
          run(fn, '["old"]', '""', 'null') == [])
    check('a failed re-run keeps the hits we have',
          run(fn, '["old"]', '"boom"', 'null') == [['server', 'boom']])

    # 3: the bridge refresh arm, the server refresh arm, and the standing
    # look (the delivery poll) — each path that learns of new files re-runs
    # the standing search.
    check('both refresh arms (bridge and server) re-run the standing search',
          vault.count('await _refreshHits();') == 3)
    # By the CALL, not by the whole statement it used to sit in. #142 split
    # `setFiles(await CafresoHQClient.vaultList());` into a load and a set so
    # the loading screen could outlive the fetch, and this line raised
    # ValueError — on a change that moved neither the load nor the re-run
    # relative to each other. The fact being checked is the ordering; the
    # assignment form is incidental to it.
    #
    # Scoped to the server arm, which is what the label says and what the old
    # line did not do. It compared the FIRST vaultList in the file against the
    # LAST _refreshHits in the file, and those are in different branches — so
    # moving this arm's re-run above its own load left a later re-run in the
    # bridge arm still satisfying the comparison. Found by firing exactly that
    # break at the re-anchored check and watching it pass; the blind spot was
    # in the original too, and re-anchoring is what exposed it.
    server_arm = vault[vault.index('const s = await CafresoHQClient.vaultStatus();'):]
    server_arm = server_arm[:server_arm.index('\n  React.useEffect(')]
    check('the re-run sits inside refresh, after the files load',
          server_arm.index('CafresoHQClient.vaultList()')
          < server_arm.index('await _refreshHits();'))

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

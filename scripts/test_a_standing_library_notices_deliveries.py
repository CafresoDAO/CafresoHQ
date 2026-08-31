#!/usr/bin/env python3
"""A delivery filed while the boss watched the Library never appeared.

Coworkers file asynchronously — that is the whole premise of the room —
but the server-vault Library only looked at the shelf once, on mount.
The bridge shell pushes vault:files:update; the shipping fs backend
pushed nothing, so a boss who left the view open waiting for a deck saw
it only after a manual ↻ or a walk to another view and back.

Now a quiet standing look runs every half-minute (and immediately when
the tab comes back into view): fetch the listing, compare path+mtime+
size against what the view already shows. Same set → nothing happens —
no graph re-layout under the boss's cursor, no hit churn. Changed set →
the one full propagation the manual ↻ would have done. Nobody looking
(document.hidden) or no Library configured → not even the fetch. A
failed look is silence, never an error banner. Verified live: a note
filed by curl appeared in the open tree in ~0.6s on the visibility
path and one poll tick later on the interval path, with the graph
refreshed exactly once.

Run: python3 scripts/test_a_standing_library_notices_deliveries.py
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


# The poll body straight from the view, with every collaborator stubbed
# to a recorder. %s slots: document.hidden, status, files-on-screen,
# server listing (null → the fetch throws).
HARNESS = r'''
const document = { hidden: %s };
const status = %s;
const files = %s;
const LIST = %s;
const calls = [];
let fetches = 0, setFilesArg = null;
const setFiles = (v) => { calls.push('setFiles'); setFilesArg = v; };
const refreshGraph = () => calls.push('graph');
const _refreshHits = async () => calls.push('hits');
const CafresoHQClient = { vaultList: async () => {
  fetches++;
  if (LIST === null) throw new Error('the shelf fell over');
  return LIST;
} };
const _pollRef = { current: null };
%s;
(async () => {
  await _pollRef.current();
  console.log(JSON.stringify({ calls, fetches,
    gotPaths: setFilesArg && setFilesArg.map(f => f.path) }));
})();
'''

A = {'path': 'Research/brief.md', 'mtime': 111, 'size': 10}
B = {'path': 'Deliveries/deck.pptx', 'mtime': 222, 'size': 19}


def run(hidden, status, files, listing):
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    body = brace_lift(vault, '_pollRef.current = async () => {')
    src = HARNESS % (hidden, json.dumps(status), json.dumps(files),
                     json.dumps(listing), body)
    p = subprocess.run(['node', '-e', src], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a standing library notices deliveries')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')

    out = run('false', {'configured': True}, [A], [A, B])
    check('a new delivery propagates: tree, then graph, then standing search',
          out['calls'] == ['setFiles', 'graph', 'hits'], out)
    check('…and the tree gets the SERVER listing, delivery included',
          out['gotPaths'] == [A['path'], B['path']], out)

    out = run('false', {'configured': True}, [B, A], [A, B])
    check('an unchanged shelf changes nothing — order is not a change',
          out['calls'] == [] and out['fetches'] == 1, out)

    out = run('false', {'configured': True}, [A],
              [{**A, 'mtime': 999}])
    check('a rewrite in place counts — mtime is part of the look',
          out['calls'] == ['setFiles', 'graph', 'hits'], out)

    out = run('true', {'configured': True}, [A], [A, B])
    check('nobody looking, nobody fetching (document.hidden)',
          out['calls'] == [] and out['fetches'] == 0, out)

    out = run('false', {'configured': False}, [A], [A, B])
    check('no Library configured, no look taken',
          out['calls'] == [] and out['fetches'] == 0, out)

    out = run('false', {'configured': True}, [A], None)
    check('a failed look is silence, never an error banner',
          out['calls'] == [] and out['fetches'] == 1, out)

    i = vault.index('_pollRef.current = async () => {')
    tail = vault[i:i + 2400]
    check('the look stands every half-minute and leaves with the view',
          "setInterval(() => { _pollRef.current && _pollRef.current(); }, 30000)" in tail
          and 'clearInterval(id)' in tail)
    check('coming back into view looks immediately, and the listener leaves too',
          "document.addEventListener('visibilitychange', onVis)" in tail
          and "document.removeEventListener('visibilitychange', onVis)" in tail)
    check('the bridge shell keeps its own push channel — no double watcher',
          'if (_bridge) return;   // the shell pushes its own updates' in tail)

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

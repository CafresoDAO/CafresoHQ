#!/usr/bin/env python3
"""Floor-language helpers (app/floor.jsx) — pure-function suite.

These decide what the office floor SAYS about real runtime events
(OFFICE_AS_INTERFACE §4), and §4's honesty rule makes the edges worth
pinning: a wrong prop mapping walks a coworker to furniture they aren't
using, and a leaky snag sentence puts a stack trace in a speech bubble
(§7 forbids raw error dumps on the floor).

Same pattern as test_artifacts.py / test_experience.py: strip the export
line and run the REAL source under node.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'floor.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('floor language helpers')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
// ── toolProp — the §4 walk table ────────────────────────────────────────
R.vaultRead    = toolProp('VAULT_READ');
R.vaultNew     = toolProp('VAULT_NEW');
R.fileWrite    = toolProp('FILE_WRITE');
R.memoryWrite  = toolProp('MEMORY_WRITE');
R.vaultSearch  = toolProp('VAULT_SEARCH');     // search WINS over storage
R.braveSearch  = toolProp('BRAVE_SEARCH');
R.deepResearch = toolProp('DEEP_RESEARCH');
R.webFetch     = toolProp('WEB_FETCH');
R.httpGet      = toolProp('HTTP_GET');
R.lowerCase    = toolProp('vault_read');       // event names arrive as-is
R.unknown      = toolProp('WALLET_SEND');      // unmappable → stays at desk
R.empty        = toolProp('');
R.nullName     = toolProp(null);
// ── placards — office words, never tool names (§6) ─────────────────────
R.placards = PROP_PLACARD;
// ── snagSentence — one honest sentence, no raw dumps (§7) ───────────────
R.snagPlain   = snagSentence('model overloaded, please retry');
R.snagStack   = snagSentence('boom\n    at Object.<anonymous> (/x/y.js:1:1)\n    at Module._compile');
R.snagJson    = snagSentence('{"error":{"message":"quota exceeded","code":429}}');
R.snagUrl     = snagSentence('fetch failed for https://api.example.com/v1/chat: 502');
R.snagLong    = snagSentence('x'.repeat(300));
R.snagLongLen = snagSentence('x'.repeat(300)).length;
R.snagEmpty   = snagSentence('');
R.snagNull    = snagSentence(null);
console.log(JSON.stringify(R));
''')

    # toolProp
    check('vault read walks to the cabinet', out['vaultRead'] == 'cabinet')
    check('vault new walks to the cabinet', out['vaultNew'] == 'cabinet')
    check('file write walks to the cabinet', out['fileWrite'] == 'cabinet')
    check('memory write walks to the cabinet', out['memoryWrite'] == 'cabinet')
    check('vault SEARCH walks to the bookshelf, not the cabinet',
          out['vaultSearch'] == 'bookshelf', str(out['vaultSearch']))
    check('web search walks to the bookshelf', out['braveSearch'] == 'bookshelf')
    check('deep research walks to the bookshelf', out['deepResearch'] == 'bookshelf')
    check('web fetch picks up the phone', out['webFetch'] == 'phone')
    check('http picks up the phone', out['httpGet'] == 'phone')
    check('mapping is case-insensitive', out['lowerCase'] == 'cabinet')
    check('unmappable tools stay at the desk', out['unknown'] is None)
    check('empty name stays at the desk', out['empty'] is None)
    check('null name stays at the desk', out['nullName'] is None)

    # placards
    check('every prop has a placard',
          set(out['placards'].keys()) == {'cabinet', 'bookshelf', 'phone'})
    check('placards use office words (no underscores / tool names)',
          all(('_' not in v and v == v.lower()) for v in out['placards'].values()))

    # snagSentence
    check('plain message passes through',
          out['snagPlain'] == 'hit a snag — model overloaded, please retry')
    check('stack trace collapses to its first line',
          out['snagStack'] == 'hit a snag — boom', repr(out['snagStack']))
    check('JSON shrapnel is stripped',
          '{' not in out['snagJson'] and 'quota exceeded' in out['snagJson'],
          repr(out['snagJson']))
    check('URLs are dropped from the bubble',
          'http' not in out['snagUrl'] and '502' in out['snagUrl'], repr(out['snagUrl']))
    check('long messages are capped with an ellipsis',
          out['snagLong'].endswith('…') and out['snagLongLen'] <= 104,
          str(out['snagLongLen']))
    check('empty error still says something honest',
          out['snagEmpty'] == 'hit a snag — something went wrong on the last run')
    check('null error tolerated', out['snagNull'] == out['snagEmpty'])

    print()
    if FAILS:
        print(f'floor language: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('floor language: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

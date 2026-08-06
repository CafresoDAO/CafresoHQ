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
/* These two exercise the FALL-THROUGH cleanup, so they must use causes the
   table cannot identify — a recognised cause is now replaced wholesale, not
   tidied up, which is the point of the table. */
R.snagJson    = snagSentence('{"error":{"message":"the flux capacitor came loose"}}');
R.snagUrl     = snagSentence('fetch failed for https://api.example.com/v1/chat while parsing');
// A recognised cause must not leak the raw text it replaced.
R.snagNoLeak  = (() => { const out = snagSentence('{"error":{"message":"quota exceeded","code":429}}');
                         return !/quota exceeded|429|[{}"]/.test(out); })();
R.snagLong    = snagSentence('x'.repeat(300));
R.snagLongLen = snagSentence('x'.repeat(300)).length;
R.snagEmpty   = snagSentence('');
// ── deskKit — room props from GRANTED capability, never achievement ─────
R.kitVault   = deskKit(['vault']);
R.kitFiles   = deskKit(['files']);
R.kitWeb     = deskKit(['web']);
R.kitEmail   = deskKit(['email']);
R.kitSearch  = deskKit(['search']);
R.kitFull    = deskKit(['web','email','cal','vault']);
R.kitDedup   = deskKit(['vault','files','fs']);      // all → one cabinet
R.kitCap     = deskKit(['vault','web','search','db']); // capped at 2
R.kitNone    = deskKit([]);
R.kitNull    = deskKit(null);
R.kitJunk    = deskKit(['wallet','payroll']);        // unmappable → shelf
R.snagNull    = snagSentence(null);
// ── snag causes: the sentence a real failure produces ──────────────────
// The literal string a live run put on the floor before this table existed.
R.snagRealKey  = snagSentence('OpenRouter 503: error : openrouter: no API key configured');
R.snag401      = snagSentence('HTTP 401 invalid bearer token');
R.snag429      = snagSentence('429 Too Many Requests');
R.snagQuota    = snagSentence('insufficient_quota: you exceeded your current quota');
R.snagRefused  = snagSentence('fetch failed: connect ECONNREFUSED 10.0.0.100:1234');
R.snagTimeout  = snagSentence('Error: request timed out after 120000ms');
R.snag500      = snagSentence('500 Internal Server Error');
R.snagUnknown  = snagSentence('the flux capacitor came loose');
// §6/§7: no jargon, no status codes, no raw dumps in ANY produced sentence.
R.snagClean = [R.snagRealKey,R.snag401,R.snag429,R.snagQuota,R.snagRefused,R.snagTimeout,R.snag500]
  .every(x => !/api[- ]?key|\b[45]\d\d\b|openrouter|econnrefused|bearer|quota|http/i.test(x));
R.snagAllPrefixed = [R.snagRealKey,R.snag401,R.snagUnknown].every(x => x.indexOf('hit a snag — ') === 0);
// An unrecognised cause must NOT be diagnosed — it falls through verbatim.
R.snagUnknownVerbatim = R.snagUnknown === 'hit a snag — the flux capacitor came loose';
// ── snagCause — the same verdict, without the spine ────────────────────
// Surfaces that supply their own subject/verb take this half. The contract
// is compositional so nobody is ever tempted to regex the prefix off
// snagSentence again (that produced "Kenji that brain isn't signed in yet").
R.causeComposes = ['OpenRouter 503: openrouter: no API key configured',
                   '429 Too Many Requests', 'the flux capacitor came loose', '', null]
  .every(x => snagSentence(x) === 'hit a snag — ' + snagCause(x));
R.causeNoSpine = ['OpenRouter 503: no API key configured', '429 Too Many Requests', '']
  .every(x => !/hit a snag/.test(snagCause(x)));
R.causeClean = ['OpenRouter 503: openrouter: no API key configured','HTTP 401 invalid bearer token',
                '429 Too Many Requests','insufficient_quota: exceeded','500 Internal Server Error']
  .map(snagCause).every(x => !/api[- ]?key|\b[45]\d\d\b|openrouter|bearer|quota|http/i.test(x));
// ── the floor event contract ───────────────────────────────────────────
R.evNames   = Object.keys(FLOOR_EVENT).sort();
R.evValues  = Object.keys(FLOOR_EVENT).map(k => FLOOR_EVENT[k]);
R.evUnique  = new Set(R.evValues).size === R.evValues.length;
R.evPrefixed = R.evValues.every(v => v.indexOf('cafresohq:') === 0);
// Unknown kind is a THROW, not a silent no-op — a typo must be loud.
R.evUnknownThrows = (() => { try { floorEmit('nope', { agentId: 'a1' }); return false; }
                             catch (e) { return /unknown floor event/.test(e.message); } })();
R.onUnknownThrows = (() => { try { floorOn('nope', () => {}); return false; }
                             catch (e) { return /unknown floor event/.test(e.message); } })();
// An event with nobody to attach it to is refused at the emitter.
const warned = [];
const _warn = console.warn; console.warn = (m) => warned.push(String(m));
R.evNoIdRefused  = floorEmit('coffee', {}) === false;
R.evNoIdWarned   = warned.length === 1 && /no agentId/.test(warned[0]);
R.evNullDetail   = floorEmit('artifact', null) === false;
console.warn = _warn;
// walkIn carries `id`, not `agentId` — both must count as placeable.
R.evAcceptsId    = (() => { const w = []; const o = console.warn; console.warn = (m) => w.push(m);
                            floorEmit('walkIn', { id: 'a1', color: 'teal' }); console.warn = o;
                            return w.length === 0; })();
// Headless (no window) returns false rather than exploding.
R.evHeadlessSafe = floorEmit('coffee', { agentId: 'a1' }) === false;
R.onHeadlessSafe = typeof floorOn('coffee', () => {}) === 'function';
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
    check('JSON shrapnel is stripped from an unrecognised cause',
          '{' not in out['snagJson'] and 'flux capacitor' in out['snagJson'],
          repr(out['snagJson']))
    check('URLs are dropped from the bubble',
          'http' not in out['snagUrl'] and 'while parsing' in out['snagUrl'], repr(out['snagUrl']))
    check('a recognised cause leaks none of the raw text it replaced',
          out['snagNoLeak'])
    check('long messages are capped with an ellipsis',
          out['snagLong'].endswith('…') and out['snagLongLen'] <= 104,
          str(out['snagLongLen']))
    check('empty error still says something honest',
          out['snagEmpty'] == 'hit a snag — something went wrong on the last run')
    check('null error tolerated', out['snagNull'] == out['snagEmpty'])

    # snagCause — the clause half, for surfaces that bring their own verb
    check('snagSentence is exactly the spine plus snagCause',
          out['causeComposes'])
    check('snagCause never carries the "hit a snag" spine',
          out['causeNoSpine'])
    check('snagCause leaks no jargon either',
          out['causeClean'])

    # deskKit — capability, not achievement
    check('vault grants a cabinet', out['kitVault'] == ['cabinet'])
    check('files grants a cabinet', out['kitFiles'] == ['cabinet'])
    check('web grants a phone', out['kitWeb'] == ['phone'])
    check('email grants a phone', out['kitEmail'] == ['phone'])
    check('search grants a bookshelf', out['kitSearch'] == ['bookshelf'])
    check('a full kit picks phone + cabinet', out['kitFull'] == ['phone', 'cabinet'],
          repr(out['kitFull']))
    check('storage synonyms collapse to ONE cabinet', out['kitDedup'] == ['cabinet'],
          repr(out['kitDedup']))
    check('room never shows more than 2 props', len(out['kitCap']) == 2, repr(out['kitCap']))
    check('toolless agent still gets a shelf (never a bare room)',
          out['kitNone'] == ['bookshelf'])
    check('null tools tolerated', out['kitNull'] == ['bookshelf'])
    check('unmappable tools claim nothing, fall back to shelf',
          out['kitJunk'] == ['bookshelf'], repr(out['kitJunk']))
    check('every kit prop has a placard (walk destinations exist)',
          all(p in out['placards'] for p in
              set(out['kitFull'] + out['kitSearch'] + out['kitNone'])))

    # ── snag sentences ────────────────────────────────────────────────
    # A live failed run put "hit a snag — OpenRouter 503: error :
    # openrouter: no API key configured" on the floor: a status code, a
    # provider name, a doubled "error :", and a §6-banned term.
    check('a real missing-sign-in failure reads as one office sentence',
          out['snagRealKey'] == "hit a snag — that brain isn't signed in yet — add it in Settings, or give this to someone else",
          out['snagRealKey'])
    check('401 maps to the same sign-in cause', 'signed in' in out['snag401'], out['snag401'])
    check('429 says to wait, not what the code was', 'rate-limited' in out['snag429'], out['snag429'])
    check('quota failures name credit, not billing APIs', 'credit' in out['snagQuota'], out['snagQuota'])
    check('a refused connection reads as offline', 'offline' in out['snagRefused'], out['snagRefused'])
    check('a timeout says we stopped waiting', 'stopped waiting' in out['snagTimeout'], out['snagTimeout'])
    check('5xx says it is not the user\'s fault', 'not something you did' in out['snag500'], out['snag500'])
    check('no produced sentence leaks jargon or a status code', out['snagClean'])
    check('every sentence still opens with the snag phrase', out['snagAllPrefixed'])
    check('an unrecognised cause is NOT diagnosed, just cleaned',
          out['snagUnknownVerbatim'], out['snagUnknown'])

    # ── the floor event contract ──────────────────────────────────────
    # Six names, one table. These used to be raw literals at ~30 sites; a
    # typo in one is a silently dead beat, which is the hardest kind of
    # bug to notice in an animation layer.
    check('all six floor events are declared',
          out['evNames'] == ['activity', 'artifact', 'coffee', 'screen', 'tool', 'walkIn'],
          str(out['evNames']))
    check('event names are unique', out['evUnique'])
    check('every event is namespaced', out['evPrefixed'])
    check('an unknown event kind throws at the emitter', out['evUnknownThrows'])
    check('an unknown event kind throws at the listener', out['onUnknownThrows'])
    check('an event with no agentId is refused', out['evNoIdRefused'])
    check('...and says so once, at the site that got it wrong', out['evNoIdWarned'])
    check('a null detail is refused, not thrown', out['evNullDetail'])
    check('walkIn\'s `id` counts as placeable', out['evAcceptsId'])
    check('emitting headless returns false, never throws', out['evHeadlessSafe'])
    check('subscribing headless returns an unsubscribe', out['onHeadlessSafe'])

    print()
    if FAILS:
        print(f'floor language: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('floor language: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

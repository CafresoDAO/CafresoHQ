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
/* A dead connection, worded by each engine that ships one. The table used to
   speak only Chrome: `network error` (spaced) misses Firefox's
   `NetworkError`, and nothing matched Safari's `Load failed`, so on two of
   three engines an offline failure fell through to the raw first line — on
   every surface using this classifier. Found by pulling the network under a
   real vault delete and reading the toast. */
R.netChrome   = snagCause('Failed to fetch');
R.netFirefox  = snagCause('NetworkError when attempting to fetch resource.');
R.netSafari   = snagCause('Load failed');
R.netRefused  = snagCause('connect ECONNREFUSED 127.0.0.1:8787');
/* The same four wordings through the OFFICE shape. Widening the connectivity
   pattern above is what taught a vault delete to blame a brain — one fix, two
   subjects — so the two subjects are now asserted side by side, in the suite
   run_tests.py actually runs. scripts/test_cause_subject.py owns the rest of
   the office table; this is the row with a history. */
R.offChrome   = officeCause('Failed to fetch');
R.offFirefox  = officeCause('NetworkError when attempting to fetch resource.');
R.offSafari   = officeCause('Load failed');
R.offRefused  = officeCause('connect ECONNREFUSED 127.0.0.1:8787');
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
// Measured live: a cold local Ollama produced exactly this, and it used to
// fall through to the raw line, leaking the banned word "backend".
R.snagCold     = snagSentence('backend did not start responding within 20s');
R.snag500      = snagSentence('500 Internal Server Error');
R.snagUnknown  = snagSentence('the flux capacitor came loose');
// §6/§7: no jargon, no status codes, no raw dumps in ANY produced sentence.
R.snagClean = [R.snagRealKey,R.snag401,R.snag429,R.snagQuota,R.snagRefused,R.snagTimeout,R.snag500,R.snagCold]
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
// ── visit vocabulary (§6 "tool call → the action itself") ───────────────
R.vWeb    = visitLine('BROWSER_FETCH', 'https://en.wikipedia.org/wiki/Paris', 'past');
R.vWebNow = visitLine('BROWSER_FETCH', 'https://en.wikipedia.org/wiki/Paris', 'now');
R.vSearch = visitLine('WEB_SEARCH', 'primary colours', 'past');
R.vVault  = visitLine('MEMORY_READ', 'facts/france.md', 'past');
R.vVaultNow = visitLine('MEMORY_READ', 'facts/france.md', 'now');
R.vUnknown  = visitLine('WEIRD_THING', 'stuff', 'past');
R.vNoArg    = visitLine('MEMORY_READ', '   ', 'past');
R.vNullArg  = visitLine('MEMORY_READ', null, 'now');
R.vCapped   = visitLine('BROWSER_FETCH', 'x'.repeat(200), 'past');
R.vNewlines = visitLine('MEMORY_READ', 'a\n\nb', 'past');
R.vIconWeb   = visitWords('BROWSER_FETCH').icon;
R.vIconSearch= visitWords('WEB_SEARCH').icon;
R.vIconVault = visitWords('VAULT_READ').icon;
R.vIconOther = visitWords('NOPE').icon;
R.vSubjScheme = visitSubject('https://example.com/a');
R.vSubjHttp   = visitSubject('http://example.com/a');
// Every surface's copy must be free of the tool's own name (§6).
R.vNoToolName = ['BROWSER_FETCH','WEB_SEARCH','MEMORY_READ','VAULT_READ']
  .map(n => [visitLine(n,'x','past'), visitLine(n,'x','now')].join(' '))
  .join(' ');
// ── the office's voice must not re-enter the model's context ────────────
R.ovForged = stripOfficeVoice('\u{1F4E1} MEMORY_READ("facts/france.md") \u2192\nFound note!\n\n\u{1F4C1} Opened facts/france.md\n(no memory)');
R.ovKeepsResult = /no memory|Found note!/.test(R.ovForged);
R.ovHeadsGone   = /\u{1F4E1}|\u{1F4C1} Opened/u.test(R.ovForged);
R.ovAllIcons    = stripOfficeVoice('a\n\u{1F310} Read x.com\n\u{1F50E} Looked up y\n\u{1F4C1} Opened z\n\u{1F5D2} Checked w\nb');
R.ovPresent     = stripOfficeVoice('a\n\u{1F4C1} opening z\nb');
R.ovProseSafe   = stripOfficeVoice('I opened the door and read the sign.');
R.ovIconInProse = stripOfficeVoice('Send \u{1F310} to the team about the launch plan');
R.ovIndented    = stripOfficeVoice('a\n   \u{1F310} Read x.com   \nb');
R.ovEmpty       = stripOfficeVoice('');
R.ovNull        = stripOfficeVoice(null);
// ── argument-less visits fall back to the placard, not to nothing ───────
R.vpCabinet = visitPlace('MEMORY_LIST', 'past');
R.vpShelf   = visitPlace('SEARCH', 'now');
R.vpPhone   = visitPlace('BROWSER_FETCH', 'past');
R.vpUnknown = visitPlace('WEIRD_THING', 'now');
R.vpUnknownPast = visitPlace('WEIRD_THING', 'past');
R.vpMatchesPlacard = visitPlace('MEMORY_LIST', 'past') === PROP_PLACARD.cabinet;
// ── toVisit: structured data, never text ────────────────────────────────
R.tvHead = toVisit({ name: 'MEMORY_READ', arg: 'facts/france.md', result: 'nothing here' });
R.tvNoArg = toVisit({ name: 'MEMORY_LIST', arg: '', result: 'a\nb' });
R.tvNoName = toVisit({ arg: 'x', result: 'y' });
R.tvNull   = toVisit(null);
R.tvEmptyResult = toVisit({ name: 'MEMORY_READ', arg: 'x', result: '' }).body;
R.tvNullResult  = toVisit({ name: 'MEMORY_READ', arg: 'x', result: null }).body;
R.tvCapped = toVisit({ name: 'BROWSER_FETCH', arg: 'a.com', result: 'z'.repeat(5000) }).body.length;
R.tvCappedEllipsis = /\u2026$/.test(toVisit({ name: 'BROWSER_FETCH', arg: 'a.com', result: 'z'.repeat(5000) }).body);
// A visit object must expose no field a model could have authored as prose.
R.tvKeys = Object.keys(toVisit({ name: 'MEMORY_READ', arg: 'x', result: 'y' })).sort().join(',');
// `name`/`arg` are the record, not the caption — they exist so a stopped
// run can be replayed to the brain in the frame a live hop uses. Pinned to
// their real values so a future edit cannot leave the keys and empty them.
R.tvRecord = (v => v.name + '|' + v.arg)(
  toVisit({ name: 'MEMORY_READ', arg: '  facts/france.md  ', result: 'y' }));
/* A tool can fail WITHOUT raising — a missing file, a path that isn't a
   directory, a non-zero exit all answer normally with the explanation as the
   result. Watched live 2026-08-13: a failed DIR_LIST rendered "Opened ./site"
   directly above its own "Not a directory: ./site". The visit must take its
   tense from the outcome, not from the fact that something came back. */
R.tvFail      = toVisit({ name: 'DIR_LIST', arg: './site', result: 'Not a directory: ./site', failed: true });
R.tvFailWrite = toVisit({ name: 'FILE_WRITE', arg: 'notes/x.md', result: 'nope', failed: true });
R.tvFailNoArg = toVisit({ name: 'MEMORY_LIST', arg: '', result: 'nope', failed: true });
R.tvOkStillPast = toVisit({ name: 'DIR_LIST', arg: './site', result: 'a\nb', failed: false }).head;
/* The verb, not just the noun. This table keyed on VAULT|FILE|MEMORY alone,
   so every write came out "Opened notes/x.md" — the coworker saved something
   and the floor said they looked at it — and EXPORT/GENERATE/PUBLISH fell to
   the modest default, "Checked deck.pptx", for work that produced a file.
   Found by running all 31 registry tools through visitWords rather than
   spot-checking; VAULT_NEW was still wrong after the first fix because its
   name says NEW, not WRITE. */
R.vWrites = ['MEMORY_WRITE','MEMORY_APPEND','FILE_WRITE','VAULT_NEW','VAULT_APPEND']
  .map(n => visitLine(n, 'x.md', 'past'));
R.vReads  = ['VAULT_READ','FILE_READ','MEMORY_READ','DIR_LIST']
  .map(n => visitLine(n, 'x.md', 'past'));
R.vMade   = visitLine('EXPORT_PPTX', 'deck.pptx', 'past');
R.vPub    = visitLine('PUBLISH_SITE', 'site/', 'past');
R.vSearchTool = visitLine('VAULT_SEARCH', 'gold', 'past');

/* toolActivity — the line filed into the activity feed. Both call sites in
   app.jsx used to build this by hand, on the `start` phase, in the PAST
   tense: the feed said "saved report.md" before the save was attempted and
   never went back to correct it when the save failed. */
const AG = { id: 'a1', name: 'Nova', color: '#8ab' };
/* JSON.stringify DROPS undefined values, so a dropped field would reach the
   python side as a missing key and blow up with a KeyError instead of the
   assertion's own explanation. Pin every field to null so a regression reads
   as the failure it is. */
const keep = o => ({ agentId: o.agentId ?? null, agentName: o.agentName ?? null,
                     color: o.color ?? null, action: o.action ?? null,
                     text: o.text ?? null, taskId: o.taskId ?? null });
R.actOk    = keep(toolActivity(AG, { name: 'VAULT_NEW', arg: 'report.md', failed: false }));
R.actFail  = keep(toolActivity(AG, { name: 'VAULT_NEW', arg: 'report.md', failed: true }));
R.actNoFlag= keep(toolActivity(AG, { name: 'DIR_LIST', arg: './site' })).text;
R.actNoArg = keep(toolActivity(AG, { name: 'MEMORY_LIST', arg: '', failed: true })).text;
R.actExtra = keep(toolActivity(AG, { name: 'FILE_WRITE', arg: 'x.md' }, { taskId: 't9' })).taskId;
R.actNoAgent = (() => { try { return toolActivity(null, { name: 'DIR_LIST', arg: 'x' }).text; }
                        catch (e) { return 'THREW: ' + e.message; } })();
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
    OFFLINE = "couldn't reach that brain — it looks offline from here"
    for engine, key in (('Chrome', 'netChrome'), ('Firefox', 'netFirefox'),
                        ('Safari', 'netSafari'), ('Node/ECONNREFUSED', 'netRefused')):
        check(f'a dead connection is classified on {engine}',
              out[key] == OFFLINE,
              f"{out[key]!r} — this table is shared by every surface, so an "
              f"engine it cannot parse leaks that engine's raw wording "
              f"app-wide, not just on one screen")

    # The same four wordings, the other subject. Widening the pattern above is
    # what taught a vault delete to say "couldn't reach that brain" about the
    # boss's own filing cabinet: the fix was right, it just had two callers and
    # only one got checked. Both are checked here now.
    for engine, key in (('Chrome', 'offChrome'), ('Firefox', 'offFirefox'),
                        ('Safari', 'offSafari'), ('Node/ECONNREFUSED', 'offRefused')):
        check(f'...and blames the OFFICE, not a brain, on {engine}',
              out[key] == "the office isn't answering — check it's still running",
              f"{out[key]!r} — a file, the vault and a publish have no brain to be "
              f"offline; naming one sends the boss to their model settings, which "
              f"cannot help")

    check('URLs are dropped from the bubble',
          'http' not in out['snagUrl'] and 'while parsing' in out['snagUrl'], repr(out['snagUrl']))
    check('a recognised cause leaks none of the raw text it replaced',
          out['snagNoLeak'])
    check('a cold local model reads as warming up, not "backend"',
          'warming up' in out['snagCold'] and 'backend' not in out['snagCold'].lower(),
          repr(out['snagCold']))
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

    # visit vocabulary — one table for bubble, log, echo and filed note
    check('a fetch reads its source', out['vWeb'] == 'Read en.wikipedia.org/wiki/Paris', str(out['vWeb']))
    check('…and reads it in the present tense on a live bubble',
          out['vWebNow'] == 'reading en.wikipedia.org/wiki/Paris', str(out['vWebNow']))
    check('a search looks something up', out['vSearch'] == 'Looked up primary colours', str(out['vSearch']))
    check('search wins over web on WEB_SEARCH', 'Read' not in str(out['vSearch']))
    check('a memory read opens a file', out['vVault'] == 'Opened facts/france.md in their notes', str(out['vVault']))
    check('…present tense for the bubble', out['vVaultNow'] == 'opening facts/france.md in their notes', str(out['vVaultNow']))
    check('an unknown tool still names an action', out['vUnknown'] == 'Checked stuff', str(out['vUnknown']))
    check('a visit with no subject says nothing', out['vNoArg'] is None and out['vNullArg'] is None)
    check('a runaway subject is capped', len(out['vCapped']) <= 94 and out['vCapped'].endswith('\u2026'),
          str(len(out['vCapped'])))
    check('newlines never break the one-liner', '\n' not in out['vNewlines'])
    check('each visit kind has its own icon',
          len({out['vIconWeb'], out['vIconSearch'], out['vIconVault'], out['vIconOther']}) == 4)
    check('the scheme is dropped from a url', out['vSubjScheme'] == 'example.com/a' and out['vSubjHttp'] == 'example.com/a')
    check('no phrasing anywhere names the tool (\u00a76)',
          not any(n in out['vNoToolName'] for n in ('BROWSER_FETCH','WEB_SEARCH','MEMORY_READ','VAULT_READ')),
          out['vNoToolName'])

    # the office's voice never becomes the model's
    check('a forged echo head is removed', out['ovHeadsGone'] is False, repr(out['ovForged']))
    check('…but the result bodies survive as context', out['ovKeepsResult'] is True,
          repr(out['ovForged']))
    check('every visit icon+verb head is caught', out['ovAllIcons'] == 'a\n\nb',
          repr(out['ovAllIcons']))
    check('the present-tense form is caught too', out['ovPresent'] == 'a\n\nb',
          repr(out['ovPresent']))
    check('ordinary prose using the same verbs is untouched',
          out['ovProseSafe'] == 'I opened the door and read the sign.')
    check('an icon mid-sentence is not a head line',
          out['ovIconInProse'] == 'Send \U0001F310 to the team about the launch plan',
          repr(out['ovIconInProse']))
    check('leading/trailing whitespace does not hide a head', out['ovIndented'] == 'a\n\nb',
          repr(out['ovIndented']))
    check('empty and null are safe', out['ovEmpty'] == '' and out['ovNull'] == '')

    # argument-less tools still say where they went
    check('MEMORY_LIST reads as the cabinet trip it is',
          out['vpCabinet'] == 'at the filing cabinet', str(out['vpCabinet']))
    check('a bare SEARCH is a bookshelf trip', out['vpShelf'] == 'at the bookshelf')
    check('a bare fetch is a phone call', out['vpPhone'] == 'on the phone')
    check('an unplaceable tool still says something true',
          out['vpUnknown'] == 'looking something up' and out['vpUnknownPast'] == 'looked something up')
    check('the fallback IS the floor placard, not a second wording',
          out['vpMatchesPlacard'] is True)

    # toVisit — the office's record as data
    check('a visit carries icon + office-words head',
          out['tvHead']['icon'] == '\U0001F4C1' and out['tvHead']['head'] == 'Opened facts/france.md in their notes',
          str(out['tvHead']))
    check('…and the real result as its body', out['tvHead']['body'] == 'nothing here')
    check('an argument-less visit falls back to the placard',
          out['tvNoArg']['head'] == 'at the filing cabinet', str(out['tvNoArg']))
    check('a nameless or missing event yields no visit',
          out['tvNoName'] is None and out['tvNull'] is None)
    check('empty and null results become an empty body, not "null"',
          out['tvEmptyResult'] == '' and out['tvNullResult'] == '')
    check('a huge result is capped so it cannot bury the answer',
          out['tvCapped'] <= 620 and out['tvCappedEllipsis'] is True, str(out['tvCapped']))
    # `name` and `arg` joined the shape when chatToMessages learned to
    # replay a stopped run's results to the brain: a result needs the frame
    # it arrived in, and `head` — the office's own words for the trip — is
    # the one thing that must never go back into a prompt. The pin stays
    # exact so a third field cannot arrive unexamined; see
    # scripts/test_the_coworker_can_pick_it_up.py, which owns the replay
    # and checks that only these two ever leave the message.
    # `outcome` joined the shape in `#313`. `failed` alone was enough while
    # there was one way for a trip not to work; WALLET_SEND can distinguish a
    # send the boss REFUSED, a send PENDING their stamp and a send that broke,
    # and the FILED note re-derives its own tense from this stored record long
    # after the event is gone. This pin stays exact — it is here so a field
    # cannot arrive unexamined, and this one was examined: it is the office's
    # own vocabulary word, never model text, and it does not go back into a
    # prompt.
    check('the visit shape is exactly {arg, at, body, failed, head, icon, name, outcome}',
          out['tvKeys'] == 'arg,at,body,failed,head,icon,name,outcome', out['tvKeys'])
    check('…and the two the transcript replays hold the real call',
          out['tvRecord'] == 'MEMORY_READ|facts/france.md',
          [out['tvRecord'], '— trimmed but never truncated: `body` is capped '
           'because a page fetch is long, and a path cut short is a '
           'different path'])

    # A trip that did not work must not be captioned as one that did.
    check('a failed visit says it could not, and wears the warning icon',
          out['tvFail']['head'] == "Couldn't open ./site"
          and out['tvFail']['icon'] == '⚠'
          and out['tvFail']['failed'] is True,
          str(out['tvFail']))
    check('…and keeps the real reason as its body',
          out['tvFail']['body'] == 'Not a directory: ./site', str(out['tvFail']))
    check('a failed write says it could not save, not that it saved',
          out['tvFailWrite']['head'] == "Couldn't save notes/x.md", str(out['tvFailWrite']))
    check('a failed argument-less visit does not borrow the prop placard',
          out['tvFailNoArg']['head'] == "couldn't do that", str(out['tvFailNoArg']))
    check('a visit that DID work still reads in the past tense',
          out['tvOkStillPast'] == 'Opened ./site in the project', out['tvOkStillPast'])

    check('every write reads as a write, not as a read',
          all(v.startswith('Saved ') for v in out['vWrites']), out['vWrites'])
    check('…and reads are untouched',
          all(v.startswith('Opened ') for v in out['vReads']), out['vReads'])
    check('an export is something they made', out['vMade'] == 'Made deck.pptx in the cabinet', out['vMade'])
    # Said 'Published site/' until #76 — PUBLISH_SITE queues an approval and
    # publishes nothing, so the past tense here sat one line above its own
    # "Nothing is public yet".
    check('a publish says it was asked for, not done',
          out['vPub'] == 'Asked to publish site/', out['vPub'])
    check('a vault search still looks it up', out['vSearchTool'] == 'Looked up gold in the cabinet', out['vSearchTool'])

    # toolActivity — the activity feed is a RECORD, so it reads in the past
    # tense; that is exactly why it may only be written once the outcome is
    # known. These pin the tense to the outcome and nothing else.
    check('a filed tool line carries the coworker and the tool action',
          out['actOk']['agentId'] == 'a1' and out['actOk']['agentName'] == 'Nova'
          and out['actOk']['color'] == '#8ab' and out['actOk']['action'] == 'tool',
          str(out['actOk']))
    check('a write that landed is filed as saved',
          out['actOk']['text'] == 'saved report.md in the cabinet', str(out['actOk']))
    check('a write that failed is NOT filed as saved',
          out['actFail']['text'] == "couldn't save report.md", str(out['actFail']))
    check('an event with no failed flag is treated as success',
          out['actNoFlag'] == 'opened ./site in the project', str(out['actNoFlag']))
    check('a failed argument-less tool does not borrow the placard',
          out['actNoArg'] == "couldn't do that", str(out['actNoArg']))
    check('extra fields (taskId) ride along so the task card can show the trip',
          out['actExtra'] == 't9', str(out['actExtra']))
    check('a missing agent does not throw inside the stream callback',
          not str(out['actNoAgent']).startswith('THREW'), str(out['actNoAgent']))

    print()
    if FAILS:
        print(f'floor language: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('floor language: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

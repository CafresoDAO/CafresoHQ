#!/usr/bin/env python3
"""Night Shift's scheduling error message could be a raw JS parser error.

`missions.jsx`'s `NightShiftSection` talks to serve.py through one shared
helper:

    const nsFetch = (path, opts) =>
      fetch(nsBase() + path, { credentials: 'include', ...(opts || {}) }).then(r => r.json());

Unconditional `.json()` — no `r.ok` check, no guard around a body that
isn't valid JSON. A proxy error page, an empty 502, a stray 404 served by
whatever is in front of serve.py: any of those reject with a raw
`SyntaxError`, V8's own words for "this wasn't JSON" —

    Unexpected token '<', "<html><bo"... is not valid JSON
    Unexpected end of JSON input

`schedule()`'s catch (missions.jsx:787, added deliberately to attribute a
scheduler failure without running it through the BRAIN-only `snagCause`
classifier — see the comment a few lines above it) then put that string on
screen verbatim:

    catch (e) { setMsg(`Couldn't schedule that — ${String(e.message || e)}`); }

"Couldn't schedule that — Unexpected token '<', \"<html><bo\"... is not
valid JSON" is a parser's opinion of a response body, not an office
sentence — the exact raw-dump shape §7 bans, and the same shape task #2's
`night_runner.py` fix (`docs/OFFICE_AS_INTERFACE.md`, "A brain failure
reached the boss as a stack trace") already eliminated on the SERVER side
of this same feature. This is the client side of the identical mistake.

**The fix.** `nsFetch` still rejects on a bad body — `load()`'s "office
offline" handling depends on that and is untouched — but the rejection now
carries one honest, hand-written sentence naming the actual HTTP status
instead of the parser's own message:

    .then(r => r.json().catch(() => {
      throw new Error(`the server's answer couldn't be read (HTTP ${r.status}...)`);
    }))

`schedule()`'s catch is unchanged; it already does the right thing with
whatever `e.message` holds, so the fix is entirely in what `nsFetch` hands
it.

Run: python3 scripts/test_night_shift_bad_response_is_not_a_parser_error.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = (ROOT / 'missions.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Night Shift: a bad response reads as one sentence, not a parser error")

    # ── 1. the source ──────────────────────────────────────────────────
    start = MISSIONS.index('const nsBase = (')
    end = MISSIONS.index('/* Next occurrence of 2:00 AM local')
    block = MISSIONS[start:end]

    # Regression as sharp as it gets: no .catch() at all means every
    # non-JSON body rejects with the raw SyntaxError again.
    check('nsFetch still guards the JSON parse',
          '.json().catch(' in block, block)

    check('...and does not swallow it into a resolved value',
          'throw new Error(' in block,
          'load() (missions.jsx:703-710) treats ANY nsFetch rejection as '
          '"office offline" — turning the catch into a resolved {error} '
          'object would make a genuinely bad response look reachable-but-empty')

    check('...names the real HTTP status rather than repeating the parser',
          re.search(r"throw new Error\(`[^`]*\$\{r\.status\}", block) is not None,
          block)

    thrown_msg_m = re.search(r'throw new Error\(`([^`]*)`\)', block)
    check("...and the thrown message doesn't quote the parser's own vocabulary",
          thrown_msg_m is not None
          and not re.search(r'Unexpected|JSON\.parse|SyntaxError', thrown_msg_m.group(1), re.I),
          'the whole point is that the sentence is hand-written, not the '
          "engine's own parse-error text — checked on the actual thrown "
          "template literal, not the surrounding explanatory comment, which "
          "necessarily quotes those exact words to describe the bug it fixed")

    schedule_a = MISSIONS.index('const schedule = async (startAtMs) => {')
    schedule_b = MISSIONS.index('const cancel = async (id) => {')
    schedule_src = MISSIONS[schedule_a:schedule_b]
    check('schedule() still surfaces whatever nsFetch rejects with',
          'setMsg(`Couldn\'t schedule that — ${String(e.message || e)}`)' in schedule_src,
          'this ticket fixes what the message CONTAINS, not this line — '
          'changing this line without fixing nsFetch would just move the leak')

    # ── 2. the mechanism, run for real: node, no browser needed ─────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        js = block + r'''
const CafresoHQClient = { backendBase: () => '' };

function fakeResponse(status, statusText, parseError) {
  return { status, statusText, json: () => Promise.reject(parseError) };
}

async function attempt(fetchImpl) {
  global.fetch = fetchImpl;
  try {
    const res = await nsFetch('/missions/schedule', { method: 'POST' });
    return { resolved: res };
  } catch (e) {
    return { rejectedMessage: e.message };
  }
}

(async () => {
  const out = {};
  out.htmlProxyPage = await attempt(() => Promise.resolve(fakeResponse(
    502, 'Bad Gateway',
    new SyntaxError("Unexpected token '<', \"<html><bo\"... is not valid JSON"))));
  out.emptyOkBody = await attempt(() => Promise.resolve(fakeResponse(
    200, 'OK', new SyntaxError('Unexpected end of JSON input'))));
  out.happyPath = await attempt(() => Promise.resolve({
    status: 200, statusText: 'OK', json: () => Promise.resolve({ schedule: { id: 'abc123' } }) }));
  out.structuredErrorBody = await attempt(() => Promise.resolve({
    status: 400, statusText: 'Bad Request', json: () => Promise.resolve({ error: 'topic required' }) }));
  console.log(JSON.stringify(out));
})();
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:600])
        else:
            out = json.loads(p.stdout)

            msg = out['htmlProxyPage'].get('rejectedMessage', '')
            check('a proxy HTML error page still rejects (load() stays honest '
                  'about being unreachable)', 'rejectedMessage' in out['htmlProxyPage'], out)
            check('...but the message is hand-written, not the parser\'s',
                  'Unexpected token' not in msg and 'is not valid JSON' not in msg, msg)
            check('...and names the real status', '502' in msg and 'Bad Gateway' in msg, msg)

            msg2 = out['emptyOkBody'].get('rejectedMessage', '')
            check('an empty-but-200 body is caught the same way',
                  'Unexpected end of JSON input' not in msg2 and '200' in msg2, msg2)

            check('a real JSON success body still resolves normally',
                  out['happyPath'].get('resolved', {}).get('schedule', {}).get('id') == 'abc123',
                  out['happyPath'])

            check("a real {error: ...} JSON body still resolves — schedule()'s "
                  "existing `if (res.error)` branch (missions.jsx ~769) must "
                  "still be the one that handles it, not a rethrow",
                  out['structuredErrorBody'].get('resolved', {}).get('error') == 'topic required',
                  out['structuredErrorBody'])

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

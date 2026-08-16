#!/usr/bin/env python3
"""A brief is trimmed before filing, and the record shows no sign of it.

Measured 2026-08-16. `createMessage` capped `body` at 8000 characters with
a bare `.slice(0, 8000)` — no marker, no count, no flag. A 9,023-character
brief filed as 8,000 and the record looked complete:

    bossTyped        9023
    kipWasHanded     9023      <- dispatch streams `prompt`, not the record
    registryFiled    8000
    lost             1023
    anyFieldNamingIt []

So the trim cost only the REGISTRY — the one surface whose whole job is to
be the account of what was sent. Three consequences:

  - the Inbox row rendered 8,000 characters as if they were the brief;
  - ↻ RE-SEND reads the body back (`dispatchToAgent(agent, m.body, …)`),
    so a retry handed the coworker a SHORTER job than the one that failed,
    and the confirm dialog shows 200 characters either way — no surface
    could show the difference;
  - and the row-button's skipped door is earned by "you are looking at
    what you are re-sending", a premise the trim makes false.

The fix mirrors `historyDropped` one field over: keep the cap (messages
persist; a pasted 2MB file has no business in the state blob) and make the
record carry the size of what it lost. `bodyDropped` on the record, a gap
line on the Inbox row that says WHICH WAY the gap runs, and the retry door
back up for both callers — naming the loss rather than refusing, because
8,000 characters of brief is usually still the brief and only the boss
knows if it is.

Run: python3 scripts/test_the_brief_says_what_it_lost.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_from(src, i):
    """The braced block starting at index `i` (which must be a '{')."""
    if i < 0 or i >= len(src) or src[i] != '{':
        return ''
    d = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            d += 1
        elif src[j] == '}':
            d -= 1
            if d == 0:
                return src[i:j + 1]
    return ''


def lift_arrow(src, decl):
    """`const foo = (…) => { … };` lifted whole, by its declaration line.

    `decl` ends with the opening brace, so the block is taken from that
    same character and the declaration is re-joined WITHOUT it — glueing
    `… => {` to a balanced `{…}` leaves one brace open, and node reports
    that as a syntax error at the end of the whole script.
    """
    i = src.find(decl)
    if i < 0:
        return ''
    body = brace_from(src, i + len(decl) - 1)
    return (decl[:-1] + body + ';') if body else ''


def main():
    print('the brief says what it lost')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    collab = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── the cap is a name, not a number scattered around ────────────────
    m = re.search(r'const MSG_BODY_CAP = (\d+);', bare)
    check('the cap has a name at module scope', bool(m),
          'a test that carries its own copy of 8000 passes a fix that '
          'changes the cap and forgets the accounting')
    cap = int(m.group(1)) if m else 0

    check('nothing slices a record body by a bare literal any more',
          '.slice(0, 8000)' not in bare,
          'the trim has to go through the named cap so one place owns it')
    check('the cap is spelt once',
          len(re.findall(r'\bMSG_BODY_CAP\b', bare)) >= 2
          and bare.count(f'= {cap};') == 1 if cap else False,
          'declared once, read where the trim happens')

    # ── the record carries the loss ─────────────────────────────────────
    check('the record has a field for what was cut',
          'bodyDropped: full.length - body.length,' in bare,
          'the arithmetic, not a boolean — "some was cut" is the same '
          'silence with a flag on it')

    # ── the row says it, and says which way it runs ─────────────────────
    check('the Inbox row renders the gap', 'm.bodyDropped > 0 &&' in collab)
    check('...with the count, not just a mark',
          'm.bodyDropped.toLocaleString()' in collab)
    check('...and says the COWORKER got the whole thing',
          'got the whole brief' in collab
          and 'than this record kept' in collab,
          'a reader who gets the direction backwards thinks the work was '
          'under-briefed, which is the opposite of what happened')
    check('...and does not promise it can be recovered',
          "can't be recovered from here" in collab)

    # ── the retry door ──────────────────────────────────────────────────
    resend = lift_arrow(app, 'const resendMessage = async (m, { confirm = true } = {}) => {')
    check('the re-send lifts', bool(resend))
    rbare = strip_comments(resend)
    check('a trimmed record forces the door open even for the row button',
          '(confirm || cut > 0)' in rbare,
          'the row button skips the door because the boss is looking at '
          'what they are re-sending — a trim makes that premise false')
    check('the re-send still sends the body it has',
          'dispatchToAgent(agent, m.body,' in rbare,
          'refusing would be worse (§7) — 8,000 characters of brief is '
          'usually still the brief, and only the boss knows if it is')

    # ── the trim costs the record and NOT the coworker ──────────────────
    disp_at = bare.find('const dispatchToAgent = async (agent, prompt, opts = {})')
    disp_end = bare.find('\n  const ', disp_at + 100)
    disp = bare[disp_at:disp_end] if -1 < disp_at < disp_end else ''
    check('the dispatch region lifts', bool(disp))
    # The region DOES read records back — twice, both times for `state`,
    # which is fine. What must never happen is a read of `.body`: the gap
    # line on the row promises the coworker got the untrimmed text, so the
    # moment a dispatch sources its prompt from the record that sentence
    # becomes a lie in the other direction. Named by variable rather than
    # by the call, so a third reader added later is covered too.
    readers = re.findall(r'const (\w+) = MessageRegistry\.getMessage\(', disp)
    leaks = [v for v in readers if re.search(r'\b' + v + r'\.body\b', disp)]
    check('the coworker is handed the prompt, never the filed copy',
          'body: prompt,' in disp and not leaks,
          [readers, leaks or 'no .body read'])

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behaviour checks need it')
        print()
        if FAILS:
            print(f'brief-trim: {len(FAILS)} FAILED')
            return 1
        print('brief-trim: source checks passed')
        return 0

    # ── behaviour: the real createMessage, the real re-send ─────────────
    i = app.find('    const createMessage = (input) => {')
    create = 'const createMessage = (input) => ' + brace_from(app, app.find('{', i + 30)) + ';'
    check('createMessage lifts', bool(i > 0 and create.endswith('};')))
    if not (create.endswith('};') and resend):
        print('FAIL — nothing to run')
        return 1

    js = f'''
const MSG_BODY_CAP = {cap};
let STORE = [];
const messagesRef = {{ get current() {{ return STORE; }} }};
const setMessages = (fn) => {{ STORE = fn(STORE); }};
const _now = () => 1700000000000;
let _n = 0;
const _genId = (p) => p + '_' + (++_n);
{create}

/* the re-send, with everything around it stubbed */
let ASKED, SENT, ANSWER, TOASTS;
let agents = [{{ id: 'a_kip', name: 'Kip' }}];
const dispatchToAgent = (agent, body, opts) => {{ SENT.push({{ to: agent.id, chars: body.length, parent: opts.parentMessageId }}); }};
const window = {{
  hqConfirm: async (msg, opts) => {{ ASKED.push({{ msg, danger: !!(opts && opts.danger) }}); return ANSWER; }},
  cafresohqToast: {{ warn: (t) => TOASTS.push(t), error: (t) => TOASTS.push(t), success: (t) => TOASTS.push(t) }},
}};
{resend}

const file = (chars) => {{
  STORE = [];
  const brief = 'HEAD:' + 'x'.repeat(Math.max(0, chars - 10)) + ':TAIL';
  const id = createMessage({{ toAgentId: 'a_kip', toAgentName: 'Kip', body: brief }});
  const rec = STORE.find(m => m.id === id);
  return {{ sent: brief.length, kept: rec.body.length, dropped: rec.bodyDropped,
           addsUp: rec.body.length + rec.bodyDropped === brief.length,
           keepsTheHead: rec.body.startsWith('HEAD:') }};
}};

const retry = async (dropped, confirmFlag, answer) => {{
  STORE = [{{ id: 'msg_x', parentId: null, state: 'failed', toAgentId: 'a_kip',
             toAgentName: 'Kip', fromAgentId: 'boss',
             body: 'y'.repeat(200), bodyDropped: dropped }}];
  ASKED = []; SENT = []; TOASTS = []; ANSWER = answer;
  await resendMessage(STORE[0], {{ confirm: confirmFlag }});
  return {{ asked: ASKED.length, danger: ASKED[0] ? ASKED[0].danger : null,
           says: ASKED[0] ? ASKED[0].msg : '', sent: SENT.length }};
}};

const R = {{
  under:  file(100),
  at:     file(MSG_BODY_CAP),
  over:   file(MSG_BODY_CAP + 1023),
  way:    file(MSG_BODY_CAP * 3),
  empty:  (() => {{ STORE = []; const id = createMessage({{ body: '' }});
                    const r = STORE.find(m => m.id === id);
                    return {{ body: r.body, dropped: r.bodyDropped }}; }})(),
  absent: (() => {{ STORE = []; const id = createMessage({{ toAgentId: 'a' }});
                    const r = STORE.find(m => m.id === id);
                    return {{ body: r.body, dropped: r.bodyDropped }}; }})(),
  rowWhole:   await retry(0, false, true),
  rowTrimmed: await retry(1023, false, true),
  palTrimmed: await retry(1023, true, true),
  refused:    await retry(1023, false, false),
}};
console.log(JSON.stringify(R));
'''
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted pieces run', False, p.stderr.strip()[:400])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a brief under the cap is filed whole, and says nothing',
          r['under']['kept'] == r['under']['sent'] and r['under']['dropped'] == 0,
          r['under'])
    check('a brief exactly at the cap reports nothing dropped',
          r['at']['kept'] == cap and r['at']['dropped'] == 0,
          [r['at'], '— an off-by-one here puts a "1 character was cut" line '
           'on a record that is whole'])
    check('a brief over the cap keeps the cap and names the rest',
          r['over']['kept'] == cap and r['over']['dropped'] == 1023,
          r['over'])
    check('the accounting adds up at every size',
          all(r[k]['addsUp'] for k in ('under', 'at', 'over', 'way')),
          [k for k in ('under', 'at', 'over', 'way') if not r[k]['addsUp']])
    check('what is kept is the START of the brief',
          all(r[k]['keepsTheHead'] for k in ('under', 'at', 'over', 'way')),
          'the gap line says the TAIL was cut')
    check('an empty body drops nothing rather than NaN',
          r['empty'] == { 'body': '', 'dropped': 0 }
          and r['absent'] == { 'body': '', 'dropped': 0 },
          [r['empty'], r['absent']])

    check('the row button still skips the door on a whole record',
          r['rowWhole']['asked'] == 0 and r['rowWhole']['sent'] == 1,
          [r['rowWhole'], '— the skip is earned there and must survive'])
    check('the row button asks when the record is short',
          r['rowTrimmed']['asked'] == 1 and r['rowTrimmed']['danger'] is True,
          r['rowTrimmed'])
    check('the question says how much is missing',
          '1,023 character' in r['rowTrimmed']['says']
          and 'SHORTENED' in r['rowTrimmed']['says'],
          r['rowTrimmed']['says'][:160])
    check('...and does not claim the tail can be got back',
          "isn't recoverable" in r['rowTrimmed']['says'],
          r['rowTrimmed']['says'][:160])
    check('the palette route asks once, not twice',
          r['palTrimmed']['asked'] == 1 and r['palTrimmed']['sent'] == 1,
          r['palTrimmed'])
    check('a boss who says no sends nothing',
          r['refused']['asked'] == 1 and r['refused']['sent'] == 0,
          r['refused'])

    print()
    if FAILS:
        print(f'brief-trim: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('brief-trim: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

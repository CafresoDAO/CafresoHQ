#!/usr/bin/env python3
"""The boss was asked to stamp work the office never showed them.

Watched end to end in a virgin office: hire the local Llama, take the
"Research brief" starter task, wait. The coworker researched it, filed it
to the cabinet, and asked for a stamp. The card:

    Research brief on pros and cons of remote work for a small team
    by Llama · awaiting stamp                     [APPROVE] [REJECT]

That is the whole card. The brief is not on it.

And that title is not a description the office wrote. `extractApproval`
lifts it out of the coworker's own `[NEEDS_APPROVAL: …]` marker — it is
the requester's one-line summary of its own output. The tray has a
`detail` slot for exactly this, under a comment reading "the title above
is the REQUESTER's summary of its own request — this gate exists to catch
a summary that doesn't match the action, so the boss has to be able to see
both." A previous pass wired it for the three kinds that ask permission.
The stamp — the commonest approval in the product, the one that fires on
every finished deliverable — still passed nothing, at all four sites.

The body was in scope at every one of them. Each site already handed it to
`logActivity`'s detail. The activity feed could show you the work; the
card where you decide could not.

The first real run after wiring it produced the case the gate was written
for: title "research proposal on remote work's impact on small teams",
body a two-sentence summary plus "now I need approval before proceeding
with further research". Those are not the same thing.

**Second defect, same rows.** They passed `elevated: !!agent.elevated`.
On an approval `elevated` means THIS DECISION carries privilege — the tray
draws a 🛡, a red rule and "coworker waiting on your call" off it. Read
from the agent it answers a different question: does this coworker hold
file and shell access. So a research brief written by Claude rendered in
the same visual language as "give me the run of the filesystem", and the
one card that should mean "stop and read this" got cheaper every time an
elevated coworker finished an ordinary job.

Run: python3 scripts/test_the_stamp_shows_the_work.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
CHAT = ROOT / 'ui' / 'chat.jsx'
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr[-1500:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def hq_preamble():
    """The REAL hq-runtime, so approvalBody/visibleReply/cleanHarmony run
    rather than being reimplemented in the test. Imports and the export
    statement come off; the browser globals it touches on the way past are
    declared undefined, which its own guards already handle."""
    s = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
    s = re.sub(r'(?m)^\s*import\s.*$', '', s)
    s = re.sub(r'(?m)^\s*export\s*\{[^}]*\}\s*;?\s*$', '', s)
    return 'var CafresoHQClient, React, localStorage, window;\n' + s


def literals(src):
    """Every `onApprovalRequest({…})` argument, brace-matched."""
    out = []
    for m in re.finditer(r'onApprovalRequest\(\{', src):
        j = src.index('{', m.end() - 1)
        d, k = 0, j
        while k < len(src):
            if src[k] == '{':
                d += 1
            elif src[k] == '}':
                d -= 1
                if d == 0:
                    break
            k += 1
        out.append(src[j:k + 1])
    return out


# Long on purpose, and NOT a prefix of the title: a fixture shorter than the
# cap cannot see a truncation bug, and one that echoes the title cannot see
# a card that quietly shows the title twice.
BODY = ('Remote work suits small teams for three reasons. '
        + 'Concrete finding number %d, with enough words after it to matter. '
          % 1
        + ('Supporting detail that goes on. ' * 60))
TITLE = 'research proposal on remote work'


def main():
    print('an approval has to show the work, not the requester\'s summary of it')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    chat = CHAT.read_text(encoding='utf-8')
    feats = FEATURES.read_text(encoding='utf-8')
    HQ = hq_preamble()

    # ── 1. approvalBody, run for real ───────────────────────────────────
    def body(js_arg):
        return run_js(HQ + f'\nconsole.log(JSON.stringify(approvalBody({js_arg})));')

    check('nothing to show stays nothing', body("''") == '' and body('null') == '',
          'an empty <pre> is a worse card than no <pre>')
    short = body(json.dumps('Two short sentences.'))
    check('a short deliverable is shown whole', short == 'Two short sentences.', short)

    long_out = body(json.dumps(BODY))
    # Not `len(out) < len(BODY)`: approvalBody trims, BODY ends in a space,
    # so removing the cap entirely still shrinks it by one character and that
    # check went green on a body with no cap at all. Assert the SIZE it was
    # cut to, which only a real cap can satisfy.
    check('a long one is cut to something the card can hold',
          len(long_out) <= 1400 and len(BODY) > 1800,
          f'{len(long_out)} out of {len(BODY)} — the tray renders this in a '
          '<pre>; an uncapped deliverable pushes the buttons off the tray')
    check('...and SAYS it was cut',
          'shortened' in long_out,
          'silently showing the first part of a longer brief swaps one false '
          'impression for another — the boss would stamp it believing they '
          'had read it')
    check('...keeping the beginning, not a middle',
          long_out.startswith('Remote work suits small teams'), long_out[:60])

    # ── 2. every stamp site hands the work over ─────────────────────────
    SITES = [
        ('app.jsx', app,
         "const agent = { id:'a_llama', name:'Llama', elevated:true };\n"
         "const a = agent;\nconst taskId = 't_1';\n"),
        # The CEO site gets the RAW stream, marker and all — it has to clean
        # what it hands over. A fixture without a marker could not see that
        # cleaning removed, which is how the last three fixtures went blind.
        ('ui/chat.jsx', chat,
         # Marker FIRST. Appended, it sat past the 1200-character cut and was
         # truncated away before the scaffolding check could see it — the
         # cleaning arm went green with the cleaning removed.
         "const finalText = %s;\n"
         % json.dumps('[NEEDS_APPROVAL: ' + TITLE + ']\n' + BODY)),
    ]
    seen = 0
    for label, src, extra in SITES:
        for lit in literals(src):
            if not re.search(r"kind:\s*'awaiting stamp'", lit):
                continue
            seen += 1
            # No stub HQ: hq-runtime.jsx declares the real one, and the call
            # sites reach it as `HQ.approvalBody`, so the helper the app uses
            # is the helper under test.
            scope = (HQ + f'\nconst approvalDesc = {json.dumps(TITLE)};\n'
                     + f'const cleanBuf = {json.dumps(BODY)};\n' + extra)
            obj = run_js(scope + f'console.log(JSON.stringify({lit}));')
            got = obj.get('detail')
            check(f'{label}: a stamp request carries the work itself',
                  bool(got),
                  'the card is a title, a byline and two buttons — and the '
                  'title is the string the requester wrote about its own '
                  'output')
            check(f'{label}: ...the body, not the title again',
                  bool(got) and got != obj.get('title')
                  and got.startswith('Remote work suits small teams'),
                  f'{str(got)[:70]!r} vs title {obj.get("title")!r}')
            check(f'{label}: ...and no scaffolding in it',
                  bool(got) and 'NEEDS_APPROVAL' not in got
                  and '[HANDOFF' not in got,
                  f'{str(got)[-80:]!r} — §6 keeps marker syntax off the one '
                  'card the boss is asked to read closely')
            check(f'{label}: a stamp is not dressed as a privilege request',
                  obj.get('elevated') in (None, False),
                  'the tray draws a 🛡, a red rule and "coworker waiting on '
                  'your call" off `elevated`; set from the AGENT it fires on '
                  'every ordinary deliverable from anyone with file access, '
                  'and the one badge that should mean "stop and read" stops '
                  'meaning anything')

    check('all four stamp sites were found and checked', seen == 4,
          f'{seen} — app.jsx has three (DM reply, delegate, task run) and '
          'ui/chat.jsx has the CEO one; a new path that skips this is how '
          'the gate went unwired for so long')

    # ── 3. the tray still has somewhere to put it ───────────────────────
    check('the tray renders the verbatim body', 'p.detail &&' in feats,
          'features.jsx')
    i = feats.find('function ApprovalTray')
    tray = feats[i:i + 1200] if i >= 0 else ''
    check('the shield is still driven by the request, not the row',
          "p.elevated ? '🛡 '" in tray,
          'features.jsx — the flag is the contract; this test pins the call '
          'sites to setting it truthfully rather than the tray to ignoring it')

    print()
    if FAILS:
        print(f'stamp: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('stamp: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

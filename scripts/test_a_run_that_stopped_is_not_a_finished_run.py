#!/usr/bin/env python3
"""A task card that ran out of turns mid-job was filed as DONE.

Reproduced 2026-08-16 on office 9280 against the canned brain on port
9236. One card, "Summarise the vendor notes", handed to a local brain with
vault access. The brain answered every hop the same way:

    Let me check the vendor notes on file before I answer.

    [VAULT_READ: Research/vendor-notes.md]

Four hops, four identical trips to the same file, and the tool budget ran
out before it ever wrote a summary. `asked.jsonl` grew by exactly four.
Then every record the office keeps agreed the job was finished:

    tasks.json     status: "done", blockedReason: "", blockedAt: null
    the card       result: the stalling sentence, four times over
    the cabinet    Deliveries/summarise-the-vendor-notes-…-seven.md,
                   headed "*Delivered by Local Brain · 2026-08-16*", the
                   stalling sentence four times under it
    the feed       finished "Summarise the vendor notes — probe one t" ✓
                   filed to Deliveries 🗄
    the XP ledger  {"kind": "task", "outcome": "done"}

Nothing any of them read was wrong. `hasSubstance` asks whether anything
is THERE, and four ordinary sentences are there — no markers, no headings,
nothing for the cleaner to take. The question it cannot ask is whether the
run REACHED anything, because a run ending early is not a property of its
text. The office knew: agentStream had said so in the same second, through
`onHint`, in a sentence that went to the chat bubble and nowhere else.

So the ending is returned as well as spoken. Prose to the boss is not a
fact the caller can act on, and the caller is the one holding the card.

Two things this fix had to avoid making up:

  · "with nothing" is the OTHER shortfall's sentence. A run that stopped
    part-way comes back with real paragraphs. Three surfaces say this
    about one run — the desk line, the feed row, the spoken announcement
    — so they read one function, `shortfallLine`.

  · The chat hint's second half is a promise about history: ask again and
    they will pick it up. True of the conversational callers, which pass
    the last few turns and (post-#126) carry the tool results back with
    them. False of the board, which passes no chat at all on purpose — a
    card run is its brief. The board gets a sentence about the door it
    actually has.

ceoStream's hop budget is deliberately left as it was. It has the same
loop and the same hint, and no record to falsify: no card, no cabinet, no
XP ledger. A return value nothing reads would only look like one that does.

Run: python3 scripts/test_a_run_that_stopped_is_not_a_finished_run.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FLOOR = (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8')
ARTIFACTS = (ROOT / 'app' / 'artifacts.jsx').read_text(encoding='utf-8')
FAILS = []

# The reproduced buffer, whole. Four sentences that pass every content test
# the office has and are not an answer to anything.
STALL = ('Let me check the vendor notes on file before I answer.\n\n' * 4).strip()


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose. This file's comments quote the sentences
    under test — including the one that must NOT appear on the board."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching; the opener is the first `{` at paren depth 0."""
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print('a run that stopped is not a finished run')
    runtime = strip_comments(RUNTIME)
    stream = brace_lift(runtime, 'async function agentStream(')
    # Structural anchor, not a comment: the tail is everything after the
    # last message pushed into the conversation, which is the last statement
    # of the hop loop. An anchor on the comment above the fix would move
    # every time the comment is reworded.
    tail = stream[stream.rindex('messages.push('):]

    # ── 1. the fact leaves the runtime ───────────────────────────────────
    check('a run cut short by the tool budget says so on the way out',
          re.search(r'return \{ ranOutOfHops: true, note: stopNote \};', tail),
          [tail[-400:], '— the hint said it to the boss; nothing said it to '
           'the caller, and the caller is the one holding the card'])
    check('...and it is still said out loud as well',
          'onHint(' in tail,
          '— the boss watching the bubble learns the run stopped; taking '
          'that away to add the return would trade one silence for another')
    # Absent means "not cut short", so every OTHER way out of this function
    # has to stay absent. A future early return that carried a value would
    # be read by the board as an ending it is not.
    # #128 added a second one: a CLI driver that never started. That is
    # exactly the case this guards — a run that did NOT finish on its own —
    # so the rule is not "there is one" but "every value that comes back
    # NAMES the reason". A bare `return {}` or one carrying only output
    # would still be read as an ordinary ending, which is the real hazard.
    code_returns = re.findall(r'return \{([^}]*)\}', stream)
    check('...and every other exit that returns a value says WHY it stopped',
          code_returns and all(
              # As a KEY. Matching the bare word found `streamResult
              # .driverError` on the right-hand side, so `return { note:
              # streamResult.driverError }` — a value the board reads as an
              # ordinary ending — passed the check written to forbid it.
              re.search(r'\b(ranOutOfHops|driverError)\s*:', r)
              for r in code_returns),
          [code_returns, '— the board reads a missing return as "the run '
           'finished on its own", which is safe only while a returned '
           'value always means the opposite'])

    # ── 2. the promise splits on what the caller passed ──────────────────
    hints = re.findall(r"'_\(they did as much as they can[^']*'", tail)
    check('the hop-budget sentence has a version for each caller',
          len(hints) == 2, [hints, '— one sentence cannot be true for both'])
    if len(hints) == 2:
        with_chat, without_chat = hints
        check('the caller that passes history is still told to ask again',
              'ask again' in with_chat.lower(),
              [with_chat, '— #126 made that true; it must stay said'])
        check('...and the caller that passes none is not',
              not re.search(r'ask again|pick it up|carry on|where they left off',
                            without_chat, re.I),
              [without_chat, '— a card re-run starts from the brief, so '
               'ask-again is the empty promise #126 was about'])
        check('...and is told what its own door does instead',
              'brief' in without_chat.lower(),
              [without_chat, "§7: an honest sentence about a limit still "
               'needs a way forward'])
        check('the split is decided by the history itself',
              re.search(r'const stopNote = chat\s*\n?\s*\?', tail),
              [tail[-900:], '— keyed on `chat` because that IS the thing '
               'the promise is about; any other flag can disagree with it'])

    # ── 3. the board reads it ────────────────────────────────────────────
    app = strip_comments(APP)
    run = app[app.index('const ending = await HQ.agentStream('):
              app.index('appendJournal(agent.id, cleanBuf, task.title)')]
    check('the task run keeps what agentStream handed back',
          re.search(r'const ending = await HQ\.agentStream\(', app),
          '— it was awaited and dropped, which is why the one fact that '
          'could have stopped the false DONE never arrived')
    # This is what makes the board's sentence the right one. If the board
    # ever starts passing chat, the hint flips by itself — and this check
    # is here so the change is a decision rather than a surprise.
    check('...and still hands the coworker no history',
          not re.search(r'chat:', run),
          [run[:200], '— a card run is its brief; that is the premise the '
           "board's version of the hint rests on"])
    check('the ending is read once, where the outcome is decided',
          len(re.findall(r'ranOutOfHops', run)) == 1,
          '— a second reading is a second answer waiting to disagree')

    # ── 3b. the three surfaces say it in one voice ───────────────────────
    # Caught by fire-testing this suite: reverting the desk line alone to
    # its hardcoded sentence survived every check here and every check in
    # the suite that owns `produced`, because that one pins the shape of
    # the line up to the colon and this one only tested shortfallLine on
    # its own. A shared function nobody is required to call is a suggestion.
    check('the desk reads the shared sentence',
          re.search(r'recent: produced \? cleanBuf\.slice\(0, 140\) : '
                    r'shortfallLine\(shortfall\),', run),
          '— the desk badge and the desk line are read together; "came '
          'back with nothing" under a stuck badge is the whole false claim')
    check('...and so does the announcement',
          re.search(r'shortfallLine\(shortfall, task\.title\)', run),
          '— spoken aloud, it is the surface the boss cannot scroll back to')
    check('...and the feed row is told which one it was',
          re.search(r'doneLine\(task\.title, honesty\.length, shortfall\)', run),
          '— doneLine hands its shortfall branch to the same function')
    check('no surface spells the sentence out for itself',
          'came back with nothing' not in run
          and 'part-way' not in run,
          [re.findall(r".*came back with nothing.*|.*part-way.*", run),
           '— three copies of a sentence is how three surfaces start '
           'giving three accounts of one afternoon'])

    # ── 4. the card's reason is the sentence the office already said ─────
    # Written fresh, it came out saying the same thing in different words,
    # and the boss read both in one bubble one under the other — measured
    # 2026-08-16, the office correcting itself twice about one run. The
    # runtime hands back the sentence it emitted; the card carries that
    # one, and flush.note drops the copy the bubble already holds.
    check('a parked card says why it is parked',
          re.search(r"if \(shortfall === 'ranout' && ending\.note\) \{\s*"
                    r'honesty = honesty\.concat\(\[ending\.note\]\);', app),
          '— #51: a card in `doing` with no reason is worse than the false '
          'DONE it replaces, because at least DONE said something')
    check('...in the office\'s own words rather than a second set',
          re.search(r'return \{ ranOutOfHops: true, note: stopNote \};', tail)
          and re.search(r'if \(onHint\) onHint\(stopNote\);', tail),
          [tail[-300:], '— #64: two sentences about one fact is the office '
           'correcting itself twice'])
    check('the reason is in hand before the notes are joined',
          app.index("shortfall === 'ranout'") < app.index('const honestyText ='),
          '— honestyText is what reaches blockedReason, the card body and '
          'the feed detail; a note added after it is added to nothing')
    check('...and survives the strip that puts it on the card',
          re.search(r"honesty\.join\(' '\)\.replace\(/_\\\(\|\\\)_/g, ''\)", app),
          '— the note is written in the hint channel\'s `_(…)_`; the card '
          'is prose, and this is the line that takes the markers off')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the gate checks need it')
        print()
        return 1 if FAILS else 0

    # ── 5. the gate itself, as written ───────────────────────────────────
    # The real expression, lifted rather than retyped: a copy here would
    # keep passing after the original changed, which is the whole failure
    # this suite exists to catch.
    # Located by the assignment, not by its first branch: #128 put a new
    # branch in front and this lift raised ValueError, failing the suite on
    # a change that left the lifted expression's behaviour intact.
    start = APP.index("const shortfall = ")
    gate = APP[start:APP.index('const produced = !shortfall;', start)
               + len('const produced = !shortfall;')]
    js = (brace_lift(ARTIFACTS, 'function hasSubstance(text) {') + '\n'
          + brace_lift(FLOOR, 'function shortfallLine(kind, subject) {') + '\n'
          + 'function decide(ending, cleanBuf) {\n' + gate
          + '\n  return { shortfall, produced };\n}\n'
          + 'const STALL = ' + json.dumps(STALL) + ';\n'
          + 'const R = {\n'
          '  reproduced: decide({ ranOutOfHops: true }, STALL),\n'
          '  answered: decide(undefined, "Freight is the largest line item."),\n'
          '  empty: decide(undefined, "   \\n  "),\n'
          '  leadIn: decide(undefined, "Here is what I did:"),\n'
          '  endingWithoutFlag: decide({}, "Freight is the largest line item."),\n'
          '  ranOutSilent: decide({ ranOutOfHops: true }, ""),\n'
          '  deskRanOut: shortfallLine("ranout"),\n'
          '  deskEmpty: shortfallLine("empty"),\n'
          '  spokenRanOut: shortfallLine("ranout", "Summarise the vendor notes"),\n'
          '};\n'
          'console.log(JSON.stringify(R));')
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if p.returncode != 0:
        check('the gate harness runs', False, p.stderr.strip()[:400])
    else:
        R = json.loads(p.stdout)
        check('the reproduced run is not a delivery',
              R['reproduced'] == {'shortfall': 'ranout', 'produced': False},
              [R['reproduced'], '— this is the card that sat green in DONE '
               'with the stalling sentence filed under a "Delivered by" '
               'byline'])
        check('...and a run that answered still is',
              R['answered'] == {'shortfall': '', 'produced': True},
              [R['answered'], '— the common path carries every card the '
               'office gets right; it must not move'])
        check('an empty run is still empty, not stopped',
              R['empty'] == {'shortfall': 'empty', 'produced': False}
              and R['leadIn'] == {'shortfall': 'empty', 'produced': False},
              [R['empty'], R['leadIn'], '— #51 and #80 keep their own word'])
        check('an ending with no such fact on it is not a shortfall',
              R['endingWithoutFlag'] == {'shortfall': '', 'produced': True},
              [R['endingWithoutFlag'], '— only the fact itself parks a card'])
        # Both are true of a run that spent four hops on tool calls and
        # wrote no prose at all. "Came back with nothing" is the one that
        # reads as though the coworker sat still; they made four trips.
        check('a run that stopped having said nothing is still a stop',
              R['ranOutSilent']['shortfall'] == 'ranout',
              [R['ranOutSilent'], '— the more specific fact is the more '
               'useful one, and both are true'])

        check('the desk does not say nothing came back',
              R['deskRanOut'] and 'nothing' not in R['deskRanOut']
              and 'part-way' in R['deskRanOut'],
              [R['deskRanOut'], '— four paragraphs came back'])
        check('...and the empty run keeps the words it had',
              R['deskEmpty'] == 'came back with nothing', R['deskEmpty'])
        check('the announcement names the job it stopped part-way through',
              R['spokenRanOut'] == 'stopped part-way through '
                                   '"Summarise the vendor notes"',
              R['spokenRanOut'])

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

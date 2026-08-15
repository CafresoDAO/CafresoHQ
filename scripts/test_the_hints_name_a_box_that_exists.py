#!/usr/bin/env python3
"""The hint channel told the boss to turn dials that are not on the wall.

`onHint` is the out-of-band channel the office uses when a run produced no
answer. It is boss-facing, so §6 binds it, and it was breaking §6 on eight
strings — three of them naming terms the table lists outright:

    tool results came back but Nova's model didn't write a final answer.
    Last attempt: "…". Try a stronger model — sonnet/opus or
    claudecode:sonnet — for the synthesis step, or lower temperature.

    model produced only commentary — try a different model or raise
    max_tokens

    per-turn tool budget exhausted (12 hops); ask again to continue

`temperature` is in the table as *hidden*. `model (as a selector)` is in
the table as *coworker*. There is no temperature control in this product
and no max_tokens field, so the advice is not merely jargon — it points at
dials that do not exist. And `claudecode:sonnet` is a raw routing id, the
exact thing `brainName()` was written to keep off the coworker card.

Underneath the jargon sat a §5 problem too. Two hints named the tool the
coworker reached for by its runtime name:

    model attempted WEB_SEARCH, VAULT_NEW but those aren't wired up —
    check Settings → Roster

Settings → Roster has no box called WEB_SEARCH. It has one called **Web
Search**. Sending the boss to a checkbox under a name that is not printed
on it is the same wrong door as pointing them at a page that doesn't hire.

The fix reads the label off `TOOLS_CATALOG` — the list the checkboxes are
rendered from — so the sentence and the box cannot drift apart. Only the
tool-name → catalog-id grouping is new, and it mirrors the grants in
`toolsForAgent`, which is the one place a ticked box becomes a real tool.

Run: python3 scripts/test_the_hints_name_a_box_that_exists.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []

# Same list as the honesty-notes test, plus the terms specific to this
# channel. Kept duplicated rather than shared: these are two different
# surfaces with two different failure histories, and a shared list is one
# more thing that has to be edited in lockstep to stay honest.
JARGON = [
    'model', 'models', 'temperature', 'max_tokens', 'token', 'tokens',
    'prompt', 'hop', 'hops', 'budget', 'raw', 'buffer', 'api', 'json',
    'wired up', 'rate-limited', 'stderr', 'exception', 'null', 'undefined',
    'parse', 'parsed', 'marker', 'closing tag', 'commentary', 'synthesis',
]
# Runtime tool names must never appear in a hint. Sampled from the
# registry rather than listed by hand where possible.
TOOL_NAME_RE = re.compile(r'\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def jargon_in(text):
    low = str(text).lower()
    return [w for w in JARGON if re.search(r'\b' + re.escape(w) + r'\b', low)]


def main():
    print('a hint names a box the boss can actually go and tick')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = RUNTIME.read_text(encoding='utf-8')

    # ── 1. the label comes from the catalog, run for real ───────────────
    js = re.search(r'^const TOOLS_CATALOG = \[[\s\S]*?^\];$', src, re.M).group(0) + '\n'
    js += re.search(r'^const TOOL_CLAIM_GROUPS = \[[\s\S]*?^\];$', src, re.M).group(0) + '\n'
    js += brace_lift(src, 'function toolClaimLabel(') + '\n'
    js += brace_lift(src, 'function claimLabels(') + '\n'
    js += r'''
const R = { one: {}, lists: {} };
for (const n of ['WEB_SEARCH','SEARCH','BROWSER_FETCH','BROWSER_SCREENSHOT',
                 'VAULT_NEW','VAULT_APPEND','VAULT_SEARCH','EXPORT_PDF',
                 'GENERATE_IMAGE','GENERATE_VIDEO','BASH','FILE_WRITE',
                 'DIR_LIST','MEMORY_WRITE','ACK','DM_TO','']) {
  R.one[n || '(empty)'] = toolClaimLabel(n);
}
R.lists.one   = claimLabels(['VAULT_NEW']);
R.lists.two   = claimLabels(['WEB_SEARCH', 'VAULT_NEW']);
R.lists.three = claimLabels(['WEB_SEARCH', 'VAULT_NEW', 'GENERATE_IMAGE']);
R.lists.dupes = claimLabels(['VAULT_NEW', 'VAULT_APPEND', 'EXPORT_PDF']);
R.lists.none  = claimLabels(['MEMORY_WRITE', 'ACK']);
R.lists.mixed = claimLabels(['MEMORY_WRITE', 'WEB_SEARCH']);
R.lists.empty = claimLabels([]);
R.catalog = TOOLS_CATALOG.map(t => t.label);
console.log(JSON.stringify(R));
'''
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from hq-runtime')
    R = json.loads(proc.stdout.strip().split('\n')[-1])
    one, lists, catalog = R['one'], R['lists'], R['catalog']

    check('a search tool names the Web Search box',
          one['WEB_SEARCH'] == 'Web Search' and one['SEARCH'] == 'Web Search',
          repr([one['WEB_SEARCH'], one['SEARCH']]))
    check('...and so do the browser tools, which ride the same box',
          one['BROWSER_FETCH'] == 'Web Search',
          repr(one['BROWSER_FETCH']) + ' — toolsForAgent grants fetch on '
          "claimed.has('web'), so that is the box to send the boss to")
    check('every cabinet tool names the Vault Notes box',
          all(one[n] == 'Vault Notes' for n in
              ('VAULT_NEW', 'VAULT_APPEND', 'VAULT_SEARCH', 'EXPORT_PDF')),
          repr({n: one[n] for n in ('VAULT_NEW', 'VAULT_APPEND',
                                    'VAULT_SEARCH', 'EXPORT_PDF')})
          + ' — one checkbox grants all seven, so all seven name it')
    check('media tools name the Image Gen box',
          one['GENERATE_IMAGE'] == 'Image Gen'
          and one['GENERATE_VIDEO'] == 'Image Gen',
          repr([one['GENERATE_IMAGE'], one['GENERATE_VIDEO']]))
    check('the shell tool names Code Exec, not File Access',
          one['BASH'] == 'Code Exec', repr(one['BASH']) + ' — two different '
          'boxes, and sending the boss to the wrong one costs them the same '
          'trip as naming no box at all')
    check('...and the file tools name File Access',
          one['FILE_WRITE'] == 'File Access' and one['DIR_LIST'] == 'File Access',
          repr([one['FILE_WRITE'], one['DIR_LIST']]))

    check('every label returned is really on a checkbox',
          all(v in catalog for v in one.values() if v),
          repr(sorted({v for v in one.values() if v} - set(catalog)))
          + ' — the whole point is that the sentence and the box cannot '
            'drift apart, so nothing may be returned that the catalog '
            'does not contain')

    # ── 2. a tool with no box says nothing rather than something wrong ──
    check('a tool every coworker already has names no box',
          one['MEMORY_WRITE'] == '' and one['ACK'] == '' and one['DM_TO'] == '',
          repr({k: one[k] for k in ('MEMORY_WRITE', 'ACK', 'DM_TO')})
          + ' — a coworker reaching for its own memory is not a capability '
            'question, and naming a box would send the boss to tick '
            'something that changes nothing')
    check('...and an empty name too', one['(empty)'] == '', repr(one['(empty)']))
    check('a list of only unboxed tools comes back empty',
          lists['none'] == '' and lists['empty'] == '',
          repr([lists['none'], lists['empty']]) + ' — the caller has a '
          'vaguer true sentence for this; a half-empty list would be worse '
          'than either')
    check('...and a mixed list keeps only what has a box',
          lists['mixed'] == 'Web Search', repr(lists['mixed']))

    # ── 3. it reads as a sentence, not as a dump ────────────────────────
    check('one box reads as one name', lists['one'] == 'Vault Notes',
          repr(lists['one']))
    check('two boxes get an "and"', lists['two'] == 'Web Search and Vault Notes',
          repr(lists['two']))
    check('three get commas and a final "and"',
          lists['three'] == 'Web Search, Vault Notes and Image Gen',
          repr(lists['three']))
    check('three tools behind one box are named once',
          lists['dupes'] == 'Vault Notes', repr(lists['dupes'])
          + ' — a coworker that opened, appended and exported has still '
            'only missed one checkbox, and saying it three times reads as '
            'three separate things to go and fix')

    # ── 4. no hint speaks machine ───────────────────────────────────────
    # Every parenthetical office note in the file, template and all. A
    # template is the right unit here: the jargon that was here lived in
    # the literal text, not in the interpolations.
    notes = re.findall(r"[`'\"]_\((.*?)\)_[`'\"]", src, re.S)
    check('the sweep found the hint strings at all', len(notes) >= 10,
          f'{len(notes)} found — if this drops to zero the section below '
          'passes by measuring nothing')
    dirty = {}
    for n in notes:
        found = jargon_in(n)
        if found:
            dirty[n[:60]] = found
    check('no office note uses a word from the §6 table', not dirty,
          json.dumps(dirty, indent=1))

    named = {}
    for n in notes:
        copy = re.sub(r'\$\{[^}]*\}', '', n)
        hits = TOOL_NAME_RE.findall(copy)
        if hits:
            named[n[:60]] = hits
    check('...and none of them spells a runtime tool name out', not named,
          json.dumps(named, indent=1))

    # The check above scans the LITERAL text, and the defect it is named
    # for did not live there — `${orphans.map(o => o.tool).join(', ')}`
    # puts the same raw names on the screen through an interpolation the
    # scan strips before looking. Found by reverting the fix and watching
    # this pass. So the interpolations get their own rule, and it is a
    # shape rule rather than a word rule: a hint may interpolate the
    # LABELS, never the names they were derived from.
    piped = {}
    for n in notes:
        for expr in re.findall(r'\$\{([^}]*)\}', n):
            if re.search(r'\.tool\b|\borphans\b|\bmissing\b|\bcall\.name\b', expr):
                piped.setdefault(n[:60], []).append(expr.strip())
    check('...nor pipes one in through an interpolation', not piped,
          json.dumps(piped, indent=1) + ' — every one of these has to go '
          'through claimLabels first, which is the only thing that knows '
          'which of them the boss has a checkbox for')

    # ── 5. and the dial itself, since the hint pointed at it ────────────
    # This check exists because writing the one above got it wrong. The
    # first draft asserted no temperature control existed at all; there is
    # one, in Settings → Roster, and it was labelled Temperature — so the
    # commit that called the word jargon would have shipped alongside a
    # screen printing it. The table's own prescription is "creativity", and
    # the coworker-card audit already settled "Brain" for the selector
    # beside it.
    settings = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    knobs = re.search(r'<div className="row-knob">[\s\S]{0,900}?pxslider', settings)
    check('the Roster found its knobs where the check expects them',
          knobs is not None,
          'modals/settings.jsx: the per-agent brain/creativity block moved '
          'or was rewritten, so the two label checks below are measuring '
          'nothing and need re-anchoring')
    block = knobs.group(0) if knobs else ''
    check('the brain selector is not labelled Model',
          '>Brain<' in block and '>Model<' not in block,
          repr(block[:200]) + ' — §6: model as a selector reads "coworker", '
          'and the coworker card settled on Brain for this same control')
    check('...and the creativity dial is not labelled Temperature',
          '>Creativity<' in block and '>Temperature<' not in block,
          repr(block[-200:]) + ' — §6 lists temperature as hidden, or a '
          '"creativity" dial if it ever surfaced; it surfaced')
    check('the settings search still finds it under both words',
          re.search(r"kw:'[^']*temperature[^']*creativity", settings) is not None,
          'renaming a label must not make the thing unfindable for someone '
          'who knows it by the old word — the keyword row keeps both')

    # ── 6. and it has to actually reach the boss ────────────────────────
    # Found by driving the fixed sentences live rather than trusting the
    # unit above. A fresh office, one hire, a brain answering with two
    # harmony tool calls and no prose: agentStream reached the branch,
    # emitted the note, and the stored message came out as the raw buffer
    # with nothing appended. The note was painted by flushNow and wiped by
    # the caller's own final setChat one line later, which recomputes the
    # text from `buf` — and `buf` has never contained the note.
    #
    # Run it the way app.jsx runs it, in that order, so the test would have
    # caught the original.
    js2 = brace_lift(src, 'function cleanHarmony(') + '\n'
    js2 += brace_lift(src, 'function throttleTokens(') + '\n'
    js2 += r'''
const NOTE = '_(they reached for Code Exec, which they don’t have.)_';
function drive(streamed, finalText, note) {
  let msgs = [{ id: 'm1', text: '' }];
  const setChat = (fn) => { msgs = fn(msgs); };
  const flush = throttleTokens(setChat, 'm1');
  if (streamed) flush(streamed);
  if (note) flush.note(note);          // agentStream emits, mid-run
  flush.flushNow();                    // caller step 1
  flush.cancel();                      // caller step 2
  setChat(prev => prev.map(m => m.id === 'm1'
    ? { ...m, text: flush.withNotes(finalText) } : m));   // caller step 3
  return msgs[0].text;
}
const HARMONY = '<|channel|>commentary to=functions.bash<|message|>{"a":1}<|call|>';
console.log(JSON.stringify({
  emptyRun: drive(HARMONY, '', NOTE),
  spokeAndNoted: drive('The answer is four.', 'The answer is four.', NOTE),
  noNote: drive('The answer is four.', 'The answer is four.', null),
  noNoteEmpty: drive('', '', null),
}));
'''
    proc2 = subprocess.run(['node', '--input-type=module', '-e', js2],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc2.returncode != 0:
        print(proc2.stderr, file=sys.stderr)
        raise SystemExit('node harness failed driving throttleTokens')
    D = json.loads(proc2.stdout.strip().split('\n')[-1])

    check('a run that said nothing still shows the boss the note',
          'reached for Code Exec' in D['emptyRun'],
          repr(D['emptyRun']) + ' — this is the measured case: no answer, '
          'and the office silent about it too')
    check('...with nothing else in the bubble but the note',
          D['emptyRun'].strip() == D['emptyRun'] and D['emptyRun'].count('\n') == 0,
          repr(D['emptyRun']) + ' — no leading blank lines from the join')
    check('a run that answered keeps both halves',
          D['spokeAndNoted'].startswith('The answer is four.')
          and 'reached for Code Exec' in D['spokeAndNoted'],
          repr(D['spokeAndNoted']))
    check('...separated, not run together',
          '\n\n' in D['spokeAndNoted'], repr(D['spokeAndNoted']))
    check('a run with no note is left exactly as the caller wrote it',
          D['noNote'] == 'The answer is four.' and D['noNoteEmpty'] == '',
          repr([D['noNote'], D['noNoteEmpty']]) + ' — withNotes must be '
          'invisible when there is nothing to carry, or every silent bubble '
          'grows whitespace')

    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = re.findall(r'text:\s*(?:cleanBuf|cleaned)\s*\}', app)
    check('no dispatch path writes the finished reply on its own',
          not bare, f'{len(bare)} final write(s) still recompute the bubble '
          'from the buffer alone, which is exactly how the note got erased')
    check('...and all three of them carry the note through',
          len(re.findall(r'flush\.withNotes\(', app)) >= 3,
          '@mention, delegate and a task dropped on a desk each end with '
          'their own setChat; every one of them has to go through withNotes')
    check('the note channel is still wired on those paths',
          len(re.findall(r'onHint:\s*flush\.note', app)) >= 3,
          'withNotes carries nothing if nobody hands the throttle a note')

    print()
    if FAILS:
        print(f'the right box: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('the right box: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

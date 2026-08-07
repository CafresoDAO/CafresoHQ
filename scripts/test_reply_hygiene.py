#!/usr/bin/env python3
"""visibleReply (hq-runtime.jsx) — protocol markers must never reach the boss.

Agents speak to the host in brackets: [ACK: in_progress: …] tells the inbox
where a run is. Those are wire protocol, and §7's no-raw-dumps rule covers
them exactly as it covers stack traces — the boss never asked to read them.

Two real regressions this pins, both found by driving a SUCCESSFUL run
against a small local model (which emits bare ACKs far more readily than a
large one, so failure-only testing never surfaced either):

  - the task-dispatch path stripped nothing, so the marker became the task's
    stored `result` — the deliverable the boss opens
  - the chat path stripped, then fell back with `cleaned || raw`, restoring
    the bracket precisely when the whole reply was one

Extracted with the same strip-imports/run-under-node harness as the others.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'hq-runtime.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    """Pull just the three functions under test — hq-runtime is a large
    browser module, so slicing beats trying to evaluate the whole file."""
    text = SRC.read_text(encoding='utf-8')
    wanted = []
    # The orphan-tag regex is a module-level const, not a function — pull it
    # first so stripOrphanTags can see it.
    pconst = re.search(r'^const PLACEHOLDER_ARG\s*=.*?;$', text, re.M)
    if not pconst:
        raise SystemExit('could not find PLACEHOLDER_ARG')
    wanted.append(pconst.group(0))
    mconst = re.search(r'^const ORPHAN_TAG_RE\s*=\s*$\n\s*/.*?/gim;', text, re.M | re.S)
    if not mconst:
        mconst = re.search(r'^const ORPHAN_TAG_RE\s*=.*?;', text, re.M | re.S)
    if not mconst:
        raise SystemExit('could not find ORPHAN_TAG_RE')
    wanted.append(mconst.group(0))
    for fn in ('extractAcks', 'stripAcks', 'stripOrphanTags', 'stripBlocks', 'visibleReply', 'vaultPaths', 'upToToolCall', 'placeholderRefusal', 'unsentHandoff', 'unsentElevation', 'unsentBlocks'):
        m = re.search(r'^function ' + fn + r'\(.*?^\}', text, re.M | re.S)
        if not m:
            raise SystemExit(f'could not find {fn} in {SRC}')
        wanted.append(m.group(0))
    src = '\n'.join(wanted)
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


CASES = r'''
const R = {};
// The exact string a live local-model run produced.
R.bareAck      = visibleReply('[ACK: in_progress: gathering context for regression check]');
R.bareAckNoNote= visibleReply('[ACK: in_progress]');
R.mixed        = visibleReply('[ACK: in_progress: thinking]\nRed, green, blue.');
R.trailing     = visibleReply('Red, green, blue. [ACK: completed: done]');

/* Verbatim off the floor, 2026-08-07. The boss asked for one colour; the
   reply carried a whole [MEMORY_WRITE] block whose delimiters were stripped
   while its BODY stayed as prose, and an [ACK: completed: …] whose nested
   markers defeated a `[^\]]*` detail match and stranded "]]" mid-line. Both
   were live in shipped code, both invisible to every check above, because
   every check above used a single-line marker. */
R.realBlockLeak = visibleReply(
  "I'll use this note as a reference, but I need to create it first.\n" +
  '[MEMORY_WRITE: projects/local_file_access.md]\n<content>\n' +
  'Local file access is required for reading the file.\n[/MEMORY_WRITE]\n\n' +
  'The boss asked me to name one color, so I\'ll provide that directly.\n\n' +
  '[ACK: completed: • [BROWSER_FETCH: https://en.wikipedia.org/wiki/Primary_color]' +
  ' • [MEMORY_READ: projects/local_file_access.md]]The article defines them.');
/* An UNCLOSED block never parsed, so its tool never ran and unsentBlocks
   must still be able to see the opener. Stripping to end-of-text would also
   swallow any real answer that followed. */
R.unclosedKept = stripBlocks('Sure.\n[HIRE_AGENT: designer]\nname: Vee');
R.noMarkers    = visibleReply('Red, green, blue.');
R.empty        = visibleReply('');
R.nullIn       = visibleReply(null);
// Never leaks a bracket, whatever the shape.
R.noBrackets = ['[ACK: in_progress: x]', '[ACK: completed]', '[ACK: blocked: y]',
                '[ACK: in_progress: a]\ntext', 'text [ACK: completed: b]']
  .map(visibleReply).every(x => !/\[\s*ACK/i.test(x));
// An unknown ACK state is not a recognised marker — extractAcks ignores it,
// so it must survive as ordinary text rather than vanishing.
R.unknownState = visibleReply('[ACK: banana: hm]');
// Observed live: an 8B local model opened a DM block and never closed it,
// so extractDM never matched and the opener reached the boss as prose.
R.orphanDm   = visibleReply('[DM_TO: Claude]\nCan you help?\n\n[ACK: in_progress: awaiting_reply]');
R.orphanOnly = visibleReply('[DM_TO: Claude]');
// Executed tools: the office already appends its own visit line, so the
// coworker's raw invocation is scaffolding in the KEPT record.
R.orphanFetch = visibleReply('Looking it up.\n[BROWSER_FETCH: https://a.com/x]\n\n\u{1F310} Read a.com/x\nParis.');
R.orphanMem   = visibleReply('[MEMORY_READ: facts/france.md]\n[/MEMORY_READ]\n\nResult: Paris.');
R.orphanBash  = visibleReply('[BASH: ls -la]\ndone');
// …but a marker INSIDE a sentence is content; removing it breaks the line.
R.orphanInline = visibleReply('I will use [MEMORY_READ: decisions/x.md] to check.');
// A lookalike that is not one of ours stays put.
R.orphanNotOurs = visibleReply('[TODO: buy milk]\nreal text');
// vaultPaths — /vault/list returns records, not strings. Reading them as
// strings killed [MEMORY_LIST] and silently emptied every agent's memory
// summary; both failures were invisible for the same reason.
R.vpRecords = vaultPaths([{path:'Agents/Llama/a.md'},{path:'Deliveries/b.md'}]);
R.vpStrings = vaultPaths(['Agents/Llama/a.md']);
R.vpMixed   = vaultPaths([{path:'a.md'}, 'b.md', {title:'no path'}, null, '']);
R.vpNull    = vaultPaths(null);
R.vpStartsWith = vaultPaths([{path:'Agents/Llama/a.md'}]).filter(x => x.startsWith('Agents/Llama/')).length;
// upToToolCall — a coworker must never be handed back the result it guessed.
// The real case: [MEMORY_LIST] followed by three invented file names.
const FAB = "I'll check what's saved: [MEMORY_LIST]\n\nHere are the notes:\n* decisions/auth.md\n* preferences.md";
R.cutFab      = upToToolCall(FAB, '[MEMORY_LIST]');
R.cutKeepsAsk = /I'll check what's saved/.test(R.cutFab);
R.cutDropsGuess = /decisions\/auth\.md|preferences\.md/.test(R.cutFab);
R.cutKeepsMarker = /\[MEMORY_LIST\]$/.test(R.cutFab);
R.cutNoRaw    = upToToolCall(FAB, null);
R.cutAbsent   = upToToolCall('plain prose', '[NOPE]');
R.cutEmpty    = upToToolCall('', '[X]');
R.cutNullText = upToToolCall(null, '[X]');
// Only the FIRST occurrence bounds it — a marker repeated later must not
// let the guess back in.
R.cutFirstOnly = upToToolCall('a [X] b [X] c', '[X]');
// placeholderRefusal — a template copied out of the tool docs is not a value.
R.phUrl    = placeholderRefusal('BROWSER_FETCH', '<url>');
R.phPath   = placeholderRefusal('MEMORY_READ', '<path>');
R.phSpaced = placeholderRefusal('MEMORY_READ', '  <your-file.md>  ');
R.phReal   = placeholderRefusal('BROWSER_FETCH', 'https://example.com');
R.phPathReal = placeholderRefusal('MEMORY_READ', 'decisions/art.md');
R.phPartial  = placeholderRefusal('SEARCH', 'compare <a> and <b> tags');
R.phInner    = placeholderRefusal('SEARCH', 'a<b');
R.phEmpty    = placeholderRefusal('MEMORY_LIST', '');
R.phNull     = placeholderRefusal('MEMORY_LIST', null);
R.phNested   = placeholderRefusal('SEARCH', '<<url>>');
R.phSaysNotRun = /Nothing was looked up/.test(R.phUrl || '');
// unsentHandoff — the exact reply from the first two-coworker run.
const INLINE_DM = '• Blue is a primary color. [DM_TO: Mika] Can you provide your perspective?';
R.uhInline    = unsentHandoff(INLINE_DM, 0);
R.uhNamesWho  = /Mika/.test(R.uhInline || '');
R.uhDelivered = unsentHandoff(INLINE_DM, 1);      // something went out → silent
R.uhWellFormed = unsentHandoff('[DM_TO: Mika]\nplease help\n[/DM_TO]', 1);
R.uhNoMarker  = unsentHandoff('Blue is a primary color.', 0);

// unsentElevation — same shape, for the request where silence is worst.
// Driven live: a coworker wrote the opening tag alone, the parser correctly
// ignored it, and the boss read "I'm requesting access" with an empty tray.
const BARE_ASK = '[REQUEST_ELEVATION: need to read a local file]\n\nI will use it carefully.';
const FULL_ASK = '[REQUEST_ELEVATION: need to read a local file]\nI need FILE_READ on ./notes\n[/REQUEST_ELEVATION]';
R.ueBare      = unsentElevation(BARE_ASK, false);
R.ueRaised    = unsentElevation(BARE_ASK, true);       // one really did land → silent
R.ueWellFormed= unsentElevation(FULL_ASK, true);
R.ueNoMarker  = unsentElevation('Here are three colours.', false);
R.ueSaysRoute = /approvals|Settings/i.test(unsentElevation(BARE_ASK, false) || '');

// unsentBlocks — the rest of the class, each leaving a person waiting.
R.ubHire     = unsentBlocks('[HIRE_AGENT: Quill]\nwe need an editor');
R.ubHireOk   = unsentBlocks('[HIRE_AGENT: Quill]\nwe need an editor\n[/HIRE_AGENT]');
R.ubSpawn    = unsentBlocks('[SPAWN_SUBAGENT: reviewer]\ncheck this diff');
R.ubHandoff  = unsentBlocks('[HANDOFF_TO: Mika]\nover to you');
R.ubTwo      = unsentBlocks('[HIRE_AGENT: A]\nx\n[SPAWN_SUBAGENT: b]\ny');
R.ubWrite    = unsentBlocks('[MEMORY_WRITE: notes/a.md]\nhello');   // write class → not ours
R.ubNone     = unsentBlocks('Just an ordinary reply.');
R.ubMixed    = unsentBlocks('[HIRE_AGENT: A]\nx\n[/HIRE_AGENT]\n[SPAWN_SUBAGENT: b]\ny');
R.uhOwnLine   = unsentHandoff('[DM_TO: Kenji]', 0);   // stripped from view, still unsent
R.uhEmpty     = unsentHandoff('', 0);
R.uhNull      = unsentHandoff(null, 0);
R.uhLongName  = (unsentHandoff('[DM_TO: ' + 'x'.repeat(200) + ']', 0) || '').length < 260;
// The protocol must not ask for anything it then deletes. Pin the property
// rather than the wording: a result placed inside an ACK is unreachable.
R.ackEatsResult = visibleReply('Here is what I found.\n\n[ACK: completed: • red • blue • yellow]');
R.ackOnlyFallsBack = visibleReply('[ACK: blocked: need vault access]');
R.ackKeepsProse = visibleReply('The capital is Tokyo.\n[ACK: awaiting_reply: checking with Kenji]');
R.phNamesTool  = /BROWSER_FETCH/.test(R.phUrl || '');
// A tag mid-sentence is the agent TALKING about the protocol, not using it.
R.inlineKept = visibleReply('Use [DM_TO: name] to reach someone.');
console.log(JSON.stringify(R));
'''


def main():
    print('reply hygiene — no protocol markers on user surfaces')
    if not shutil.which('node'):
        print('  SKIP  node not available')
        return 0
    out = run_js(CASES)

    check('a bare ACK shows its note, not the bracket',
          out['bareAck'] == 'gathering context for regression check', repr(out['bareAck']))
    check('a bare ACK with no note says something plain',
          out['bareAckNoNote'] == 'still working on it', repr(out['bareAckNoNote']))
    check('a marker beside real text keeps only the text',
          out['mixed'] == 'Red, green, blue.', repr(out['mixed']))
    check('a trailing marker is removed cleanly',
          out['trailing'] == 'Red, green, blue.', repr(out['trailing']))
    check('text without markers is untouched',
          out['noMarkers'] == 'Red, green, blue.')
    check('empty stays empty', out['empty'] == '')
    check('null tolerated', out['nullIn'] == '')
    check('NO shape ever leaks a bracket', out['noBrackets'])
    # The two failures that were live on the floor on 2026-08-07.
    check('a MEMORY_WRITE block leaves no body and no <content> behind',
          '<content>' not in out['realBlockLeak']
          and 'Local file access is required' not in out['realBlockLeak'],
          repr(out['realBlockLeak']))
    check('an ACK with nested markers strands nothing mid-line',
          '[' not in out['realBlockLeak'] and ']' not in out['realBlockLeak'],
          repr(out['realBlockLeak']))
    check('…and the prose either side of both survives intact',
          'name one color' in out['realBlockLeak']
          and out['realBlockLeak'].endswith('The article defines them.'),
          repr(out['realBlockLeak']))
    check('an UNCLOSED block keeps its opener so unsentBlocks can report it',
          'HIRE_AGENT' in out['unclosedKept'], repr(out['unclosedKept']))
    check('an unrecognised ACK state stays as ordinary text',
          '[ACK: banana: hm]' in out['unknownState'], repr(out['unknownState']))
    check('an unclosed DM_TO opener is scrubbed, its text kept',
          out['orphanDm'] == 'Can you help?', repr(out['orphanDm']))
    check('a reply that is only an orphan tag falls back, not blank',
          out['orphanOnly'] == '[DM_TO: Claude]', repr(out['orphanOnly']))
    check('an executed BROWSER_FETCH line is dropped from the record',
          out['orphanFetch'] == 'Looking it up.\n\n\U0001F310 Read a.com/x\nParis.',
          repr(out['orphanFetch']))
    check('MEMORY_READ open+close lines both go',
          out['orphanMem'] == 'Result: Paris.', repr(out['orphanMem']))
    check('a BASH invocation line goes', out['orphanBash'] == 'done', repr(out['orphanBash']))
    check('a marker inside a sentence is left alone',
          out['orphanInline'] == 'I will use [MEMORY_READ: decisions/x.md] to check.',
          repr(out['orphanInline']))
    check('vault records become path strings',
          out['vpRecords'] == ['Agents/Llama/a.md', 'Deliveries/b.md'], str(out['vpRecords']))
    check('bare strings still work', out['vpStrings'] == ['Agents/Llama/a.md'])
    check('pathless / null / empty entries are dropped',
          out['vpMixed'] == ['a.md', 'b.md'], str(out['vpMixed']))
    check('a null list is safe', out['vpNull'] == [])
    check('the result supports startsWith — the call that was crashing',
          out['vpStartsWith'] == 1)
    check('an inline DM_TO that never dispatched is reported',
          bool(out['uhInline']) and out['uhNamesWho'], repr(out['uhInline']))
    check('…and it says plainly that nothing was sent',
          'Nothing was sent' in (out['uhInline'] or ''), repr(out['uhInline']))
    check('a run that DID deliver stays silent',
          out['uhDelivered'] is None and out['uhWellFormed'] is None)
    check('an ordinary reply is never flagged', out['uhNoMarker'] is None)

    # unsentElevation — §7 on the security request
    check('a bare REQUEST_ELEVATION is called out', bool(out['ueBare']))
    check('…and it names a route out', out['ueSaysRoute'] is True)
    check('a request that really landed stays silent', out['ueRaised'] is None)
    check('a well-formed block stays silent', out['ueWellFormed'] is None)
    check('no marker at all says nothing', out['ueNoMarker'] is None)

    # unsentBlocks — one guard for the rest of the request class
    check('an unclosed hire request is called out', bool(out['ubHire']))
    check('…and a well-formed one is not', out['ubHireOk'] is None)
    check('an unclosed helper request is called out', bool(out['ubSpawn']))
    check('an unclosed hand-off is called out', bool(out['ubHandoff']))
    check('two broken markers produce two notes',
          out['ubTwo'] is not None and out['ubTwo'].count('_(') == 2, out['ubTwo'])
    check('a WRITE marker is not this guard\'s business — no visit block is '
          'already the honest record', out['ubWrite'] is None)
    check('an ordinary reply is silent', out['ubNone'] is None)
    check('a good marker beside a broken one only flags the broken one',
          out['ubMixed'] is not None and out['ubMixed'].count('_(') == 1, out['ubMixed'])
    check('an own-line marker still counts as unsent', bool(out['uhOwnLine']))
    check('empty and null are safe', out['uhEmpty'] is None and out['uhNull'] is None)
    check('a runaway name cannot blow up the note', out['uhLongName'] is True)
    check('a result placed inside an ACK is NOT shown — the reason the '
          'instruction to put one there had to go',
          out['ackEatsResult'] == 'Here is what I found.', repr(out['ackEatsResult']))
    check('an ACK-only reply still falls back to its note rather than blank',
          'need vault access' in out['ackOnlyFallsBack'], repr(out['ackOnlyFallsBack']))
    check('prose survives alongside a state marker',
          out['ackKeepsProse'] == 'The capital is Tokyo.', repr(out['ackKeepsProse']))
    check('an angle-bracket template is refused', bool(out['phUrl']) and bool(out['phPath']))
    check('surrounding whitespace does not hide one', bool(out['phSpaced']))
    check('a real url runs', out['phReal'] is None)
    check('a real path runs', out['phPathReal'] is None)
    check('brackets INSIDE a real query are left alone',
          out['phPartial'] is None and out['phInner'] is None)
    check('an argument-less tool is not mistaken for a template',
          out['phEmpty'] is None and out['phNull'] is None)
    check('a nested-bracket oddity is not refused (narrow rule)', out['phNested'] is None)
    check('the refusal says plainly that nothing ran', out['phSaysNotRun'] is True)
    check('…and names the tool so the model can retry it', out['phNamesTool'] is True)
    check('the ask survives the cut', out['cutKeepsAsk'] is True, repr(out['cutFab']))
    check('the invented result is cut away', out['cutDropsGuess'] is False, repr(out['cutFab']))
    check('the marker itself is kept, so the model sees what it asked for',
          out['cutKeepsMarker'] is True, repr(out['cutFab']))
    check('no raw match leaves the text untouched — never truncate blind',
          out['cutNoRaw'] == out['cutFab'] or len(out['cutNoRaw']) > len(out['cutFab']))
    check('an absent marker changes nothing', out['cutAbsent'] == 'plain prose')
    check('empty and null inputs are safe', out['cutEmpty'] == '' and out['cutNullText'] == '')
    check('a repeated marker cuts at the FIRST one', out['cutFirstOnly'] == 'a [X]',
          repr(out['cutFirstOnly']))
    check('a bracketed line that is not one of our tools survives',
          out['orphanNotOurs'] == '[TODO: buy milk]\nreal text', repr(out['orphanNotOurs']))
    check('a tag mid-sentence is content, not scaffolding',
          out['inlineKept'] == 'Use [DM_TO: name] to reach someone.', repr(out['inlineKept']))

    # ── Every block-form marker has had a guard DECISION ──────────────────
    #
    # A marker whose regex demands a closing tag can be written without one,
    # in which case it silently never parses. For a REQUEST that leaves a
    # person waiting (a hire, a helper, a hand-off, an access request) the
    # office must say so; for a WRITE it must not, because "no visit block"
    # is already the honest record.
    #
    # This was a comment claiming "13 block-form markers" — which was a
    # miscount for 16, and the kind of number that rots the moment someone
    # adds a marker. As a test it cannot rot: adding a block-form marker
    # fails here until it is placed in one bucket or the other.
    src = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
    names = [(m.start(), m.group(1))
             for m in re.finditer(r"name: '([A-Z_]+)'", src)]
    regexes = [(m.start(), m.group(0)) for m in re.finditer(r're: /[^\n]+', src)]
    block = set()
    for pos, name in names:
        near = [rx for p, rx in regexes if 0 <= p - pos < 900]
        if not near:
            continue
        rx = near[0]
        closing = ('\\/' in rx and name in rx.split('\\/')[1][:40]) \
            or ('/\\s*' + name) in rx
        if closing:
            block.add(name)

    # Guarded by name, in unsentBlocks' own table or a bespoke guard.
    guarded = set(re.findall(r"\['([A-Z_]+)',", src)) | {'DM_TO', 'REQUEST_ELEVATION'}
    # Deliberately silent: the tool simply never ran and no visit block says so.
    write_class = {'VAULT_NEW', 'VAULT_APPEND', 'MEMORY_WRITE', 'MEMORY_APPEND',
                   'FILE_WRITE', 'EXPORT_PPTX', 'EXPORT_DOCX', 'EXPORT_PDF',
                   'GENERATE_IMAGE', 'GENERATE_VIDEO'}
    undecided = block - guarded - write_class
    check('every block-form marker is either guarded or a known write',
          not undecided,
          'undecided: ' + ', '.join(sorted(undecided)) +
          ' — add a guard in unsentBlocks, or list it as write-class with a reason')
    check('the request-class guards all still exist',
          {'DM_TO', 'HANDOFF_TO', 'HIRE_AGENT', 'HIRE_ASSISTANT',
           'REQUEST_ELEVATION', 'SPAWN_SUBAGENT'} <= guarded)

    print()
    if FAILS:
        print(f'reply hygiene: {len(FAILS)} failure(s)')
        return 1
    print('reply hygiene: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

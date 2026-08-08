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
    for fn in ('extractAcks', 'stripAcks', 'stripOrphanTags', 'stripBlocks', 'stripSelfLabel', 'visibleReply', 'extractAllDMs', 'vaultPaths', 'upToToolCall', 'placeholderRefusal', 'unsentHandoff', 'unsentElevation', 'unsentBlocks', 'unsentAsk', 'fabricatedRelay'):
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
// A reply that is ONLY a hand-off: the strip understands it and removes it,
// and the raw fallback used to print the protocol straight back at the boss.
R.pureDM       = visibleReply('[DM_TO: Nano]\nCan you name one color of a ripe banana?\n[/DM_TO]');
R.pureDMTwo    = visibleReply('[DM_TO: Nano]\nq1\n[/DM_TO]\n[DM_TO: Kip]\nq2\n[/DM_TO]');
R.pureDMSame   = visibleReply('[DM_TO: Nano]\nq1\n[/DM_TO]\n[DM_TO: Nano]\nq2\n[/DM_TO]');
// Prose alongside the hand-off still wins -- the boss's words come first.
R.dmWithProse  = visibleReply('On it.\n[DM_TO: Nano]\nq\n[/DM_TO]');
// An UNRECOGNISED marker keeps the old behaviour: show it rather than
// silently drop what someone said.
R.unknownTag   = visibleReply('[MYSTERY_TAG: x]');

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

/* Verbatim off the FIRST-RUN path, 2026-08-07: a fresh office, one hire
   (Llama, local), the "Research brief" starter card. This exact line was
   written into the filed .md in the boss's cabinet — a kept file naming a
   vault path that does not exist. The marker is mid-line, behind a label
   the model invented, which is why the whole-line orphan strip missed it. */
R.inlineVaultLeak = visibleReply(
  '**Vault Path:** [VAULT_NEW: Research/sourdough_starter.md]\n\n' +
  'Sourdough bread needs a starter because wild yeast tolerates acidity.');
R.inlineVaultNote = unsentBlocks(
  '**Vault Path:** [VAULT_NEW: Research/sourdough_starter.md]\n\n' +
  'Sourdough bread needs a starter because wild yeast tolerates acidity.');
/* Verbatim off the floor, 2026-08-07. Three runs asked Llama to save a note;
   all three emitted an unclosed [MEMORY_WRITE:…] — so nothing was written —
   and all three announced success in their own ACK. The office said nothing,
   because write-class markers were excluded from this guard on the argument
   that a missing visit block is record enough. It is not: an absence does not
   contradict a claim. */
/* Off the floor, 2026-08-07. Two local coworkers, two attempts to make
   one hand off to the other. Neither produced a marker, so unsentHandoff
   stayed silent — correctly. The second attempt ACKed `awaiting_reply`
   having sent nothing, which is a claim the office can prove false from
   its own structured data. */
/* Verbatim, 2026-08-07, and the first clean handoff test after the
   delegate bug was fixed. Asked in plain words with no protocol named,
   Nova sent nothing and answered in the office's OWN relay format,
   putting words in Llama's mouth. */
R.fakeRelay      = fabricatedRelay('[Llama \u2192 Nova]:\n\u2022 A ripe lemon is typically yellow.', 0, ['Llama','Nova']);
R.relayDelivered = fabricatedRelay('[Llama \u2192 Nova]: hi', 1, ['Llama','Nova']);
R.relayStranger  = fabricatedRelay('[Bob \u2192 Sue]: hi', 0, ['Llama','Nova']);
R.relayProse     = fabricatedRelay('I asked Llama about lemons.', 0, ['Llama','Nova']);

R.claimedAsk     = unsentAsk(['awaiting_reply'], 0);
R.claimedAskSent = unsentAsk(['awaiting_reply'], 1);
R.noClaimNoNote  = unsentAsk(['completed'], 0);
R.proseOnlyQuiet = unsentAsk([], 0);

R.unsentWrite  = unsentBlocks(
  '[MEMORY_WRITE: notes/citrus.md]\nThe boss likes lemons.\n\n' +
  '[ACK: completed: • saved note on citrus preferences]');
R.closedWriteOk = unsentBlocks('[MEMORY_WRITE: a.md]\nbody\n[/MEMORY_WRITE]');
/* Verbatim, 2026-08-07. The model read the office's own context format out of
   its history and typed it back, which pushed the marker off column zero and
   blinded the line-anchored strip. */
R.echoedLabel  = visibleReply('[Llama · Generalist]: [MEMORY_WRITE: notes/figs.md]\nThe boss likes figs.');
R.refDefKept   = visibleReply('[1]: https://example.com\nSee the link.');
R.midReplyKept = visibleReply('I asked, and\n[Mika · Head of Inbox]: said no.');
/* Verbatim from a filed task delivery, 2026-08-07. A stale line from earlier
   context, then the speaker's OWN label, then the real answer — so the label
   was not at the start of the text and survived. Naming the speaker is what
   separates it from the quotation above. */
R.selfMidText  = visibleReply('The boss likes figs.\n\n[Llama · Generalist]: Grape.', 'Llama');
R.othersKept   = visibleReply('I asked, and\n[Mika · Head of Inbox]: said no.', 'Llama');
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
R.ubWrite    = unsentBlocks('[MEMORY_WRITE: notes/a.md]\nhello');   // write class → NOW ours
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


def check_every_reply_path():
    """Every stream caller is a reply path, and each one has to run its
    final text through visibleReply before a person sees it.

    Counts ceoStream too, and scans ui/chat.jsx, since 2026-08-07. The
    census had enumerated `agentStream` callers only — so the CEO, the
    coworker a boss talks to most, was never in it. Its reply was cleaned
    only when it happened to emit a handoff or a DM, by a local regex that
    knew two marker types out of sixteen. A census is only as wide as the
    entry point it knows to look for.

    This exists because six paths existed and three cleaned. The suite was
    green throughout, because it tests visibleReply — which was correct — and
    nothing tested whether a path CALLS it. Finding the other three meant
    enumerating callers by hand; this does that automatically.

    Deliberately crude: it asks whether visibleReply appears within 150 lines
    after the stream opens, not whether it is wired correctly. A new path that
    forgets entirely is the failure this catches; one that calls it wrongly is
    what the live run is for.
    """
    import re as _re
    paths = []
    for rel in ('app.jsx', 'features.jsx', 'missions.jsx', 'ui/chat.jsx'):
        text = (ROOT / rel).read_text(encoding='utf-8')
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if _re.search(r'\b(?:agentStream|ceoStream)\s*\(', line) and 'function agentStream' not in line and 'function ceoStream' not in line:
                window = '\n'.join(lines[i:i + 150])
                paths.append((rel, i + 1, 'visibleReply' in window))
    return paths


def check_raw_buffer_shown():
    """The census above asks whether `visibleReply` appears within 150 lines
    of a stream opening. That is crude on purpose -- and on 2026-08-07 it was
    crude enough to be WRONG. It stayed green while the dispatch path, the
    office's most-used route, built its final text with `cleanHarmony(buf)`
    alone: some other `visibleReply` in the window satisfied the search, and
    the one that mattered was never called. The rule under-claimed its scope,
    which this repo already warns is as misleading as over-claiming.

    So this checks the ANTI-PATTERN directly rather than the presence of a
    cure somewhere nearby: no reply-path file may hand the raw accumulated
    buffer to `cleanHarmony`, because the recipe is always
    `cleanHarmony(visibleReply(...))`. Narrow, and honest about being narrow
    -- it catches the exact shape that shipped, not the idea.

    hq-runtime.jsx is excluded: `cleanHarmony(buf)` there is the streaming
    internals cleaning their own buffer, not a path showing text to a person.
    """
    import re as _re
    bad = []
    for rel in ('app.jsx', 'features.jsx', 'missions.jsx', 'ui/chat.jsx'):
        f = ROOT / rel
        if not f.exists():
            continue
        text = f.read_text(encoding='utf-8')
        text = _re.sub(r'/\*.*?\*/', '', text, flags=_re.S)
        for i, line in enumerate(text.split('\n')):
            if _re.search(r'cleanHarmony\s*\(\s*buf\s*\)', line):
                bad.append(f'{rel}:{i + 1}')
    return bad


def check_guards_cover_every_path():
    """A guard wired into one path of three protects one path of three.

    Found by census on 2026-08-07: `fabricatedRelay` was added to the
    dispatch path only, and the run that first exposed the fabrication it
    catches was a TASK run -- one of the two paths without it. `unsentAsk`
    is legitimately dispatch-only (it reads parsed ACK states, and only that
    path parses them), so this pins the guards that need nothing but the
    buffer and the roster.

    `unsentHandoff` is the baseline: it has been in every path since before
    any of this. Any sibling that takes the same inputs should appear the
    same number of times. Counts calls, not definitions.
    """
    import re as _re
    text = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    text = _re.sub(r'/\*.*?\*/', '', text, flags=_re.S)
    def count(name):
        return len(_re.findall(r'HQ\.' + name + r'\s*&&\s*HQ\.' + name + r'\s*\(', text)) or \
               len(_re.findall(r'HQ\.' + name + r'\b\s*$', text, _re.M))
    base = count('unsentHandoff')
    out = {}
    for g in ('unsentBlocks', 'fabricatedRelay'):
        out[g] = (count(g), base)
    return out


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
    # Contract CHANGED deliberately, 2026-08-07. It used to require the
    # opener be KEPT so unsentBlocks could report it. That was a misreading
    # of its own rule: unsentBlocks runs on the RAW buffer at every call
    # site, never on this output, so hiding the tag here cannot blind it —
    # and keeping it put a live-looking [VAULT_NEW: …] into a filed
    # deliverable, asserting a cabinet path that was never written. The tag
    # goes; the text after it stays, which was the real reason the original
    # rule existed.
    check('an UNCLOSED opener is dropped — its tool never ran',
          'HIRE_AGENT' not in out['unclosedKept'], repr(out['unclosedKept']))
    check('…but the text after the unclosed opener survives',
          'name: Vee' in out['unclosedKept'] and 'Sure.' in out['unclosedKept'],
          repr(out['unclosedKept']))
    check('the real first-run leak: an inline VAULT_NEW never reaches the file',
          'VAULT_NEW' not in out['inlineVaultLeak']
          and 'Sourdough bread needs a starter' in out['inlineVaultLeak'],
          repr(out['inlineVaultLeak']))
    check('…and the office still says the file was never written',
          bool(out['inlineVaultNote']) and 'cabinet' in out['inlineVaultNote'],
          repr(out['inlineVaultNote']))
    check("a FABRICATED relay in the office's own label is called out",
          bool(out['fakeRelay']) and 'not Llama' in out['fakeRelay'],
          repr(out['fakeRelay']))
    check('…silent when a message really was delivered',
          out['relayDelivered'] is None, repr(out['relayDelivered']))
    check('…silent for names nobody hired, and for plain prose',
          out['relayStranger'] is None and out['relayProse'] is None,
          repr([out['relayStranger'], out['relayProse']]))
    check('a DECLARED wait with nothing sent is called out',
          bool(out['claimedAsk']) and 'nothing was sent' in out['claimedAsk'],
          repr(out['claimedAsk']))
    check('…and it stays silent when something really was delivered',
          out['claimedAskSent'] is None, repr(out['claimedAskSent']))
    check('…and when no wait was declared',
          out['noClaimNoNote'] is None and out['proseOnlyQuiet'] is None,
          repr([out['noClaimNoNote'], out['proseOnlyQuiet']]))
    check('an unclosed WRITE is called out, not left to an absent visit block',
          bool(out['unsentWrite']) and 'saved' in out['unsentWrite'],
          repr(out['unsentWrite']))
    check('…and the note contradicts the claim rather than describing a parse error',
          bool(out['unsentWrite']) and 'however it was described above' in out['unsentWrite'],
          repr(out['unsentWrite']))
    check('a properly closed write says nothing at all',
          out['closedWriteOk'] is None, repr(out['closedWriteOk']))
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
    # SUPERSEDED, deliberately, by evidence rather than by preference. This
    # asserted the opposite until 2026-08-07: that a write marker was not this
    # guard's business because "no visit block is already the honest record".
    # Three live runs killed that argument — Llama emitted an unclosed
    # [MEMORY_WRITE:…] every time, wrote nothing, and announced success in its
    # own ACK. An absence is not a record a person reads, and it never wins
    # against an explicit claim to the contrary.
    check('an unclosed WRITE is called out too', bool(out['ubWrite']), repr(out['ubWrite']))
    check('an echoed [Name · Role] label goes, and unblinds the marker strip',
          out['echoedLabel'] == 'The boss likes figs.', repr(out['echoedLabel']))
    check('a markdown reference definition is not a speaker label',
          out['refDefKept'].startswith('[1]: https://example.com'), repr(out['refDefKept']))
    check('a label quoted mid-reply is content, not a self-announcement',
          '[Mika · Head of Inbox]:' in out['midReplyKept'], repr(out['midReplyKept']))
    check('the speaker\'s own label goes wherever it lands, not just line one',
          out['selfMidText'] == 'The boss likes figs.\n\nGrape.', repr(out['selfMidText']))
    check('…and another coworker\'s label is still content',
          '[Mika · Head of Inbox]:' in out['othersKept'], repr(out['othersKept']))
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

    cover = check_guards_cover_every_path()
    thin = [f'{g}: {n}/{b} paths' for g, (n, b) in cover.items() if n < b]
    check('every buffer-and-roster guard runs in every reply path',
          not thin, ', '.join(thin))

    raw = check_raw_buffer_shown()
    check('no reply path shows the RAW buffer — cleanHarmony(buf) without visibleReply',
          not raw, ', '.join(raw))

    paths = check_every_reply_path()
    missing = [f'{r}:{n}' for r, n, ok in paths if not ok]
    check(f'all {len(paths)} reply paths clean their final text',
          not missing, 'uncleaned: ' + ', '.join(missing) if missing else '')

    # ── a hand-off is not a protocol dump ───────────────────────────────
    # Watched live on LM Studio: the boss asked Gemma a question and the
    # whole bubble read "[DM_TO: Nano] Can you name one color of a ripe
    # banana? [/DM_TO]". The raw fallback is for markers we did NOT
    # understand; a recognised block is the opposite case.
    check('a pure hand-off reads as an office sentence',
          out['pureDM'] == 'Sent this to Nano — their reply lands in the team room.',
          repr(out['pureDM']))
    # The same branch renders for a DM sent BACK, so it must not claim the
    # sender did the asking, and must not promise a follow-up this office
    # does not deliver.
    check('the sentence promises nothing it cannot keep',
          not re.search(r"come back to you|I'?ll (?:get|let you)", out['pureDM'], re.I),
          repr(out['pureDM']))
    check('two coworkers are both named', 'Nano and Kip' in out['pureDMTwo'], repr(out['pureDMTwo']))
    check('the same coworker twice is named once',
          out['pureDMSame'].count('Nano') == 1, repr(out['pureDMSame']))
    check('prose alongside a hand-off still wins', out['dmWithProse'] == 'On it.', repr(out['dmWithProse']))
    check('an unrecognised marker is still shown, not swallowed',
          out['unknownTag'] == '[MYSTERY_TAG: x]', repr(out['unknownTag']))

    # ── the answer comes home ───────────────────────────────────────────
    # Every agent-to-agent DM lands in 'team', so a chain the boss started
    # ended in a room the boss was not watching: the coworkers cooperated
    # and the boss got no answer. The last link now reports back -- but only
    # once the round-trip has SETTLED.
    app_src = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    rb = re.search(r'if \(chainOrigin && thread !== chainOrigin[\s\S]{0,400}?\n      \}', app_src)
    check('the last link of a boss-started chain reports back', bool(rb),
          'app.jsx: no report-back block found')
    body = rb.group(0) if rb else ''
    # The trap, and it bit once: cleanBuf has already had the hand-off
    # STRIPPED, so asking it "did they hand off?" always answers no.
    check('the settled-check reads the raw buffer, not the stripped one',
          'extractAllDMs(buf)' in body and 'extractAllDMs(cleanBuf)' not in body,
          'app.jsx: test `buf` — cleanBuf has the hand-off removed already')
    check('only the coworker the boss asked reports back',
          'agent.id === chainAskedId' in body,
          'app.jsx: a peer pulled into the chain does not owe the boss a reply')
    check('nothing is posted twice into the room it came from',
          'thread !== chainOrigin' in body,
          'app.jsx: guard against relaying into the originating thread')

    # ── the first sentence of the product ───────────────────────────────
    # The greeting promised a brain nobody had probed: "I'm already running
    # on Cafreso's Gemma 4 brain - nothing to sign up for", stated flat, one
    # clause after "nothing here is pre-staged, so everything you see happen
    # from here on is real". On a self-hosted install that opening line was
    # simply false. probeManagedBrain() already answered the question and
    # had no listener, so the claim now waits for it.
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    intro = re.search(r"text: \"Welcome to your HQ[^\"]*\"", app)
    check('the greeting claims no brain before anything has looked',
          bool(intro) and not re.search(r'gemma|already running on|nothing to sign up',
                                        intro.group(0), re.I),
          'app.jsx: the welcome line must not assert a brain')
    seg = app[intro.end():intro.end() + 1600] if intro else ''
    check('the brain is reported only after probeManagedBrain resolves',
          'probeManagedBrain' in seg and 'brain' in seg,
          'app.jsx: the follow-up must await the probe')
    check('both answers are written, not just the happy one',
          "shared brain" in seg and "don't have a shared brain" in seg,
          'app.jsx: a probe with one branch is an assertion with extra steps')


    print()
    if FAILS:
        print(f'reply hygiene: {len(FAILS)} failure(s)')
        return 1
    print('reply hygiene: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

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
    for fn in ('extractAcks', 'stripAcks', 'stripOrphanTags', 'stripBlocks', 'stripSelfLabel', 'visibleReply', 'extractAllDMs', 'extractApproval', 'isHandoffPlaceholder', 'vaultPaths', 'upToToolCall', 'placeholderRefusal', 'unsentHandoff', 'unsentElevation', 'unsentBlocks', 'unsentAsk', 'fabricatedRelay'):
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
// Generator and recogniser must stay in sync: the recogniser is what lets
// call sites re-dress the placeholder per room, so if someone rewords the
// sentence in visibleReply without teaching isHandoffPlaceholder, every
// re-dress silently stops and the stale copy ships again.
R.phRound = isHandoffPlaceholder(visibleReply('[DM_TO: Nano]\nq\n[/DM_TO]'));
R.phTwo   = isHandoffPlaceholder(visibleReply('[DM_TO: Nano]\nq1\n[/DM_TO]\n[DM_TO: Kip]\nq2\n[/DM_TO]'));
R.phPlain = isHandoffPlaceholder('Red.');
// A reply that was ONLY an approval ask — the "walks to your desk" moment.
R.apOnly  = visibleReply('[NEEDS_APPROVAL: order two pizzas — $40]');
R.apProse = visibleReply('I can do that, but it costs money.\n[NEEDS_APPROVAL: send the newsletter]');
R.apSpace = visibleReply('[NEEDS APPROVAL: send the invoice]');
// The unclosed-DM_TO recovery. Both real misses (an 8B model, then
// gemma-4-e4b captured verbatim) had this exact shape: opener, own line,
// body, then the stream just stops.
R.dmUnclosedExtract = extractAllDMs('[DM_TO: Nano]\nWhat is 4+4?');
R.dmUnclosedReply   = visibleReply('[DM_TO: Nano]\nWhat is 4+4?');
// A CLOSED block earlier plus an unclosed one after — both must survive,
// the closed one untouched, the trailing one recovered.
R.dmMixedExtract = extractAllDMs('[DM_TO: Llama]\nQ1\n[/DM_TO]\n[DM_TO: Nano]\nQ2');
// The model changed its mind and kept talking after the opener — a blank
// line, then unrelated prose. Must NOT be recovered: that is abandonment,
// not a forgotten closer.
R.dmAbandonedExtract = extractAllDMs('[DM_TO: Nano]\nWhat is 4+4?\n\nActually never mind, I will just answer directly.');
// Opened, nothing after it at all.
R.dmEmptyOpenExtract = extractAllDMs('[DM_TO: Nano]');
// A closed block with NOTHING after it — the tail-recovery path must not
// invent a phantom second entry from empty leftover text.
R.dmClosedOnlyExtract = extractAllDMs('[DM_TO: Nano]\nQ\n[/DM_TO]');
// A stamp with no content is not a request. Watched live: the boss's tray
// read "N/A · by Gemma · awaiting stamp".
R.apNA    = extractApproval('[NEEDS_APPROVAL: N/A]');
R.apNone  = extractApproval('[NEEDS_APPROVAL: none needed]');
R.apDash  = extractApproval('[NEEDS_APPROVAL: -]');
R.apDots  = extractApproval('[NEEDS_APPROVAL: ...]');
R.apReal  = extractApproval('[NEEDS_APPROVAL: order two pizzas — $40]');
R.apShort = extractApproval('[NEEDS_APPROVAL: pay $40 to Luigi]');

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
// The workflow-run leak (2026-08-12 ledger entry): genuine model prose
// immediately after a line-opening marker, NO separating newline. The old
// whole-line strip ate the prose too, emptied `cleaned`, and the raw
// marker+prose came back out through the "nothing survived" fallback --
// filed verbatim into a delivered .md. Only the marker should go.
R.orphanGenuine = visibleReply("[MEMORY_READ: decisions/banana.md]I do see that 'banana' was a result from a previous task.");
// The doc-string echo this whole rule exists for must still be fully
// removed -- the em dash right after the bracket is the signal that this
// is TOOL_REGISTRY's own `doc:` text coming back, not the coworker's words.
// (Real surrounding content, like orphanFetch above -- a bare marker+echo
// with nothing else falls to a different, pre-existing "nothing survived
// the strip" fallback that this fix does not touch.)
R.orphanEcho = visibleReply('Looking it up.\n[BROWSER_FETCH: https://en.wikipedia.org/wiki/Lime] — fetch a URL and return its readable text content.\nLime is a citrus fruit.');
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
/* skipKinds — the task path's exception. The office files the deliverable
   itself there (fileDelivery), so once filing succeeded the two cabinet
   kinds must NOT be called out: the note would contradict the FIRST
   DELIVERY sheet, the floor log, and the file the boss can open. Watched
   live on a virgin office's first starter task (Llama emitted an unclosed
   [VAULT_APPEND: while the office filed the finished draft to Drafts/).
   Everything else stays guarded even with the skip in force. */
R.ubSkipVault    = unsentBlocks('the draft\n[VAULT_APPEND: Drafts/note.md]\nbody', ['VAULT_NEW', 'VAULT_APPEND']);
R.ubSkipVaultNew = unsentBlocks('[VAULT_NEW: Drafts/note.md]\nbody', ['VAULT_NEW', 'VAULT_APPEND']);
R.ubSkipKeepsRest= unsentBlocks('[VAULT_APPEND: a.md]\nx\n[MEMORY_WRITE: b.md]\ny', ['VAULT_NEW', 'VAULT_APPEND']);
R.ubNoSkipVault  = unsentBlocks('the draft\n[VAULT_APPEND: Drafts/note.md]\nbody');
R.uhOwnLine   = unsentHandoff('[DM_TO: Kenji]', 0);   // stripped from view, still unsent
/* A coworker addressing ITSELF. Watched live: Nova answered a plain
   question and also emitted an empty, unclosed [DM_TO: Nova]. The office
   skipped it (right — there is nobody to deliver to), and the guard then
   told the boss "the handoff to Nova didn't go out … ask them yourself with
   @Nova", in the bubble where the boss had just done exactly that. */
R.uhSelf      = unsentHandoff('[DM_TO: Nova]\n', 0, 'Nova');
R.uhSelfCase  = unsentHandoff('[DM_TO: nova]\n', 0, 'Nova');
R.uhSelfThenReal = unsentHandoff('[DM_TO: Nova]\n[DM_TO: Kenji]\n', 0, 'Nova');
R.uhNoSelfName = unsentHandoff('[DM_TO: Nova]\n', 0);
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
    check('genuine prose right after a line-opening marker survives, only the marker goes',
          out['orphanGenuine'] == "I do see that 'banana' was a result from a previous task.",
          repr(out['orphanGenuine']))
    check('a doc-string echo (marker + em dash) is still fully dropped',
          out['orphanEcho'] == 'Looking it up.\n\nLime is a citrus fruit.',
          repr(out['orphanEcho']))
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
    # skipKinds: the task path files the deliverable itself, so once filing
    # succeeded the cabinet kinds must go quiet — and ONLY the cabinet kinds.
    check('a skipped VAULT_APPEND is silent when the office already filed',
          out['ubSkipVault'] is None, repr(out['ubSkipVault']))
    check('…and a skipped VAULT_NEW likewise', out['ubSkipVaultNew'] is None,
          repr(out['ubSkipVaultNew']))
    check('the skip leaves every other kind guarded — MEMORY_WRITE still flags',
          out['ubSkipKeepsRest'] is not None
          and out['ubSkipKeepsRest'].count('_(') == 1
          and 'memory' in out['ubSkipKeepsRest'],
          repr(out['ubSkipKeepsRest']))
    check('without the skip an unclosed VAULT_APPEND is still called out '
          '(the chat paths, where nothing was filed for them)',
          out['ubNoSkipVault'] is not None and 'cabinet' in out['ubNoSkipVault'],
          repr(out['ubNoSkipVault']))
    # And the wiring, not just the function: the TASK path in app.jsx must
    # actually pass the skip, gated on the office having filed. Without this
    # a refactor could drop the second argument and every check above would
    # stay green while the live bug returned.
    #
    # The five guards are one call now (HQ.honestyNotes), so the skip rides
    # in the task path's `honestyFor` closure rather than at the unsentBlocks
    # call itself. Same requirement, one layer up.
    app_src = (Path(__file__).resolve().parent.parent / 'app.jsx').read_text()
    check('app.jsx task path gates the cabinet kinds on deliveryFiled',
          re.search(r"skipKinds:\s*deliveryFiled\s*\?\s*\['VAULT_NEW',\s*'VAULT_APPEND'\]\s*:\s*undefined",
                    app_src) is not None)
    check('app.jsx sets deliveryFiled from the filing outcome',
          'deliveryFiled = !!filedPath;' in app_src)
    # …and sets it BEFORE anything asks. The flag used to be assigned thirty
    # lines below the activity row that now depends on it, which is exactly
    # the kind of ordering a reader cannot see from either end.
    # Scoped to the task path: `honesty = honestyFor(buf)` also appears on
    # the Delegate path, earlier in the file, and an unscoped index() would
    # compare two different functions and pass for the wrong reason.
    task_path = app_src[app_src.index('let deliveryFiled = false;'):]
    check('...before the guards are run on the task path',
          task_path.index('deliveryFiled = !!filedPath;')
          < task_path.index('honesty = honestyFor(buf);'),
          'app.jsx: the skip is decided at call time, so filing has to have '
          'happened first or the office contradicts its own cabinet')
    check('an own-line marker still counts as unsent', bool(out['uhOwnLine']))
    check('a coworker addressing itself leaves nobody waiting',
          out['uhSelf'] is None and out['uhSelfCase'] is None,
          f"{out['uhSelf']!r} / {out['uhSelfCase']!r} — the note names a "
          'person the boss should chase, and here that person is the one who '
          'just answered them')
    check('...but a real recipient behind a self-DM is still reported',
          out['uhSelfThenReal'] is not None and 'Kenji' in out['uhSelfThenReal'],
          f"{out['uhSelfThenReal']!r} — skipping the self-addressed marker "
          'must not become a way to hide the one that mattered')
    check('with no speaker named, nothing is assumed',
          out['uhNoSelfName'] is not None,
          'unsentHandoff must keep working for callers that do not pass a '
          'speaker — silence there would be a guess, not a fact')
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
    # The GENERIC sentence stays promise-free because visibleReply cannot
    # know whether a report-back is armed; the promise lives at the call
    # site, which checks chainOrigin before making it (see below).
    check('the generic sentence promises nothing it cannot keep',
          not re.search(r"come back to you|I'?ll (?:get|let you)", out['pureDM'], re.I),
          repr(out['pureDM']))
    check('the placeholder recogniser accepts its own generator',
          out['phRound'] is True and out['phTwo'] is True,
          'isHandoffPlaceholder must match what visibleReply writes')
    check('...and only that', out['phPlain'] is False)
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
    rb = re.search(r'if \(chainOrigin && thread !== chainOrigin[\s\S]{0,900}?\n      \}', app_src)
    check('the last link of a boss-started chain reports back', bool(rb),
          'app.jsx: no report-back block found')
    body = rb.group(0) if rb else ''
    # The trap, and it bit once: cleanBuf has already had the hand-off
    # STRIPPED, so asking it "did they hand off?" always answers no.
    # Two re-parses were tried here and both were wrong: cleanBuf has the
    # hand-off stripped out already, and extractAllDMs() needs a newline
    # after the tag so it scores a one-line DM as zero. Ask the queue the
    # dispatcher itself iterates.
    check('the settled-check asks the dispatcher queue, not a re-parse',
          '!dmQueue.length' in body and 'extractAllDMs' not in body,
          'app.jsx: use dmQueue — the one authority on whether this turn handed off')
    check('nothing is posted twice into the room it came from',
          'thread !== chainOrigin' in body,
          'app.jsx: guard against relaying into the originating thread')
    # This condition used to read `agent.id === chainAskedId` -- only the
    # coworker the boss ASKED may report back -- on the reasoning that a peer
    # pulled into the chain owes the boss nothing. It describes a run of the
    # asked coworker that is itself in some other thread, which happens only
    # if the peer DMs them back. The ordinary two-hop shape the boss actually
    # produces (boss asks Nova, Nova asks Pip, Pip answers) never gets there:
    # Nova's run ends at the dispatch and she has no second turn. So nobody
    # reported, and the unkept-promise notice below fired -- the office told
    # the boss "nothing came back to pass on" about a complete answer sitting
    # one tab away, seconds after promising in its own voice to bring it.
    # Watched live in both DM shapes. Whoever is holding the answer brings it.
    # Read the CONDITION, not the block: chainAskedId still appears inside,
    # because naming the hop needs to know who did the asking. What must not
    # come back is the identity test in the guard.
    cond = body.split(') {')[0]
    check('the coworker holding the answer brings it, asked or not',
          'chainAskedId' not in cond,
          'app.jsx: requiring the ASKED coworker strands the ordinary two-hop '
          'chain, where that coworker never runs again')
    check('...exactly once, however deep the chain went',
          '!chain.reported' in body and 'chain.reported = true;' in body,
          'app.jsx: without the flag every caller above the answer relays it too')
    # Copied, never paraphrased, and under their OWN name -- the boss asked
    # one person and should not have to work out why a second is talking, so
    # a one-line HQ note says how it got here.
    check('the relay carries their own words and their own name',
          'text: cleanBuf' in body and 'name: `${agent.name}' in body,
          'app.jsx: the office does not summarise a coworker back to the boss')
    check('...with a note naming who asked whom',
          re.search(r'asked \$\{agent\.name\} — here', body)
          and 'asker.id !== agent.id' in body,
          'app.jsx: name the hop, and only when there was one')

    # The other half of the loop: the coworker the boss asked, holding a
    # peer's answer, must be TOLD to answer the boss. The generic DM framing
    # says "You are replying to X, NOT to the boss" and mandates a closing
    # [DM_TO: X] -- so the one coworker who could close the loop was
    # instructed never to, and pairs ping-ponged to the depth cap while the
    # boss's thread sat empty. Watched twice before the cause was found in
    # the PROMPT, not the plumbing.
    # The other end of the chain: "ask Nano what 4+4 is" produced a bare
    # echo of the question - no DM, no chain - in 3 of 5 live runs, and got
    # MORE likely at low temperature. The boss-direct framing presented
    # [DM_TO] only as a skillset fallback, and 4+4 is inside everyone's
    # skillset, so an obedient model had no licensed path to DM the
    # coworker the boss named. With the license written in: 3/3 clean runs.
    check('naming a coworker licenses the DM, skillset or not',
          'when the boss NAMES a coworker' in app_src and 'that IS a [DM_TO' in app_src,
          'app.jsx: the boss-direct framing must cover "ask <name> ..." explicitly')

    check('the coworker the boss asked is prompted to report back, not loop',
          'owesTheBoss' in app_src
          and re.search(r'owesTheBoss = !!dmFrom && !!chainOrigin && agent\.id === chainAskedId', app_src)
          and 'report back to the person who asked you' in app_src,
          'app.jsx: the boss-asked coworker needs its own DM framing')

    # ── an approval ask reads as the walk, not the protocol ────────────
    # Every finalize listens for [NEEDS_APPROVAL], but no strip family knew
    # the marker and only the CEO was ever taught it. A coworker told to
    # "get the boss's approval" invented its own bracket, matched nothing,
    # and no tray appeared; a coworker who emitted it correctly would have
    # shown the boss raw protocol beside the tray.
    check('"N/A" is not an authorisation request', out['apNA'] is None)
    check('nor is "none needed"', out['apNone'] is None)
    check('nor a dash', out['apDash'] is None)
    check('nor an ellipsis', out['apDots'] is None)
    check('a real ask still comes through', out['apReal'] == 'order two pizzas — $40')
    check('...including a short real one', out['apShort'] == 'pay $40 to Luigi')

    check('a marker-only reply reads as the walk to the desk',
          out['apOnly'] == 'Asked for your stamp — "order two pizzas — $40". It\'s waiting on your desk.',
          repr(out['apOnly']))
    check('prose beside the marker survives; the marker does not',
          out['apProse'] == 'I can do that, but it costs money.', repr(out['apProse']))
    # ── an unclosed DM_TO is recovered, not silently dropped ────────────
    # Both real misses captured verbatim (an 8B model, then gemma-4-e4b
    # through the live proxy) had the SAME shape: the model opened the tag
    # correctly and simply never emitted the closer. Before this, dispatch
    # silently failed (dmQueue stayed empty, Nano was never asked) and
    # display showed a non-sequitur to the boss ("Gemma: What is 4+4?").
    check('extractAllDMs recovers a trailing unclosed opener',
          out['dmUnclosedExtract'] == [{'to': 'Nano', 'body': 'What is 4+4?'}],
          repr(out['dmUnclosedExtract']))
    check('visibleReply renders the recovered hand-off as the walk, not a non-sequitur',
          out['dmUnclosedReply'] == 'Sent this to Nano — their reply lands in the team room.',
          repr(out['dmUnclosedReply']))
    check('a closed block earlier is untouched, and the trailing unclosed one is added',
          out['dmMixedExtract'] == [{'to': 'Llama', 'body': 'Q1'}, {'to': 'Nano', 'body': 'Q2'}],
          repr(out['dmMixedExtract']))
    check('a blank line after the opener means abandonment, not a forgotten closer',
          out['dmAbandonedExtract'] == [], repr(out['dmAbandonedExtract']))
    check('an opener with nothing after it recovers nothing',
          out['dmEmptyOpenExtract'] == [], repr(out['dmEmptyOpenExtract']))
    check('a closed block with no trailing text does not grow a phantom second entry',
          out['dmClosedOnlyExtract'] == [{'to': 'Nano', 'body': 'Q'}], repr(out['dmClosedOnlyExtract']))

    check('the space variant is understood too',
          'waiting on your desk' in out['apSpace'], repr(out['apSpace']))
    rt = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
    # The trap that ate the tray, pinned as a census: a scan that reads the
    # CLEANED text is blind to every marker the cleaning removed. The
    # approval scan must read the raw stream at every listener — buf before
    # reassignment (rawReply), the un-reassigned task/delegate bufs, or the
    # throttle's raw() on the CEO path. cleanBuf/finalText/cleaned are all
    # post-strip and therefore always empty of markers.
    chat_src = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
    bad_scans = (re.findall(r'extractApproval\((?:cleanBuf|cleaned)\)', app_src)
                 + re.findall(r'extractApproval\(finalText\)', chat_src))
    check('no approval scan reads post-strip text',
          not bad_scans, 'found: %s' % bad_scans)
    # Grepping for cleanBuf/finalText alone is WEAKER than the defect: the
    # live bug was extractApproval(buf) AFTER `buf = cleaned` — same name,
    # poisoned value, invisible to a token grep. So pin the exact shape:
    # one rawReply capture, taken BEFORE the one rewrite; the dispatch scan
    # takes rawReply; the task/delegate scans take their never-reassigned
    # bufs — and there is exactly ONE `buf = cleaned` in the file, so a new
    # rewrite in those functions cannot appear without failing here.
    check('the dispatch finalize captures the raw stream before cleaning',
          app_src.count('rawReply = buf;') == 2
          and app_src.index('rawReply = buf;') < app_src.index('buf = cleaned;')
          and app_src.count('const approvalDesc = HQ.extractApproval(rawReply);') == 1
          and app_src.count('const approvalDesc = HQ.extractApproval(buf);') == 2
          and app_src.count('buf = cleaned;') == 1,
          'app.jsx: rawReply before the rewrite; scans pinned per path')

    check('every coworker run is taught the marker, not just the CEO',
          'const approvalNote' in rt
          and re.search(r'toolsNote \+ elevatedNote \+ approvalNote', rt)
          and 'NEEDS_APPROVAL' in rt.split('const approvalNote')[1][:600],
          'hq-runtime.jsx: approvalNote must join agentStream\'s system prompt')

    # ── the placeholder is re-dressed per room ─────────────────────────
    # In the team room the placeholder sat NEXT TO the DM bubble it
    # described — two bubbles per hand-off. In the boss's thread it still
    # said "their reply lands in the team room", copy written before the
    # report-back existed, pointing the boss away from an answer that now
    # comes to them.
    check('the team room drops the placeholder beside its own DM bubble',
          re.search(r'if \(handedOff && dmFrom\) return prev\.filter\(m => m\.id !== agentMsgId\)', app_src),
          'app.jsx: pure hand-off in the team room keeps only the DM bubble')
    check("the boss's thread gets the promise only when the report-back is armed",
          re.search(r'const promising = handedOff && askedForHelp;', app_src)
          and "I'll bring their answer back here" in app_src,
          'app.jsx: promise gated on an open chain')
    # SAYING the promise and HAVING an open chain are different questions, and
    # reading both off isHandoffPlaceholder is what broke the second one.
    # That matcher recognises exactly the office's own substitute sentence,
    # which exists only for a reply that was nothing BUT the DM block. So a
    # coworker who did the natural thing and explained itself first ("I will
    # ask Pip to draft it.") kept its own words -- correctly -- and in the
    # same stroke left chain.promised false. Nothing tracked the round trip:
    # no relay, and no unkept-promise notice either. The boss got a sentence
    # about asking Pip and then permanent silence. Watched live.
    check('asking for help opens the chain, whatever else was said',
          re.search(r'const askedForHelp = dmQueue\.length > 0 && !dmFrom && !!chainOrigin;', app_src),
          'app.jsx: chain tracking must not be gated on the reply being NOTHING '
          'but the hand-off — that is a question about the bubble, not the chain')
    check('...and whose words go in the bubble is the other question',
          'const handedOff = dmQueue.length > 0 && HQ.isHandoffPlaceholder(cleaned);' in app_src,
          'app.jsx: keep the two flags distinct or they drift back together')
    # A promise needs its failure notices in the SAME room it was made in.
    check('the depth cap is announced where the promise was made',
          re.search(r'went back and forth too long without an answer[\s\S]{0,80}thread: originThread', app_src),
          'app.jsx: cap notice must post to originThread too')
    check("a peer's snag is announced where the promise was made",
          re.search(r'hit a snag on the way to your answer[\s\S]{0,60}thread: chainOrigin', app_src),
          'app.jsx: catch must notify chainOrigin when a peer dies mid-chain')

    # ── the promise has three failure notices, not two ──────────────────
    # "I'll bring their answer back here" is a promise, and a promise needs
    # its failures announced in the room it was made in. Two notices already
    # covered the loud failures (depth cap, peer snag). The QUIET one had
    # nothing: the peer returns no answer at all and the boss's thread just
    # stays silent forever — watched live when nemotron spent its whole
    # budget thinking and returned zero content chunks.
    check('a promise that goes unanswered is admitted, not left silent',
          re.search(r'chain\.promised && !chain\.reported', app_src)
          and 'nothing came back to pass on' in app_src,
          'app.jsx: the boss-level frame must report an unkept promise')
    # It must be a FACT, not a timeout that got bored. Every child dispatch
    # is awaited, so at the boss-level frame the chain has terminated.
    check('the unkept-promise notice needs no timer',
          not re.search(r'setTimeout[^\n]{0,80}(promised|reported|came back)', app_src),
          'app.jsx: this is decidable from awaited state — a timer would guess')
    # Guard both halves of the bookkeeping, since either one silently
    # disables the notice: promised is set where the promise is rendered,
    # reported where the answer is delivered.
    check('the promise is recorded where it is made',
          'if (askedForHelp) chain.promised = true;' in app_src,
          'app.jsx: chain.promised must be set wherever a chain OPENS, not '
          'only where the office happens to narrate it')
    check('keeping the promise is recorded where the answer lands',
          'chain.reported = true;' in app_src,
          'app.jsx: chain.reported must be set by the report-back')
    # One object per chain, shared by reference down the recursion — if a
    # dispatch site forgets to pass it, the deepest frame reports against a
    # fresh object and the notice fires on a promise that WAS kept.
    dm_sites = re.findall(r'dmFrom: \w+, dmDepth: dmDepth \+ 1[^}]*', app_src)
    check('every recursive dispatch carries the same chain object',
          bool(dm_sites) and all('chainState: chain' in d for d in dm_sites),
          'app.jsx: %d recursive site(s), missing chainState on some' % len(dm_sites))
    # Only the boss-level frame speaks, or a deep chain says it repeatedly.
    # A specific failure already told the boss what happened -- the
    # generic notice must not repeat it in weaker words. Caught live: a
    # peer timeout raised its own snag notice AND left chain.reported
    # false, so without this gate the boss got two system lines back to
    # back for the one failure.
    check('the depth cap marks the failure as already explained',
          re.search(r'chain\.failureNoticed = true;\s*//[^\n]*\n\s*setChat[\s\S]{0,160}went back and forth too long', app_src),
          'app.jsx: depth-cap branch must set chain.failureNoticed before its own notice')
    check("a peer's snag marks the failure as already explained",
          re.search(r'chain\.failureNoticed = true;[\s\S]{0,200}hit a snag on the way', app_src),
          'app.jsx: the catch branch must set chain.failureNoticed before its own notice')
    check('the generic notice defers to a specific one that already fired',
          re.search(r'chain\.promised && !chain\.reported && !chain\.failureNoticed', app_src),
          'app.jsx: the third notice must not repeat a diagnosis already given')

    check('only the boss-level frame announces it',
          re.search(r'if \(!dmFrom && chain\.promised', app_src),
          'app.jsx: guard on !dmFrom so a five-hop chain says this once')

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

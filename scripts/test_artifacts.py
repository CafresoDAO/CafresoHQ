#!/usr/bin/env python3
"""Artifact-landing helpers (app/artifacts.jsx) — pure-function suite.

These decide what actually gets written into the user's vault when a task
finishes (OFFICE_AS_INTERFACE §3.6), so their edge cases are worth pinning:
a too-greedy marker filter eats the deliverable, a too-strict one files
machine syntax as the user's first delivery.

The module imports claude-client.jsx (browser-only), so we lift the pure
functions out of the real source and run THEM — not a copy — under node.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'artifacts.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def _strip_module_lines(path):
    return '\n'.join(ln for ln in path.read_text(encoding='utf-8').split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))


def pure_source():
    """The source minus its import/export lines — the pure half runs as-is.

    floor.jsx is prepended because artifacts imports `visitLine` from it:
    the delivery footer, the desk bubble, the activity row and the chat echo
    all share one phrasing table now, so the test runs the REAL one rather
    than a stand-in that could drift from it.
    """
    src = _strip_module_lines(FLOOR) + '\n' + _strip_module_lines(SRC)
    # cabinetIsEncrypted/fileDelivery close over browser globals; drop them so
    # the rest evaluates standalone. Everything else is pure string work.
    for fn in ('function cabinetIsEncrypted', 'async function fileDelivery'):
        i = src.find(fn)
        if i == -1:
            continue
        depth, j, started = 0, i, False
        while j < len(src):
            if src[j] == '{':
                depth += 1
                started = True
            elif src[j] == '}':
                depth -= 1
                if started and depth == 0:
                    j += 1
                    break
            j += 1
        src = src[:i] + src[j:]
    return src


def run_js(cases_js):
    script = pure_source() + '\n' + cases_js
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('artifact landing helpers')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
// ── stripToolMarkers ────────────────────────────────────────────────────
R.dropsUpperMarker   = stripToolMarkers('[MEMORY_WRITE: a/b.md]\nreal text');
R.dropsMixedCase     = stripToolMarkers('[Vault_APPEND: Research/x.md]\nreal text');
R.dropsClosing       = stripToolMarkers('real text\n[/VAULT_NEW]');
R.dropsBareUpper     = stripToolMarkers('[ACK]\nreal text');
R.keepsCheckbox      = stripToolMarkers('[x]\nreal text');
R.keepsLowerAside    = stripToolMarkers('[draft]\nreal text');
R.keepsMdLink        = stripToolMarkers('[Text](https://example.com)');
R.keepsRefDef        = stripToolMarkers('[1]: https://example.com');
R.keepsInlineMention = stripToolMarkers('use [MEMORY_WRITE: x] to save');
R.collapsesBlanks    = stripToolMarkers('a\n\n[ACK: done]\n\n\nb');
R.allMarkersEmpty    = stripToolMarkers('[ACK: done]\n[/DM_TO]');
// ── extractHtml ─────────────────────────────────────────────────────────
R.htmlFromFence      = extractHtml('here you go\n```html\n<!doctype html><h1>Hi</h1>\n```\ndone');
R.htmlFromBareFence  = extractHtml('```\n<html><body>Hi</body></html>\n```');
R.htmlUnfenced       = extractHtml('<!doctype html>\n<h1>Hi</h1>');
R.htmlSkipsProseFence= extractHtml('```\njust notes, no markup\n```');
R.htmlNullOnProse    = extractHtml('I would build a page with a header and a footer.');
// ── slugify ─────────────────────────────────────────────────────────────
R.slug               = slugify('First draft: a two-sentence welcome note!');
R.slugEmpty          = slugify('   ');
R.slugCapped         = slugify('x'.repeat(120)).length;
// A title cut mid-word must not leave the hyphen hanging.
R.slugNoTrailDash = slugify('Save a note to your memory saying the boss likes bullet points, then confirm');
R.slugTrailsClean = /-$/.test(R.slugNoTrailDash);
R.slugManyDashes  = slugify('a' + ' -- '.repeat(30) + 'b');
// ── buildDelivery ───────────────────────────────────────────────────────
R.briefHome = buildDelivery({ title: 'T', starter: 'brief' }, { name: 'A' }, 'body').path;
R.draftHome = buildDelivery({ title: 'T', starter: 'draft' }, { name: 'A' }, 'body').path;
R.pageHtml  = buildDelivery({ title: 'T', starter: 'page' }, { name: 'A' }, '```html\n<h1>Hi</h1>\n```');
R.pageProse = buildDelivery({ title: 'T', starter: 'page' }, { name: 'A' }, 'I would build a nice page.');
R.plainHome = buildDelivery({ title: 'T' }, { name: 'A' }, 'body').path;
R.emptyBody = buildDelivery({ title: 'T' }, { name: 'A' }, '   ');
R.markerOnly= buildDelivery({ title: 'T' }, { name: 'A' }, '[ACK: done]');
R.headerHas = buildDelivery({ title: 'My Task' }, { name: 'Llama' }, 'body').content;
// ── stripToolEcho ───────────────────────────────────────────────────────
// The exact shape hq-runtime.jsx appends and hands back as ev.echo.
const echo = (n, a, r) => `\n\n📡 ${n}("${a}") →\n${r}\n\n`;
const fetched = echo('BROWSER_FETCH', 'https://en.wikipedia.org/wiki/Primary_color',
  'URL: https://en.wikipedia.org/wiki/Primary_color\nStatus: 200\n\nPage body\n\nmore body\n[…truncated, 79626 more chars]');
R.echoGone      = stripToolEcho(`I'll look it up.${fetched}Red, yellow and blue.`, [fetched]);
R.echoMultiline = /Status: 200|truncated|📡/.test(R.echoGone);
R.echoNoVisits  = stripToolEcho('just prose', []);
R.echoNullSafe  = stripToolEcho('just prose', [null, undefined, '']);
R.echoTwice     = stripToolEcho(`a${fetched}b${fetched}c`, [fetched]);
R.echoUnmatched = stripToolEcho('prose only', [echo('X', 'y', 'z')]);
R.echoRegexSafe = stripToolEcho('a\n\n📡 F("a.b(c)[d]*") →\nr\n\nb', ['\n\n📡 F("a.b(c)[d]*") →\nr\n\n']);
// ── workingNotes ────────────────────────────────────────────────────────
R.notesWeb   = workingNotes([{ name: 'BROWSER_FETCH', arg: 'https://example.com/x' }]);
R.notesSearch= workingNotes([{ name: 'WEB_SEARCH', arg: 'primary colours' }]);
R.notesVault = workingNotes([{ name: 'VAULT_READ', arg: 'Research/notes.md' }]);
R.notesOther = workingNotes([{ name: 'WEIRD_TOOL', arg: 'thing' }]);
R.notesDedup = workingNotes([{ name: 'BROWSER_FETCH', arg: 'https://a.com' },
                             { name: 'BROWSER_FETCH', arg: 'https://a.com' }]);
R.notesNoArg = workingNotes([{ name: 'BROWSER_FETCH', arg: '  ' }]);
R.notesArgless  = workingNotes([{ name: 'MEMORY_LIST', arg: '' }]);
R.notesArglessMix = workingNotes([{ name: 'MEMORY_READ', arg: 'a.md' }, { name: 'MEMORY_LIST', arg: '' }]).length;
R.notesNoName   = workingNotes([{ arg: 'x' }]);
R.notesNone  = workingNotes([]);
R.notesJargon= workingNotes([{ name: 'BROWSER_FETCH', arg: 'https://a.com' }]).join('\n');
// ── buildDelivery with visits ───────────────────────────────────────────
R.withWorking = buildDelivery({ title: 'T' }, { name: 'A' },
  `Answer.${fetched}`, [{ name: 'BROWSER_FETCH', arg: 'https://a.com', echo: fetched }]).content;
R.echoOnlyBody = buildDelivery({ title: 'T' }, { name: 'A' }, fetched,
  [{ name: 'BROWSER_FETCH', arg: 'https://a.com', echo: fetched }]);
R.noWorkingSection = buildDelivery({ title: 'T' }, { name: 'A' }, 'body').content;
// ── citesOutside — does the reply point past the coworker's own head? ───
R.coSourceExt  = citesOutside('- Teams miss deadlines. (Source: Harvard Business Review article "Why Small Teams Fail")');
R.coSourceLine = citesOutside('Source: The Mythical Man-Month by Fred Brooks');
R.coSourceItem = citesOutside('- Source: Peopleware, DeMarco & Lister');
R.coSourcesHdr = citesOutside('Sources: Peopleware; Deep Work');
R.coUrl        = citesOutside('See https://hbr.org/2019/x for the study.');
R.coWww        = citesOutside('More at www.example.com today.');
R.coMixed      = citesOutside('- A. (Source: what I already know)\n- B. (Source: Deep Work by Cal Newport)');
// The compliant behaviour the brief itself invites must NOT be flagged.
R.coOwnKnow    = citesOutside('- Deadlines slip. (Source: what I already know)');
R.coOwnGeneral = citesOutside('(Source: general knowledge)');
R.coOwnMemory  = citesOutside('(Source: from memory)');
R.coOwnExper   = citesOutside('(Source: my own experience)');
R.coNoSource   = citesOutside('(Source: no specific source)');
R.coDontHave   = citesOutside("(Source: I don't have a source for this)");
R.coEmptyTag   = citesOutside('Source:');
R.coPlainProse = citesOutside('Small teams miss deadlines because scope grows.');
R.coMidProse   = citesOutside('I trust my sources: they are careful people.');
R.coNull       = citesOutside(null);
// ── buildDelivery: the stated contradiction ─────────────────────────────
R.footClaims   = buildDelivery({ title: 'T' }, { name: 'A' },
  'Finding. (Source: Harvard Business Review article "Why Small Teams Fail")', []).content;
R.footHonest   = buildDelivery({ title: 'T' }, { name: 'A' },
  'Finding. (Source: what I already know)', []).content;
R.footVisited  = buildDelivery({ title: 'T' }, { name: 'A' },
  'Finding. (Source: hbr.org)\nhttps://hbr.org/x',
  [{ name: 'BROWSER_FETCH', arg: 'https://hbr.org/x' }]).content;
// ── agentFiledPath: did the coworker file it themselves? ────────────────
R.afNone    = agentFiledPath([{ name: 'BROWSER_FETCH', arg: 'https://a.com' }]);
R.afVault   = agentFiledPath([{ name: 'VAULT_NEW', arg: 'Research/topic.md' }]);
R.afAppend  = agentFiledPath([{ name: 'VAULT_APPEND', arg: 'Research/topic.md' }]);
R.afPptx    = agentFiledPath([{ name: 'EXPORT_PPTX', arg: 'Slides/deck.pptx' }]);
R.afImage   = agentFiledPath([{ name: 'GENERATE_IMAGE', arg: 'Images/x.png' }]);
R.afNewest  = agentFiledPath([{ name: 'VAULT_NEW', arg: 'a.md' }, { name: 'VAULT_NEW', arg: 'b.md' }]);
// Private memory is NOT a deliverable — suppressing the host's filing for
// these would lose the boss their artifact entirely.
R.afMemWrite  = agentFiledPath([{ name: 'MEMORY_WRITE', arg: 'prefs/boss.md' }]);
R.afMemAppend = agentFiledPath([{ name: 'MEMORY_APPEND', arg: 'prefs/boss.md' }]);
R.afFileWrite = agentFiledPath([{ name: 'FILE_WRITE', arg: 'src/index.js' }]);
R.afEmptyArg  = agentFiledPath([{ name: 'VAULT_NEW', arg: '   ' }]);
R.afNull      = agentFiledPath(null);
R.afMixed     = agentFiledPath([{ name: 'MEMORY_WRITE', arg: 'p.md' }, { name: 'VAULT_NEW', arg: 'Research/r.md' }]);
// ── officeDate ──────────────────────────────────────────────────────────
// 8:05pm New York on Aug 6 is Aug 7 in UTC. The header must say Aug 6.
R.dateLocal = officeDate(new Date(2026, 7, 6, 20, 5));
R.dateUtcWouldSay = new Date(2026, 7, 6, 20, 5).toISOString().slice(0, 10);
R.datePadded = officeDate(new Date(2026, 0, 3, 9, 0));

// ── officeStamp — same rule, with a clock on it (filed-note headers) ──────
R.stampLocal   = officeStamp(new Date(2026, 7, 6, 20, 5));
R.stampPadded  = officeStamp(new Date(2026, 0, 3, 9, 4));
R.stampMidnight= officeStamp(new Date(2026, 7, 7, 0, 0));
R.stampAgrees  = officeStamp(new Date(2026, 7, 6, 20, 5)).startsWith(officeDate(new Date(2026, 7, 6, 20, 5)));
console.log(JSON.stringify(R));
''')

    # stripToolMarkers — drops machine syntax, keeps prose
    check('drops an ALL_CAPS marker line', out['dropsUpperMarker'] == 'real text')
    check('drops a Mixed_Case marker line', out['dropsMixedCase'] == 'real text',
          repr(out['dropsMixedCase']))
    check('drops a closing marker line', out['dropsClosing'] == 'real text')
    check('drops a bare [ACK] line', out['dropsBareUpper'] == 'real text')
    check('keeps a [x] checkbox line', out['keepsCheckbox'] == '[x]\nreal text')
    check('keeps a lowercase [draft] aside', out['keepsLowerAside'] == '[draft]\nreal text')
    check('keeps a markdown link', out['keepsMdLink'] == '[Text](https://example.com)')
    check('keeps a reference definition', out['keepsRefDef'] == '[1]: https://example.com')
    check('keeps a marker mentioned inside prose',
          out['keepsInlineMention'] == 'use [MEMORY_WRITE: x] to save')
    check('collapses the blank run a dropped line leaves',
          out['collapsesBlanks'] == 'a\n\nb', repr(out['collapsesBlanks']))
    check('marker-only body strips to empty', out['allMarkersEmpty'] == '')

    # extractHtml — only claims html when there IS markup
    check('extracts html from a ```html fence', '<h1>Hi</h1>' in (out['htmlFromFence'] or ''))
    check('extracts html from an unlabelled fence',
          '<body>' in (out['htmlFromBareFence'] or ''))
    check('accepts unfenced markup', '<h1>Hi</h1>' in (out['htmlUnfenced'] or ''))
    check('ignores a prose-only fence', out['htmlSkipsProseFence'] is None)
    check('returns null when there is no markup', out['htmlNullOnProse'] is None)

    # slugify
    check('slugifies a title', out['slug'] == 'first-draft-a-two-sentence-welcome-note',
          out['slug'])
    check('empty title falls back', out['slugEmpty'] == 'delivery')
    check('slug is length-capped', out['slugCapped'] <= 56)
    check('a slug cut mid-word has no dangling hyphen',
          out['slugTrailsClean'] is False, out['slugNoTrailDash'])
    check('…and a run of separators at the cap is cleaned too',
          not out['slugManyDashes'].endswith('-'), out['slugManyDashes'])

    # buildDelivery — routing + shape
    check('brief files to Research/', out['briefHome'].startswith('Research/'))
    check('draft files to Drafts/', out['draftHome'].startswith('Drafts/'))
    check('page with markup files .html',
          out['pageHtml']['path'].endswith('.html') and out['pageHtml']['kind'] == 'page')
    check('page WITHOUT markup falls back to .md',
          out['pageProse']['path'].endswith('.md'), out['pageProse']['path'])
    check('page html is written raw (no md header)',
          not out['pageHtml']['content'].lstrip().startswith('#'))
    check('a plain task files to Deliveries/', out['plainHome'].startswith('Deliveries/'))
    check('empty body files nothing', out['emptyBody'] is None)
    check('marker-only body files nothing', out['markerOnly'] is None)
    check('markdown gets a title + attribution header',
          out['headerHas'].startswith('# My Task') and 'Delivered by Llama' in out['headerHas'])

    # stripToolEcho — the transcript is not the deliverable
    check('removes the whole tool echo, blank lines and all',
          out['echoMultiline'] is False, repr(out['echoGone']))
    check('keeps the prose either side of the echo',
          out['echoGone'] == "I'll look it up.\n\nRed, yellow and blue.", repr(out['echoGone']))
    check('no visits is a no-op', out['echoNoVisits'] == 'just prose')
    check('null/empty echoes are skipped', out['echoNullSafe'] == 'just prose')
    check('removes every occurrence of a repeated echo',
          out['echoTwice'] == 'a\n\nb\n\nc', repr(out['echoTwice']))
    check('an echo that is not present changes nothing',
          out['echoUnmatched'] == 'prose only')
    check('regex metacharacters in the echo are literal, not a pattern',
          out['echoRegexSafe'] == 'a\n\nb', repr(out['echoRegexSafe']))

    # workingNotes — provenance survives, in office words
    check('a fetch reads a source', out['notesWeb'] == ['- Read example.com/x'],
          repr(out['notesWeb']))
    check('a search looks something up',
          out['notesSearch'] == ['- Looked up primary colours'], repr(out['notesSearch']))
    check('a vault visit opens a file',
          out['notesVault'] == ['- Opened Research/notes.md in the cabinet'], repr(out['notesVault']))
    check('an unknown tool still reads as an action',
          out['notesOther'] == ['- Checked thing'], repr(out['notesOther']))
    check('the same source twice is listed once', len(out['notesDedup']) == 1)
    check('an argument-less tool is still recorded, by where it went',
          out['notesArgless'] == ['- at the filing cabinet'], str(out['notesArgless']))
    check('…and does not displace the visits that do have a subject',
          out['notesArglessMix'] == 2, str(out['notesArglessMix']))
    check('a visit with no tool name at all is skipped',
          out['notesNone'] == [] and out['notesNoName'] == [])
    check('an empty-string argument falls back rather than vanishing',
          out['notesNoArg'] == ['- on the phone'], str(out['notesNoArg']))
    check('the footer never names the tool (§6)',
          'BROWSER_FETCH' not in out['notesJargon'] and 'http' not in out['notesJargon'],
          out['notesJargon'])

    # buildDelivery — the memo, with its sources
    check('a delivery with visits gets a Working footer',
          '**Working**' in out['withWorking'] and '- Read a.com' in out['withWorking'],
          out['withWorking'])
    check('the filed note no longer carries the raw tool echo',
          '📡' not in out['withWorking'] and 'Status: 200' not in out['withWorking'])
    check('a body that was ONLY a tool echo files nothing',
          out['echoOnlyBody'] is None, repr(out['echoOnlyBody']))
    # SUPERSEDED 2026-08-07, by evidence rather than taste. This asserted the
    # opposite: no visits meant no Working section. The omission made "this
    # coworker consulted nothing" indistinguishable from "this file predates
    # the footer", and left an absence exactly where a claim needs answering.
    # A real delivery filed "Yellow." followed by an invented
    # "[Vault path: Research/banana-colour.md]" with no Research folder in
    # existence. The office cannot detect that claim — it is prose with no
    # marker — but it CAN state what it actually did, directly beneath it.
    check('a delivery with no visits still says so, in words',
          '**Working**' in out['noWorkingSection']
          and 'Nothing opened, saved or looked up' in out['noWorkingSection'],
          out['noWorkingSection'])

    # citesOutside — a claim of outside sources, never a claim of own head.
    # The asymmetry is deliberate: a miss falls back to the passive footer
    # (the standing mitigation); a false alarm accuses an honest reply, which
    # is the §7 failure the whole feature exists to avoid.
    check('a Source: naming an external work is outside',
          out['coSourceExt'] is True)
    check('a line-leading Source: counts', out['coSourceLine'] is True)
    check('a list-item Source: counts', out['coSourceItem'] is True)
    check('a Sources: header counts', out['coSourcesHdr'] is True)
    check('a URL with no visit behind it is outside', out['coUrl'] is True)
    check('so is a bare www. address', out['coWww'] is True)
    check('one external source among honest ones still counts',
          out['coMixed'] is True)
    check('"(Source: what I already know)" — the brief invites this — is NOT',
          out['coOwnKnow'] is False)
    check('"general knowledge" is not outside', out['coOwnGeneral'] is False)
    check('"from memory" is not outside', out['coOwnMemory'] is False)
    check('"my own experience" is not outside', out['coOwnExper'] is False)
    check('"no specific source" is not outside', out['coNoSource'] is False)
    check('"I don\'t have a source" is not outside', out['coDontHave'] is False)
    check('an empty Source: tag names nothing', out['coEmptyTag'] is False)
    check('plain prose with no attribution is not outside',
          out['coPlainProse'] is False)
    check('"my sources:" mid-sentence is not an attribution line',
          out['coMidProse'] is False)
    check('null is safe and not outside', out['coNull'] is False)

    # buildDelivery — when the record is empty AND the reply names sources,
    # the footer states the contradiction instead of merely making it
    # available (OFFICE_AS_INTERFACE "Known open" — the invented-HBR-article
    # filing of 2026-08-12).
    check('an empty record under claimed sources states the contradiction',
          'Nothing opened, saved or looked up' in out['footClaims']
          and 'recalled, not checked' in out['footClaims'],
          out['footClaims'])
    check('…in observed terms, not an accusation',
          'made' not in out['footClaims'].split('**Working**')[1]
          and 'invent' not in out['footClaims'].split('**Working**')[1],
          out['footClaims'])
    check('an honest own-head attribution gets NO callout',
          'Nothing opened, saved or looked up' in out['footHonest']
          and 'recalled, not checked' not in out['footHonest'],
          out['footHonest'])
    check('a reply with real visits gets NO callout',
          'recalled, not checked' not in out['footVisited']
          and '- Read hbr.org/x' in out['footVisited'],
          out['footVisited'])

    # agentFiledPath — defer to a coworker that filed its own deliverable
    check('an ordinary tool visit is not a filing', out['afNone'] is None)
    check('VAULT_NEW / VAULT_APPEND count',
          out['afVault'] == 'Research/topic.md' and out['afAppend'] == 'Research/topic.md')
    check('the real-file exports count',
          out['afPptx'] == 'Slides/deck.pptx' and out['afImage'] == 'Images/x.png')
    check('the newest write is the deliverable', out['afNewest'] == 'b.md')
    check('PRIVATE memory is not a deliverable — the host must still file',
          out['afMemWrite'] is None and out['afMemAppend'] is None)
    check('a workspace file write is not a cabinet filing', out['afFileWrite'] is None)
    check('an empty path does not suppress host filing', out['afEmptyArg'] is None)
    check('a null visit list is safe', out['afNull'] is None)
    check('a memory write alongside a real filing does not mask it',
          out['afMixed'] == 'Research/r.md')

    # officeDate — the office runs on the boss's clock
    check('the header stamps the LOCAL date', out['dateLocal'] == '2026-08-06',
          out['dateLocal'])
    check('single-digit month/day are padded', out['datePadded'] == '2026-01-03',
          out['datePadded'])
    check('the filed-note stamp is local, with the time',
          out['stampLocal'] == '2026-08-06 20:05', out['stampLocal'])
    check('hours and minutes are padded', out['stampPadded'] == '2026-01-03 09:04',
          out['stampPadded'])
    check('midnight is 00:00, not blank or 24:00',
          out['stampMidnight'] == '2026-08-07 00:00', out['stampMidnight'])
    check('the stamp and the date never disagree about the day',
          out['stampAgrees'] is True)

    if out['dateUtcWouldSay'] != out['dateLocal']:
        check('…where UTC would have said the wrong day',
              out['dateUtcWouldSay'] == '2026-08-07', out['dateUtcWouldSay'])
    else:
        print('  ok    (machine is at/near UTC — no date skew to exercise here)')

    print()
    if FAILS:
        print(f'artifact landing: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('artifact landing: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

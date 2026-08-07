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
// ── officeDate ──────────────────────────────────────────────────────────
// 8:05pm New York on Aug 6 is Aug 7 in UTC. The header must say Aug 6.
R.dateLocal = officeDate(new Date(2026, 7, 6, 20, 5));
R.dateUtcWouldSay = new Date(2026, 7, 6, 20, 5).toISOString().slice(0, 10);
R.datePadded = officeDate(new Date(2026, 0, 3, 9, 0));
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
          out['notesVault'] == ['- Opened Research/notes.md'], repr(out['notesVault']))
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
    check('a delivery with no visits gets no empty Working section',
          '**Working**' not in out['noWorkingSection'])

    # officeDate — the office runs on the boss's clock
    check('the header stamps the LOCAL date', out['dateLocal'] == '2026-08-06',
          out['dateLocal'])
    check('single-digit month/day are padded', out['datePadded'] == '2026-01-03',
          out['datePadded'])
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

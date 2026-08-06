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

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def pure_source():
    """The source minus its import/export lines — the pure half runs as-is."""
    text = SRC.read_text(encoding='utf-8')
    kept = [ln for ln in text.split('\n')
            if not ln.startswith('import ') and not ln.startswith('export ')]
    src = '\n'.join(kept)
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

    print()
    if FAILS:
        print(f'artifact landing: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('artifact landing: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

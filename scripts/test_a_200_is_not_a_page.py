#!/usr/bin/env python3
"""The office said it read a page it could not read, and nobody could turn on search.

One chain, measured end to end on a fresh office on 2026-08-13, with the free
front-desk hire (Llama, tools: ['web']) and nothing else configured.

THE DOOR.  `TOOL_REGISTRY.search.requires()` reads `braveEnabled && braveKey`.
The only controls that set either live in `BraveTab`, in `modals/providers.jsx`
— a file mounted nowhere. So no boss could turn web search on by pressing
anything, and no coworker was ever handed `[SEARCH: query]`. Two siblings in
that same unmounted file, `VaultTab` and `MediaTab`, had already been found and
mounted in earlier passes; this one was left behind, and it was the one gating
the tool the front desk advertises first ("can search the web").

THE SUBSTITUTE.  `BROWSER_FETCH` goes to anyone claiming 'web',
unconditionally. So a coworker asked to search has exactly one thing left to
try, and tries it. Measured, same office, same minute:

    google.com/search?q=…    200 ·  104 chars · "If you're having trouble
                             accessing Google Search, please click here"
    duckduckgo.com/?q=…      200 ·   41 chars · the title, no results
    bing.com/search?q=…      200 ·  631 chars · nav chrome, a few snippets
    en.wikipedia.org/…       200 · 8032 chars · (control — a real page)

THE CLAIM.  The tool returned `Status: 200` above the bot-check notice and the
chat rendered `🌐 Read www.google.com/search?…`. "Read" is an assertion that
reading happened. Llama then wrote three headlines attributed to The Guardian,
CNBC and Forbes, out of a page containing none of them — and the office filed
it `finished ✓` into Done and told the boss "Nothing needs you right now. 🎉".

The invention is the model's and this app cannot prevent it. The claim that a
page was read is the office's own. §4: detection is a hint, not a verdict — and
a status code is a hint about the REQUEST, never a verdict about the page.

THE HEADER.  `meta.failed` already existed for exactly this ("Did it actually
work? Not the same question as 'did it return'") and this tool was not setting
it, so even once the body said "Couldn't read that page", the headline above it
still said "Read" — the shape that mechanism's own note names: "Opened ./site"
directly above "Not a directory: ./site".

Run: python3 scripts/test_a_200_is_not_a_page.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
PROVIDERS = ROOT / 'modals' / 'providers.jsx'
CLIENT = ROOT / 'claude-client.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1600:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def brace_lift(src, header):
    """`header` plus its balanced `{ … }` body, verbatim from the file.

    Anchored on the DECLARATION, never on the expression under test."""
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return src[i:k + 1]


def line_lift(src, header):
    i = src.index(header)
    return src[i:src.index('\n', i)]


# The four pages above, as the shapes /browser/fetch actually hands back.
GOOGLE = {'url': 'https://www.google.com/search?q=four+day+work+weeks&num=10',
          'status': 200, 'title': 'Google Search',
          'text': ("Google Search If you're having trouble accessing Google "
                   "Search, please  click here , or send  feedback .")}
DDG = {'url': 'https://duckduckgo.com/?q=test', 'status': 200,
       'title': 'test at DuckDuckGo', 'text': 'test at DuckDuckGo \n\n \n\n \n\n \n\n DuckDuckGo'}
BING = {'url': 'https://www.bing.com/search?q=test', 'status': 200,
        'title': 'test - Search', 'text': 'x' * 631}
WIKI = {'url': 'https://en.wikipedia.org/wiki/Four-day_week', 'status': 200,
        'title': 'Four-day workweek - Wikipedia', 'text': 'y' * 8032}
JS_SHELL = {'url': 'https://app.example.com/dashboard', 'status': 200,
            'title': 'Dashboard', 'text': 'Loading…'}


def main():
    print('a 200 is not a page, and the search door has to exist')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    rt = RUNTIME.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')
    providers = PROVIDERS.read_text(encoding='utf-8')
    client = CLIENT.read_text(encoding='utf-8')

    # ── 1. barrenPage, run for real ──────────────────────────────────────
    floor = line_lift(rt, 'const READABLE_FLOOR =')
    hosts = line_lift(rt, 'const SEARCH_HOSTS =')
    fn = brace_lift(rt, 'function barrenPage(j, url) {')
    SCOPE = floor + '\n' + hosts + '\n' + fn + '\n'

    def barren(page):
        return run_js(SCOPE + 'console.log(JSON.stringify(barrenPage(%s, %s)));'
                      % (json.dumps(page), json.dumps(page['url'])))

    g, d, b, w, jsx = (barren(GOOGLE), barren(DDG), barren(BING),
                       barren(WIKI), barren(JS_SHELL))

    check('a real page is handed through untouched', w == '',
          f'{w!r} — 8032 characters of Wikipedia is a page; if this fires the '
          'tool has stopped working, which is worse than the bug')
    check('a search page with a few real snippets is left alone', b == '',
          f'{b!r} — 631 characters measured off bing.com; the floor exists to '
          'catch nothing-at-all, not short-but-real')
    check('google’s bot check is not reported as a page', g != '', g)
    check('duckduckgo’s empty shell is not either', d != '', d)
    check('a JavaScript shell is not reported as a page', jsx != '', jsx)

    check('the search-engine case says so, rather than guessing',
          'search engine' in g and 'search engine' in d,
          f'{g!r} — the host settles this one, so §7 wants the real cause')
    check('...and carries the way out with it',
          'Settings' in g and 'Connections' in g,
          f'{g!r} — a boss reading this needs to know search is a thing they '
          'can turn on')
    check('the generic case does NOT invent a search engine',
          'search engine' not in jsx,
          f'{jsx!r} — app.example.com is not Google; a confident wrong cause '
          'is worse than a vague honest one')

    # The number in the sentence has to be the number it counted, not a
    # number it liked the look of — that count is the only part of the
    # message that is measurement rather than inference.
    for label, page, s in (('google', GOOGLE, g), ('js shell', JS_SHELL, jsx)):
        n = len(re.sub(r'\s+', ' ', page['text']).strip())
        check(f'it reports what it actually counted ({label})',
              re.search(r'\b%d\b' % n, s),
              f'{s!r} — expected the character count {n}')
    for label, s in (('google', g), ('duckduckgo', d), ('js shell', jsx)):
        check(f'...and tells the model not to quote it ({label})',
              'quote' in s and 'cite' in s,
              f'{s!r} — this string IS the [TOOL_RESULT] the model reads next; '
              'it is the only thing standing between an empty page and a '
              'fabricated citation')

    # ── 2. the tool marks the trip as failed ─────────────────────────────
    # Real run(), stubbed transport: the claim is about meta.failed, which is
    # what picks the visit header's verb and icon.
    run_src = brace_lift(rt, "run: async (url, { signal, meta }) => {")
    run_src = 'const runFetch = ' + run_src[len('run: '):]

    def call(page, err=None):
        payload = dict(page)
        if err:
            payload = {'url': page['url'], 'status': page['status'],
                       'error': err, 'text': '', 'title': ''}
        return run_js(
            SCOPE
            + 'globalThis.fetch = async () => ({ json: async () => (%s) });\n'
            % json.dumps(payload)
            + run_src + ';\n'
            + 'const meta = {};\n'
            + 'const out = await runFetch(%s, { signal: null, meta });\n'
            % json.dumps(page['url'])
            + 'console.log(JSON.stringify({ out, failed: !!meta.failed }));')

    ok, blocked, errored = call(WIKI), call(GOOGLE), call(WIKI, 'HTTP 404: Not Found')

    check('a page that was read is not marked failed', ok['failed'] is False,
          ok)
    check('...and comes back with the page in it', 'Status: 200' in ok['out'],
          ok['out'][:120])
    check('a page that could not be read IS marked failed',
          blocked['failed'] is True,
          f'{blocked} — without this the visit header keeps the success verb '
          'and the boss reads "🌐 Read <url>" directly above "Couldn\'t read '
          'that page"')
    check('...and an outright error is too', errored['failed'] is True,
          errored)
    check('both failures speak in the same sentence',
          blocked['out'].startswith("Couldn't read that page — ")
          and errored['out'].startswith("Couldn't read that page — "),
          {'blocked': blocked['out'][:60], 'errored': errored['out'][:60]})
    check('a page with no body is never presented as one',
          '(no body)' not in rt,
          'the old fallback printed a header, a status line and "(no body)" '
          'and called that a result')

    # ── 3. the door that was mounted nowhere ─────────────────────────────
    check('BraveTab is exported', re.search(r'export function BraveTab', providers),
          'unexported it can only be used inside the one file nothing mounts')
    check('...and reads the settings store itself, like its siblings',
          re.search(r'export function BraveTab\(\)\s*\{\s*\n?\s*const \[s, update\] = useSettingsStore\(\);',
                    providers),
          'taking `s`/`update` as props is what tied it to the unmounted '
          'component; Settings has no such store to hand down, and a snapshot '
          'passed as a prop toggles without re-rendering')
    check('...with no caller still passing the old props',
          not re.search(r'<BraveTab\s+s=', providers), 'stale call site')
    check('Settings imports it', re.search(r'import \{ BraveTab \}', settings),
          'the whole defect: the panel existed and nothing mounted it')
    check('...and mounts it where a boss can reach it',
          re.search(r'<BraveTab />', settings),
          'imported but not rendered is the same dead end with an extra step')
    check('Connections is where it lands, next to the other rescued panel',
          settings.index('<BraveTab />') < settings.index('<VaultTab />')
          or abs(settings.index('<BraveTab />') - settings.index('<VaultTab />')) < 200,
          'this is a key the boss supplies — the same argument that makes '
          'CONNECTIONS self-hosted-only')

    check('the settings search can find it',
          re.search(r"tab:'connections', label:'Web search'", settings),
          "a boss looking for this types \"search\"; before this entry the "
          'settings search answered nothing')

    # ── 4. the signpost that pointed at a tab that does not exist ────────
    # There is no API tab. SETTINGS_TABS is account · connections · agents ·
    # icp-services · media · appearance, and has been since managed premium
    # pulled the self-host setup surface out of Settings. Six strings across
    # four files were still sending the boss to `Settings → API`, one of them
    # to a `→ Tools` drawer inside it. Comments are stripped first: the
    # comments *above* those lines quote the dead path on purpose, to record
    # why it was there. It is the strings a boss reads that must not.
    tabs = re.search(r'const SETTINGS_TABS = \[(.*?)\n\];', settings, re.S).group(1)
    ids = set(re.findall(r"id: '([a-z-]+)'", tabs))
    check('there is still no API tab, so nothing may name one', 'api' not in ids,
          f'{sorted(ids)} — if an API tab is ever added back, this test is '
          'the wrong one to satisfy: point the signposts at it instead')

    def strip_comments(src):
        src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
        return re.sub(r'(?m)^\s*//.*$', '', src)

    onboard = (ROOT / 'ui' / 'onboarding.jsx').read_text(encoding='utf-8')
    for name, src in (('claude-client.jsx', client), ('hq-runtime.jsx', rt),
                      ('ui/onboarding.jsx', onboard)):
        hits = re.findall(r'Settings → API[^\'"`)]*', strip_comments(src))
        check(f'no live string sends the boss to the API tab ({name})',
              not hits, hits)

    check('the search key error names a tab that is really there',
          re.search(r'open Settings → Connections', client),
          'the tab BraveTab is now mounted in')
    # Was pinned to the whole sentence — "aren't wired up — check Settings →
    # Roster" — which made it a hostage to the wording as well as the
    # destination, and it went red the day that sentence was rewritten for
    # §6 (the raw tool names and "wired up" both went). The destination is
    # what this check is named for and all it should hold: both branches of
    # the hint, the one that can name the box and the one that can't, still
    # send the boss to the tab where tools are ticked.
    reached = re.findall(r'reached for[^\n]{0,220}?Settings → Roster', rt)
    check('the unwired-tools hint points at where tools are ticked',
          len(reached) >= 4,
          f'{len(reached)} of the hint branches name Roster — which tools a '
          'coworker gets is a per-agent question, and ROSTER is the '
          'per-agent tab')
    check('onboarding names no tab at all',
          re.search(r'change it anytime in Settings\.', onboard),
          'this line is read on managed containers too, and CONNECTIONS — '
          'the tab that would be right for a self-hoster — is filtered out '
          'of the nav there; a destination that exists for half the readers '
          'is the §5 problem, not the fix for it')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

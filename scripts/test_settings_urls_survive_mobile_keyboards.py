#!/usr/bin/env python3
"""Settings -> Connections/Media never got the mobile-keyboard URL/token
protection a *different* Settings page already had.

2026-07-22's fix ("settings: prevent mobile keyboards from mangling
URL/token fields") added autocapitalize="off"/autocorrect="off" to four
fields on frontend/src/routes/hq/settings/+page.svelte — the Fleet/
Workspaces API settings page for the cafreso-pages/fleet dashboard — plus
a save-time scheme normalizer, after a live repro on iOS: Safari's
on-screen keyboard auto-capitalizes the first character typed into a
plain text field even with autocapitalize honored inconsistently across
versions, silently turning "https://" into "Https://". The field looks
identical; the fetch just stops resolving, with zero visible sign
anything is wrong.

That fix never touched modals/providers.jsx — the Settings modal every
CafresoHQ boss actually opens (Connections/Media tabs), which is mobile-
supported in its own right (see test_vault_mobile_tabbar_clearance.py,
test_team_mobile_tabbar_clearance.py, etc. — this same modal system has
several dedicated mobile-layout regression tests already). Confirmed live
against a fresh dev office (127.0.0.1:8910): before this fix, EVERY
URL/token field rendered in Settings -> Connections/Media (Anthropic key,
Google key, Brave key, Library folder, Obsidian REST URL, Obsidian REST
key, and Media's local-provider base URL/key fields) had NO
autocapitalize/autocorrect/autocomplete/spellcheck attributes at all —
`getAttribute('autocapitalize')` etc. all returned null on the live DOM.
A boss on a phone typing "https://127.0.0.1:27124" into LIBRARY -> OBSIDIAN
REST -> REST URL, or any local-provider base URL in Settings -> Media,
was exposed to the exact same silent failure the other page was fixed for.

Fix: a shared `NO_MANGLE_PROPS` spread
(autoCapitalize/autoCorrect/autoComplete: 'off', spellCheck: false) applied
to every affected field — VaultTab's LIBRARY FOLDER / REST URL / REST API
KEY, MediaTab's local-provider BASE URL (image + video) and MediaKeyRow's
API KEY, BrowserKeysTab's Anthropic/Google API KEY, and BraveTab's API
KEY — plus a `normalizeUrlScheme(v)` helper (identical contract to the
2026-07-22 fix: lowercase an anchored `http(s)://` scheme, touch nothing
else) applied at the three points that actually persist a URL value:
VaultTab's `saveRest()` (draftUrl, at its explicit SAVE button) and
MediaTab's two local-provider BASE URL `onChange` handlers (no separate
save step there, so it runs inline — safe because it only replaces a
same-length case-insensitive prefix, never repositioning the cursor).
Token/key fields and the LIBRARY FOLDER path are never passed through the
normalizer — only NO_MANGLE_PROPS, matching the original fix's "token
values are never touched" rule.

Live-verified round-trip: typed "Https://127.0.0.1:27124" into REST URL,
pressed SAVE, and the field read back "https://127.0.0.1:27124" from the
server after refresh(). Typed "Http://127.0.0.1:7860" into Media's a1111
BASE URL and it read "http://127.0.0.1:7860" immediately (no separate
save step on that field).

Run: python3 scripts/test_settings_urls_survive_mobile_keyboards.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ROOT / 'modals' / 'providers.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_function(src, name):
    """Brace-balanced extraction of `function <name>(...) { ... }` — the
    real source text, not a re-implemented copy."""
    marker = 'function ' + name + '('
    start = src.index(marker)
    brace = src.index('{', start)
    depth = 0
    i = brace
    while i < len(src):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise ValueError('unbalanced braces for ' + name)


def find_input_tag(src, marker):
    """The full `<input ... />` tag text surrounding a unique marker
    string inside it (placeholder/value expression), found by scanning
    outward from the marker rather than assuming a fixed line range."""
    idx = src.index(marker)
    start = src.rfind('<input', 0, idx)
    end = src.index('/>', idx)
    if start == -1 or end == -1:
        raise ValueError('could not bound <input ... /> around: ' + marker)
    return src[start:end + 2]


def main():
    print('Settings URL/token fields survive mobile-keyboard auto-capitalize')
    src = PROVIDERS.read_text(encoding='utf-8')

    # ── the shared props object exists with the right shape ─────────────
    m = re.search(r'const NO_MANGLE_PROPS = \{([^}]*)\};', src)
    check('NO_MANGLE_PROPS is defined', m is not None)
    props_body = m.group(1) if m else ''
    for pair in ("autoCapitalize: 'off'", "autoCorrect: 'off'",
                 "autoComplete: 'off'", 'spellCheck: false'):
        check(f'NO_MANGLE_PROPS sets {pair}', pair in props_body)

    # ── every affected field actually spreads it ─────────────────────────
    FIELDS = [
        ('VaultTab LIBRARY FOLDER (local path)',
         "'C:/Users/you/Documents/cafresohq/hq-state/vault'"),
        ('VaultTab REST URL', 'placeholder="https://127.0.0.1:27124"'),
        ('VaultTab REST API KEY',
         "'paste from Obsidian → Local REST API settings'"),
        ('MediaTab image BASE URL', 'value={s[imgMeta.urlField] || \'\'}'),
        ('MediaTab video BASE URL', 'value={s[vidMeta.urlField] || \'\'}'),
        ('MediaKeyRow API KEY',
         "has ? '•••• (saved — type to replace)' : meta.ph"),
        ('BrowserKeysTab API KEY', 'value={s[r.keyField] || \'\'}'),
        ('BraveTab API KEY', 'placeholder="BSA-…"'),
    ]
    tags = {}
    for label, marker in FIELDS:
        try:
            tag = find_input_tag(src, marker)
        except ValueError as e:
            check(f'{label}: <input> tag locatable', False, str(e))
            continue
        tags[label] = tag
        check(f'{label}: spreads {{...NO_MANGLE_PROPS}}',
              '{...NO_MANGLE_PROPS}' in tag)

    # ── the scheme normalizer itself: real source, run for real under Node
    try:
        fn_src = extract_function(src, 'normalizeUrlScheme')
    except ValueError as e:
        check('normalizeUrlScheme extracts cleanly', False, str(e))
        fn_src = None
    check('normalizeUrlScheme is defined', fn_src is not None)

    if fn_src and shutil.which('node'):
        cases = [
            'Https://127.0.0.1:27124',
            'HTTPS://Example.com/Path',
            'http://already-lowercase.test',
            'HTTP://',
            '',
            None,
            'ftp://not-http.test',
            'not a url at all',
            'httpsX://looks-close-but-isnt.test',
            'redirect=Https://mid-string.test',
        ]
        js = fn_src + '\n' + (
            'const cases = ' + json.dumps(cases) + ';\n'
            'console.log(JSON.stringify(cases.map(normalizeUrlScheme)));\n'
        )
        p = subprocess.run(['node', '--input-type=module', '-e', js],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
        check('lifted normalizeUrlScheme runs under Node', p.returncode == 0,
              p.stderr.strip()[:300])
        if p.returncode == 0:
            out = json.loads(p.stdout.strip().split('\n')[-1])
            expected = [
                'https://127.0.0.1:27124',
                'https://Example.com/Path',
                'http://already-lowercase.test',
                'http://',
                '',
                '',
                'ftp://not-http.test',
                'not a url at all',
                'httpsX://looks-close-but-isnt.test',
                'redirect=Https://mid-string.test',
            ]
            check('mangled https scheme is lowercased, rest of the URL untouched',
                  out[0] == expected[0], out[0])
            check('mangled HTTPS (all-caps) scheme is lowercased, path case kept',
                  out[1] == expected[1], out[1])
            check('an already-correct URL is left byte-identical',
                  out[2] == expected[2], out[2])
            check('a bare mangled scheme with nothing after it still normalizes',
                  out[3] == expected[3], out[3])
            check('empty string in, empty string out', out[4] == expected[4], out[4])
            check('null/undefined never throws — falsy guard holds', out[5] == expected[5], out[5])
            check('a non-http(s) scheme (ftp) is never touched', out[6] == expected[6], out[6])
            check('plain text with no scheme is never touched', out[7] == expected[7], out[7])
            check("a near-miss scheme ('httpsX://') is never mistaken for https",
                  out[8] == expected[8], out[8])
            # The regex is anchored (`^`) — this only matters for a value
            # that ISN'T scheme-first, e.g. a mangled scheme sitting mid-string
            # after other text. Dropping the anchor entirely escaped every
            # other case above (none of them has real scheme text after
            # position 0), so this is the one case load-bearing for `^`.
            check("a mangled scheme buried mid-string (not at position 0) "
                  "is left untouched — the normalizer only ever looks at "
                  "the start of the value, not anywhere inside it",
                  out[9] == expected[9], out[9])
    elif not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')

    # ── the normalizer is wired at exactly the three real persist points,
    #    and nowhere near a token/key/path field ────────────────────────
    total_calls = len(re.findall(r'normalizeUrlScheme\(', src))
    check('normalizeUrlScheme is called at exactly 3 sites '
          '(saveRest, image BASE URL, video BASE URL) — one definition, '
          'three uses, never wired onto a key/path field',
          total_calls == 1 + 3, total_calls)
    check('saveRest() normalizes draftUrl before persisting it',
          'restUrl: normalizeUrlScheme(draftUrl.trim())' in src)
    check('MediaTab image BASE URL onChange normalizes before storing',
          'update({ [imgMeta.urlField]: normalizeUrlScheme(e.target.value) })' in src)
    check('MediaTab video BASE URL onChange normalizes before storing',
          'update({ [vidMeta.urlField]: normalizeUrlScheme(e.target.value) })' in src)

    # ── negative checks: token/secret values are never run through the
    #    scheme normalizer (case-sensitive secrets must survive untouched)
    for label, tag in tags.items():
        if 'KEY' in label.upper():
            check(f'{label}: value is never passed through normalizeUrlScheme',
                  'normalizeUrlScheme(' not in tag)
    check('LIBRARY FOLDER (a filesystem path, not a URL) is never normalized',
          'normalizeUrlScheme(' not in tags.get('VaultTab LIBRARY FOLDER (local path)', ''))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

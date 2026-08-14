#!/usr/bin/env python3
"""The office told the boss where to go, and the room was empty.

Measured on a fresh office on 2026-08-13, manual hire form, nothing configured.

`localModelOptions()` appends "Anthropic (Claude API · credits)" and "Google
(Gemini API · credits)" to EVERY brain picker on EVERY install. The manual
hire form's default brain is `anthropic:claude-haiku-4-5-20251001`. It
correctly works out that the brain is not signed in, and says so:

    ⚠ this brain isn't signed in yet — they can be hired, but can't work
      until you add it in Settings → Connections

Followed that instruction as a boss would. Settings → Connections held four
panels — ON THIS MACHINE, CLOUD KEYS, BRAVE WEB SEARCH, MARKDOWN VAULT — and
one password field, for Brave. No Anthropic. No Google. The only inputs that
have ever written `anthropicKey` or `googleKey` were inside `ApiTab`, in
`modals/providers.jsx`, which nothing imports.

So the warning was right, the destination existed, and the boss still could
not act on it: hire anyway, drop a task, and `streamAnthropic` throws "No
Anthropic API key — open Settings → Connections", which is the same sentence
pointing at the same empty room. §7 says a failure is one honest sentence
PLUS a way forward. A way forward that returns to the message is a circle.

Both panels were gated on `s.provider === 'anthropic' | 'google'`, and the
only control that writes `s.provider` is a `<select>` in that same unmounted
component — so it has sat at its default of 'hermes' since the tab was
removed, and those two panels were dead twice over. The gate is also the
wrong question now: `parseModelId` lets any coworker pin `anthropic:…`
regardless of the global provider, which is how brains are actually chosen.

The last check here is the general one: every key that `hasUsableKey` reads
to decide "is this brain signed in" must have a control somewhere Settings
actually mounts. That is the rule this whole class of bug breaks, and it
should fail for the next orphan without anyone writing a new test.

Run: python3 scripts/test_the_room_the_warning_names.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ROOT / 'modals' / 'providers.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
CLIENT = ROOT / 'claude-client.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    """`header` plus its brace-balanced body, verbatim."""
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def main():
    print('the room the warning names has to have the thing in it')
    providers = PROVIDERS.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')
    client = CLIENT.read_text(encoding='utf-8')
    hire = HIRE.read_text(encoding='utf-8')

    # ── 1. the panel exists, is exported, and is self-sufficient ─────────
    check('BrowserKeysTab is exported',
          re.search(r'export function BrowserKeysTab', providers),
          'unexported it can only be used inside the file nothing mounts')
    # Checked BEFORE the lift, and the lift is anchored on the no-props
    # signature: written the other way round, putting the props back made
    # brace_lift raise and the whole run died with a traceback instead of a
    # named failure. A test that crashes is not a test that reports.
    noprops = 'export function BrowserKeysTab() {' in providers
    check('...and takes no props', noprops,
          'the `s`/`update` pair is exactly what tied the old panels to the '
          'one component that holds the store; Settings has no such store to '
          'hand down, and a snapshot passed as a prop never re-renders')
    tab = brace_lift(providers, 'export function BrowserKeysTab() {') if noprops else ''
    check('...reading the store itself, like the three rescued before it',
          'useSettingsStore()' in tab, tab[:120])

    # ── 2. it is not gated on a toggle nothing can set ───────────────────
    # Comments stripped: the note on the component explains what `s.provider`
    # used to gate and why it no longer should, which is worth keeping and is
    # not a gate. Same trap as the signpost check in the tick before this one.
    code = re.sub(r'/\*.*?\*/', '', tab, flags=re.S)
    code = re.sub(r'(?m)^\s*//.*$', '', code)
    check('the panel is NOT gated on s.provider',
          "s.provider" not in code,
          "the only writer of s.provider is a <select> inside the unmounted "
          "ApiTab, so the gate has been stuck at 'hermes' for as long as the "
          'tab has been gone — and per-agent brains pin their provider in the '
          'model id anyway')
    picker = brace_lift(providers, 'function ApiTab() {')
    check('...and ApiTab keeps no second copy to drift from',
          picker.count('anthropicKey') == 0 and picker.count('googleKey') == 0,
          'ApiTab renders <BrowserKeysTab /> now; two copies of an unmounted '
          'panel is most of how this got here')

    # ── 3. Settings mounts it ────────────────────────────────────────────
    check('Settings imports it',
          re.search(r'import \{ BrowserKeysTab \}', settings), 'the whole bug')
    check('...and renders it', re.search(r'<BrowserKeysTab />', settings),
          'imported but not rendered is the same dead end with a longer path')
    check('...in Connections, with the other key panels',
          settings.index('<BrowserKeysTab />') > settings.index('CLOUD KEYS')
          and settings.index('<BrowserKeysTab />') < settings.index('<VaultTab />'),
          'a boss arriving from a hire warning is looking for a key field, '
          'not for which of two key panels is theirs')

    # ── 4. both fields, and both are writers ─────────────────────────────
    for field, ph in (('anthropicKey', 'sk-ant-'), ('googleKey', 'AIza')):
        check(f'{field} has an input that writes it',
              re.search(r'\[r\.keyField\]: e\.target\.value', tab)
              and f"keyField: '{field}'" in tab,
              tab[:200])
        check(f'...with the {ph}… placeholder a boss recognises',
              ph in tab, f'no {ph} placeholder')
    # The data AND the markup that renders it. Checking only the `where`/
    # `link` fields passes with the whole hint deleted — the first version of
    # this check did exactly that, and the fire test caught it: the strings
    # sat in the rows array feeding nothing.
    for host in ('console.anthropic.com', 'aistudio.google.com'):
        check(f'a key source is listed ({host.split(".")[1]})',
              tab.count(host) == 2 and f'https://{host}' in tab,
              f'{tab.count(host)} occurrences of {host}; want the visible '
              'label and the href')
    check('...and the row actually renders it',
          re.search(r'<a href=\{r\.link\}[^>]*>\{r\.where\}</a>', tab),
          '"add it in Settings" is half an instruction if you have no key '
          'yet, and a link nothing renders is no instruction at all')
    check('and says the key stays in the browser',
          'stays in this browser' in tab,
          'this is the fact that makes a form here legitimate at all, where '
          'CLOUD KEYS deliberately refuses one — these two go straight from '
          'the tab to the vendor and never touch the Cafreso server')

    # ── 5. the settings search finds it by brand ─────────────────────────
    for brand, kw in (('claude', 'sk-ant'), ('gemini', 'aiza')):
        check(f'searching for "{brand}" reaches the panel',
              any(brand in e and kw in e for e in
                  re.findall(r"tab:'connections'[^}]*kw:'([^']*)'", settings)),
              f'a boss sent here by a hire warning searches the brand on the '
              f'brain they picked, not a category name; {kw} too, because '
              'pasting the key into the search box is a real thing people do')

    # ── 6. the general rule this class of bug breaks ─────────────────────
    # Every browser-side key that `hasUsableKey` consults to decide "is this
    # brain signed in" must have a writer in a panel Settings actually mounts.
    # This is the check that should catch the NEXT orphan unassisted.
    usable = brace_lift(client, 'function hasUsableKey(s) {')
    read_keys = set(re.findall(r's\.(\w+Key)\b', usable))
    check('hasUsableKey still reads the keys this test knows about',
          {'anthropicKey', 'googleKey'} <= read_keys,
          f'{sorted(read_keys)} — if these moved, re-derive the rule below '
          'rather than deleting it')

    mounted = set(re.findall(r'<(\w+)\s*/>', settings))
    bodies = settings
    for comp in sorted(mounted):
        if re.search(r'export function %s\(' % comp, providers):
            bodies += brace_lift(providers, 'export function %s() {' % comp)

    # openrouterKey is set server-side by design — CLOUD KEYS names the env
    # var instead of taking the secret in the browser, and that panel says so.
    BY_ENV_VAR = {'openrouterKey', 'groqKey', 'geminiKey'}
    for key in sorted(read_keys - BY_ENV_VAR):
        check(f'{key} can be set from a panel Settings mounts',
              re.search(r'\b%s\b' % key, bodies)
              or re.search(r"keyField: '%s'" % key, bodies),
              f'`hasUsableKey` reads {key} to tell a boss their brain is not '
              'signed in, and nothing Settings mounts can write it — which is '
              'the exact shape of the bug this test was written for')

    # ── 7. the sentence that started it still names that room ────────────
    check('the hire warning still points at Connections',
          re.search(r"add it in Settings → Connections", hire),
          'if this moves, move the panel with it')
    check('...and the throws agree with it',
          client.count('open Settings → Connections') >= 3,
          'streamAnthropic, streamGoogle and streamOpenAICompat all end up '
          'in the same room now')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

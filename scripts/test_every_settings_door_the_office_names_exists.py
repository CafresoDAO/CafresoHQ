#!/usr/bin/env python3
"""The office sent a brand-new boss to "Settings → Keys". There is no Keys tab.

`app/cast.jsx`'s `routeOut` is the last rung of the failure ladder — the
sentence that fires when a coworker's brain can't be reached and there is
nobody else to hand the work to. On a genuine first run (no agents hired,
no brain configured) it was the boss's answer to their very first message:

    ⚠ Couldn't reach that brain — it looks offline from here. Nobody's
      hired yet — hire someone on the Team tab, or add your own AI key
      in Settings → Keys.

The boss opens Settings and finds six tabs — ACCOUNT, CONNECTIONS, ROSTER,
MODULES, MEDIA, APPEARANCE. No Keys. `keys` survives only as a deep-link
alias in `SETTINGS_TAB_ALIAS`, under a comment naming it exactly what it
is: "old/removed id → canonical id". The one sentence written to stop a
first-run dead end was itself a dead end.

Two siblings had the same defect: `claude-client.jsx`'s CLI-install
timeout said "Settings → Code Agents" (the old `agentcli` tab) and
`views/terminal.jsx`'s Hermes hint said "Settings → System" (the old
`system` tab). All three now say Connections, which is where the cloud
keys, the Hermes model selector, and the on-this-machine CLI panel all
actually render (providers.jsx → BrowserKeysTab → ConnectionsPanel,
gated on activeTab === 'connections').

Rather than pin three more hand-written strings, this test derives the
truth from the nav itself: every user-facing "Settings → X" in the
codebase must name a tab that a boss can actually see, and must NOT name
one of the removed ids that only survive as deep-link aliases. A future
tab rename now breaks this test instead of silently stranding the copy.

Run: python3 scripts/test_every_settings_door_the_office_names_exists.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'modals' / 'settings.jsx'
FAILS = []

# Files whose "Settings → X" strings reach a boss's eyes. Everything the
# office says out loud, plus the two client/view surfaces that throw or
# render their own hints.
SURFACES = [
    'app.jsx', 'app/cast.jsx', 'claude-client.jsx', 'hq-runtime.jsx',
    'missions.jsx', 'modals/hire.jsx', 'modals/providers.jsx',
    'modals/settings.jsx', 'modals/starter.jsx',
    'views/terminal.jsx', 'views/projects.jsx',
]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def norm(s):
    """'ICP Services' / 'icp-services' / 'CODE AGENTS' → 'icpservices' etc."""
    return re.sub(r'[^a-z]', '', s.lower())


def strip_comments(src):
    """Blank out /* … */ and // … so the sweep reads CODE, not commentary.

    Comments legitimately quote the old door names while explaining why they
    were wrong — this very fix's comments do — and a sweep that can't tell
    the two apart would flag its own explanation. Replaces comment bodies
    with spaces rather than deleting them, so line numbers still line up
    with the real file for the offender report.
    """
    out = list(src)
    i, n = 0, len(src)
    quote = None
    while i < n:
        ch = src[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in '"\'`':
            quote = ch
            i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != '\n':
                    out[k] = ' '
            i = j
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = ' '
            i = j
            continue
        i += 1
    return ''.join(out)


def main():
    print('every Settings door the office names is a door that exists')
    settings_src = SETTINGS.read_text(encoding='utf-8')

    # ── Derive the real nav from SETTINGS_TABS, not from a hardcoded list ──
    tabs_block = re.search(r'const SETTINGS_TABS = \[(.*?)\n\];',
                           settings_src, re.S)
    check('SETTINGS_TABS is still a parseable literal (this test derives the '
          'valid door names from it — if its shape changed, the derivation '
          'below is no longer trustworthy)', tabs_block is not None)
    if not tabs_block:
        print('\n1 FAILED — cannot derive the nav')
        return 1

    tab_ids = re.findall(r"id:\s*'([^']+)'", tabs_block.group(1))
    tab_labels = re.findall(r"label:\s*'([^']+)'", tabs_block.group(1))
    check('the derived nav has one label per tab and is non-empty',
          len(tab_ids) == len(tab_labels) and len(tab_ids) >= 5,
          (tab_ids, tab_labels))

    real = {norm(x) for x in tab_ids + tab_labels}
    print('        nav on screen: ' + ' · '.join(tab_labels))

    # ── Derive the REMOVED ids that survive only as deep-link aliases ─────
    alias_block = re.search(r'const SETTINGS_TAB_ALIAS = \{(.*?)\};',
                            settings_src, re.S)
    check('SETTINGS_TAB_ALIAS is still a parseable literal', alias_block is not None)
    alias_keys = re.findall(r"(\w+):\s*'", alias_block.group(1)) if alias_block else []
    # A removed id is one that is aliased and is NOT itself a live tab.
    removed = {norm(k) for k in alias_keys} - real
    check('at least one removed-tab id is known (keys/system/agentcli) — if '
          'this is empty the alias map changed shape and the guard below '
          'would silently pass on anything', bool(removed), alias_keys)
    print('        removed ids (deep-link only): ' + ', '.join(sorted(removed)))

    # Human spellings of removed tabs that no longer appear as ids — the copy
    # said "Code Agents", the alias key is `agentcli`. Normalization can't
    # bridge that, so name it explicitly.
    removed_spellings = {'codeagents'} | removed

    # ── Sweep every user-facing "Settings → X" ───────────────────────────
    offenders = []
    unknown = []
    total = 0
    for rel in SURFACES:
        p = ROOT / rel
        if not p.exists():
            continue
        code = strip_comments(p.read_text(encoding='utf-8'))
        for i, line in enumerate(code.splitlines(), 1):
            for m in re.finditer(r'Settings → ([A-Za-z][A-Za-z ]*)', line):
                # First segment only: "Settings → Connections → MARKDOWN VAULT"
                # is a valid door plus a sub-panel.
                seg = m.group(1).strip()
                seg = re.split(r'\s{2,}', seg)[0].strip()
                if not seg:
                    continue
                total += 1
                n = norm(seg)
                # Trailing prose bleeds into the capture ("Roster does not
                # have a box"); accept any prefix that resolves to a tab.
                words = seg.split()
                resolved = None
                for take in range(len(words), 0, -1):
                    cand = norm(' '.join(words[:take]))
                    if cand in real:
                        resolved = cand
                        break
                    if cand in removed_spellings:
                        resolved = '!' + cand
                        break
                if resolved is None:
                    unknown.append(f'{rel}:{i} → {seg!r}')
                elif resolved.startswith('!'):
                    offenders.append(f'{rel}:{i} → "Settings → {seg}"')

    check('the sweep actually found Settings-door strings to check (a regex '
          'that matches nothing would pass vacuously)', total >= 20, total)

    check('no user-facing sentence sends the boss to a REMOVED Settings tab '
          '— this is the actual regression: "Settings → Keys" fired on the '
          'emptiest possible office (first run, nobody hired, no brain) and '
          'named a door that had been taken off the wall',
          not offenders, '\n          ' + '\n          '.join(offenders))

    check('every Settings door named resolves to a tab in SETTINGS_TABS '
          '(an unrecognized name is either a new typo or a nav change this '
          'test needs to learn about)',
          not unknown, '\n          ' + '\n          '.join(unknown))

    # ── The specific first-run sentence, pinned ──────────────────────────
    cast_src = (ROOT / 'app' / 'cast.jsx').read_text(encoding='utf-8')
    brain = re.search(r"const BRAIN = '([^']+)';", cast_src)
    check("routeOut's BRAIN sentence — the one a first-run boss reads — "
          'names Connections', brain is not None and 'Connections' in brain.group(1),
          brain.group(1) if brain else 'BRAIN const not found')
    check('...and no longer names Keys',
          brain is not None and 'Keys' not in brain.group(1),
          brain.group(1) if brain else '')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:4]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

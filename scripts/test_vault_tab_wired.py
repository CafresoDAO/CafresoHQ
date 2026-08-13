#!/usr/bin/env python3
"""VaultTab existed, fully built, and was completely unreachable.

modals/providers.jsx has a real, finished VaultTab component: storage
toggle (local dir / Obsidian REST), DETECT OBSIDIAN auto-discovery, save
paths for both backends. It's the only in-app caller of the real,
server-backed CafresoHQClient.vaultConfigure()/vaultDiscover() methods.
But nothing ever imported it — confirmed both by grep (zero real `import`
sites anywhere, one stray comment mention in views/vault.jsx) and at the
compiled level (rebuilt via scripts/build_ui_bundle.mjs, grepped the
output bundle for the unique string "DETECT OBSIDIAN", zero matches —
esbuild's import-graph-following never even compiled the file in). The
only way to point CafresoHQ at an existing Obsidian vault, switch to the
REST backend, or move the vault root was the CAFRESOHQ_VAULT /
CAFRESOHQ_VAULT_BACKEND env vars, set before the process starts —
invisible to a normal boss clicking around Settings.

Two-part fix, since the component itself was also never exported:
  1. modals/providers.jsx: `function VaultTab()` -> `export function VaultTab()`
  2. modals/settings.jsx: import it and mount <VaultTab /> as a third panel
     inside ConnectionsPanel (Settings -> Connections), alongside the real
     "ON THIS MACHINE" / "CLOUD KEYS" panels it was written to sit next to.

Verified live: rebuilt bundle now contains "DETECT OBSIDIAN"; drove
Settings -> Connections in a throwaway office and the MARKDOWN VAULT panel
rendered with a working Storage toggle and a DETECT OBSIDIAN button that
made a real backend call and found an actual local Obsidian vault.

Run: python3 scripts/test_vault_tab_wired.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ROOT / 'modals' / 'providers.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


providers_src = PROVIDERS.read_text()
settings_src = SETTINGS.read_text()

# 1. VaultTab must actually be exported, not just defined.
check(
    re.search(r'^export function VaultTab\s*\(', providers_src, re.M),
    "modals/providers.jsx: VaultTab must be declared `export function VaultTab()` "
    "— without `export`, esbuild treats the import as undefined and drops the "
    "component from the bundle entirely (silent, no build error).",
)
check(
    not re.search(r'^function VaultTab\s*\(', providers_src, re.M),
    "modals/providers.jsx: found a non-exported `function VaultTab(` — "
    "there must be exactly one declaration and it must be exported.",
)

# 2. settings.jsx must import VaultTab from providers.jsx.
check(
    re.search(r"import\s*\{\s*VaultTab\s*\}\s*from\s*'\./providers\.jsx'", settings_src),
    "modals/settings.jsx: missing `import { VaultTab } from './providers.jsx';` "
    "— VaultTab must be pulled into the module that actually renders it.",
)

# 3. ConnectionsPanel's function body must mount <VaultTab />.
m = re.search(r'function ConnectionsPanel\s*\([^)]*\)\s*\{', settings_src)
check(m, "modals/settings.jsx: could not find `function ConnectionsPanel(`.")
if m:
    # Grab the panel's body up to the next top-level function declaration
    # (cheap proxy for "end of ConnectionsPanel") rather than a full brace
    # parser — consistent with this suite's other structural tests.
    tail = settings_src[m.end():]
    next_fn = re.search(r'\nfunction [A-Za-z_]', tail)
    body = tail[: next_fn.start()] if next_fn else tail
    check(
        '<VaultTab' in body,
        "modals/settings.jsx: ConnectionsPanel's JSX never renders <VaultTab /> "
        "— the import alone doesn't put it on screen.",
    )
    check(
        'CLOUD KEYS' in body,
        "modals/settings.jsx: sanity check failed — the existing CLOUD KEYS "
        "panel text vanished from ConnectionsPanel, test may be mis-scoped.",
    )
    if '<VaultTab' in body and 'CLOUD KEYS' in body:
        # <VaultTab /> should come after the CLOUD KEYS panel, matching the
        # intended "third sibling panel" placement.
        check(
            body.index('<VaultTab') > body.index('CLOUD KEYS'),
            "modals/settings.jsx: <VaultTab /> is mounted before the CLOUD KEYS "
            "panel — expected it as the third panel, after ON THIS MACHINE and "
            "CLOUD KEYS.",
        )

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")

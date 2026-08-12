#!/usr/bin/env python3
"""Vault search must not cross the bridge/local boundary — views/vault.jsx.

VaultBridge (the postMessage proxy to the SvelteKit shell that holds the
vetKeys master key) exposes list/read/write/create/remove. It has NO search
message. search() called CafresoHQClient.vaultSearch() unconditionally,
which always hits the LOCAL serve.py /vault/search endpoint — so inside the
encrypted shell (the boss's real, primary path per the north star's §3.5
vault trust story), a search either errored against an unrelated backend or
silently searched the wrong vault store, coming back empty for content that
genuinely exists. Every other vault action in this file (upload, rename,
delete) is correctly gated on `!_bridge`; search was the one action that
wasn't, and it's the one every other one of those actions doesn't need to
be correct to matter — a boss who can't find a note doesn't know it's there
to open, rename, or delete.

Static source checks (no DOM/React harness — search()/bridgeSearch() are
closures inside VaultView, not exported pure functions). Run:
    python3 scripts/test_vault_search.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'vault.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('vault search — bridge vs local')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    src = SRC.read_text(encoding='utf-8')

    m = re.search(r'const bridgeSearch = async[\s\S]*?\n  \};', src)
    check('a bridgeSearch() exists for encrypted-vault mode',
          bool(m), 'views/vault.jsx: no client-side search path for _bridge mode')
    bridge_body = m.group(0) if m else ''

    check('bridgeSearch() reads file content via the bridge, not the local API',
          '_bridge.read(' in bridge_body and 'vaultRead' not in bridge_body,
          'views/vault.jsx: bridgeSearch must decrypt through VaultBridge.read, '
          'the only content-fetch path that reaches the real (encrypted) notes')

    check('bridgeSearch() never calls the local-only vaultSearch endpoint',
          'vaultSearch' not in bridge_body,
          'views/vault.jsx: CafresoHQClient.vaultSearch() hits serve.py '
          '/vault/search, which has no relationship to the bridge vault')

    fn = re.search(r'const search = async \(\) => \{[\s\S]*?\n  \};', src)
    check('search() exists', bool(fn))
    fn_body = fn.group(0) if fn else ''

    check('search() branches on _bridge before calling vaultSearch',
          bool(re.search(r'_bridge\s*\?\s*await bridgeSearch\(', fn_body)),
          'views/vault.jsx: search() must route to bridgeSearch() in bridge '
          'mode instead of unconditionally calling CafresoHQClient.vaultSearch — '
          'that endpoint is local-only and knows nothing about the encrypted '
          'vault the boss is actually looking at inside the shell')

    # The search <input>/button must stay visible in bridge mode (that part
    # was never the bug — only the endpoint it called was wrong). Regressing
    # this the other way (hiding search under !_bridge) would silently take
    # away the ONLY way to find a note in a vault with more than a handful
    # of files, which is worse than a wrong answer.
    search_inputs = re.findall(r'placeholder="Search vault…"', src)
    check('the search box itself is not gated behind !_bridge',
          len(search_inputs) >= 1,
          'views/vault.jsx: the fix routes the ENDPOINT, not visibility — '
          'bridge-mode users still need to be able to search')

    print()
    if FAILS:
        print(f'vault search: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('vault search: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

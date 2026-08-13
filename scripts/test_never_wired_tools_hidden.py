#!/usr/bin/env python3
"""Four tool checkboxes in Hire/Roster gated nothing — audited, then hidden.

Drove Settings -> ROSTER for the first time this session and noticed the
"Image Gen" checkbox does nothing (toolsForAgent gates GENERATE_IMAGE purely
on `s.imageProvider`, never on `agent.tools`). That led to auditing the
whole grid: grepped every `claimed.has('<id>')` check inside toolsForAgent
and every TOOL_REGISTRY entry name. Of the 10 ids in TOOLS_CATALOG, only
'web', 'vault', and 'wallet' gate anything real. 'code' and 'files' are
harmlessly redundant with the separate `agent.elevated` toggle. 'email',
'cal', 'db', and 'slack' gate nothing because EMAIL_SEND / CALENDAR /
DATABASE / SLACK were never built as tools at all — not ungated, just
absent from TOOL_REGISTRY entirely. A boss checking any of those four in
Hire or Roster was granting nothing, with no warning that it did nothing.

The model itself was never at risk — its system prompt separates "claimed
capabilities" from "wired up for real execution" and is told to refuse
anything outside the wired set, so a coworker claiming 'email' still
correctly declines to pretend it sent one. The harm was entirely on the
boss-facing checkbox, which implied a real, working grant.

Fix: `visibleToolsCatalog()` (modals/settings.jsx), the single filter both
Hire and Roster already shared for the wallet-tool's money-module gate, now
also drops the four never-wired ids. 'code'/'files' (real capability exists,
just gated elsewhere) and 'img' (real tool, gated on an orphaned setting,
tracked separately) are deliberately left alone — removing those needs an
actual product decision this filter shouldn't make on its own.

Run: python3 scripts/test_never_wired_tools_hidden.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'

NEVER_WIRED = ['email', 'cal', 'db', 'slack']
STILL_REAL = ['web', 'vault', 'wallet']
INTENTIONALLY_KEPT_BUT_INERT = ['code', 'files', 'img']

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('never-wired tool claims — audited and hidden from Hire/Roster')
    for p in (RUNTIME, SETTINGS, HIRE):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1

    runtime_src = RUNTIME.read_text(encoding='utf-8')
    settings_src = SETTINGS.read_text(encoding='utf-8')
    hire_src = HIRE.read_text(encoding='utf-8')

    # 1. The audit's own premise still holds: none of the four ids are
    #    consulted by any claimed.has(...) check in toolsForAgent. If a
    #    future change wires one of them up for real, this test should
    #    start failing here — that's the signal to also remove it from
    #    NEVER_WIRED_TOOL_IDS instead of leaving it hidden needlessly.
    claimed_checks = set(re.findall(r"claimed\.has\('([a-z_]+)'\)", runtime_src))
    for tid in NEVER_WIRED:
        check(f"'{tid}' still gates nothing in toolsForAgent (claimed.has)",
              tid not in claimed_checks,
              f"claimed.has('{tid}') now appears in hq-runtime.jsx — this tool IS "
              f"wired up now, so it should come OUT of NEVER_WIRED_TOOL_IDS in "
              f"modals/settings.jsx, not stay hidden")
    for tid in STILL_REAL:
        check(f"'{tid}' is still actually gated (claimed.has present)",
              tid in claimed_checks or tid == 'wallet',
              f"claimed.has('{tid}') is missing — a previously-real tool claim "
              f"may have silently stopped mattering")

    # 2. modals/settings.jsx actually filters them out.
    m = re.search(r'NEVER_WIRED_TOOL_IDS\s*=\s*new Set\(\[([^\]]*)\]\)', settings_src)
    check('NEVER_WIRED_TOOL_IDS is defined', bool(m))
    if m:
        ids_in_set = set(re.findall(r"'([a-z_]+)'", m.group(1)))
        check('the filter set matches exactly the four audited ids',
              ids_in_set == set(NEVER_WIRED), ids_in_set)
    check('visibleToolsCatalog filters by NEVER_WIRED_TOOL_IDS',
          bool(re.search(r'visibleToolsCatalog\s*=\s*\(\)\s*=>\s*[\s\S]{0,200}'
                          r'NEVER_WIRED_TOOL_IDS', settings_src)),
          'settings.jsx: the filter chain does not reference the set')

    # 3. The Hire modal reaches the same filtered function, not the raw
    #    catalog — otherwise this fix would only ever apply to Roster.
    check("modals/hire.jsx renders tools via the SHARED visibleToolsCatalog, "
          "not HQ.TOOLS_CATALOG directly",
          'visibleToolsCatalog()' in hire_src and 'HQ.TOOLS_CATALOG' not in hire_src,
          'hire.jsx: either the import is gone, or it fell back to the raw '
          'unfiltered catalog')

    # 4. The intentionally-kept-but-inert ids are still offered — this test
    #    should not silently start hiding more than the four it audited.
    for tid in INTENTIONALLY_KEPT_BUT_INERT:
        check(f"'{tid}' is NOT in NEVER_WIRED_TOOL_IDS (kept visible on purpose)",
              m is not None and tid not in set(re.findall(r"'([a-z_]+)'", m.group(1))))

    print()
    if FAILS:
        print(f'never-wired tools: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('never-wired tools: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

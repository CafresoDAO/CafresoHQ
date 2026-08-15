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
# 'code' and 'files' were on this list until 2026-08-14, and the check that
# read it was named "kept visible on purpose" — which stayed green while
# both were hidden, because they moved into a SECOND filter set rather than
# into NEVER_WIRED_TOOL_IDS. They are hidden now: real file/shell access is
# granted by the 🛡 switch on the same card and by nothing these boxes did.
# 'img' genuinely is kept-but-inert — its real door is Settings → Media, so
# hiding it would leave the coworker card silent about images altogether.
INTENTIONALLY_KEPT_BUT_INERT = ['img']
# Hidden because the capability is real and its door is somewhere else.
GRANTED_ELSEWHERE = ['code', 'files']

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
    g = re.search(r'GRANTED_ELSEWHERE_TOOL_IDS\s*=\s*new Set\(\[([^\]]*)\]\)',
                  settings_src)
    # A declared set hides nothing on its own. Built from the sets the
    # filter chain actually APPLIES, because the arm that deletes the
    # `.filter(...)` line leaves both declarations in place — and read
    # from the declaration, `hidden` still listed two ids that were back
    # on the screen, so the invariant below sailed through the exact
    # regression it exists to catch.
    chain = re.search(r'visibleToolsCatalog\s*=\s*\(\)\s*=>[\s\S]{0,400}?;',
                      settings_src)
    applied = chain.group(0) if chain else ''
    hidden = set()
    for name, mm in (('NEVER_WIRED_TOOL_IDS', m),
                     ('GRANTED_ELSEWHERE_TOOL_IDS', g)):
        if mm and name in applied:
            hidden |= set(re.findall(r"'([a-z_]+)'", mm.group(1)))
    for tid in INTENTIONALLY_KEPT_BUT_INERT:
        check(f"'{tid}' is still rendered (kept visible on purpose)",
              tid not in hidden,
              f"'{tid}' got filtered out by one of the two hide-sets; its "
              'real door is on another screen, so hiding it here leaves the '
              'card unable to say anything about it at all')

    # 5. The invariant the four checks above are each a special case of: a
    #    checkbox the boss can see has to be READ somewhere. Every previous
    #    audit here worked the other way round — start from a known-dead id
    #    and confirm it is hidden — which is why 'code' and 'files' survived
    #    two audits: nobody asked the question from the checkbox's side.
    check('GRANTED_ELSEWHERE_TOOL_IDS is defined and filters the catalog',
          bool(g) and bool(re.search(
              r'visibleToolsCatalog\s*=\s*\(\)\s*=>\s*[\s\S]{0,300}'
              r'GRANTED_ELSEWHERE_TOOL_IDS', settings_src)),
          'settings.jsx: the second hide-set is missing from the filter chain')
    check('the second hide-set holds exactly the audited ids',
          bool(g) and set(re.findall(r"'([a-z_]+)'", g.group(1))) == set(GRANTED_ELSEWHERE),
          g.group(1) if g else None)

    runtime_src = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
    catalog = runtime_src[runtime_src.index('const TOOLS_CATALOG = ['):]
    catalog = catalog[:catalog.index('\n];')]
    rendered = [i for i in re.findall(r"id: '([^']+)'", catalog) if i not in hidden]
    # Comments stripped before the scan, and this is not a tidiness point.
    # Written against the raw source, this check passed while 'code' and
    # 'files' were unread — because the commit that FIXED them added a
    # comment reading "there is no claimed.has('code') … anywhere in
    # toolsForAgent", and the scan found the literal inside the sentence
    # denying it. Three checks in that commit matched its own prose. A
    # commit that documents a defect manufactures the strings that make a
    # naive check believe the defect is gone.
    code_only = re.sub(r'/\*[\s\S]*?\*/', '', runtime_src)
    code_only = re.sub(r'^\s*//.*$', '', code_only, flags=re.M)
    unread = [i for i in rendered
              if i not in INTENTIONALLY_KEPT_BUT_INERT
              and f"claimed.has('{i}')" not in code_only]
    check('every checkbox still on the card is read by toolsForAgent',
          not unread,
          f'{unread} render as ticking checkboxes but no claimed.has() reads '
          'them, so ticking one grants nothing — hide them, wire them, or '
          'add them to INTENTIONALLY_KEPT_BUT_INERT with the reason')

    print()
    if FAILS:
        print(f'never-wired tools: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('never-wired tools: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

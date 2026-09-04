#!/usr/bin/env python3
"""The HQ Terminal tab's header advertises fewer CLIs than it actually offers.

views/misc.jsx's TerminalView renders a full-page terminal via
ProjectTerminal (views/terminal.jsx), whose "+" add-session menu is the only
place a user discovers what kinds of tabs they can open. That menu (the
HQSH_COMMANDS-adjacent addSession list in terminal.jsx) has five entries:
hermes, claude, codex, gemini, and hqsh — the last one added in the very
same refactor that split misc.jsx out of the old monolithic views.jsx
(df10d31), which is presumably why the header subtitle was never updated
to match: it lists only "Hermes · Claude Code · Codex · Gemini", silently
dropping hqsh (the HQ chain shell — the REPL used for wallet/payroll/on-chain
commands, not a PTY at all). A user reading the header has no reason to
suspect a fifth kind of session exists, let alone that it's the one that can
run `hq wallets`/`hq send`/etc.

This test parses the real addSession menu list out of views/terminal.jsx
(the ground truth for what "+" actually offers) and asserts every one of
those CLI ids' display names appears in views/misc.jsx's header subtitle
string. It fails on the pre-fix header (missing "hqsh") and passes once the
subtitle is updated to include it.

Run: python3 scripts/test_terminal_header_lists_every_cli.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


term_src = (ROOT / 'views' / 'terminal.jsx').read_text()
misc_src = (ROOT / 'views' / 'misc.jsx').read_text()

# Pull the addSession menu's literal array of [id, icon, label, isDefault]
# tuples straight out of terminal.jsx — e.g.
#   [['hermes', '☼', 'Hermes', true], ['claude', '✦', 'Claude Code', false], ...]
m = re.search(
    r"\[\['hermes',.*?\]\]\.map\(\(\[c, ico, label, isDefault\]\)",
    term_src, re.S,
)
check(m is not None, "couldn't locate the addSession menu's CLI list in views/terminal.jsx "
                      "— has it been restructured? (update this test's regex)")

entries = []
if m:
    # Extract each ['id', 'icon', 'Label', bool] tuple's id + label.
    entries = re.findall(r"\['(\w+)',\s*'[^']*',\s*'([^']*)',\s*(?:true|false)\]", m.group(0))
    check(len(entries) >= 5,
          f"expected at least 5 CLI entries in the addSession menu, found {len(entries)}: {entries}")

# views/misc.jsx must first still render the header text at all.
header_m = re.search(
    r"Hermes · Claude Code · Codex · Gemini[^<]*", misc_src,
)
check(header_m is not None,
      "views/misc.jsx's TerminalView header subtitle text is missing or changed shape "
      "— expected it to start with 'Hermes · Claude Code · Codex · Gemini'.")
header_text = header_m.group(0) if header_m else ''

# Every CLI id offered by the real "+" menu must be discoverable from the
# header text — by its short id ('hqsh') or its full label ('HQ chain
# shell' / 'Claude Code' / 'Codex CLI' / 'Gemini CLI').
for cli_id, label in entries:
    mentioned = (
        cli_id.lower() in header_text.lower()
        or label.lower() in header_text.lower()
        or label.split(' — ')[0].split(' ')[0].lower() in header_text.lower()
    )
    check(mentioned,
          f"TerminalView's header subtitle doesn't mention '{cli_id}' "
          f"({label!r}), even though the '+' add-session menu offers it. "
          f"Header text: {header_text!r}")

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")

#!/usr/bin/env python3
"""The CEO ran a template it copied out of its own tool docs.

`agentStream` (the per-coworker chat path) guards against a coworker that
writes back the EXAMPLE out of its own tool instructions instead of a real
value — `[BROWSER_FETCH: <url>]`, copied verbatim from the doc string that
teaches the marker. `placeholderRefusal` catches that shape (the whole
argument is a single `<...>` token) and returns a correction instead of
letting it run, so the boss never sees a spent hop and a phantom "visit"
for a call that was never really an attempt.

`ceoStream` — the CEO/"CafresoHQ" chat path, a few hundred lines above the
same guard — never got it. The CEO reads a system prompt built out of the
very same TOOL_REGISTRY doc strings (`ceoToolSnippet`, built from
`toolsPromptSnippet`/`toolsPromptSnippetJson`), which are full of
`<query>`/`<path>` examples for VAULT_READ, VAULT_APPEND, VAULT_NEW and
SEARCH. Writing `[VAULT_READ: <path>]` back verbatim used to run for real
in ceoStream: a live vault read against the literal text "<path>", a
`start`/`done` visit pair on the floor for a call that was never a real
attempt, and one of the CEO's four tool hops spent on it — while the exact
same reply from a specialist agent was caught and corrected for free.

Run: python3 scripts/test_the_ceo_that_copied_the_template.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("the CEO that copied the template")

    fn = re.search(r"async function ceoStream\([\s\S]*?\n}\n\nasync function agentStream", RUNTIME)
    check('found ceoStream (bounded by the next function, agentStream)', fn is not None)
    body = fn.group(0) if fn else ''

    check("ceoStream calls placeholderRefusal on the detected call, same guard agentStream runs",
          re.search(r"placeholderRefusal\(call\.tool\.name,\s*call\.arg\)", body) is not None)

    # The refusal has to run BEFORE the 'start' event fires and before the
    # tool actually executes — a refused template must never become a visit.
    refusal_pos = body.find('placeholderRefusal(call.tool.name, call.arg)')
    start_pos = body.find("onTool({ phase: 'start'")
    run_pos = body.find('call.tool.run(call.arg')
    check("the refusal check sits before the 'start' visit event",
          refusal_pos != -1 and start_pos != -1 and refusal_pos < start_pos)
    check("the refusal check sits before the tool actually runs",
          refusal_pos != -1 and run_pos != -1 and refusal_pos < run_pos)

    # On a refusal, ceoStream must feed the correction back to the model and
    # try the next hop — not silently drop the turn (return) and not run
    # the tool anyway.
    continue_block = re.search(
        r"const ceoRefusal = placeholderRefusal\(call\.tool\.name, call\.arg\);\s*\n"
        r"\s*if \(ceoRefusal\) \{\s*\n"
        r"\s*messages\.push\(\{ role: 'assistant', content: upToToolCall\(buf, call\.raw\) \}\);\s*\n"
        r"\s*messages\.push\(\{ role: 'user', content: ceoRefusal \}\);\s*\n"
        r"\s*continue;\s*\n"
        r"\s*\}",
        body)
    check("a refusal pushes the correction as the next user turn and continues the hop loop",
          continue_block is not None)

    # agentStream's own placeholderRefusal call is untouched — this fix adds
    # a sibling call, it does not touch or duplicate the existing one.
    check("agentStream's own placeholderRefusal call is untouched",
          RUNTIME.count('placeholderRefusal(call.tool.name, call.arg)') == 2)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

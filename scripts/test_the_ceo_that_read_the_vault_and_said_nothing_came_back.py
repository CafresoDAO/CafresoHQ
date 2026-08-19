#!/usr/bin/env python3
"""ceoStream never distinguished "did the legwork" from "brain is busy".

Reproduced by reading the source. `agentStream` (the per-coworker chat
path) tracks a `toolsExecuted` counter across hops and, when a hop comes
back with no tool call and no text, checks it FIRST: a coworker who ran
a real tool earlier in the exchange gets "did the legwork but never
wrote it up" — a materially truer message than "may be offline or busy"
would be, since the brain clearly wasn't offline five seconds earlier
when it read a file.

`ceoStream` — the CEO/"CafresoHQ" chat path, a few lines above in the
same file — never got the same counter. A CEO that successfully read
the vault or ran a search on hop 1, then produced an empty reply on hop
2, fell straight into the generic "nothing came back from me that time
— the brain running this office may be offline or busy" line, even
though it plainly was not offline: it had just done real work.

Run: python3 scripts/test_the_ceo_that_read_the_vault_and_said_nothing_came_back.py
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
    print("the CEO that read the vault and said nothing came back")

    fn = re.search(r"async function ceoStream\([\s\S]*?\n}\n\nasync function agentStream", RUNTIME)
    check('found ceoStream (bounded by the next function, agentStream)', fn is not None)
    body = fn.group(0) if fn else ''

    check("ceoStream declares its own toolsExecuted counter, initialised to 0",
          re.search(r"let toolsExecuted = 0;", body) is not None)
    check("...incremented once per tool call, success or failure alike (same as agentStream)",
          re.search(r"catch \(err\) \{ result = `That didn't work — \$\{err\.message\}`; meta\.failed = true; \}\s*\n\s*toolsExecuted\+\+;",
                     body) is not None)

    # The empty-response branch must check toolsExecuted BEFORE the
    # missing/orphans/generic fallbacks — same priority order as agentStream.
    order = re.search(
        r"if \(toolsExecuted > 0\) \{\s*\n\s*emit\('_\(I did the legwork but never wrote it up\. Ask me to summarise what I found\.\)_'\);\s*\n\s*\} else if \(note\) \{",
        body)
    check("the empty-reply branch checks toolsExecuted first, ahead of the missing-door and orphan checks",
          order is not None)

    # The two pre-existing, unrelated fallback messages must still exist
    # untouched — this fix must not replace them, only add a branch ahead.
    check('the "talked myself through it" fallback is untouched',
          "I talked myself through that one and never actually answered" in body)
    check('the generic "may be offline or busy" fallback is untouched (still reachable when toolsExecuted is 0)',
          "the brain running this office may be offline or busy" in body)

    # agentStream's own toolsExecuted is a separate counter — this fix must
    # not touch it or its "did the legwork" sibling message.
    check("agentStream's own toolsExecuted counter and message are untouched",
          "did the legwork but never wrote it up" in RUNTIME
          and RUNTIME.count("let toolsExecuted = 0;") == 2)

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

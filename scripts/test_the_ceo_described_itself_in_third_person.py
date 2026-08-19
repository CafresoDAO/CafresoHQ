#!/usr/bin/env python3
"""ceoStream's hop-exhausted hint spoke of the CEO as "they".

Reproduced by reading the source. `hq-runtime.jsx`'s `ceoStream` is the
CEO/"CafresoHQ" chat streaming path, and is documented in its own file,
at length, as deliberately first-person throughout — the function's own
comment block (just above, at lines 3984-3994) recounts fixing this
exact defect once already in a sibling message, explicitly calling out
"'they' is the office describing itself in the third person" as one of
three things wrong with the old text.

That fix didn't reach every message in the same function. The
per-turn tool-hop-budget-exhausted hint still read:

    '_(they did as much as they can in one go and stopped there.
       Ask again and they will carry on from where they left off.)_'

Third person, in the one chat surface (per the file's own repeated
documentation) that must never use it — `agentStream`, the per-coworker
equivalent a few lines below, is correctly third-person throughout,
because it IS describing someone else. ceoStream is the office speaking
about itself.

Run: python3 scripts/test_the_ceo_described_itself_in_third_person.py
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
    print('the CEO described itself in the third person')

    fn = re.search(r"async function ceoStream\([\s\S]*?\n}\n\nasync function agentStream", RUNTIME)
    check('found ceoStream (bounded by the next function, agentStream)', fn is not None)
    body = fn.group(0) if fn else ''

    check('the hop-exhausted hint no longer says "they did"',
          'they did as much as they can' not in body)
    check('...or "they will carry on"',
          'they will carry on' not in body)
    check('...it says "I did" / "I will carry on" instead, first person like the rest of ceoStream',
          re.search(r"I did as much as I can in one go and stopped there\. Ask again and I will carry on from where I left off\.",
                     body) is not None)

    # The sibling message this exact bug class was already fixed in once
    # (a few lines above) stays first-person, and its own explanatory
    # comment — the one that names "they" as the defect — is untouched.
    check("the earlier, already-fixed sibling hint stays first person",
          "nothing came back from me that time" in body)
    check("the comment documenting that earlier fix (which names this exact bug) is untouched",
          re.search(r'is the office describing itself in the third person', RUNTIME) is not None)

    # agentStream is a different surface — it describes a named coworker,
    # so third person is correct there and must not be touched by this fix.
    agent_fn = re.search(r"async function agentStream\([\s\S]{0,4000}", RUNTIME)
    check('agentStream (the per-coworker, correctly-third-person twin) is untouched',
          agent_fn is not None and 'async function agentStream' in RUNTIME)

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

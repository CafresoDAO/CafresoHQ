#!/usr/bin/env python3
"""The office ran the marker its registry listed first, not the one the
coworker wrote first — and threw the other one away.

`detectToolCall`'s bracket pass walked the agent's tool ARRAY and returned on
the first regex that matched anywhere in the reply. `toolsForAgent` builds
that array in a fixed order: SEARCH, then the whole vault group, then
files/shell, then browser, then the private-memory pair. So which of two
markers in one reply actually ran was a property of that push order, not of
what the coworker asked for.

The shape that costs a file — a coworker with 'web' and 'vault', filing what
it found and then asking one more question:

    [VAULT_NEW: Research/findings.md]
    …everything it had just worked out…
    [/VAULT_NEW]
    [SEARCH: one more thing]

SEARCH ran. The write did not. Then `upToToolCall` keeps the buffer up to and
including the marker that RAN, so the entire VAULT_NEW block went back into
the transcript as an assistant turn, with `[TOOL_RESULT: SEARCH]` beneath it
and "Do NOT repeat the tool call" beside it. From the model's side the note
is filed; it tells the boss so; the Library is empty. Nothing downstream
catches it either: VAULT_NEW is a GRANTED marker so `reachedFor` stays quiet,
and the delivery sheet's unfiled-path note reads the cleaned body, where the
block has already been stripped.

The fix is one comparison: among the tools whose regex matches, take the one
whose match starts EARLIEST in the reply. Ties keep registry order.

Run: python3 scripts/test_the_first_marker_in_the_reply_runs_first.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift():
    """Slice detectToolCall and its dependencies out of the browser module."""
    parts = [m.group(0) for m in
             re.finditer(r'^const ORPHAN_TAG_\w+\s*=[\s\S]*?;$', SRC, re.M)]
    if not parts:
        raise SystemExit('could not find any ORPHAN_TAG_* const')
    for fn in ('reasoningPatterns', 'stripReasoning', 'maskReasoning',
               'extractAllDMs', 'detectJsonToolCall', 'extractHarmonyToolCalls',
               'harmonyArgsFor', 'detectToolCall', 'upToToolCall'):
        m = re.search(r'^function ' + fn + r'\(.*?^\}', SRC, re.M | re.S)
        if not m:
            raise SystemExit('could not find %s in hq-runtime.jsx' % fn)
        parts.append(m.group(0))
    return '\n'.join(parts)


def run_js(cases_js):
    proc = subprocess.run(['node', '--input-type=module', '-e',
                           lift() + '\n' + cases_js],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


# The tool array in the order toolsForAgent actually pushes them for a
# coworker with 'web' + 'vault' + elevated. Regexes copied from TOOL_REGISTRY
# and pinned against it below, so this cannot drift into testing a fiction.
TOOLS_JS = r'''
const TOOLS = [
  { name: 'SEARCH',     re: /\[\s*SEARCH\s*:\s*([^\]\n]+)\]/i },
  { name: 'VAULT_READ', re: /\[\s*VAULT_READ\s*:\s*([^\]\n]+)\]/i },
  { name: 'VAULT_NEW',  re: /\[\s*VAULT_NEW\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*VAULT_NEW\s*\]/i },
  { name: 'BASH',       re: /\[\s*BASH\s*:\s*([^\]\n]+)\]/i },
];
'''

BODY = 'Everything I worked out, and the only copy of it.'

CASES = [
    # label, reply, tool that must run, arg that must come with it
    ('the measured defect: a filing then a question',
     '[VAULT_NEW: Research/findings.md]\n' + BODY + '\n[/VAULT_NEW]\n'
     '[SEARCH: one more thing]',
     'VAULT_NEW', 'Research/findings.md'),
    ('...still true with prose around it',
     'Filing what I have first.\n'
     '[VAULT_NEW: Research/findings.md]\n' + BODY + '\n[/VAULT_NEW]\n'
     'Now let me check one more thing.\n[SEARCH: one more thing]',
     'VAULT_NEW', 'Research/findings.md'),
    ('a shell call before a read',
     '[BASH: npm run build]\n[VAULT_READ: Notes/a.md]',
     'BASH', 'npm run build'),
    # The registry order is right whenever it agrees with the reply order —
    # this is the case that passed before and must keep passing.
    ('the search really was first',
     '[SEARCH: primary colours]\n[VAULT_READ: Notes/a.md]',
     'SEARCH', 'primary colours'),
    ('a lone marker is unaffected',
     '[VAULT_READ: Notes/a.md]', 'VAULT_READ', 'Notes/a.md'),
]


def main():
    print('the first marker in the reply runs first')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    js = TOOLS_JS + 'const R = {};\n'
    for label, reply, _t, _a in CASES:
        js += ('R[%s] = (c => c && { tool: c.tool.name, arg: c.arg, body: c.body })'
               '(detectToolCall(%s, TOOLS));\n'
               % (json.dumps(label), json.dumps(reply)))
    # The body of the block that runs must be the block's OWN body — picking
    # the earliest match is worthless if it hands over the wrong content.
    js += ('R.__body = (c => c && c.body)(detectToolCall(%s, TOOLS));\n'
           % json.dumps('[VAULT_NEW: Research/findings.md]\n' + BODY
                        + '\n[/VAULT_NEW]\n[SEARCH: one more thing]'))
    # `raw` has to be the winner's own text too: upToToolCall slices the
    # transcript at it, and a raw from the wrong marker would cut the
    # assistant turn in the wrong place.
    js += ('R.__raw = (c => c && upToToolCall(%s, c.raw))(detectToolCall(%s, TOOLS));\n'
           % (json.dumps('[VAULT_NEW: Research/findings.md]\n' + BODY
                         + '\n[/VAULT_NEW]\n[SEARCH: one more thing]'),
              json.dumps('[VAULT_NEW: Research/findings.md]\n' + BODY
                         + '\n[/VAULT_NEW]\n[SEARCH: one more thing]')))
    js += 'console.log(JSON.stringify(R));'
    out = run_js(js)

    for label, reply, want_tool, want_arg in CASES:
        got = out[label]
        check(label,
              got and got['tool'] == want_tool
              and str(got['arg']).strip() == want_arg,
              'got %r, wanted %s(%r)' % (got, want_tool, want_arg))

    check('the winning block carries its own body',
          out['__body'] == BODY,
          'got %r, wanted %r' % (out['__body'], BODY))
    check('the transcript is cut at the marker that ran',
          out['__raw'] is not None and out['__raw'].rstrip().endswith('[/VAULT_NEW]'),
          'got %r' % (out['__raw'],))

    # ── pin the mechanism, not just the outcome ─────────────────────────
    #
    # Every case above would pass again if someone reordered TOOL_REGISTRY so
    # the vault group happened to come first. The rule is "earliest match in
    # the text wins", and it has to be visible in the code.
    loop = re.search(r'function detectToolCall\([\s\S]*?^\}', SRC, re.M)
    check('detectToolCall compares match positions',
          loop and re.search(r'\.index\s*<', loop.group(0)),
          'the bracket pass still returns on the first tool that matches')
    check('...and does not return inside the scan loop',
          loop and not re.search(
              r'for \(const t of tools\) \{\n\s*const m = String\(scan\)\.match\(t\.re\);\n\s*if \(m\) return',
              loop.group(0)),
          'the early-return is back')

    # The tool array this suite fakes must stay honest about the real
    # regexes — a change to TOOL_REGISTRY's patterns has to reach here.
    for name in ('SEARCH', 'VAULT_READ', 'VAULT_NEW', 'BASH'):
        pat = re.search(r"name: '" + name + r"',\s*\n(?:\s*/\*[\s\S]*?\*/\s*\n)?\s*re: (.+),\n",
                        SRC)
        check('the fake %s regex matches TOOL_REGISTRY' % name,
              pat and pat.group(1) in TOOLS_JS,
              pat and pat.group(1))

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

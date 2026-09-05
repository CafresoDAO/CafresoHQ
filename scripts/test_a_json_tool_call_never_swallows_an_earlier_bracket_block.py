#!/usr/bin/env python3
"""#257 made the bracket pass honour reply order. The JSON pass above it
still did not, and it is the pass that runs FIRST.

`detectToolCall` called `detectJsonToolCall` and returned unconditionally on
a hit, before the bracket scan had looked at anything. So a reply carrying
both shapes was decided by which DETECTOR runs first, not by what the
coworker wrote first — the same defect #257 fixed, one layer up.

It is not hypothetical for a JSON-format coworker. `supportsJsonToolFormat`
puts every Anthropic/Google/capable-local brain on the JSON snippet, but the
bracket vocabulary reaches the same system prompt from two places that
snippet does not control: the office's own FILE-DELIVERY RULE ("MUST be saved
to the Library using [VAULT_NEW: <path>]…[/VAULT_NEW]") and every shipped
persona that orders "[SEARCH] … then [VAULT_NEW]". Told to file in brackets
and to call in JSON, the model does both:

    [VAULT_NEW: Research/findings.md]
    …everything it had just worked out…
    [/VAULT_NEW]
    <<<TOOL>>>
    {"tool": "SEARCH", "arg": "one more thing"}
    <<<END_TOOL>>>

The SEARCH ran. `upToToolCall` then cut the transcript at the JSON block —
which sits LATER — so the entire VAULT_NEW block went back as an assistant
turn with `[TOOL_RESULT: SEARCH]` beneath it and "Do NOT repeat the tool
call" beside it. From the model's side the note is filed; it says so to the
boss; the Library is empty. Nothing downstream catches it: VAULT_NEW is a
granted marker so `reachedFor` stays quiet, and the delivery sheet reads the
cleaned body, where the block has already been stripped.

The fix is the same comparison #257 made: whichever call STARTS earliest in
the reply wins, whatever wire format it arrived in. A tie keeps the old
JSON-first answer.

Run: python3 scripts/test_a_json_tool_call_never_swallows_an_earlier_bracket_block.py
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


def strip_comments(js):
    """Block and line comments out, so the explanatory note that documents
    this bug cannot itself satisfy (or break) a source check below."""
    js = re.sub(r'/\*[\s\S]*?\*/', '', js)
    return re.sub(r'^\s*//.*$', '', js, flags=re.M)


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
# coworker with 'web' + 'vault'. Regexes copied from TOOL_REGISTRY and pinned
# against it below, so this cannot drift into testing a fiction.
TOOLS_JS = r'''
const TOOLS = [
  { name: 'SEARCH',     re: /\[\s*SEARCH\s*:\s*([^\]\n]+)\]/i },
  { name: 'VAULT_READ', re: /\[\s*VAULT_READ\s*:\s*([^\]\n]+)\]/i },
  { name: 'VAULT_NEW',  re: /\[\s*VAULT_NEW\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*VAULT_NEW\s*\]/i },
];
'''

BODY = 'Everything I worked out, and the only copy of it.'


def tool_json(name, arg):
    return ('<<<TOOL>>>\n' + json.dumps({'tool': name, 'arg': arg})
            + '\n<<<END_TOOL>>>')


FILING = '[VAULT_NEW: Research/findings.md]\n' + BODY + '\n[/VAULT_NEW]'

CASES = [
    # label, reply, tool that must run, arg that must come with it
    ('the measured defect: a bracket filing, then a JSON call',
     FILING + '\n' + tool_json('SEARCH', 'one more thing'),
     'VAULT_NEW', 'Research/findings.md'),
    ('...still true with prose around it',
     'Filing what I have first.\n' + FILING
     + '\nNow let me check one more thing.\n'
     + tool_json('SEARCH', 'one more thing'),
     'VAULT_NEW', 'Research/findings.md'),
    # The JSON-first answer is right whenever it agrees with the reply
    # order — these are the cases that passed before and must keep passing.
    ('a JSON call really was first',
     tool_json('SEARCH', 'primary colours') + '\n[VAULT_READ: Notes/a.md]',
     'SEARCH', 'primary colours'),
    ('a lone JSON call is unaffected',
     tool_json('VAULT_READ', 'Notes/a.md'), 'VAULT_READ', 'Notes/a.md'),
    ('a lone bracket marker is unaffected',
     '[VAULT_READ: Notes/a.md]', 'VAULT_READ', 'Notes/a.md'),
    # A marker quoted INSIDE the JSON block starts later than the block
    # itself, so it must never steal the turn.
    ('a bracket marker inside the JSON payload does not win',
     tool_json('SEARCH', 'what does [VAULT_READ: Notes/a.md] do'),
     'SEARCH', 'what does [VAULT_READ: Notes/a.md] do'),
]


def main():
    print('a json tool call never swallows an earlier bracket block')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    js = TOOLS_JS + 'const R = {};\n'
    for label, reply, _t, _a in CASES:
        js += ('R[%s] = (c => c && { tool: c.tool.name, arg: c.arg, body: c.body })'
               '(detectToolCall(%s, TOOLS));\n'
               % (json.dumps(label), json.dumps(reply)))
    mixed = FILING + '\n' + tool_json('SEARCH', 'one more thing')
    # Picking the earliest call is worthless if it hands over the wrong
    # content, and worse than worthless if `raw` belongs to the loser:
    # upToToolCall slices the assistant turn at it.
    js += ('R.__body = (c => c && c.body)(detectToolCall(%s, TOOLS));\n'
           % json.dumps(mixed))
    js += ('R.__raw = (c => c && upToToolCall(%s, c.raw))(detectToolCall(%s, TOOLS));\n'
           % (json.dumps(mixed), json.dumps(mixed)))
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
    check('...and the JSON block the model wrote after it is not kept',
          out['__raw'] is not None and '<<<TOOL' + '>>>' not in out['__raw'],
          'got %r' % (out['__raw'],))

    # ── pin the mechanism, not just the outcome ─────────────────────────
    #
    # Comments stripped first: the note explaining this fix quotes the very
    # shapes the checks look for.
    fn = re.search(r'function detectToolCall\([\s\S]*?^\}', SRC, re.M)
    check('detectToolCall is still here', bool(fn))
    body = strip_comments(fn.group(0)) if fn else ''
    check('the JSON pass no longer returns before the bracket scan',
          not re.search(r'detectJsonToolCall\([^)]*\);\s*\n\s*if \(\w+\) return \w+;', body),
          'the unconditional early return is back')
    check('detectToolCall compares the JSON call position against the bracket one',
          bool(re.search(r'indexOf\(\w+\.raw\)', body))
          and bool(re.search(r'>\s*best\.m\.index', body)),
          body)

    # The tool array this suite fakes must stay honest about the real
    # regexes — a change to TOOL_REGISTRY's patterns has to reach here.
    for name in ('SEARCH', 'VAULT_READ', 'VAULT_NEW'):
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

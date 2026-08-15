#!/usr/bin/env python3
"""A correct tool call became a filename, and the office called it "Saved".

`harmonyArgsFor` turns a harmony JSON payload into the `{arg, body}` the
tool runners take. It was a switch with a case per tool and, underneath,
`default: { arg: payload }` — the whole JSON object handed over as the
argument. Ten of the office's thirty-one tools had a case. The other
twenty-one did not, and they are the ones on which a coworker produces
something the boss keeps: every file, export, publish, memory and wallet
tool.

Reproduced on office 9262, 2026-08-15, gpt-oss-20b through LM Studio. The
boss asked for a landing page at site/index.html. The model got it right,
in the format its own tokenizer declares:

    <|channel|>commentary to=FILE_WRITE <|constrain|>json<|message|>
    {"path":"site/index.html","content":"<!DOCTYPE html>\n…"}

The office used that whole string as the path. Every `/` in the boss's own
HTML — `</title>`, `</head>`, `</h1>`, `</p>`, `</body>`, `</html>` —
became a directory separator, so the workspace got a seven-level tree of
directories named after fragments of the page, with an empty file at the
bottom and no site/index.html anywhere. What the boss saw:

    📝 Saved {"path":"site/index.html","content":"<!DOCTYPE html>… in the project
       Wrote 0 chars → …/sp62/{"path":"site/index.html","content":"…

"Saved", and "0 chars", in the same block, about a path nobody asked for.

The same office, the same question, after the fix:

    📝 Saved site/index.html in the project
       Wrote 467 chars → …/sp62/site/index.html

The fix is not a case for FILE_WRITE. An allow-list of tools is a list
that silently stops being complete — it had already stopped, twenty-one
times, and adding a twenty-second entry would leave the next tool exactly
where this one was. The mapping is key-driven with a generic default, so a
tool added later is covered by construction, and this suite sweeps EVERY
tool in the registry rather than the one that was reported.

Run: python3 scripts/test_a_json_tool_call_is_not_a_filename.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_RAW = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comment written with this fix quotes the
    old `default: { arg: payload }` line and the broken visit block."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def const_lift(src, name):
    m = re.search(r'^const ' + name + r' = [\s\S]*?;\s*$', src, re.M)
    if not m:
        raise AssertionError('cannot lift ' + name)
    return m.group(0)


# Every tool the office defines, read out of the registry rather than
# listed here. A list of tool names in a test file is the same mistake one
# level down: it stops being complete the moment someone adds a tool.
TOOL_NAMES = sorted(set(re.findall(r"^\s{4}name: '([A-Z0-9_]+)',", RUNTIME_RAW, re.M)))


def main():
    print('a JSON tool call is not a filename')
    code = strip_comments(RUNTIME_RAW)

    check('the registry has tools to sweep',
          len(TOOL_NAMES) > 25, len(TOOL_NAMES))

    # ── 1. the line that did it ─────────────────────────────────────────
    body = brace_lift(code, 'function harmonyArgsFor(')
    check('no branch hands the raw payload on as the argument by default',
          not re.search(r'default\s*:\s*return \{ arg: payload \}', body)
          and 'switch (tool.name)' not in body,
          '— `default: { arg: payload }` under a per-tool switch is the '
          'defect; a switch is an allow-list and it had already stopped '
          'being complete twenty-one times')
    check('...but a payload that is not an object is still the argument',
          re.search(r'if \(!isObj\) return \{ arg: payload \};', body),
          '— `[SEARCH: lemons]` sends a bare string, and always worked')

    # ── 2. the sweep. Every tool, not the one that was reported ─────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the sweep needs it')
    else:
        js = ''
        for c in ('JSON_ARG_KEYS', 'JSON_BODY_KEYS', 'JSON_KEYS_BY_TOOL'):
            js += const_lift(code, c) + '\n'
        js += body + '\n'
        js += 'const TOOLS = ' + json.dumps(TOOL_NAMES) + ';\n'
        js += r'''
// The payload off the live run, byte for byte.
const REPRO = JSON.stringify({
  path: 'site/index.html',
  content: '<!DOCTYPE html>\n<html lang="en">\n<head>\n<title>Lemonade Stand</title>\n'
    + '</head>\n<body>\n<h1>Welcome to Sunny Lemonade Stand!</h1>\n</body>\n</html>',
});
const call = (name, payload) => harmonyArgsFor({ name }, payload);

// Shapes a tool-trained model actually emits, none of them tool-specific.
const SHAPES = [
  { path: 'site/index.html', content: 'hello' },
  { file: 'notes/a.md', text: 'hello' },
  { query: 'lemonade stands', q: 'lemonade stands' },
  { url: 'https://example.com' },
  { command: 'ls -la' },
  { to: 'Vera', message: 'can you look at this' },
  { name: 'Vera', role: 'Analyst', rationale: 'because' },
  { path: 'a/b.md', content: 'x', extra: { nested: 'object' } },
];
// A key nothing knows. The office does not know what was meant, and the
// one thing it must not do is act as though it did.
const UNKNOWN = { wibble: 'site/index.html', flim: 'flam' };

const bloblike = s => typeof s === 'string' && /^\s*[{[]/.test(s);
const swept = [];
for (const name of TOOLS) {
  for (const shape of SHAPES.concat([UNKNOWN])) {
    const r = call(name, JSON.stringify(shape));
    if (bloblike(r.arg)) swept.push([name, JSON.stringify(shape).slice(0, 40)]);
  }
}

const repro = call('FILE_WRITE', REPRO);
const R = {
  // Nothing, anywhere, turns an object into an argument.
  blobs: swept,
  // The reported case, end to end.
  reproArg: repro.arg,
  reproBodyHead: String(repro.body || '').slice(0, 15),
  // A bare string payload is untouched.
  bareString: call('SEARCH', 'lemonade stands').arg,
  // An unknown key set yields nothing rather than something wrong.
  unknown: call('FILE_WRITE', JSON.stringify(UNKNOWN)).arg,
  // A transfer is never guessed at from whichever fields turned up.
  walletSend: call('WALLET_SEND', JSON.stringify({ token: 'ICP', amount: '5', to: 'aaaaa-aa' })).arg,
  // A nested object is not a string and is not an argument.
  nested: call('FILE_WRITE', JSON.stringify({ path: { a: 1 }, content: 'x' })).arg,
  // GENERATE_IMAGE takes a vault PATH; a bare prompt is not one.
  imageNoPath: call('GENERATE_IMAGE', JSON.stringify({ prompt: 'a lemon' })).arg,
  // The per-tool key lists are NARROWER than the generic one, and that is
  // their job: a recipient is not a path. Given both, the tool must take
  // the one it actually addresses. Without its entry DM_TO falls back to
  // the generic list, where `path` comes first — and the office sends the
  // boss's message to a filename.
  crossTalkDm:      call('DM_TO', JSON.stringify({ path: 'site/index.html', to: 'Vera', message: 'hi' })).arg,
  crossTalkHandoff: call('HANDOFF_TO', JSON.stringify({ url: 'https://x.dev', to: 'Vera', message: 'hi' })).arg,
  // The ten tools that already worked must still work identically.
  old: {
    SEARCH:            call('SEARCH', JSON.stringify({ query: 'lemons' })).arg,
    VAULT_SEARCH:      call('VAULT_SEARCH', JSON.stringify({ q: 'lemons' })).arg,
    VAULT_READ:        call('VAULT_READ', JSON.stringify({ path: 'Daily/x.md' })).arg,
    VAULT_NEW:         call('VAULT_NEW', JSON.stringify({ path: 'a.md', content: 'c' })),
    DM_TO:             call('DM_TO', JSON.stringify({ to: 'Vera', message: 'hi' })),
    SPAWN_SUBAGENT:    call('SPAWN_SUBAGENT', JSON.stringify({ role: 'Editor', task: 't' })),
    REQUEST_ELEVATION: call('REQUEST_ELEVATION', JSON.stringify({ reason: 'r', details: 'd' })),
    HIRE_AGENT:        call('HIRE_AGENT', JSON.stringify({ name: 'Vera', role: 'Analyst', rationale: 'w' })),
  },
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the mapper harness runs', False, p.stderr.strip()[:500])
        else:
            R = json.loads(p.stdout)
            check('no tool in the registry turns a JSON object into its argument',
                  not R['blobs'],
                  [R['blobs'][:6], '— every one of these writes a file, runs a '
                   'command or fetches a URL named after its own arguments'])
            check('the reported call now names the path the boss asked for',
                  R['reproArg'] == 'site/index.html', R['reproArg'])
            check('...and the page itself is the body',
                  R['reproBodyHead'] == '<!DOCTYPE html>',
                  [R['reproBodyHead'], '— it was empty, so the office wrote 0 '
                   'chars and reported "Saved"'])
            check('a bare string payload is still the argument',
                  R['bareString'] == 'lemonade stands', R['bareString'])
            check('an object with no key we know yields nothing',
                  R['unknown'] == '',
                  [R['unknown'], '— an empty argument fails the tool, which '
                   'the boss sees as a failed visit. The blob succeeded'])
            check('a nested object is never used as an argument',
                  R['nested'] == '', R['nested'])
            check('an image prompt is not mistaken for a vault path',
                  R['imageNoPath'] == '',
                  [R['imageNoPath'], '— that is how a file ends up named '
                   'after its own contents'])
            check('a transfer is never assembled from whichever fields turned up',
                  R['walletSend'] == '',
                  [R['walletSend'], '— every other tool fails by doing '
                   'nothing; this one would fail by moving money'])
            check('a tool that addresses a person never addresses a path',
                  R['crossTalkDm'] == 'Vera' and R['crossTalkHandoff'] == 'Vera',
                  [R['crossTalkDm'], R['crossTalkHandoff'],
                   '— the per-tool key lists are narrower than the generic '
                   'one on purpose; drop one and the generic list answers, '
                   'where `path` comes first'])
            old = R['old']
            check('the ten tools that already worked still map the same way',
                  old['SEARCH'] == 'lemons'
                  and old['VAULT_SEARCH'] == 'lemons'
                  and old['VAULT_READ'] == 'Daily/x.md'
                  and old['VAULT_NEW'] == {'arg': 'a.md', 'body': 'c'}
                  and old['DM_TO'] == {'arg': 'Vera', 'body': 'hi'}
                  and old['SPAWN_SUBAGENT'] == {'arg': 'Editor', 'body': 't'}
                  and old['REQUEST_ELEVATION'] == {'arg': 'r', 'body': 'd'},
                  [old, '— the point of the rewrite is the DEFAULT; the tools '
                   'that had a case must not notice it happened'])
            check('...including the two whose argument is built from two fields',
                  old['HIRE_AGENT']['arg'] == 'Vera · Analyst'
                  and old['HIRE_AGENT']['body'] == 'w',
                  old['HIRE_AGENT'])

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

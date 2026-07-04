#!/usr/bin/env python3
"""Grammar parity test — night_runner.py vs hq-runtime.jsx TOOL_REGISTRY.

The night runner re-implements the bracket-marker tool grammar in Python; the
two implementations MUST stay textually identical or day/night agents drift
apart silently. This extracts the `re: /.../i` source for every tool the night
shift uses from hq-runtime.jsx and compares byte-for-byte with
night_runner._TOOL_RE_SRC, then runs behavioral fixtures through the compiled
Python regexes. Run: python3 scripts/test_night_grammar.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import night_runner  # noqa: E402


def extract_js_regexes(src):
    """Map tool NAME → regex source for every `name: 'X', … re: /…/i` entry."""
    out = {}
    for m in re.finditer(
            r"name:\s*'([A-Z_]+)',\s*(?:/\*[\s\S]*?\*/\s*)?re:\s*/((?:[^/\\]|\\.)+)/i", src):
        out[m.group(1)] = m.group(2)
    return out


def main():
    with open(os.path.join(ROOT, 'hq-runtime.jsx'), 'r', encoding='utf-8') as f:
        js = extract_js_regexes(f.read())
    failures = 0

    # 1. Textual parity for every night-shift tool.
    for name, py_src in night_runner._TOOL_RE_SRC.items():
        js_src = js.get(name)
        if js_src is None:
            print('FAIL %-14s missing from hq-runtime.jsx TOOL_REGISTRY' % name)
            failures += 1
        elif js_src != py_src:
            print('FAIL %-14s drift\n  js: %s\n  py: %s' % (name, js_src, py_src))
            failures += 1
        else:
            print('PASS %-14s textual match' % name)

    # 2. The night subset must NEVER include the day-only dangerous tools.
    for banned in ('BASH', 'FILE_WRITE', 'WALLET_SEND', 'PUBLISH_SITE',
                   'EXPORT_PDF', 'GENERATE_IMAGE'):
        if banned in night_runner._TOOL_RE_SRC:
            print('FAIL %-14s must not be night-callable' % banned)
            failures += 1
    print('PASS night subset excludes BASH/FILE_WRITE/WALLET/PUBLISH/EXPORT/GENERATE')

    # 3. Behavioral fixtures through the compiled Python regexes.
    fixtures = [
        ('[SEARCH: icp token economics]', 'SEARCH', 'icp token economics', None),
        ('[ vault_read : Research/x.md ]', 'VAULT_READ', 'Research/x.md ', None),
        ('[VAULT_NEW: Research/a.md]\n# T\n\nbody [with] brackets\n[/VAULT_NEW]',
         'VAULT_NEW', 'Research/a.md', '# T\n\nbody [with] brackets'),
        ('[VAULT_APPEND: a.md]\nline1\nline2\n[/ VAULT_APPEND ]',
         'VAULT_APPEND', 'a.md', 'line1\nline2'),
        ('text before [DIR_LIST: /work/proj] after', 'DIR_LIST', '/work/proj', None),
        ('[BROWSER_FETCH: https://example.com/a?b=c]', 'BROWSER_FETCH',
         'https://example.com/a?b=c', None),
    ]
    for text, want_name, want_arg, want_body in fixtures:
        hit = night_runner.find_first_tool(text)
        ok = (hit is not None and hit[0] == want_name
              and hit[1] == want_arg and hit[2] == want_body)
        print('%s fixture %-13s %r' % ('PASS' if ok else 'FAIL', want_name, text[:44]))
        if not ok:
            print('   got: %r' % (hit,))
            failures += 1

    # 4. First-match-wins ordering (mirrors the browser hop loop).
    two = '[VAULT_READ: b.md] then [SEARCH: q]'
    hit = night_runner.find_first_tool(two)
    ok = hit and hit[0] == 'VAULT_READ'
    print('%s fixture first-match-wins' % ('PASS' if ok else 'FAIL'))
    failures += 0 if ok else 1

    print('\n%d failure(s)' % failures)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()

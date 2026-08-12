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
    with open(os.path.join(ROOT, 'missions.jsx'), 'r', encoding='utf-8') as f:
        missions_src = f.read()
    failures = 0

    # 0. Three numeric constants night_runner.py claims "parity with
    # missions.jsx" for, in comments, with nothing checking it. The same
    # gap as the tool-grammar parity below (section 1) already closes for
    # the regex table — these three were the ones left as a promise
    # instead of a check. Found by sweeping for the session's own recurring
    # bug shape ("two sources, one rule") rather than by tripping over a
    # live drift, unlike the harmony-parsing and dotted-naming gaps this
    # file's other fixtures record.
    m = re.search(r'maxTokens:\s*(\d+),\s*\n\s*maxToolHops:\s*(\d+),', missions_src)
    if not m:
        print('FAIL could not find missions.jsx\'s maxTokens/maxToolHops mission-runner call')
        failures += 1
    else:
        js_tokens, js_hops = int(m.group(1)), int(m.group(2))
        if js_tokens != night_runner.MAX_ITER_TOKENS:
            print('FAIL MAX_ITER_TOKENS drift: missions.jsx=%d night_runner.py=%d'
                  % (js_tokens, night_runner.MAX_ITER_TOKENS))
            failures += 1
        else:
            print('PASS MAX_ITER_TOKENS parity (%d)' % night_runner.MAX_ITER_TOKENS)
        if js_hops != night_runner.MAX_TOOL_HOPS:
            print('FAIL MAX_TOOL_HOPS drift: missions.jsx=%d night_runner.py=%d'
                  % (js_hops, night_runner.MAX_TOOL_HOPS))
            failures += 1
        else:
            print('PASS MAX_TOOL_HOPS parity (%d)' % night_runner.MAX_TOOL_HOPS)

    m = re.search(r'\(m\.errors \|\| 0\) >= (\d+)\)', missions_src)
    if not m:
        print('FAIL could not find missions.jsx\'s auto-pause threshold')
        failures += 1
    elif int(m.group(1)) != night_runner.ERROR_STREAK_AUTO_PAUSE:
        print('FAIL ERROR_STREAK_AUTO_PAUSE drift: missions.jsx=%d night_runner.py=%d'
              % (int(m.group(1)), night_runner.ERROR_STREAK_AUTO_PAUSE))
        failures += 1
    else:
        print('PASS ERROR_STREAK_AUTO_PAUSE parity (%d)' % night_runner.ERROR_STREAK_AUTO_PAUSE)

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

    # 5. Harmony fallback — the gap a LIVE run found, not a hypothesis. A
    # scheduled mission on Ollama's llama3.1 (this office's own zero-config
    # hire) ran clean end to end — iterations: 1, errors: 0 — and wrote
    # NOTHING, because its reply was harmony syntax this function had no
    # regex for: "<|channel|>commentary to=browser_fetch<|message|>
    # {"url":"..."}" . The hop loop's `if not hit: break` fired on turn
    # one, and the run reported SUCCESS having done nothing at all — worse
    # than an honest error, since a quiet night and a broken tool-call
    # format read identically in the morning report. The browser side
    # already carries this exact fix for "gpt-oss-20b, qwen-3, and other
    # OSS models" (hq-runtime.jsx's extractHarmonyToolCalls) — both of
    # which this machine's own LM Studio catalog actually offers, so this
    # was the other half of a fix that had only shipped to chat.
    harmony_fixtures = [
        # the exact text captured from the live failing run
        ('<|channel|>commentary to=browser_fetch <|constrain|>json<|message|>'
         '{"url":"https://en.wikipedia.org/wiki/Meander"}',
         'BROWSER_FETCH', 'https://en.wikipedia.org/wiki/Meander', None),
        ('<|channel|>commentary to=vault_new <|message|>'
         '{"path":"Research/x.md","content":"# Title\\nBody text"}',
         'VAULT_NEW', 'Research/x.md', '# Title\nBody text'),
        ('<|channel|>commentary to=functions.search <|message|>{"query":"river deltas"}',
         'SEARCH', 'river deltas', None),
    ]
    for text, want_name, want_arg, want_body in harmony_fixtures:
        hit = night_runner.find_first_tool(text)
        ok = (hit is not None and hit[0] == want_name
              and hit[1] == want_arg and hit[2] == want_body)
        print('%s harmony fixture %-13s %r' % ('PASS' if ok else 'FAIL', want_name, text[:50]))
        if not ok:
            print('   got: %r' % (hit,))
            failures += 1

    # Dotted tool naming — a SECOND live-observed shape from the same
    # model, in a different run: "browser.fetch" instead of
    # "browser_fetch" (plus an extra unrelated "id" field). One fold-dots-
    # to-underscores normalization step covers both, and the namespaced
    # form too.
    dotted_fixtures = [
        ('<|channel|>commentary to=browser.fetch <|constrain|>json<|message|>'
         '{"id":"1","url":"https://en.wikipedia.org/wiki/Delta_(finance)"}',
         'BROWSER_FETCH', 'https://en.wikipedia.org/wiki/Delta_(finance)'),
        ('<|channel|>commentary to=functions.browser.fetch <|message|>{"url":"https://x.com"}',
         'BROWSER_FETCH', 'https://x.com'),
        ('<|channel|>commentary to=vault.new <|message|>{"path":"Research/x.md","content":"body"}',
         'VAULT_NEW', 'Research/x.md'),
    ]
    for text, want_name, want_arg in dotted_fixtures:
        hit = night_runner.find_first_tool(text)
        ok = hit is not None and hit[0] == want_name and hit[1] == want_arg
        print('%s dotted-namespace fixture %-13s %r' % ('PASS' if ok else 'FAIL', want_name, text[:50]))
        if not ok:
            print('   got: %r' % (hit,))
            failures += 1

    # A harmony call to a tool night shift doesn't support (DM_TO, HIRE_*,
    # anything outside TOOL_RES) must be ignored, not fabricated into one
    # of the eight it does understand.
    unsupported = night_runner.find_first_tool(
        '<|channel|>commentary to=functions.dm_to <|message|>{"to":"Nano","message":"hi"}')
    ok = unsupported is None
    print('%s harmony call to an unsupported tool is ignored' % ('PASS' if ok else 'FAIL'))
    if not ok:
        print('   got: %r' % (unsupported,))
    failures += 0 if ok else 1

    # Bracket format must still win when both are present in one reply —
    # the harmony fallback only fires when the bracket scan finds nothing.
    both = '[SEARCH: bracket wins] <|channel|>commentary to=vault_read <|message|>{"path":"x"}'
    hit = night_runner.find_first_tool(both)
    ok = hit and hit[0] == 'SEARCH'
    print('%s bracket format still wins over harmony when both present' % ('PASS' if ok else 'FAIL'))
    if not ok:
        print('   got: %r' % (hit,))
    failures += 0 if ok else 1

    # 6. run_iteration end-to-end: a model that narrates "Wrote 1" without
    # ever calling VAULT_NEW/VAULT_APPEND must come back as an honest
    # error, not a silent success. Watched live on the harmony fix's own
    # retest: iterations: 1, errors: 0, writes: [], reply ending "Wrote 1.
    # Next iteration could explore..." — a run that reported success while
    # the vault gained nothing. The prompt's own closing rule is what
    # invites this ("End your reply with a plain status line: 'Wrote X.'"
    # sounds like a wrap-up sentence, not evidence gated on a real write),
    # so the fix is two-layered: build_prompt now says the write is a
    # mandatory TOOL CALL and the status line only follows it; this test
    # covers the belt-and-suspenders half — small models will still
    # sometimes skip it, and a claim with nothing behind it must not pass
    # as a quiet, honest night.
    real_llm_call = night_runner.llm_call

    def fake_llm_call_narrates_no_write(ctx, messages, max_tokens=None):
        return ("Reviewed the topic and found good material. "
                "Wrote 1. Next iteration could explore a related angle."), 42

    def fake_llm_call_honest_quiet_night(ctx, messages, max_tokens=None):
        return "Nothing new to add this round — will look again next iteration.", 10

    def fake_llm_call_real_write(ctx, messages, max_tokens=None):
        if len(messages) <= 2:
            return ('[VAULT_NEW: Research/x.md]\n# X\n\nreal content\n[/VAULT_NEW]'), 30
        return "Wrote 1. Next iteration could explore Y.", 15

    class _FakeCtx(object):
        brave_key = ''

    night_runner.llm_call = fake_llm_call_narrates_no_write
    res = night_runner.run_iteration(_FakeCtx(), {'vaultFolder': 'Research/x', 'agentName': 'Test'}, 0, 1)
    # NOT `'VAULT_NEW' in res['error']` — this string lands verbatim in the
    # morning Gazette, and asserting the token by name is what kept it
    # there: §6 bans wire-format names on a human surface, and the
    # Gazette's own 60-char slice cut the sentence at exactly the end of
    # the tokens, leaving jargon and deleting "nothing landed in the
    # vault". Assert the MEANING instead, so the wording stays free to be
    # human while the detector stays pinned.
    ok = ((not res['writes']) and res['error'] is not None
          and re.search(r'said it (?:saved|wrote)', res['error'], re.I)
          and re.search(r'nothing (?:reached|landed)', res['error'], re.I)
          and 'VAULT_NEW' not in res['error'])
    print('%s run_iteration: a fabricated "Wrote 1" with no write is an honest error' % ('PASS' if ok else 'FAIL'))
    if not ok:
        print('   got: %r' % (res,))
    failures += 0 if ok else 1

    night_runner.llm_call = fake_llm_call_honest_quiet_night
    res = night_runner.run_iteration(_FakeCtx(), {'vaultFolder': 'Research/x', 'agentName': 'Test'}, 0, 1)
    ok = (not res['writes']) and res['error'] is None
    print('%s run_iteration: an honest quiet night is NOT an error' % ('PASS' if ok else 'FAIL'))
    if not ok:
        print('   got: %r' % (res,))
    failures += 0 if ok else 1

    orig_run_tool = night_runner.run_tool
    night_runner.run_tool = lambda ctx, name, arg, body: 'Wrote %d chars → %s' % (len(body or ''), arg)
    night_runner.llm_call = fake_llm_call_real_write
    res = night_runner.run_iteration(_FakeCtx(), {'vaultFolder': 'Research/x', 'agentName': 'Test'}, 0, 1)
    ok = len(res['writes']) == 1 and res['error'] is None
    print('%s run_iteration: a REAL VAULT_NEW call is not flagged' % ('PASS' if ok else 'FAIL'))
    if not ok:
        print('   got: %r' % (res,))
    failures += 0 if ok else 1
    night_runner.run_tool = orig_run_tool
    night_runner.llm_call = real_llm_call

    print('\n%d failure(s)' % failures)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()

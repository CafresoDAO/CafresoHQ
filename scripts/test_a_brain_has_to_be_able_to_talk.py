#!/usr/bin/env python3
"""The hire form offered an embedding model as a brain.

Measured on a live office, BRING IN A HELPER -> NEW HIRE, the BRAIN
picker. Thirty-nine options, one of them:

    text-embedding-nomic-embed-text-v1.5

An embedding model cannot hold a conversation. Hiring it seats a coworker
at a desk with a name, a job description and a job title, who then fails
every task forever. The only clue available to the boss is the model's own
id, which needs you to already know what an embedding model is — precisely
the expertise the north star says nobody should need.

The office was not guessing and did not lack the facts.
`lmStudioModelDetails` reads LM Studio's /api/v0/models and carries `type`
back on every row; LM Studio reports this one as `type: "embeddings"` in
the same response the office already parsed. `localModelOptions` then
mapped over the list and used only `id` and `state`. The evidence was
fetched, held, and dropped one line before it would have mattered.

Same shape as the front-desk finding: a capability offered with nothing
behind it, one layer further down. Worse in one respect — the front desk
merely described a tool that did not exist, while this hands the boss a
hire that is guaranteed to fail and looks exactly like the ones that work.

Two things this pins, and both are the interesting half:

- `vlm` stays. Vision-language models chat fine, and there were five of
  them; a filter that kept only `llm` would have deleted most of the
  boss's usable local models to fix one bad row.
- An untyped row stays. `lmStudioModelDetails` has a fallback that returns
  bare `{id}` when /api/v0/models is unavailable, so "no type" is the
  normal shape on a whole class of setups. Dropping untyped rows would
  empty the group on exactly the installs least able to diagnose it. Only
  a STATED non-chat type is evidence.

Run: python3 scripts/test_a_brain_has_to_be_able_to_talk.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / 'claude-client.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)//.*$', '', src)


def main():
    print('a brain has to be able to hold a conversation')
    src = CLIENT.read_text(encoding='utf-8')

    # ── 1. the fact is still fetched ─────────────────────────────────────
    details = brace_lift(src, 'async function lmStudioModelDetails() {')
    check('the office still asks LM Studio what each model is',
          're.type' not in details and 'type: m.type' in details,
          'the filter below is only as good as this field; if the fetch '
          'stops carrying `type` the filter silently passes everything')
    check('...from the endpoint that reports it',
          "'/api/v0/models'" in details,
          '/v1/models is the OpenAI-compatible shape and has no type')

    # ── 2. and now actually used ─────────────────────────────────────────
    opts = strip_comments(brace_lift(src, 'async function localModelOptions() {'))
    check('the LM Studio group is filtered before it is offered',
          re.search(r'lm\.filter\(', opts),
          'localModelOptions mapped straight over the raw list, so every '
          'row LM Studio reported became a hireable brain')
    check('...on the type field, not the model id',
          re.search(r'CHATLESS\.has\(String\(m\.type', opts),
          'matching on the name would be guessing; the type is stated')
    check('...and the filtered list is what gets offered',
          re.search(r'if \(lmChat\.length\)', opts)
          and re.search(r'options: lmChat\.map', opts),
          'filtering into a new list and then rendering the old one is a '
          'real way to write this fix and have it do nothing')

    # ── 3. the two deliberate non-filters ────────────────────────────────
    chatless = re.search(r"const CHATLESS = new Set\(\[([^\]]*)\]\)", opts)
    check('the chatless set exists and is narrow', bool(chatless), opts[:200])
    kinds = set(re.findall(r"'(\w+)'", chatless.group(1))) if chatless else set()
    check('...and names only embeddings',
          kinds <= {'embeddings', 'embedding'},
          f'{sorted(kinds)} — vlm chats fine and there were five of them; '
          'widening this deletes the usable local models too')

    # ── 4. run it over the real measured roster ──────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arm')
        return 1 if FAILS else 0

    # Verbatim from `curl /lmstudio/api/v0/models` on the machine where
    # this was found, types included.
    roster = [
        {'id': 'qwen/qwen3.5-9b', 'type': 'vlm'},
        {'id': 'qwen/qwen3-vl-8b', 'type': 'vlm'},
        {'id': 'google/gemma-4-12b-qat', 'type': 'vlm'},
        {'id': 'gemma-4-e4b-uncensored-hauhaucs-aggressive', 'type': 'vlm'},
        {'id': 'nsfw_wan_14b-video', 'type': 'llm'},
        {'id': 'meta-llama-3.1-8b-instruct', 'type': 'llm'},
        {'id': 'google/gemma-4-e4b', 'type': 'vlm'},
        {'id': 'nvidia/nemotron-3-nano', 'type': 'llm'},
        {'id': 'mistralai/ministral-3-14b-reasoning', 'type': 'vlm'},
        {'id': 'openai/gpt-oss-20b', 'type': 'llm'},
        {'id': 'nvidia/nemotron-3-nano-4b', 'type': 'llm'},
        {'id': 'text-embedding-nomic-embed-text-v1.5', 'type': 'embeddings'},
        # The fallback path's shape: no /api/v0/models, so no type at all.
        {'id': 'some-model-from-the-v1-fallback'},
    ]
    body = re.search(r'const CHATLESS = new Set\(\[[^\]]*\]\);\s*\n\s*const lmChat = lm\.filter\([^\n]*\);',
                     opts)
    # A missing filter is the defect this file exists for, so it has to be
    # a named failure. Raising here instead made the run die with a
    # traceback and no FAILED line -- a test that crashes is not a test
    # that reports, which the fire test caught on the very first arm.
    check('the filter is still there to be run', bool(body),
          'no `const CHATLESS = ...` + `const lmChat = lm.filter(...)` pair '
          'in localModelOptions, so nothing filters the picker')
    if not body:
        print()
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    js = ('const lm = %s;\n' % json.dumps(roster)) + body.group(0) + \
         '\nconsole.log(JSON.stringify(lmChat.map(m => m.id)));'
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1200:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    kept = json.loads(p.stdout.strip().split('\n')[-1])

    check('the embedding model is not offered as a brain',
          'text-embedding-nomic-embed-text-v1.5' not in kept, kept)
    check('every vision-language model survives',
          all(m['id'] in kept for m in roster if m.get('type') == 'vlm'),
          [m['id'] for m in roster if m.get('type') == 'vlm' and m['id'] not in kept])
    check('every plain chat model survives',
          all(m['id'] in kept for m in roster if m.get('type') == 'llm'),
          [m['id'] for m in roster if m.get('type') == 'llm' and m['id'] not in kept])
    check('an untyped row from the fallback path survives',
          'some-model-from-the-v1-fallback' in kept,
          'no type is the normal shape when /api/v0/models is unreachable; '
          'dropping those empties the group on the setups that need it most')
    check('exactly one row was removed', len(kept) == len(roster) - 1,
          f'{len(roster)} in, {len(kept)} out')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

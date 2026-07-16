#!/usr/bin/env python3
"""Deep-research worker loop tests — serve._sw_deep and its helpers.

The deep path makes several LLM calls (plan → note-per-angle → synthesis) and
several Brave calls. Rather than stand up an HTTP fake, we stub the two seams
every step funnels through — `_sw_brave` (search) and `_sw_complete` (LLM) — and
assert the ORCHESTRATION: angles parsed, a note page per angle, budget guard,
synthesis + its fallback, and the research-tree graph shape (topic nodes carry a
`page` attr; source nodes carry url/domain).

No network, no GPU. Run: python3 scripts/test_deep_research.py
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SEARCH_WORKER', '')      # never start the worker loop
import serve  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── stubs ────────────────────────────────────────────────────────────────────
BRAVE_CALLS = []


def fake_brave(q, deadline=None, kind='human'):
    BRAVE_CALLS.append((q, kind))
    return [
        {'title': 'Source A for ' + q[:20], 'url': 'https://a.example/' + str(len(BRAVE_CALLS)),
         'description': 'Some evidence about ' + q},
        {'title': 'Source B for ' + q[:20], 'url': 'https://b.example/' + str(len(BRAVE_CALLS)),
         'description': 'More detail regarding ' + q},
    ]


def fake_complete(prompt, deadline, max_tokens=600, schema=None):
    """Prompt-aware fake: the deep steps have distinguishable prompts."""
    if 'sub-questions ("angles")' in prompt:
        return (json.dumps({'angles': ['What is the mechanism?', 'What is the evidence?',
                                       'What are the trade-offs?']}),
                'test-model', 42, 'direct')
    if 'ONE section of a research report' in prompt:
        return (json.dumps({'title': 'Section Title', 'body': 'A clear takeaway. '
                            'Detail with citations [1][2].'}), 'test-model', 30, 'direct')
    if 'executive summary' in prompt:
        return ('A cohesive synthesis answering the question across all angles.',
                'test-model', 25, 'direct')
    return ('', '', 0, '')


def with_stubs(brave=fake_brave, complete=fake_complete):
    serve._sw_brave = brave
    serve._sw_complete = complete
    BRAVE_CALLS.clear()


# ── tests ────────────────────────────────────────────────────────────────────
def test_json_obj():
    print('_sw_json_obj')
    check('parses fenced object', serve._sw_json_obj('```json\n{"a":1}\n```') == {'a': 1})
    check('parses bare array', serve._sw_json_obj('junk [1,2,3] tail') == [1, 2, 3])
    check('None on garbage', serve._sw_json_obj('not json at all') is None)


def test_happy_path():
    print('deep happy path')
    with_stubs()
    out = serve._sw_deep('How does X work?', time.monotonic() + 300)
    check('returned a result (not degraded)', out is not None)
    answer, model, pages, graph, tokens, sources = out
    check('3 note pages (one per angle)', len(pages) == 3, len(pages))
    check('each page has body + title + question',
          all(p['body'] and p['title'] and p['question'] for p in pages))
    check('page ids are t0..t2', [p['id'] for p in pages] == ['t0', 't1', 't2'])
    check('answer is the synthesis', 'cohesive synthesis' in answer, answer[:40])
    check('tokens summed across steps', tokens > 0, tokens)
    check('brave used the deep lane', all(k == 'deep' for _, k in BRAVE_CALLS) and len(BRAVE_CALLS) == 3, BRAVE_CALLS)
    check('sources returned', len(sources) == 6, len(sources))


def test_graph_shape():
    print('research-tree graph shape')
    with_stubs()
    out = serve._sw_deep('How does X work?', time.monotonic() + 300)
    g = json.loads(out[3])
    nodes = {n['key']: n['attributes'] for n in g['graph']['nodes']}
    check('has a query hub', nodes.get('q', {}).get('kind') == 'query')
    topics = [k for k, a in nodes.items() if a.get('kind') == 'topic']
    check('3 topic nodes', len(topics) == 3, topics)
    check('every topic carries a `page` attr the viewer can open',
          all(nodes[t].get('page') for t in topics), {t: nodes[t].get('page') for t in topics})
    srcs = [a for a in nodes.values() if a.get('kind') == 'source']
    check('source nodes carry url + domain', srcs and all(s.get('url') and s.get('domain') for s in srcs))
    check('title marks it deep research', g['title'].startswith('Deep research:'), g['title'])


def test_degrades_when_planning_fails():
    print('degrade paths')
    with_stubs(complete=lambda *a, **k: ('', '', 0, ''))   # LLM unreachable
    check('planning failure → None (caller degrades to single-shot)',
          serve._sw_deep('q', time.monotonic() + 300) is None)

    # Brave returns nothing for every angle → no pages → degrade.
    with_stubs(brave=lambda *a, **k: [])
    check('no sources on any angle → None', serve._sw_deep('q', time.monotonic() + 300) is None)


def test_synth_fallback():
    print('synthesis fallback')

    def no_synth(prompt, deadline, max_tokens=600, schema=None):
        if 'executive summary' in prompt:
            return ('', '', 0, '')          # synthesis step fails
        return fake_complete(prompt, deadline, max_tokens, schema)
    with_stubs(complete=no_synth)
    out = serve._sw_deep('How does X work?', time.monotonic() + 300)
    check('still returns a result when synthesis fails', out is not None)
    check('answer stitched from page takeaways', out and bool(out[0]), out and out[0][:40])


def test_budget_guard():
    print('budget guard')
    with_stubs()
    # A deadline already inside the 45s reserve → stop before any page.
    out = serve._sw_deep('q', time.monotonic() + 10)
    check('near-deadline stops early → None (no pages)', out is None)


def main():
    test_json_obj()
    test_happy_path()
    test_graph_shape()
    test_degrades_when_planning_fails()
    test_synth_fallback()
    test_budget_guard()
    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'deep research: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

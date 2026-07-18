#!/usr/bin/env python3
"""Deep-research worker loop tests — serve._sw_deep_step / _sw_process_deep.

Deep research is RESUMABLE: one angle per claim, checkpointed via the
'progress' worker op, resumed later from the JSON a prior checkpoint left.
Only the last angle synthesizes + calls 'fulfill'. Rather than stand up an
HTTP fake for the canister, we stub the three seams every step funnels
through — `_sw_brave` (search), `_sw_complete` (LLM), and `_sw_call` (the
canister worker API) — and assert the ORCHESTRATION: angles parsed, one
checkpoint per claim, correct resume-from-progress, the terminal
synthesis/fulfill, the all-dry-angles fail path, and the research-tree graph
shape (topic nodes carry a `page` attr; source nodes carry url/domain).

No network, no GPU. Run: python3 scripts/test_deep_research.py
"""
import json
import os
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
WORKER_CALLS = []   # [(op, lines)] — captures every _sw_call the code under test makes


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


def fake_call(op, lines):
    WORKER_CALLS.append((op, list(lines)))
    return 200, {'ok': True, 'libraryId': 'lib_test'}


def with_stubs(brave=fake_brave, complete=fake_complete, call=fake_call):
    serve._sw_brave = brave
    serve._sw_complete = complete
    serve._sw_call = call
    BRAVE_CALLS.clear()
    WORKER_CALLS.clear()


def run_all_steps(q, deadline_seconds=300, max_topics=None):
    """Drives _sw_deep_step to completion the way real claims would: each call
    feeds the PREVIOUS call's state back in as progress_in. Returns the list
    of intermediate states (last one has done=True), or None if it degraded."""
    states = []
    progress_in = None
    while True:
        state = serve._sw_deep_step(q, time.monotonic() + deadline_seconds, progress_in, max_topics)
        if state is None:
            return None if not states else states   # degrade on the very first claim
        states.append(state)
        if state['done']:
            return states
        progress_in = state
        if len(states) > 20:
            raise RuntimeError('runaway loop — done never became true')


def run_full_job(q, deadline_seconds=300, max_topics=None):
    """Simulates the full multi-claim job lifecycle through _sw_process_deep,
    including the terminal fulfill/fail call. `job` mimics exactly what the
    canister's claim response hands the worker each time."""
    progress = ''
    topics = str(max_topics) if max_topics else ''
    handled_count = 0
    while True:
        job = {'id': 'j001', 'q': q, 'mode': 'deep', 'topics': topics, 'progress': progress}
        handled = serve._sw_process_deep(job, 'j001', q, time.monotonic() + deadline_seconds,
                                         time.monotonic(), lambda s: s)
        if not handled:
            return None, handled_count           # degraded
        handled_count += 1
        last_op, last_lines = WORKER_CALLS[-1]
        if last_op == 'fulfill':
            return ('fulfill', last_lines), handled_count
        if last_op == 'fail':
            return ('fail', last_lines), handled_count
        # last_op == 'progress': lines[1] is the checkpoint JSON this claim posted
        progress = last_lines[1]
        if handled_count > 20:
            raise RuntimeError('runaway loop — never reached fulfill/fail')


# ── tests ────────────────────────────────────────────────────────────────────
def test_json_obj():
    print('_sw_json_obj')
    check('parses fenced object', serve._sw_json_obj('```json\n{"a":1}\n```') == {'a': 1})
    check('parses bare array', serve._sw_json_obj('junk [1,2,3] tail') == [1, 2, 3])
    check('None on garbage', serve._sw_json_obj('not json at all') is None)


def test_step_resumable_happy_path():
    print('deep step-by-step happy path')
    with_stubs()
    states = run_all_steps('How does X work?')
    check('completed (not degraded)', states is not None)
    check('exactly 3 checkpoints (one per angle)', len(states) == 3, len(states) if states else None)
    check('only the LAST state is done', [s['done'] for s in states] == [False, False, True])
    check('nextAngle counts up 1,2,3', [s['nextAngle'] for s in states] == [1, 2, 3])
    final_pages = states[-1]['pages']
    check('3 note pages total', len(final_pages) == 3, len(final_pages))
    check('each page has body + title + question + ranAt',
          all(p['body'] and p['title'] and p['question'] and p.get('ranAt') for p in final_pages))
    check('page ids are t0..t2', [p['id'] for p in final_pages] == ['t0', 't1', 't2'])
    check('tokens accumulate monotonically across checkpoints',
          states[0]['tokens'] < states[1]['tokens'] < states[2]['tokens'],
          [s['tokens'] for s in states])
    check('brave used the deep lane once per checkpoint',
          all(k == 'deep' for _, k in BRAVE_CALLS) and len(BRAVE_CALLS) == 3, BRAVE_CALLS)


def test_resume_from_serialized_progress():
    print('resume from a JSON-round-tripped checkpoint (as the canister stores it)')
    with_stubs()
    first = serve._sw_deep_step('How does X work?', time.monotonic() + 300, None, None)
    check('first claim produced one page, not done', len(first['pages']) == 1 and not first['done'])
    # Round-trip through JSON exactly like the canister's opaque progress blob.
    resumed_in = json.loads(json.dumps(first))
    second = serve._sw_deep_step('How does X work?', time.monotonic() + 300, resumed_in, None)
    check('second claim advances to 2 pages', len(second['pages']) == 2, len(second['pages']))
    check('first page preserved verbatim across the resume', second['pages'][0] == first['pages'][0])


def test_custom_topic_count():
    print('submitter-requested topic count')
    with_stubs()
    states = run_all_steps('How does X work?', max_topics=2)
    # fake_complete always offers 3 angles; max_topics=2 caps how many _sw_deep_plan keeps.
    check('capped to 2 angles when 2 requested', len(states[-1]['pages']) == 2, len(states[-1]['pages']))


def test_full_job_terminal_fulfill():
    print('full job lifecycle → terminal fulfill')
    with_stubs()
    result, handled_count = run_full_job('How does X work?')
    check('reached fulfill (not degraded)', result is not None and result[0] == 'fulfill')
    check('exactly 3 claims total (2 progress + 1 fulfill)', handled_count == 3, handled_count)
    ops = [op for op, _ in WORKER_CALLS]
    check('op sequence is progress, progress, fulfill', ops == ['progress', 'progress', 'fulfill'], ops)
    fulfill_lines = result[1]
    check('answer is the synthesis', 'cohesive synthesis' in fulfill_lines[3], fulfill_lines[3][:60])
    pages_json = json.loads(__import__('urllib.parse', fromlist=['unquote']).unquote(fulfill_lines[-1]))
    check('fulfilled pages JSON carries all 3 pages', len(pages_json['pages']) == 3, len(pages_json['pages']))


def test_graph_shape():
    print('research-tree graph shape')
    with_stubs()
    states = run_all_steps('How does X work?')
    graph = serve._sw_deep_graph('How does X work?', states[-1]['pages'])
    g = json.loads(graph)
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
    print('degrade path: planning fails on the very first claim')
    with_stubs(complete=lambda *a, **k: ('', '', 0, ''))   # LLM unreachable
    check('planning failure → None (caller degrades to single-shot)',
          serve._sw_deep_step('q', time.monotonic() + 300, None, None) is None)


def test_all_angles_dry_fails_at_terminal():
    print('every angle empty → completes the run but FAILS rather than fulfilling empty')
    with_stubs(brave=lambda *a, **k: [])   # every angle comes up dry
    result, handled_count = run_full_job('q')
    check('reached a terminal result (not stuck)', result is not None)
    check('terminal op is fail, not fulfill', result[0] == 'fail', result)
    check('dud pages were still recorded as receipts along the way, per-angle',
          handled_count == 3, handled_count)


def test_synth_fallback():
    print('synthesis fallback')

    def no_synth(prompt, deadline, max_tokens=600, schema=None):
        if 'executive summary' in prompt:
            return ('', '', 0, '')          # synthesis step fails
        return fake_complete(prompt, deadline, max_tokens, schema)
    with_stubs(complete=no_synth)
    result, _ = run_full_job('How does X work?')
    check('still fulfills when synthesis fails', result is not None and result[0] == 'fulfill')
    check('answer stitched from page takeaways', bool(result[1][3]), result[1][3][:40])


def test_budget_guard():
    print('budget guard')
    with_stubs()
    # A deadline already inside the 45s reserve → the very first claim can't
    # even attempt one angle, and with zero pages ever produced, degrades.
    out = serve._sw_deep_step('q', time.monotonic() + 10, None, None)
    check('near-deadline first claim → None (no pages ever produced)', out is None)


def main():
    test_json_obj()
    test_step_resumable_happy_path()
    test_resume_from_serialized_progress()
    test_custom_topic_count()
    test_full_job_terminal_fulfill()
    test_graph_shape()
    test_degrades_when_planning_fails()
    test_all_angles_dry_fails_at_terminal()
    test_synth_fallback()
    test_budget_guard()
    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'deep research: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

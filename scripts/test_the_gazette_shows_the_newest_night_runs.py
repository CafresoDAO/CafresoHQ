#!/usr/bin/env python3
"""The Gazette's lead story showed the STALEST runs, not the newest.

hq-state/mission-runs.json is append order: oldest run first, newest run
last. app.jsx's Gazette effect keeps the newest 10 with `.slice(-10)` — but
that slice preserves the oldest-first order of the KEPT window, and
MorningReportModal (features.jsx) reads the front of that array with
`.slice(0, 5)` expecting "front of list = most recent" (the same convention
NightShiftSection already uses two hundred lines away via `.slice(-5).reverse()`).
So a night with more than 5 qualifying runs led with the 5 OLDEST of the kept
window, silently dropping the freshest ones from the "while you were away"
report.

This test extracts the REAL filter/cap expression from app.jsx's Gazette
effect (by locating it via its section comment + `useEffectA` block, brace-
balanced) and the REAL slice from features.jsx's MorningReportModal (by
locating the whole named function, brace-balanced), then runs both — for
real, under Node, against a pinned synthetic run log — end to end.

Run: python3 scripts/test_the_gazette_shows_the_newest_night_runs.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read(name):
    with open(os.path.join(ROOT, name), 'r', encoding='utf-8') as f:
        return f.read()


def find_balanced_end(src, start_idx, open_ch, close_ch):
    """src[start_idx] must be open_ch. Return the index of the matching
    close_ch, treating '...'/"..."/`...` and // and /* */ as opaque, and
    correctly resuming code-mode inside a template literal's `${ ... }`."""
    assert src[start_idx] == open_ch, repr(src[start_idx])
    stack = [open_ch]
    i = start_idx + 1
    n = len(src)
    while i < n:
        c = src[i]
        top = stack[-1]
        if top in ('"', "'"):
            if c == '\\':
                i += 2; continue
            if c == top:
                stack.pop()
            i += 1; continue
        if top == '`':
            if c == '\\':
                i += 2; continue
            if c == '`':
                stack.pop(); i += 1; continue
            if c == '$' and i + 1 < n and src[i + 1] == '{':
                stack.append('DOLLAR{'); i += 2; continue
            i += 1; continue
        # code mode (top is a bracket frame or 'DOLLAR{')
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i); i = n if j == -1 else j; continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2); i = n if j == -1 else j + 2; continue
        if c in ('"', "'", '`'):
            stack.append(c); i += 1; continue
        if c in '({[':
            stack.append(c); i += 1; continue
        if c in ')}]':
            want = {'}': '{', ')': '(', ']': '['}[c]
            if top == 'DOLLAR{' and c == '}':
                stack.pop(); i += 1; continue
            if top == want:
                stack.pop()
                if not stack:
                    return i
                i += 1; continue
            i += 1; continue  # mismatched — tolerate, keep scanning
        i += 1
    raise ValueError('unbalanced %r for %r starting at %d' % (close_ch, open_ch, start_idx))


def component(src, name):
    """Locate a top-level `function NAME(...) { ... }` by NAME and return its
    full source text (param list + body), brace/paren-balanced to its end."""
    m = re.search(r'\nfunction\s+' + re.escape(name) + r'\s*\(', src)
    assert m, 'component not found: ' + name
    paren_start = src.index('(', m.start())
    paren_end = find_balanced_end(src, paren_start, '(', ')')
    brace_start = src.index('{', paren_end)
    brace_end = find_balanced_end(src, brace_start, '{', '}')
    return src[m.start() + 1:brace_end + 1]


def prop_value(src, prop_name):
    """Find `NAME:` and return the exact RHS expression text up to the next
    top-level comma (bracket-depth 0) — unlike a naive regex, this doesn't
    truncate at a comma nested inside the expression's own arguments, e.g.
    `nightRuns: nightRuns.slice(0, 10).reverse(),`."""
    m = re.search(r'\b' + re.escape(prop_name) + r':\s*', src)
    assert m, 'property not found: ' + prop_name
    i = m.end()
    n = len(src)
    depth = 0
    j = i
    while j < n:
        c = src[j]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == ',' and depth == 0:
            break
        j += 1
    return src[i:j].strip()


def block_after(src, anchor_text, open_pattern):
    """Find anchor_text (a section comment), then the next match of
    open_pattern (must end just past the block's opening '{'), and return the
    block's source text brace-balanced to its end."""
    ci = src.index(anchor_text)
    m = re.search(open_pattern, src[ci:])
    assert m, 'block not found after anchor %r' % anchor_text
    brace_idx = ci + m.end() - 1
    assert src[brace_idx] == '{', src[brace_idx - 5:brace_idx + 5]
    end = find_balanced_end(src, brace_idx, '{', '}')
    return src[ci + m.start():end + 1]


# ---- locate the real code -------------------------------------------------
app_src = read('app.jsx')
feat_src = read('features.jsx')

gazette_block = block_after(
    app_src, 'Morning Report ("HQ GAZETTE")', r'useEffectA\(\(\)\s*=>\s*\{')

filter_m = re.search(
    r'nightRuns = \(j\.runs \|\| \[\]\)\.filter\([^;]*\);', gazette_block)
assert filter_m, 'filter statement not found inside the Gazette effect block'
FILTER_STMT = filter_m.group(0)

CAP_EXPR = prop_value(gazette_block, 'nightRuns')

# Array-reordering methods safe to chain onto the extracted expression. Stops
# BEFORE `.map(...)` deliberately — the real code's .map(...) callback returns
# JSX, which isn't valid plain-Node JS, and the ordering bug lives in what
# .slice/.reverse/.sort feed to that .map, not in the render itself.
_CHAINABLE = ('reverse', 'sort', 'filter', 'slice')


def call_chain(src, start_text):
    """From the first occurrence of start_text (ending just past its opening
    '('), extract `start_text(...)` plus any immediately-chained
    `.reverse()/.sort()/.filter()/.slice()` calls, each brace/paren-balanced —
    so a changed slice count OR an added `.sort(...)` is picked up as real
    current code, not hardcoded."""
    i = src.index(start_text)
    open_idx = i + len(start_text) - 1
    assert src[open_idx] == '(', src[i:i + len(start_text) + 5]
    end = find_balanced_end(src, open_idx, '(', ')') + 1
    while end < len(src) and src[end] == '.':
        m = re.match(r'\.(\w+)\(', src[end:])
        if not m or m.group(1) not in _CHAINABLE:
            break
        call_open = end + m.end() - 1
        end = find_balanced_end(src, call_open, '(', ')') + 1
    return src[i:end]


modal_src = component(feat_src, 'MorningReportModal')
# Extract whatever the current call (and any chained calls) actually are —
# not hardcoded "0, 5" — so a broken slice count or an added .sort(...) is
# caught by the behavioral checks below, not by extraction itself.
MODAL_EXPR = call_chain(modal_src, 'report.nightRuns.slice(')


# ---- run the real expressions under Node, against pinned synthetic data ---
def run_harness(runs, prev_seen):
    """runs: list of dicts in ARRAY order (oldest first, like mission-runs.json).
    Returns dict with afterFilter/afterCap/displayed id lists (+ startedAt)."""
    script = (
        "const j = { runs: %s };\n"
        "const prevSeen = %d;\n"
        "let nightRuns = [];\n"
        "%s\n"
        "const report = { nightRuns: (%s) };\n"
        "const displayed = (%s);\n"
        "console.log(JSON.stringify({\n"
        "  afterFilter: nightRuns.map(r => r.id),\n"
        "  afterCap: report.nightRuns.map(r => r.id),\n"
        "  displayed: displayed.map(r => ({ id: r.id, startedAt: r.startedAt })),\n"
        "}));\n"
    ) % (json.dumps(runs), prev_seen, FILTER_STMT, CAP_EXPR, MODAL_EXPR)
    with tempfile.NamedTemporaryFile('w', suffix='.mjs', delete=False) as f:
        f.write(script)
        path = f.name
    try:
        out = subprocess.run(['node', path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    if out.returncode != 0:
        raise RuntimeError('node harness failed:\n' + out.stdout + out.stderr)
    return json.loads(out.stdout.strip().splitlines()[-1])


def run_record(rid, started, finished):
    return {
        'id': rid, 'agentName': 'TestAgent', 'topic': rid,
        'startedAt': started, 'finishedAt': finished,
        'iterations': 3, 'writes': [], 'summary': '', 'lastError': '',
    }


# 12 finished runs (run-01 .. run-12), ascending startedAt, plus one still-
# running (unfinished, finishedAt=0) run-13 that started AFTER all of them —
# real evidence that "most recent" isn't just "highest index".
MANY = [run_record('run-%02d' % i, 1000 + i * 100, 1000 + i * 100 + 50) for i in range(1, 13)]
MANY.append(run_record('run-13-unfinished', 1000 + 13 * 100, 0))

FEW = [run_record('run-A', 5000, 5050),
       run_record('run-B', 5100, 5150),
       run_record('run-C', 5200, 5250)]


def main():
    failures = []

    def check(name, cond, detail=''):
        status = 'PASS' if cond else 'FAIL'
        print('%s %s%s' % (status, name, (' — ' + detail) if detail and not cond else ''))
        if not cond:
            failures.append(name)

    many = run_harness(MANY, prev_seen=0)
    few = run_harness(FEW, prev_seen=0)

    # -- filter --
    check('check_unfinished_excluded',
          'run-13-unfinished' not in many['afterFilter'],
          'got afterFilter=%r' % many['afterFilter'])

    check('check_filter_order_preserved',
          many['afterFilter'] == ['run-%02d' % i for i in range(1, 13)],
          'got %r' % many['afterFilter'])

    # -- cap (nightRuns.slice(-10)...) --
    check('check_cap_length',
          len(many['afterCap']) == 10,
          'got len=%d %r' % (len(many['afterCap']), many['afterCap']))

    check('check_cap_newest_first',
          many['afterCap'][0] == 'run-12',
          'got afterCap[0]=%r' % (many['afterCap'][0] if many['afterCap'] else None))

    check('check_cap_drops_stale',
          'run-01' not in many['afterCap'] and 'run-02' not in many['afterCap'],
          'got afterCap=%r' % many['afterCap'])

    # -- modal (report.nightRuns.slice(0, 5)) --
    check('check_modal_count',
          len(many['displayed']) == 5,
          'got len=%d' % len(many['displayed']))

    displayed_ids = {d['id'] for d in many['displayed']}
    check('check_modal_newest_set',
          displayed_ids == {'run-08', 'run-09', 'run-10', 'run-11', 'run-12'},
          'got %r' % sorted(displayed_ids))

    started_seq = [d['startedAt'] for d in many['displayed']]
    check('check_modal_descending_order',
          started_seq == sorted(started_seq, reverse=True) and len(set(started_seq)) == len(started_seq),
          'got startedAt sequence %r' % started_seq)

    check('check_few_runs_passthrough',
          [d['id'] for d in few['displayed']] == ['run-C', 'run-B', 'run-A'],
          'got %r' % [d['id'] for d in few['displayed']])

    print('\n%d failure(s)' % len(failures))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""The night shift's own brain-call failures reached the boss verbatim.

Driven live 2026-08-18: scheduled a "RUN NOW" night shift for the "Local
Brain" coworker. `night_runner.py`'s `resolve_backend()` (a per-agent,
`hermes_home/config.yaml`-based lookup, deliberately isolated from the
browser's shared driver registry) resolved to an address this machine
cannot reach. `run_iteration`'s hop loop raised, and the outer
`except Exception as e: return {..., 'error': str(e)}` stored the raw
Python exception text verbatim:

    cannot reach http://10.0.0.100:1234/v1: <urlopen error [Errno 60]
    Operation timed out>

RECENT NIGHT RUNS then rendered it unchanged (`innerText`, live):

    ⚠ Aug 18, 1:13 PM · Local Brain · memory verification probe ·
    1 round · 0 notes · cannot reach http://10.0.0.100:1234/v1: <urlopen
    error [Errn

— truncated mid-word by terminal.jsx's own 50-char slice, a URL and a
bracketed exception repr sitting where every OTHER error path in this
same function (`vault_refused_sentence`, `night_cannot_sentence`, the two
hard-coded "said it..." lines) puts one honest §7-shaped sentence.

Every one of those other paths is reachable from a specific, named cause.
This one was not, because nothing upstream of it could raise anything
BUT a brain-call failure: `run_tool` catches its own exceptions ("tools
never kill an iteration") and always returns a string, and
`find_first_tool` / `vault_write_status` only pattern-match strings
`llm_call` already guarantees are non-empty. `run_iteration`'s outer
except is therefore populated exclusively by `llm_call` — safe to
classify as a BRAIN failure without risking the misattribution
app/floor.jsx's own SNAG_CAUSES commentary warns against (a failed probe
of the office's own backend, put through the brain-specific classifier,
answered "couldn't reach that brain" and named the wrong thing).

The fix adds `_BRAIN_CAUSES` / `brain_cause()` to night_runner.py — the
same classifier shape as app/floor.jsx's SNAG_CAUSES / snagCause, same
patterns, same order, but reworded to fit NIGHT_ERROR_MAX (50 chars):
the browser's snag bubble is not sliced at 50, and this surface is. The
same tightening applies to the fallback (`_clean_cause`, cleanCause's
port), capped at NIGHT_ERROR_MAX instead of the JS side's 90.

This suite:
  · confirms the safe-attribution premise — run_tool has no `raise` in
    its own body, so a tool failure can never surface here misclassified
    as a brain failure;
  · confirms run_iteration's outer except calls brain_cause(e), not the
    raw str(e), at the source level;
  · classifies the exact live-captured raw string, plus one representative
    string per SNAG_CAUSES-equivalent pattern, and checks every resulting
    sentence: correct classification, fits NIGHT_ERROR_MAX, office words
    only (§6: no ALLCAPS token, no underscore, no bare 3-digit code), and
    says what happened with a way forward (§7: an em dash);
  · confirms the unrecognised-failure fallback strips a URL and caps to
    NIGHT_ERROR_MAX rather than fabricating a diagnosis;
  · drives the real run_iteration end-to-end with llm_call faked to raise
    the exact live DriverError, and confirms the RECORD (not just the
    classifier in isolation) carries brain_cause's sentence, never str(e).

Run: python3 scripts/test_a_brain_failure_is_not_a_stack_trace.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import night_runner as nr          # noqa: E402
from drivers.base import DriverError  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


SRC = read('night_runner.py')

# The exact string captured live on RECENT NIGHT RUNS, byte for byte.
LIVE_RAW = ('cannot reach http://10.0.0.100:1234/v1: '
            '<urlopen error [Errno 60] Operation timed out>')

# One representative raw exception per classifier pattern.
CASES = [
    (LIVE_RAW, 'that took too long — try again'),
    ('OpenRouter 401: error: invalid bearer token',
     "that brain isn't signed in — check Settings"),
    ('OpenRouter 429: rate limit exceeded',
     'that brain is rate-limited — try again soon'),
    ('insufficient_quota: you exceeded your current quota',
     'that brain is out of credit — try another'),
    ('ECONNREFUSED 127.0.0.1:1234',
     "couldn't reach that brain — try again"),
    ('LM Studio: model did not start responding within 20s',
     'that brain is still warming up — try again'),
    ('OpenRouter 503: service unavailable',
     "that brain's having trouble — not you"),
    ('Ollama 404: model "nope" not found',
     "that brain isn't installed — pick another"),
]


def def_body(src, header):
    """A Python function's body, lifted by indentation (not brace depth —
    this is Python, not the JS these other suites usually lift from)."""
    i = src.find(header)
    if i < 0:
        raise AssertionError('anchor not found: %r' % header)
    lines = src[i:].splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        if line.strip() == '' or line.startswith((' ', '\t')):
            out.append(line)
        else:
            break
    return '\n'.join(out)


def main():
    print('a brain failure is not a stack trace')

    # ── 1. the safe-attribution premise ─────────────────────────────────
    run_tool_body = def_body(SRC, 'def run_tool(ctx, name, arg, body):')
    check('run_tool body was found', len(run_tool_body) > 200,
          run_tool_body[:120])
    check('run_tool never raises — its own except returns a string '
          '("tools never kill an iteration")',
          'raise' not in run_tool_body,
          'a raise here would let a TOOL failure reach run_iteration\'s '
          'outer except and be misclassified as a BRAIN failure')
    check('...and it really does catch everything itself',
          re.search(r'except Exception as e:.*\breturn\b',
                    run_tool_body, re.S) is not None,
          run_tool_body[-200:])

    # ── 2. the wiring at the real call site ──────────────────────────────
    iter_body = SRC[SRC.index('def run_iteration('):]
    iter_body = iter_body[:iter_body.index('\ndef ')]
    check('run_iteration\'s outer except classifies the failure, rather '
          'than handing back str(e) verbatim',
          re.search(r"except Exception as e:\s*\n(?:\s*#[^\n]*\n)*\s*return "
                    r"\{[^}]*'error':\s*brain_cause\(e\)", iter_body)
          is not None, iter_body[iter_body.index('except Exception'):
                                  iter_body.index('except Exception') + 260])
    check('...and the raw str(e) shape is gone from that return',
          "'error': str(e)" not in iter_body, iter_body)

    # ── 3. classification, budget, and voice ─────────────────────────────
    for raw, expected in CASES:
        got = nr.brain_cause(raw)
        check('classifies %r' % raw[:44], got == expected, got)
        check('...fits the narrowest surface (%d)' % len(got),
              len(got) <= nr.NIGHT_ERROR_MAX,
              '%d > %d: %r' % (len(got), nr.NIGHT_ERROR_MAX, got))
        check('...office words only (§6)',
              not re.search(r'[A-Z]{2,}|_|\b\d{3}\b', got), got)
        check('...says what happened AND a way forward (§7)',
              '—' in got, got)

    # ── 4. the fallback names nothing it cannot confirm ──────────────────
    mystery = ('a genuinely unrecognized failure with a '
               'https://example.com/some/deep/path url and then some '
               'more text that runs well past fifty characters total')
    cleaned = nr.brain_cause(mystery)
    check('an unrecognised failure gets the honest fallback, not a '
          'wrong-but-confident diagnosis',
          cleaned not in [s for _rx, s in nr._BRAIN_CAUSES], cleaned)
    check('...with the URL stripped', 'http' not in cleaned, cleaned)
    check('...and capped to the same budget as every classified sentence',
          len(cleaned) <= nr.NIGHT_ERROR_MAX,
          '%d > %d: %r' % (len(cleaned), nr.NIGHT_ERROR_MAX, cleaned))

    # ── 5. drive the real run_iteration end to end ────────────────────────
    class FakeCtx(object):
        brave_key = ''

    def raise_live(ctx, messages, max_tokens=None):
        raise DriverError(LIVE_RAW, status=502)

    real_llm = nr.llm_call
    nr.llm_call = raise_live
    try:
        rec = nr.run_iteration(
            FakeCtx(), {'vaultFolder': 'Research/night', 'topic': 't'}, 0, 1)
    finally:
        nr.llm_call = real_llm

    check('the real run records the classified sentence',
          rec.get('error') == nr.brain_cause(LIVE_RAW), rec)
    check('...never the raw exception text',
          'urlopen error' not in (rec.get('error') or '')
          and 'http://' not in (rec.get('error') or ''), rec.get('error'))
    check('...and it still fits the narrowest surface',
          len(rec.get('error') or '') <= nr.NIGHT_ERROR_MAX, rec.get('error'))

    print()
    if FAILS:
        print('%d check(s) failed' % len(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

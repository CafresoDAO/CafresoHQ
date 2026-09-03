#!/usr/bin/env python3
"""Switching the Hermes local backend must never offer the LAST backend's models.

Bug (modals/providers.jsx, ApiTab): the hbModels probe effect —

    useEffectM(() => {
      if (!hbMeta.local || !C || !C.hermesLocalModels) { setHbModels(null); return; }
      C.hermesLocalModels(hbUrl).then(r => setHbModels(r.models || []))
        .catch(() => setHbModels([]));
    }, [hBackend, hbUrl]);

had two holes, each its own way to put the WRONG backend's model list on
screen as pickable options:

1. No reset at probe start. Switching LM Studio -> Ollama re-ran the effect
   but left the previous list in state until the new probe landed — and an
   unreachable endpoint takes the whole network timeout to land. For those
   seconds the "Model" row under the OLLAMA heading rendered LM STUDIO's
   models, and picking one calls saveLocalBackend(ollama, url, lmModelId),
   which writes that wrong model id into the gateway config and restarts
   the gateway (~15s).

2. No cancellation latch. Switching A -> B -> A fired two probes with no
   ordering guarantee; if B's landed last, backend A's row showed backend
   B's models indefinitely — a stale list with no "checking…" tell at all.

Fix: same shape as the front-desk driver probe in modals/hire.jsx —
setHbModels(null) before the probe (null already renders this row's
"checking what your backend has…" state), and a `let dead = false` latch
checked in .then/.catch with a cleanup that flips it, so only the CURRENT
[hBackend, hbUrl] pair's probe may write.

This lifts the REAL ApiTab source out of modals/providers.jsx
(brace-balanced extraction, same technique as
test_workspace_terminal_key.py), isolates the one effect keyed on
[hBackend, hbUrl], and checks the structural invariants directly.
Run: python3 scripts/test_a_backend_switch_never_offers_the_last_backends_models.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'modals' / 'providers.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_function(src, name):
    """Brace-balanced extraction of `function NAME(...) { ... }`."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{', src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1  # the opening '{'
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def strip_comments(src):
    """Drop /* */ and // comments so prose about the bug can never satisfy
    (or trip) a check that is about the code."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'//[^\n]*', '', src)


def main():
    print('ApiTab — local-backend model probe resets and latches per backend/url')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    body = extract_function(text, 'ApiTab')
    check('ApiTab extracted from modals/providers.jsx', body is not None)
    if body is None:
        print('\nFAILED: extraction')
        return 1
    body = strip_comments(body)

    # The one effect keyed on [hBackend, hbUrl] — locate its closing deps,
    # then walk back to its own useEffectM opener.
    m_end = re.search(r'\},\s*\[hBackend,\s*hbUrl\]\);', body)
    check('found the effect keyed on [hBackend, hbUrl]', m_end is not None)
    if m_end is None:
        print('\nFAILED: %s' % FAILS)
        return 1
    start = body.rfind('useEffectM(', 0, m_end.start())
    check('effect opener found before its deps array', start != -1)
    if start == -1:
        print('\nFAILED: %s' % FAILS)
        return 1
    effect = body[start:m_end.end()]

    check('effect is the hbModels probe (calls hermesLocalModels)',
          'hermesLocalModels(' in effect)

    # 1. Reset at probe start: a setHbModels(null) BETWEEN the not-local
    #    bail branch and the probe call, so the previous backend's list can
    #    never sit under the new backend's heading while the probe runs.
    call_at = effect.find('hermesLocalModels(hbUrl)')
    resets = [m.start() for m in re.finditer(r'setHbModels\(null\)', effect)]
    check('probe call site located', call_at != -1)
    check('a setHbModels(null) reset runs before the probe call '
          '(beyond the not-local bail branch)',
          len(resets) >= 2 and any(effect.find('return;') < r < call_at
                                   for r in resets),
          f'resets at {resets}, call at {call_at}')

    # 2. Cancellation latch, same shape as the hire-modal driver probe.
    check('effect declares a dead latch (let dead = false)',
          re.search(r'let\s+dead\s*=\s*false', effect) is not None)
    check('.then only writes when the latch is live (if (!dead))',
          re.search(r'\.then\([^)]*=>\s*\{\s*if\s*\(!dead\)\s*setHbModels',
                    effect) is not None)
    check('.catch only writes when the latch is live (if (!dead))',
          re.search(r'\.catch\(\(\)\s*=>\s*\{\s*if\s*\(!dead\)\s*setHbModels',
                    effect) is not None)
    check('cleanup flips the latch (return () => { dead = true; })',
          re.search(r'return\s*\(\)\s*=>\s*\{\s*dead\s*=\s*true;?\s*\};',
                    effect) is not None)

    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'backend-switch model probe: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

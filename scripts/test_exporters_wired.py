#!/usr/bin/env python3
"""Every helper exporters.py calls on `self` must actually be wired onto Handler.

serve.py composes its Handler class from free functions by explicit,
individual assignment — `_export_pptx = exporters._export_pptx` — rather
than real inheritance. That means a function only becomes a real method of
Handler if serve.py names it. exporters.py's own shared helper,
`_read_json_body`, is called via `self._read_json_body()` from all five of
EXPORT_PPTX/DOCX/PDF and GENERATE_IMAGE/VIDEO, but was never itself named in
serve.py's binding list — so every one of those five tools crashed the
request thread with a raw AttributeError the instant a coworker actually
tried to use them.

Confirmed live, not assumed: `curl -X POST .../export/pptx` returned an
EMPTY reply (curl error 52) before the fix, with
`AttributeError: 'Handler' object has no attribute '_read_json_body'` in the
server log. After binding it, the same request returns a clean structured
error (`{"error": "python-pptx not installed — run: pip install
python-pptx"}` on this machine, which has none of the three export
libraries installed — an environment fact, not a code defect; the graceful
ImportError path this fix restores was already written and correct).

None of these five tools had ever been exercised before this was found,
which is why the gap survived. This test is general on purpose — it does
not just pin `_read_json_body` by name, it checks EVERY `self._X(` call
inside exporters.py against serve.py's binding list, so the same class of
bug (a helper added to exporters.py and called via `self.`, but never
wired) is caught automatically for any future helper, not just this one.

Run: python3 scripts/test_exporters_wired.py
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTERS = ROOT / 'exporters.py'
SERVE = ROOT / 'serve.py'

FAILS = []

# Handler methods defined directly in serve.py (not via module wiring) that
# exporters.py's functions are allowed to call — real base-class methods,
# not something this test should expect a `= exporters.X` binding for.
KNOWN_HANDLER_BUILTINS = {'_send_json', '_send_bytes', '_send_response',
                          'send_response', 'send_header', 'end_headers',
                          'send_error', 'log_message', 'log_error'}


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def self_calls_in(func_body_src):
    """Every `self._name(` call inside a chunk of source."""
    return set(re.findall(r'\bself\.(_[A-Za-z_][A-Za-z0-9_]*)\s*\(', func_body_src))


def main():
    print('exporters wiring — every self-called helper must be bound onto Handler')
    if not EXPORTERS.is_file() or not SERVE.is_file():
        print('  FAIL  missing exporters.py or serve.py')
        return 1

    exp_src = EXPORTERS.read_text(encoding='utf-8')
    serve_src = SERVE.read_text(encoding='utf-8')

    tree = ast.parse(exp_src, filename=str(EXPORTERS))
    top_level_funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    check('exporters.py defines top-level functions to check',
          len(top_level_funcs) > 0, 'expected free functions taking self')

    # Every self._X() call anywhere in the file, keyed to which top-level
    # function it lives inside (so the failure message names the right one).
    lines = exp_src.split('\n')
    func_starts = sorted(
        (n.lineno, n.name) for n in tree.body if isinstance(n, ast.FunctionDef))
    called_by = {}   # helper name -> set of caller function names
    for i, (start, name) in enumerate(func_starts):
        end = func_starts[i + 1][0] - 1 if i + 1 < len(func_starts) else len(lines)
        body = '\n'.join(lines[start - 1:end])
        for helper in self_calls_in(body):
            called_by.setdefault(helper, set()).add(name)

    # What serve.py actually binds onto Handler, from ANY module (exporters,
    # fs_routes, etc.) — `NAME = module.NAME` or `NAME = module.something`.
    bound = set(re.findall(r'^\s{4}(_[A-Za-z_][A-Za-z0-9_]*)\s*=\s*\w+\.\w+',
                           serve_src, re.M))
    # Handler methods defined directly with `def _name(self...)` inside serve.py.
    bound |= set(re.findall(r'^\s+def\s+(_[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*self\b',
                            serve_src, re.M))

    missing = {h: callers for h, callers in called_by.items()
              if h not in bound and h not in KNOWN_HANDLER_BUILTINS}

    check('every self._X() helper exporters.py calls is bound onto Handler',
          not missing,
          f'{missing!r} — called via self. but never given a binding line in '
          "serve.py (`_name = exporters._name`) or defined directly on Handler. "
          "This is exactly how _read_json_body went unbound: called five times, "
          "bound zero times, and nothing failed until a coworker actually "
          "invoked one of the five tools.")

    # The specific instance, pinned by name so this exact regression can never
    # come back even if the general check above is ever weakened.
    check('_read_json_body specifically is bound',
          re.search(r'^\s{4}_read_json_body\s*=\s*exporters\._read_json_body',
                    serve_src, re.M) is not None,
          'serve.py: the line this fix added')

    print()
    if FAILS:
        print(f'exporters wiring: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('exporters wiring: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

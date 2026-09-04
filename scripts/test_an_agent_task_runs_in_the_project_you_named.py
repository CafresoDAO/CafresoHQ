#!/usr/bin/env python3
"""An agent task asked for `proj` runs in the workspace's `proj`.

`_agent_task_cwd` is the one place every agent stream route decides where the
coworker's task actually runs. It resolved a relative `cwd` against the server
process's own directory — the repo serve.py was started from — instead of the
workspace root that `_workspace_path` exists to anchor to (#264 closed the same
trap on /tools/exec's own cwd; this is the sibling it left behind).

With an explicit allowlist, a relative `proj` resolved against the repo either
lands outside every allowed dir or fails `is_dir()`. Either way the whitelist
loop falls through without assigning, `cwd` keeps its default — the FIRST
allowed dir — and the task runs in the workspace root. No error: the boss picks
a project, the stream opens, and the coworker works somewhere else entirely.

Worse when the repo happens to hold a same-named directory: `docs` resolves to
the REPO's docs/, a real directory that is simply not the one that was asked
for, and the fallback hides the mismatch just as silently.
"""
import ast
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails = []


def ok(label, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + label + (('  — ' + str(detail)) if detail and not cond else ''))
    if not cond:
        fails.append(label)


def lift(name, src):
    """Pull one method out of serve.py by name, as a bare function."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            node.args.args = [a for a in node.args.args if a.arg != 'self']
            mod = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(mod)
            return mod
    raise SystemExit('could not find ' + name + ' in serve.py')


src = (ROOT / 'serve.py').read_text()

with tempfile.TemporaryDirectory() as tmp:
    # .resolve() up front: on macOS the temp root is itself a symlink, and
    # the code under test resolves, so the expectations must too.
    workspace = (pathlib.Path(tmp) / 'workspace').resolve()
    repo = (pathlib.Path(tmp) / 'repo').resolve()
    (pathlib.Path(tmp) / 'workspace' / 'proj').mkdir(parents=True)
    (pathlib.Path(tmp) / 'workspace' / 'docs').mkdir()
    # The repo ALSO has a docs/ — the case where the wrong answer is a real
    # directory, so nothing downstream can notice it is the wrong one.
    (pathlib.Path(tmp) / 'repo' / 'docs').mkdir(parents=True)

    allowed = [str(workspace)]

    def _client_path(p):
        return p

    def _workspace_path(path, strict=False):
        p = pathlib.Path(path)
        if p.is_absolute():
            return p
        return pathlib.Path(allowed[0]) / p

    ns = {
        'pathlib': pathlib,
        '_client_path': _client_path,
        '_workspace_path': _workspace_path,
        '_cafresohq_allowed_dirs': allowed,
        'OSError': OSError,
        'ValueError': ValueError,
    }
    exec(compile(lift('_agent_task_cwd', src), '<serve.py>', 'exec'), ns)
    agent_task_cwd = ns['_agent_task_cwd']

    got = agent_task_cwd({'cwd': 'proj'})
    ok("a relative 'proj' runs in the workspace's proj",
       got == str(workspace / 'proj'), got)

    got = agent_task_cwd({'cwd': 'docs'})
    ok("'docs' means the workspace's docs, not the repo's",
       got == str(workspace / 'docs'), got)
    ok("...and it is NOT the repo directory of the same name",
       got != str(repo / 'docs'), got)

    # An absolute cwd inside the workspace still works, unchanged.
    got = agent_task_cwd({'cwd': str(workspace / 'proj')})
    ok('an absolute cwd inside the workspace is honoured',
       got == str(workspace / 'proj'), got)

    # A path outside every allowed dir still falls back — the allowlist is not
    # weakened by anchoring, only the meaning of a relative string is fixed.
    got = agent_task_cwd({'cwd': str(repo / 'docs')})
    ok('an absolute cwd outside the allowlist still falls back to the workspace',
       got == str(workspace), got)

    # A relative path naming nothing falls back too, rather than inventing one.
    got = agent_task_cwd({'cwd': 'nope'})
    ok('a relative cwd that does not exist falls back',
       got == str(workspace), got)

    # No cwd at all: the default is untouched.
    got = agent_task_cwd({})
    ok('no cwd at all still means the first allowed dir',
       got == str(workspace), got)

# The source itself must not resolve a relative cwd against the process cwd.
fn = src[src.index('def _agent_task_cwd'):]
fn = fn[:fn.index('def _agent_drivers')]
ok('_agent_task_cwd anchors through _workspace_path',
   '_workspace_path(req_cwd)' in fn)
ok('...and no longer resolves the raw client path against the process cwd',
   'pathlib.Path(_client_path(req_cwd)).resolve()' not in fn)

print()
if fails:
    print('FAILED %d check(s): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('an agent task runs in the project you named: all checks passed')

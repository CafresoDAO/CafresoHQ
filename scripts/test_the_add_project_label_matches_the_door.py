#!/usr/bin/env python3
"""The add-project dialog invited exactly the folder it then refused.

Measured live on the first-run path (#143). Getting-started step 5 opens
ADD PROJECT. Under the ABSOLUTE PATH field:

    Any folder on this machine — 📁 Browse shows the ones your coworkers
    can open.

Typing a real absolute folder outside the sandbox and pressing Add:

    That folder is outside the ones this office can show you — 📁 Browse
    shows the ones that work.

Both sentences on screen at once. The refusal is right; the invitation was
the leftover. `_addRefusedOutsideSandbox` asks /fs/browse before filing a
project, and that route enforces the allowlist in EVERY mode -- deliberately,
because it is keyless. The hint predates that guard: its comment argued from
`_safe_path`, which DOES take a local-mode skip, and that is the door the
coworker tools use, not the door the boss's own tree and this modal's Browse
use. Two true statements about two different doors, and the label was quoting
the wrong one.

The same stale sentence had also settled in `_fs_browse`'s docstring ("In
local mode: any readable path is allowed") twenty lines above the code that
contradicts it, and in this suite's own rationale for the hint. Corrected in
all three.

What is checked here is the AGREEMENT, not the wording: the office must not
promise a set of folders wider than the door it asks. So the copy is measured
against the live behaviour of the real guard rather than against a fixed
string -- a rewrite of the sentence passes, a re-broadened promise does not.
"""
import json
import os
import re
import subprocess
import sys
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def brace_lift(src, opener):
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


PROJ = open(os.path.join(ROOT, 'views', 'projects.jsx')).read()
FS = open(os.path.join(ROOT, 'fs_routes.py')).read()

# Comments in this file discuss the old copy by quoting it, so every sweep
# below runs on code with block and line comments removed. Verified to bite
# rather than assumed -- an inert strip would find the documentation and
# report the label was fixed.
PROJ_CODE = re.sub(r'/\*[\s\S]*?\*/', '', PROJ)
PROJ_CODE = re.sub(r'(?m)^\s*//.*$', '', PROJ_CODE)


def main():
    # By the DROP, not by the absence. "not in PROJ_CODE" also fails whenever
    # the old sentence is genuinely back in the markup, which is the other
    # check's job -- firing that break made this one fail alongside it for a
    # reason that had nothing to do with stripping.
    check("comment stripping actually removed the discussion of the old copy",
          PROJ.count('Any folder on this machine') > PROJ_CODE.count('Any folder on this machine'),
          '— the old sentence is quoted in a comment; a no-op strip would '
          'let every check below pass on that quote')

    print("1. the label the boss reads before typing")
    m = re.search(r'<small>([^<]*Browse shows the ones your coworkers can open[^<]*)</small>',
                  PROJ_CODE)
    check("the ABSOLUTE PATH field still carries a hint",
          bool(m), 'views/projects.jsx: the field is the one place the rule '
                   'can be stated before the boss has typed anything')
    hint = m.group(1) if m else ''

    # Not a pinned string: any sentence that does not promise an unrestricted
    # set passes. What is forbidden is the CLAIM, in whatever words -- so a
    # NEGATED quantifier is the fix, not the bug, and must not trip this.
    # The first draft read `\b(any|every|all)\s+folder` and failed on "Not
    # every folder works", which is the corrected copy: a check that cannot
    # tell a promise from its denial would have sent the sentence back to
    # the overpromise it was written to forbid.
    def promises_everything(text):
        for m in re.finditer(r'\b(any|every|all)\s+(folder|directory|path|dir)',
                             text, re.I):
            lead = text[max(0, m.start() - 14):m.start()].lower()
            if re.search(r"\b(not|n't|never|isn't|aren't)\s*$", lead):
                continue          # a denial of the claim, not the claim
            return m.group(0)
        return None

    over = promises_everything(hint)
    check("...and it does not promise a folder the door will refuse",
          over is None,
          repr(hint) + f' says {over!r} — the add is gated on /fs/browse, '
          'which is sandboxed in every mode; a label wider than that gate '
          'invites the refusal')
    check("...while still naming the door that answers",
          'Browse' in hint,
          '— "some folders do not work" with no way to find one that does is '
          'a worse sentence than the overpromise it replaced')
    check("...without naming a rule the boss cannot look up from here",
          'CAFRESOHQ' not in hint, repr(hint))

    print("2. the door the label is describing, actually run")
    # The real guard, lifted from the app and executed. If this stops
    # refusing, the label above becomes the wrong sentence in the other
    # direction -- and nothing else in the suite would notice, because the
    # copy would still read as cautious.
    try:
        fn = brace_lift(PROJ, 'const _addRefusedOutsideSandbox = async (path, toast) => {')
    except (ValueError, AssertionError) as e:
        print(f"FAILED: could not lift the door check ({e})")
        return 1

    harness = """
const toasts = [];
const toast = (kind, msg) => toasts.push({ kind, msg });
const window = { _API_BASE: '' };
const fetch = async () => ({ status: %s });
%s;
(async () => {
  const refused = await _addRefusedOutsideSandbox('/some/where', toast);
  console.log(JSON.stringify({ refused, toasts }));
})();
"""
    tmp = tempfile.mkdtemp(prefix='addproj-label-')
    got = {}
    try:
        for label, code in (('refused', '403'), ('allowed', '200')):
            p = os.path.join(tmp, label + '.mjs')
            with open(p, 'w') as fh:
                fh.write(harness % (code, fn))
            proc = subprocess.run([shutil.which('node') or 'node', p],
                                  capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                print("  FAIL node harness errored: " + proc.stderr.strip()[:300])
                failures.append('node harness ' + label)
                got = {}
                break
            got[label] = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if got:
        check("a folder the reading door refuses stops the add",
              got['refused']['refused'] is True,
              '— this is what makes "not every folder works" a true sentence')
        check("...and a folder it allows is added without a word",
              got['allowed']['refused'] is False and got['allowed']['toasts'] == [])
        # The two sentences the boss sees, checked against each other rather
        # than each on its own. This is the pairing that was broken: both were
        # individually defensible and they contradicted.
        msg = got['refused']['toasts'][0]['msg'] if got['refused']['toasts'] else ''
        check("the refusal and the invitation point at the same door",
              'Browse' in msg and 'Browse' in hint,
              f'hint={hint!r} refusal={msg!r}')

    print("3. the route the whole sentence rests on")
    # If /fs/browse ever takes the local-mode skip that _validate_path
    # offers, the label goes back to being wrong -- the other way round.
    try:
        i = FS.index('def _fs_browse(self):')
        body = FS[i:FS.index('\ndef ', i + 1)]
    except ValueError as e:
        print(f"FAILED: could not lift _fs_browse ({e})")
        return 1
    check("browsing is gated on the allowlist",
          'if not _within_allowed_dirs(p):' in body,
          'fs_routes.py: the add-project door reads this route\'s 403')
    check("...in every mode, with no local-runtime escape",
          '_ALLOWED_DIRS_EXPLICIT' not in body and "_RUNTIME_ENV == 'local'" not in body,
          'fs_routes.py: this route is keyless, so the skip _validate_path '
          'grants local runs would be an unauthenticated read of any path')
    # The docstring is what the next reader trusts before they read the code.
    # Asserted positively rather than by forbidding the old words: the
    # docstring now RECORDS the sentence it used to make, and a check that
    # only banned the phrase would fail on that record -- the same
    # can't-tell-a-quote-from-a-claim mistake as the hint check above.
    doc = body[:body.index('"""', body.index('"""') + 3)]
    stale = re.search(r'\b(any|every|all)\s+readable\s+path\s+is\s+allowed', doc)
    check("...and the docstring says so too",
          'EVERY mode' in doc, repr(doc[:200]))
    # Marked as history, not counted by quote parity -- the docstring's own
    # `"""` skews that count, which is how the first draft of this check
    # failed on a correctly-quoted record.
    check("...stating the old claim only as history, never as the rule",
          (not stale) or re.search(r'used to say|claimed|no longer',
                                   doc[max(0, stale.start() - 80):stale.start()]),
          '— it claimed the opposite of the check twenty lines below it, '
          'which is where the dialog\'s sentence came from')

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: the dialog does not invite a folder the office will refuse")
    return 0


if __name__ == '__main__':
    sys.exit(main())

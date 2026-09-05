#!/usr/bin/env python3
"""A fleet-managed HQ with its own working brain was still told to sign up
for an OpenRouter key it did not need.

The tour's key step (`OnboardingKeyStep` in ui/onboarding.jsx) has always
known about ONE zero-config path: the shared OpenRouter trial, reported by
GET /hermes/trial-status ({active, remaining, cap}). That is the mechanism
docker/hermes-bootstrap.py wires when CAFRESOHQ_TRIAL_KEY is set and no user
key exists.

There is a SECOND, older zero-config path: a fleet-provisioned container
with LMSTUDIO_BASE_URL injected server-side (see /health's `brain` field in
serve.py — "advertises the managed default model when Cafreso provisioned
this HQ with a shared endpoint"). claude-client.jsx's probeManagedBrain()
reads exactly this field, and app.jsx's own hasKey/officeCanWork — the thing
that drives the topbar's ⚠ ADD AI KEY chip and the getting-started
checklist's "Your AI brain" step — already trusts it. hermes-bootstrap.py's
own precedence list puts LMSTUDIO_BASE_URL (branch 2) AHEAD of the trial
branch (4b), and only the trial branch writes trial.json — so a container
provisioned this way answers /health with a populated `brain` object and
/hermes/trial-status with `active: false`, at the same time.

OnboardingKeyStep asked only the trial-status question. On exactly the boxes
the LMSTUDIO_BASE_URL path covers, the rest of the app agreed the office
already had a working brain — chip hidden, checklist step ticked — while the
tour's OWN key step told the new user "it needs your own free key from
OpenRouter" and walked them through signing up for one they did not need.
Same class of bug as the CEO's old opening line (app.jsx) and emptyOfficeNote
(app/cast.jsx): a fixed string answering a question this component never
actually asked.

The fix adds the same check the rest of the app already trusts —
CafresoHQClient.managedBrain() / probeManagedBrain(), the cached read of
/health's `brain` field — as a second, independent way this step can already
be "set", distinct from the metered trial (no remaining-count clause, and
different wording: "its own AI brain built in" vs "Cafreso's free shared
brain").

This suite:
  · boots a REAL serve.py on a scratch HOME with LMSTUDIO_BASE_URL set (the
    managed-fleet shape) and CAFRESOHQ_TRIAL_KEY unset, and confirms live
    that /health.brain is populated while /hermes/trial-status.active is
    false — the exact contradiction this fix closes;
  · lifts the real `onTrial` expression out of ui/onboarding.jsx by name and
    evaluates it under node against {managedBrain, trial, existing}
    combinations, including the live-measured one above;
  · pins that the "already set" paragraph tells the two zero-config cases
    apart (no remaining-count claim when there is no metered cap to report).

Run: python3 scripts/test_a_managed_brain_isnt_told_to_get_a_key.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import strip_comments  # noqa: E402

ONB = ROOT / 'ui' / 'onboarding.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:                            # noqa: BLE001
        return 0, None


def boot(home, extra_env):
    port = free_port()
    env = dict(os.environ, PORT=str(port), HOME=str(home),
               CAFRESOHQ_HQ_STATE_DIR=str(home / 'state'),
               CAFRESOHQ_VAULT=str(home / 'vault'),
               CAFRESOHQ_ALLOWED_DIRS=str(home / 'work'))
    for k in ('OPENROUTER_API_KEY', 'GROQ_API_KEY', 'ANTHROPIC_API_KEY',
              'GOOGLE_API_KEY', 'LMSTUDIO_BASE_URL', 'CAFRESOHQ_TRIAL_KEY',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    env.update(extra_env)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        status, _ = get(base + '/hermes/trial-status')
        if status == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def on_trial_expr():
    bare = strip_comments(ONB.read_text(encoding='utf-8'))
    m = re.search(r"const onTrial = (.+?);\n", bare)
    if not m:
        raise SystemExit('could not find `const onTrial = ...;` in ui/onboarding.jsx')
    return m.group(1).strip()


def already_set_paragraph_source():
    bare = ONB.read_text(encoding='utf-8')  # keep comments out of the way but text intact
    bare = strip_comments(bare)
    m = re.search(r"\{onTrial \? \(\s*<p[\s\S]*?</p>\s*\) : \(", bare)
    if not m:
        raise SystemExit('could not find the onTrial paragraph in ui/onboarding.jsx')
    return m.group(0)


def eval_on_trial(cases):
    expr = on_trial_expr()
    js = ('const CASES = %s;\n'
          'const OUT = {};\n'
          'for (const [name, c] of Object.entries(CASES)) {\n'
          '  const managedBrain = c.managedBrain;\n'
          '  const trial = c.trial;\n'
          '  const existing = c.existing;\n'
          '  OUT[name] = (%s);\n'
          '}\n'
          'console.log(JSON.stringify(OUT));' % (json.dumps(cases), expr))
    return run_js(js)


def main():
    print("a managed brain isn't told to sign up for a key it doesn't need")

    # ── 1. source shape ───────────────────────────────────────────────────
    bare = strip_comments(ONB.read_text(encoding='utf-8'))
    check('OnboardingKeyStep reads managedBrain()/probeManagedBrain(), not just trial-status',
          'C.managedBrain' in bare and 'C.probeManagedBrain' in bare,
          'the shared cached probe app.jsx already trusts must be read here too')
    para = already_set_paragraph_source()
    check('the already-set paragraph tells the two zero-config cases apart',
          re.search(r'managedBrain\s*\?\s*"', para) is not None,
          'a managed container has no metered cap to talk about, and the '
          'wording should not claim a "shared" trial it is not on')
    check('the remaining-count clause is suppressed for a managed brain',
          re.search(r'!managedBrain\s*&&\s*trial\s*&&', para) is not None,
          'a managed brain has no daily cap; showing one would be a new '
          'fabricated claim in the same paragraph the fix is repairing')

    if not shutil_which_node():
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    # ── 2. the real office, provisioned the managed-fleet way ────────────
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        (home / 'work').mkdir()
        (home / 'vault').mkdir()
        base, kill = boot(home, {
            'LMSTUDIO_BASE_URL': 'http://127.0.0.1:1234/v1',
            'LMSTUDIO_MODEL': 'test-managed-model',
        })
        try:
            if not base:
                check('serve.py answered', False, 'the office never came up')
                health, trial = None, None
            else:
                hstatus, health = get(base + '/health')
                tstatus, trial = get(base + '/hermes/trial-status')
                check('a managed-fleet box reports a populated /health.brain',
                      hstatus == 200 and health and health.get('brain')
                      and health['brain'].get('model') == 'test-managed-model',
                      f'{health!r}')
                check('...while /hermes/trial-status stays inactive on that same box',
                      tstatus == 200 and trial and trial.get('active') is False,
                      f'{trial!r} — this is the exact contradiction OnboardingKeyStep '
                      'used to miss: a working brain the trial probe never sees')
        finally:
            kill()

    if health is None or trial is None:
        print('FAILED: could not measure the live office')
        return 1

    # ── 3. the real onTrial expression, fed the live-measured values ────
    live_managed_brain = health['brain']
    cases = {
        'managed_fleet_live':  {'managedBrain': live_managed_brain, 'trial': trial, 'existing': ''},
        'managed_fleet_synthetic': {'managedBrain': {'model': 'x', 'provider': 'cafreso'},
                                    'trial': {'active': False, 'remaining': 0, 'cap': 0}, 'existing': ''},
        'shared_trial':        {'managedBrain': False, 'trial': {'active': True, 'remaining': 12, 'cap': 25}, 'existing': ''},
        'genuinely_bare':      {'managedBrain': False, 'trial': {'active': False, 'remaining': 0, 'cap': 25}, 'existing': ''},
        'unknown_probe':       {'managedBrain': None, 'trial': None, 'existing': ''},
        'byok_already_set_should_not_override': {'managedBrain': {'model': 'x'}, 'trial': None, 'existing': 'sk-or-already-here'},
    }
    out = eval_on_trial(cases)
    for name, v in sorted(out.items()):
        print(f'    {name}: onTrial={v}')
    print()

    check('a live managed-fleet office reads as already set',
          out['managed_fleet_live'] is True, out)
    check('...and so does the synthetic managed-brain shape',
          out['managed_fleet_synthetic'] is True, out)
    check('the pre-existing shared-trial case still reads as already set (no regression)',
          out['shared_trial'] is True, out)
    check('a genuinely bare box (neither mechanism) still asks for a key',
          out['genuinely_bare'] is False, out)
    check('an unresolved probe (both null) does not claim "already set"',
          out['unknown_probe'] is False, out)
    check('a user who already pasted their own key is never told "already set" instead',
          out['byok_already_set_should_not_override'] is False, out)

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


def shutil_which_node():
    import shutil
    return bool(shutil.which('node'))


if __name__ == '__main__':
    raise SystemExit(main())

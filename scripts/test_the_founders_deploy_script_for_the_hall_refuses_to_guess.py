#!/usr/bin/env python3
"""scripts/deploy_market.sh is the one step the office never takes: it
creates the hiring hall's canister on mainnet and spends cycles. So the
script must refuse to guess — and this suite pins the refusals, because a
deploy script that silently does the wrong thing does it with money.

Pinned, by reading the script and by running it where that is safe:
  * it is executable, parses, and `--help` prints its own header;
  * it exports DFX_VERSION from .dfx-version and refuses a dfx that answers
    a different version (the canister is written for that moc);
  * it refuses IDENTITY=ic_admin (deploys here use the default identity);
  * it compile-checks (`dfx build cafresohq_market --check`) BEFORE any
    command that names a network;
  * `--dry-run` prints the plan and exits 0 without running `dfx deploy`,
    `dfx canister create` or `dfx canister call` (asserted by a fake dfx on
    PATH that logs every invocation);
  * without --yes it asks, and an empty answer does not deploy;
  * the only network-touching commands are deploy, canister id, and the
    plan-admin claim, all with --network and --identity spelled out;
  * an unknown argument is a usage error, not a deploy.

The fake dfx answers `--version` with the pinned version and succeeds on
`build --check`, so the run here never reaches a replica. Run:
    python3 scripts/test_the_founders_deploy_script_for_the_hall_refuses_to_guess.py
"""
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'deploy_market.sh'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


FAKE_DFX = '''#!/usr/bin/env bash
echo "$@" >> "$FAKE_DFX_LOG"
case "$1" in
  --version) echo "dfx ${FAKE_DFX_VERSION:-0.24.3}"; exit 0 ;;
  identity) [ "$2" = list ] && { printf 'default\\nic_admin\\n'; exit 0; } ;;
  build) exit 0 ;;
  deploy) echo "FAKE DEPLOY"; exit 0 ;;
  canister) [ "$2" = id ] && { echo "aaaaa-aa"; exit 0; }; echo "(true)"; exit 0 ;;
esac
exit 0
'''


def run(args, env_extra=None, stdin=''):
    with tempfile.TemporaryDirectory() as d:
        binp = Path(d) / 'bin'
        binp.mkdir()
        fake = binp / 'dfx'
        fake.write_text(FAKE_DFX)
        fake.chmod(0o755)
        log = Path(d) / 'dfx.log'
        env = dict(os.environ, PATH=f'{binp}:{os.environ.get("PATH", "")}', FAKE_DFX_LOG=str(log))
        env.update(env_extra or {})
        r = subprocess.run(['bash', str(SCRIPT), *args], cwd=ROOT, env=env, input=stdin,
                           capture_output=True, text=True, timeout=120)
        calls = log.read_text().splitlines() if log.exists() else []
        return r.returncode, r.stdout + r.stderr, calls


def main():
    print("the founder's deploy script for the hall refuses to guess")
    src = SCRIPT.read_text(encoding='utf-8')
    check('the script is executable', bool(SCRIPT.stat().st_mode & stat.S_IXUSR))
    check('it parses', subprocess.run(['bash', '-n', str(SCRIPT)], capture_output=True).returncode == 0)
    check('it exports DFX_VERSION from .dfx-version', 'export DFX_VERSION="$PIN"' in src and '.dfx-version' in src)
    check('every network-touching dfx command spells out --network and --identity',
          all('--network' in line and '--identity' in line for line in src.splitlines()
              if re.match(r'\s*(if\s+!\s+)?dfx (deploy|canister call)\b', line)))
    check('the compile check comes before any command that names a network',
          src.index('dfx build cafresohq_market --check') < src.index('dfx deploy'))
    check('canister create is left to dfx deploy (no second creation path)', 'canister create' not in src)

    code, out, calls = run(['--help'])
    check('--help prints the header and runs no dfx', code == 0 and 'one command to open the hiring hall' in out and calls == [])

    code, out, calls = run(['--dry-run'])
    check('--dry-run exits 0 with the plan', code == 0 and 'plan: deploy cafresohq_market' in out and 'dry run: nothing deployed' in out, out[-400:])
    check('--dry-run ran the compile check', any(c.startswith('build cafresohq_market --check') for c in calls), calls)
    check('--dry-run never deployed, created or called anything',
          not any(c.startswith(('deploy', 'canister')) for c in calls), calls)

    code, out, calls = run(['--dry-run'], {'FAKE_DFX_VERSION': '0.29.1'})
    check('a dfx of another version is refused, naming the pin', code == 1 and '0.29.1' in out and '0.24.3' in out and not any(c.startswith('build') for c in calls))

    code, out, calls = run(['--dry-run'], {'IDENTITY': 'ic_admin'})
    check('ic_admin is refused before anything runs', code == 1 and 'refusing to deploy as ic_admin' in out and not any(c.startswith('build') for c in calls))

    code, out, calls = run([], stdin='\n')
    check('without --yes it asks, and an empty answer does not deploy',
          code == 1 and 'Deploy? [y/N]' in out and 'not deployed' in out and not any(c.startswith('deploy') for c in calls), out[-300:])

    code, out, calls = run(['--yes'])
    check('--yes deploys, reads the id, claims plan admin, prints the follow-ups',
          code == 0 and any(c.startswith('deploy cafresohq_market --network ic --identity default') for c in calls)
          and any(c.startswith('canister call cafresohq_market market_admin_claim --network ic --identity default') for c in calls)
          and 'VITE_CANISTER_ID_CAFRESOHQ_MARKET=aaaaa-aa' in out and 'CAFRESOHQ_MARKET_CANISTER=aaaaa-aa' in out, (code, calls, out[-300:]))

    code, out, calls = run(['--yes'], {'NETWORK': 'local'})
    check('NETWORK=local deploys to local, not ic', code == 0 and any(c.startswith('deploy cafresohq_market --network local') for c in calls) and not any('--network ic' in c for c in calls))

    code, out, calls = run(['--please'])
    check('an unknown argument is a usage error, not a deploy', code == 2 and 'unknown argument' in out and calls == [])

    print()
    if FAILS:
        print(f'deploy script: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('deploy script: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

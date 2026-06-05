#!/usr/bin/env python3
"""One-shot recovery helper: make the OCIR pull credential readable by
fleet-manager's provision step.

Docker Desktop stores the iad.ocir.io credential in its credential STORE
(credsStore=desktop.exe), so ~/.docker/config.json has no inline `auth` field.
But fleet-manager._read_ocir_pull_secret only understands inline `auth`. This
script asks the Desktop credential helper for the stored iad.ocir.io credential
and writes it inline into ~/.docker/config.json so provision can attach a
BasicImagePullSecret to the container instance.

Single purpose, no secret is printed. Safe to re-run.
"""
import base64
import json
import os
import subprocess

REGISTRY = 'iad.ocir.io'
HELPER = 'docker-credential-desktop.exe'   # WSL can invoke the Windows helper


def main():
    try:
        p = subprocess.run([HELPER, 'get'], input=REGISTRY.encode(),
                           capture_output=True, timeout=20)
    except FileNotFoundError:
        print(f'ERROR: {HELPER} not found on PATH (Docker Desktop WSL integration?)')
        raise SystemExit(1)
    if p.returncode != 0:
        print(f'ERROR: credential helper failed: {p.stderr.decode("utf-8","replace")[:200]}')
        raise SystemExit(1)
    cred = json.loads(p.stdout.decode('utf-8', 'replace'))
    user, secret = cred.get('Username', ''), cred.get('Secret', '')
    if not user or not secret:
        print('ERROR: credential helper returned no Username/Secret for ' + REGISTRY)
        raise SystemExit(1)

    cfg_path = os.path.expanduser('~/.docker/config.json')
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
    cfg.setdefault('auths', {}).setdefault(REGISTRY, {})['auth'] = \
        base64.b64encode(f'{user}:{secret}'.encode()).decode()
    with open(cfg_path, 'w') as f:
        json.dump(cfg, f, indent=2)
    # Mask everything but the namespace segment of the username.
    print(f'OK: wrote inline {REGISTRY} auth for {user.split("/")[0]}/*** into {cfg_path}')


if __name__ == '__main__':
    main()

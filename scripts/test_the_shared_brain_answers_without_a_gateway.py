#!/usr/bin/env python3
"""An office with the shared Cafreso brain but no Hermes gateway still answers.

Inside Cafreso Linux the office is handed the GPU's address and nothing else:
no Hermes is installed. /health advertised the brain, the checklist ticked
"Your AI brain", and every message then failed at a gateway that was never
there. /health now says how the brain is reached, the client goes straight to
it when the answer is `direct`, and Settings has one Brain tab that names it,
tests it and holds the answer-length control the error messages point at.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failures = []


def check(name, ok, detail=''):
    print(('    ok    ' if ok else '    FAIL  ') + name + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        failures.append(name)


client = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
settings = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')

# 1. a real office, no gateway: /health says the brain is reached directly
port = 18000 + os.getpid() % 1000
with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_BIND='127.0.0.1', CAFRESOHQ_FLEET_MODE='local',
               CAFRESOHQ_HQ_STATE_DIR=tmp, CAFRESOHQ_VAULT=tmp,
               LMSTUDIO_BASE_URL='http://127.0.0.1:9/v1', LMSTUDIO_MODEL='test-model')
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    brain = None
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as r:
                    brain = json.load(r).get('brain')
                break
            except Exception:
                time.sleep(0.25)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
check('/health names the shared brain', bool(brain) and brain.get('model') == 'test-model', str(brain))
check("/health says it is reached directly when no gateway is running",
      bool(brain) and brain.get('via') == 'direct', str(brain))

# 2. the client takes the direct road before the Hermes one
stream = client[client.index('async function stream(opts)'):]
stream = stream[:stream.index('\n}\n')]
direct = stream.find('sharedBrainDirect()')
hermes = stream.find('return streamHermes(next)')
check('stream() checks for the direct brain before handing off to Hermes', 0 < direct < hermes)
check('sharedBrainDirect is exported on the client',
      re.search(r'const CafresoHQClient = \{[^}]*\bsharedBrainDirect\b', client, re.S) is not None)

# 3. Settings: one Brain tab, first, with the control the errors point at
tabs = re.search(r'const SETTINGS_TABS = \[(.*?)\n\];', settings, re.S).group(1)
ids = re.findall(r"id: '([a-z-]+)'", tabs)
check('Brain is the first Settings tab', ids[:1] == ['brain'], str(ids))
check('the Brain tab is mounted', "activeTab === 'brain' && <BrainTab" in settings)
check('the Brain tab holds Answer length', 'Answer length' in settings and 'maxTokens: v' in settings)
check('no message sends the boss to a Max tokens control that does not exist',
      'raise Max tokens in Settings' not in client)

if failures:
    print(f'\n{len(failures)} check(s) failed')
    sys.exit(1)
print('\nall checks passed')

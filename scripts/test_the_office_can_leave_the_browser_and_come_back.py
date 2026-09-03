#!/usr/bin/env python3
"""The whole office lived in one browser profile with no way out.

Everything browser-side — chat, team, tasks, prefs — persists under the
cafresohq localStorage prefixes. One cleared profile, one new machine,
one different browser: the office starts empty, and until this existed
the Settings modal offered an export for the HERMES config but nothing
for the office itself.

Settings → OFFICE BACKUP now exports those entries as one JSON file and
restores from one. The security contract mirrors the Hermes export's
"keys NOT included" promise, and it is enforced on BOTH directions:

  - `cafresohq_agent_keys_v1` (encrypted per-agent key blob) and
    `cafresohq_device_key_v1` (the raw AES device key) never leave, and
    are refused on the way back in even if a file carries them;
  - every field matching /key$/i inside the `cafresohq_client_v1`
    settings blob (openrouterKey, anthropicKey, googleKey, braveKey, and
    whatever gets added later) is blanked on export AND re-blanked on
    import — a hand-edited backup can't smuggle a key into storage;
  - import refuses files that aren't office backups, refuses entries
    outside the allowed prefixes, confirms with a danger prompt before
    replacing anything, and reloads so the restored state is what mounts.

Run: python3 scripts/test_the_office_can_leave_the_browser_and_come_back.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the office can leave the browser and come back')
    settings = strip_comments((ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8'))

    # ── the surface exists ──────────────────────────────────────────────
    check('the OFFICE BACKUP panel exists',
          '<h4>OFFICE BACKUP</h4>' in settings)
    check('export and import are both offered',
          'onClick={exportOffice}' in settings and 'onChange={importOffice}' in settings)
    check('the export names its own limit honestly',
          'keys NOT included' in settings)

    # ── the rescued Hermes config surface ───────────────────────────────
    # The agent-config export/import (client methods + serve.py endpoints,
    # both live) had its ONLY UI inside `SystemTab`, a component that was
    # defined but mounted nowhere — a real feature no user could reach.
    # It lives in AccountTab now, and the dead tab is gone.
    check('the Hermes agent-config surface is reachable now',
          'onClick={exportHermesConfig}' in settings
          and 'onChange={importHermesConfig}' in settings)
    check('...wired to the real client methods',
          'CafresoHQClient.hermesExportConfig()' in settings
          and 'CafresoHQClient.hermesImportConfig(text)' in settings)
    check('the dead SystemTab stays deleted',
          'SystemTab' not in settings,
          '— a defined-but-never-mounted tab is where this feature '
          'hid unreachable for its whole life')

    # ── the contract, structurally ──────────────────────────────────────
    check('the secret stores are blocked by name',
          "OFFICE_EXPORT_BLOCKED = ['cafresohq_agent_keys_v1', 'cafresohq_device_key_v1']" in settings)
    check('the block is applied on export',
          re.search(r'exportOffice[\s\S]*?OFFICE_EXPORT_BLOCKED\.includes\(key\)\) continue;', settings))
    check('...and on import — a carried secret is refused, not restored',
          re.search(r'importOffice[\s\S]*?!OFFICE_EXPORT_BLOCKED\.includes\(key\)', settings))
    check('the client blob is scrubbed on export AND import',
          settings.count("key === 'cafresohq_client_v1' ? _scrubClientBlob(") == 2,
          settings.count("key === 'cafresohq_client_v1' ? _scrubClientBlob("))
    check('import confirms with a danger prompt before replacing anything',
          re.search(r'importOffice[\s\S]*?window\.hqConfirm\([\s\S]*?danger: true \}\)\)\) return;', settings))
    check("...whose button says what it does — 'Replace office', not the "
          "danger default 'Delete'",
          "{ okLabel: 'Replace office', danger: true }" in settings,
          '— caught live by test_confirm_dialog_labels: danger:true with no '
          'okLabel renders a Delete button on an action that is not one')
    check('import reloads so the restored state is what mounts',
          re.search(r'importOffice[\s\S]*?window\.location\.reload\(\);', settings))
    check('import refuses files that are not office backups',
          "data.format !== 'cafresohq-office-backup'" in settings)

    # ── the scrub and the filter, behaviorally ──────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')
    else:
        # Lift the constants and the scrubber, then drive the import filter
        # logic the way importOffice applies it.
        pieces = []
        for opener, closer in (
            ("const OFFICE_HQ_PREFIX = ", ";"),
            ("const OFFICE_EXPORT_PREFIXES = [", ";"),
            ("const OFFICE_EXPORT_BLOCKED = [", ";"),
            ("const _scrubClientBlob = (raw) => {", "\n  };"),
        ):
            i = settings.index(opener)
            j = settings.index(closer, i) + len(closer)
            pieces.append(settings[i:j])
        js = '\n'.join(pieces) + r'''
const entries = {
  'cafresohq_hq_v1:chat': '[]',
  'cafresohq:graph:prefs': '{}',
  'cafresohq_client_v1': JSON.stringify({ model: 'x', openrouterKey: 'sk-LEAK', braveKey: 'b-LEAK', maxTokens: 5 }),
  'cafresohq_agent_keys_v1': '{"smuggled":"blob"}',
  'cafresohq_device_key_v1': 'AAAA',
  'total_stranger_key': 'nope',
  'cafresohq_hq_v1:tasks': 42,
};
const keys = Object.keys(entries).filter(key =>
  !OFFICE_EXPORT_BLOCKED.includes(key)
  && OFFICE_EXPORT_PREFIXES.some(p => key === p || key.startsWith(p))
  && typeof entries[key] === 'string');
const scrubbed = JSON.parse(_scrubClientBlob(entries['cafresohq_client_v1']));
console.log(JSON.stringify({ keys: keys.sort(), scrubbed }));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            check('the lifted pieces run', False, p.stderr.strip()[:300])
        else:
            r = json.loads(p.stdout.strip().split('\n')[-1])
            check('the import filter admits exactly the office entries',
                  r['keys'] == ['cafresohq:graph:prefs', 'cafresohq_client_v1',
                                'cafresohq_hq_v1:chat'],
                  [r['keys'], '— no secret stores, no foreign keys, no '
                   'non-string values'])
            check('the scrub blanks every *Key field and keeps the rest',
                  r['scrubbed'] == { 'model': 'x', 'openrouterKey': '',
                                     'braveKey': '', 'maxTokens': 5 },
                  r['scrubbed'])

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

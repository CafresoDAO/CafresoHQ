#!/usr/bin/env python3
"""Settings sold open-in-Obsidian and the only door had been deleted.

Settings -> Connections -> Vault, under the backend picker, in the
product's own words:

    Obsidian REST is optional. It unlocks plugin-mediated file access and
    open-in-Obsidian.

The OBSIDIAN REST button really works — it POSTs the backend switch, the
server really flips `_vault_backend`, and `POST /vault/open` is fully
implemented behind it and calls the plugin. `vaultOpenInObsidian` is
implemented in claude-client.jsx and exported. Everything on that path was
real except the last inch: no control anywhere in the product called it.
A boss could install a community plugin, paste an API key, throw the
switch, and the one capability the switch named by name did not exist.

§5: a wrong door is worse than a locked one.

The button HAD existed and was deleted, on a premise that had gone stale:
a comment in modals.jsx said providers.jsx was "deliberately NOT imported",
so the reasoning ran, VaultTab never ships, the REST backend is
unreachable, /vault/open can only ever 400, delete the button. Every clause
was true when written. By then modals/settings.jsx imported four of that
file's panels by name. The stale sentence was load-bearing for a deletion
four tickets after it stopped being true, which is why this suite pins the
FACT (who imports what) rather than trusting any of the prose about it.

The fix is a gate, not a restoration: the control renders only when the
live backend is already 'rest' — exactly the condition the server answers
to — so the 99% who never touched Obsidian see what they saw yesterday and
the boss who did the setup gets what the setup promised.

Run: python3 scripts/test_the_promised_door_exists.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

GATE = "const _obsidianOn = !!status && status.backend === 'rest';"
# The server's precondition, verbatim. The gate exists to mean the same
# thing; if this line ever moves, the gate has to move with it or the
# button goes back to being a button that can only fail.
SERVER_GUARD = "if _vault_backend != 'rest':"
SERVER_REFUSAL = 'open-in-Obsidian requires REST backend'

# Sentences that were measured false in the product and removed. Each one
# claimed, in some wording, that modals/providers.jsx does not ship.
STALE_CLAIMS = [
    ('is deliberately NOT imported',
     'no comment still calls providers.jsx deliberately unimported'),
    ('has zero real `import` sites',
     '…nor claims in the present tense that it has no import sites'),
]

# What settings.jsx really mounts out of providers.jsx, and what really is
# still held back. The stale prose is only dangerous because nobody checks
# the fact underneath it; this suite checks the fact.
MOUNTED = ['VaultTab', 'MediaTab', 'BraveTab', 'BrowserKeysTab']
UNMOUNTED = ['ApiTab', 'ClaudeCodePanel', 'CodexPanel']


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the promised door exists')

    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    providers = (ROOT / 'modals' / 'providers.jsx').read_text(encoding='utf-8')
    settings = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    client = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    v_bare = strip_comments(vault)

    # ── the promise is still on the wall ────────────────────────────────
    check('Connections still sells open-in-Obsidian',
          'open-in-Obsidian' in providers,
          'if the promise is ever withdrawn, the gate below can go with it')
    check('…and the switch that is supposed to buy it is still there',
          "onClick={()=>setBackend('rest')}" in providers,
          'OBSIDIAN REST is what makes the promise true')

    # ── the door ────────────────────────────────────────────────────────
    callers = []
    for p in sorted(ROOT.rglob('*.jsx')):
        rel = str(p.relative_to(ROOT))
        if rel.startswith('.claude') or 'node_modules' in rel or 'dist-ui' in rel:
            continue
        if rel == 'claude-client.jsx':
            continue          # where it is implemented, not a door onto it
        if 'vaultOpenInObsidian' in strip_comments(p.read_text(encoding='utf-8')):
            callers.append(rel)
    check('something in the product actually calls vaultOpenInObsidian',
          callers, 'implemented, exported, and reachable from nowhere')
    check('the client method still posts to the endpoint it names',
          'vaultOpenInObsidian' in client and "'/vault/open'" in client,
          'the last inch of the path')

    # Both editor toolbars — the desktop split view and the tabbed one.
    # A control on only one of them is the same defect on a smaller screen.
    heads = [m.start() for m in re.finditer(r'className="vault-edit-head"', v_bare)]
    check('both editor toolbars are still there to carry it', len(heads) == 2, heads)
    windows = [v_bare[i:i + 1600] for i in heads]
    check('…and both of them render the control',
          all('onClick={openInObsidian}' in w and 'onClick={renameNote}' in w
              for w in windows),
          [('openInObsidian' in w) for w in windows])

    # ── the gate ────────────────────────────────────────────────────────
    check('the gate is stated once', v_bare.count('const _obsidianOn') == 1,
          'one condition, or it is two conditions')
    check('the gate reads the live backend', GATE in v_bare,
          'not a settings value, not a cached flag — what /vault/status says now')
    lines = re.findall(r'[^\n]*onClick=\{openInObsidian\}', v_bare)
    check('the control never renders ungated',
          lines and all('_obsidianOn &&' in l for l in lines), lines)

    check('the server still refuses every other backend',
          SERVER_GUARD in serve and SERVER_REFUSAL in serve,
          'the gate is only honest while this is what the endpoint does')
    check('the pane that makes the promise reads the backend the same way',
          "status.backend === 'rest'" in providers,
          'VaultTab and the vault pane must not disagree about what "on" means')

    # ── the failure path ────────────────────────────────────────────────
    fn = re.search(r'const openInObsidian = async \(\) => \{.*?\n  \};', v_bare, re.S)
    check('the handler lifts', bool(fn))
    if fn:
        body = fn.group(0)
        # Obsidian is a SEPARATE APP. `snag` routes through officeCause,
        # whose first rule owns ECONNREFUSED for the office itself — driven
        # live with the plugin shut, it blamed the office, which had just
        # answered with a 502 saying Obsidian refused.
        check('a real failure names Obsidian, not the office',
              'obsidianCause(' in body and 'snag(' not in body, body[-260:])
        check('…and never the raw cause underneath it',
              'e.message' in body and '${e.message}' not in body,
              'the message goes THROUGH the classifier, never around it')
        check('a note with no path is a no-op, not a request',
              'if (!n || !n.path) return;' in body, body[:200])
    check('the vault pane still has no native alert()',
          'alert(' not in v_bare, '#37 — five of them lived in this file')
    check('the classifier is imported, not re-implemented here',
          "import { obsidianCause, officeCause } from '../app/floor.jsx';" in vault,
          'one classifier family, one file — see the paragraph above OFFICE_CAUSES')
    # An import of a name the module does not export is not a soft failure:
    # the whole bundle refuses to load, so the office is a blank page. This
    # is the arm that survived the first fire pass — the checks above read
    # the import line and the table body and neither looked at the seam
    # between them.
    floor_src = (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8')
    exported = set(re.findall(r'[\w$]+', re.search(r'^export \{(.*?)\};',
                                                   floor_src, re.M | re.S).group(1)))
    wanted = set(re.findall(r'[\w$]+',
                            re.search(r"import \{([^}]*)\} from '\.\./app/floor\.jsx';",
                                      vault).group(1)))
    check('…and every name it imports is really exported',
          wanted <= exported, sorted(wanted - exported))

    # ── the premise that deleted it ─────────────────────────────────────
    for claim, name in STALE_CLAIMS:
        holders = []
        for p in sorted(ROOT.rglob('*.jsx')):
            rel = str(p.relative_to(ROOT))
            if rel.startswith('.claude') or 'node_modules' in rel or 'dist-ui' in rel:
                continue
            if claim in p.read_text(encoding='utf-8'):
                holders.append(rel)
        check(name, not holders, holders)

    imports = re.findall(r"import \{ (\w+) \} from '\./providers\.jsx';", settings)
    check('settings.jsx really does mount four of its panels',
          sorted(imports) == sorted(MOUNTED), imports)
    check('…and providers.jsx really does export them',
          all(f'export function {n}(' in providers for n in MOUNTED),
          [n for n in MOUNTED if f'export function {n}(' not in providers])
    check('the part of the old claim that is still true is still true',
          all(f'export function {n}(' not in providers for n in UNMOUNTED),
          'ApiTab and the CLI panels really are held back for a build flag')

    # ── drive the real gate over every backend the server can report ────
    if not shutil.which('node'):
        print('SKIP (partial) — node not on PATH; static checks above still ran')
    else:
        expr = GATE[GATE.index('=') + 1:].strip().rstrip(';')
        js = ('const GATE = ' + json.dumps(expr) + ';\n'
              + r'''
const gate = new Function('status', 'return (' + GATE + ');');
/* Every shape /vault/status can hand this pane, plus the two the pane
   makes for itself: null while loading, and the encrypted-shell bridge. */
console.log(JSON.stringify({
  loading:   gate(null),
  fs:        gate({ configured: true,  backend: 'fs'   }),
  rest:      gate({ configured: true,  backend: 'rest' }),
  oci:       gate({ configured: true,  backend: 'oci'  }),
  bridge:    gate({ configured: true,  backend: 'bridge' }),
  unconfig:  gate({ configured: false, unavailable: true, error: 'boom' }),
  noBackend: gate({ configured: true }),
}));
''')
        p = subprocess.run(['node', '--input-type=module', '-e', js],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            check('the lifted gate runs', False, p.stderr.strip()[:400])
        else:
            r = json.loads(p.stdout.strip().split('\n')[-1])
            check('the boss who did the Obsidian setup gets the button',
                  r['rest'] is True, r)
            # Every one of these is a build where pressing it could only
            # produce a snag. That is the ticket, inverted.
            check('…and nobody else is shown a button that can only fail',
                  not any(r[k] for k in
                          ['loading', 'fs', 'oci', 'bridge', 'unconfig', 'noBackend']),
                  r)
            check('a pane still loading is not a crash',
                  r['loading'] is False, 'status is null until /vault/status answers')

        # ── the fifth subject: what the boss is told when it fails ──────
        floor = (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8')
        f_bare = strip_comments(floor)
        tbl = re.search(r'const OBSIDIAN_CAUSES = \[.*?\n\];\n\nfunction obsidianCause'
                        r'\(raw\) \{.*?\n\}', f_bare, re.S)
        off = re.search(r'const OFFICE_CAUSES = \[.*?\n\];\n\nfunction officeCause'
                        r'\(raw\) \{.*?\n\}', f_bare, re.S)
        check('the Obsidian table lifts', bool(tbl))
        check('the office table lifts', bool(off))
        if tbl and off:
            cjs = ('const SRC = ' + json.dumps(off.group(0) + '\n' + tbl.group(0)) + ';\n'
                   + r'''
const m = new Function('cleanCause', SRC + ' return { obsidianCause, officeCause };')(
  (s) => String(s).slice(0, 90));
/* Measured 2026-08-16 against the real endpoint: the 502 body serve.py
   returns when the plugin is shut, plus the other four ways it says no. */
console.log(JSON.stringify({
  refused:  m.obsidianCause('obsidian: [Errno 61] Connection refused'),
  http401:  m.obsidianCause('obsidian: http 401'),
  timeout:  m.obsidianCause('obsidian: timed out'),
  wrongBk:  m.obsidianCause('open-in-Obsidian requires REST backend'),
  notFound: m.obsidianCause('obsidian: http 404'),
  unknown:  m.obsidianCause('something nobody has a rule for'),
  officeStillOwnsIt: m.officeCause('[Errno 61] Connection refused'),
}));
''')
            cp = subprocess.run(['node', '--input-type=module', '-e', cjs],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
            if cp.returncode != 0:
                check('the lifted classifier runs', False, cp.stderr.strip()[:400])
            else:
                c = json.loads(cp.stdout.strip().split('\n')[-1])
                check('a shut plugin is Obsidian being shut, not the office',
                      'Obsidian' in c['refused'] and 'office' not in c['refused'],
                      c['refused'])
                check('…and the office table still owns that word for the office',
                      'office' in c['officeStillOwnsIt'], c['officeStillOwnsIt'])
                check('a refused key sends the boss to where the key lives',
                      'Local REST API settings' in c['http401'], c['http401'])
                check('a timeout does not read as a refusal', 'starting up' in c['timeout'],
                      c['timeout'])
                check('the backend jargon never reaches the boss',
                      'REST backend' not in c['wrongBk'] and 'Connections' in c['wrongBk'],
                      c['wrongBk'])
                check('a missing note blames the path, not the app',
                      'different folder' in c['notFound'], c['notFound'])
                check('an unrecognised failure falls through, it does not invent',
                      c['unknown'] and 'Obsidian' not in c['unknown'], c['unknown'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())

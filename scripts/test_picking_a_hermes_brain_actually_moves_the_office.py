#!/usr/bin/env python3
"""Picking a Hermes backend must reach the gateway, not just the select.

Bug (modals/providers.jsx, ApiTab):

    const changeBackend = (prov) => {
      if (!HBACKENDS[prov]) return;
      setHBackend(prov); update({ hermesBackend: prov });
    };

That is the entire handler behind the "Hermes brain (runs in your office)"
select. It wrote a browser preference and stopped. The ONLY code path that
ever told the container to switch was the key field's onBlur -> saveKey,
which opens with

    if (val === (s[meta.field] || '')) return;

so a backend whose key is already on file could not be applied at all: the
field renders that saved key as its defaultValue, blurring it re-submits an
unchanged value, and saveKey returns before calling hermesSetProvider.

Measured consequence: a boss on OpenRouter (50 requests/day on :free) who
has a Gemini key saved picks "Google Gemini (most reliable free)". The
select moves, the sub-line under it changes to Gemini's ~1500/day note, no
error appears, no "gateway reloading (~15s)" appears either — and the
office keeps running OpenRouter, keeps hitting the cap they switched to
escape. hermesEnsureProvider cannot repair it: it re-pushes only when
hermesGetProvider reports `configured: false`, and this container IS
configured (with the old provider). On the next reload the same
hermesGetProvider call snaps the select back to openrouter, so the switch
vanishes with nothing ever having said it did not take.

The local half of this select never had the defect: picking LM Studio /
Ollama lands on saveLocalBackend, which does push to hermesSetProvider.

Fix: changeBackend applies a cloud backend that has a key on file, and says
so with the same "applied · gateway reloading (~15s)" line the key path
uses; when the server refuses or is offline it says the office is still on
the old brain instead of staying silent. A backend with NO saved key stays
silent and defers to the key field, which is the only thing that can help.

This lifts the REAL HBACKENDS table and the REAL changeBackend/saveKey
bodies out of modals/providers.jsx (brace-balanced extraction, same
technique as test_a_turn_is_billed_once_not_twice.py), stubs the React
state setters and CafresoHQClient, and drives the select.
Run: python3 scripts/test_picking_a_hermes_brain_actually_moves_the_office.py
"""
import json
import re
import subprocess
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


def _balance(src, i):
    """Return src[start_of_stmt:end] for a brace/paren-balanced value that
    begins at index i (the first char after `=`), ending at the `;` that
    closes the top-level statement."""
    depth = 0
    j = i
    while j < len(src):
        c = src[j]
        if c in '{([':
            depth += 1
        elif c in '})]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[i:j + 1]
        j += 1
    return None


def extract_const(src, name):
    """Brace-balanced extraction of `const NAME = <value>;` (arrow fn or
    object literal), returned as a full statement."""
    m = re.search(r'\bconst\s+' + re.escape(name) + r'\s*=\s*', src)
    if not m:
        return None
    val = _balance(src, m.end())
    return None if val is None else ('const %s = %s' % (name, val))


HARNESS = r"""
'use strict';
%(hbackends)s

/* ── the React/component context the lifted handlers close over ───────── */
let hBackend = 'openrouter';
let settings = {};
const calls = [];        // every hermesSetProvider(prov, key, model)
const updates = [];      // every update({...}) patch
let probeResult = null;
let keyBusy = false;

const s = new Proxy({}, { get: (_t, k) => settings[k] });
const setHBackend   = (v) => { hBackend = v; };
const update        = (p) => { updates.push(p); Object.assign(settings, p); };
const setProbeResult = (v) => { probeResult = v; };
const setKeyBusy     = (v) => { keyBusy = v; };

/* CafresoHQClient stand-in. Mirrors the real hermesSetProvider's contract:
   a reachable container answers { serverStored: true }. */
let SERVER_OK = true;
const C = {
  hermesSetProvider: async (prov, key, model) => {
    calls.push({ prov, key, model });
    return SERVER_OK
      ? { ok: true, serverStored: true, provider: prov }
      : { ok: true, serverStored: false, detail: 'offline — saved locally' };
  },
};

%(changebackend)s
%(savekey)s

function reset(initial, backend) {
  settings = Object.assign({}, initial);
  hBackend = backend || 'openrouter';
  calls.length = 0; updates.length = 0;
  probeResult = null; keyBusy = false;
  SERVER_OK = true;
}

async function run() {
  const out = {};

  /* 1. THE BUG. Office is on OpenRouter; a Gemini key is already on file
        (saved earlier, or re-hydrated by hermesEnsureProvider). The boss
        picks Google Gemini from the select and touches nothing else. */
  reset({ hermesBackend: 'openrouter', openrouterKey: 'sk-or-v1-old',
          geminiKey: 'AIzaSaved' }, 'openrouter');
  await changeBackend('gemini');
  out.savedKeySwitch = {
    calls: calls.slice(), backend: hBackend, probe: probeResult,
    pref: settings.hermesBackend,
  };

  /* 1b. …and the key field's onBlur, which is the only other path, cannot
         cover for it: the field's defaultValue IS the saved key, so
         blurring re-submits an unchanged value and saveKey bails. */
  const callsAfterSwitch = calls.length;
  await saveKey('gemini', 'AIzaSaved');
  out.blurIsNoHelp = { extraCalls: calls.length - callsAfterSwitch };

  /* 2. No key on file yet — nothing to push, and the key field below is
        the real door. Must NOT invent a call (the server rejects an empty
        key with "invalid Groq key") and must not leave a stale success
        line from a previous action on screen. */
  reset({ hermesBackend: 'openrouter', openrouterKey: 'sk-or-v1-old' }, 'openrouter');
  probeResult = { ok: true, detail: 'stale line from earlier' };
  await changeBackend('groq');
  out.noKey = { calls: calls.slice(), probe: probeResult, backend: hBackend,
                pref: settings.hermesBackend };

  /* 3. Local backends belong to saveLocalBackend (URL blur), not here —
        pushing a keyless provider from the select would race it. */
  reset({ hermesBackend: 'openrouter', openrouterKey: 'sk-or-v1-old',
          hermesLmUrl: 'http://localhost:1234/v1' }, 'openrouter');
  await changeBackend('lmstudio');
  out.local = { calls: calls.slice(), backend: hBackend,
                pref: settings.hermesBackend };

  /* 4. Container unreachable: the switch must not be reported as applied. */
  reset({ hermesBackend: 'openrouter', geminiKey: 'AIzaSaved' }, 'openrouter');
  SERVER_OK = false;
  await changeBackend('gemini');
  out.offline = { calls: calls.slice(), probe: probeResult };

  /* 5. Unknown provider is still refused, and re-picking the current one
        is a no-op rather than a gratuitous gateway restart. */
  reset({ hermesBackend: 'gemini', geminiKey: 'AIzaSaved' }, 'gemini');
  await changeBackend('nonesuch');
  await changeBackend('gemini');
  out.noops = { calls: calls.slice(), updates: updates.slice(),
                backend: hBackend };

  /* 6. The busy latch is released either way, or the whole panel stays
        disabled after one switch. */
  out.busy = keyBusy;

  return out;
}

run().then(o => { console.log('__RESULT__' + JSON.stringify(o)); })
     .catch(e => { console.log('__ERROR__' + (e && e.stack || e)); });
"""


def main():
    print('ApiTab — picking a Hermes brain applies it to the office')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    hbackends = extract_const(text, 'HBACKENDS')
    changebackend = extract_const(text, 'changeBackend')
    savekey = extract_const(text, 'saveKey')
    check('HBACKENDS lifted from modals/providers.jsx', hbackends is not None)
    check('changeBackend lifted from modals/providers.jsx', changebackend is not None)
    check('saveKey lifted from modals/providers.jsx', savekey is not None)
    if FAILS:
        print('\nFAILED: %s' % FAILS)
        return 1

    js = HARNESS % {'hbackends': hbackends, 'changebackend': changebackend,
                    'savekey': savekey}
    tmp = ROOT / '.hermes_backend_switch_harness.mjs'
    tmp.write_text(js, encoding='utf-8')
    try:
        p = subprocess.run(['node', str(tmp)],
                           capture_output=True, text=True, timeout=60)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    if '__RESULT__' not in p.stdout:
        print('  FAIL  harness did not produce a result')
        print((p.stdout + p.stderr)[-2000:])
        return 1
    out = json.loads(p.stdout.split('__RESULT__', 1)[1].strip().splitlines()[0])

    # 1 — the switch reaches the gateway with the saved key.
    sk = out['savedKeySwitch']
    check('switching to a backend with a saved key pushes it to the gateway',
          len(sk['calls']) == 1, f"calls={sk['calls']}")
    if sk['calls']:
        check('it pushes the NEW provider (gemini), not the old one',
              sk['calls'][0]['prov'] == 'gemini', str(sk['calls'][0]))
        check('it pushes that provider\'s own saved key',
              sk['calls'][0]['key'] == 'AIzaSaved', str(sk['calls'][0]))
    check('the boss is told the gateway is reloading',
          bool(sk['probe']) and sk['probe'].get('ok') is True
          and 'reloading' in (sk['probe'].get('detail') or ''),
          str(sk['probe']))
    check('the local preference still follows the select',
          sk['pref'] == 'gemini' and sk['backend'] == 'gemini', str(sk))

    # 1b — the key field genuinely cannot cover for it.
    check('the key field\'s onBlur alone would NOT have applied the switch',
          out['blurIsNoHelp']['extraCalls'] == 0,
          'saveKey re-submitting the unchanged saved key must still bail — '
          'that is why changeBackend has to do the work')

    # 2 — no key on file: defer to the key field, silently.
    nk = out['noKey']
    check('a backend with no saved key pushes nothing',
          nk['calls'] == [], str(nk['calls']))
    check('and clears the stale success line rather than leaving it up',
          nk['probe'] is None, str(nk['probe']))
    check('the select and preference still move for a keyless backend',
          nk['backend'] == 'groq' and nk['pref'] == 'groq', str(nk))

    # 3 — local backends stay with saveLocalBackend.
    lo = out['local']
    check('a local backend is not pushed from the select (saveLocalBackend owns it)',
          lo['calls'] == [], str(lo['calls']))
    check('but the select and preference still move for a local backend',
          lo['backend'] == 'lmstudio' and lo['pref'] == 'lmstudio', str(lo))

    # 4 — offline must not read as success.
    off = out['offline']
    check('an unreachable container is not reported as applied',
          bool(off['probe']) and off['probe'].get('ok') is False,
          str(off['probe']))
    check('and the failure line says the office is still on the old brain',
          'still on the old brain' in (off['probe'] or {}).get('detail', '')
          or 'offline' in (off['probe'] or {}).get('detail', ''),
          str(off['probe']))

    # 5 — no-ops.
    no = out['noops']
    check('an unknown provider is refused (no push, no preference write)',
          not any(u.get('hermesBackend') == 'nonesuch' for u in no['updates']),
          str(no['updates']))
    check('re-picking the backend already selected does not restart the gateway',
          no['calls'] == [], str(no['calls']))

    # 6 — latch released.
    check('the busy latch is released after a switch', out['busy'] is False)

    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'hermes backend switch: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

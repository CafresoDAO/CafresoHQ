#!/usr/bin/env python3
"""`hasUsableKey` (claude-client.jsx) misjudged readiness for a Groq,
Gemini-API, Gemini-CLI, or per-agent-pinned OpenRouter coworker.

`parseModelId` recognizes 'groq:', 'gemini-api:', 'gemini:', and
'openrouter:' as real per-agent provider prefixes, and modals/hire.jsx's
FRONT_DESK offers exactly these as "cloud" cards (a_cloud_groq,
a_cloud_gemini, a_cloud_openrouter) — but ONLY when the server itself
already reports `det.authenticated` for that driver (hire.jsx ~line 312:
`if (FRONT_DESK[d.id] && FRONT_DESK[d.id].cloud) return !!det.authenticated;`).
Once hired, `app/cast.jsx`'s `agentBrainReady()` probes readiness with
`hasUsableKey({...settings, provider: parsed.provider})` — but the
switch in `hasUsableKey` had no case for 'gemini', 'groq', or
'gemini-api', and its 'openrouter' case fell into the SAME default
branch as the bare 'hermes' fallback:

    case 'hermes':
    case 'openrouter':
    default:           return !!s.openrouterKey || !!_managedBrain;

`s.openrouterKey` is an unrelated field — the Hermes-internal backend
key a boss can type into Settings → Providers to make the CONTAINER's
shared Hermes brain ride OpenRouter (modals/providers.jsx's HBACKENDS
flow). It has nothing to do with a per-agent coworker whose model is
pinned to 'groq:...' / 'gemini-api:...' / 'openrouter:...' and whose
key already lives server-side, authenticated before the hire card was
ever shown.

Concrete failure: hire a Groq or Gemini-API coworker (or repoint an
existing one to it in Settings → Roster) on an office whose default
Hermes provider has no managed brain and no Hermes-internal OpenRouter
key. That coworker is fully functional, but `hasUsableKey` said no,
which broke `officeHasBrain()` (the "⚠ ADD AI KEY" alarm stays lit for
a working office), `routeOut()` (skips this working coworker when
suggesting who else can help), and modals/hire.jsx's inline brain-picker
warning (falsely tells the boss to go add a key that isn't needed).

The GLOBAL "Brain (this browser)" selector (modals/providers.jsx's
PROVIDER panel) has no "openrouter" option — its choices are lmstudio,
ollama, anthropic, google, claudecode, hermes, codex — so a per-agent
'openrouter' probe can never collide with the legitimate
s.openrouterKey gate, which only ever fires from the 'hermes'/default
branch.

Fix: added explicit cases for 'gemini', 'groq', 'gemini-api', and
'openrouter' returning true unconditionally, matching 'claudecode' and
'codex' — all four are offered only after server-side authentication,
so there is nothing left to check client-side.

Run: python3 scripts/test_hasusablekey_covers_server_authed_providers.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT_JSX = ROOT / 'claude-client.jsx'
HIRE_JSX = ROOT / 'modals' / 'hire.jsx'
PROVIDERS_JSX = ROOT / 'modals' / 'providers.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    i = src.index(header)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise ValueError('unbalanced braces for ' + header)


def main():
    print("hasUsableKey covers every server-authenticated per-agent provider")

    src = CLIENT_JSX.read_text(encoding='utf-8')
    fn = brace_lift(src, 'function hasUsableKey(s) {')

    for prov in ('gemini', 'groq', 'gemini-api', 'openrouter'):
        check(f"hasUsableKey has an explicit case for '{prov}'",
              re.search(r"case '" + re.escape(prov) + r"':", fn) is not None)

    check("those four cases return true unconditionally (server-authenticated, "
          "nothing left to check client-side) — the actual regression: they "
          "used to fall through to the bare-hermes default's "
          "s.openrouterKey/_managedBrain check, an unrelated setting",
          bool(re.search(
              r"case 'gemini':.*?case 'groq':.*?case 'gemini-api':.*?"
              r"case 'openrouter': return true;", fn, re.S)))

    hire_src = HIRE_JSX.read_text(encoding='utf-8')
    check("modals/hire.jsx's FRONT_DESK still offers exactly these four as "
          "cloud (server-key) cards — confirms the fix targets a real, "
          "still-current flow",
          all(f"model: '{p}:" in hire_src
              for p in ('openrouter', 'groq', 'gemini-api')))

    providers_src = PROVIDERS_JSX.read_text(encoding='utf-8')
    brain_select_m = re.search(
        r'<select value=\{s\.provider\}[\s\S]*?</select>', providers_src)
    check('found the GLOBAL "Brain (this browser)" <select value={s.provider}> '
          'block (distinct from the Hermes-backend <select value={hBackend}> '
          "a few lines below it, which DOES list an openrouter option but "
          "writes a different field entirely)",
          brain_select_m is not None)
    check('...and it has no "openrouter" option — so the new unconditional '
          "'openrouter' case in hasUsableKey can never shadow the legitimate "
          "s.openrouterKey Hermes-backend gate, which only fires from the "
          'bare hermes/default branch',
          brain_select_m is not None
          and '<option value="openrouter"' not in brain_select_m.group(0))

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'hasUsableKey below)', has_node, 'skipping the live-execution check')

    if has_node:
        js = f"""
        let _managedBrain = false;
        let _settings = {{}};
        {fn}
        const results = {{}};
        for (const provider of ['gemini', 'groq', 'gemini-api', 'openrouter']) {{
          // No managed brain, no openrouterKey typed anywhere — the exact
          // office state the bug report describes. A coworker pinned to
          // one of these providers is still fully functional.
          results[provider] = hasUsableKey({{ provider, openrouterKey: '' }});
        }}
        // The bare/default hermes case must still correctly gate on
        // s.openrouterKey || managedBrain — this fix must not make THAT
        // always-true too.
        results.hermesNoKeyNoBrain = hasUsableKey({{ provider: 'hermes', openrouterKey: '' }});
        results.hermesWithKey      = hasUsableKey({{ provider: 'hermes', openrouterKey: 'sk-or-x' }});
        _managedBrain = {{ model: 'gemma', provider: 'cafreso' }};
        results.hermesWithManagedBrain = hasUsableKey({{ provider: 'hermes', openrouterKey: '' }});
        console.log(JSON.stringify(results));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted hasUsableKey ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-800:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            for prov in ('gemini', 'groq', 'gemini-api', 'openrouter'):
                check(f"a coworker pinned to '{prov}' with no managed brain and "
                      'no Hermes-internal OpenRouter key now reads as usable — '
                      'this is exactly what was broken before the fix',
                      out.get(prov) is True, out)
            check('the bare hermes/default case still correctly says NOT usable '
                  'with no key and no managed brain (the fix must not make this '
                  'always-true too)',
                  out.get('hermesNoKeyNoBrain') is False, out)
            check('...but IS usable once a Hermes-internal OpenRouter key is set',
                  out.get('hermesWithKey') is True, out)
            check('...or once a managed brain is detected',
                  out.get('hermesWithManagedBrain') is True, out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

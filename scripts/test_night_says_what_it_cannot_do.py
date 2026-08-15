#!/usr/bin/env python3
"""A clean night, zero errors, and a coworker who could not do the job.

Reproduced 2026-08-15 against a canned brain (port 9236) whose reply was:

    I have built the landing page and it is ready to go live.
    [PUBLISH_SITE: /private/tmp/…/scratchpad/sp54/mysite]
    Published the site for you.

run_iteration returned writes: [], error: None — a run the morning report
counts as clean — and the summary carried the raw marker verbatim,
absolute filesystem path and all.

find_first_tool returns None for every one of the 23 TOOL_REGISTRY tools
outside the night subset, the hop loop's `if not hit: break` fires, and
nothing records that a reach happened. That is the same failure this
file's sibling in night_runner.py (find_first_tool's docstring) already
condemns for harmony syntax: a quiet night and a coworker who could not
do the job are indistinguishable to whoever reads the report.

The SEAM is deliberate and stays. Publishing signs with the boss's
identity and at 3am nobody is holding it, so the fix is not access, it is
admitting the reach — in office words, with a door.

Second half, measured the same day: four surfaces slice lastError, at
90 / 60 / 200 / 50. The shipped 51-character message — itself already
shortened once after an earlier truncation — was one over the tightest,
so the CLI night report had been printing "…nothing reached the vaul".
Hand-counting is what produced 51; NIGHT_ERROR_MAX plus the checks here
are what stop the next one.

Run: python3 scripts/test_night_says_what_it_cannot_do.py
"""
import os
import re
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import night_runner as nr          # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def strip_js_comments(src):
    """Two of this repo's past checks passed by matching prose written in
    the very commit that introduced them. Every scan below runs on code."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the night shift says what it cannot do')

    # ── 1. no 24th silent no-op ─────────────────────────────────────────
    registry = set(re.findall(
        r"name:\s*'([A-Z_]+)',\s*(?:/\*[\s\S]*?\*/\s*)?re:\s*/",
        read('hq-runtime.jsx')))
    check('the browser registry was found', len(registry) > 20, len(registry))
    classified = set(nr._TOOL_RE_SRC) | set(nr.NIGHT_CANNOT) | set(nr.NIGHT_IGNORES)
    missing = sorted(registry - classified)
    check('every browser tool is supported, named, or explicitly ignored',
          not missing,
          f'{missing} — a tool added to the browser and forgotten here '
          'becomes another marker the night shift drops in silence')
    # The reverse: a name here that no longer exists is a phrase nobody
    # will ever read, and hides that the real name changed.
    stale = sorted((set(nr.NIGHT_CANNOT) | set(nr.NIGHT_IGNORES)) - registry)
    check('...and nothing is named here that the browser dropped', not stale, stale)
    check('the seam still holds — publishing is not night-callable',
          'PUBLISH_SITE' not in nr._TOOL_RE_SRC,
          'the fix is admitting the reach, never granting it')

    # ── 2. the sentence survives the narrowest surface ──────────────────
    # Scanning the JSX for what it actually slices, rather than trusting a
    # constant to have been kept in step with four separate files.
    slices = []
    for rel in ('features.jsx', 'missions.jsx', 'views/terminal.jsx'):
        src = strip_js_comments(read(rel))
        for m in re.finditer(r'lastError[^\n]{0,40}?\.slice\(\s*0\s*,\s*(\d+)\s*\)', src):
            slices.append((rel, int(m.group(1))))
    check('the surfaces that slice a night error were found', len(slices) >= 3, slices)
    tightest = min(n for _f, n in slices) if slices else 0
    check('NIGHT_ERROR_MAX is no wider than the narrowest surface',
          nr.NIGHT_ERROR_MAX <= tightest,
          f'budget {nr.NIGHT_ERROR_MAX} vs tightest slice {tightest} '
          f'({slices}) — a sentence is only as complete as the narrowest '
          'place it is read')

    too_long = [(t, s) for t in nr.NIGHT_CANNOT
                for s in [nr.night_cannot_sentence(t)]
                if len(s) > nr.NIGHT_ERROR_MAX]
    check('every "cannot" sentence fits the budget', not too_long,
          [(t, len(s)) for t, s in too_long])

    # The other night error, which is what taught this lesson. Lifted from
    # source so a future edit to the wording is measured, not assumed.
    lit = re.findall(r"error = '([^']{10,})'", read('night_runner.py'))
    check('the write-claim message was found in source', lit, lit)
    over = [s for s in lit if len(s) > nr.NIGHT_ERROR_MAX]
    check('...and it fits too', not over, [(s, len(s)) for s in over])

    # ── 3. office words, not wire names ─────────────────────────────────
    # §6. The tool NAME is the thing the boss must never be handed; the
    # phrase is what replaces it.
    leaks = [t for t in nr.NIGHT_CANNOT
             if re.search(r'[A-Z]{2,}|_', nr.night_cannot_sentence(t))]
    check('no sentence hands the boss a protocol name', not leaks, leaks)
    check('...and each one names a way forward',
          all('in the office' in nr.night_cannot_sentence(t) for t in nr.NIGHT_CANNOT),
          '§7: a refusal with no door is half a message')

    # ── 4. detection ────────────────────────────────────────────────────
    f = nr.find_unsupported_tool
    check('a bracket marker for an unavailable tool is seen',
          f('ready to go live.\n[PUBLISH_SITE: /tmp/site]\nDone.') == 'PUBLISH_SITE')
    check('...in harmony syntax too',
          f('<|channel|>commentary to=functions.publish_site<|constrain|>json'
            '<|message|>{"path":"/tmp/site"}<|call|>') == 'PUBLISH_SITE',
          'a model that speaks harmony reaches in harmony as well')
    check('...and lowercase, the way models actually write it',
          f('[publish_site: /tmp/site]') == 'PUBLISH_SITE')
    check('a supported tool is not reported as unavailable',
          f('[VAULT_NEW: Research/a.md]\nbody\n[/VAULT_NEW]') is None)
    check('prose in brackets is not a tool call',
          f('I considered [NOTE: this] and [TODO: that].') is None,
          'membership in the table is what makes this safe, not the shape')
    check('an acknowledgement is not reported as a failed reach',
          f('[ACK: got it]') is None,
          'ACK implies no work; reporting it would be noise')

    # ── 5. the raw marker never reaches the boss ────────────────────────
    s = nr.strip_unsupported_markers(
        'Built it.\n[PUBLISH_SITE: /Users/someone/private/path/site]\nAll set.')
    check('the marker is stripped from the summary', 'PUBLISH_SITE' not in s, s)
    check('...along with the filesystem path it carried',
          '/Users/someone' not in s,
          'the reproduced summary printed an absolute path from the '
          "boss's own machine")
    check('...and the sentences around it survive',
          'Built it.' in s and 'All set.' in s, s)
    check('a supported marker is left alone',
          '[VAULT_READ: a.md]' in nr.strip_unsupported_markers('see [VAULT_READ: a.md]'))

    # ── 6. what the record says ─────────────────────────────────────────
    # run_iteration with the network stubbed out: this is the exact shape
    # that came back green from the live canned-brain run.
    reply = ('I have built the landing page and it is ready to go live.\n'
             '[PUBLISH_SITE: /private/tmp/scratch/mysite]\n'
             'Published the site for you.')
    ctx = types.SimpleNamespace(base_url='http://127.0.0.1:0', api_key=None,
                                brave_key=None, hermes_home=None, ssl_ctx=None)
    orig_llm, orig_notes = nr.llm_call, nr._notes_index
    nr.llm_call = lambda _c, _m, max_tokens=0: (reply, 0)
    nr._notes_index = lambda _c, _f: ''
    try:
        rec = nr.run_iteration(ctx, {'agentName': 'Nova', 'topic': 't',
                                     'vaultFolder': 'Research/night'}, 0, 1)
    finally:
        nr.llm_call, nr._notes_index = orig_llm, orig_notes

    check('the run no longer reports a clean night', rec.get('error'), rec)
    check('...naming what was reached for',
          'publishing' in (rec.get('error') or ''), rec.get('error'))
    check('...and it fits the narrowest surface',
          len(rec.get('error') or '') <= nr.NIGHT_ERROR_MAX,
          f"{len(rec.get('error') or '')} chars")
    check('...while the summary carries no wire format',
          'PUBLISH_SITE' not in (rec.get('summary') or ''), rec.get('summary'))
    check('...and no path from the boss\'s machine',
          '/private/tmp/scratch' not in (rec.get('summary') or ''), rec.get('summary'))
    # The reply also claims a write it never made. Both are true; the reach
    # is the one with a door on it, so it is the one that gets said.
    check('the reach outranks the generic write-claim line',
          'saved a note' not in (rec.get('error') or ''), rec.get('error'))

    print()
    if FAILS:
        print(f'night cannot: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('night cannot: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

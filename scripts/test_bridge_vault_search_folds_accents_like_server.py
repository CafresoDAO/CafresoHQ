#!/usr/bin/env python3
"""The encrypted bridge vault's client-side search silently missed
accented notes that the server-backed vault search finds fine.

serve.py's `_fold_accents` (used by every backend arm of /vault/search
via `_vault_search_hit`) NFD-decomposes each character and drops the
combining marks before matching, specifically so 'unicas' finds
'únicas' and 'investigacion' finds 'investigación' — the docstring
spells out the reason: "or the search quietly splits the vault by
keyboard layout."

`views/vault.jsx`'s `bridgeSearch` — used only when a `VaultBridge` is
present (the encrypted shell holding the boss's actual identity-linked
notes, which has no vault:search message of its own, so the client has
to score locally) — had its own comment claiming it "Mirrors serve.py's
own /vault/search scoring... so results rank the same either way," but
it matched with plain `.toLowerCase()` and no accent folding at all.
Concretely: a note containing "investigación" was findable by typing
"investigacion" against the server-backed vault, but NOT against the
bridge vault — the more security-conscious, identity-holding path
silently returned zero hits for the same query, with no error or
fallback notice (the "silent-wrong-answer failure the vetKeys trust
story can't afford," per this same function's own comment about its
prior bug).

Found by a background hunt agent sweeping previously-unswept areas,
directly falsifying the "mirrors serve.py" claim in bridgeSearch's own
comment by diffing it against serve.py's actual `_fold_accents`/
`_vault_search_hit`.

Fix: added `_foldAccents` (views/vault.jsx), a JS port of serve.py's
`_fold_accents` — NFD-decompose each code point, drop combining marks
(U+0300-U+036F), building an index map back to the original text so the
snippet still comes from the untouched original (accents intact).
`bridgeSearch` now folds the query, each candidate's title, and each
candidate's body through it before scoring, matching the server arm.

This test extracts `_foldAccents` verbatim from source (not a
hand-copied duplicate) and genuinely executes it via Node, confirming
an accented and unaccented spelling now fold to the same string and
that snippet extraction still recovers ORIGINAL (accented) text via the
index map — not a folded copy.

Run: python3 scripts/test_bridge_vault_search_folds_accents_like_server.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT_JSX = ROOT / 'views' / 'vault.jsx'
SERVE_PY = ROOT / 'serve.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("bridgeSearch folds accents the same way serve.py's /vault/search does")

    src = VAULT_JSX.read_text(encoding='utf-8')
    serve_src = SERVE_PY.read_text(encoding='utf-8')

    fold_m = re.search(
        r"const _foldAccents = \(s\) => \{\n(.*?)\n\};\n",
        src, re.S)
    check('found the _foldAccents helper', fold_m is not None)
    fold_body = fold_m.group(0) if fold_m else ''

    check('_foldAccents drops Unicode combining marks (U+0300-U+036F), '
          'matching serve.py\'s category-Mn strip',
          '\\u0300-\\u036f' in fold_body)
    check('_foldAccents NFD-normalizes before stripping (required so a '
          'precomposed accented character actually decomposes into a '
          'base letter + combining mark to strip)',
          "normalize('NFD')" in fold_body)

    check("serve.py's _fold_accents still exists and still NFD-decomposes "
          "+ drops category Mn (confirms this test is comparing against "
          "the real current server behavior, not a stale assumption)",
          "unicodedata.normalize('NFD', c)" in serve_src
          and "unicodedata.category(ch) == 'Mn'" in serve_src)

    bridge_m = re.search(
        r"const bridgeSearch = async \(query\) => \{(.*?)\n  \};",
        src, re.S)
    check('found bridgeSearch', bridge_m is not None)
    bridge_body = bridge_m.group(1) if bridge_m else ''

    # A later fix (the multi-word AND-search ticket) split `query` into
    # words before folding each one, so the literal call is now
    # `_foldAccents(w)` inside a `String(query).split(...).map(...)` —
    # still folding the query, just per word instead of as one phrase.
    # Accept either shape so this accent check doesn't false-positive as
    # a regression the next time the query-handling shape legitimately
    # changes; it only fails if `query` stops being folded at all.
    check('bridgeSearch folds the query through _foldAccents before '
          'matching (the actual regression — it used to be plain '
          'query.toLowerCase())',
          '_foldAccents(query)' in bridge_body
          or ('String(query).split' in bridge_body and '_foldAccents(w)' in bridge_body))
    check('bridgeSearch folds each candidate\'s body text through '
          '_foldAccents before matching',
          bool(re.search(r'_foldAccents\(text\)', bridge_body)))
    check('bridgeSearch folds each candidate\'s title through '
          '_foldAccents before matching',
          bool(re.search(r'_foldAccents\(f\.title\)', bridge_body)))
    check('bridgeSearch no longer relies on plain .toLowerCase() for its '
          'own match/score computation (the old, accent-blind path)',
          not re.search(r'const ql = query\.toLowerCase\(\)', bridge_body))

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          '_foldAccents helper below)', has_node,
          'skipping the live-execution check')

    if has_node and fold_m:
        js = f"""
        {fold_m.group(0)}
        const [accented] = _foldAccents('investigación');
        const [plain] = _foldAccents('investigacion');
        const [upper] = _foldAccents('INVESTIGACIÓN');
        console.log(JSON.stringify({{ accented, plain, upper }}));

        // Snippet-recovery check: the index map must point back to the
        // ORIGINAL (accented) text, not the folded copy.
        const original = 'Notas sobre la investigación única del proyecto.';
        const [ftext, tmap] = _foldAccents(original);
        const [fq] = _foldAccents('investigacion');
        const idx = ftext.indexOf(fq);
        const oStart = tmap[idx], oEnd = tmap[idx + fq.length - 1] + 1;
        const recovered = original.slice(oStart, oEnd);
        console.log(JSON.stringify({{ idx, recovered }}));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted _foldAccents helper ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            import json
            lines = r.stdout.strip().splitlines()
            fold_out = json.loads(lines[0])
            check('an accented spelling and its unaccented equivalent fold '
                  'to the identical string (this is exactly what was '
                  'missing before the fix — bridgeSearch would have '
                  'scored these as two different strings, silently '
                  'missing the accented note for an unaccented query)',
                  fold_out['accented'] == fold_out['plain'], fold_out)
            check('folding is also case-insensitive, matching the '
                  'lowercasing serve.py\'s fold does as part of the same '
                  'pass',
                  fold_out['upper'] == fold_out['plain'], fold_out)

            recover_out = json.loads(lines[1])
            check('the folded match still recovers the ORIGINAL '
                  '(accented) substring via the index map, not a folded '
                  'copy — the snippet shown to the boss must have their '
                  'own accents intact, not a normalized rewrite of their '
                  'note',
                  recover_out['recovered'] == 'investigación', recover_out)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

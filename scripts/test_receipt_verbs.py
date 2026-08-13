#!/usr/bin/env python3
"""The receipts tray called every non-vault deliverable an "append".

`recordToolReceipt` in app.jsx built its receipt title inline as

    ev.name === 'VAULT_NEW' ? 'Wrote' : 'Appended'

so every deliverable tool that wasn't VAULT_NEW filed under "Appended":
a coworker who CREATED index.html filed "Appended index.html" (watched
live 2026-08-13 on a fresh project, with the file confirmed newly created
on disk), an exported deck would file "Appended deck.pptx", a published
site "Appended https://…", a generated image "Appended logo.png".

That is not a cosmetic wording slip. The receipts tray is the permanent
record a boss scrolls back through to answer "who touched this, and did
they keep what was there?" — and "Appended" promises the previous
contents survived, which is the exact opposite of what FILE_WRITE
(create-or-overwrite) and the exporters do. The corkboard pin four lines
below in the same function already computed the right verb from a proper
ladder; only the receipt title was wrong, so the two surfaces disagreed
about the same event.

Fix: one `deliverableVerb(name)` helper, read by BOTH the corkboard pin
and the receipt title.

Run: python3 scripts/test_receipt_verbs.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


src = APP.read_text()

m = re.search(r'const deliverableVerb = \(name\) => \((.*?)\n  \);', src, re.S)
check(m, "app.jsx: could not find the `deliverableVerb` helper — the receipt "
         "title and the corkboard pin must share ONE verb ladder, or they "
         "drift back into disagreeing about the same event.")

if m:
    ladder = m.group(1)
    # Each tool's verb must be the true one for what that tool does to its target.
    expectations = [
        ('VAULT_APPEND', 'Appended',
         "VAULT_APPEND is the ONLY tool that appends — it must keep that verb."),
        ('PUBLISH_SITE', 'Published', "PUBLISH_SITE publishes."),
        ('EXPORT_', 'Exported', "the EXPORT_* family exports."),
        ('GENERATE_', 'Generated', "the GENERATE_* family generates."),
    ]
    for name, verb, why in expectations:
        pair = re.search(
            re.escape(name) + r"'?\s*\)?\s*(?:===\s*0\s*)?\?\s*'" + verb + r"'",
            ladder,
        )
        check(pair, f"deliverableVerb must map {name} → '{verb}' — {why}")

    # The fallback catches VAULT_NEW and FILE_WRITE: both create or overwrite.
    check(
        re.search(r":\s*'Wrote'", ladder),
        "deliverableVerb's fallback must be 'Wrote' — VAULT_NEW and FILE_WRITE "
        "both create-or-overwrite their target, and calling that an append "
        "tells the boss the old contents survived when they did not.",
    )
    check(
        ladder.count("'Appended'") == 1,
        "only VAULT_APPEND may resolve to 'Appended' — exactly one occurrence "
        f"expected in the ladder, found {ladder.count(chr(39) + 'Appended' + chr(39))}.",
    )

# Both consumers must read the helper, not re-derive a verb inline.
check(
    re.search(r'rcTitle\s*=\s*isDeliverable\s*\n?\s*\?\s*`\$\{deliverableVerb\(ev\.name\)\}', src),
    "the receipt title must call deliverableVerb(ev.name) — this is the "
    "surface that was wrong, and an inline ternary here is how it got wrong.",
)
check(
    re.search(r'const verb = deliverableVerb\(ev\.name\);', src),
    "the corkboard pin must call deliverableVerb(ev.name) too — it had the "
    "correct ladder locally, which is precisely why the two surfaces "
    "disagreed; sharing one helper is the fix.",
)
check(
    "ev.name === 'VAULT_NEW' ? 'Wrote' : 'Appended'" not in src,
    "the old inline `VAULT_NEW ? 'Wrote' : 'Appended'` ternary must be gone — "
    "it is the exact expression that filed created files as appends.",
)

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")

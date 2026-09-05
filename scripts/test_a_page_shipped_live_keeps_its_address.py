#!/usr/bin/env python3
"""The delivery sheet published a page to the public internet, then threw the address away.

Reproduced by reading the source. `modals/delivery.jsx` renders the
"🚀 Share it live" button; `doShare()` calls `CafresoHQClient.sharePage()`
and did exactly one thing with the result:

    setShare({ path, url: r.url });

That URL then lived in one place only: React state inside a modal that

  * is mounted at most ONCE per HQ — `app.jsx` gates it on
    `firstDeliverySeen`, which is a `useStored` flag, so the sheet never
    comes back after the first delivery; and
  * is unmounted by BOTH footer buttons — "Later" and the primary
    "Open the page →", which is the natural next click.

Nothing else in the product renders that address: there is no published-
sites list, and unlike `publishSite()` — which has always dropped a
clickable `<name>.url` deliverable into the project for precisely this
reason — `sharePage()` writes nothing back to the cabinet. So a boss who
hit Share, saw the link, and then clicked "Open the page →" had put a page
on the public internet and no longer had any way to find out where it was.

The fix files the address into the cabinet next to the page before the
sheet can be dismissed, and the sheet says whether that copy got written
(a cabinet write that fails must not report a successful publish as a
failure, but it must not be claimed either).

Run: python3 scripts/test_a_page_shipped_live_keeps_its_address.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / 'modals/delivery.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


print('a page shipped live keeps its address')

# ── 0. the premise: the sheet really is one-shot and really is dismissable ──
check('the sheet is gated on a stored firstDeliverySeen flag (shown once, ever)',
      re.search(r"useStored\(ks\('firstDeliverySeen'\), false\)", APP) is not None
      and re.search(r"if \(!firstDeliverySeen\) \{\s*\n\s*setFirstDeliverySeen\(true\);", APP)
      is not None,
      '— if this stops holding, the "lost forever" premise needs rechecking')
check('the primary footer button unmounts the sheet',
      re.search(r"onOpenNote\(path\); onClose\(\);", SRC) is not None)

doshare = re.search(r"const doShare = async \(\) => \{[\s\S]*?\n  \};", SRC)
check('found doShare()', doshare is not None)
body = doshare.group(0) if doshare else ''

# ── 1. the URL is written back to the cabinet, not just into React state ───
check('doShare() files the live link into the cabinet via vaultWrite',
      'CafresoHQClient.vaultWrite(' in body,
      '— setShare() alone leaves the address in a modal that is about to be closed forever')
check('...at a path derived from the page it published',
      re.search(r"String\(path\)\.replace\(/\\\.html\?\$/i, ''\) \+ '\.link\.md'", body)
      is not None)
check('...carrying the actual returned URL, not the vault path',
      re.search(r"vaultWrite\(\s*linkPath,[\s\S]{0,200}?\$\{r\.url\}", body) is not None)

# ── 2. the write happens BEFORE the sheet can be dismissed on a success ────
check('the cabinet write is awaited before setShare() reveals the URL',
      body.find('await CafresoHQClient.vaultWrite(') >= 0
      and body.find('await CafresoHQClient.vaultWrite(') < body.find('setShare({ path, url:'),
      '— filing after the reveal races the click that closes the sheet')

# ── 3. a failed filing must not sink a publish that actually succeeded ─────
check('the vaultWrite is wrapped in its own try/catch',
      re.search(r"try \{\s*\n\s*linkPath = [\s\S]*?\} catch \(_e\) \{ linkPath = null; \}", body)
      is not None,
      '— the page IS live at that point; throwing here would report success as an error')
check('the URL still renders when the filing failed',
      re.search(r"setShare\(\{ path, url: r\.url, linkPath \}\)", body) is not None)

# ── 4. and the sheet tells the truth about which of the two happened ───────
done = re.search(r"delivery-share-done[\s\S]{0,700}?</div>\s*\n\s*\) :", SRC)
check('found the success block', done is not None)
dblock = done.group(0) if done else ''
check('the success block names where the link was filed',
      'shareFor.linkPath' in dblock and 'cabinet' in dblock)
check('...and warns to copy it when nothing was filed',
      re.search(r"linkPath\s*\n?\s*\?[\s\S]{0,200}?:\s*\"[^\"]*copy it before you close[^\"]*\"",
                dblock) is not None,
      '— silence here would be the §4 lie: an address the boss cannot get back')

print()
if FAILS:
    print('%d check(s) failed:' % len(FAILS))
    for f in FAILS:
        print('  - ' + f)
    sys.exit(1)
print('all checks passed')

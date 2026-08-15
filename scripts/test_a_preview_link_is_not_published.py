#!/usr/bin/env python3
""""Published — link copied" handed the boss a localhost URL.

Reproduced 2026-08-15 on a live office (port 9254, standalone browser, no
II-holding shell). Added a project, opened its index.html, clicked
🚀 Publish, and the slot rendered:

    Published — link copied.
    http://127.0.0.1:9254/fs/site/L3ByaXZhdGUvdG1wL2NsYXVkZS01MDEv…/index.html

…with that URL written to the clipboard. Three separate problems in one
sentence:

  1. It was not published. publishSite() degrades to an owner-scoped
     /fs/site preview link whenever CafresoHQChain.isAvailable() is false —
     which is EVERY standalone and self-hosted office, so the fallback is
     the default path, not an edge case.
  2. The clipboard write is what turns "I opened a local link" into "I sent
     someone a dead link".
  3. The base64 path segment decodes to the absolute filesystem path of the
     boss's machine, in a URL the copy invited them to share.

The render decided what had happened by testing /^https?:/ against the
message. That establishes "this is a URL" and concludes "this went public".

sharePage() in claude-client.jsx already refuses the same fallback, and its
comment says why: a "share" that hands back a localhost link would be the
§4 kind of lie. Two publish surfaces, one policy — the preview link is
still built and still offered, it is just no longer called publishing.

Run: python3 scripts/test_a_preview_link_is_not_published.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = (ROOT / 'views' / 'projects.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
CLIENT = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """JS comments only. Every check below runs on this, because the
    explanations written IN THIS COMMIT contain the exact phrases the
    checks look for — 'Published', 'preview link', 'ai.cafreso.com'. A
    check that reads its own commit message passes on prose alone.
    (Learned the hard way in #57: three checks matched an ASCII diagram.)"""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def block(src, start, end_marker):
    """Source from `start` up to the next `end_marker` AFTER it.

    Searching from `i` rather than `i + len(start)` let the end marker
    match inside the start marker itself: 'function ' occurs six
    characters into 'async function sharePage', so the block came back as
    the string "async " and every check against it passed vacuously by
    finding nothing. A window that can collapse to nothing is worse than
    no window — it reports agreement.
    """
    i = src.find(start)
    if i < 0:
        return ''
    j = src.find(end_marker, i + len(start))
    return src[i:j if j > 0 else len(src)]


def main():
    print('a preview link is not a publish')
    p_code = strip_comments(PROJECTS)
    a_code = strip_comments(APP)
    c_code = strip_comments(CLIENT)

    # ── 1. the fallback still exists, and is still the default ──────────
    # If publishSite stopped falling back, most of this file is moot — but
    # so is the feature for every self-hosted office. Pinning it means a
    # later "simplification" that deletes the preview has to argue with a
    # named check rather than slip through.
    check('publishSite still builds a preview when the shell is absent',
          "mode = 'preview'" in c_code and '/fs/site/' in c_code,
          'the preview link is useful; the claim about it was the defect')
    check('...and reports which of the two happened',
          re.search(r"mode\s*=\s*'canister'", c_code) and 'mode' in c_code)

    # ── 2. the projects surface reads the outcome, not the string ───────
    pub = block(p_code, 'const publishOpen', 'const editorPane')
    check('the publish handler exists to check', pub)
    check('...and branches on the reported mode',
          "r.mode === 'canister'" in pub or "mode === 'canister'" in pub,
          'the old code never looked at mode at all')
    check('...and no longer decides by sniffing the URL for http',
          not re.search(r'/\^https\?:/\.test', p_code),
          'that test establishes "this is a URL" and concluded "published"')

    # The load-bearing one. Everything else is wording; this is the step
    # that put a dead link into a message the boss sends to someone.
    copies = re.findall(r'clipboard\.writeText', pub)
    check('the clipboard is written at most once', len(copies) <= 1, copies)
    if copies:
        before = pub[:pub.find('clipboard.writeText')]
        # The copy has to sit INSIDE the canister branch, after the early
        # return that ends it — measured by the branch keyword preceding it.
        check('...and only on the branch that actually went public',
              "=== 'canister'" in before,
              'a preview URL on the clipboard is a dead link the boss sends')

    # ── 3. what the boss is told ────────────────────────────────────────
    # 'Published' is allowed to appear, but not on the preview path. The
    # check is positional: the word must not survive downstream of the
    # canister branch's return.
    tail = pub[pub.rfind('return;'):] if 'return;' in pub else pub
    check('the word "Published" does not appear on the preview path',
          'Published' not in tail,
          'this is the exact sentence that shipped: "Published — link copied."')
    check('the preview path says plainly that it is not public',
          re.search(r'[Nn]ot public', tail), tail[:200])
    check('...and names the door to the real thing',
          'ai.cafreso.com' in tail,
          '§7: one honest sentence PLUS a way forward — a refusal with no '
          'door is half a message')

    # ── 4. the button names what it will do ─────────────────────────────
    # Detection, not the setting. canPublish() reads icpServices.publish,
    # which is the boss's intent; whether anything is reachable is a
    # separate question and the button was answering the wrong one.
    check('there is a reachability check distinct from the setting',
          'publicHostingReady' in p_code and 'isAvailable' in p_code,
          'canPublish() reads a settings flag, not whether a shell exists')
    check('...and the button label is chosen by it',
          re.search(r'publicHostingReady\(\)[\s\S]{0,400}?🚀 Publish', p_code),
          'the button promised publishing on offices that cannot publish')
    check('...offering the preview by its own name',
          'Preview link' in p_code,
          'a button does the thing it is named after — the rule this file '
          'already applies to its empty-state CTA')
    # The pre-check must NOT be what the result is read from: a handshake
    # can succeed and the upload still fail.
    check('the result is still read from the outcome, not the pre-check',
          'publicHostingReady' not in pub.split('await CafresoHQClient.publishSite')[-1],
          'a reachable shell is not the same fact as a completed upload')

    # ── 5. the approval-stamp path, which is the agent-driven one ───────
    stamp = block(a_code, "ap.kind === 'publish'", 'catch (err)')
    check('the stamp path exists to check', stamp)
    check('...and headlines the preview as preview, not as shipped',
          not re.search(r'Shipped[^\n]{0,40}\$\{where\}', stamp)
          and 'wentPublic' in stamp,
          'the clause said "a local preview link" under the headline '
          '"🚀 Shipped" — the headline is what gets read')
    check('...and the activity line does not say shipped for a preview',
          re.search(r'wentPublic[\s\S]{0,200}?shipped', stamp)
          and 'not published' in stamp,
          'the office ledger recorded "shipped … as a preview link"')

    # ── 6. the two publish surfaces agree ───────────────────────────────
    share = block(c_code, 'async function sharePage', 'function ')
    check('sharePage still refuses the fallback outright',
          'public hosting needs' in share and '/fs/site/' not in share,
          'the precedent this ticket brings publishSite into line with')

    print()
    if FAILS:
        print(f'preview vs published: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('preview vs published: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

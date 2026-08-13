#!/usr/bin/env python3
"""GENERATE_IMAGE/GENERATE_VIDEO were fully built and completely unreachable.

exporters.py's _generate_image/_generate_video are real, tested backend
tools (5 image providers, 4 video providers, clean structured errors on
every branch). hq-runtime.jsx's toolsForAgent gates both purely on
`s.imageProvider`/`s.videoProvider` being truthy. But an exhaustive grep of
every .jsx file for imageProvider/videoProvider/imageModel/videoModel/
a1111Url/comfyUrl turned up exactly four matches, all read-side: the two
gate checks, one comment, and _mediaConfig's own fallback logic. No control
anywhere in the product could ever make `s.imageProvider` truthy — the
settings keys existed, the backend worked, and there was no door to either.
See docs/OFFICE_AS_INTERFACE.md, "GENERATE_IMAGE/GENERATE_VIDEO are fully
built and completely unreachable" (2026-08-12).

Two-part fix:
  1. modals/providers.jsx: a new `export function MediaTab()` — provider
     pickers for image/video, model fields, base-URL fields for the two
     local providers (a1111/comfyui), and API-key fields for the three
     cloud providers (openai/google/fal) that write through the SAME
     encrypted vault generateImage/generateVideo already read
     (CafresoHQClient.setAgentKey/getAgentKey).
  2. modals/settings.jsx: import MediaTab, add a real 'media' entry to
     SETTINGS_TABS, and mount <MediaTab /> when activeTab === 'media'.

A second, related bug rides along: claude-client.jsx's _mediaConfig()
defaulted an unset video provider to 'openai' — the one video provider
guaranteed to fail (exporters.py's openai video branch is a hardcoded 501,
"Sora API is gated"). fal is the only video provider that can succeed on
just an API key, so that's the corrected default. Fixing the default was
moot while the gate had no door; both land in the same change.

Verified live: rebuilt via scripts/build_ui_bundle.mjs, drove
Settings -> Media in a throwaway office (CAFRESOHQ_HQ_STATE_DIR) and
confirmed the IMAGE GENERATION / VIDEO GENERATION / PROVIDER KEYS panels
render, save imageProvider/videoProvider/imageModel/videoModel/a1111Url/
comfyUrl to settings, and that a saved key round-trips through the vault
(hasAgentKey flips true after save, key never re-displayed).

Run: python3 scripts/test_media_settings_wired.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ROOT / 'modals' / 'providers.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
CLAUDE_CLIENT = ROOT / 'claude-client.jsx'

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


providers_src = PROVIDERS.read_text()
settings_src = SETTINGS.read_text()
client_src = CLAUDE_CLIENT.read_text()

# 1. MediaTab must actually be exported, not just defined.
check(
    re.search(r'^export function MediaTab\s*\(', providers_src, re.M),
    "modals/providers.jsx: MediaTab must be declared `export function MediaTab()` "
    "— without `export`, esbuild treats the import as undefined and drops the "
    "component from the bundle entirely (silent, no build error).",
)
check(
    not re.search(r'^function MediaTab\s*\(', providers_src, re.M),
    "modals/providers.jsx: found a non-exported `function MediaTab(` — "
    "there must be exactly one declaration and it must be exported.",
)

# 2. settings.jsx must import MediaTab from providers.jsx.
check(
    re.search(r"import\s*\{\s*MediaTab\s*\}\s*from\s*'\./providers\.jsx'", settings_src),
    "modals/settings.jsx: missing `import { MediaTab } from './providers.jsx';` "
    "— MediaTab must be pulled into the module that actually renders it.",
)

# 3. SETTINGS_TABS must have a real 'media' entry (not just an alias to
#    another tab — the old state had `media: 'appearance'` in
#    SETTINGS_TAB_ALIAS, which silently redirected any deep-link away from
#    a tab that didn't exist).
m = re.search(r'const SETTINGS_TABS\s*=\s*\[([\s\S]*?)\];', settings_src)
check(m, "modals/settings.jsx: could not find `const SETTINGS_TABS = [...]`.")
if m:
    check(
        re.search(r"id:\s*'media'", m.group(1)),
        "modals/settings.jsx: SETTINGS_TABS has no `{ id: 'media', ... }` entry "
        "— the nav rail has no way to reach the Media tab.",
    )

# 3b. The stale alias (media -> appearance) must be gone now that 'media'
#     is itself a canonical tab id; leaving it would make setTab('media')
#     redirect straight past the tab this test is pinning.
m = re.search(r'const SETTINGS_TAB_ALIAS\s*=\s*\{([\s\S]*?)\};', settings_src)
check(m, "modals/settings.jsx: could not find `const SETTINGS_TAB_ALIAS = {...}`.")
if m:
    check(
        not re.search(r"media\s*:\s*'appearance'", m.group(1)),
        "modals/settings.jsx: SETTINGS_TAB_ALIAS still maps media -> appearance "
        "— now that 'media' is a real tab id this alias would redirect any "
        "deep-link straight past it.",
    )

# 4. The settings body must actually mount <MediaTab /> gated on
#    activeTab === 'media', mirroring how icp-services/appearance/etc. are
#    mounted (cheap proxy: look for the exact conditional-render line).
check(
    re.search(r"activeTab === 'media'[\s\S]{0,40}<MediaTab", settings_src),
    "modals/settings.jsx: no `activeTab === 'media' && <MediaTab />` render "
    "— the import and tab entry alone don't put it on screen.",
)

# 5. _mediaConfig's video default must no longer be 'openai' — that branch
#    is a guaranteed-fail hardcoded 501 in exporters.py (Sora API gated).
#    fal is the only video provider that can succeed on just an API key.
OLD_BUG = "(kind === 'video' ? s.videoProvider : s.imageProvider) || 'openai'"
check(
    OLD_BUG not in client_src,
    "claude-client.jsx: _mediaConfig still falls back to 'openai' for BOTH "
    "image and video — the openai video branch is a hardcoded 501, so an "
    "unset video provider is guaranteed to fail.",
)
check(
    "(kind === 'video' ? 'fal' : 'openai')" in client_src,
    "claude-client.jsx: _mediaConfig's provider fallback must default video "
    "to 'fal' (the only video provider that can succeed on just an API key) "
    "and image to 'openai' (unchanged, still works).",
)

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")

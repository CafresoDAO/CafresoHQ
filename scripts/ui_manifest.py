"""Shared helper: turn dist-ui/manifest.json into the HQ UI <script> tags and
inject them into hq.html at the `<!--HQ_SCRIPTS-->` placeholder.

Used by BOTH serve.py (local/electron, substitutes on the fly) and
scripts/build_hq_ui.py (asset canister, bakes the substituted hq.html). Keeping
this in one place avoids the two surfaces drifting on load order or tag shape.
"""
import json
import os

PLACEHOLDER = '<!--HQ_SCRIPTS-->'


def load_manifest(dist_dir):
    with open(os.path.join(dist_dir, 'manifest.json'), encoding='utf-8') as fh:
        return json.load(fh)


# Vendor bundles only one screen needs. They are NOT script tags: the boot
# script below loads them the first time that screen opens, so a new boss's
# first load skips ~110 KB gzipped (xterm ~63 KB for Terminal, the graph
# engine ~48 KB for the Library map). Matched by bundle file name.
LAZY_VENDOR = {'xterm': ('xterm-', 'xterm-fit-', 'xterm-css-')}


def _lazy_group(path):
    name = os.path.basename(path)
    for group, prefixes in LAZY_VENDOR.items():
        if name.startswith(prefixes):
            return group
    return None


# window.cafresoLoad(name) -> Promise: injects that group's CSS + JS once, in
# order, and resolves when the last script has run. Plain ES5 so it runs
# before the app bundle.
LOADER_JS = (
    "(function(){var L=window.__CAFRESO_LAZY__||{},P={};"
    "function one(u){return new Promise(function(ok,ko){var css=/\\.css$/.test(u),"
    "e=document.createElement(css?'link':'script');if(css){e.rel='stylesheet';e.href=u;}"
    "else{e.src=u;e.async=false;}e.onload=ok;e.onerror=function(){ko(new Error('failed to load '+u));};"
    "document.head.appendChild(e);});}"
    "window.cafresoLoad=function(n){if(!P[n]){var us=L[n]||[];"
    "P[n]=us.reduce(function(p,u){return p.then(function(){return one(u);});},Promise.resolve());"
    "P[n].catch(function(){delete P[n];});}return P[n];};})();"
)


def render_tags(manifest):
    """Vendor CSS + vendor JS globals + boot data (worker URL, on-demand
    bundles, loader) + app JS, in order. React/ReactDOM must precede the app
    files (which read window.React etc.). xterm and the graph engine are
    on-demand: see LAZY_VENDOR and window.cafresoLoad."""
    parts = []
    lazy = {}
    for css in manifest.get('vendorCss', []):
        g = _lazy_group(css)
        if g:
            lazy.setdefault(g, []).append(css)
        else:
            parts.append(f'<link rel="stylesheet" href="{css}"/>')
    for js in manifest.get('vendor', []):
        g = _lazy_group(js)
        if g:
            lazy.setdefault(g, []).append(js)
        else:
            parts.append(f'<script src="{js}"></script>')
    if manifest.get('graphEngine'):
        lazy['graph'] = [manifest['graphEngine']]
    boot = {}
    if manifest.get('analyticsWorker'):
        # Hand the hashed analytics-worker URL to the graph engine (new Worker(url)).
        boot['analyticsWorker'] = manifest['analyticsWorker']
    parts.append('<script>window.__CAFRESO_BUNDLE__=%s;window.__CAFRESO_LAZY__=%s;%s</script>'
                 % (json.dumps(boot), json.dumps(lazy), LOADER_JS))
    for js in manifest.get('app', []):
        parts.append(f'<script src="{js}"></script>')
    return '\n'.join(parts)


def inject(html, manifest):
    return html.replace(PLACEHOLDER, render_tags(manifest))

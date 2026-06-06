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


def render_tags(manifest):
    """Vendor CSS + vendor JS globals + worker-URL bootstrap + (optional) graph
    engine + app JS, in order. React/ReactDOM/xterm must precede the app files
    (which read window.React etc.); the graph engine must precede the app too."""
    parts = []
    for css in manifest.get('vendorCss', []):
        parts.append(f'<link rel="stylesheet" href="{css}"/>')
    for js in manifest.get('vendor', []):
        parts.append(f'<script src="{js}"></script>')
    boot = {}
    if manifest.get('analyticsWorker'):
        boot['analyticsWorker'] = manifest['analyticsWorker']
    if boot:
        # Hand the hashed analytics-worker URL to the graph engine (new Worker(url)).
        parts.append('<script>window.__CAFRESO_BUNDLE__=%s;</script>' % json.dumps(boot))
    if manifest.get('graphEngine'):
        parts.append(f'<script src="{manifest["graphEngine"]}"></script>')
    for js in manifest.get('app', []):
        parts.append(f'<script src="{js}"></script>')
    return '\n'.join(parts)


def inject(html, manifest):
    return html.replace(PLACEHOLDER, render_tags(manifest))

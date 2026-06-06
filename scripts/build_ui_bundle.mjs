/**
 * build_ui_bundle.mjs — CafresoHQ UI build (replaces in-browser Babel).
 *
 * WHY: hq.html used to ship raw JSX + the full @babel/standalone compiler + the
 * React dev build from unpkg, transpiling ~1MB of JSX on the main thread on every
 * load. This script removes Babel entirely:
 *   1. Self-hosts the vendor UMD globals (React prod, ReactDOM prod, xterm, fit
 *      addon) from node_modules — drops the unpkg dependency.
 *   2. esbuild-TRANSFORMS each .jsx -> .js (JSX -> React.createElement) with
 *      whitespace/syntax minify but NO identifier renaming. The 11 HQ files rely
 *      on separate-classic-script scoping (cross-file comms are via window.Openclaw*
 *      globals; component defs live on the global object, consumers take `const`
 *      bindings). Transforming each file independently and loading them as the
 *      SAME ordered <script> tags preserves that runtime model exactly — bundling
 *      or concatenating would collapse scopes and cause redeclaration errors.
 *   3. (Phase 1) BUNDLES the new graph engine + analytics worker (which DO use npm
 *      imports: sigma/graphology) into their own IIFE chunks. Skipped until present.
 *
 * Output: dist-ui/bundle/<name>-<hash>.{js,css} + dist-ui/manifest.json
 * The manifest drives placeholder substitution in hq.html (done by serve.py for
 * local/electron and by scripts/build_hq_ui.py for the asset canister).
 */
import * as esbuild from 'esbuild';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'dist-ui');
const BUNDLE = path.join(OUT, 'bundle');

const TARGET = ['es2019'];

// HQ app JSX files — ORDER IS LOAD-BEARING (mirrors the old hq.html script order).
const APP_FILES = [
  'tweaks-panel', 'sprites', 'claude-client', 'mock-data', 'ui',
  'modals', 'features', 'cooccur', 'cafreso-ecobar', 'views', 'missions', 'agent_runner', 'app',
];

// Vendor UMD globals copied verbatim from node_modules (each sets a window global:
// React / ReactDOM / Terminal / FitAddon — the same files unpkg served).
const VENDOR = [
  { name: 'react',     src: 'node_modules/react/umd/react.production.min.js' },
  { name: 'react-dom', src: 'node_modules/react-dom/umd/react-dom.production.min.js' },
  { name: 'xterm',     src: 'node_modules/xterm/lib/xterm.js' },
  { name: 'xterm-fit', src: 'node_modules/xterm-addon-fit/lib/xterm-addon-fit.js' },
];
const VENDOR_CSS = [
  { name: 'xterm-css', src: 'node_modules/xterm/css/xterm.css' },
];

// Phase-1 bundles (npm-importing). Built only if the entry file exists.
const ENGINE_BUNDLES = [
  { name: 'graph-engine',     entry: 'graph-engine.js',     key: 'graphEngine' },
  { name: 'analytics-worker', entry: 'analytics.worker.js', key: 'analyticsWorker' },
];

function shortHash(buf) {
  return createHash('sha256').update(buf).digest('hex').slice(0, 10);
}

function writeHashed(name, ext, content) {
  const hash = shortHash(content);
  const file = `${name}-${hash}.${ext}`;
  fs.writeFileSync(path.join(BUNDLE, file), content);
  return `bundle/${file}`;
}

async function bundleApp() {
  // Bundle the 11 HQ files into ONE IIFE. This is what the original
  // <script type="text/babel"> setup did implicitly: @babel/standalone executes
  // each script in an ISOLATED scope, so the files' top-level const/class names do
  // NOT share a global lexical env. Loading them as plain classic scripts would
  // collapse them into one shared scope and throw "already declared". A bundle
  // gives each module its own closure — matching Babel — while cross-file comms
  // stay via window.Openclaw* globals. React/ReactDOM/xterm are read as window
  // globals provided by the vendor UMD scripts loaded before this bundle.
  const entry = APP_FILES.map((n) => `import './${n}.jsx';`).join('\n');
  const r = await esbuild.build({
    stdin: { contents: entry, resolveDir: ROOT, loader: 'js', sourcefile: 'hq-entry.js' },
    bundle: true,
    format: 'iife',
    target: TARGET,
    jsx: 'transform',
    jsxFactory: 'React.createElement',
    jsxFragment: 'React.Fragment',
    loader: { '.jsx': 'jsx' },
    minify: true,                          // safe: one module graph, consistent renames
    sourcemap: false,
    legalComments: 'none',
    write: false,
  });
  return [writeHashed('hq-app', 'js', r.outputFiles[0].contents)];
}

function copyVendor() {
  const js = [];
  for (const v of VENDOR) {
    const abs = path.join(ROOT, v.src);
    if (!fs.existsSync(abs)) throw new Error(`vendor file missing: ${v.src} (did npm install run?)`);
    js.push(writeHashed(v.name, 'js', fs.readFileSync(abs)));
  }
  const css = [];
  for (const v of VENDOR_CSS) {
    const abs = path.join(ROOT, v.src);
    if (fs.existsSync(abs)) css.push(writeHashed(v.name, 'css', fs.readFileSync(abs)));
  }
  return { js, css };
}

// Public read-only graph viewer (Phase 2). Bundled to a FIXED name so the static
// graph-viewer.html can reference it without manifest injection. Small: sigma +
// graphology core only (no FA2 layout / analytics worker — all precomputed).
async function buildViewer() {
  const entry = path.join(ROOT, 'graph-viewer.js');
  if (!fs.existsSync(entry)) return null;
  const r = await esbuild.build({
    entryPoints: [entry], bundle: true, format: 'iife', target: TARGET,
    minify: true, sourcemap: false, write: false, legalComments: 'none',
    define: { 'process.env.NODE_ENV': '"production"' },
  });
  fs.writeFileSync(path.join(OUT, 'graph-viewer.js'), r.outputFiles[0].contents);
  return 'graph-viewer.js';
}

async function buildEngines() {
  const result = {};
  for (const b of ENGINE_BUNDLES) {
    const entry = path.join(ROOT, b.entry);
    if (!fs.existsSync(entry)) { result[b.key] = null; continue; }
    const r = await esbuild.build({
      entryPoints: [entry],
      bundle: true,
      format: 'iife',
      target: TARGET,
      minify: true,
      sourcemap: false,
      define: { 'process.env.NODE_ENV': '"production"' },
      write: false,
      legalComments: 'none',
    });
    result[b.key] = writeHashed(b.name, 'js', r.outputFiles[0].contents);
  }
  return result;
}

async function build() {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(BUNDLE, { recursive: true });

  const vendor = copyVendor();
  const app = await bundleApp();
  const engines = await buildEngines();
  const viewer = await buildViewer();

  const manifest = {
    vendor: vendor.js,
    vendorCss: vendor.css,
    app,
    graphEngine: engines.graphEngine,
    analyticsWorker: engines.analyticsWorker,
    viewer,
  };
  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2));
  const total = vendor.js.length + vendor.css.length + app.length +
    (engines.graphEngine ? 1 : 0) + (engines.analyticsWorker ? 1 : 0);
  console.log(`[ui] built ${total} assets -> dist-ui/  (graphEngine=${!!engines.graphEngine})`);
  return manifest;
}

async function main() {
  await build();
  if (process.argv.includes('--watch')) {
    console.log('[ui] watching for changes…');
    const watched = new Set([
      ...APP_FILES.map((n) => path.join(ROOT, `${n}.jsx`)),
      ...ENGINE_BUNDLES.map((b) => path.join(ROOT, b.entry)),
    ]);
    let timer = null;
    const rebuild = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        build().catch((e) => console.error('[ui] build error:', e.message));
      }, 120);
    };
    for (const f of watched) {
      try { fs.watch(f, rebuild); } catch { /* file may not exist yet */ }
    }
    // Also watch the root dir to catch the engine files being created later.
    fs.watch(ROOT, (_ev, fname) => {
      if (fname && (fname.endsWith('.jsx') || fname === 'graph-engine.js' || fname === 'analytics.worker.js')) rebuild();
    });
  }
}

main().catch((e) => { console.error(e); process.exit(1); });

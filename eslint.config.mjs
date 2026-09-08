// Minimal, deliberate: ONE rule. no-undef is the mechanical guard for the
// window-globals → ES-modules conversion — a bare identifier that used to
// resolve through window is now a ReferenceError at runtime, and this is the
// only tool that catches it before a browser does. jsx-uses-vars makes
// <Sprite/> count as a use so no-undef sees JSX-position identifiers too.
// Style rules are intentionally absent; this is a tripwire, not a linter setup.
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';

const BROWSER = Object.fromEntries([
  'window', 'document', 'navigator', 'localStorage', 'sessionStorage', 'fetch',
  'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval', 'console',
  'URL', 'URLSearchParams', 'AbortController', 'TextEncoder', 'TextDecoder',
  'Blob', 'File', 'FileReader', 'FormData', 'Headers', 'Request', 'Response',
  'WebSocket', 'EventSource', 'CustomEvent', 'Event', 'KeyboardEvent',
  'MouseEvent', 'PointerEvent', 'ClipboardEvent', 'DOMException', 'DOMParser',
  'XMLSerializer', 'Node', 'NodeList', 'HTMLElement', 'HTMLButtonElement',
  'Image', 'Audio',
  'crypto', 'history', 'location', 'performance', 'screen', 'devicePixelRatio',
  'requestAnimationFrame', 'cancelAnimationFrame', 'requestIdleCallback',
  'getComputedStyle', 'matchMedia', 'alert', 'confirm', 'prompt', 'atob',
  'btoa', 'structuredClone', 'queueMicrotask', 'reportError', 'globalThis',
  'self', 'indexedDB', 'Notification', 'ResizeObserver', 'MutationObserver',
  'IntersectionObserver', 'ReadableStream', 'MessageChannel',
  'BroadcastChannel', 'Worker', 'AbortSignal', 'innerWidth', 'innerHeight',
].map((g) => [g, 'readonly']));

// Vendor UMD globals the bundle self-hosts (see scripts/build_ui_bundle.mjs).
const VENDOR = Object.fromEntries(
  ['React', 'ReactDOM', 'Terminal', 'FitAddon'].map((g) => [g, 'readonly']));

export default [
  {
    files: ['*.jsx', 'views/*.jsx', 'ui/*.jsx', 'modals/*.jsx', 'app/*.jsx'],
    plugins: { react, 'react-hooks': reactHooks },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...BROWSER, ...VENDOR },
    },
    rules: {
      'no-undef': 'error',
      'react/jsx-uses-vars': 'error',
    },
  },
];

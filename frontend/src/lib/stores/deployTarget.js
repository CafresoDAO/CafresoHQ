// ── Deploy-target store ──────────────────────────────────────────────────────
// Where the user runs their HQ backend:
//   'local'     → their own machine (Start-CafresoHQ on Mac/Windows-WSL/Linux)
//   'oci-fleet' → our managed OCI cloud (provisioned container behind the gateway)
//   ''          → not chosen yet (ProvisionPanel shows the chooser)
// Persisted in localStorage. The connect flow in ProvisionPanel branches on this:
// local skips provisioning and points at http://localhost:8787; oci-fleet keeps
// the existing lookup→provision path. Reuses endpoint.js — does not replace it.
import { writable } from 'svelte/store';

export const DEPLOY_TARGETS = { LOCAL: 'local', OCI: 'oci-fleet' };

const STORAGE_KEY = 'cafresohq.deploy_target';
const browser = () => typeof window !== 'undefined';

function _initial() {
  if (!browser()) return '';
  try { return localStorage.getItem(STORAGE_KEY) || ''; } catch (_) { return ''; }
}

export const deployTarget = writable(_initial());

deployTarget.subscribe((v) => {
  if (!browser()) return;
  try {
    if (v) localStorage.setItem(STORAGE_KEY, v);
    else   localStorage.removeItem(STORAGE_KEY);
  } catch (_) { /* private mode */ }
});

/** Set the deploy target ('local' | 'oci-fleet' | '' to reset). */
export function setDeployTarget(t) {
  deployTarget.set(t === DEPLOY_TARGETS.LOCAL || t === DEPLOY_TARGETS.OCI ? t : '');
}

// ── CafresoAI deployment config ─────────────────────────────────────────────
// Single source of truth for the URLs that vary by environment.
// `import.meta.env.PROD` is true in `vite build`; false in `vite dev`.

export const PROD_HOST = 'ai.cafreso.com';

/**
 * CafresoPages self-hosted search API (home server → Cloudflare Tunnel).
 * Queries hit the semantic vault first; Brave Search API is the fallback.
 */
export const SEARCH_API_BASE = 'https://search.cafreso.com';

/**
 * Where this app is served — falls back to the current location at runtime.
 * Useful for share URLs, OG tags, error reports, etc.
 */
export const APP_ORIGIN = (typeof window !== 'undefined' && window.location?.origin)
  ? window.location.origin
  : `https://${PROD_HOST}`;

/**
 * Sister dapps in the Cafreso ecosystem. Used by the footer, settings, and
 * (later) cross-dapp link-outs. All authenticate against the same II anchor,
 * so the user's principal is identical across them.
 */
export const ECOSYSTEM = {
  pages:    'https://cafreso.com',          // Cafreso Pages (Dev/Forum/Shop)
  cafreso_ai: 'https://ai.cafreso.com',     // CafresoAI control plane (this app)
  hq_gateway: 'https://hq.cafreso.com',     // Per-user OCI containers (Phase 5)
  banking:  'https://cqyto-tiaaa-aaaau-agppa-cai.icp0.io', // Banking.Brave (II anchor)
  minegold: 'https://cqyto-tiaaa-aaaau-agppa-cai.icp0.io/mine'  // Mine (Banking.Brave canister; minegold.defi domain currently down)
};

/**
 * HQ app UI, served from the `cafresohq_ui` ICP asset canister (frontend/backend
 * split — Phase 3). The post-login iframe loads this canister's /hq.html with
 * `?api=<container endpoint>`, so UI updates ship via a ~1-min `dfx deploy`
 * instead of a Docker image rebuild + container recreate. The container's
 * serve.py stays API-only and is reached cross-origin (CORS echoes Origin +
 * Allow-Credentials; the hq_session cookie is SameSite=None so the cross-site
 * iframe sends it). Empty string disables the split (falls back to the
 * container's own baked-in UI).
 *
 * Served from hq-ui.cafreso.com (IC custom domain on the cafresohq_ui canister)
 * rather than the raw *.icp0.io origin, so the iframe is SAME-SITE with the API
 * (hq.cafreso.com) and shell (ai.cafreso.com) — all cafreso.com. That keeps the
 * hq_session cookie first-party, immune to third-party-cookie blocking. The raw
 * canister URL (https://vhoil-eyaaa-aaaal-qxc7q-cai.icp0.io) still works but is
 * cross-site and gets its cookie dropped by most browsers in the iframe.
 */
export const HQ_UI_CANISTER_ORIGIN = 'https://hq-ui.cafreso.com';

/**
 * Per-user OCI container URL pattern — matches fleet-api.py + Caddy routing.
 * Slug = sha256(principal)[:16] (hex). Matches _gateway_url_for_principal()
 * in fleet-api.py and the Caddyfile handle_path /u/{slug}/* pattern.
 */
export async function gatewayUrlForPrincipal(principal) {
  if (!principal) return null;
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(principal)
  );
  const hex = [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  const slug = hex.slice(0, 16);
  return `${ECOSYSTEM.hq_gateway}/u/${slug}`;
}

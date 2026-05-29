// Cross-canister link resolver.
//
// Cafreso (this Svelte dapp) is deployed to `dqcmv-zqaaa-aaaab-agp2a-cai`.
// Banking.Brave (the Minegold React protocol dapp) lives on a separate
// canister. The two are stitched together at the UI layer: Header nav and
// "Mine / Exchange / Bridge / Transactions" call-sites resolve through this
// helper so a future domain change is a one-line edit.
//
// Env vars (set in `.env` or `.env.local` — `PUBLIC_` prefix is Vite's
// convention for client-visible values):
//   PUBLIC_BANKING_BRAVE_ORIGIN — https host for Banking.Brave, e.g.
//                                  https://cqyto-tiaaa-aaaau-agppa-cai.icp0.io
//
// If the env var is unset we fall back to the known mainnet canister URL.
// When `custom-domain` is eventually configured the env var override wins.

const DEFAULT_BANKING_BRAVE_ORIGIN =
  'https://cqyto-tiaaa-aaaau-agppa-cai.icp0.io';

export const bankingBraveOrigin =
  (typeof import.meta !== 'undefined' && import.meta.env?.PUBLIC_BANKING_BRAVE_ORIGIN) ||
  DEFAULT_BANKING_BRAVE_ORIGIN;

export function bb(path = '/') {
  if (!path.startsWith('/')) path = '/' + path;
  return `${bankingBraveOrigin}${path}`;
}

// Which UI paths route to Banking.Brave vs stay in Cafreso. Kept in one place
// so the Header and Footer can't drift out of sync.
export const bbRoutes = {
  mine: '/mine',
  exchange: '/exchange',
  bridge: '/bridge',
  transactions: '/transactions',
  admin: '/admin'
};

export const bbLinks = Object.fromEntries(
  Object.entries(bbRoutes).map(([k, v]) => [k, bb(v)])
);

// AI Cafreso — CafresoDAO Library agent-workflow frontend.
// Override via PUBLIC_AI_CAFRESO_ORIGIN for local dev or testnet routing.
const DEFAULT_AI_CAFRESO_ORIGIN = 'https://ai.cafreso.com';
export const aiCafresoOrigin =
  (typeof import.meta !== 'undefined' && import.meta.env?.PUBLIC_AI_CAFRESO_ORIGIN) ||
  DEFAULT_AI_CAFRESO_ORIGIN;

// banking.cafreso.com — future custom domain for the Banking.Brave canister.
// Falls back to bankingBraveOrigin until the custom domain DNS is live.
const DEFAULT_BANKING_CAFRESO_ORIGIN = 'https://banking.cafreso.com';
export const bankingCafresoOrigin =
  (typeof import.meta !== 'undefined' && import.meta.env?.PUBLIC_BANKING_CAFRESO_ORIGIN) ||
  DEFAULT_BANKING_CAFRESO_ORIGIN;

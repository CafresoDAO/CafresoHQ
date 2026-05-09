---
tags: [research]
---

# Frontend asset security headers

Angle for this iteration: verify whether `minegold.defi`’s frontend asset canister is explicitly hardened with `.ic-assets.json5` security headers and certified asset redirects.

## Why this matters

Internet Computer frontend canisters can serve static assets through the asset canister, which supports:

- per-file response headers via `.ic-assets.json5`
- automatic asset certification
- redirects from non-certified endpoints to certified endpoints
- CSP and other browser security headers

The IC docs emphasize that frontend projects created with `dfx new` include a default `.ic-assets.json5` Content Security Policy, but apps often weaken or omit this during framework customization.

This is separate from backend issues already noted in [[caller-authorization-checks]], [[upgrade-state-persistence]], and [[icp-async-reentrancy]]: even if canister logic is sound, a weak frontend policy can expose users to asset tampering, clickjacking, XSS, or unsafe embedding.

## Codebase checks to perform

Look for:

- `.ic-assets.json5`
- `dfx.json` frontend canister asset configuration
- custom HTTP serving code if assets are not using the standard asset canister
- headers on `index.html`, JS bundles, WASM, images, and fallback routes

Minimum expected hardening:

- `Content-Security-Policy`
- `X-Frame-Options` or CSP `frame-ancestors`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy`
- `Permissions-Policy`
- certified-asset redirect behavior where appropriate

## Potential vulnerability pattern

If `index.html` or route fallbacks are served without a strict CSP, any frontend XSS becomes much more damaging, especially for a DeFi app where the UI may initiate wallet approvals or canister calls.

Risky CSP signs:

- `script-src 'unsafe-inline'`
- broad `connect-src *`
- broad `frame-src *`
- no `frame-ancestors`
- allowing arbitrary third-party scripts
- no distinction between local dev and production headers

## Suggested patch direction

If missing, add a project-level `.ic-assets.json5` and start from the IC default security policy, then tighten it around the app’s real dependencies.

Example shape:

```json5
[
  {
    "match": "**/*",
    "headers": {
      "Content-Security-Policy": "default-src 'self'; script-src 'self'; connect-src 'self' https://icp0.io https://*.icp0.io https://icp-api.io https://*.icp-api.io; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self';",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()"
    }
  }
]
```

Notes:

- Replace `style-src 'unsafe-inline'` with hashes/nonces if feasible.
- Add wallet/provider domains only if actually required.
- Avoid production `connect-src *`.
- Prefer CSP `frame-ancestors 'none'` over only `X-Frame-Options`, since CSP is more flexible and modern.
- Test with the deployed certified URL, not only local dev.

## Follow-up

In a later iteration, inspect the actual project files to confirm whether the frontend canister has `.ic-assets.json5`, whether headers are deployed, and whether any third-party wallet/auth integrations require CSP exceptions.
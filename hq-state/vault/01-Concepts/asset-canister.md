---
title: Asset Canister
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/asset-canister
  - icp/deployment/asset-canister
source:
  - https://internetcomputer.org/docs/building-apps/frontends/using-an-asset-canister
  - https://github.com/dfinity/sdk
related:
  - "[[canisters]]"
  - "[[dfx]]"
  - "[[principals]]"
  - "[[mainnet-deploy]]"
  - "[[local-replica]]"
  - "[[internet-identity]]"
difficulty: beginner
open_questions:
  - Current prebuilt asset-canister Wasm name and versioning story — whether the `type: assets` entry in dfx.json still pulls a single blessed Wasm or now selects from the `ic-frontend-canister` / `assets-api-v*` split.
  - Exact current configuration surface of `.ic-assets.json5` (headers, redirects, SPA fallback rules) — drifts across dfx releases.
  - Per-canister static-asset size ceiling in practice (docs reference ~1 GiB; verify against current storage defaults).
---

# Asset Canister

> An asset canister is a [[canisters|canister]] dedicated to serving static web assets (HTML, JS, CSS, images) over HTTPS: `dfx` ships a prebuilt Wasm for it, you mark a canister as `"type": "assets"` in `dfx.json` and point it at a source directory, and `dfx deploy` uploads the built frontend into it — no HTTP server, no S3, no CDN.

## Why it exists

A full ICP dapp needs a UI, not just a backend canister. The naive options are (a) host the frontend off-chain on a traditional web host — giving up the on-chain provenance story — or (b) write your own HTTP-serving canister from scratch. The asset canister is option (c): DFINITY maintains a reference Wasm that implements the IC's HTTP interface correctly (including **certified** responses), and `dfx` wires the upload pipeline for you. Result: the frontend lives on-chain alongside the backend, reachable as a normal HTTPS URL, and its content is cryptographically attested.

## How it works

- **Prebuilt Wasm** — you do not normally write the asset canister's code. `dfx` bundles a reference implementation (historically published from the `dfinity/sdk` repo, with on-chain delivery via the `ic-frontend-canister` / assets-API crates). Declaring `"type": "assets"` in `dfx.json` selects that Wasm; `dfx build` produces the frontend bundle and `dfx deploy` installs the Wasm + uploads assets into it via a chunked upload protocol.
- **`dfx.json` entry** — a typical frontend canister block looks like:
  ```json
  "my_frontend": {
    "type": "assets",
    "source": ["dist/"],
    "dependencies": ["my_backend"]
  }
  ```
  `source` is the directory (or list) whose files will be uploaded as assets. `dependencies` makes `dfx` deploy the backend first and (historically) surface its canister ID to the frontend bundle via a generated `canister_ids.js` or environment variables.
- **HTTP interface** — the canister exposes the IC's `http_request` / `http_request_update` methods. The public HTTP gateway (`icp0.io` on mainnet, the local gateway under [[local-replica]]) translates incoming HTTP requests into canister calls and streams the responses back. The canister URL form is `https://<canister-id>.icp0.io`.
- **Certified assets** — for each uploaded asset, the canister keeps a witness in a certified data structure (historically an `ic-certified-map`, now the `ic-http-certification` library covers the full response certification story including headers). At read time, the canister returns the response *together with a signature chain rooted in the subnet's threshold key*. The boundary node / service worker verifies the chain, so the client is assured that the asset is exactly what the subnet agreed it was — no on-path tampering by a CDN or ISP.
- **Headers and rewrites** — a `.ic-assets.json5` (or `.ic-assets.json`) file inside the `source` directory configures per-path headers, cache-control, redirects, and (importantly for SPAs) a **fallback** file that is served when a requested path does not match any uploaded asset.
- **SPA routing** — a single-page app typically wants `/any/client/route` to serve `index.html` so the client-side router can take over. The idiomatic way to get that with the asset canister is to configure the fallback rule in `.ic-assets.json5` to return `index.html` for unmatched paths. (Historical docs reference a `$$` / wildcard glob; exact syntax varies between dfx releases — consult the current `.ic-assets.json5` reference.)
- **Upload model** — assets are chunked and uploaded through a `create_batch` / `create_chunk` / `commit_batch` flow on the canister; `dfx deploy` drives it. This lets the canister atomically cut over to the new asset set rather than racing partial uploads against live traffic.
- **`ic-frontend-canister` / `assets-api-v*` split** — qualitatively: the asset canister has evolved from one monolithic implementation into a layered pair. The **API layer** (versioned `assets-api-v*`) defines the wire protocol between the client uploading assets and the canister. The **frontend-canister layer** (`ic-frontend-canister`) is a reference implementation on top of that API. Treating them as separate means downstream projects (custom asset canisters, asset-backed SDKs) can implement the API without reimplementing the reference canister.

## Example

```json
// dfx.json
{
  "canisters": {
    "notes_backend": { "type": "motoko", "main": "src/notes_backend/main.mo" },
    "notes_frontend": {
      "type": "assets",
      "source": ["src/notes_frontend/dist/"],
      "dependencies": ["notes_backend"]
    }
  }
}
```

```json5
// src/notes_frontend/dist/.ic-assets.json5
// One file per path match; last matching rule wins. The fallback rule at the bottom
// rewrites any path the SPA's client router owns back to index.html.
[
  {
    "match": "**/*",
    "headers": {
      "Cache-Control": "public, max-age=3600"
    }
  },
  {
    "match": "index.html",
    "headers": {
      "Cache-Control": "no-cache"
    }
  }
  // SPA fallback configured via the current `.ic-assets.json5` fallback syntax —
  // consult the dfx release docs for the exact key name and glob form.
]
```

```bash
# Build the SPA, then deploy — dfx uploads dist/ into the asset canister.
npm --prefix src/notes_frontend run build
dfx deploy --network ic notes_frontend
```

## Gotchas

- **No server-side logic.** The asset canister is a static server. If you need dynamic HTML, a render-on-request endpoint, or server-side auth checks, write a separate canister that implements `http_request` yourself; do not try to twist the asset canister into that role.
- **Mainnet URLs differ from local.** Local the canister is at `http://<canister-id>.localhost:<port>` (via the dfx local gateway). Mainnet it is at `https://<canister-id>.icp0.io`. Hardcoding localhost or a specific canister ID in frontend code will break on the other side. See [[local-replica]] and [[mainnet-deploy]].
- **SPA fallback is a config, not a default.** Out of the box the canister returns 404 for unmatched paths; deep-linking to `/dashboard` will fail until you configure the fallback. Test deep links before declaring launch.
- **Size matters.** A single asset canister is practical up to roughly the single-canister storage ceiling (docs reference ~1 GiB of static assets as a common practical budget; split large sites across multiple asset canisters). Ship media from a dedicated asset canister or off-chain storage if it will outgrow that.
- **Auth is on the backend.** If the UI uses [[internet-identity]], auth flows happen in the frontend's JS and call into the backend canister. The asset canister itself has no concept of the signed-in user; treating it as an authenticated server is a category error.
- **Certification is per-response.** Custom headers you add via `.ic-assets.json5` must be covered by the certification story; anything the canister does not certify can be stripped or modified by a malicious boundary node and the client cannot tell. Prefer the prebuilt headers rules to hand-rolled ones.

## See also

- [[canisters]]
- [[dfx]]
- [[mainnet-deploy]]
- [[local-replica]]
- [[principals]]
- [[internet-identity]]

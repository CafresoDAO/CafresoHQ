# Publish-to-Canister

The **Publish** ICP-Service lets an agent (or you, from the Workspace) publish a built
multi-file site to a **public, HQ-owned asset canister** and drop a clickable `<name>.url`
deliverable into the project.

## Architecture: `cafresohq_sites` — one shared, public, per-principal canister

Publishing targets **`cafresohq_sites`** (`src/cafresohq_sites/main.mo`) — a single
HQ-owned, DAO-funded canister that hosts **every** user's sites. It is **part of HQ
infrastructure** (like the frontend canister): users never provision or fund their own.

- **Isolation:** every write is keyed by `msg.caller` (your Internet Identity), so you can
  only write your own namespace — the same model as `cafresohq_state`. This is why a shared
  multi-tenant host is safe here but *not* on the stock DFINITY assets canister (whose commit
  permission is canister-wide, not path-scoped).
- **Public serving:** `http_request` serves any namespace publicly at
  `https://<cafresohq_sites>.icp0.io/<principalText>/<project>/`. For the MVP it upgrades GETs
  to an update call (`http_request_update`) so no IC asset certification is needed yet
  (certified query serving + streaming for >2 MiB files are the perf follow-ups).
- **Limits:** ≤ 2 MiB per file, 200 MiB of published sites per user, ≤ 300 files per publish.

## The flow

1. Agent builds a site in the container `/fs/<project>/` and calls
   `[PUBLISH_SITE: <dir or index.html>]` (or you click **🚀 Publish** on the Workspace preview).
   The tool appears once the **Publish** service is installed in Settings → ICP Services.
2. The embedded HQ app collects the files (`GET /fs/collect?path=<dir>` → base64 + content-type,
   allowed-dirs guarded) and hands them to the shell over the `postMessage` bridge
   (`chain:publish`).
3. The shell (which holds II) uploads each file to `cafresohq_sites.putSiteFile(...)` under
   **your** principal and returns the public URL.
4. A clickable `<project>.url` is written into the project so the deliverable shows in the
   tree/preview.

If the sites canister isn't configured yet (or the app is opened standalone, outside the
shell), Publish falls back to the owner-scoped `/fs/site` preview link and says so.

## Founder one-time setup (user-owned — costs cycles)

Deploy + fund the canister once; after that every user publishes for free:

```
dfx deploy cafresohq_sites --network ic --identity default
# note the printed canister id; top it up with cycles
```

`dfx` injects `VITE_CANISTER_ID_CAFRESOHQ_SITES` into the frontend build env, which
`sitesActor.js` reads (with a null fallback until then). Rebuild + deploy the frontend and
Publish goes live for everyone.

> Converting ICP→cycles and creating/funding canisters are financial steps Claude does not
> perform — you run them.

## Later upgrades
- Certified query serving (drop the update-call upgrade → faster loads).
- Streaming (`http_request_streaming_callback`) for files > 2 MiB.
- Optional dedicated canister-per-site + custom domains.

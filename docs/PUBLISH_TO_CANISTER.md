# Publish-to-Canister

The **Publish** ICP-Service lets an agent (or you, from the Workspace) publish a built
multi-file site to a **public HQ host** and drop a clickable `<name>.url` deliverable into
the project.

## Where sites live: the `cafresohq_state` canister (no separate canister)

Published sites are hosted **inside the existing `cafresohq_state` canister** — reused on
purpose so there is **no new canister to create or fund**. It already has the exact model we
need:

- **Isolation:** every write (`putSiteFile`) is keyed by `msg.caller` (your Internet
  Identity), so you can only write your own namespace. (This is why a shared multi-tenant
  host is safe here but *not* on the stock DFINITY assets canister, whose commit permission
  is canister-wide.)
- **Public serving:** `http_request` serves any namespace publicly at
  `https://<cafresohq_state>.icp0.io/<principalText>/<project>/`. The handler reads **only**
  the site files — never the vault/doc maps (and vault data is client-encrypted anyway). For
  the MVP it upgrades GETs to an update call (`http_request_update`) so no IC asset
  certification is needed yet (certified query serving + streaming for >2 MiB are follow-ups).
- **Limits:** ≤ 2 MiB per file, 200 MiB of sites per user.

## The flow

1. Agent builds a site in the container `/fs/<project>/` and calls
   `[PUBLISH_SITE: <dir or index.html>]` (or you click **🚀 Publish** on the Workspace preview).
   The tool appears once the **Publish** service is installed in Settings → ICP Services.
2. The embedded HQ app collects the files (`GET /fs/collect?path=<dir>` → base64 +
   content-type, allowed-dirs guarded) and hands them to the shell over the `postMessage`
   bridge (`chain:publish`).
3. The shell (which holds II) uploads each file to `cafresohq_state.putSiteFile(...)` under
   **your** principal and returns the public URL.
4. A clickable `<project>.url` is written into the project so the deliverable shows in the tree.

If the app is opened standalone (outside the shell), Publish falls back to the owner-scoped
`/fs/site` preview link and says so.

## Founder step to go live (user-owned)

There is **no separate deploy for Publish** — it ships with the `cafresohq_state` upgrade you
already need for the wallet + services:

```
dfx deploy cafresohq_state --network ic --identity default
```

That's an **upgrade of the already-deployed, already-funded** canister (`ydacz-…`) — new
stable vars initialise empty, so it's lossless. The deploying identity must be a **controller**
of `cafresohq_state`. Once upgraded, both the wallet/services *and* Publish are live; the
frontend already pins the state canister id, so no env wiring is needed.

## Later upgrades
- Certified query serving (drop the update-call upgrade → faster loads).
- Streaming (`http_request_streaming_callback`) for files > 2 MiB.
- If site traffic ever warrants isolation from private state, split sites into their own
  canister — the client (`sitesActor.js`) is the only thing that would repoint.

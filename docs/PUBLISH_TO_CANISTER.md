# Publish-to-Canister

The **Publish** ICP-Service lets an agent (or you, from the Workspace) publish a built
multi-file site and drop a **clickable `<name>.url` deliverable** into the project.

## What ships today

- **Agent tool** `PUBLISH_SITE: <dir or index.html>` and a **🚀 Publish** button on the
  Workspace preview pane (both appear once the **Publish** service is installed in
  Settings → ICP Services).
- Publishing writes `<project>.url` into the project directory and returns a shareable URL.
- The URL is served by the container's `/fs/site/<b64dir>/<file>` endpoint (the same
  multi-file server the live Preview uses), so **relative assets resolve** and the site
  renders complete.

### Scope / honesty note

That `/fs/site` URL is served **through the gateway's `forward_auth`** — it opens for the
**authenticated owner** (you), not the anonymous public. So today's deliverable is a
one-click link to your own live site, not yet a public address you can hand to a stranger.

## The gated upgrade: true public `*.icp0.io` hosting

To make published sites **publicly reachable at a verifiable `*.icp0.io` URL**, the site
must live in a **public asset canister** on the Internet Computer. That needs a one-time,
**user-owned** setup (it costs cycles — converting ICP→cycles is a financial step Claude
does not perform):

1. **Provision a public "sites" asset canister** (or reuse `cafresohq_ui`-style assets):
   ```
   dfx deploy cafresohq_sites --network ic --identity default
   ```
   Make your Internet Identity principal a **controller / authorized uploader** of it.
2. **Wire the id** into the frontend build env as `VITE_SITES_CANISTER_ID` (mirrors how
   `stateActor.js` pins `cafresohq_state`).
3. The Publish client (`claude-client.jsx → publishSite`) is structured so the upload path
   swaps in cleanly: instead of writing a `/fs/site` link, it uploads the collected site
   files to the sites canister (asset `store` / `commit_batch`) and returns
   `https://<sites-canister>.icp0.io/<principal-slug>/<project>/` — which anyone can open.
4. Optional later: a **dedicated canister per published site** (stronger isolation +
   custom domains) — also a cycles/controller step you run.

Until step 1–2 are done, Publish uses the owner-scoped `/fs/site` link above. Everything
else (catalog install, the button, the agent tool, the `.url` deliverable) already works.

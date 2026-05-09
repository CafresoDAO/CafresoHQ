---
title: Notes Dapp
type: project
status: planning
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/project
  - icp/project/notes-dapp
  - lang/motoko
  - lang/typescript
stack:
  - motoko
  - react
  - internet-identity
  - ic-stable-structures-motoko
repo: ""
---
–
# Notes Dapp

## Summary

A minimal, per-user "notes" dapp running entirely on the Internet Computer. Signed-in users can create, edit, list, and delete plain-text notes scoped to their [[principals|principal]]. No sharing, no collaboration, no search — the point is to exercise the full on-chain stack (auth, persistence, frontend, deploy) with the smallest possible feature surface and then use it as a baseline for more ambitious projects.

This note is a **spec**, not an implementation. Do not build from it yet; it exists to anchor the vault's Deployment / Patterns branches in a concrete target.

## Architecture

- **Backend canister (Motoko).** A `persistent actor` that owns a `Map<Principal, [Note]>` (or an append-only `StableBTreeMap` keyed by `(Principal, NoteId)` — to be decided in milestone 2). Public methods: `create(text) : async NoteId`, `update(id, text) : async Result`, `delete(id) : async Result`, `list() : async [Note]`. Every method derives the caller from `caller` and refuses requests whose caller is anonymous.
- **Frontend canister (React, asset canister).** A small React SPA bundled into `dist/` and served by a `"type": "assets"` canister. See [[asset-canister]]. `.ic-assets.json5` configures the SPA fallback so deep-links resolve to `index.html`.
- **Auth.** [[internet-identity]] via `@dfinity/auth-client`. The frontend obtains a session delegation; the backend simply trusts `caller`. No custom auth code on the canister.
- **Persistence.** Notes live in [[stable-memory]]. Motoko's enhanced orthogonal persistence is sufficient for correctness, but notes should be modelled as `stable` from the start so upgrade-compatibility checks stay cheap even at scale.
- **Deployment.** Local per [[local-replica]], mainnet per [[ship-to-mainnet]]. One Motoko backend canister + one asset frontend canister; both installed under a dedicated mainnet identity, both top-up-planned before launch.

### Data model (draft)

```motoko
type NoteId = Nat;

type Note = {
  id : NoteId;
  text : Text;
  createdAt : Int; // ns since epoch
  updatedAt : Int;
};

// Per-principal notes. Dedicated stable structure so upgrades stay cheap as
// users accumulate data.
```

### Call graph

```
Browser (React + @dfinity/auth-client)
  --login-->  Internet Identity canister (returns delegation)
  --call-->   notes_backend.create / update / delete / list
                 ^
                 |  caller = per-origin principal derived by II
```

## Milestones

- [ ] **M1 — Scaffold.** `dfx new notes --type motoko` (backend only), add a React SPA source dir, add `"type": "assets"` frontend canister in `dfx.json`. Green `dfx deploy` on [[local-replica]]. No auth yet; `caller` unused.
- [ ] **M2 — Data model + stable storage.** Define `Note` / `NoteId`; pick between `stable var notes : Map<Principal, [Note]>` under Motoko EOP vs. a `Region`-backed structure. Decision logged in this file's "Notes" section when made. See [[stable-memory]].
- [ ] **M3 — CRUD backend.** Implement `create` / `update` / `delete` / `list`. Enforce `caller != anonymous`. Enforce per-note ownership by principal. Unit-test locally with two different `dfx identity`s.
- [ ] **M4 — Frontend CRUD.** React components for list / new / edit / delete, wired to the backend via a generated Candid agent binding. No auth yet — calls go anonymous and fail; the UI shows the error. See [[candid]].
- [ ] **M5 — Internet Identity auth.** Drop in `@dfinity/auth-client`, login/logout UI, session persistence in browser storage. Backend now accepts calls. See [[internet-identity]].
- [ ] **M6 — Upgrade hooks.** Simulate an upgrade locally (`dfx deploy --mode upgrade`); verify notes survive. Document whether classical `pre_upgrade`/`post_upgrade` are needed (they should not be, under EOP + stable vars) in the "Notes" section. See [[upgrade-hooks]].
- [ ] **M7 — Asset canister polish.** `.ic-assets.json5` with sensible cache headers and an SPA fallback. Deep-links (`/notes/42`) resolve correctly. See [[asset-canister]].
- [ ] **M8 — Mainnet deploy.** Execute [[ship-to-mainnet]] end-to-end: mainnet identity, cycles funding via the cycles ledger, `dfx deploy --network ic`, verify controllers, record canister IDs. See [[mainnet-deploy]] and [[cycles-wallet]].
- [ ] **M9 — Top-up runbook.** Pick the top-up strategy (manual / cycles-ops / external alerting), write it down in a `RUNBOOK.md`, rehearse it once. See [[cycles]].
- [ ] **M10 — Ship.** Post the mainnet URL somewhere durable. Status → `shipped`.

## Open design questions

- **Which stable structure?** Motoko EOP with `stable var` of a built-in `Map` is simplest. A `Region`-backed manual layout is more upgrade-cost-robust at very large sizes but is overkill for a personal notes app. Default to the simpler option; revisit only if M6 surfaces an actual upgrade cost problem.
- **One canister per user, or one shared?** Default: one shared backend canister keyed by principal. Per-user canisters would scale storage further but add a canister-factory pattern, per-canister cycles accounting, and cross-canister calls — all scope creep for a baseline project.
- **Rate limiting.** A hostile caller could fill the canister with long notes and drain [[cycles]]. For the baseline, cap note length and count per principal in the canister; defer real abuse handling.
- **Frontend framework.** React is the default because `dfx new` + the ICP ecosystem samples center on it. Any SPA framework works; this is not a React-specific design.

## Non-goals (for v1)

- Sharing notes between users.
- Collaboration, comments, history.
- Full-text search.
- Encryption at rest (all data is visible to the canister's controllers — document this, do not pretend otherwise).
- Mobile app wrappers.

## Notes

This section is intentionally empty at `planning` status. As the project moves through milestones, decisions (stable-structure choice, upgrade-hook conclusions, cycles burn observed on mainnet) get appended here with dates.

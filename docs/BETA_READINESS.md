# Beta readiness — the first thirty minutes

What an outside tester hits that nobody who already has this running would ever
hit. Walked cold: fresh `git clone` into a scratch directory, followed the
README literally, ran `serve.py` against an empty state dir, and read the
first-run paths in the code.

**Headline: the app is in better shape than the docs are.** Every in-product
failure surface I probed — no brain, unreachable brain, wrong key in Settings,
a stale bundle, a delete — already says what is wrong and what to do about it,
often with a comment recording the live run that produced the sentence. The
things that would lose a beta tester are almost entirely in *getting the thing
to start*, and two of the three are single-line documentation errors. Section
(c) is longer than section (a) on purpose; that is the honest result.

Verified against `aae4317` on branch `hunt295-beta`.

---

## (a) Genuinely broken

### 1. A fresh clone cannot start. The README's own commands produce a blank 500.

**What breaks.** `dist-ui/` is gitignored (`.gitignore:46`), so a clone has no
UI bundle. `README.md:56-58` says the way to run the HQ app is `python serve.py`
and nothing else — no `npm install`, no `npm run build`. The launcher
`Start-CafresoHQ.sh:66` doesn't build either. Reproduced end to end:

```
$ git clone … && python3 serve.py
$ curl http://localhost:8921/hq.html   →  500
Message: HQ UI not built: [Errno 2] No such file or directory: '…/dist-ui/manifest.json' (run `npm run build`).
```

Then `npm run build` on its own — the remedy the error names — also fails,
because `node_modules/` is gitignored too:

```
$ npm run build
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'esbuild' … Node.js v22.17.1
```

**What the tester sees.** The stdlib error page: black-on-white "Error response
/ Error code: 500", then a raw Node stack trace when they follow its advice.
Two dead ends before the product has rendered a pixel.

**Smallest fix.** Two lines in `README.md:56-58`'s code block: `npm install`
then `npm run build` before `python3 serve.py`. (Applied in this commit — see
"Documentation fixes applied" below.) `serve.py:2101`'s message is already
correct and helpful; it just names the second step of two.

### 2. `python serve.py` is not a command on macOS (or most current Linux).

**What breaks.** `README.md:58`. macOS ships no `python` shim; Homebrew installs
`python3` only. Verified on this machine: `which python` → not found.

**What the tester sees.** `zsh: command not found: python`. They now have to
guess whether the project needs Python 2.

**Smallest fix.** `python` → `python3` at `README.md:58`. (Applied.)
`Start-CafresoHQ.sh:66` already gets this right.

### 3. With `mkcert` installed, the server is HTTPS and the README's URL is wrong — and startup can appear to hang.

**What breaks.** A genuine local run auto-provisions TLS
(`serve.py:5483-5486` → `_ensure_local_tls`, `serve.py:5316`). If `mkcert` is on
PATH, `serve.py:5364` shells out to `mkcert -install`, the server binds HTTPS,
and `README.md:58`'s `http://localhost:8787` is the wrong scheme.
`Start-CafresoHQ.sh:57-59` actively tells the tester to go install mkcert, so
this is a state the docs steer people into.

Two compounding details:

- `mkcert -install` prompts for the admin password on first use, with a 60s
  timeout (`serve.py:5364`). This happens *before* any banner is printed, so a
  tester who misses or ignores the prompt watches a silent terminal for up to a
  minute.
- The banner itself (`serve.py:5519`) is a bare `print()`. stdout is block-
  buffered whenever it isn't a tty, so under `nohup`, a redirect, or Electron
  capturing the pipe, the line naming the correct scheme and URL never
  appears. Confirmed: my cold-start log contains the 500 (stderr) and no
  `CafresoHQ -> …` line at all. The stale-bundle warning three lines below
  already carries `flush=True` for exactly this reason; the URL line does not.

**What the tester sees.** Either a hung-looking terminal, or — following the
README — `ERR_EMPTY_RESPONSE` on `http://localhost:8787` while a working HTTPS
server sits on the same port.

**Smallest fix.** `README.md:58`: say the server prints its own URL and scheme,
and that with mkcert installed it will be `https://`. Separately (code, not
this ticket): add `flush=True` to `serve.py:5519`.

### 4. The onboarding key step shows a green ✓ for a key the server refused.

**What breaks.** `hermesSetProvider` (`claude-client.jsx:880`) never reports
failure: a non-2xx returns `{ok: true, serverStored: false, detail: 'server
400: …'}` (`claude-client.jsx:914`) and a network error returns `{ok: true,
serverStored: false}` (`claude-client.jsx:916`). That contract is fine — the
Settings → Connections pane reads `serverStored` and renders
`✕ server 400: invalid OpenRouter key` (`modals/providers.jsx:133-134`). The
onboarding step does not: `ui/onboarding.jsx:338` maps `serverStored: false` to
the state `'local'`, which renders at `ui/onboarding.jsx:408` as
`✓ Key saved. (Stored in this browser — your container will pick it up.)`
The `'err'` branch at `ui/onboarding.jsx:410` is unreachable, because the only
thing that would trigger it is a thrown exception and `hermesSetProvider`
never throws.

Confirmed the server side rejects: `POST /hermes/provider {"key":"sk-or-typo"}`
→ `400 {"error": "invalid OpenRouter key"}` (`serve.py:4952`).

**What the tester sees.** A truncated paste, a key with a stray space, or a
container that isn't reachable all produce a green tick and the words "you're
ready". They discover otherwise several minutes later, at their first message,
in a completely different part of the UI.

**Smallest fix.** `ui/onboarding.jsx:338` — treat `serverStored: false` as the
error state and surface `r.detail`, matching what `modals/providers.jsx:133-134`
already does.

### 5. Saving a key on a machine with no Hermes gateway reports success, and only the first message reveals it didn't work.

**What breaks.** `POST /hermes/provider` writes `~/.hermes/.env` and
`config.yaml` and then calls `gateway_restart` (`drivers/hermes.py:88`), whose
whole body is a best-effort `subprocess.Popen(['hermes', …])` inside a
`try/except`. On a machine with no `hermes` binary this raises, is swallowed,
and `restarted` comes back `False` — but `serve.py:4964` still answers `200
{ok: true, …, note: 'gateway reloading; allow ~10s'}`, and the client only
looks at HTTP status (`claude-client.jsx:897`).

The office then routes chat to `127.0.0.1:8642` and gets nothing:

```
POST /agent/stream  →  {"error": "cannot reach http://127.0.0.1:8642/v1: <urlopen error [Errno 61] Connection refused>"}
```

**What the tester sees.** "✓ Key saved… You're ready," followed by every single
message failing with `couldn't reach that brain — it looks offline from here`
(`app/floor.jsx:339`). That sentence is correct and it is not enough: it never
names Hermes, never says a gateway has to be running, and never points at
`Start-CafresoHQ.sh`, which is the script that would have started one.

**Smallest fix.** Have the key-save surfaces consume the `restarted` field the
server already returns, and when it is false on a self-host, say so: "key
saved, but nothing is listening on 127.0.0.1:8642 — run
`sh Start-CafresoHQ.sh`, or pick a different brain in Settings → Connections."
The liveness fact is already computed — `drivers/hermes.py:383` produces
`probeError: 'is not running'` with the detail `nothing is listening on
127.0.0.1:8642`, and the hire modal renders it as `NOT RUNNING`
(`modals/hire.jsx:516`). The key-save path just doesn't ask.

### 6. The README documents a directory that was deleted, and an env var that moved out of the repo.

- `README.md:16` and `README.md:50-54` describe a `frontend/` SvelteKit app and
  tell the reader to run `npm --prefix frontend install`. There is no
  `frontend/` in this repo — it was removed in `8dbcc6f` ("Cutover: move
  cafreso.com frontend to the cafreso-pages repo"), and `git ls-files` matches
  zero paths under it. `README.md:73-74`'s deploy commands have the same
  problem.
- `README.md:81` says to "copy `.env.example` and set `GATEWAY_IP` first".
  `.env.example` says the opposite in its own header: "Fleet/gateway deploy
  config (GATEWAY_*, OCI_*, ORACLE_SRC, …) moved to the cafreso-fleet repo".
  There is no `GATEWAY_IP` to set. (Line corrected in this commit.)

**What the tester sees.** The first command block in "Local development" fails
with `ENOENT`, which reads as a broken clone rather than a stale doc.

**Smallest fix.** The `GATEWAY_IP` sentence is corrected here. The `frontend/`
sections need a real decision (point at cafreso-pages, or drop them) and are
left for scoped work rather than guessed at in an audit.

---

## (b) Works, but unexplained

- **The office lives in this browser and nowhere else.** Chat, roster, tasks
  and prefs are localStorage under `cafresohq_hq_v1:` / `cafresohq:`
  (`modals/settings.jsx:1354-1356`). One cleared browser profile is the whole
  office. There is a well-built export/import — with secrets scrubbed in both
  directions — but nothing on the first-run path mentions that this state is
  ephemeral or that a backup exists.
- **Nothing says what the default brain requires.** The default provider is
  `hermes` (`claude-client.jsx:364`) and the entire onboarding narrative is
  "get a free OpenRouter key". On a self-host, that key is necessary and not
  sufficient — a Hermes gateway must also be running. Item 5 above is the
  failure; the missing sentence is the cause.
- **Raw driver errors exist behind the classifier.** `drivers/local_http.py:135`
  emits `cannot reach <url>: <urlopen error [Errno 61] Connection refused>` and
  `:131` emits `upstream <code>: <body>`. Every UI surface I checked funnels
  these through `SNAG_CAUSES` / `OFFICE_CAUSES` / `OBSIDIAN_CAUSES`
  (`app/floor.jsx:322`, `:503`) and turns them into one plain sentence. Worth
  knowing that the raw string is one un-classified call site away from a
  tester's screen.
- **`Start-CafresoHQ.sh` is the better entry point and the README never
  mentions it.** It starts the Hermes gateway, shares the bearer key, and
  explains the mkcert tradeoff — i.e. it solves items 3 and 5 for anyone who
  knows to run it. The README sends people to bare `serve.py` instead.

---

## (c) Fine — stated so it doesn't get re-audited

These are the places I expected to find problems and did not.

- **Error copy is genuinely excellent.** `app/floor.jsx` classifies a failure
  into one honest sentence with a way forward, and covers cases most products
  miss: Safari's `Load failed` and Firefox's `NetworkError…` alongside Chrome's
  wording (`:330-340`), a cold local model still loading weights (`:346`), a
  model that isn't installed, and a separate table for Obsidian so an
  `ECONNREFUSED` from a *different* program doesn't get blamed on the office
  (`:503-535`).
- **The first-run path does not auto-launch a slideshow.** `app.jsx:582-598`
  deliberately opens with the CEO greeting and the candidates deck instead.
  `GettingStarted` (`ui/onboarding.jsx:443`) persists past a tour skip, so
  there is no dead end.
- **The tour-reopen bug is already fixed.** `ui/onboarding.jsx:190` resets
  `idx` on every open, with a comment naming both ways the old behaviour
  reached a user, including the cross-width `steps[9] === undefined` blank
  render.
- **The no-brain state is honest.** `app/cast.jsx:604-633` says
  `No brain is set up yet — add your own AI key in Settings → Connections`, and
  explicitly refuses to claim a shared brain it hasn't verified. The Settings
  system panel likewise gates its "Premium active" line on `health.managed`
  (`modals/settings.jsx:1512`) rather than hardcoding it.
- **Destructive actions are labelled.** 39 `window.hqConfirm` call sites. Vault
  delete names the file, counts the inbound wikilinks that will go dead, and
  says "this cannot be undone" (`views/vault.jsx:1295-1305`). Office import
  says it REPLACES and reloads (`modals/settings.jsx:1429`). Clearing the
  notification bell says explicitly that nothing is deleted
  (`ui/onboarding.jsx:640`). Notably, the *dangerous* surface is off by
  default: `/cafresohq/stream` is DISABLED unless `CAFRESOHQ_ALLOWED_DIRS` is
  set, and the banner says so (`serve.py:5548`).
- **Secrets are handled correctly on every path I traced.** No key is logged,
  printed, or echoed — grepping `serve.py`, `drivers/`, `docker/` and
  `night_runner.py` for key-shaped output found nothing. The provider key is
  written only to `~/.hermes/.env` at `0600` (`drivers/hermes.py:254-258`).
  The office backup blocks the encrypted key blob and the device AES key
  outright and blanks any `*Key` field, *in both directions*
  (`modals/settings.jsx:1355-1356`). The Hermes config export ships
  `config.yaml` only and refuses key material on import
  (`serve.py:4986-4996`). The "copy diagnostics" button collects apiBase,
  health, UA and URL — no secrets (`modals/settings.jsx:1316-1322`). Keys do
  sit in plaintext localStorage in the browser, which is inherent to a
  local-first browser app and is at least honestly labelled as a convenience
  copy (`claude-client.jsx:257-259`).
- **A vault path that doesn't exist isn't a failure mode.** The vault root
  defaults under the state dir and is created on demand
  (`serve.py:848-849`, `:934`); a cold `/vault/list` returns `{"files": []}`.
- **Local runs need no ICP identity.** `/health` reports
  `auth_required: false` on a bare `serve.py`; nothing gates the first thirty
  minutes behind Internet Identity.
- **Binding wide without a key is caught.** `serve.py:5507` warns, and the
  privileged routes refuse non-loopback callers regardless.
- **The stale-bundle trap is handled twice over** — a flushed startup warning
  and a `console.warn` injected into the page itself, both naming the build
  command (`serve.py:5292-5300`, `:2093-2098`).

---

## Documentation fixes applied in this commit

Only errors verified by running them:

- `README.md:58` — `python` → `python3`, and the missing `npm install` /
  `npm run build` steps added ahead of it (items 1 and 2). Without these two
  lines a clone cannot reach the app at all.
- `README.md:58` — the URL now says the server prints its own scheme, because
  it is `https://` whenever mkcert is present (item 3).
- `README.md:81` — the `GATEWAY_IP` instruction removed; `.env.example` says
  that config moved to the cafreso-fleet repo (item 6).

The `frontend/` sections (item 6) are **not** touched — pointing them at
cafreso-pages versus deleting them is a decision, not a typo.

No behavioural code changes. Every code fix above is described, not made.

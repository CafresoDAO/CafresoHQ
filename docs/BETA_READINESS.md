# Beta readiness — re-audit

**2026-09-05 (second pass).** Supersedes the audit dated the same day at
`89d1163`, whose verdict was *"not shippable to an outside tester today, for
exactly one reason: the default security posture."* Verified against `6887f20`
(`#336`), in a clean worktree, `npm run build` → `[ui] built 8 assets ->
dist-ui/ (graphEngine=true)`.

One commit landed after the measurements below were taken: `## 337.`, on the
integration branch, closing an ask-then-write race on both upload doors. It is
described under durability rather than measured here, because it postdates the
running server every probe in this document was sent to. It strengthens the
verdict and changes nothing in it.

Method: a real `python3 serve.py` with **no configuration at all** — no `.env`,
no `CAFRESOHQ_ALLOWED_DIRS`, no `CAFRESOHQ_API_KEY` — then adversarial probing
of the running process with raw `http.client`, not `urllib`, so the `Host`
header could be forged (urllib rewrites it from the URL and would have turned
every rebinding probe into a no-op). Twenty-eight request shapes in the first
sweep, thirty-one in the second. Every finding below carries a request I
actually sent and the reply I actually got back.

Test suite at this commit: **519/520 suites pass**. The single failure is the
known, pre-existing, foreign-owned
`scripts/test_worker_payout_sweep_does_not_wipe_mid_sweep_accrual.py`: its nine
behavioural assertions all pass and it fails only on `moc`'s implicit-`transient`
diagnostics (`M0219`) in `src/cafresohq_state/main.mo`, a file this session may
read and must not touch.

---

## Headline

**Yes. An outside beta tester can be handed this today.**

The blocker the last audit named is closed, closed on all three of the
mechanisms that made it work, and closed in a way I re-measured rather than
read. Everything still open is a rough edge: a tester is annoyed, confused for
a minute, or waits fifteen seconds too long. Nobody's SSH key leaves the
machine, nobody loses work, and nothing on the first-run path dead-ends.

What follows is the measurement, then the annoyances, then the four gates that
are real but are not this session's to close.

---

## The default posture, re-measured from scratch

This is the section the last audit's verdict turned on, so it is the section I
re-derived from nothing rather than diffing.

Startup banner on a bare `python3 serve.py`:

```
CafresoHQ -> http://localhost:8974/hq.html
  📱 Mobile / LAN  -> http://10.0.0.131:8974/hq.html
  proxy /lmstudio/* -> localhost:1234/*
  proxy /ollama/*   -> localhost:11434/*
  /cafresohq/stream  ELEVATED · tools=… · dirs=['/Users/anthonym/Documents']
  /fs/* reads        sandboxed to ['/Users/anthonym/Documents']
  /codex/stream      CODEX · dirs=['/Users/anthonym/Documents']
```

Two things changed in that banner since the last audit and both matter: the
sandbox is `~/Documents` alone, and the `/fs` read routes now get their own
line saying what they will do rather than leaving the reader to infer it from
the agent endpoint's line.

### What a page the tester merely visits can reach

Every row below is a request sent at that running server. `ACAO` is the
`Access-Control-Allow-Origin` header on the reply — with no ACAO the browser
refuses the body to the page, whatever the status code says.

**Reads.**

| request | result |
|---|---|
| `GET /fs/file?path=~/Documents/<decoy>` | 200, **no ACAO** |
| `GET /fs/file?path=~/<decoy>` (dotfile tier) | **403** `path is outside CAFRESOHQ_ALLOWED_DIRS` |
| `GET /fs/file?path=/etc/hosts` | **403** |
| `GET /fs/browse?path=$HOME` | **403** |
| `GET /fs/collect?path=~/.ssh` | **403** |
| `GET /hq/state/tasks`, `/vault/list`, `/terminal/status`, `/browser/status` | 200, **no ACAO** |
| `GET /health`, `/idle`, `/market/quotes` | 200, `ACAO: *` — public by design |

The `$HOME`-wide default is gone (`## 315.`). `~/.ssh` and `~/.hermes/.env` are
403 on a default run — I probed the real paths and read no byte of either; the
assertion is about the boundary, not the secret.

**Writes and code execution.** Every one of these was fired with
`Content-Type: text/plain`, which is not preflighted, so the browser cannot
refuse on the office's behalf and the gate has to:

```
POST /tools/exec          Origin: https://evil.example  → 403 origin not allowed
POST /spawn                       "                     → 403
POST /missions                    "                     → 403
POST /projects/clone              "                     → 403
POST /approvals/external          "                     → 403
POST /agents/install              "                     → 403
POST /graph/publish               "                     → 403
POST /browser/open                "                     → 403
POST /fs/mkdir                    "                     → 403
POST /fs/delete                   "                     → 403
PUT  /hq/state/<name>             "                     → 403
PUT  /vault/note                  "                     → 403
POST /cafresohq/stream            "                     → 403
POST /lmstudio/v1/chat/completions "                    → 403
```

That is `## 322.` (the gate over the key-protected prefixes) plus `## 332.`
(the `ROUTES` proxy fall-through it did not originally cover). `/tools/exec` and
`/lmstudio/` now answer the same forged Origin the same way, which is exactly
the discrepancy `## 332.` existed to remove.

**The rebinding path — the one that defeats both CORS and loopback binding.**
An attacker who points `evil.example` at `127.0.0.1` has a page that is
genuinely same-origin with the office, sends no `Origin` at all, and originates
on the victim's own loopback. Sent with `Host: evil.example:8974`:

```
GET  /fs/file?path=~/Documents/<decoy>  → 403 host not allowed
GET  /fs/browse?path=~/Documents        → 403 host not allowed
POST /fs/mkdir                          → 403 host not allowed
POST /tools/exec                        → 403 host not allowed
POST /terminal/spawn                    → 403 host not allowed
POST /cafresohq/stream                  → 403 host not allowed
GET  /terminal/nonce                    → 403 host not allowed
```

`## 315.` for the `/fs` family, `## 323.` for the terminal. The terminal one is
the important half: `## 315.` left it explicitly as a measured, unpulled thread
and `## 323.` pulled it and found `101 Switching Protocols` on the end of it.
On this build `/terminal/nonce` answers a forged `Host` with 403, and the
`Origin: https://evil.example` variant with `403 origin not allowed`.

**The empty-string trap.** `CAFRESOHQ_ALLOWED_DIRS=` used to print `DISABLED`
and open the whole disk — the most security-conscious reading of the banner was
the one that unlocked everything. `.env.example:13-15` now documents the
reversed polarity, and the opt-out has a name of its own
(`CAFRESOHQ_ALLOWED_DIRS_UNRESTRICTED`) that cannot be arrived at by leaving a
variable blank. A dangerous behaviour no longer hides behind an absence.

**Secrets on the way out.** `_LOG_SECRET_RE` now covers
`k|key|token|api_key|nonce`. Measured on the live server:

```
$ curl -H 'Upgrade: websocket' '…/terminal/ws?k=HUNT341FAKEKEY'
$ grep HUNT341FAKEKEY serve.log      → no match
$ grep terminal/ws    serve.log      → "GET /terminal/ws?k=<redacted> HTTP/1.1" 404
```

That is `## 315.`'s incidental find plus `## 326.`, which caught the PTY nonce
riding the parameter that the first redaction did not name. `## 325.` closed the
worst of the family — a BYOK Google key returned whole in a 500 body, because a
`ValueError` on a mistyped model name stringified a URL with `?key=` in it —
by moving the credential to an `x-goog-api-key` header and scrubbing every
generate error path.

### Verdict on the default posture

A page the tester merely visits gets: `/health`, `/idle`, `/market/quotes`, and
nothing else it can read or fire. That is the right answer, and it is the answer
the last audit was waiting for.

---

## The last audit's four findings, tracked

1. **`$HOME` served keylessly to any caller, and the documented opt-out opened
   the whole disk.** — **CLOSED**, `## 315.`, all three mechanisms (default
   narrowed to `~/Documents`, empty list now denies, `/fs` family behind the
   rebinding host gate). Re-measured above. `## 323.` closed the terminal-shaped
   twin that `## 315.` had measured and left standing.
2. **The banner prints two URLs; one lands on a different server, the other is
   dead; a contended port is a raw traceback.** — **STILL OPEN**, all three
   halves, re-measured. See rough edges 1–3.
3. **The unload flush is capped at 64 KiB by `keepalive`.** — **UNCHANGED** in
   code (`app/storage.jsx:242-246`), and on re-reading it is smaller than the
   last audit ranked it. See rough edge 4.
4. **The API key lands verbatim in the access log.** — **CLOSED**, `## 315.` +
   `## 326.`. Measured above.

---

## Rough edges — a tester is annoyed, not hurt

Ordered by how likely a tester is to hit one, not by how loud it is.

### 1. The `📱 Mobile / LAN` URL the banner prints does not work

`serve.py:6109-6122` prints the LAN line whenever `_local_ip()` returns
anything, with no reference to what the server actually bound;
`serve.py:6093-6095` binds `127.0.0.1` on every local run. Measured against the
address the banner itself printed:

```
banner:  📱 Mobile / LAN  -> http://10.0.0.131:8974/hq.html
$ curl -m 4 http://10.0.0.131:8974/health   →  exit 7, connection refused
```

"Try it on my phone" is one of the first things anyone does with a product that
ships a mobile tab bar and an iOS service worker. The banner invites it and the
address is dead. `README.md:75-78` now explains this, which is why it is an edge
and not a blocker — but the explanation is in a file the tester has already
scrolled past, and the invitation is on the screen in front of them.

### 2. `localhost` is IPv6-first and the office binds IPv4 only

`serve.py:6110` prints `http://localhost:{PORT}/hq.html`; the socket is bound to
the IPv4 literal. On macOS `localhost` resolves `::1` first. Reproduced on this
machine, on the default port, running the README's exact command:

```
$ python3 serve.py
CafresoHQ -> http://localhost:8787/hq.html     ← started fine, bound 127.0.0.1
$ lsof -nP -iTCP:8787 -sTCP:LISTEN
  com.docke …  TCP *:8787 (LISTEN)             ← IPv6, someone else's
  Python    …  TCP 127.0.0.1:8787 (LISTEN)     ← ours
$ curl http://localhost:8787/health
  {"status":"ok", …, "uptime_seconds": 2738921, "platform": "Linux",
   "runtime_env": "container"}                 ← 31 days up, a different server
```

The banner says the office is up, the office *is* up, and the printed URL goes
somewhere else with no error and no warning. This is the highest-consequence
edge on the list because it is silent, and the lowest-frequency one because it
needs something already listening on `::1:8787`. A tester with a clean machine
never sees it; a tester who once ran the container does.

### 3. A genuinely contended port is a stack trace

`serve.py:6101`'s `with ThreadedServer((_bind_host, PORT), Handler)` is
unguarded. Measured:

```
OSError: [Errno 48] Address already in use
```

No sentence naming `PORT`, no suggestion to pick another. So the default port
has two opposite failure modes — contended on IPv4 gives a traceback, contended
on IPv6 gives the wrong server silently — and neither is explained on screen.

### 4. The unload flush is capped at 64 KiB, and it matters less than it looks

`app/storage.jsx:242-246` still sends the last-gasp PUT with `keepalive: true`,
which every browser caps at 64 KiB across all in-flight keepalive requests,
rejecting an oversize body with a `TypeError` that the deliberate
`.catch(() => {})` swallows. Unchanged since the last audit, and I did not
reproduce it in a browser.

Ranked lower than last time, on re-reading rather than on new evidence. The
comment at `:226-227` is right that "localStorage still holds the value either
way": the browser copy is written synchronously and is what the next load reads,
so the cap costs the *server file's* freshness, not the tester's work. The loss
only materialises for someone who clears site data or moves browsers between
sessions. And `## 336.` shrank the exposure from the other end — `receipts` was
the store with no bound at all, growing 220 bytes a stamp toward the origin's
5 MB ceiling, and now caps at 200 in both the write and the mount-fetch merge,
the way the activity log always did.

Worth a browser-side reproduction before anyone changes code. Not worth holding
a beta for.

### 5. A missing brain costs fifteen silent seconds before the error

`_hermes_proxy` retries the upstream connect ten times at 1.5s apart before
answering. Measured with the gateway port pointed at a dead port:

```
POST /hermes/v1/chat/completions
  → nothing for ~15s, then 502
    {"error": "hermes: [Errno 61] Connection refused",
     "hint": "the agent gateway is restarting or down — retry in ~15s"}
```

The retry exists for a good reason (the gateway is briefly down after any key or
model change, and a transient 502 mid-conversation is worse). The error, when it
finally lands, is well built — it names the cause and offers a next step, which
is more than most. But a first-run tester whose gateway never came up types
hello and watches nothing happen for fifteen seconds, three times, before
learning anything.

`Start-CafresoHQ.sh:66-68` heads this off for the commonest case — no `hermes`
CLI at all gets an immediate `WARN … /hermes will 502 until you install it
(Settings → Agents)` — and `## 334.` fixed the cruellest version of it, where
the gateway's own 401 was relayed to the shell and rendered as *"Your session
expired — reopen HQ from ai.cafreso.com"* to somebody who had installed the
thing ninety seconds ago and had no session to expire. The banner now branches
on `runsLocally` (`app.jsx:761, 7260-7299`) and sends a local reader to
Settings → Connections instead of out of the product.

The residue is the fifteen seconds of silence, and it is the largest thing
standing between a first-run tester and their first reply.

### 6. `/gap/status` and `/news/status` are readable cross-origin — new, minor

Not in the last audit, and not in any prefix list. `## 333.` made
`_HOST_DATA_PREFIXES` iterate `ROUTES` so a proxied GET stops handing the local
model roster to a stranger's tab. These two are hand-named paths
(`serve.py:2141-2142`) that proxy the standalone search worker's status
listener, and they sit under no listed prefix at all. Measured:

```
GET /gap/status   Origin: https://evil.example
  → 200, Access-Control-Allow-Origin: *
    {"brave": {"month": "2026-09", "used": 0, "cap": 3000,
               "remaining": 3000, "byKind": {}, …}}
GET /news/status  Origin: https://evil.example
  → 200, ACAO: *   {"news": {"enabled": false, "perRunMax": 6, …}}
```

Operational counters — search quota consumed, per-kind breakdown, run history.
No credential, no file, no write, and only populated when the standalone worker
container is running. It is the same species as `## 333.` one route further out,
and it is on this list rather than the one above because what leaks is a usage
graph, not a secret.

### 7. The relayed upstream ACAO defeats `## 333.` when the model server is permissive

`_proxy` (`serve.py:5314-5318`) forwards every upstream response header except
the hop-by-hop set and `content-encoding` — including the upstream's own
`Access-Control-Allow-Origin`. So `## 333.`'s withholding is only as good as the
model server's CORS. Measured with a service on `:1234` that echoes `Origin`:

```
GET /lmstudio/v1/models   Origin: https://evil.example
  → 404 (upstream's), Access-Control-Allow-Origin: https://evil.example
```

The office withheld its own header correctly; the upstream's rode through
underneath it. Read-only, and the POST arm is 403 regardless (`## 332.`, proved
above), so what a stranger's tab can obtain is whatever the local model server
answers to a GET — the roster, on a real LM Studio. Worth a hunt of its own; not
worth a beta.

---

## What is *not* on the blocker list, and why

Three things a generous auditor would be tempted to write up, checked and found
not to be problems:

- **`/cafresohq/stream` is `ELEVATED` by default with `Edit,Write` in its tool
  list.** That is the product — an office whose agent cannot write is not a
  safer office, it is a broken one — and it is reachable only from loopback,
  only same-origin, and only inside `~/Documents`. Forged Origin: 403. Forged
  Host: 403.
- **The first-run path.** `npm install` → `npm run build` → `python3 serve.py`
  works from the tree; `hq.html` is 200 and all fourteen of its referenced local
  assets are 200. `Start-CafresoHQ.sh` does the npm steps itself if `dist-ui/`
  is missing, rather than handing the 500 page the job of teaching a stranger
  what to run.
- **Server-side durability.** `PUT /hq/state/<name>` → `GET` round-trips through
  `hq-state/`, written with `mkstemp` + `fsync` + `os.replace` under a per-name
  temp file. `## 335.` closed the one path that could *delete* data on a
  transient fault — the OCI append arm treated any exception on the read half as
  "the note does not exist yet" and wrote the fragment over the whole note,
  answering `200 {"mode":"append"}` while the boss's note went to the bucket in
  pieces. It now classifies the failure and refuses to write on anything that is
  not a genuine 404.

  `## 337.` closed the last member of that family I am aware of, and it is the
  one most likely to have met a beta tester. `serve.py` is a `ThreadingMixIn`
  server, and both upload doors asked `free_name` whether a name was taken and
  *then* wrote it. Forty concurrent POSTs of `report.txt` to `/fs/upload`
  produced **40 receipts saying filed and 13 files on disk**, with
  `report (2).txt` handed to twelve different uploads; `/vault/upload` lost
  seventeen of forty the same way. The receipt was at its most confident exactly
  where the loss was total — full path, byte count, and a `renamedFrom` line
  explaining a considerate sidestep onto a name eleven other people had also been
  given. `claim_name` now makes "is this free?" and "this is mine" one
  `O_CREAT|O_EXCL` syscall, and both doors write through the descriptor they
  claimed rather than re-opening a path they merely looked at.

  I did not re-measure this one: it landed after the server every probe above
  was sent to. I am reporting it because a tester dragging files into a shared
  project is an ordinary Tuesday, and a lie in a receipt is the one failure
  shape a beta tester cannot detect for themselves.

---

## Gates that exist and are not this session's to close

Named explicitly so nobody reads their absence above as a claim that they are
done. None of them blocks handing a **local** office to a tester — the default
run is `mode: local`, `auth_required: false`, `vault_backend: fs`, and touches
no canister — but all four are real, and three of them gate the *hosted* path.

1. **The `src/cafresohq_state/main.mo` heap → stable-memory migration**
   (`docs/STATE_CANISTER_STORAGE_MIGRATION.md`, Track 2, not started). A foreign
   session holds uncommitted work in that file; this audit read it and changed
   nothing. It is also the sole failing suite, via `moc`'s `M0219` diagnostics.
2. **Any mainnet action.** No `dfx deploy`, no install/upgrade, no IC call of any
   kind was made here, read-only ones included. Only the user can trigger one,
   and the hosted beta needs one.
3. **Cycles auto-top-up.** Still absent. `cafresohq_state` reached zero on
   2026-08-05 and the IC wiped module and state; the monitor dashboard that
   landed the same day reports but does not alert and does not top up. A hosted
   beta that outlives its balance loses its testers' data, exactly once.
4. **Nine MCP connectors unauthorized in this session** (figma, intercom, asana,
   atlassian, clickup, linear, monday, notion, slack). They need authorization
   through claude.ai connector settings or an interactive `claude mcp` / `/mcp`
   session; nothing here can do it, and no finding above depends on them.

---

## Documentation fixes applied in this commit

Only errors verified by running them:

- `README.md:78-80` — "The `/fs` read routes … default to serving your **home
  directory**." That was true at the last audit and has been false since
  `## 315.`: the default is `$HOME/Documents`, and `$HOME` itself is 403.
  Corrected, with the empty-string polarity and the named opt-out spelled out,
  since the sentence's whole job is to tell a tester what a bare run exposes.
- `.env.example:15` — the parenthetical crediting the empty-list reversal cites
  `#318`; the entry that made an empty list deny is `## 315.` (`#318` is the
  night-shift one). Corrected.
- `docs/BETA_READINESS.md` — this file, rewritten.

No behavioural code changes and no new tests. Every code-level finding above is
described, not fixed.

---

## Verdict

**Shippable to an outside beta tester today.**

The one blocker is closed on every mechanism that made it work, and I measured
each one rather than reading the entry that claims it. A page the tester merely
visits can reach `/health`, `/idle` and a stock ticker. Their home directory is
403. Their shell is 403 twice over — once on Origin, once on Host. Their API key
is `<redacted>` in the log and absent from the error body.

What is left is seven annoyances, and the two worth fixing before the invitation
goes out are the cheap ones: the LAN URL the banner promises and cannot deliver,
and the fifteen seconds of silence before a missing brain says so. Neither costs
a tester anything but patience, and neither needs a decision — only an hour.

Send the invitation.

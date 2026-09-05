# Beta readiness — re-audit

**2026-09-05.** Supersedes the audit dated at `aae4317`. Verified against
`89d1163` on branch `hunt316-beta2`.

Method: a genuine fresh install — `git archive HEAD | tar -x` into an empty
scratch directory, then the README's commands run verbatim as a stranger would
run them, followed by adversarial probing of the running server. Every finding
below carries a command I actually ran or a line I actually read.

**Headline: the three blockers from the last audit are genuinely closed, and
the first-run path now works end to end on a cold clone.** What is left is one
finding that is materially worse than anything the last audit found — it is a
security problem, not a startup problem — and a small cluster of first-run
papercuts around the printed URLs. The previous audit's verdict, "the app is in
better shape than its docs," is still true of the *product*; it is no longer
true of the *default security posture*, and one line of the old report's own
"clean" list turns out to have been wrong.

Test suite at this commit: **496/497 suites pass**. The single failure is the
known, pre-existing, foreign-owned
`scripts/test_worker_payout_sweep_does_not_wipe_mid_sweep_accrual.py` (it fails
on `moc`'s implicit-`transient` diagnostics in `src/cafresohq_state/main.mo`,
not on the behaviour it tests).

---

## Closed and verified since the last audit

Each of these was re-run, not taken on trust.

- **A fresh clone can start.** `npm install` → `npm run build` → `python3 serve.py`
  works from a bare `git archive` export with nothing else on the machine.
  `npm run build` printed `[ui] built 8 assets -> dist-ui/ (graphEngine=true)`.
  Every asset `hq.html` references resolves 200 on the fresh server — all five
  icons, all seven bundle files, `manifest.webmanifest`, `styles.css?v=22`. The
  first pixel renders. (Old items 1, 2; ledger `## 296.`, `## 300.`)
- **The startup banner survives a redirect.** `serve.py:5497` calls
  `sys.stdout.reconfigure(line_buffering=True)` before anything prints.
  Confirmed: `python3 serve.py > log 2>&1` produced the full banner including
  the `CafresoHQ -> …` line. (Old item 3; ledger `## 301.`)
- **The onboarding green ✓ is gone.** `ui/onboarding.jsx:348` now reads
  `if (!(r && r.serverStored))` and takes the error branch, with a comment
  naming the exact failure it closed. (Old item 4; ledger `## 297.`)
- **The README no longer documents `frontend/`.** `README.md:16` and `:50-52`
  now say it lives in `../cafreso-pages` and was deleted here in `8dbcc6f`.
  `README.md:86` no longer mentions `GATEWAY_IP`. (Old item 6.)
- **The cross-origin `/fs` read hole is closed.** `serve.py:1822-1838` withholds
  `Access-Control-Allow-Origin` entirely for `_HOST_DATA_PREFIXES`. Confirmed:
  `curl -H 'Origin: https://evil.example' /fs/file?path=$HOME/.zshrc` returns
  200 with **no** ACAO header, so a browser refuses the body. (Ledger `## 294.`)
- **Server-side state writes are atomic.** `serve.py:3853-3867` uses
  `mkstemp` + `fsync` + `os.replace`, with a per-name temp file so two
  concurrent writers cannot truncate each other. A killed server mid-write
  leaves the previous complete file, not a truncated one.

---

## (a) Genuinely broken

### 1. A default `python3 serve.py` serves the tester's entire home directory to any unauthenticated caller — and the one knob that looks like it turns this off turns the sandbox off instead.

This is the finding that would embarrass the project. It has two halves.

**Half one — the default is $HOME, not "disabled".** `serve.py:197-203`:

```python
_ALLOWED_DIRS_EXPLICIT = 'CAFRESOHQ_ALLOWED_DIRS' in os.environ
_cafresohq_allowed_dirs = [d.strip() for d in
                          os.environ.get('CAFRESOHQ_ALLOWED_DIRS',
                              os.path.expanduser('~') + os.pathsep +
                              os.path.join(os.path.expanduser('~'), 'Documents')
                          ).split(os.pathsep)
                          if d.strip()]
```

The comment eleven lines above it (`serve.py:187-188`) says the opposite:
"If either allowlist is empty the endpoint refuses requests, so the
unconfigured default is safe." `.env.example:7` says a third thing: "defaults
to `$HOME/Documents`". The default is `$HOME` **and** `$HOME/Documents`, and
`$HOME` subsumes the other.

The `/fs` read routes are keyless by design (`serve.py:366-370, 403-410`). On
the fresh install, with no configuration at all:

```
$ curl -s 'http://localhost:8974/fs/collect?path=/Users/anthonym/.ssh'
{"root": "/Users/anthonym/.ssh", "files": [{"path": "id_ed25519",
 "contentType": "application/octet-stream", "size": 419,
 "b64": "LS0tLS1CRUdJTiBPUEVOU1NIIFBSSVZBVEUgS0VZLS0tLS0K…"}]
```

That is the private key, base64, in one request. `~/.hermes/.env` — the file
holding the tester's own OpenRouter key — also returns 200.

**And it is reachable from a web page.** The DNS-rebinding defence in
`_app_origins` (`serve.py:3652-3682`) is real and works, but only guards the
routes that consult it. `/fs` does not:

```
$ curl -H 'Host: evil.example:8974' '…/terminal/nonce'            → 403
$ curl -H 'Host: evil.example:8974' '…/fs/file?path=$HOME/.zshrc' → 200 + body
```

Under a rebinding attack the attacker's page is *same-origin* with the server,
so the (correct) CORS withholding above never comes into play — the browser
needs no ACAO for a same-origin fetch. Loopback binding does not help either,
because that is precisely what rebinding defeats. Net: any page a beta tester
visits while the office is running can read their home directory.

**Half two — the documented opt-out is an opt-*in* to everything.**
`serve.py:222-223`, inside `_within_allowed_dirs`:

```python
if not _cafresohq_allowed_dirs:
    return True
```

and the banner, `serve.py:5599-5600`:

```
  /cafresohq/stream  DISABLED (set CAFRESOHQ_ALLOWED_DIRS to enable)
```

A security-conscious tester who reads that banner and sets
`CAFRESOHQ_ALLOWED_DIRS=` to lock the thing down gets told **DISABLED** and
gets the whole filesystem:

```
$ CAFRESOHQ_ALLOWED_DIRS= PORT=8976 python3 serve.py
  /cafresohq/stream  DISABLED (set CAFRESOHQ_ALLOWED_DIRS to enable)
$ curl 'http://localhost:8976/fs/file?path=/etc/hosts'
##
# Host Database
$ curl 'http://localhost:8976/fs/browse?path=/etc'
{"path": "/private/etc", "parent": "/private", "entries": [{"name": "apache2", …
```

The banner is honest about `/cafresohq/stream` — that endpoint genuinely does
refuse. It is the `/fs` read routes that read the same variable with the
opposite polarity, and nothing in the banner or the docs distinguishes them.

**Why this matters more than the last audit's items 1–3.** Those were dead ends
before a pixel rendered: annoying, visible, self-correcting. This one is
invisible, and the failure mode is the tester's SSH key leaving their machine.

**Not fixed here** (audit, not bug hunt). Three things want deciding, not
guessing: whether the local default should be the state dir rather than `$HOME`;
whether an empty allowlist should mean "refuse" everywhere rather than "allow"
in `_within_allowed_dirs`; and whether the `/fs` reads should get the same
loopback-literal `Host` gate that `_app_origins` already implements for the PTY.

### 2. The banner prints two URLs. One can silently land on a different server, and the other is dead.

**The LAN URL is dead.** `serve.py:5580-5581` prints the Mobile/LAN line
whenever `_local_ip()` returns anything — unconditionally, with no reference to
what the server actually bound. `serve.py:5552-5554` binds `127.0.0.1` on every
genuine local run. Measured:

```
$ lsof -nP -iTCP:8974 -sTCP:LISTEN
Python  94318 anthonym  3u  IPv4  …  TCP 127.0.0.1:8974 (LISTEN)

banner said:  📱 Mobile / LAN  -> http://10.0.0.131:8974/hq.html
$ curl -m 3 http://10.0.0.131:8974/health   →  exit 7 (connection refused)
```

"Try it on my phone" is one of the first things a tester does with a product
that ships a mobile tab bar and an iOS service worker. The banner invites it
and the address does not work, with nothing on screen explaining why or naming
`CAFRESOHQ_BIND`.

**The localhost URL is IPv4-only while `localhost` is IPv6-first.**
`serve.py:5569` prints `http://localhost:{PORT}/hq.html`; the socket is bound to
the IPv4 literal `127.0.0.1`. On macOS `localhost` resolves `::1` first. On this
very machine, the maintainer's own, running the README's exact command:

```
$ python3 serve.py
CafresoHQ -> http://localhost:8787/hq.html      ← started fine, bound 127.0.0.1
$ curl -w '%{remote_ip}' http://localhost:8787/health
200 via ::1   {"status":"ok", …, "uptime_seconds": 2729697, …}
```

31 days of uptime: that is a *different* long-running container on `[::1]:8787`,
not the server just started. The banner says the office is up, the office is up,
and the printed URL goes somewhere else entirely — no error, no warning.

**The other half of the same trap: a truly occupied port is a raw traceback.**
`serve.py:5560`'s `with ThreadedServer((_bind_host, PORT), Handler)` is
unguarded. With an IPv4 listener already on the port:

```
Traceback (most recent call last):
  File ".../serve.py", line 5560, in <module>
    with ThreadedServer((_bind_host, PORT), Handler) as httpd:
  ...
OSError: [Errno 48] Address already in use
```

No sentence naming `PORT`, no suggestion to pick another. So port 8787 has two
opposite failure modes and neither is explained: contended on IPv4 → stack
trace; contended on IPv6 → silent wrong server.

### 3. The unload flush that closes `## 305.` is capped at 64 KiB, and the store it was written for is the one that outgrows it.

`app/storage.jsx:242-247`, the last-gasp write:

```js
fetch(`${window._API_BASE || ''}/hq/${p.scope}/${p.name}`, {
  method: 'PUT', headers: { 'content-type': 'application/json' },
  body: p.body, keepalive: true,
}).catch(() => {});
```

`keepalive: true` is what makes the write survive the page teardown, and it is
also what caps the request body at 64 KiB across all in-flight keepalive
requests — a Fetch-spec limit every browser enforces, rejecting the oversize
request with a `TypeError` rather than truncating it. The `.catch(() => {})` on
the same expression swallows that rejection, deliberately and for a good reason
(`app/storage.jsx:226-227`: "no toast on failure here — there is no surface left
to show one on").

The consequence is that the fix works while the office is small and stops
working once it isn't, with no signal at either point. The stores at risk are
exactly the two `## 305.` names as most exposed. `messages` is capped at 500
records (`app/storage.jsx:626`), each carrying up to 30 history entries
(`:627`) — 15,000 objects at the ceiling, far past 64 KiB; `activity` is the
store `## 305.` describes as "perpetually mid-debounce for as long as anyone is
working". The debounced timer at `:190-207` has no such cap and is unaffected;
it is only the tab-close path that quietly stops paying, and that is the path
the entry exists to protect.

I did not reproduce this in a browser — a fair reading is "a described risk with
a named mechanism", not "a measured loss". It is ranked third because when it
does bite, it re-opens `## 305.` exactly, and the person it bites is a tester
who has used the product enough to have something worth losing.

### 4. The API key lands verbatim in the server's access log.

`serve.py:5264-5265`:

```python
def log_message(self, fmt, *args):
    sys.stderr.write(f'{self.address_string()} - {fmt % args}\n')
```

No redaction. `serve.py:1876-1884` permits the key in the query string for
WebSocket handshakes — with a comment that names this exact hazard ("query
strings leak into access logs, proxy logs and the Referer of any resource the
page loads") as the reason to refuse `?k=` everywhere else. Measured:

```
$ curl -H 'Upgrade: websocket' 'http://localhost:8974/terminal/ws?k=SUPERSECRETKEY123'
$ grep SUPERSECRET serve.log
127.0.0.1 - "GET /terminal/ws?k=SUPERSECRETKEY123 HTTP/1.1" 404 -
```

`*.log`, `serve_stdout.log` and `serve_stderr.log` are all gitignored
(`.gitignore:8-10`), so this cannot be committed by accident. The realistic
route out is a tester attaching their log to a bug report — which is exactly
what you ask a beta tester to do. A one-line `?k=` scrub in `log_message` closes
it.

---

## (b) Works, but unexplained

- **Nothing on the first-run path says the office exposes `$HOME`.** Finding 1
  is the mechanism; this is the missing sentence. The banner reports the
  allowlist accurately (`dirs=['/Users/anthonym', '/Users/anthonym/Documents']`)
  and a tester will read it as a capability, not an exposure.
- **`Start-CafresoHQ.sh` is still the better entry point and the README still
  does not mention it.** Unchanged from the last audit. It starts the Hermes
  gateway, shares the bearer key, and explains the mkcert tradeoff. A README
  pointer is added in this commit.
- **The office still lives in this browser and nowhere else.** Unchanged and
  still worth a first-run sentence. The export/import is well built and
  scrubs secrets in both directions (`modals/settings.jsx:1355-1356`); nothing
  on the way in mentions it exists.
- **`.env.example:7` misdescribes the allowlist default** as `$HOME/Documents`.
  Corrected in this commit.

---

## (c) Checked and found clean — do not re-audit these

- **Path traversal, every route I could reach.** `/hq/state/..%2f..%2f..%2fetc%2fpasswd`
  → `{"error": "invalid name: …"}`; `PUT /hq/state/../../../../tmp/pwned` wrote
  nothing (`/tmp/pwned.json` does not exist); `/vault/file?path=../../../../etc/hosts`
  → `{"error": "path escapes vault directory"}`. `_within_allowed_dirs`
  (`serve.py:215-224`) uses `Path.relative_to` on a resolved path, not
  `str.startswith`, so a sibling prefix and a symlink both fail closed. The
  sandbox logic is right; only its default membership (finding 1) is wrong.
- **Error pages disclose nothing.** A malformed JSON body returns
  `{"error": "body must be valid JSON"}`; an unknown route returns the plain
  stdlib 404 page. `grep -c 'traceback.print_exc\|traceback.format_exc' serve.py`
  → 0. No stack trace reaches a client on any path I could provoke. (The
  `Server: SimpleHTTP/0.6 Python/3.14.6` header is version disclosure and is not
  worth a line item.)
- **No secrets in tracked files.** `git grep -nIE '(sk-or-v1-…|sk-ant-…|AKIA…|ghp_…|-----BEGIN … PRIVATE)'`
  over the whole tree returns exactly one hit, and it is a deliberate decoy in
  `scripts/test_a_late_init_frame_never_types_your_api_key_into_the_terminal.py:82`.
- **`.gitignore` covers what it needs to.** `hq-state/` (which contains the
  TLS cert and key — `_ensure_local_tls` caches them under `<state_dir>/tls`,
  `serve.py:5363-5371`), `.env`, `.env.local`, `worker.env`,
  `worker-standalone.env`, `*.log`, `dist-ui/`, `node_modules/`. I looked for a
  secret-bearing artifact the file misses and did not find one.
- **localStorage quota failure is handled properly.** `app/storage.jsx:165-171`
  catches, warns and dispatches; `app.jsx:1519-1538` listens, throttles to one
  toast per 10s, and distinguishes `QuotaExceededError` ("storage full") from a
  generic failure and both from a failed *file* write. This is better than most
  shipped products do.
- **Server-side write atomicity** — see "Closed and verified" above.
- **`serve.py` is cwd-independent.** `os.chdir(os.path.dirname(os.path.abspath(__file__)))`
  at `serve.py:5505`. Launched from an unrelated directory, `hq.html`,
  `graph-viewer.html` and `/health` all return 200, `PUT /hq/state/tasks` lands
  in the script's own `hq-state/`, and `/graph/publish` →
  `/graph/snapshot/<slug>` round-trips. I went looking for a split between
  `_hq_state_dir` (script-relative, `serve.py:432-433`) and `_public_graph_dir`
  (`os.getcwd()`, `serve.py:2165`) and the `chdir` makes them agree.
- **Cross-origin reads and the PTY rebinding gate** — see "Closed and verified".
- **The stale-bundle warning, the no-brain state, the destructive-action
  labelling and the error-copy classifier** were all re-confirmed present at the
  lines the last audit cited. I have nothing to add to that section and did not
  reproduce it here.

**One correction to the last audit's clean list.** It stated: "the *dangerous*
surface is off by default: `/cafresohq/stream` is DISABLED unless
`CAFRESOHQ_ALLOWED_DIRS` is set, and the banner says so." That is true of
`/cafresohq/stream` and false of the `/fs` read routes reading the same
variable, and the banner it cites is what makes the mistake easy to make. See
finding 1.

---

## Documentation fixes applied in this commit

Only errors verified by running them:

- `.env.example` — the `CAFRESOHQ_ALLOWED_DIRS` comment said the default is
  `$HOME/Documents`; it is `$HOME` **and** `$HOME/Documents`. Corrected, with a
  note that leaving it unset exposes the home directory to the keyless `/fs`
  reads.
- `README.md` — added a pointer to `Start-CafresoHQ.sh` (the entry point that
  starts the Hermes gateway, which bare `serve.py` does not), and a short
  "what a local run exposes" note covering finding 1 and the loopback bind.
- `docs/BETA_READINESS.md` — this file, rewritten.

No behavioural code changes. Every code-level finding above is described, not
fixed.

---

## Verdict

**Not ready to hand to an outside tester today — but for one reason, and it is
fixable in an afternoon.**

The product itself is in good shape and has visibly improved: the cold-start
path works, the error copy remains the best-built thing in the repo, the
persistence layer is atomic on the server and honest about failure in the
browser, and the traversal and CORS defences held under every probe I threw at
them. Finding 1 is the blocker, and it is a configuration-default problem sitting
on top of sandbox code that is otherwise correct. Findings 2 and 4 are an hour
of work between them. Finding 3 wants a browser-side reproduction before anyone
changes code.

Ship the moment finding 1 is decided.

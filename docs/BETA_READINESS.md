# Beta readiness — re-audit

## 2026-09-05 (`## 412.`) — the first five minutes INSIDE the office

`## 396.`, `## 399.` and `## 405.` walked everything up to the moment the page
renders. Nobody had driven what happens after it. Driven on an office of its
own — own port (8973, chosen after `lsof` showed a concurrent session holding
the first one over IPv6 while mine held IPv4), own `HOME`, `hermes` off
`PATH`. Nothing on mainnet, no II, no hosted path.

**Correct the mental model first: the onboarding tour is not part of a first
run.** `setTourOpen(true)` appears at exactly one site in `app.jsx`, the
`cafresohq:replayTour` handler. The first-run effect sets `tourSeen` true,
writes the CEO's welcome, and opens the candidate deck 1600ms later — it never
opens the tour. So the two onboarding surfaces a beta tester actually gets are
the **Getting Started checklist** and the **just-in-time coach marks**, and
anything reachable only through a tour step is second-visit-only.

**Fixed.** Both of those surfaces were behind one flag,
`ks('gettingStartedDone')`, whose only writer in the repo set it *true* — from
a 14px ✕ sitting flush against a 14px "–" that collapses the same card
reversibly. `useStored`, so it outlived the tab; and `coachMark` opens with
`if (gsDismissed) return null`, so the one click took both. The palette's only
recovery command ("Replay onboarding tour") recovers neither — the checklist's
render guard is `!gsDismissed && !tourOpen`. There is now a door back:
`cafresohq:showGettingStarted`, a listed Help command, and a ✕ tooltip that
says so. `scripts/test_the_x_on_getting_started_was_a_one_way_door.py` (the
wiring) and `scripts/test_the_x_on_getting_started_comes_back.py` (the same
click and the same door, driven in headless Chrome on a fresh profile).

**Not fixed, and the largest remaining onboarding gap.**
`<OnboardingKeyStep>` — the surface carrying `## 399.`'s honest key errors —
renders only inside a tour step, so on a genuine first run nobody sees it. The
checklist's own "Your AI brain" button goes to Settings → Connections instead.
What the first run *should* contain is a product decision, not an edit. And
when that step is reached, it asks `managedBrain` and `/hermes/trial-status`
but never the front desk's own measurement, so a machine with a working local
brain (measured here: `/health` `brain: null`, trial `active: false`,
`/agent/drivers?probe=1` → `ollama {"version": "reachable"}`) is told it "needs
your own free key from OpenRouter" and walked through the signup.

**Measured green, for the record.** A provider key survives a server restart
(`configured: true` → kill → restart → `configured: true`; `~/.hermes/.env` at
0600). A malformed key is refused with a sentence, not a status code. A
whitespace-padded key is trimmed on both sides of the wire. An empty key is a
removal and says so. And the front desk did not fall for a decoy: another
process held port 1234 and LM Studio still reported not-reachable, because the
probe asks `/v1/models` rather than trusting a TCP connect.

**Weak verdict, flagged.** "Onboarding writes survive a reload" is reasoned,
not driven, for the `tourSeen`-vs-CEO-welcome half: `tourSeen` is synchronous
localStorage set at t=800ms while the welcome goes through the file-backed
chat store, so a tab closed inside that window should come back with the flag
set and no welcome and no candidate deck. Unreproduced; durability is another
pass's scope.

**Still human-only:** the hosted / ICP first run, Internet Identity, and the
worker's own registration. None attempted.

---

## 2026-09-05 (`## 405.`) — the first run, walked in the README's own order

`## 396.` did the first cold-start pass and found the README's ordering did not
work. This one walked what that pass left: the prerequisites nobody checked,
the mkcert step nobody documented, and the search worker's separate setup path
nobody had followed. `git archive hunt409-coldstart | tar -x` into an empty
directory, `HOME` pointed at an empty temp dir, no `hermes` on `PATH`.

**The README's sequence works, exactly as written.** This is the transcript,
not a claim about it:

```
$ npm install
npm warn deprecated xterm-addon-fit@0.8.0: … xterm@5.3.0: …
added 265 packages, and audited 266 packages in 2s
$ npm run build
[ui] built 8 assets -> dist-ui/  (graphEngine=true)
$ python3 serve.py                       # PORT=8811, empty HOME
CafresoHQ -> http://localhost:8811/hq.html
  📱 Mobile / LAN  -> http://10.0.0.131:8811/hq.html
  💡 Set CAFRESOHQ_TLS_CERT + CAFRESOHQ_TLS_KEY (or install mkcert) for HTTPS …
$ curl -o /dev/null -w '%{http_code} %{size_download}' …/hq.html
200 11071
```

Three findings, all of them in what happens when a step is *not* met.

**1. "Node 18+ and Python 3" was a sentence, not a check.** `package.json`
declared no `engines` at all, so npm had nothing of the repo's own to enforce;
`esbuild@0.24.2` declares `>=18` and eslint its own floor, and npm treats every
`engines` field as a **warning** by default. A tester on Node 16 got that
warning buried under 265 packages of output and then "added 265 packages", and
discovered the problem later from inside the bundler, in a message that never
says "Node". Now: `engines.node: ">=18"` declared once, `.npmrc` sets
`engine-strict=true`, and `npm install` refuses. Measured, with the floor
temporarily raised to `>=99` to drive it on this machine:

```
npm error code EBADENGINE
npm error notsup Required: {"node":">=99"}
npm error notsup Actual:   {"npm":"10.9.2","node":"v22.17.1"}
```

The build script is the second net, for anyone who runs it directly. Driven
with `process.version` redefined to `v16.20.0`:

```
[ui] Node v16.20.0 is too old — CafresoHQ needs Node 18+.
[ui] The bundler (esbuild) and the linter both require it; on an older Node
     this build fails somewhere inside them with an error that never says so.
[ui] Install Node 18 or newer from https://nodejs.org (or `nvm install 18 …`)
```

**Python 3 was the weaker half of the worry.** serve.py and every module it
imports parse at `feature_version=(3,6)`; the whole office was driven green on
stock macOS `/usr/bin/python3` — **3.9.6** — and on 3.14.6, `GET /hq.html` 200
on both. The real failure is python3 missing outright, and the launcher handled
`npm` and not it. Before, verbatim:

```
[start] serving CafresoHQ on :8787  (loopback-only; serve.py prints the exact URL + scheme)
./Start-CafresoHQ.sh: line 86: exec: python3: not found
```

It promised a running office one line before the shell said the backend could
not start. After:

```
[start] ERROR python3 is not on PATH, and serve.py — the whole backend — is a
        Python program. Nothing in CafresoHQ can start without it.
        Install Python 3 (https://www.python.org/downloads/, or
        `brew install python3` / `apt install python3`), then re-run this script.
```

**2. The mkcert paragraph said the opposite of what the code does.** Item 6
below has the detail. Short version: no mkcert means **plain HTTP**, not a
self-signed cert; both `Start-CafresoHQ.sh` and item 6 of this document claimed
the fallback. Corrected in both, and the test derives the rule from serve.py's
call site rather than pinning the sentence.

**3. The search worker's setup path did not lead anywhere.** Item 7 below has
the detail: a gitignored `env_file` with no committed template, and a README
naming the *other* compose file's env file for the compose command. Fixed as
far as an agent may go; the credentials themselves are a human gate.

**Still human-only, and untouched by this pass:** the hosted / ICP first run
(item 3 below), Internet Identity (item 4), the worker's own registration and
Brave key (item 7). None was attempted. Docker Desktop was not running on this
machine, so `docker compose` was never executed either — the worker findings
are from the compose file, the README and `.gitignore`, and the new test
asserts them without docker.

---

## 2026-09-05 (follow-up to the fourth pass) — the silence, measured

The fourth pass below names one item "the largest single beta-blocker on the
path" and calls it a product decision. It is two things, and only one of them
is. This note records what the second one actually measured and what `## 399.`
did about it. Nothing else in this document is re-audited here.

**The number was wrong, and low.** The fourth pass, and rough edge 5 before it,
say *fifteen seconds of silence*. Driven on a genuine cold start — `git archive
HEAD | tar -x`, a temp `HOME` with no `~/.hermes`, a `PATH` with no `hermes` on
it, the gateway port pointed at a dead port — a first message took **46,467ms**
(46467 / 46993 / 46875 across three runs) to fail. The fifteen is `_hermes_proxy`
retrying the upstream connect ten times at 1.5s, measured on the wire at
15,104ms. The other two thirds are the browser: 502 is a retryable status to
`fetchStreamHead`, which tries the whole request three times. Both halves were
written down in this document already; nobody multiplied them.

**The answer that landed was a payload, not a sentence.** Raw JSON in the chat
bubble, a Unix errno inside it, and its only advice — *retry in ~15s* — false on
that machine specifically, because nothing was going to start.

**All four browser first-message paths shared it**: the boss chat and coworker
chat (`hq-runtime.jsx`), the terminal (`views/terminal.jsx`), and the mission
runner (`agent_runner.jsx`) all funnel through `CafresoHQClient.stream()`, whose
provider in a brand-new office is `'hermes'`. So did the client's own liveness
probe — asking *whether* there was a brain cost 15,069ms. `night_runner.py` is
the one sender that does not share it.

### What is now handled

- **The failure is fast.** `drivers/hermes.py` can now tell "the gateway is
  restarting" from "there is no hermes on this machine and never has been", and
  `_hermes_proxy` asks before it waits. **46,467ms → 25ms**, end to end through
  the browser's own send path against a real cold `serve.py`.
- **The failure is legible, and it points somewhere real.** The tester now
  reads: *"This office has no brain yet — nothing on this machine is answering
  as a model, so there is nowhere for that message to go. Open Settings →
  Connections and give the office one: paste a cloud key under CLOUD KEYS, or
  start LM Studio or Ollama and pick a model under ON THIS MACHINE."* That room
  is mounted and both of those panel headings are in it; the test asserts it
  rather than trusting it.
- **The restart window is intact.** A machine that *has* a gateway still sits
  out the full retry budget, verified against a cold tree with a `hermes` on
  `PATH`. The fleet container `pip install`s `hermes-agent`, so its console
  script resolves there and nothing about the hosted path changes.

### What is still a product decision

**Which brain the beta ships with.** Unchanged, and unchangeable from code. The
office still has none: no bundled model, no trial key, no first-run screen that
hands one over. A tester who does nothing after reading that sentence still
cannot send a message. `## 399.` makes the office honest about its own state in
25ms instead of dishonest about it in 46 seconds — that is a first impression
fixed, not a working brain delivered. Item 1 of "What a beta tester CANNOT
self-serve" below stands exactly as written, minus its last five words.

The fourth pass's closing line — that the two cheap fixes before the invitation
goes out are the LAN URL and the fifteen seconds of silence — is now one item
plus the sentence in the invitation naming which brain to install.

---

## 2026-09-05 (fourth pass) — the first-run path, actually walked

Scope note first, because it matters for how much of this document it moves:
this is **not** a re-audit. It is one thing the three passes below never did —
a cold start from a genuinely empty machine — plus the honest list of what a
beta tester cannot do for themselves. Verified against `4b22087` (`## 393.`)
plus `## 396.`, this session's own fix. Everything under the third-pass
heading stands; nothing here re-measures the security posture.

Every hunt in the standing loop, and every pass of this document, has walked
an office that already exists. Nobody had walked in as a stranger. That path
decides whether beta testing produces feedback or a pile of "it didn't start,"
and it is by construction the least-exercised code in the repo, because
everyone developing it already has state.

**Method.** `git archive HEAD | tar -x` into an empty directory — which is
exactly what a tester has, since `dist-ui/` and `node_modules/` are both
gitignored — a temp `HOME` with no `~/.hermes`, no `.env`, no `~/Documents`
and no keys of any kind, and `python3 serve.py` on a port of my own. Then the
same tree again with the bundle built. No mainnet call of any kind was made.

### What a fresh tester hits, step by step

1. **`python3 serve.py` starts.** The banner prints, `hq-state/` is created on
   demand with its `vault/` and `tls/` subdirectories, and `/health` answers
   `200` with `mode: local`, `auth_required: false`, `vault_backend: fs`,
   `hermes: false`, `claude_code: false`, `brain: null`. No config file is
   required to boot and no key is required to boot. Good.
2. **`GET /hq.html` before the build returns nothing at all.** Not a 500 — an
   empty reply, `ERR_EMPTY_RESPONSE` in the browser. **Fixed in `## 396.`**;
   see below. This was the single hardest stop on the path and it was
   invisible to every prior pass, because it is a runtime crash on a code path
   only an unbuilt tree reaches.
3. **After `npm install && npm run build`, `hq.html` is 200** and the office
   loads. Confirmed on the fresh tree.
4. **Empty state, server side, is deliberate and correct.**
   `GET /hq/state/tasks|agents|projects|notes|receipts` on a never-written
   store answers `200 null` rather than 404 — a decision `#142` made on
   purpose and documented in place — so a first load produces no red console
   and nothing downstream `.map`s an `undefined`. `/vault/list` answers
   `{"files": []}`. `/missions/scheduled` answers
   `{"schedules": [], "running": [], "browserActive": false}`.
   `/agents` answers a real roster with `installed: false`. Client-side empty
   states already have dedicated coverage in `scripts/`
   (`test_an_empty_office_never_promises_a_brain_this_machine_lacks.py`,
   `test_an_empty_library_greets_its_first_boss.py`,
   `test_a_first_run_is_not_judged.py`,
   `test_a_first_run_on_your_own_machine_is_not_told_its_session_expired.py`),
   and this pass found no new empty-collection fault to add to them.
5. **The first message needs a brain, and the tester has none.** On a machine
   with no `hermes` CLI, `/hermes/*` was the fifteen seconds of silence written
   up as rough edge 5 below. This pass did not improve it and did not re-measure
   it; a real fresh machine gets connection-refused, not the 401 my temp-`HOME`
   run saw from this developer's own already-running gateway.
   > **Re-measured and fixed by `## 399.`** It was not fifteen seconds, it was
   > **46.5**, and the tester's brain is still missing — see the follow-up at
   > the top of this document.
6. **Peripherals fail politely.** `/gap/status` and `/news/status` answer a
   5-second `502` naming the exact compose command that starts the standalone
   search worker.

### What `## 396.` fixed

`_serve_hq_html` passed its whole advisory sentence as `send_error`'s second
argument — the HTTP **reason phrase**, which the stdlib encodes latin-1. The
em dash in it raised `UnicodeEncodeError` *inside* `send_error`, after the
handler had committed to replying, so the socket closed with no response.
The `except` clause whose entire job is to teach a stranger the two commands
was itself the failure, and had been since it was written. The same call
interpolates `os.getcwd()`, so the crash also fires for any tester whose home
directory is named in a non-latin-1 script, em dash or not. Two siblings of
the same shape in `pty_server.py` (the nonce refusal, and the WS origin
refusal, whose phrase interpolates a caller-supplied `Origin`) went with it.
Full detail in `docs/OFFICE_AS_INTERFACE.md ## 396.`

**Two claims in this document were wrong and are corrected here**, both under
"What is *not* on the blocker list": the first-run path did **not** work from
the tree in the order the README prints it, and `Start-CafresoHQ.sh` was not
merely improving on "the 500 page" — there was no 500 page. `README.md:65`'s
own "hq.html is 500 until dist-ui/ exists" was false for the same reason.

### What a beta tester CANNOT self-serve

These are not code fixes. They are the list of things a stranger will need a
human for, and they should go in the invitation rather than be discovered.

1. **A brain.** The default office has none. There is no bundled model, no
   trial key, and no first-run screen that hands the tester one. They must
   either install the `hermes` CLI and let it start a gateway, or run LM
   Studio / Ollama locally, or bring their own API key. Until one of those is
   true, every message fails. **This is the largest single beta-blocker on the
   path and it is a product decision, not a bug.** Whoever sends the invitation
   has to answer "what do I type my first message *to*" in the invitation
   itself. (The trailing clause here used to read "— after fifteen seconds of
   silence." `## 399.` measured that at 46.5 seconds, made it 25ms, and gave it
   a sentence that names Settings → Connections. The brain is still missing;
   only the wait and the wording were ever fixable in code.)
2. **Node.js 18+ and Python 3.** Still not bundled — that part stands, and no
   page in the product can install an interpreter. But "not checked for" was
   true when this was written and is not true now: `## 405.` walked it and
   both are checked. See that entry's note at the top of this document for
   what was measured; in short, `npm install` now refuses an under-floor Node
   naming Required and Actual, the build script refuses one itself, and
   `Start-CafresoHQ.sh` checks `python3` before it does any work. Python 3
   turned out to be the weaker half of the worry: serve.py parses back to 3.6
   and was driven green on stock macOS `/usr/bin/python3` (3.9.6) as well as
   3.14.6.
3. **Any hosted / ICP path at all.** A local office touches no canister and
   needs no identity, and that is the path to hand a tester. The hosted face
   needs a mainnet action, and a mainnet action is the user's alone — no
   session in this loop may make one. Consequently nothing about the hosted
   first run, Internet Identity sign-in, or per-user container provisioning
   has been walked by any pass of this document, including this one. **If the
   beta is meant to be hosted rather than local, this document does not yet
   cover its first-run path.**
4. **Internet Identity configuration.** Out of scope by policy for this loop —
   `derivationOrigin` and the anchor whitelist are not to be touched or
   changed by an agent. Any II-related first-run failure needs a human.
5. **Cycles.** Unchanged from gate 3 below: `cafresohq_state` has no auto
   top-up and has already been wiped once, on 2026-08-05. A hosted beta that
   outlives its balance loses its testers' data, exactly once.
6. **`mkcert`, for a warning-free HTTPS embed.** Optional, and the clause
   this item used to carry — "serve.py falls back to a self-signed cert" —
   was **false**, corrected by `## 405.` after driving a cold tree with no
   mkcert installed: the office came up on `http://localhost:8811/hq.html`,
   plain HTTP, no cert at all. `_ensure_local_tls` is called with
   `allow_selfsigned=_tls_forced` and that flag is only set by
   `CAFRESOHQ_TLS_AUTO=1`; the reason is written at the call site (a TLS-only
   server with a cert the browser rejects is *unreachable*, which is worse
   than HTTP, and `http://localhost` is already a secure context). So HTTP is
   the honest default and mkcert is the only route to HTTPS — a tester who
   wants the `ai.cafreso.com` embed or the iOS service worker has to install
   a third-party tool first, and one who was told to expect a self-signed
   cert went looking for a warning that never comes. `Start-CafresoHQ.sh`
   carried the same false sentence and now says the true one.
7. **The standalone search worker.** A separate `docker compose` and a Brave
   key. The 502 says so clearly, which is the right behaviour; it is still a
   thing the tester cannot produce on their own. `## 405.` walked the setup
   path up to the point where it becomes a mainnet action and found it did
   not lead anywhere: `docker-compose.worker.yml` declares
   `env_file: worker-standalone.env`, that name is gitignored, and the fresh
   clone had **no template for it and none for `worker.env` either** — so the
   first command in `search_worker_service/README.md` aborted on Compose's
   own words about a missing env file. Worse, that README named `worker.env`
   for the compose path, which is the *other* compose file's env file and the
   one thing the command will never read. Both env files now have committed
   `.example` templates and the README names the right one. What remains is
   genuinely a human gate: `WORKER_PRINCIPAL`/`WORKER_SECRET` come from
   registering a worker in ai.cafreso.com's settings — a mainnet action — and
   `BRAVE_API_KEY` from a Brave account. No agent in this loop may make the
   first, so the worker was never *run* here; only its setup path was walked.

### Verdict delta

The second pass's verdict — shippable to an outside **local** beta tester —
survives, but it was resting on an untrue sentence about the first-run path,
and one of the two "cheap fixes before the invitation goes out" it named
should now be three: the LAN URL, the fifteen seconds of silence, and a
sentence in the invitation naming which brain to install. `## 396.` closed the
one that was a genuine dead end.

---

**2026-09-05 (third pass, status update — not a re-audit).** The second pass
below (verified against `#336`/`#337`, verdict: *"shippable to an outside beta
tester today"*) still stands; nothing here changes that verdict. This is a
progress note from the coordinator running the standing bug-hunt loop, current
through `## 380.` (`a4bb342`).

Since `#337`, roughly 44 more numbered fixes landed (`#338`–`#380`, a handful of
ledger numbers reserved-then-skipped for relaunched agent work). None of them
touch the security-posture findings the second pass measured — that surface
hasn't moved. What they closed instead is a different, quieter reliability
class this session ran down methodically:

- **Stale-snapshot component state** (`#374`–`#378`): five real bugs where a
  panel/modal captured a coworker, task, or meeting-roster object once at open
  time instead of re-reading it live — Settings edits made while the panel
  stayed open (model, tools, color) silently never reached it. Swept until a
  dedicated hunt for more instances came back clean.
- **`useFileStored` hydration races** (`#379`, `#380`): two stores (the
  approvals/receipts audit trail, and the coworker job/résumé ledger) could
  have their entire on-disk history silently discarded and overwritten if a
  new entry was recorded in the ~100–300ms window before the file finished
  loading from disk on mount. Swept until every remaining `useFileStored` call
  site was checked and confirmed either safe or already correctly wired.
- Plus a scattering of one-off finds: a Night Shift permission gate that only
  covered vault *writes* and not reads/search (`#375`), a stale DM-roster
  closure surviving a boss-blocking confirm dialog (`#376`), and a duplicate
  chat escalation on every page reload (`#374`).

Full suite as of `## 380.`: **555/556 suites pass.** The sole failure is the
same one this document has named at every prior pass —
`test_worker_payout_sweep_does_not_wipe_mid_sweep_accrual.py`, blocked on
`moc`'s `M0219` diagnostics against a foreign session's uncommitted
`src/cafresohq_state/main.mo`, which this session may read and must not touch.

The four gates listed near the end of this document (the `main.mo` migration,
any mainnet action, cycles auto-top-up, and the nine unauthorized MCP
connectors) are unchanged and remain true today — none of the 44 fixes above
were in a position to close any of them, since none are within this session's
authority to touch.

**Reading this update alongside the second pass:** the second pass answered
"is it safe to hand to a stranger," and the answer there hasn't moved. This
update answers "has anything rotted since," and the answer is no — the app has
gotten more internally consistent (fewer places where the UI quietly lies about
current state), not less safe. Nothing below this line has been re-verified
against today's commit; it is preserved as the second pass's own record.

---

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

Startup banner on `python3 serve.py` (run here with `PORT=8974` to sidestep an
already-occupied port — **the default port is 8787**, `serve.py:59`):

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

### 5. A missing brain costs fifteen silent seconds before the error — ✅ FIXED

> **Resolved by `## 399.`, and the number below is an undercount.** The browser
> retries a 502 three times, so the tester's real wait was **46.5s**, not 15s.
> `_hermes_proxy` now distinguishes a gateway that is restarting from a machine
> that has no hermes at all and answers the second case in 25ms with a written
> sentence naming Settings → Connections. The finding below is kept as the
> record of what was measured then; its closing line ("the residue is the
> fifteen seconds of silence") no longer holds.

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

### 6. `/gap/status` and `/news/status` are readable cross-origin — ✅ FIXED

> **Resolved.** `/gap/` and `/news/` are now literal members of
> `_HOST_DATA_PREFIXES` (`serve.py`), so a foreign Origin gets no ACAO header at
> all. Re-measured on a live local instance: `GET /gap/status` with
> `Origin: https://evil.example` returns **no** `Access-Control-Allow-Origin`.
> The finding below is kept as the record of what was measured then.

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

  > **Corrected by the fourth pass (`## 396.`).** This bullet was measured only
  > in the right order, on a tree that had been built. Run in the wrong order —
  > or after a build that failed part-way — `hq.html` did not serve a 500 page
  > for `Start-CafresoHQ.sh` to improve upon: it served **nothing**, closing
  > the connection mid-`send_error` on a latin-1 encode of its own advisory
  > sentence. The claim above is true of the happy path and was false of the
  > one a stranger is most likely to take. Fixed; see the fourth pass at the
  > top of this document.
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

> **The second of those two is closed (`## 399.`)** — it was 46.5 seconds, not
> fifteen, and it is now 25ms with a sentence that names the room. The LAN URL
> stands. And "costs a tester nothing but patience" was the wrong reading of it:
> what the missing brain cost was the whole first impression.

Send the invitation.

---

## Durability: what a tester loses when the office restarts (`## 408.`, 2026-09-05)

Measured, not derived — the real `useFileStored` driven headlessly against a
real `python3 serve.py`, thirteen file-backed stores, three events each.
`hq-state/` is gitignored, so `git status --short hq-state/` proves nothing;
these are round trips.

| what the office holds | (a) reload | (b) `serve.py` restart | (c) fresh origin / cleared data |
|---|---|---|---|
| tasks, missions, workflows, projects, meetings, pins, receipts, experience, messages, activity, windows, roster, office memory | survives | survives | survives |
| the Library (`hq-state/vault/`) | survives | survives | survives |
| **the conversation (`chat`)** | survives | survives | **LOST** |
| **saved workspaces** | survives | survives | **LOST** |
| theme / density / read-marks / onboarding flags | survives | survives | lost (correct) |
| **half-typed message in the composer** | **LOST** | **LOST** | **LOST** |
| approvals, install jobs, night locks, market cache, PTY sessions | survives | **LOST — correct** | survives |

### Closed by `## 408.`

An edit made while the office was down (restart, crash, sleeping laptop) had
its PUT refused, lived on in `localStorage` — and then the **reload deleted
it**, because a freshly reloaded tab is neither dirty nor touched and the
mount fetch adopted the stale file over it. The only warning was a toast on
the page the reload destroyed. Now a `<key>::unpaid` note survives the reload,
the mount reads it as "local is ahead", and disk is healed. Guarded by
`scripts/test_an_edit_made_while_the_office_was_down_is_not_deleted.py`.

### New beta gates

1. **The conversation is not file-backed.** `app.jsx:189` uses `useStored`,
   so there is no `hq-state/chat.json`. A tester on a second browser or a
   cleared cache keeps everything except every conversation they have had.
   This is the largest remaining gap on the map and should close before the
   invitation goes out to anyone likely to use two devices.
2. **There is no export-all and no restore.** The whole map above is one
   `hq-state/` directory on one laptop. A tester who loses it loses
   everything, and nothing in the product tells them that or offers a way to
   take a copy.
3. Saved workspaces (`app.jsx:619`) and the composer draft (`ui/chat.jsx:90`)
   are the two smaller losses, in that order.

# The Office as Interface — design system for the non-guru

> **Status:** Design doc · 2026-08-05 · implements North Star §3.2/§3.6
> (`strategy/08-north-star-real-product.md`).
> **Builds on** `OFFICE_REVAMP.md` (the continuous floor) and `LIVING_FLOOR.md`
> (desktop mode) — those cover how the office *renders*; this covers how it
> *teaches*. Scope: the metaphor as onboarding + UX for people who will never
> open a terminal, and the copy/animation rules that keep it honest.
>
> ✅ **Rendering replaced 2026-08-06 — "Pixel HQ."** The DOM/CSS cross-section
> floor (`OFFICE_REVAMP.md`/`LIVING_FLOOR.md`) is retired; `ui/office.jsx`
> now renders a GBA-era pixel-art building cutaway — sky/skyline backdrop,
> rooftop "CAFRESO HQ" sign, CEO penthouse, agent floors (two rooms per
> storey), vacant-desk floor, vault, lobby, and a Japan-town street with an
> ambient dog patrol. Assets are hand-authored ASCII pixel specs machine-
> rendered to PNG by `scripts/gen_pixel_hq.py` (pure stdlib, no Pillow/sips —
> deterministic, re-runnable). Original art only: no Nintendo/Game Freak
> assets, names, or trade dress — era-authentic grammar (16×24 characters,
> blue-black outlines, dialog-box speech bubbles), not a copy. Every §4
> event→animation beat and every live surface (desk screens, tool placards,
> the asking-visitor, Night Shift board, P&L/Situation HUD, tip rain, vault
> balances) carried over 1:1 — this is a re-skin of real wiring, not a mockup.
> This is a full replacement, not a selectable theme: the old room-card
> rendering is gone.
>
> ✅ **§4's prop walk is a real walk (2026-08-06).** It was a teleport: the
> code unmounted the coworker and hung a sign reading "at the bookshelf".
> Now `deskKit()` puts the furniture in the room (from `agent.tools`, the
> capability actually granted) and the coworker crosses to it. Binding
> invariant: the **transit is a fixed 0.8s; the standing-at-the-prop state
> lasts the real tool duration**. Never scale the walk to the call — a 40s
> tool must not produce a 40s stroll, or the animation starts reporting
> effort as distance. Placards now appear only for meeting / water-cooler /
> asking-the-boss, where the coworker genuinely IS off the floor.

> ✅ **Vacant units are rooms, not gaps (2026-08-06).** Unhired slots used
> to render as one full-width band of flat `#4c4658` rectangles below the
> tower — so the building changed shape halfway down, and since
> `INITIAL_AGENTS` is empty that band was the majority of what a first-run
> boss ever saw. Vacancies now flow through the same two-per-storey
> sequence as leased rooms: same wall, same floorboards, same window,
> unfurnished and drained of warmth. **A vacant unit keeps its unlit pane
> at night** rather than swapping to the lamplit `window_night` art — the
> night swap is a time-of-day cue everywhere else, but in an empty room it
> would be an occupancy claim. Nothing in the room is earned state: no
> desk, no props, and the nameplate pip stays grey.

> ✅ **The mug says what it did (2026-08-06).** Coffee clears a coworker's
> context *and* kills whatever they were mid-way through, and reported both
> identically ("Cleared X's context") with no sign at the desk at all. The
> toast now distinguishes the two (`abortAgentRun` returns whether anything
> was in flight), and a one-shot steam beat plays at the mug. Not
> `ambientOk`-gated — like `trayDrop`, it reports a real state change the
> boss just caused, so reduced-motion gets the still cue rather than none.
> It also stopped parking `task: 'freshly caffeinated'` on the agent: `task`
> is "what they're working on", and an idle coworker's bubble must not
> claim a job that doesn't exist.

> ✅ **A hire lands for everyone (2026-08-06).** The only floor feedback on
> the biggest state change in the product was the lobby walk-in, and that
> is `ambientOk`-gated — so mobile and reduced-motion bosses watched a room
> appear from nowhere with no cue that it was theirs. The **room** now
> marks itself just-leased for ~2.6s (lights coming up, plate turns gold,
> `MOVED IN` on the nameplate), ungated, on the `trayDrop` principle: this
> reports real state, it doesn't decorate. The lobby **walk** stays gated —
> that one genuinely is ambient. The tag pops rather than blinks: a blink
> is a 50% duty cycle, so a label carrying the message would be unreadable
> half the time it exists (the same trap the eye-blink fell into).

> ✅ **Scenery hides on mobile; instruments don't (2026-08-06).** The narrow
> viewport rule swept the **LIVE lamp** and the **Situation Wall** into the
> same `display: none` list as the clouds, the skyline and the dog. Those
> two are not scenery — they are the only answers to "is my business
> working right now?" and "is the container even up?", so a phone had no
> way to tell a running office from a dead one. Both render everywhere now;
> the wall lays out as a strip above the tower instead of a box floating
> over it. **The Agent P&L stays desktop-only** on purpose: its rows are
> `nowrap` three-figure money lines, and truncating money is worse than
> deferring it to the Team tab.
>
> Rule of thumb for that media query: if hiding it loses the user a *fact*,
> it is an instrument — re-lay it out, don't drop it.

> ✅ **The floor is keyboard-operable (2026-08-06).** Measured before
> touching anything: **19 clickable surfaces, exactly 1 keyboard-reachable**
> — and that one an `<a href>` by accident. Hire, open a file, read the
> reports, take a delivery, sit with the CEO, answer an approval: none of it
> could be done without a mouse, on the product's primary surface. Now 15
> labelled controls, 0 unlabelled.
>
> `pressable(onActivate, label)` gives a prop `role` + `tabIndex` +
> Enter/Space and an `aria-label` in office words. Two constraints it
> encodes: the focus ring is an **`outline`**, never a border or padding —
> half these props carry centring transforms and a layout change on focus
> would make the room jump — and it **stops propagation** the same way the
> click handlers do, so activating the mug can't also open the room behind
> it. `:focus-visible` means a mouse user never sees the ring.
>
> An occupied room is `role="group"`, not a button — it *contains* buttons,
> and nesting them is invalid. Its **door plate** is the focusable control
> that opens the coworker's file, which is also a better affordance than a
> whole-room hit target that only mouse users could ever discover.

> ✅ **…and so can the rest of the app (2026-08-06).** Re-running the same
> census outside the office turned up something worse than the floor: the
> **navigation rail** is nine `<a>` tags with **no `href`**, so Office /
> Tasks / Calendar / Memory / Vault / Team / Terminal / Workspace /
> Settings were *all* unreachable by keyboard. Not a corner of the product
> — its primary navigation. Also fixed: the Situation Wall's SEARCH row
> (the one instrument you can *act* on — it re-probes the search network)
> and the keyboard-shortcuts button, which was itself mouse-only.
>
> Census now: 74 click handlers, 3 unreachable — and all three are the
> `role="group"` rooms, which is the intended design, not a gap.
>
> Method note: a naive "has onclick but isn't focusable" scan reports
> `#root` as a violation. That is React's delegated listener, not a
> control. Check the handler before believing the count.

> ✅ **The event→floor wire is one table (2026-08-06).** §4's mapping was
> real but its *transport* was not: six event names as raw string literals
> at ~30 sites across 10 files. A typo in one is the worst kind of bug this
> layer can have — **nothing throws, nothing warns, the beat simply never
> plays**. (`cafresohq:coffee` was added exactly that way: by hand, twice,
> in two files.) `FLOOR_EVENT` / `floorEmit` / `floorOn` in `app/floor.jsx`
> now own the six names, with 11 checks in `scripts/test_floor.py`.
>
> Two rules the emitter enforces, both learned from this layer's failure
> mode. An **unknown kind throws** — a typo must be loud, not silent. And
> an event with **no agent id is refused with one warning**: every floor
> beat is *about* a coworker, so without an id the office has no room to
> play it in and would drop it anyway; the warning names the site that got
> it wrong instead of leaving a dead animation to be discovered by eye.
>
> Note for anyone verifying this: the artifact beat correctly does nothing
> on a floor with no filed deliveries — the out-tray only renders once a
> real artifact exists, so there is no prop to animate. Absence of the
> animation is not absence of the wire.

> ✅ **What one real failed run taught us (2026-08-06).** Everything above
> was verified with synthetic events. Dispatching an actual message to a
> coworker with no brain configured — a genuine round trip, failing
> locally at no cost — found two things no synthetic test had:
>
> 1. **The rooftop lamp was dark for the entire run.** `anyLive` counted
>    tool calls and open streams, both *event*-driven, so nothing lit
>    between dispatch and first token — the room read `status-busy` while
>    the building claimed nothing was happening. `agent.status` is the
>    authoritative answer to "is anyone working" and now sits alongside the
>    events. (Third pass on this one definition. It keeps drifting because
>    the events are the tempting signal and the status is the true one.)
> 2. **The snag bubble was still a log line.** It read *"hit a snag —
>    OpenRouter 503: error : openrouter: no API key configured"*: a status
>    code, a provider name, a doubled `error :`, and a §6-banned term, on
>    the floor. `SNAG_CAUSES` maps identifiable failures to one office
>    sentence that also says what to do. **Unrecognised causes still fall
>    through to the cleaned raw line** — a confident wrong diagnosis is
>    worse than a vague honest one — and `detail` keeps the raw text for
>    the inspect panel, per §7.
>
> The attention inbox was rendering the same failure as *"unknown: Inspect
> error and retry"* — `classify()`'s developer strings straight through. It
> now uses the same `snagSentence`, so the inbox and the floor tell one
> story in one voice. `classify()`'s structured `kind`/`retryable` stay:
> escalation reads them, users never do.
>
> **Two existing assertions in `test_floor.py` changed** — they fed inputs
> (`code: 429`, `: 502`) that the table now classifies, and asserted the
> raw content *survived*. That was the old contract. Keeping "502" in a
> speech bubble is the thing §7 forbids; the cleanup path is still covered,
> with causes the table cannot identify.

> ✅ **Stopping a coworker is not their failure (2026-08-06).** Running the
> coffee-abort against a real in-flight run — the path made *honest* two
> commits earlier but never actually exercised — found three linked bugs:
>
> 1. **The stop took 6.0 seconds to appear.** `onCoffee` cleared mood and
>    task but not `status`, so the room kept its busy plate (and, since
>    `anyLive` reads status, the building kept its LIVE lamp) until the
>    aborted request unwound. A stop the boss commanded is true the moment
>    they command it; we do not need the network's permission to say so.
>    Now ~1s, which is the measurement's own granularity.
> 2. **The retry layer swallowed the cancellation.** Aborting during a
>    backoff sleep fell out of the loop and threw the *last network error*,
>    so `err.name === 'AbortError'` was false and the run was recorded as a
>    failure: **"hit a snag — request failed after retries" on a coworker
>    the boss had simply stopped.** §5's ledger rule ("a run the USER
>    stopped is not the coworker's failure", which would otherwise reset
>    their streak) could not be honoured, because the information was
>    already destroyed one layer down. The loop now throws a real
>    `AbortError`, and its backoff wakes on abort instead of sleeping out.
> 3. **`err.name` was the only abort signal.** All three catch sites now
>    also trust `controller.signal.aborted`, which no re-wrapping can lose.
>
> Verified after: stop visible in ~1s, and once the aborted request fully
> unwinds the room is idle with **no bubble** and the log reads `run
> stopped` — no `failed` row. A genuine failure still snags normally.

> ✅ **The stand-up speaks office too (2026-08-06).** Ran a real meeting.
> The floor half is sound — measured the participants walking to the room
> (2 walkers, 1.0s→8s) and their desks holding the "in the meeting room"
> placard for the whole meeting, exactly the §4 split between a fixed
> transit and a real-duration away state. Two things were not:
>
> - **The transcript dumped raw JSON.** Each failed turn read `⚠ OpenRouter
>   503: {"error": "openrouter: no API key configured"}` — §7's raw dump
>   and a §6-banned term, on a user surface. The floor already had one
>   honest sentence for exactly this failure; the meeting room just never
>   used it. It uses `snagSentence` now, both for participants and for the
>   moderator's synthesis.
> - **The building went dark during a stand-up.** `moderate()` streams
>   directly and touched no floor state, so a boss watching the office saw
>   nothing while the whole team was mid-round. Participant turns now emit
>   the `screen` event as they stream.
>
> That last change exposed a latent bug worth recording: the screen
> listener guarded on `!d.tail`, so **a caller closing its monitor — which
> by definition has nothing left to show — was dropped**, and the desk kept
> a stale monitor lit until the 60s backstop swept it. A terminal event
> with no tail now closes the monitor immediately.
>
> ~~⬜ Still open: the meeting's dispatch→first-token window shows no
> work…~~ ✅ **Closed same day.** `onUpdateAgent` is threaded through to
> `MeetingRoom`, and each participant is marked `busy` for the **whole
> turn** — set before the stream opens, cleared in `finally` so a failed or
> stopped turn can never strand them. Measured across a real round: busy
> and the rooftop lamp both run ~1s→~12s covering both turns, and both are
> clean at the end.
>
> The general rule, now three surfaces deep: **work starts when it is
> dispatched, not when the first token lands.** Event-driven signals
> (`tool`, `screen`) can only ever report the second, so anything that
> wants to answer "is this coworker working right now" has to read
> `status`. Every new run path needs to set it.

---

## 1. The principle: the metaphor does the teaching

Every AI concept a newcomer finds alien gets a physical counterpart they
already understand from any workplace. We never *explain* the concept; the
office layout and the coworkers' behavior demonstrate it. This is the whole
accessibility strategy — not tooltips, not a tutorial video.

| AI concept | Office counterpart | Where it lives |
|---|---|---|
| Model / agent runtime | **A coworker** with visible strengths | roster + floor |
| Connecting a backend / auth | **Hiring** ("we found your Claude subscription — want them on the team?") | front desk |
| System prompt / persona | **Job description** (editable, plain language) | coworker card |
| Context / workspace dir | **Their desk** — what's on it is what they know | desk view |
| Multi-agent planning | **The meeting room** (already a floor destination) | meeting table |
| E2E vault | **The filing cabinet** — visibly locked; only you have the key | vault |
| Scheduled missions / night_runner | **The Night Shift board** (bulletin board) | missions |
| Tool-use approval | **Coworker walks to YOUR desk and asks** | approval flow |
| Logs / traces | **Watching them work** (animation = trace viewer) | floor |
| Tokens / usage / cost | **Payroll** | payroll ledger |
| Artifacts / outputs | **The out-tray**, filed to the cabinet | desk → vault |
| Model catalog / marketplace (Phase C) | **The hiring pool** — candidates with résumés | hiring board |

**Rule:** if a feature can't be mapped to something in a real office, that's a
smell it doesn't belong in the newcomer path (it may still belong behind the
Living Floor's desktop-mode door for power users).

## 2. The cast

Coworkers are the product's characters — the roster mechanic (a team of
distinct helpers with different strengths, collect the ones you need) is what
makes model-agnosticism *legible*. Each hireable coworker gets a card:

- **Sprite + name** — ours, consistent with the existing 16×16 office art.
  The vendor appears as a small, honest "powered by Claude / Gemini / GPT /
  local GPU" chip — never as the coworker's identity. (Vendors change; your
  coworker persists. This also keeps rebadging drivers trivial.)
- **Stat bars (4, no more):** Speed · Depth · Code · Cost. Derived from the
  driver manifest's costHint + model class; honest and relative, not
  benchmark cosplay.
- **Specialty tag:** one line ("great with research briefs", "ships small
  sites", "cheap and tireless" for local models).
- **Job description:** the persona, in plain prose, editable in place. This IS
  the system prompt — we just never call it that.
- **Experience:** jobs completed, current streak (see §5).

Tone guardrails: **corporate HQ with heart** — warm, professional, a little
playful. Not childish, no baby-talk, no fake enthusiasm in copy. The office is
charming; the coworkers are competent.

> ✅ **Card shipped 2026-08-06 (Phase B1)** — `app/cast.jsx` + the inspect
> panel. Powered-by chip from the model id's shape (unknown vendor → NO chip,
> never a wrong brand; local daemons say "your hardware"). The four bars are
> a small model-CLASS table (1..4, first match wins through driver prefixes)
> — coarse colleague-judgements, exactly not benchmark cosplay — with Cost
> reading as value (4 = costs nothing extra; payroll shows real numbers).
> Specialty: an EARNED XP affinity ("2 drafts") beats the class tagline
> ("cheap and tireless"). Job description edits in place, saves on blur; the
> panel now mounts only while open so an abandoned draft can't resurface
> looking saved. Covered by `scripts/test_cast.py`.

## 3. First run — five minutes to first delight

The protected front door (North Star §3.6). No settings pages, no model IDs,
no keys pasted in this path.

1. **Walk in.** The front desk greets you; behind it, the office floor is
   visibly alive (trial brain doing ambient work). One sentence of promise, no
   feature tour.
2. **"Here's who we can hire today."** Driver `detect()` runs (existing
   `_agent_auth_detect` machinery): found subscriptions/CLIs/local daemons
   appear as candidates — *"We found your Claude subscription"*. Nothing
   found → the trial brain is already at a desk, pre-hired.
3. **Hire one.** One click; the sprite walks in, sits at a desk. (First
   micro-delight — target < 60 seconds from landing.)
4. **Pick a starter task.** Three cards, real outcomes, zero blank-prompt
   anxiety. Free-text exists but is not the star.
   > ✅ **Shipped 2026-08-05** — `modals/starter.jsx`. The sheet opens 1.4 s
   > after the first hire (long enough that the walk-in is what you watch
   > first) and only for a genuinely empty HQ. Cards: *Research brief* ·
   > *First draft* · *Simple page* — each asks for ONE subject, then mints a
   > normal task and sends it down the same path as dragging a card onto a
   > desk, so activity logging and checklist steps 4/6 come free. The same
   > cards fill the task board's empty inbox (there they land unassigned, so
   > the drag-to-a-desk mechanic still gets taught).
   >
   > *Digest ("summarize these files into my vault") is deliberately not in
   > the set:* a fresh HQ has an empty vault, and none of the front-desk
   > hires claim `vault` access, so the card would promise a deliverable it
   > can't file. For the same reason each brief adapts — it only says "save
   > it to Research/…" when that coworker actually holds vault access, and
   > otherwise asks for the deliverable in the reply. Revisit once filing to
   > the cabinet (step 6) is wired for every hire.
5. **Watch the work.** The animation layer (§4) plays the task honestly.
   If the task needs a permission, the coworker walks over and asks — the
   user's first approval is diegetic, not a modal ambush.
6. **The artifact lands.** Out-tray → filing cabinet, with an open sheet.
   First delight + the trust story in one beat.
   > ✅ **Shipped 2026-08-05** — `app/artifacts.jsx` + `modals/delivery.jsx`.
   > When a TASK completes, the host files the deliverable to the vault
   > (`Research/` · `Drafts/` · `Sites/` by starter card, else
   > `Deliveries/`), the desk grows an out-tray that plays a one-shot drop
   > and opens the latest artifact on click, and the first delivery ever
   > gets a sheet with the path and an "Open it" that lands in the cabinet.
   >
   > **Filing is host-side, not a `[VAULT_NEW:…]` the agent emits.** No
   > front-desk hire claims `vault` in its tools, so they *cannot* emit it —
   > and the small local models a zero-config user is likeliest to hire are
   > exactly the ones that would forget. The office files the out-tray; the
   > coworker only has to finish the work. Deliverables are also swept of
   > stray tool markers first (a file that opens on `[Vault_APPEND: …]` is
   > not a deliverable) — narrowly, so prose, `[x]` checkboxes and
   > `[Customer Name]` placeholders survive. Covered by
   > `scripts/test_artifacts.py`.
   >
   > **The trust line is conditional, and that is the point.** "The cabinet
   > is encrypted — only you can open it" is true only when HQ is framed by
   > the shell that holds the user's identity and does the vetKeys work
   > (`VaultBridge.isAvailable()`). A self-hosted vault is an ordinary
   > folder, and the sheet says so instead. §4 forbids the animation layer
   > from lying; a claim about *security* is the last place to start.
   >
   > ~~Deferred: **share**.~~ ✅ **Shipped 2026-08-06 with Ship-to-chain**
   > (`DRIVER_CONTRACT.md` §7): PAGE deliverables get a "Share it live"
   > button on the delivery sheet — `sharePage()` publishes the .html note
   > to the public HQ host, tip jar riding along. Pages only (a brief or a
   > draft is a private note, not a site), and only when the II-holding
   > shell is present — no shell → no button, never a localhost link
   > dressed up as "shared". The user's click is the approval;
   > agent-initiated publishes (`[PUBLISH_SITE:…]`) instead queue one
   > boss stamp and the coworker walks over to ask (§4).
   > Only task completions file — a chat reply or a DM is not an artifact.

Exit test (from the North Star): a non-developer stranger completes this
unaided in under five minutes.

## 4. Show-the-work: event → animation mapping

The driver contract's event stream (`DRIVER_CONTRACT.md` §1.3) is the
animation API. One mapping, every backend, including future hired network
agents:

| event | sprite behavior |
|---|---|
| `status: thinking` | sits, thought bubble |
| `token` | typing at the desk (monitor glow) |
| `tool_call` (auto-approved) | walks to the relevant prop — cabinet = file read, bookshelf = Library/search, phone = web fetch |
| `tool_call` (needs approval) | **walks to the user's desk, waits with a speech bubble** |
| `tool_result` | returns to desk |
| `artifact` | carries a document to the out-tray |
| `usage` | (silent — feeds payroll) |
| `error` | scratches head, "hit a snag" bubble with one honest sentence |
| `done` | stretches, files the result, back to idle |

Rules: animations must be **honest** (never play "working" when the driver is
erroring), **interruptible** (a tap on the sprite opens the live task detail
for anyone who does want the text stream), and **cheap** (reuse the existing
walker/commute system from `OFFICE_REVAMP.md`; no per-event new tech).

> ✅ **Shipped 2026-08-06** — the table above is now fully wired.
> `app/floor.jsx` holds the pure mapping (covered by
> `scripts/test_floor.py`); the floor renders it with the away-placard
> language the meeting/cooler states already spoke — no new animation tech.
>
> - **tool_call → prop walk:** the tool name decides the prop (search →
>   bookshelf, web → phone, files/vault/memory → cabinet; search WINS over
>   storage, so `VAULT_SEARCH` is a bookshelf trip). Unmappable tools stay
>   at the desk with the tool chip. `tool_result`/`done` walks them back
>   (the 1.6 s linger the monitor glow already used). Real state — not
>   ambientOk-gated, and the placard survives mobile.
> - **needs-approval → walks to YOUR desk:** any pending approval carrying
>   an `agentId` stands that coworker at the boss desk with the ask in a
>   speech bubble ("<name> asks: …", click answers it) while their own desk
>   shows "at your desk, asking". External CLI approvals
>   (`/approvals/external`) now carry `agentId` when the asking agent's
>   name matches a floor coworker — a CLI tool-use request walks the same
>   walk instead of living only in the tray. This also ships §3 step 5's
>   diegetic-approval beat.
> - **error → one honest sentence:** failed runs set a "hit a snag — …"
>   bubble via `snagSentence()` (first line only, URLs/JSON shrapnel
>   stripped, ~90 chars — the full dump stays in the inspect panel, §7).
>   A run the USER stopped clears the bubble instead: taking the folder
>   back is not the coworker's failure.
> - **The honesty fix that motivated the beat:** run paths now close the
>   desk monitor on failure (`makeScreenEmitter.error()` → a brief red
>   `is-error` freeze, cleared in 2.5 s). Before this, a crashed run left
>   the monitor in its live "working" flicker for the full 60 s safety
>   sweep — exactly what the rule above forbids.
> - **done → stretch:** a one-shot scaleY stretch composed WITH the bob
>   (a lone animation would freeze the sway for as long as the mood
>   lingers), then back to idle. Reduced-motion drops it.

## 5. Experience & the résumé (Phase B → C bridge)

Each completed task increments the coworker's visible experience: jobs
completed, streaks, specialty affinity ("12 research briefs"). Phase B value:
attachment and legibility ("Mira's done all my briefs"). Phase C value: the
same numbers become the **on-chain résumé ledger** for marketplace agents —
jobs completed, re-hire rate, disputes — the trust signal that makes hiring a
stranger's agent feel like reading a CV instead of gambling on a GPU. Design
the XP counters now with that continuity in mind (per-agent, per-task-type,
append-only).

> ✅ **Shipped 2026-08-05** — `app/experience.jsx`, an append-only ledger of
> `{at, agentId, kind, outcome, taskId, title}` entries persisted alongside
> tasks (`state/experience`, so the résumé survives a browser wipe and a
> fire-and-re-hire — front-desk ids are stable). Derived, never stored:
> jobs completed, current streak, per-kind tallies, and the specialty line,
> shown on the roster card ("Jobs · 🔥") and the Performance-review panel.
>
> **What counts as a job:** a task completed — dropped on a desk or closed
> via `[TASK_DONE:…]` in chat — and a mission that ran its schedule (one
> night shift per mission, not per iteration). A chat reply or a DM is not
> a job, same as it is not an artifact (§3.6); the legacy `agent.tasksDone`
> counter counted those, which is why the cards no longer display it.
>
> **Honesty invariants:** a job completes once (`xpRecord` refuses a second
> 'done' for the same taskId — double-fire paths are safe by construction);
> a failed run is a snag and resets the streak, but a run the USER stopped
> is not recorded — taking the folder back is not the coworker's failure;
> the specialty label only appears once earned (≥ 2 of a real task type —
> generic jobs are never a "specialty"). Covered by
> `scripts/test_experience.py` (32 checks).

## 6. Jargon translation table (binding for all UI copy)

| Never say | Say |
|---|---|
| system prompt | job description |
| context window | memory span ("what fits on their desk") |
| tokens / usage | work done · payroll |
| model (as a selector) | coworker |
| temperature | (hidden; "creativity" dial behind Advanced if ever) |
| API key / OAuth | subscription / sign-in |
| agent runtime / backend / driver | (internal words — users see coworkers) |
| tool call | (shown as the action itself: "reading files", "searching") |
| inference / completion | working / answer |

> ✅ **Audited and enforced 2026-08-06.** The table had drifted where it
> mattered most — the coworker card and the Team card were printing
> `Tokens (session)`, `Cost`, and `Model: openrouter:google/gemma-3-27b-it`,
> and the Situation Wall's FUEL row said "tokens spent" *on the floor*,
> which this section names explicitly. Now: **Work done · Payroll · Brain**,
> with the raw id kept in the `title` so debugging doesn't lose it.
> `brainName()` (`app/cast.jsx`, 9 checks in `scripts/test_cast.py`) is
> **formatting only** — it drops the routing prefix, org path and tuning
> suffixes but never substitutes a different name, so a card can't claim a
> brain the coworker isn't running; no model at all reads "not set yet"
> rather than inventing a default. Renaming Cost → Payroll also un-collides
> it with the Cost *stat-bar*, which means the opposite thing (value, not
> spend). And the card's `☕ REFRESH CTX` button — jargon, and it zeroed the
> counter while leaving an in-flight run streaming — is now `☕ COFFEE
> BREAK` on the floor's own `onCoffee` handler: one gesture, one behaviour.
>
> Tooltips claim no unit. Token counts are not word counts, and "words read
> and written" would be a small lie told confidently.

> ✅ **Pass two — hiring and the door plate (2026-08-06).** Walking the
> actual first-run path (empty roster, the Job Postings sheet auto-opens)
> turned up the rest of it. The candidate cards printed prefix-stripped raw
> ids; they use `brainName()` now. Five front-desk roles read `Local Model ·
> your hardware` / `Cloud Model · your account` — model-as-selector in the
> very first sentence a new boss reads about their first hire — and are now
> plain job titles, with *where the brain runs* left to the powered-by chip
> and the found line, which already said it honestly.
>
> That `·` clause was also feeding the office **door plate**, which printed
> only the role's LAST word: hiring the local Llama produced a room labelled
> **"LLAMA · HARDWARE"**, and every coding agent read "· AGENT". The plate
> now prints the whole role and lets the existing ellipsis handle a long
> one — **truncation is honest; word-picking guesses.** Verified a
> pathological 57-character role clips with an ellipsis, stays inside the
> plate, and leaves the status pip visible.
>
> Last of it: "bring your own model / your own key" → "bring your own
> brain". *Brain* is already the product's word for it everywhere else
> (onboarding, `/health`, the welcome message) — this was drift, not a
> second concept.

Raw model IDs, JSON, and driver names may appear in desktop-mode surfaces and
settings — never on the floor, the cards, or onboarding.

## 7. What newcomers never see

- A terminal (Living Floor desktop mode keeps it, behind the door).
- A blank prompt box as the primary call to action.
- Vendor logos as coworker identities.
- Settings as a prerequisite to the first task.
- Raw error dumps — every failure is one honest sentence plus "try again /
  ask differently / pick another coworker."

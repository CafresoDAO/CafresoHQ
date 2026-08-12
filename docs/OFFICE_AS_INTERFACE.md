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

> ✅ **The Meeting Room's own layout was broken (2026-08-06).** Went back to
> run a real stand-up after the fixes above and the modal itself was
> unusable: the three seats (moderator + 2 attendees) rendered as a ~46×12px
> sliver at the top of the dialog, every seat pushed off the bottom, and the
> transcript log invisible. Cause: `.meeting-table` was defined TWICE in
> `styles.css` — once as this modal's real seat grid, once as a leftover
> decorative floor-nook sprite from an abandoned isometric-office concept
> that nothing in the codebase still built (`grep` for the class in every
> `.jsx` found exactly one caller: this modal). Same class name, later rule
> wins, so the modal's grid quietly inherited a 46×12px wood-table sprite's
> dimensions. The dead rule also sat in a `≤768px { display: none }` list —
> so on any phone-width viewport the seats didn't overflow, they vanished
> outright, a second bug from the same collision. Deleted the orphaned rule
> (plus its now-pointless `body.night` filter and the equally-orphaned
> `.floor-zone`/`.fz-meeting`/`.fz-kitchen`) and dropped `.meeting-table`
> from the mobile hide-list — the grid's own `auto-fit` already reflows to
> one column on narrow screens, no override needed.
>
> Verified live: reopened the room, all three seats render side by side
> with names/roles/remove buttons, ran a real round (2 fast OpenRouter
> snags + one slower Hermes 502-then-retry snag, ~35s), and every turn
> landed in a properly-sized, scrollable transcript in the same
> `snagSentence()` language as the floor and inbox. One event, one story,
> now on a fourth surface.

> ✅ **Sweep for the same bug everywhere else it could hide (2026-08-06).**
> Four fixed surfaces raised an obvious question — where else does a run
> failure still dump raw text? Ran the STAND-UP for the first time this
> session and found two more, immediately:
>
> - The pre-flight agent list printed the raw model id as a chip —
>   **`GOOGLE/GEMMA-3-27B-IT`** — the exact §6 violation `brainName()` was
>   built to fix on the coworker card, just never migrated to this call
>   site. Same fix: `brainName()`, formatting only.
> - Every reporting agent's failure read `⚠ OpenRouter 503: {"error":
>   "openrouter: no API key configured"}` verbatim — its own, separate,
>   never-fixed error path.
>
> `grep`ing the whole codebase for the shape of that second bug (`` `⚠
> ${err.message}` ``) found **five more live instances**, not one:
> the stand-up's own end-of-round synthesis, the CEO 1:1 chat panel (two
> separate implementations — `features.jsx` and `ui/chat.jsx` duplicate
> this logic), and Research Missions' both the chat notification AND the
> `lastError` field stored on the mission itself, which two more surfaces
> (the mission card, the receipts row) read back out raw. Seven call sites
> total, one bug, because nobody had grepped for it as a pattern before.
>
> `snagSentence`/`snagCause` already existed for exactly this (added two
> commits ago for this same reason) — every site now calls one of the two,
> chosen by whether the surface supplies its own subject ("Mission
> iteration failed — …") or needs the full sentence. Verified live: a
> real stand-up round now reads "hit a snag — that brain isn't signed in
> yet — …" from every agent and the synthesis step, and a real 1-minute
> research mission's card, chat note, and (by construction, same write
> path) the receipts row all read the same clause. Nothing here was a
> design decision that needed relitigating — it was one bug, copy-pasted
> by hand into new features seven times before anyone searched for it.
> All 12 suites green.

> ✅ **Second pass — the pattern search widened (2026-08-06).** Grepped
> more broadly (`err.message` in any shape, not just the one literal
> string) and found six more copies of the exact same mistake: every
> multi-@mention dispatch and DM/handoff failure path in `ui/chat.jsx`
> wrote `"(Miko bowed out: OpenRouter 503: {...})"` — a raw dump
> introducing itself as a system aside. Fixed all six with `snagCause()`
> (each line already supplies its own subject: "bowed out", "couldn't
> take the handoff"). Also found — and fixed — a stray instance of the
> exact anti-pattern §7 exists to prevent: `app.jsx`'s ship-to-chain
> failure note was calling `snagSentence(...).replace(/^hit a snag — /,
> '')` to get the bare clause, the same fragile regex-strip that produced
> the verbless inbox row two commits ago. Swapped for `snagCause()`
> directly — the function this whole thread built specifically so nobody
> has to do that again.
>
> Also checked and deliberately left alone: `hq-runtime.jsx`'s tool-call
> error banners (raw text fed back into the AGENT's own context so it can
> self-correct — a different audience, not the boss), and every raw
> `e.message` inside Vault/Terminal/Projects/IDE/Settings, which §6's own
> exception covers explicitly ("desktop-mode surfaces and settings").
> Not every raw string is the bug — only the ones a non-technical boss
> reads as the whole story.
>
> Live-verified five of six `ui/chat.jsx` sites is impractical — the
> multi-@mention `.catch()` only fires for exceptions `dispatchToAgent`
> doesn't already handle internally (confirmed live: two agents mentioned
> at once both resolved through the already-fixed per-agent bubble, no
> "bowed out" note at all — that path needs a genuinely unexpected throw,
> not an ordinary no-brain failure). Correctness here rests on the same
> `snagCause()` already proven live across seven other surfaces today,
> not a fresh repro. All 12 suites green.

> ✅ **The delegation loop, end to end (2026-08-06).** Drove the headline
> interaction — the banner's own "DROP TASK CARDS ON DESKS TO DELEGATE" —
> for the first time: starter card → real task → `dragover` lights the
> room's drop outline → drop delegates → the coworker goes busy with the
> real title in their bubble → snag → mood stuck, rooftop dark, `{kind:
> 'brief', outcome: 'snag'}` in the ledger, task back to `inbox` with
> `assignedTo` cleared. All correct.
>
> One gap: **a snagged task came back looking untouched.** Returning it to
> the inbox is right (it must stay re-delegatable), but the one surface
> where you decide what to do next said nothing, so the obvious next move
> was handing it straight back to the coworker it had just defeated. Both
> card surfaces now carry `⚠ Kenji hit a snag on this`, derived from the
> ledger — never stored, same rule as the rest of §5. It states a **fact,
> not a recommendation**: whether to retry, reword or reassign is the
> boss's call and we have no standing to guess. A let-go coworker leaves
> the fact intact and loses only the name ("someone since let go").
>
> Two things checked and found already honest, worth not "fixing": the
> dropdown assign path (the keyboard-reachable one) assigns **without**
> dispatching — so the room shows the task on the desk while staying
> `idle` with the rooftop dark, which is exactly right — and the marker
> correctly keeps naming the last real *attempt* rather than the latest
> assignment.

> ✅ **The office's buttons work in windowed mode (2026-08-06).** With 8
> real failures accumulated, the **⚠ "N need you" banner clicked into
> nothing.** Cause: in desktop/windowed mode `setActiveView` is a silent
> no-op — windows sit *over* the office wallpaper, so changing the
> wallpaper view changes nothing visible — and only the nav rail routed
> through `openOrRaise`. Every in-office navigation button was dead in
> that mode: the attention banner, the inbox tray's **Board →**, and the
> **memory cabinet** prop. The exact buttons that exist to be clicked in a
> moment of "something needs me".
>
> One verb now: `navTo(view)` — `openOrRaise` in desktop mode (with
> `'chat'` mapped to the chat panel's own switch, since chat is not a
> window view), `setActiveView` otherwise. Verified in windowed mode
> (banner → STAFF ROSTER window with the inbox open; Board → TASKS window;
> cabinet → MEMORY SHELF window) and at 375px (Board → switches the full
> view, zero windows). Rule for future buttons: **never call
> `setActiveView` directly from an office surface — go through `navTo`.**

---

## 0. Where this stands (read this first)

This document has grown a long chronological tail of ✅ notes — useful as a
record of *why* each rule exists, unusable as a map. This section is the map.
It is a **status summary, not a spec**; the sections below remain the spec.

### What has actually been driven, end to end

**Verified end to end, by driving the real app against a live local model:**

| loop | evidence |
|---|---|
| first run on a wiped install | front desk → hire → task → **▶ START** → delivery filed, zero §6 jargon in the hiring copy |
| work in → work out | task assigned → visit block → memo filed to `Deliveries/` with the local date and a Working footer |
| the cabinet | vault tree → note → editor + preview render the filed note |
| private memory | write → the index reaching the next prompt (captured off the wire) → read → the coworker answering from it |
| day 2 | the HQ Gazette summarises the night; **DELIVERABLES** counts filings, not receipts |
| the §7 route out actually works, 2026-08-07 | the blocked-START refusal names a fix — "turn them on in Settings → Roster" — and the whole round trip was walked: START disabled with Llama on `['web']` → Settings → Roster → per-coworker TOOLS grid → **Vault Notes** on → persisted as `['web','vault']` → back to the mission sheet, **START enabled**, with Nova still correctly annotated "(needs Web + Vault tools)". A refusal that names a cure is only honest if the cure exists |
| refusal, RE-VERIFIED 2026-08-07 | it did not hold, and a live run proved it: a research mission started on a coworker whose tools were `['web']`, ran to round 4, reported "Wrote 1" in its own transcript, and left `writes: null`, `folder: null` and no `Research/` directory. Disabling the `<option>` stops a tool-less coworker being CHOSEN; it never stopped one being the default already selected, and START only checked topic and agentId. START now checks `canDoMode` too — re-tested on the same path: topic filled, Llama selected, **START disabled**, with the Settings → Roster route still on screen |
| work in → work out, re-verified 2026-08-07 | after the reply-pipeline repairs: task created → assigned → **▶ START** → done in 10s → filed to `Deliveries/` reading "Yellow." and nothing else. Assignment and dispatch are deliberately separate; a task waits at ▶ START until the boss says go |
| no desk stays lit — audited, 2026-08-07 | the §4 lie is a coworker who looks busy after the run ended, so all six `agentStream` paths were walked for it. Clean: the three dispatch paths clear in `finally` via `endAgentRun`/`settleAfterRun`; the meeting turn resets status in `finally`; the stand-up never sets a status, so it has nothing to leave behind; the night shift calls `standDown` on every one of its three endings (deadline, error-limit, coworker removed). And `ceoBusy` is **derived** — `chat.some(m => m.from === 'ceo' && m.streaming)` — not a flag that can desync from what it describes |
| every stamp does something — audited, 2026-08-07 | an approval the boss can stamp that quietly does nothing is the worst dead end in the app. `onApprove`/`onReject` are symmetric: both drop the card, record a receipt, and post the decision into chat, so the kind-specific branches (publish, hire-agent, hire-assistant, grant-elevation, workflow-step) only ADD side effects. `awaiting stamp` has no branch and needs none — the stamp itself is the outcome, and it reaches the coworker as chat context on their next turn |
| section 3.4 watched on the floor, not in the ledger, 2026-08-08 | *"Sprites doing things ARE the trace viewer... a newcomer never opens a log"* is the accessibility strategy, and every previous check of it had read the ACTIVITY LEDGER instead — the log a newcomer is promised they'll never need. Watched the floor itself during a live run, sampling every 900ms: **1s–12s** the desk screen is lit (`lit=2`) and the desk line reads *"LLAMA · GENERALIST — write a short paragraph about…"* — what they are doing, in the boss's own words; **13s** the glow goes out the same tick the state turns `active/done` and the line becomes *"reporting back ✓"*. Honest in the section-4 sense: the glow tracks the run, it does not linger. Two failed attempts first, both mine and both instructive: at a narrow viewport the floor and composer are exclusive tabs so nothing was observable, and at 3.5s sampling llama3.1 finished a trivial prompt inside the first gap — I'd concluded "stayed idle" from a run that had already completed. Same lesson as the empty-bubble reads, mirrored: sample faster than the thing you are watching |
| **Phase A's exit test, run for real, 2026-08-08** | *"a non-developer stranger delegates a task in under five minutes"* (`08 §6`) — never actually measured until now. Wiped the state dir AND localStorage, started a clock, took the zero-config path a stranger would take (Ollama's llama3.1, no keys, nothing configured). Beats: **7s** page load → CEO greeting + honest brain report → candidate book opens itself; hire Llama from the front desk → **1 HIRED**, "Welcome aboard, Llama! I've set up a desk", starter sheet opens itself with *"FIRST ASSIGNMENT · Llama is at a desk"*; pick **First draft** → exactly one field ("What should Llama draft?") → **START**; **92 seconds** later the task reads `done`, the activity ledger reads assigned → done → *filed to Drafts 🗄*, an XP entry exists, and the vault announces **"FIRST DELIVERY FILED TO YOUR CABINET"**. The filed note is real prose (not an outline), with the local date, an honest Working footer, and the model's own *Assumptions* section. Every UI beat was immediate; the only latency that matters is the brain's 92s. A human doing this unassisted lands around **2–2.5 minutes** — the test passes with room. Caveat on my own number: my instrumented wall clock read 369s, inflated by an automation mistake of mine (I typed the topic into the message-search box, whose placeholder I'd matched by taking the first visible `input`), not by anything the product did |
| the task leg still lands after the reasoning split, 2026-08-08 | the day's riskiest plumbing change gave model thinking its own channel (unclaimed = dropped, all-monologue = "ran out of room"), and the task path was the surface most exposed: a reasoning-heavy brain filing a delivery. Seeded a task to gemma-4-e4b on the fresh office, ▶ START → **status done, XP entry recorded, activity reads assigned → done → "filed to Deliveries 🗄"**, and the filed note is one clean sentence with the local date and an honest Working footer — no monologue stapled to the front, which is precisely what this change could have broken |
| the boss's errand round-trips, 2026-08-08 | the one-liner's full loop, watched on two different LM Studio brains (gemma-4-e4b asking, llama-3.1-8b answering): "@Gemma ask Nano what 4+4 is, then tell me their answer" → direct thread reads the question, **"Asked Nano — watch the team room, and I'll bring their answer back here"**, then **"Nano confirmed that the answer to 4 + 4 is 8"** — while the team room holds exactly three bubbles: the DM, the verbatim answer, the closing words. Three findings got it there: every agent-to-agent DM landed in `team` so a boss-started chain ENDED in a room the boss wasn't watching (origin now rides the recursion; the last link reports back, in the coworker's own words); the DM framing told the one coworker who could close the loop "you are replying to X, NOT to the boss" (that coworker now gets report-back framing); and the boss-direct framing licensed [DM_TO] only for work "outside your skillset", so "ask Nano what 4+4 is" — inside everyone's skillset — produced a bare echo of the question in **3 of 5** runs, WORSE at low temperature. With the license written in: **3/3** clean. One content garble noted (a 4B brain restated 6+6 as "4 + 4" while carrying the right answer, 12) — brain quality, honestly rendered, ground truth verbatim in the team room one click away, which is what §3.4 is for |
| first run on a wiped install, re-verified 2026-08-07 | after a day that touched all six reply paths, the onboarding copy, the hire modal's default job description and the delivery footer: empty state → **0 HIRED** with the ⚠ ADD AI KEY alarm on → front desk lists Claude, Codex and Llama as found on this machine → hire the local one → **1 HIRED**, alarm clears, starter sheet opens → *First draft* → one field → filed to `Drafts/` **20 seconds** after the click, with real sentences, the local date, and a Working footer that says nothing was consulted. Zero §6 jargon anywhere on the path |
| coworkers actually work together, 2026-08-07 | the north star's central claim, watched live between two local brains. "@Llama ask Nova to name one colour" produced a real two-way chain — `Llama → Nova`, `Nova → Llama`, `Llama → Nova` — each rendered with its direction on the bubble, all 18 team-thread messages displayed, zero blank bubbles. The MECHANIC is sound. The CONTENT drifted: both models wandered off the question into an invented "olives project code review", which is the confabulation already in Known open, not an office defect |
| the calendar runs on the boss's clock, 2026-08-07 | "YOUR BUSINESS BY DAY · TASKS WHEN RAISED · MISSIONS WHEN THEY WRAP" — and the first half is exact: a task listed at 8:42 AM has `createdAt` = 08:42 local, where UTC would have read 12:42 PM, the same off-by-a-timezone that once dated a delivery tomorrow. Day grouping is local too, and the "Today 4" header matches its four rows. The missions half is unverified — no mission has run in this office |
| what each run is HANDED — audited, 2026-08-07 | third use of the entry-point census, this time on context rather than cleaning: of six `agentStream` callers only the two conversational ones should carry chat history, and only the TASK path wrongly did (fixed — it produced a delivery about the wrong subject). Missions pass `onUsage`/`onTool` and run on their own prompt; the meeting turn carries the transcript it needs; the stand-up passes `signal` and `maxTokens` and nothing else. One defect, five confirmed clean |
| the office survives ordinary accidents, 2026-08-07 | five checked, three were broken. **Reload mid-run**: the stream dies with the page and the task sat under DOING forever — now scrubbed to `inbox` on load, the way `missionsOnLoad` has always handled a dead mission. **Coffee**: stopped the run correctly but unclaimed the work, so resuming meant re-picking the person you had only paused — the assignee now survives a boss-stop, and a genuine failure still clears it so §7's "try someone else" stays the easy move. **Delete while running**: the worst — no confirmation (the guard keyed on `t.result`, which live work has not got), the desk stayed lit for a task that no longer existed, and the run went on to FILE A DELIVERY for work the boss had removed. Now it names the coworker, asks, and aborts. **Letting someone go**: the stream was already killed and the displays already degraded honestly on a dangling id; dismissal now also releases their tasks, including ones assigned but never started. **Happy path re-checked after all of it**: create → assign → ▶ START → done in 20s → filed, delivery reading "Purple" and nothing else |
| the floor's three promises | the banner names three gestures and all three are real: a task card's `dataTransfer` key matches the desk's reader (and the office carries its own draggable rail, so delegation never needs the board open); the 1:1 couch opens **1:1 WITH CAFRESOHQ · QUIET ROOM**; the meeting door opens **3 IN THE ROOM · CAFRESOHQ MODERATING** with both coworkers already seated |
| §7 holds when the DEFAULT brain is the thing that dies, 2026-08-07 | the CEO's own brain, not a coworker's — the case §7's third route was written for. Sent "Say the single word: hello" on a fresh office whose managed Gemma endpoint this machine cannot reach. The office showed an honest waiting state first (*"still waiting on that brain — it may be warming up"*, not a spinner implying progress), then after ~60s: **"⚠ hit a snag — couldn't reach that brain — it looks offline from here. Llama is still working, though — @mention them and they can pick this up."** One sentence, no raw error, a retry control, and the third route naming the coworker who really can work — `handoffHint` picking the local brain over the dead default. Nothing to fix; recorded so the next reader does not re-derive it |
| the office's side of the handoff — audited, 2026-08-07 | after two live attempts to make one local coworker hand off to another both produced prose instead of a `[DM_TO:]` block, I audited the office rather than blaming the model on a hunch. Every link holds: `const peers = agents.filter(a => a.id !== agent.id)` is populated; all three `agentStream` callers pass it (the dispatch path by shorthand, which is why a first read of the options object missed it); `toolsForAgent` adds `dm_to` whenever `peers.length`, with `requires: () => true`; and the doc it adds carries the full block form **plus** a generated `Coworkers you can DM: Nova (Generalist)` line. So the model was handed the syntax, the tool and the names, and answered in English anyway. The office is not the defect here — which is worth having checked, because the alternative reading (a tool silently gated off, contradicting the framing's "teammates available via DM_TO") would have been a serious office bug and looked identical from outside |
| the badge comes back down, 2026-08-07 | `awaiting_reply` had no closer, so the topbar count climbed by one for every hand-off that ended in a question and never fell. Fixed and then driven, on a chain I did not stage: delegating from the chat composer to Nova set off a real coworker-to-coworker exchange, and the new closer fired **four times**. End state **19 messages, 19 completed, 0 stuck**, four carrying `all 1 reply came back`, topbar showing no pending count. **CORRECTED an hour later**: I first wrote that this run was a third data point on handoff reliability, the delegate route succeeding where two direct instructions failed. It was not. `onDelegate` ignored the composer and re-sent the last user message, which was itself my instruction to *"delegate this using the DM_TO block, addressed to Nova"* — the office handed a coworker an order to delegate, and it delegated. The chain was real and the closer really fired; the inference about handoff reliability was worthless, and the 17-message ping-pong it produced was me delegating a delegation order. Reliability stands at one success, two failures, all on direct asks |
| every surface that shows EFFORT agrees on its span — census, 2026-08-07 | the same false span was found three times in one day (roster card, then Situation Wall + topbar HUD, then Settings), so the last one was closed by enumerating the CAPABILITY rather than chasing the next sighting: everything that displays a token figure. Six sites, and all six are now honest — the topbar HUD and the wall share `OFFICE_EFFORT_TIP`, the inspect panel and Team detail share `EFFORT_TIP`, both reading "since you hired them"; Settings carries its own local copy, now "Usage so far / since you hired them"; and the Night Shift card's "Effort this run" is per-mission and was right all along. **The Settings one is the lesson**: it shares no constant with the others, so the census-by-constant that found the first four could never have reached it. Hoisted copy makes one class of drift findable and hides another |
| every guard block EXECUTED, not just present — 2026-08-08 | prompted by a crash of my own: `acks is not defined`, a ReferenceError on the primary dispatch path that shipped hours earlier and had never run. `no-undef` was silent (the binding exists in the function, just not in that block), 21 suites were green, and the earlier runs that "verified" the path took branches that never reached the line. **A guard only executes when the thing it guards against is possible, so a rarely-hit guard is rarely-tested code.** So all three blocks were then driven for real: **@mention** (dispatch) → clean reply, **▶ START** (task) → done and filed to `Deliveries/`, **Delegate** → no error and the typed brief carried through. Presence of a guard in the source says nothing about whether it can run; only running it does |
| §3.6's five minutes, actually timed — 2026-08-08 | the promise is locked ("stranger sits down → detect → hire one coworker → pick a starter task → watch it happen → a real artifact lands") and had never been put on a clock. Wiped state dir, cleared mirror, cold load. **~19s** from the front desk appearing to pressing START — that is three interactions, hire + pick card + type a subject, with no settings page and no key prompt anywhere on the path — then **12s** for the model to finish and the file to land. **~31 seconds total.** Caveat stated plainly: scripted clicks are faster than a person's, so the honest reading is not "31 seconds" but "the flow contains three decisions and one wait, and the system's own contribution is 12 seconds". A human reading each screen has four and a half minutes of headroom |
| the coworker card matches §2 in full — audited 2026-08-08 | never checked against the spec end to end before. Live on a hired local coworker: **all four** stat bars present (Speed · Depth · Code · Cost, no fifth), the vendor rendered as `powered by your hardware` — a chip, not the identity, and the right phrasing for a local model — the specialty tag reading `cheap and tireless`, which is §2's own worked example for local brains, plus the job description and the experience block. **No raw model id anywhere on the card**: no `ollama:`, no `:latest`, no `claude-*`. The one thing the spec asks for that a card cannot show on its own — vendors change, coworkers persist — is exactly what the chip protects |
| first run, re-verified on a THIRD wiped install, 2026-08-07 | after ~40 further changes (the reply-path repairs, the marker strippers, the vocabulary sweep, the mobile doors): empty state → **⚠ NOBODY HIRED** with the front desk already open → hire the local one → alarm clears → starter sheet, with the Research card correctly NOT promising "sourced" on a machine with no search key → *why bread dough needs salt* → filed to `Research/` with the local date. **Zero protocol markers anywhere in the cabinet** (`grep -rlE '\[(VAULT_NEW\|BROWSER_FETCH\|ACK\|DM_TO)'` → none), which is the check that would have failed this morning: the equivalent run then wrote `[VAULT_NEW: …]` into the boss's first kept file |
| first run, re-checked | after ~40 commits of vocabulary/layout change: front desk → hire → the ⚠ ADD AI KEY alarm firing with nothing hired and clearing on a local-brain hire → "Your AI brain" ticking itself |

### The executable rules — and what a rule can and cannot be

**Which rules are executable now.** Most of this document is prose a reader has
to remember. Four parts are not, and that is where the leverage is — each was
written only after the same class of bug was fixed by hand three or four times:

| test | what it refuses to let back in |
|---|---|
| `scripts/test_no_invented_numbers.py` | a hardcoded per-token price; a percentage against a phantom 1,000,000-token budget |
| `scripts/test_floor_vocabulary.py` | `sub-agent`, `elevated`, `tok`, `iteration`/`iter` — and `agent` meaning a person — in any string a person reads, **including the prompt**, since the prompt teaches the model the word and the model says it back. Config surfaces and genuine technical nouns are exempt *by name, with reasons* |
| `scripts/test_reply_hygiene.py` | protocol markers reaching the boss as syntax — across **all 11** stream callers since 2026-08-07 (`agentStream` **and** `ceoStream`, the latter having been outside the census entirely, with the CEO's own chat reply cleaned only when it happened to emit a handoff) — and, since 2026-08-07, **a coworker inventing a colleague's words in the office's own handwriting** (`fabricatedRelay`: a `[Llama → Nova]:` relay label when nothing was delivered), a **declared wait with nothing sent** (`unsentAsk`), and a reply path that shows the **raw buffer** (`check_raw_buffer_shown`, which replaced a census that had been green through the defect it existed to catch) — including a block marker's **payload**, since stripping a `[MEMORY_WRITE: …]` opener and closer while keeping what they wrapped leaves the note body sitting in the reply as prose, a second unasked-for copy of a note already filed — and **requests that vanish**: a block-form marker opened without its closing tag never parses, so the coworker believes they asked and nobody is coming (`unsentHandoff`, `unsentElevation`, `unsentBlocks`) |
| `scripts/test_cast.py` | the shared cast vocabulary, and one rule the helper cannot defend itself: `handoffHint` only knows whose brain is ready, so the call site must exclude the coworker who just refused — otherwise a failed hand-off answers "Llama couldn't take it" with "Llama is still working, @mention them" |

**A census is only as wide as the entry point it knows to look for, and
the name you happened to be looking at becomes the definition.** The
reply-hygiene census enumerated `agentStream` callers. That was never a
definition of "reply path" — it was the function in front of me when the
rule was written — and it quietly became one. The CEO runs on
`ceoStream`, so the coworker a boss talks to most sat outside the rule
that exists to keep protocol markers off their screen.

Four uncleaned paths were behind it, and the main chat reply is the one
to remember: it was cleaned **only when the CEO happened to emit a
handoff or a DM**, by a local regex that knew two marker types out of
sixteen. A reply with an `[ACK: …]` and no handoff went to the boss as
raw syntax, every time, for as long as that code has existed.

Widening the census to both stream functions took 7 paths to 11 and
found three of the four new ones broken. Then check there is no third
door: `HQ.*Stream` callers across the repo are exactly 6 + 5, and
`mockStream` is an alias of `ceoStream`, so 11 is the whole set.

The check that generalises: **enumerate by CAPABILITY, not by function
name.** "What can put model text on a person's screen" is the real
question; `agentStream(` was a proxy for it that silently stopped being
true.

**The third bound: which FILES a rule looks at.** `GLOBS` in the vocabulary
suite lists nine paths and has never listed `claude-client.jsx`. Probing it
found ten hits, of which exactly two were copy — the provider picker's
`label: 'CafresoHQ · elevated (Claude Code + tools)'` and its Codex twin,
which a boss reads while choosing a brain. Both fixed by hand.

The file is **not** added to `GLOBS`, and the reason is the same standard
that refused the ternary rule: the other eight hits are identifiers —
`'hermes-agent'`, `'elevated-agent'`, a bare `'agent'` mode string — in a
transport module that is dense with them. Covering two findings would cost
eight hand-written exemptions, and an exemption list that long stops being
a rule and becomes a second copy of the file.

So the gap is written down instead: **`claude-client.jsx` is unscanned,
and its `label:` fields are boss-facing.** If provider labels multiply,
the right move is a narrow scan of that file's DISPLAY_KEYS only — not
the whole-file glob.

**A rule's BOUNDS are as much a claim as its pattern.** The vocabulary
scanner's JSX-text rule capped fragments at 120 characters. Nobody chose
that number for the copy it was guarding; it was a reasonable-looking
default that quietly redefined "copy" as "short copy". Seven boss-facing
violations lived behind it, and they were the *longest* strings in the
product — which is exactly what a boss reads when something matters:

- the **crash screen** ("Your projects, agents, and…")
- the **unattended-access consent** ("Only check this if you trust the
  topic + the agent's prompt", over "N iterations") — the most
  safety-critical sentence in the app, in machine vocabulary
- the hire modal's permission card, the Workspace ledger, the shop, the
  research thread

Raised to 400 and all seven surfaced at once. When a rule is green for a
long time, check what its *limits* exclude before congratulating it: a
threshold, a window, a truncation and a name list are all assertions
about where the problem cannot be, and none of them was tested.

Note the contrast with the ternary rule rejected the same hour. Both were
attempts to widen the same suite. The ternary form had **no audience
signal** and flooded, so it was refused; the length cap sat on a form that
already had one (text between tags in a view), so raising it was safe and
immediately productive. Widen a rule along an axis it already reasons
about; refuse to widen it along one it cannot.

**A refused rule is worth re-probing when the toolkit around it changes.**
The JSX-ternary rule was refused twice on 2026-08-07 and shipped on the
third attempt the same day. The refusals were correct: a bare ternary
carries no audience signal, and both early versions flooded — 22 hits,
then 28 — across object literals and prompt bodies. Shipping either would
have been worse than the gap.

What changed was not the pattern but the filters available to it. Three
arrived from work done in between:

- the **code-shaped reject** (`[;=]`, `const`, `return`) written for
  `_after_expr_spots` an hour later
- a **minimum length**, because `'on'` / `'md'` / `'off'` are flags
- marking those spots **not boss-facing**, so `prompt` and `context` —
  banned only on boss surfaces — stop firing on prompt bodies

Ten locations, zero false positives, every one real: `HIRE A SUB-AGENT`
as a **modal title**, two sub-agent lines in the provider picker, the
Night Shift form's "~N iterations" and "🛡 elevated agent", the Workspace
empty state on both viewports, a retry toast, and the CEO's
out-of-tokens note.

So "this cannot be scoped" meant "I have not found the axis yet". Hold
both halves: refuse a rule that floods **and** re-probe it when a new
filter shows up, because the reason for the refusal may have expired
without anyone noticing.

**Check for the DEFECT, not for the fix.** The sharpest lesson of
2026-08-07, and it came from a rule in this very table.
`check_every_reply_path` asks whether `visibleReply` appears within 150
lines of a stream opening — the presence of the cure, near the wound. It
was green through the entire period the dispatch path, the office's
most-used route, built its final text with `cleanHarmony(buf)` alone:
some OTHER `visibleReply` in the window satisfied the search, and the one
that mattered was never called. A tool marker plus the registry's own doc
string reached the boss's chat while the suite said all six paths were
clean.

Its replacement, `check_raw_buffer_shown`, looks for the anti-pattern
itself — a raw accumulated buffer handed to `cleanHarmony` — and cannot
be satisfied by an unrelated occurrence, because there is no unrelated
occurrence of a defect. Proven the only way that claim can be proven:
revert the real fix, run the suite, watch the new check FAIL naming
`app.jsx:1531` while the old census still reports "all 6 reply paths
clean their final text". Two rules over the same code, disagreeing.

Where both framings are available, take the negative one. A rule that
hunts for a cure can be fooled by a coincidence; a rule that hunts for a
wound cannot.

How to re-derive that list rather than trust the number: a *rule* asserts
about source it is not the unit test of. Two scan the repo (`ROOT.glob`); one
classifies a whole registry inside its subject; and `test_cast.py` is the only
suite that opens a second file — `ui/chat.jsx` — because the thing it defends
lives at a call site its own module cannot see. Every other suite reads
exactly one file, its own.

The pattern behind all four: when you catch yourself doing the same sweep a
third time, **the sweep is the deliverable, not the fix**.

**A rule is usually right about WHAT and wrong about WHERE.** The vocabulary
ban never changed; the list of places it looks has been wrong five times, and
each new surface was found by a leak, not by design. It started on display
props and JSX text, and has since had to learn: text sandwiched between two
interpolations (`{r.iterations} iter · {n} notes`, which touches neither `>`
nor `<`); the `body:` key, behind which the entire onboarding tour was
teaching every new boss "sub-agent" under titles that already said
"coworkers"; blocking dialogs, the loudest copy in the app and the least
prop-like; and `|| 'fallback'` defaults, which are the hardest of all,
because they only render when the real value is missing — precisely when
nobody is watching. One of those sat on the approval card for publishing to
the public internet, where the emitter, the builder and the renderer all
independently defaulted to the same banned word. When a rule passes clean,
ask what it cannot see before believing the surface is clean.

**Not every gap is worth a rule.** A sixth surface — string literals inside JSX
child expressions — returned 221 hits, mostly code fragments a regex misread
as strings. That needs a real parser, and a tripwire nobody trusts is worse
than none, so it was left out deliberately rather than exempted into
silence. And a detector's
first run is about the detector — two of these returned confident garbage
before they were useful, so prove one against a bug you can reproduce (0 → 1 →
0) before trusting a zero from it.


### Measuring this app without fooling yourself

**Testing a state-dependent branch: localStorage is a mirror, not the store.**
A surface that only renders past a threshold (`{xp.snags > 0 && …}`) is exactly
the kind that can silently never fire, so it has to be *seen*, not reasoned
about. Injecting the state through `localStorage` does not work: when
`CAFRESOHQ_HQ_STATE_DIR` is set the server-side JSON is the source of truth and
rehydrates over the mirror on load — twice in a row the probe entry vanished
and the row "correctly" didn't render, which would have read as a passing test
of a branch that was never actually entered. That is failure shape (4), a
measurement taken against a precondition never established. Write the
`$CAFRESOHQ_HQ_STATE_DIR/*.json` file instead, keep a `.probebak`, reload, read
the DOM, then restore and reload again to confirm the surface goes back.

**Not every repeated bug has a single detectable shape.** "Computed and then
discarded" turned up three times in one session — `agent.tasksDone` written
by three sites and read by none, a `userText` parameter accepted and ignored
until three surfaces said "a job", and a friendly label `('boss', 'You
(boss)', …)` unpacked and dropped so the map drew a node called "boss". Same
mistake, three different syntactic forms: a field, a parameter, a loop
target. An AST rule for the third found exactly one more instance and that
one was harmless. Shipping it would have implied coverage of the pattern
while catching a third of it — the mirror of the 221-hit scan that was
rejected for noise. A rule that under-claims its scope is as misleading as
one that over-claims. Some patterns are for a reader to carry, not a script.

**Census beats sweep, and a clean census still earns its keep.** The reply-path
census found three uncleaned paths under a green suite; the desk-clearing
census that followed found nothing. Both were worth running, and the second
is worth WRITING DOWN — otherwise the next reader re-derives it, or worse,
assumes it was never checked. Enumerate by ENTRY POINT (every
`agentStream(` caller) rather than by grepping for the fix: grepping for the
fix can only ever find the places that already have it.

**What the office cannot catch, and should not pretend to.** Two residues in
filed deliverables came from the model, not the pipeline: a stale sentence
replayed out of earlier context ("The boss likes figs." on a task about
fruit), and an invented `[Vault path: Research/banana-colour.md]` for a file
that does not exist. Both LOOK like office chrome and neither carries a
marker, so no structural rule reaches them — the guard for unclosed writes
works only because there is an opener to see. Filtering on shape would mean
guessing which of a coworker's sentences it meant, which is worse than
leaving them visible. The honest posture is the one already built: the
delivery's **Working** footer lists visits that really happened, so a
fabricated filing shows up as a claim with no matching line. That is a weak
signal against a confident sentence, and it is the correct amount of
certainty the office actually has.

**…and the line moved once, on 2026-08-07, which shows where it really
sits.** Driving two local coworkers and failing twice to make one hand off
to the other turned up a third residue that looked like the two above: the
coworker told the boss it had asked a teammate, and nothing had been sent.
The first attempt was pure prose ("Nova, can you name one colour of a ripe
lemon?") and belongs squarely on the cannot-catch side — no marker, nothing
structural, and reading it would mean guessing at sentences.

The second attempt was different, and the difference is the whole rule. It
ACKed the state `awaiting_reply` while the delivery queue came back empty.
A state the model **chose from a fixed set** is not prose — it is a claim in
the office's own vocabulary, checkable against the office's own record. So
`unsentAsk` catches it, on exactly the same terms as its siblings: silent if
anything was delivered, silent unless the wait was actually declared, and it
takes the PARSED STATES rather than the text so a sentence containing the
word cannot trigger it.

The boundary is not "claims the model makes" versus "claims it doesn't". It
is **claims made in a vocabulary the office defines** — markers, ACK states,
tool visits — versus claims made in English. The first kind is checkable and
every one of them should be checked. The second is not, and pretending
otherwise is how a guard starts guessing.

**A function can be right and unused.** The reply-hygiene suite was green
through the whole of the worst bug this session: `visibleReply` was correct,
and its output never reached the chat bubble on two of three dispatch paths.
The cleaned text went to the desk monitor, the activity detail, the journal
and the approval scan — every record except the one a person reads. Unit
tests prove a transform; they say nothing about whether the transform is
wired to the screen. The only thing that found it was sending a real message
to a real model and reading the bubble. When a rule is green and the screen
is wrong, suspect delivery before logic — and note that the same run also
exposed a queued `requestAnimationFrame` repainting raw text one frame after
the fix, so "the code is in the bundle" is not evidence either.

**The best detector this codebase has is one question, asked by a person:
what is this label actually reading?** It found six defects in seven passes
when the scripted sweeps had gone quiet, and it found them on surfaces every
suite passes:

- `MED` on every task card — a control with no lever behind it, while
  `pri-high` and `pri-low` sat fully styled and had never once rendered;
- four class bars stacked directly above two earned counters, judgement and
  measurement with nothing on screen telling them apart;
- **"Tools used"** over `agent.tools` — a permission list under a past-tense
  heading, so enabling a tool in Settings retroactively changed what a
  coworker had "done".

Asking it row by row down the Situation Wall — five rows, three findings —
added three more, and the wall is the densest run of them because every row
there is a number a boss reads as fact:

- **`⚒ 3/4`** against a roster of one. The wall's only staffing-shaped row
  read the DETECTION result — agent runtimes installed on this machine —
  and appended `· N busy`, where busy counts hired coworkers. One row, one
  separator, two unrelated populations. It now counts the office.
- **`📦 10` "finished tasks"** over a filter that is `t.artifactPath` with no
  test on status. Cards are draggable, so pulling a delivered task back to
  redo it keeps the path set — rightly — and the wall would go on calling it
  finished while the board showed it in progress. Second pass on this one
  label; the first had already moved it off counting files.
- **`⚡ 7.8K` "this session"** on a count that survived a full reload byte
  for byte. That one opened a real defect underneath the wording: the coffee
  break was zeroing it, left over from when the button was `REFRESH CTX` and
  the number meant context occupancy. Nothing had read it as occupancy in a
  long time, so the reset had no consumer — it only erased work the coworker
  really did.

None of these is wrong in the code. Each is wrong in what it lets a person
conclude, which is why no test catches them and no regex finds them: the
mismatch is between a WORD and a SOURCE, and only a reader holds both at
once. The clean passes are what make the rest findings rather than taste:
`Remembers` counts real vault files and names them in its tooltip, and the
wall's `HQ` and `SEARCH` lamps say exactly what they probe.

**A selector that matches nothing looks exactly like a broken app.** Five
times on 2026-08-07 a probe did this:

    const b = [...document.querySelectorAll('button')].find(x => /^PROJECTS$/i.test(x.innerText));
    b.click();                       // b is undefined — nothing happened
    // …then read the screen and conclude the nav is mis-wired

Every one produced a confident false finding: a nav that "landed on the
wrong view" (the label is `🗂\nPROJECTS`, so `^PROJECTS$` never matched), a
board that "already guarded busy desks" (done cards carry no `done` class,
so the filter matched all twelve), a file tree that "would not expand"
(clicked a wrapper `<div>` with no handler). Two of them nearly went into
this document as fixed behaviour.

The habit that ends it costs one line — **assert the match before believing
the outcome**, and return what you found when you didn't:

    const b = [...document.querySelectorAll('button')].find(…);
    if (!b) return JSON.stringify({ ERROR: 'no match', saw: […].map(x => x.innerText) });

Return the candidates on failure, not just the miss: that is what turns
"nothing happened" into "the label has an emoji and a newline in it". And
prefer driving the flow through the affordance a user would actually press
— the onboarding checklist's own button found the Projects dead end that
clicking the nav directly had hidden.

**A green result produced by a race is indistinguishable from a correct
one, and it will not stay green.** The `awaiting_reply` closer asked
`MessageRegistry.getMessage` for the message's current state. That reads
React state, and the write it was checking for happens in the same run
through `setMessages`, which is async.

It looked verified. On a live chain it fired **four times**, every one
correct, and the office ended 19-for-19 completed. What made those four
work was invisible: the fan-out loop had `await`ed real child dispatches,
React flushed in the gaps, and the read happened to see fresh state. The
fifth case had no awaits at all — a self-DM, a name matching nobody hired
— nothing flushed, the read returned the STALE state, and the message
stuck at `awaiting_reply` forever. The closer reproduced, through its own
race, the exact bug it was written to fix.

Two things to take from it. **Do not stop driving a thing at its first
confirmation** — four successes said "works", and the mechanism was wrong
throughout. And **never read back state your own run just wrote through an
async setter**; carry it in a run-scoped local (`markedAwaiting`,
`dmDelivered`) where the value cannot be stale by construction.

**Nothing you do synchronously after a `setState` can see its result — in
either direction.** Two bugs on 2026-08-07, opposite faces of one mistake:

- **Reading**: the `awaiting_reply` closer asked the registry for a state
  its own run had just written. When the code happened to `await` something
  first, React flushed and the read worked; when it did not, the read was
  stale and the message stuck forever.
- **Writing**: the Gazette's REPLAY called `onGoToOffice()` and then
  dispatched an event the office's listener was supposed to catch. The
  office had not mounted, the band never appeared, and the first
  re-enactment event of every replay was swallowed too.

The cures differ but the question is the same — *what has actually
rendered by now?* For reads, carry the value in a run-scoped local where it
cannot be stale by construction. For writes into something a state update
is supposed to mount, wait one beat (`MOUNT_MS`) before dispatching.

**Measure what defeated the precondition, do not guess at it.** The Gazette
would not re-fire for two attempts and I put it down to the
mirror-versus-store trap already recorded above. It was not that: the live
page's 60-second heartbeat overwrote `lastSeen` **within 2.5 seconds** of
the write — measured by writing the key, waiting, and reading it back. The
working procedure is to write the key and navigate in the SAME tick, which
leaves no window for the beat. A wrong diagnosis that names a real
documented trap is the hardest kind to notice, because it sounds correct.

**A synthetic message that looks like a user message will be read as one.**
`onDelegate` posts `(delegated "…" to Nova)` into chat as `from: 'user'`,
and separately picks "the last user message" as the brief. So each
delegation wrapped the previous one: found four deep on the floor, with
the coworker receiving the whole stack. Any record the office writes into a
stream it also READS from needs a mark saying who wrote it — here
`delegated: true`, checked when scanning back for the boss's last real ask.

**When two branches produce the same value, make one produce an impossible
one.** Unifying the office Effort total meant proving a new prop actually
reached the wall — but the prop and the fallback it replaced both evaluate
to 7,824 while `ceoTokens` is zero, so seeing the right number on screen
would have proved nothing about which branch ran. That is failure shape (4)
wearing a green result. The fix took ten seconds: set the fallback to a
sentinel (`999999`), rebuild, confirm the wall does NOT show it, restore,
rebuild. Reach for this whenever a change is invisible under current state —
it beats reasoning about which path executed, and it beats constructing the
state that would separate them when that state is expensive to reach.

**A clean census, written down: the ledger's snag rule.** `jobs` counts
task completions and missions; `snags` are written on the task path only.
That asymmetry looks like the §5 failure in the flattering direction — a
coworker who fails every dispatch keeping a perfect streak — but it is
correct, and the ledger's own header says why: a chat reply or a DM is not
a job, so a failed conversation is not a failed job. Checked the one case
that would break it, a task run routed through `dispatchToAgent`: all four
callers pass `{ taskId: null }`, so no task ever takes that path. The
`recordXp({outcome:'done'})` inside the dispatch path is a `[TASK_DONE:…]`
marker closing a real task, which is a task completion by another door.
Nothing to fix. Recorded so the next reader does not re-derive it — and
because the asymmetry is genuinely suspicious-looking, which is exactly the
kind of clean answer that goes unrecorded and gets re-investigated.

**Two of the six started as wording and ended as behaviour.** "Tools used"
was a heading over a permission list; `⚡ … this session` was a span over a
lifetime counter. In both cases the sentence that made the label honest also
made it obvious the state was wrong — a past-tense heading over a settable
list, a per-session total that a reload could not reset. Write the true
sentence first. If it comes out awkward, the awkwardness is usually the
defect, not the prose.

Ask it of anything a boss reads as fact — every counter, every badge, every
past-tense heading. Then fix the claim, not the data: the data has usually
been right every time.

**A failed edit does not stop the commit that follows it.** Chaining a
`python3 - <<PY` edit and a `git commit` in one shell call means the commit
runs even when the script raises: the assertion fired, the message still went
out describing a change that was not in the file. Do the edit, CHECK it
landed (`grep` for the new text), then commit as a separate step. This is the
same failure the app keeps having — a claim outliving the thing it described
— and the commit message is as much a surface as the floor is.

**`innerText` is not the layout.** Text extraction flattens the DOM and drops
inter-element whitespace, so it invents defects that are not on screen. Three
near-misses in one session: a bare `·` under each coworker that reads as a
dangling separator and is the idle MOOD glyph; "GENERALISTpowered by your
hardware", which renders as a distinct pill with a 6px margin, its own border
and an 8px font; and a name plate that looked unclickable because the handler
sits on the parent `.px-room`. Before filing anything about spacing, runs-on
text or a dead control, measure it — `getComputedStyle`, `getBoundingClientRect`,
a Range around the sibling text node — or take a screenshot. The mirror image
of the trap below: there, identical output hid a broken fixture; here, a
difference in the text is not a difference on the screen.

**The tell for a broken fixture is a result too uniform to be informative.**
Failure shape (4) has now surfaced three ways in one session, and each time
the bad measurement looked calm rather than wrong: three `withHandoff` cases
that returned byte-identical strings (the stub `C` never satisfied
`agentBrainReady`, so the hint was `''` every time); a Gazette probe reading
26 rows against an 80-row cap it was meant to exceed; a Situation Wall
"missing" on mobile when the office view simply wasn't open. None of them
errored. Before believing a comparison, check that the arms actually
DIFFER — if every branch agrees, suspect the fixture before the code, and
prove the precondition is real (`brainReady: [true, true]`, `0 HIRED`,
`onOffice: true`) rather than assuming the setup took.

**Clearing the mirror ALONE destroys the file — and this was NOT a testing
hazard. FIXED 2026-08-08.** The entry that stood here called it a trap for
whoever is driving the app, and told the next reader "never clear a mirror
key to reset a file-backed value". That advice was fine and the diagnosis
was wrong, which made it the most expensive paragraph in this document: it
labelled a live data-loss bug as operator error and closed the question.

What it actually is: **open the office in a second browser, clear site
data, or pick up another device, and your entire staff is deleted from
disk.** Reproduced without touching any mirror by hand — an office with one
hired coworker (`agents.json`, 08-07 17:10) read 2 bytes seven minutes
after being opened in a fresh browser context. The task from that run still
named `a_local_ollama`, a coworker who no longer existed.

And the mechanism is not the one the old entry described. It is not the
debounced PUT beating the fetch. `useFileStored` seeds from an empty
mirror; a BOOT-TIME effect then calls the setter with that empty value —
normalisation, not an edit — which sets `dirtyRef`; the arriving fetch sees
dirty and **returns without adopting**, on the rule that local edits beat
the server copy. The office is now holding `[]` *and marked dirty*, so the
next persist writes it over the real file. **The GET was turned away; the
PUT merely finished the job.** Fixing only the PUT (I tried) delays the
wipe by one mutation and nothing more.

The fix is two lines of principle: never write a file this session has not
read, and treat *dirty-but-still-byte-identical-to-the-seed* as untouched,
so the fetch is allowed to adopt. Every `useFileStored` caller was exposed
— agents, tasks, messages, experience, missions, projects, receipts, pins,
workflows, windows, memory — and all are covered by the shared fix.

The generalisable part: **"I broke it by doing something unusual" is a
hypothesis, not a finding.** The unusual act (clearing a mirror) and the
ordinary one (opening a new browser) produce the identical precondition,
and only one of them is a testing artefact. When you catch yourself writing
a rule for the operator, check whether a user can reach the same state
without trying.

**Cleaning up needs BOTH, and the mirror is the one that survives.** Restoring
only the file looks like it worked — the file reads clean — while the tab
still holds the fixture and `mergeByIdCap` merges it straight back on the next
mount. A Gazette probe of 150 rows was gone from `activity.json` and still
scrolling past on the office ticker two reloads later, because 150 of the 200
rows in `localStorage` were fixture. Clear the mirror key as well, reload, and
confirm on the surface rather than in the file you just fixed — for a merge,
the file going clean is not evidence that the state did.

**Hit-testing the floor: a rect is not what you can see.** Occlusion — a
control the user can see but cannot click — is worth sweeping for, because
each instance is silent (nothing errors, the click just goes nowhere). The
sweep is: for every interactive element, `document.elementFromPoint` at its
centre, and flag it when the answer is neither the element nor a descendant.
Two corrections it needs, both learned by getting them wrong:

- **Filter for real visibility first.** The naive version flagged 45 controls
  per view, identically across all eight views — the tell that the detector,
  not the app, was broken. Almost all were chrome inside *minimised windows*,
  which still have layout and a non-null `offsetParent`. `el.checkVisibility({
  checkOpacity: true, checkVisibilityCSS: true })` drops them: 45 → 1.
- **`getBoundingClientRect` ignores ancestor scroll-clipping, and so does
  `checkVisibility`.** The one survivor was the meeting-room door, apparently
  covered by the activity ticker. It is not: `.px-scene` is `overflow:auto`
  and ends at y=844, `.px-building` runs to 908, so the lobby and its door are
  simply **scrolled below the fold** and painted nowhere. The ticker band
  (868–893) lives *below* the scene's clip boundary and therefore cannot cover
  any scene control at all. An element whose rect is on screen may be painted
  entirely off it; intersect with every clipping ancestor before believing the
  rect.

Both corrections belong in the snippet, not in this paragraph. They were
prose here for a day, and the next sweep — mine, 2026-08-07 — ran the naive
version anyway, re-derived the meeting-room door, and got as far as measuring
the ticker overlap before remembering this note existed. A recipe you have to
remember to apply is a recipe that will be skipped, so here it is whole:

```js
const clipped = (el) => {                    // painted nowhere, whatever the rect says
  const r = el.getBoundingClientRect();
  for (let p = el.parentElement; p; p = p.parentElement) {
    const cs = getComputedStyle(p);
    if (!/auto|scroll|hidden/.test(cs.overflowY + cs.overflowX)) continue;
    const pr = p.getBoundingClientRect();
    if (r.bottom <= pr.top || r.top >= pr.bottom ||
        r.right <= pr.left || r.left >= pr.right) return true;
  }
  return false;
};
const occluded = [...document.querySelectorAll('button,a,select,[role=button],.clickable')]
  .filter(el => el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }))
  .filter(el => !clipped(el))
  .filter(el => { const r = el.getBoundingClientRect();
                  if (r.width < 4 || r.height < 4) return false;
                  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                  return hit && hit !== el && !el.contains(hit) && !hit.contains(el); });
```

Result after both corrections: zero occluded controls across all eight views
at 1440px — **with no windows open**, which is the third correction and the
one that bites next. In desktop mode a view IS a window, so a scan taken with
three of them stacked correctly reports the rail beneath as occluded: 41
controls, every one of them genuinely covered and none of them a bug. Close
the windows, or scan a single view, before reading the number. Re-measured
2026-08-07: 41 with windows open, 0 with a clear floor. A `pointer-events: none` on the ticker was written and then
reverted — the change was harmless but the failure it claimed to fix does not
exist, and a comment in this codebase is supposed to record a measurement,
not a hypothesis.

**Panes that grow instead of filling.** This class has bitten twice — the
office scene (see the note above `.hq-desktop > .office-wrap` in styles.css)
and the chat pane — and both times the symptom was a control pushed below the
fold rather than anything visibly broken. It is worth sweeping for, because it
gets WORSE with use: the pane is sized by its content, so a fresh install looks
correct and the office degrades as it fills.

The sweep: for every visible block, walk up to the nearest ancestor that bounds
height (`overflow-y` auto/scroll/hidden, or `position:fixed`) and flag the
child when it is more than ~1.5× its host. `.monitor` scored **26×** — 11,050px
inside a 417px window.

**Prove the detector before trusting a zero.** A null result from an unverified
sweep is worth nothing; two of the three sweeps in this document returned
confident garbage on their first run. Here: recreate the bug in the live DOM
(`monitor.style.flex = '0 1 auto'`, parent back to `display:block`), confirm the
sweep catches it, then restore and confirm it goes quiet. 0 → 1 → 0. Only then
does "no other pane has this" mean anything.

Current result, with that check done: **no oversized panes** across all eight
views or with the chat window open.

**snagCause is a BRAIN classifier — do not point it at anything else.** §7
says every failure is one honest sentence, and `snagCause` is the office's
shared way of producing one, so it is very tempting to route every raw error
through it. It only knows one domain. Pointed at a web page or a token ledger
it produces fluent nonsense about the wrong subject:

| raw | snagCause says | actual subject |
|---|---|---|
| `HTTP 401 Unauthorized` | "that brain isn't signed in yet — add it in Settings" | the *page* wants auth |
| `429 Too Many Requests` | "that brain is rate-limited" | the *site* is throttling |
| `insufficient funds: balance 0 < 100` | "that brain's account is out of credit — top it up" | a *token ledger* |

The last one is the one to remember: an AI-billing sentence for a money
failure, in the office's own voice. `SNAG_CAUSES` already carries the rule
that decides this — "a wrong-but-confident diagnosis is worse than a vague
honest one" — and it applies to the classifier's *scope*, not just its
fallback. I applied it to BROWSER_FETCH, BROWSER_SCREENSHOT and WALLET_SEND
and had to take it back out of all three.

For non-brain tools the honest move is to **attribute, not classify**: office
voice on the label, the source's own words for the cause ("Couldn't read that
page — …", `the ledger said: "…"`). Those backend messages are authored in
serve.py and already read as English; the machine-ish part was only ever the
label.

**The automation pane is not a browser: it toggles visibility ~96×/min.**
Measured directly — 16 `visibilitychange` events in 10 seconds, alternating
hidden/visible. Anything gated on visibility therefore behaves nothing like it
does for a person, and three separate measurements in one session were
distorted by it before the cause was found:

- the approvals poll appeared to run at 2× its intended rate (each "return to
  front" legitimately triggers a fast poll — the harness just returns to front
  constantly);
- a reconnect ladder could not be driven to its ceiling, because `onclose`
  only schedules a retry while the tab is visible;
- and a `TypeError` that looked like a real bug turned out to come from the
  `WebSocket` shim installed to measure the ladder.

So: **when a measurement disagrees with a carefully-documented design, suspect
the instrument before the code.** Reload without the probe and see if the
symptom survives. For visibility-gated code, reason from the diff — a constant
array and a reset-on-open have little room to be wrong — rather than trying to
out-measure the harness.

**Persisted state is read through a normaliser — verify against the SCREEN.**
Several writers deliberately scrub state on the way in or out, which is correct
behaviour and a trap for anyone verifying against storage:

- `persistableAgents` forces `status: 'idle'`, `mood: 'idle'`,
  `task: 'standing by'` before saving, so a coworker mid-meeting *persists* as
  idle at their desk;
- `missionsOnLoad` rewrites a persisted `running` mission to `paused`, so
  spend is never resumed without a click;
- the `$CAFRESOHQ_HQ_STATE_DIR` files rehydrate over localStorage on load.

Each is right. Together they mean **localStorage is not a mirror of what the
office is currently doing**. I reported "the meeting room cleans up after
itself, both coworkers back at their desks" on the strength of reading
`status`/`task` from storage — while the meeting was still open, and the floor
placards and the modal both said so and agreed with each other.

The reliable signals are the rendered ones: placards, tooltips, chip text,
`elementFromPoint`. If a check reads storage, ask first which writer last
touched that field and what it did to it on the way through.

**Testing a backend outage: patch `fetch`, don't stop the server.** Stopping
the real server is the obvious move and it does prove the BUG — the office
sat through 62 seconds with no backend and said nothing. It cannot prove the
FIX, because the detector skips hidden tabs and browsers throttle background
timers, and this pane is hidden most of the time.

What works: reject `/health` at the `fetch` layer and nudge the probe.

    window.fetch = (u, ...r) => /\/health\b/.test(String(u))
      ? Promise.reject(new TypeError('simulated'))
      : orig(u, ...r);
    document.dispatchEvent(new Event('visibilitychange'));   // when not hidden

That drove the whole chain in seconds — chip → OFFLINE, banner up — and
restoring `fetch` drove the recovery path back to LIVE.

Note the failed attempt first: setting `window._API_BASE` to a dead port did
nothing, because `backendHealth()` closes over a MODULE-scoped `_API_BASE`.
The banner's own text reads `window._API_BASE`, so both exist and only one is
the one that matters — patch the seam the code actually uses.

### Testing the office a new user actually meets

**A first-run bug is only visible from a first run, and the working office
actively hides it.** Every measurement in this document until 2026-08-07 was
taken against the same long-lived state dir — one with coworkers, tasks, a
filled cabinet and a session of history. That office cannot show you what a
new boss sees, because every zero-state branch is false in it.

Standing up a second server on an empty `CAFRESOHQ_HQ_STATE_DIR` (same repo,
different port) took one launch entry and immediately produced findings that
no amount of reading would have: the pinned alarm answering the wrong
question, a `[VAULT_NEW: …]` marker in the first deliverable a boss ever
receives, and a card promising "sourced" on a machine with no search. Three
defects in one sitting, on the one screen that decides whether someone stays.

Keep the fresh dir as a standing instrument, not a one-off. The cost is a
port and a directory. What it buys is the only honest answer to "what does
this look like to someone who has never seen it", which is a question the
developer's own office is structurally incapable of answering.

**Do not promise what you cannot deliver — the mirror of do not alarm.**
`officeHasBrain` returns true when the answer is unknowable, because an alarm
you cannot justify must not fire. The starter card's "sourced" claim needed
the same rule pointing the other way: with no assignee, the honest answer to
"who will source this" is nobody-known-yet, so the card must NOT promise it.
Same principle — never assert what you can't stand behind — and which
direction it falls depends only on whether the claim reassures or worries.

Worth stating because the two look like opposites and get argued as such. If
a surface is unsure, it should be quiet about the *claim*, not default to the
scarier or the friendlier reading.

**And the office's own promises are the ones to audit first.** All three
first-run findings were the office speaking in its own voice — a chip, a
filed file's contents, a card. None was a coworker's output. The model's
sentences are the part that cannot be enforced (§7 of this section); the
office's sentences are the part that can, which makes them the ones with no
excuse.

### The boundary to preserve, and what is still open

**The honesty boundary — the thing to preserve.** Everything the *office*
asserts is enforced in code and tested: the tool visit is structured data the
coworker cannot forge (§6 pass four), payroll and the FUEL gauge state only
what is true (§6 pass five), the attention queue counts problems that are
still yours, and `doing` means someone is actually on it. Everything the
*coworker* asserts is contextualised by an office record sitting beside it.
**A boss can always check the office against the coworker.** New surfaces
should extend that boundary, not blur it.

**Known open, honestly:**

- **Part of what looked like confabulation was the office's own doing.**
  Task runs passed `chat.slice(-6)` as context, same as the conversational
  paths, so back-to-back tasks handed the previous job's subject to the next
  one: a task about plums came back describing pears, filed and kept. Fixed
  2026-08-07 — a task now runs on its brief alone, since a card dropped on a
  desk IS the job and the coworker still has their memory and the vault. The
  chat paths keep their history, where the last six lines really are the job.
  Re-tested straight after the plums/pears pair: "Name one colour of a ripe
  tomato" returned "Red" and nothing else. Worth remembering before blaming a
  model: check what you handed it.
- **A coworker can still assert something false in prose**, and that prose
  reaches the filed memo. Prompt wording moved it (three deliveries' worth of
  before/after in §6), but no instruction makes a small model honest. The
  office's own record is the mitigation, not a fix — and since 2026-08-07 it
  is an explicit one: the delivery's **Working** footer is always written, so
  a note that consulted nothing says *"Nothing opened, saved or looked up for
  this one."* A real filing carried an invented
  `[Vault path: Research/lemon-colour.md]` four lines above exactly that
  sentence. Neither line is edited; they simply both appear, and the reader
  can see they disagree.
- **Unverified branches**, called out where they live: the specialist
  filing-deferral path still rests on unit tests. ATTEMPTED 2026-08-07 with a
  local brain once Vault Notes was enabled on it, and it did not reach the
  branch — asked to file with VAULT_NEW, Llama wrote
  `**Vault Path:** [VAULT_NEW: Research/pears.md]`, describing the marker
  inside a bold line instead of emitting it as a block. Mid-line, so correctly
  not stripped; never parsed, so no file; `agentFiledPath` saw no cabinet
  write and the host filed to `Deliveries/` as designed. The branch needs a
  model that emits block markers reliably, which is what "needs a cloud brain"
  meant. What the attempt DID confirm is the mitigation: the delivery carries
  the invented path and, four lines below it, "Nothing opened, saved or looked
  up for this one." — the two disagreeing on the page, on a case nobody
  staged.
  The Gazette's *"+N more coworkers"* line is now **verified** (2026-08-07) —
  it needed neither five hires nor a real absence, because the columns are
  grouped from ACTIVITY NAMES rather than the roster: six seeded names and a
  back-dated `lastSeen` produced four columns and "+2 MORE COWORKERS WERE
  BUSY — FULL LOG IN THE TEAM INBOX". The arithmetic is right and the
  overflow line carries its own route out.
- **A front-desk hire cannot run a browser Research mission.** Detected brains
  get their tools by kind — a local model `['web']`, a CLI agent
  `['files','shell','web']` — and none of them include Vault Notes, which a
  research mission requires alongside web. The saved ROLES do carry it (Kip is
  `['web','vault']`, Vera `['web','email','cal','vault']`), so the feature
  works if you hire a specialist and not if you hire a brain. That means the §3
  zero-config path — the one first run is optimised for — lands on an office
  that cannot use in-tab Research until someone visits Settings → Roster. The
  route out is on screen at the point of failure, and START is correctly
  blocked rather than running a doomed mission, so this is friction rather
  than a trap. Whether a detected brain should arrive with Vault Notes on is a
  permissions decision: it is write access to the boss's cabinet.

  > ✅ **CORRECTED 2026-08-12 — this never applied to the Night Shift, which
  > is the "headline overnight feature" the bullet used to name.** The two
  > missions do not share a toolset and never did. In-tab Research runs on the
  > BROWSER's tool registry, which is per-agent, so `canDoMode()` gates its
  > picker (`missions.jsx` — options carry `disabled` and a "(needs Web +
  > Vault tools)" suffix). The Night Shift runs server-side in
  > `night_runner.py`, whose `run_tool()` grants `VAULT_NEW`/`VAULT_APPEND`
  > unconditionally — it never consults `agent.tools` at all — and
  > `NightShiftSection`'s own picker matches that reality: every hired
  > coworker is selectable, neither 🌙 SCHEDULE nor ▶ RUN NOW carries a
  > `disabled`, and there is no gate to hit.
  >
  > Driven live rather than reasoned: scheduled a real Night Shift on **Llama
  > — `tools: ['web']`, no Vault Notes, exactly the front-desk-hire shape this
  > bullet said was blocked** — and it ran, wrote a run record with a real
  > summary, and appeared on the office floor's board. The zero-config path
  > can use the overnight feature on day one.
  >
  > Worth keeping as a lesson about this ledger itself: the entry was written
  > from the Research gate and generalised to "the headline overnight
  > feature" without driving that half. An honesty ledger that overstates
  > what is broken is wrong in the safer direction, but it is still wrong —
  > it invites a fix for a non-bug and quietly writes off a feature that
  > works.
- **`awaiting_reply` — the common case now closes; the rest is still open.**
  UPDATE 2026-08-07: the fan-out loop AWAITS every child dispatch, so when it
  exits, each recipient has run to a terminal state and the awaited thing has
  happened. A message still sitting in `awaiting_reply` at that point is now
  closed with "all N replies came back" — a statement of fact, needing none
  of the policy below. Narrow on purpose: it fires only when this run really
  dispatched somebody, so a fan-out that matched no hired teammate still
  reads as waiting, because it is. **DRIVEN LIVE, same day** — the two
  attempts that failed to produce a `DM_TO` block left this unverified for
  an hour; then delegating from the chat composer to Nova set off a real
  chain and the branch fired four times. End state: **19 messages, 19
  completed, 0 stuck**, four carrying `all 1 reply came back`, and the
  topbar showing no pending count at all. Before the fix those four would
  have been permanent. **The boss's half is now built too**: any
  non-terminal message in the Inbox carries a **✓ CLEAR THIS** button,
  transitioning it to completed with `by: 'you'` and the note `closed by
  you`, so the record never claims a coworker finished something they did
  not. Driven live on the message this race had stranded for 54 minutes:
  cleared, badge went from `📬 INBOX · 1` to no count, history showing
  `you`. What stays open is only the automatic case — a real recipient who
  never answers — still a policy question rather than a fix.
  The original writeup follows.

- **~~`awaiting_reply` never resolves, so the inbox badge only ever grows.~~**
  A coworker who asks someone and posts `[ACK: awaiting_reply: asked Nova…]`
  leaves that message non-terminal. When the answer arrives it creates a NEW
  message; all eight `MessageRegistry.transition` call sites act on the
  sender's OWN message, and none closes the one that was waiting. So the
  topbar count — which counts non-terminal messages — climbs by one for every
  hand-off that ends in a question, permanently. Measured here: 32 messages,
  24 completed, **8 stuck in awaiting_reply**, badge reading 8 with nothing
  needing the boss. I first wrote this off as litter from my own DM tests; it
  is not, it is what the lifecycle does in normal use. Closing it means
  deciding what resolves a wait — the reply landing, a timeout, or the boss —
  which is a comms-lifecycle decision rather than a one-line fix.
  Checked the escape hatch too, and there is none: the Inbox modal's only
  controls are four filter tabs and CLOSE. Expanding a thread does show each
  message's real state (`AWAITING REPLY` is right there, honestly labelled),
  so the DETAIL is truthful — but nothing in the UI can resolve, dismiss or
  close a message. The boss can watch the number and cannot touch it.
  The row/filter contradiction found alongside it IS fixed: a thread is listed
  when ANY message matches, while its pill shows the LAST message's state, so
  "ACTIVE · 8" opened on a single row badged COMPLETED. A filtered row now
  also carries "N here" — how many messages in that thread matched — so it
  reads "8 here · COMPLETED": why it is listed and where it got to, both true.
  Hidden under ALL, where nothing needs explaining.
- **The boss is typed `agent` on the vault map**, so the analysis panel counts
  the office's owner among its coworkers — "3 coworkers" for two hired. The
  node itself now reads *"You (boss)"* rather than a mysterious colleague
  called `boss`, and the boss genuinely belongs on a map of who talks to whom.
  Making the TALLY right means either a distinct node type or a special-cased
  label, which is a decision about what the map is for.
- **The meeting door sits below the fold at 1440×900**, a very common laptop
  size. `.px-scene` scrolls (142px), so the door is reachable and fully
  clickable once scrolled — measured, not assumed — but the floor's own banner
  advertises it in the same breath as two controls that are always visible.
  Whether the lobby should be above the fold is a layout call.
- **Two names on the floor still use the banned word deliberately**: the
  `AGENT OFFICE` header and the `Coding Agent` / `Slides Agent` role titles.
  Left alone on purpose — they are product naming, not leaked vocabulary.

- **The candidate book names brains two different ways.** The FOUND cards
  read `POWERED BY CLAUDE` / `POWERED BY OLLAMA`; the CANDIDATE cards below
  read `SONNET`. Both are on the first screen, inches apart. `SONNET` is a
  brand rather than a raw id like `claude-sonnet-5`, so it does not breach
  §6's letter — but two vocabularies for one fact, on the onboarding screen,
  is the drift this document is mostly about. Flagged rather than changed:
  the role titles beside it are deliberate product naming, so which register
  the hiring screen speaks in is a product call, not a defect to patch.

- **Coworker-to-coworker delegation is best-effort, and the north star
  rests on it.** "One office where all your AIs work together" needs a
  coworker to hand work to a coworker, and that runs entirely on the model
  emitting a `[DM_TO:]` block. The office supplies everything (audited —
  see the verified table). Observed reliability on `ollama:llama3.1`: it
  worked once on 2026-08-06 (a real three-hop chain, recorded above), and
  failed twice on 2026-08-07 — once unprompted, once after being told in
  the boss's own message to use the block and not answer itself. Small
  local models are the zero-config default, so this is the default
  experience.

  What is already true: the failure is caught and named (`unsentHandoff`
  for a malformed block, `unsentAsk` for a declared wait that sent
  nothing), and the boss's own routes — @mention, the Delegate button,
  dropping a card on a desk — are reliable because the OFFICE performs
  them, not the model.

  The decision, which is a product one: whether the office should ever
  interpret a prose handoff. It knows the peer names, so "Nova, can you
  …?" is matchable. It is deliberately NOT done — that is guessing at
  sentences, which is the line drawn in the boundary section above, and a
  wrong guess sends a real message to a real coworker. The alternatives
  are to leave it best-effort with honest failure (today), to lean harder
  on the prompt (tried once already, recorded null result), or to make
  the boss's routes so prominent that coworker-initiated handoff is a
  bonus rather than the path.

- **Hermes is still the default provider in code, and the picker says so.**
  North-star §3.1 forbids special treatment "not in code, not in copy, not
  in defaults", and names Hermes as the original mistake; the reminder
  confirms `HERMES_INTEGRATION_PLAN.md` now carries a superseded banner on
  the default-runtime decision. The front-desk COPY privilege is fixed
  (2026-08-08 — its card was the only one written as a pitch, "The house
  agent — already moved in", role "Resident Agent", while every sibling
  states only what was detected). What remains is the substance:
  `claude-client.jsx` sets `provider: 'hermes'` as the default setting, and
  the provider picker's `Hermes (default · in your container)` is therefore
  **factually true**. Changing that label alone would make the UI lie;
  changing the default is a product decision about which runtime a fresh
  office falls back to, tangled with §3.3's managed trial brain (which is
  Hermes-backed and which §3.3 explicitly endorses). Flagged, not patched:
  the options are to leave it, to re-point the default at the managed brain
  under a neutral name, or to make "no default until detection runs" the
  behaviour.

- **The CEO's opening line promises a brain nobody has checked.** The
  first message a new boss ever reads says *"I'm already running on
  Cafreso's Gemma 4 brain — nothing to sign up for."* It is canned text,
  printed before any probe, and on this machine the managed endpoint is
  unreachable — so the office's first sentence is a promise it then fails
  ~60s later. The failure itself is exemplary (see the §7 row in the
  verified table), which is why this is flagged rather than patched: the
  greeting is a first-impression product decision, the environment here is
  known-unreachable for local reasons, and hedging it on every machine to
  cover the machines where it breaks would cost the confidence it buys on
  the machines where it works. The options, for whoever decides: probe
  before claiming, soften to "should be ready", or leave it and rely on
  the §7 route — which does work.

- **"Workspace" still means two things, down from three.** The nav label
  for the `projects` view was renamed to **Projects** on 2026-08-07 — the
  mobile tab bar, the command palette's own `nav.projects` entry and the
  onboarding step all already said Projects, and `commands.jsx` carried
  both names for the same id sixty lines apart. Two uses remain and they
  are unrelated: the **layout mode** inside that view (`Workspace |
  Classic`), and **saved UI layouts** (`savedWorkspaces`, which toasts
  `Workspace: <name>`). Renaming a whole feature is a product call, so it
  is flagged, not patched. The collision that mattered is gone: a boss no
  longer clicks "Workspace" and lands somewhere offering to switch them to
  Workspace.

- **Candidate cards show `4 TOOLS`, a bare count.** The roster card's
  equivalent was renamed to **Can use** on 2026-08-07, because "Tools used"
  read as a past-tense record of work when it is a permission list. The
  hiring card has the same content and still shows only a number. Same
  question, unanswered: four of what, and used when?

**Recurring failure shapes, for whoever reviews the next change:**

1. **A number wearing a claim it hadn't earned** — payroll priced a free
   local model, a gauge filled toward a budget nobody set, a desk counted
   chat replies as "filed reports".
2. **Copy fixed, state left behind** — the "Sent → Drafted" toast was
   corrected while the line that moved the task to `doing` sat two lines
   above it; the meeting-door banner was corrected while its `aria-label`
   kept the old sentence.
3. **The office asking a coworker for what it already has** — narration of
   work the floor already shows, and an ACK that demanded a summary the
   office then stripped.
4. **A measurement taken against a precondition never established** — most
   of the false alarms in this doc, and every one is labelled.
5. **Computed and then discarded** — six instances by 2026-08-07, and the
   syntactic form differs every time: a field (`agent.tasksDone`), a
   parameter (`userText`), a loop target (the dropped display name), a
   written-but-unread record (`stalledNote`, mine, same day I added it), a
   value shadowed by a second write, and — the expensive one —
   `triggerChainStep` building the next step's brief WITH the previous
   step's output and then calling the dispatcher without it, so every
   chained workflow ran step two as though step one had never happened.

   Ranked by cost, not frequency: the first five dropped a label or a
   counter. The sixth dropped the entire reason its feature exists, and no
   surface anywhere looked wrong — the chain ran, both steps completed, both
   filed. **A feature can be fully wired, green, and pointless.** The only
   way this surfaced was running the feature end to end and checking whether
   the OUTPUT of step one appears in step two, which is a different question
   from whether step two ran.

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
>
> ✅ **Roster distress signal, shipped 2026-08-06.** Watching a real failure
> (Miko, no brain configured) all the way through, the STAFF ROSTER grid —
> the one place a boss goes to see "who's who" — turned out to be the one
> surface that stayed silent. The floor sprite two panels away showed an
> honest "hit a snag" bubble; the roster card read **IDLE · 0 · 0 · $0**,
> pixel-identical to a coworker who has never been given a single task.
> `agent.mood === 'stuck'` already carried the signal (set beside the honest
> sentence in `agent.task` when a run fails) — the card simply never looked.
>
> Now: a small `!` badge, a one-line honest reason under the role (the same
> `snagSentence()` text the floor and inbox use — no new copy to keep in
> sync), and Retry sits right on the card next to LET GO. The **status
> pill still only reports `agent.status`** — busy/idle, nothing else —
> because that is the §4 invariant this whole thread of fixes rests on:
> only `status` answers "is this coworker working right now." Distress is
> a second axis and gets its own badge rather than borrowing that word.
> Gated on the *live* mood, not "ever failed" — the instant a retry
> succeeds, mood clears and the badge should go with it, the same honesty
> rule as a prop visit only playing while the tool call is really running.

> ✅ **Their notebook, shipped 2026-08-06.** Fixing the dead private-memory
> feature (§6 pass four) left it working but *invisible*: a coworker's
> notes live in `Agents/<name>/` in the vault, and no boss-facing surface
> ever mentioned them. The one thing the office knows about an employee
> that survives across sessions was something you had to go digging in a
> file tree to find — which is not what having staff feels like.
>
> The card grows a **Remembers** row: `1 note`, with the note names on
> hover. One `vaultList()` for the whole roster, not one per card.
>
> **Unreadable is not the same as empty.** If the cabinet can't be read the
> row renders *nothing* — `memoryLabel` returns null. "0 notes" would claim
> the coworker has saved nothing when the truth is that nobody looked, and
> that is the same shape of lie §4 exists to stop. A coworker who really
> has saved nothing does read `0 notes`, because that claim is true.
>
> `memoryRoot()` now lives here rather than being spelled out by hand in
> two places in `hq-runtime` — the runtime writes to that folder, the
> roster reads from it, and a boss-facing count that disagreed with where
> the agent actually saves would be worse than no count. Verified end to
> end on a live local model: write → the index reaching the next prompt
> (captured off the wire) → read → the coworker answering from it.

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
   > ⚠ **A local brain must be given time to wake up** (found 2026-08-06).
   > One head timeout — 20s to the first byte — served every provider. That
   > is right for a hosted API and wrong for a local one: the first call
   > after a model is evicted loads gigabytes off disk before it can emit a
   > token. Measured — the same task failed **three times in a row** with
   > "that brain didn't answer in time" while Ollama was healthy and
   > answering a one-word prompt in 0.8s. The zero-config first hire, the
   > one most users will make, looked broken on its first job.
   >
   > `app/patience.jsx` (pure, `scripts/test_patience.py`, 31 checks) splits
   > it: **20s remote, 90s local**. "Local" is what the driver KNOWS —
   > ollama/lmstudio proxy to this machine through a same-origin path, so
   > the URL alone can't reveal it — with a loopback/RFC1918/`.local` URL
   > check as the fallback for a custom endpoint the user pointed at their
   > own box. The host check parses the URL rather than substring-matching:
   > `localhost.evil.com` and `evil.com/#localhost` are not local, and
   > `172.32.x` is not in `172.16/12`.
   >
   > **The longer budget required the waiting line, not the other way
   > round.** A streaming bubble shows three animated dots and nothing else
   > until the first byte. Raising the budget without saying anything would
   > only have made the blank stare longer — the fix would have felt like a
   > regression. So the stream head fires `cafresohq:brainSlow` at 6s and
   > the bubble adds "still waiting on that brain — it may be warming up".
   > It is shown only on a bubble that is streaming AND still empty, so the
   > sentence is true of that message no matter which run was slow, and it
   > clears the instant text arrives — a bubble that starts flowing stops
   > apologising.
   >
   > Verified live against an evicted model: dots at 0s, the line at 12s,
   > gone the moment content flowed — and the task that had failed three
   > times completed and filed.
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
   > **The transcript is not the deliverable** (found 2026-08-06, driving a
   > real filing end to end for the first time). A task "Three primary
   > colours" filed **8,833 bytes**. The coworker's actual answer was one
   > sentence. The rest was the tool echo the runtime streams inline —
   > `📡 BROWSER_FETCH("https://…")`, `URL:`, `Status: 200`, `Title:`, a
   > rule, Wikipedia's page text, and `[…truncated, 79626 more chars]`.
   > Every one of those is §6-banned jargon, in a file the boss *keeps*.
   >
   > The split is **watching vs. keeping**, and it is now a rule:
   >
   > - **The live screen shows the whole tool visit.** That is what watching
   >   someone work looks like, and removing it would make the floor read as
   >   idle while the coworker is mid-fetch — a §4 honesty failure.
   > - **Every record the boss reads later is the memo**: the task card's
   >   result, the coworker's `recent` line, the journal entry, the filed
   >   note. `stripToolEcho` runs once, before `visibleReply`, and covers
   >   all four.
   > - **But deleting the working outright would launder the sources.** A
   >   memo reporting Wikipedia's answer as the coworker's own is *less*
   >   honest than the transcript was. So the visits come back as a
   >   **Working** footer in office words — `- Read en.wikipedia.org/…`,
   >   `- Looked up …`, `- Opened …` — naming what was consulted, never
   >   which tool.
   >
   > Mechanically: the echo format is defined at the one site that owns it
   > (`hq-runtime.jsx`) and travels **with the `done` event** as `ev.echo`,
   > so filing removes it by literal string match. It is not re-derived by a
   > regex downstream — a fetched page contains blank lines, so the block's
   > end is genuinely ambiguous in the flat buffer, and a greedy pattern
   > would eat the coworker's answer.
   >
   > **The office runs on the boss's clock.** The same filing was dated
   > `2026-08-07` at 8pm on the 6th: `toISOString()` stamps UTC. Every other
   > date on the floor is local, so `officeDate()` is too.
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
>
>   > ⚠️ **The row showed the claim, not the act (fixed 2026-08-06).**
>   > Posting a real request to `/approvals/external` — `Bash`, input
>   > `rm -rf build/`, summary "Clean the build directory" — the boss was
>   > shown **only** `Bash: Clean the build directory`. `p.input` was
>   > dropped at the mapping entirely, so the command never reached the UI
>   > in any form. (The no-summary fallback was no better: it printed
>   > argument NAMES, not values — `Bash (command)`.) The title is written
>   > by the agent *asking for permission*; this gate exists to catch a
>   > summary that doesn't match the action, and it was showing the summary
>   > alone.
>   >
>   > **An approval surface inverts §7.** Everywhere else raw payload is
>   > noise to translate away; here it is the entire point — consent needs
>   > the real thing, verbatim, or it isn't consent. The row now carries
>   > `formatToolInput(p.input)` (`app/approvals.jsx`, 14 checks in
>   > `scripts/test_approvals.py`) in a monospace box, plus the `cwd`.
>   >
>   > The first cut capped values at 400 chars and testing it produced the
>   > lesson worth keeping: a command padded with 500 harmless characters
>   > and ending in `rm -rf /important` — titled "Harmless cleanup" by its
>   > author — rendered as a wall of padding with the dangerous tail cut
>   > off. The truncation was *marked*, and the one part that mattered was
>   > still the part that vanished. Length was never a layout problem (the
>   > box scrolls), so a tight cap bought nothing but hiding the END of
>   > long input — exactly where something buried would be. Cap is 8000 now
>   > and a test pins the tail surviving.
>   >
>   > **And the receipt had it worse (fixed same day).** `recordReceipt()`
>   > copied `title` and dropped `detail`, so the *permanent* record of a
>   > decision kept only the asker's summary. The evidence was already
>   > sitting in the audit trail from testing the fix above: the entry for
>   > the request whose command ended `; rm -rf /important` read, in full,
>   > **"Bash: Harmless cleanup"**. The approval row is transient — you
>   > decide and it's gone — but the receipt is the answer to "what did I
>   > actually authorise?", and it was answering with the requester's
>   > marketing copy. Receipts now carry `detail` + `cwd` and render the
>   > same box. **An audit trail that doesn't record what was audited is
>   > decoration.** Rows written before this have no `detail` and simply
>   > omit the box — nothing is back-filled or invented for them.
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
>
> **`doing` is a claim, and only starting work may make it** (found
> 2026-08-06). Two controls moved a task to `doing` before anything had
> been started:
>
> - **→ CHAT** drafts the task into the composer and waits for Enter. It
>   also flipped the task to `doing`. Measured: a task read `doing` while
>   its message was still unsent text in a textarea, and an earlier task
>   had been stuck that way all session with nobody working on it.
> - **📋 ROOM** opens the new-meeting *modal* — which the boss can cancel —
>   and flipped the task the same way.
>
> The tell: the → CHAT **toast copy had already been fixed** for exactly
> this reason ("Sent" → "Drafted … press Enter to send"), and the line that
> lied about the state was sitting two lines above it. Honest sentence,
> dishonest state — the same shape as the `agent.task` bubble bug in §4.
> **Fixing the copy is not fixing the claim.** When a §4/§5 honesty rule
> catches a sentence, check what the surrounding code writes down.
>
> Both now move on the real event: → CHAT via the existing send path
> (`onInferTaskAssignment`, keyed on the `_(from task …)_` footer), 📋 ROOM
> via `cafresohq:taskMeetingStarted`, fired from the modal's `create()`
> rather than its `open()`.
>
> **"Is anybody actually on this?"** — the follow-on, same session. Once
> `doing` stopped over-claiming, the opposite gap showed: a DOING card was
> pixel-identical whether a coworker was mid-run or the job had been
> abandoned there for hours. Two of them had. An office where jobs rot
> invisibly in progress is not an operating business.
>
> `app/worklog.jsx` (pure, `scripts/test_worklog.py`, 33 checks) adds two
> honest facts:
>
> - **When it started.** `startedAt`, stamped entering `doing`, cleared
>   leaving it, and never re-stamped mid-run — a job sitting two hours must
>   not report itself fresh every time it is touched. Enforced by
>   `applyStatus()`, which now owns **all nine** status writes; an
>   invariant applied at eight of nine sites is not an invariant.
> - **Whether anyone is on it now.** §4 is binding: `agent.status` is the
>   only authority. It deliberately does NOT try to prove the agent is on
>   *this* task — nothing links a run to a task id, and inventing that link
>   is exactly the confident-but-wrong claim §4 exists to stop.
>
> Tasks predating `startedAt` show the state without a duration rather than
> guessing from `createdAt` (when the job was *written down*, not started).
> The line never says "stuck": that word belongs to a coworker who tried
> and snagged (§5), and a job nobody picked up has failed at nothing.
>
> **▶ START closes the loop.** The board's assignee dropdown deliberately
> only names an owner ("dispatch is a separate, explicit act") — but the
> explicit act existed nowhere on the board, only as a drop on the office
> out-tray. So the honest flag had no honest remedy beside it. START is
> that act, on the same handler as a desk-drop.

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
> spend) — though see **pass five**, which retracts this note's implicit
> claim that Payroll was showing real numbers. And the card's
> `☕ REFRESH CTX` button — jargon, and it zeroed the
> counter while leaving an in-flight run streaming — is now `☕ COFFEE
> BREAK` on the floor's own `onCoffee` handler: one gesture, one behaviour.
>
> Tooltips claim no unit. Token counts are not word counts, and "words read
> and written" would be a small lie told confidently.

> ✅ **Pass four — the tool-visit row, and what it exposed (2026-08-06).**
> The table's `tool call` row — *"shown as the action itself: reading files,
> searching"* — was broken on **four** surfaces at once, each with its own
> hand-rolled string:
>
> | surface | was | is |
> |---|---|---|
> | desk bubble | `🔍 memory_read: facts/france.md` | `opening facts/france.md` |
> | activity row | `memory_read("facts/france.md")` | `opened facts/france.md` |
> | chat echo | `📡 MEMORY_READ("facts/france.md") →` | `📁 Opened facts/france.md` |
> | delivery note | `- Read facts/france.md` | (unchanged — it was the only honest one) |
>
> One table now (`visitLine` in `app/floor.jsx`, same taxonomy and same
> search-before-web order as `toolProp`); the tenses differ only because the
> surfaces do — a bubble says what is happening *now*, a log and a filed
> note say what happened. `app/artifacts.jsx` had grown its own copy of the
> phrasing, which is how one filing-cabinet trip ended up described four
> ways; that copy is gone.
>
> The model's own raw invocation lines (`[BROWSER_FETCH: …]`) now join the
> orphan-tag strip, so the KEPT record doesn't carry the same call twice —
> once as the coworker's syntax, once as the office's line. Whole-line only:
> a marker *inside* a sentence stays, because removing it leaves a broken
> sentence.
>
> ### ⚠ The office's voice is not the coworker's to borrow
>
> Verifying the new wording turned up the worst thing found on this floor.
> Asked a local model to check its memory, the chat returned **two** visit
> blocks:
>
> ```
> 📡 MEMORY_READ("facts/france.md") →
> Found note on French capitals in memory!
> [Vault path: Research/capitals-of-europe.md]
>
> 📁 Opened facts/france.md
> (no memory at "facts/france.md")
> ```
>
> The second is the office reporting what really happened. The first is the
> **model writing a tool visit that never occurred**, in the office's own
> format, with an invented result and an invented vault path. To the boss
> both read as the office speaking, and one of them is a fabricated fact
> attributed to their own filing cabinet.
>
> It learned the format from us: every visit is stored in the chat message
> text, and `chatToMessages` fed that text straight back as conversation
> history. `stripOfficeVoice` now runs at that one choke point — the office's
> report of its own actions never re-enters the model's context as something
> the model said. Only the head line goes; result bodies stay, because they
> are real information the next turn needs. Verified: the same prompt now
> produces no forged block.
>
> **Not yet closed.** The coworker can still *claim* in prose that it found
> something it didn't — that is model confabulation, and the office's line
> sitting right below it now contradicts it, which is the honest outcome.
> But the real hardening is structural: the visit should be a rendered
> element attached to the message, not text inside the bubble, so nothing
> the model types can look like the office speaking. Filed as the next pass.
>
> ### ✅ Closed — the visit left the text channel (2026-08-06)
>
> **Everything in the text channel is forgeable.** Stripping the office's
> voice out of the model's context removed the *incentive*; this removes the
> *possibility*. The runtime no longer injects the visit into the token
> stream at all — it rides the `done` event as structured data (`toVisit`),
> `attachVisit` hangs it on the streaming message, and the bubble renders it
> as office chrome: inset, ruled, its own type, deliberately nothing like a
> speech bubble. The boss can tell at a glance which lines the office
> vouches for and which the coworker merely typed.
>
> Checked first that nothing depended on the inline text: all five stream
> consumers already read tool results from `onTool`, not from the buffer.
> `echo` stays on the event because histories written before this change
> still carry the banner inline and filing removes it by exact match.
>
> One trap on the way: the direct-agent path had both `messageId` (the
> comms-registry record) and `agentMsgId` (the chat bubble) in scope, and
> passing the wrong one attaches nothing, silently. Verified by rendering.
>
> ### 🐛 …and it immediately exposed a dead feature
>
> The first real visit rendered as:
>
> > 📁 at the filing cabinet
> > `Error: d.startsWith is not a function`
>
> `/vault/list` returns records — `{path, title, mtime, size}` — and every
> consumer in the app reads `f.path`. The two MEMORY_* sites read the
> entries as plain strings. So **`[MEMORY_LIST]` threw on every call since
> it was written**, and `memorySummary()` threw the same inside a
> `try/catch` that swallowed it — meaning `agentMemoryNote` was *always*
> empty and **no coworker was ever told what was in its own memory folder**.
> The entire private-memory feature was dead, silently.
>
> It stayed hidden precisely because the thrown message was buried in a tool
> echo spliced into a chat bubble, among the model's own prose. It surfaced
> the instant a visit became its own element with the result on its own
> line. That is the argument for this change restated as a bug: **when the
> office's own account is structurally separate, its failures are legible.**
> `vaultPaths()` now normalises both shapes; pinned in
> `scripts/test_reply_hygiene.py`.

> ✅ **Pass five — Payroll was not a real number (2026-08-06).** §6's own
> note above said "Payroll shows real numbers; the bar is a vibe." It
> didn't. **Five** surfaces multiplied an agent's token count by one
> hardcoded rate — `0.0000015` — regardless of which brain ran the work.
> On the live floor that meant:
>
> | coworker | brain | showed | truth |
> |---|---|---|---|
> | Llama | local Ollama | **$0.0533** | costs nothing at all |
> | Claude | Claude Code | **$0.0011** | flat monthly plan, no per-word component |
> | — | office FUEL row | "about $X in payroll" | a total across brains that bill differently, or not at all |
>
> The rate is wrong even where the *shape* is right: the models this office
> routes to differ by roughly two orders of magnitude per token, so one
> constant isn't an estimate — it's a number with a currency symbol on it.
> This is the boss's money, on the surface §6 renamed specifically to be
> honest about money.
>
> `payrollLabel()` gives three answers and refuses to invent a fourth,
> keyed on the **routing prefix** (how the brain is actually dispatched),
> not the display name:
>
> - **local** (`ollama:` · `lmstudio:`) → `in-house` — "runs on your own
>   hardware, no per-word charge". Zero *is* a real number.
> - **subscription** (`claudecode:` · `codex:` · the house brain) → `on
>   your plan` — per-job payroll isn't a thing that exists for these.
> - **metered** (everything else) → `—`, with a tooltip saying it's billed
>   per word and no rate is configured. A dash plus the true work-done
>   count beats a confident wrong figure.
>
> The two office-wide dollar totals are gone rather than repaired: a single
> payroll number spanning free, flat-rate and metered coworkers is not a
> quantity that exists. The FUEL bar still shows work done, which is true.
> 10 checks in `scripts/test_cast.py`, including that no payroll tooltip
> anywhere contains a `$`.
>
> **The same shape, one surface over: a gauge with no scale.** Sweeping for
> siblings of the payroll bug turned up the **FUEL bar**, on the Situation
> Wall and in the token HUD, filling toward a hardcoded **1,000,000**
> tokens. Nothing sets that ceiling and nothing enforces it — no caller has
> *ever* passed a budget, so the default WAS the scale. At 38.8K it drew a
> 4%-full bar, which reads as "you have 96% of your budget left" against a
> budget that does not exist, and the word *FUEL* implies depletion on top
> of it.
>
> A bar is a claim about a limit. `TokenHUD`'s `budget` is opt-in now
> (`null` by default) and it draws no bar without one; the Situation Wall
> row shows `⚡ 38.8K`, a real quantity, like every other row on that wall.
>
> **`scripts/test_no_invented_numbers.py` is the tripwire.** Neither bug was
> catchable by a unit test — both were *plausible* numbers inside otherwise
> correct code, which is exactly why they survived. So the guard is
> source-level: the banned shapes (a hardcoded per-token price, a percentage
> against a 1,000,000 ceiling, a defaulted token budget) fail the suite with
> the reason attached. `app/cast.jsx` may still *name* the old constant in
> the comment explaining why it went. Verified the guard fires by
> reintroducing both bugs and watching it report them by file and line —
> a tripwire that has only ever passed proves nothing.

> ⚠ **An alarm may not scroll (2026-08-06).** Stopped auditing code and just
> *looked* at the floor at a laptop width. `.topbar .status` is a horizontal
> scroller whose scrollbar is **deliberately** hidden — a visible one would
> force the page's minimum width, which is a fair trade — but nothing
> replaced the affordance, so anything past the right edge wasn't merely
> awkward to reach, it was invisible. Measured at a 718px viewport: **189px
> of chrome hidden**, and what was hidden were the three controls a boss
> must never lose:
>
> | hidden | why it matters |
> |---|---|
> | `⚠ ADD AI KEY` | nothing will run until it's fixed — the blocking condition |
> | `■ STOP ALL` | the emergency brake, hidden *exactly* when agents are running and it's needed |
> | `🔔 26` | every unread notification |
>
> `■ STOP ALL` is the sharp one: it renders only while work is in flight, so
> it was guaranteed to be missing at the one moment it exists for.
>
> Now a `.status-pinned` sibling holds those three. It sits outside the
> scroller and never shrinks. **Informational chips and secondary tools may
> scroll; an alarm may not.** The strip also gains a right-edge fade, applied
> only while it genuinely overflows (`is-scrollable`, set from JS against
> `scrollWidth`) — a permanent fade would imply content that isn't there,
> the same species of small lie as a gauge with no scale.
>
> Wrapping was the obvious alternative and is wrong here: two views size
> themselves with `calc(100vh - 110px)`, so a taller header would push them
> off the bottom of the screen. Fixing the harm without that regression
> meant pinning, not reflowing.
>
> ~~**Not fixed, and worth its own pass:** the tool row is *overloaded*.~~
> ✅ **Fixed next pass — `⌗ ROOMS`.** The row needed 1024px and had 637 even
> at 1400px wide, so those launchers were behind a hidden scroll at *every*
> width, not just narrow ones.
>
> Six of them — Memory shelf · Stand-up · Research missions · Meeting rooms
> · Workflows · Day/Night — now live in one `TopbarMenu`. **INBOX stays
> out** because it carries attention; the six are rooms and facilities you
> *go to*, which is also why the button is `⌗ ROOMS` rather than a bare `⋯`.
>
> Grouped by **nature, not by measurement**. A priority-plus toolbar that
> re-measures on every resize is a lot of machinery to decide something that
> doesn't change — the split between "an alert" and "a place you visit" is
> stable, so it belongs in the markup, not in a ResizeObserver.
>
> **Folding a launcher away must not fold its COUNT away.** Hiding live
> state is precisely what this whole thread of work exists to stop, so the
> menu button carries the total (`⌗ ROOMS ▾ 2`), its tooltip enumerates
> them ("1 meeting rooms, 1 workflows"), and every row shows its own.
>
> Result, measured: at 1400px the strip needs 637 and has 637 — no overflow,
> no fade, nothing off-screen; same at 760px (740/740). The fade machinery
> from the previous pass stays for genuinely tight cases. `Apps ▾` was
> considered as a home and rejected: it belongs to the outer Cafreso
> eco-bar and switches *products*, not HQ facilities.
>
> Verified by driving it: picking "Memory shelf" closes the menu and lands
> on the Memory view; Esc closes and returns focus to the button; an
> outside click closes it.

> 🚨 **Chat could be lost permanently (2026-08-06).** Kept looking at the
> floor and noticed the chat panel parked over the middle of the office —
> clicking **Office** did not show you the office. Pulling that thread
> found something far worse underneath.
>
> **The gate.** The floating chat window was rendered behind
> `activeView !== 'chat'`. In desktop mode the content area renders
> `renderViewBody('visual')` *unconditionally*, so `activeView` is a
> leftover with no effect on what you see — **except there**. A stale
> `activeView === 'chat'`, carried over from a narrow-viewport session and
> **persisted to localStorage**, suppressed the floating window forever
> while the office rendered regardless.
>
> Measured in that state: chat unreachable, **zero** visible ways back
> anywhere in the UI, surviving reloads. The boss loses their chief of
> staff and the app offers no route home. The gate now asks the real
> question — is chat being rendered *inline* instead? — as
> `(desktopMode || activeView !== 'chat')`.
>
> **The missing door.** `NAV_ITEMS` never contained chat, so the rail — the
> app's navigation — had no entry for the single most important
> destination; the only affordance was a mobile tab bar that is
> `display: none` on desktop. Chat now sits in the rail beside the brand,
> *not* inside `NAV_ITEMS`, because that list drives the 1–8 keyboard
> shortcuts and inserting into it would renumber every shortcut a boss has
> learned. It belongs next to the chief of staff's nameplate anyway.
>
> **One navigation verb, actually.** `navTo`'s own comment says every
> surface must route through it — and the rail was still calling
> `openOrRaise` directly, so the new "going to the Office clears the floor"
> rule never fired from the one place a boss actually clicks Office. Fixed
> by passing `navTo` as the rail's launcher.
>
> Verified end to end: the stranded state recovers on load; Chat opens from
> the rail; **Office clears the floor and the office is visible**; Chat
> comes back; Tasks still opens its window and does *not* disturb chat.

> ✅ **Swept the rest of the class — mostly clean (2026-08-06).** A one-way
> door built out of *persisted* state is a class, not an incident, so every
> other persisted flag got the same treatment. Findings, including the
> negatives, because "we checked and it's fine" is worth writing down:
>
> - **Chat window geometry** — already safe. Seeded `{x:2400, y:1200}` (as
>   if dragged to the edge of a 2560px monitor, then reopened at 1400) and
>   reloaded: the window landed at (992, 432), on-screen. `app/windows.jsx`
>   carries a deliberate "one-time repair" for stale/oversized geometry.
> - **`windowsEnabled`** — reachable both ways: the dock's power button
>   exits, Settings and `openOrRaise` re-enter.
> - **`railCollapsed`** — has its own «/» toggle.
>
> Also verified the new rail Chat entry across **both** modes, since it
> routes through `navTo` and I'd only driven it in one: with desktop mode
> off, the rail item still opens a visible, on-screen composer.

> ✅ **The empty out-tray said nothing three times, and one of them was a
> lie (2026-08-06).** The header hint ("No tasks waiting — add one in the
> Tasks tab."), an `.otr-empty` body ("All clear. Drop something here from
> the Tasks tab to delegate.") and the `0` count all reported the same
> emptiness — holding a full row open on the one surface where vertical
> space *is* the product.
>
> The body line was also **false**: there is no `onDrop` handler on the
> task rail. The only one in the office is on an agent's desk. It told the
> boss to perform a gesture that does nothing.
>
> Gone. The hint already names the real next action. Measured: the rail
> drops 80px → **53px** and the floor gains 26px of height (top 182 → 156).

> ✅ **The banner named furniture the room doesn't have (2026-08-06).**
> Same technique again — read an instruction, check the code does it. The
> office banner is on screen at all times and makes three promises. An
> earlier pass audited what the three controls *do*; it never asked whether
> they are **on this surface**.
>
> - **"click guest chair for 1:1"** — there is no guest chair on the floor.
>   The 1:1 prop is a couch, and the floor labels it **`1:1 SOFA`** in its
>   own pixel type. A boss reading the banner went hunting for a chair. The
>   wording came from the CEO panel's mini-office, which really does have a
>   `.guest-chair` — but that is a different surface, behind a modal. The
>   banner now uses the floor's own word: **the room is the source of truth
>   for what is in it.**
> - **The meeting door's accessible label still read "— start a stand-up".**
>   The banner had been corrected for precisely this error (the door seats
>   the team in the *meeting room*; the stand-up is a separate modal behind
>   🌅 STAND-UP / `u`) — but the correction landed on the banner and never
>   on the control's own label. So the wrong sentence kept shipping to
>   **screen readers: the one audience that cannot see the banner that
>   replaced it.** Same shape as fixing a toast and leaving the state it
>   described (§5's `doing` bug).
>
> Method note: the first pass of this check used the CEO panel's class
> names (`.guest-chair`, `.meeting-door`) against the floor and concluded
> both were missing entirely. They weren't — the floor classes them
> `.px-couch` and `.px-meetdoor`. **A DOM query that finds nothing is not
> evidence of absence until the selector is verified.**

> ✅ **Walked the first run again, on a genuinely wiped install
> (2026-08-06).** Everything fixed in this session had been measured on a
> floor full of test debris — eight ex-coworkers, dozens of activity rows,
> a full vault. Wiped both halves (localStorage *and* the file-backed state
> dir) and walked §3 as a new boss.
>
> **The promise holds.** Front desk offers Claude · Codex · Llama · Hermes,
> each with a plain-words found-line and a `powered by` chip, and a scan for
> the §6 banned terms (*system prompt · API key · model: · temperature ·
> token · backend · driver · inference*) came back **clean**. Hired Llama
> → `1 HIRED`; created a task, assigned, **▶ START** → `1 WORKING`; the
> delivery filed itself as a 718-byte note with the local date and a
> Working footer. Also correct on a clean floor: `⌗ ROOMS` with **no**
> badge, **no** attention pill, and the out-tray's single true empty line.
>
> **What it caught.** The Working footer listed *one* source when the
> coworker had made *two* visits. `workingNotes` fell back to `continue`
> for argument-less tools — `MEMORY_LIST` takes no argument, so
> `visitLine` returns null and the visit vanished from the record. The live
> surfaces had already been given the placard fallback; the filed note, the
> one record that outlives the session, was the surface still forgetting.
> **Under-reporting the working is the same failure as over-reporting it.**
>
> **Still open, now with a concrete instance.** The same delivery contains a
> *fabricated file listing* — Llama wrote `[MEMORY_LIST]` and then invented
> three notes (`decisions/auth.md`, `preferences.md`, `projects/mdc.md`) for
> a vault created minutes earlier. This is the model confabulation logged
> as unclosed above: the office's own visit block reports the truth, and
> nothing the coworker types can forge that block, but its **prose** still
> reaches the cabinet. Stripping model prose is not the answer; the fix
> belongs in the prompt and in giving an unexecuted tool call an explicit
> refusal rather than silence.

> ✅ **Don't hand a coworker back its own guesswork (2026-08-06).** Chased
> the fabrication above to its mechanism, and it was ours.
>
> Every tool hop pushed the model's whole buffer back as its own turn,
> followed by the real `[TOOL_RESULT: …]`. Correct for the text *before* the
> marker; wrong for everything after it. Anything written after a call was
> produced **before the tool ran**, so it cannot be based on the result —
> and a small model will cheerfully write the result it expects. The old
> behaviour then replayed that invention as something the coworker had
> *said* and put the true listing underneath as a contradiction: the worst
> available framing, establishing the fabrication as prior context and
> asking the model to reconcile.
>
> `upToToolCall()` cuts the hop buffer at the marker. The coworker still
> sees that it asked; what it never sees is the answer it made up. `raw` is
> the exact matched text and all three detector paths (bracket, JSON,
> harmony) supply it, so an unrecognised shape leaves the buffer untouched
> — never truncate blind.
>
> **Evidence, and its limits.** Same prompt, clean journal, before vs after:
> the pre-fix run invented `decisions/auth.md · preferences.md ·
> projects/mdc.md` for a vault minutes old; the post-fix run wrote
> "*empty memory folder Agents/Llama/*" and then "my memory is empty, so I
> have no notes to list." That is one run of a stochastic model — evidence,
> not proof. The mechanism is unit-tested (7 checks); the live run is
> consistent with it.
>
> **A fabrication that reaches a stored record becomes context.** Re-running
> the prompt against the *poisoned* state reproduced the invented filenames
> exactly, because the pre-fix delivery had been written into the filed
> note, the task result and the activity log, and the journal feeds the
> prompt. The fix prevents new fabrications; it cannot un-write an old one.
> Verifying it therefore required wiping state first — testing against
> poisoned state would have looked like a failure and hidden a working fix.

> ✅ **A template is not an argument (2026-08-06).** The same clean run threw
> up a smaller sibling: a coworker emitted `[BROWSER_FETCH: <url>]` —
> copying the shape straight out of its own tool docs — and the office
> executed it, spent one of four tool hops, and played
>
> > 🌐 Read \<url\>
> > `Browser fetch error: url must start with http:// or https://`
>
> on the floor as a real visit. It was never a real attempt, and §4 says a
> prop visit plays only while that tool is *really* running.
>
> `placeholderRefusal()` declines before any event fires, so the floor plays
> nothing, and hands the model a correction instead of silence — the point
> being that an unexecuted call which says nothing is exactly what invites
> the coworker to invent the result (see `upToToolCall` above).
>
> The rule is **narrow on purpose**: the whole argument must be a single
> angle-bracket token. `<url>`, `<path>`, `<your-file.md>` are unambiguously
> template syntax; anything with content outside the brackets — `a<b`,
> `compare <a> and <b> tags` — runs untouched, because a wrong refusal costs
> the boss a real tool call. 10 checks cover the near misses.
>
> **Evidence, stated honestly: the refusal path was never observed live.**
> Two attempts to provoke a placeholder produced a real fetch and a
> `[VAULT_NEW:…]` instead — coaxing a specific token out of a stochastic
> model is not a reliable experiment. The rule is unit-tested and the wiring
> is a three-line guard, but "no phantom visit appeared" is equally
> consistent with no placeholder having been emitted. A `console.warn` now
> marks each refusal so the next person can tell those two apart.
>
> Method note, twice over: **both** live readings this session were first
> taken with the wrong scope — one sampled mid-stream and called a
> fabrication fixed, the other queried `.msg-visit` across *all* bubbles and
> attributed a pre-fix run's phantom visit to the current one. Scope a
> measurement to the run you are actually testing.

> ✅ **The wall reports the business now, not just the plumbing
> (2026-08-06).** Stopped bug-hunting and read the Situation Wall as a boss
> would. Four rows: **HQ** healthy · **SEARCH** reachable · **⚒ 3/4**
> runtimes installed · **⚡ work done**. All true, all *infrastructure* —
> a control room that says the lights are on and nothing about whether the
> business produced anything.
>
> Added **📦 N** — deliverables filed to the cabinet. Counted from
> `task.artifactPath`, which is set only when `fileDelivery` actually
> returned a path, so the wall cannot claim a delivery that isn't on disk.
> Hidden at zero rather than showing `📦 0`: a fresh office has shipped
> nothing and saying so on the wall is noise, not news — the same rule the
> attention pill and the payroll row already follow.
>
> This is the out-tray → cabinet loop (§3.6) made visible at a glance, which
> is the north star's actual payoff: work comes in, work ships. Verified by
> driving a real task end to end — the row appeared as `📦 1`, singular,
> at the moment the file landed.

> ◐ **The prompt half of the honesty problem (2026-08-06).** Everything
> above hardened what the *office* says. This is the other lever, and it is
> weaker by nature: what the *coworker* says.
>
> Two changes, both naming a failure the instructions previously only
> gestured at:
>
> - The tool snippet said "output the call and STOP". Procedural, and small
>   models read straight past it. It now names the actual failure —
>   **"NEVER write a tool's result yourself. If you have not been handed a
>   result, you do not have one — do not guess it, summarise it, or list
>   what you think it contains."** — plus a line that the bracketed example
>   is a shape, not a request, since a placeholder call is now refused.
> - The task prompt asked for "what you'll do (1 sentence)", which is what
>   produced memos opening *"I will use the BROWSER_FETCH tool to…"* — §6
>   jargon in a file the boss keeps. Now: **"1 sentence, plain words —
>   don't name your tools."**
>
> **Measured — and later strengthened to three runs.** The filed notes are
> themselves an auditable record, and the cabinet already held a natural
> experiment: same model, same machine, three deliveries spanning the
> change.
>
> | filed | opening line |
> |---|---|
> | before | "I will use the **[MEMORY_WRITE] tool** to create a note…" |
> | after | "I will check my **private notes folder**…" |
> | after | "I will look up a **reliable source**…" |
>
> Two after, both free of tool names; one before, carrying one. Still a
> small sample of a stochastic model, but a better one than the single run
> first reported here — and it cost no new runs, only reading the cabinet.
>
> **Not fixed, and worth being plain about:** the same memo also says *"I do
> have a note on the colors of the rainbow"* when the lookup returned
> nothing. The fabricated *tool result* is gone; a fabricated *claim* is
> not. Prompt wording shifts probabilities — it does not make a small model
> honest, and no amount of instruction will. What the office can guarantee
> is its own record: the visit block is structurally separate, unforgeable,
> and sat directly above that sentence saying the read found nothing. **The
> boss can always check the office against the coworker.** That is the
> guarantee worth having, and it is the one that is actually enforced.

> ✅ **The desk contradicted itself out loud (2026-08-06).** Read a
> coworker's desk as a boss walking past would. Two props, two counts, side
> by side:
>
> > 📄 **5 filed reports** — click to read
> > 📦 **2 deliveries filed** — click to open the latest
>
> Both said "filed"; they disagreed. Measured: Llama's journal held **5**
> entries, of which **2** were tasks and **3** were chat replies.
>
> §5 already settled this for jobs — *"a chat reply or a DM is not a job,
> same as it is not an artifact"*, which is why `agent.tasksDone` left the
> cards — but the rule had never been carried to the papers pile. The
> journal is a legitimate work **log** and chat belongs in it: **the count
> was never wrong, the word was.** The pile now reads *"5 notes in Llama's
> work log"*, and **only the out-tray may say "filed"**, because it is the
> only one counting files that exist on disk.
>
> Same shape as the payroll and FUEL findings: not a broken number, a number
> wearing a claim it hadn't earned.
>
> **The adjacency check, run deliberately.** That bug was only visible
> because the two props sit *next to each other* — either label alone reads
> as plausible. So the same check was pointed at every other pair of numbers
> describing one thing, and the rest came back clean: the Team card's
> **Jobs = 2** matches the two completed tasks (not the five journal
> entries), **Remembers = 0 notes** matches an empty `Agents/Llama/`, and
> the office HUD's **⛽ 12.6K** matches the per-agent **12,617**. Worth
> recording the negatives: §5's ledger and §2's card were already honest,
> and the papers pile was the only outlier.

> ✅ **One ticker row was eating the strip (2026-08-06).** The office pulse
> printed
>
> > `filed "Deliveries/check-your-memory-then-name-a-primary-colour.md" to the cabinet 🗄`
>
> — wide enough on its own to push every other event off the ticker, and the
> row directly above it already read `finished "Check your memory then name
> a primary colour" ✓`. The boss got the same title twice: once in prose,
> once as a hyphenated slug with a file extension, which is the *machine's*
> name for it (§6). Every other activity row is capped; this was the only
> one that wasn't.
>
> Now `filed to Deliveries 🗄` — **where** it landed is the part the boss
> doesn't already know from the line above, and the file itself is one click
> away on the desk out-tray. The pulse reads as a sequence again:
> *picked up …* → *finished … ✓* → *filed to Deliveries 🗄*.

> ✅ **An empty column is not a new office (2026-08-06).** Opened the views
> never exercised this session. **Calendar is good** — *"your business by
> day · tasks when raised · missions when they wrap"*, three dated entries
> with owner, priority and status. No changes needed.
>
> The Tasks board contradicted itself, though: header **"3 of 3"**, inbox
> column **"No tasks yet — start from one of these"** with the full starter
> card set. Both describing the same three tasks. The onboarding state was
> gated only on the *inbox column* being empty, so it came back every time
> the boss cleared their queue — greeting an office three deliveries deep as
> if it had never run anything. A cleared column now reads *"Nothing waiting
> — hit + NEW to add one."*
>
> **The first version of that fix was wrong**, and only checking it caught
> it: `TaskBoard` receives the **filtered** list (TasksView applies the
> search box and the show-completed toggle), so gating on `tasks.length`
> would have shown onboarding to an established boss whose search matched
> nothing. `totalCount` is now passed unfiltered and is the only thing that
> may trigger it. Verified all three: cleared, filtered-to-nothing, and
> genuinely empty — the starter cards return only in the last.
>
> 🚨 **Finished work was queuing itself for delegation (2026-08-07).** Looked
> at the floor with a genuinely populated office for the first time — two
> coworkers, six deliveries, a stand-up archived — and the Inbox strip read
> **1 waiting**, offering to delegate *"Stand-up — Aug 7"* to Llama or Mika.
> A completed end-of-day report, with an **Assign to…** dropdown on it.
>
> The filter was `status === 'inbox' || !t.assignedTo`. The `||` is
> deliberate — it surfaces unassigned tasks that somehow aren't in `inbox`
> — but an archived stand-up is `status: 'done'`, `assignedTo: null`, so it
> matched. Dropping it on a desk would have re-run a finished document as
> fresh work.
>
> **A terminal task is never in the queue.** The filter now excludes `done`,
> keeping the original intent for everything in flight. Verified: the strip
> went from *1 waiting* to *"No tasks waiting"* with count **0**, and the
> report is still on the board under **DONE · 4** — out of the queue, not out
> of the record.
>
> This one only appeared once the office had a *history*. Every earlier check
> ran against a floor where finished work had been deleted or wiped.

> 🚨 **"✓ archived to Docs" was archiving nowhere near Docs (2026-08-07).**
> Two coworkers unlocked the end-of-day **stand-up**, which a one-coworker
> office could never exercise. Ran one end to end and it works: preflight
> states the real budget (*"2 of 2 agents · cap 220 tok/each · 90s timeout ·
> ⚠ 2 local models — heavy on a VM"*), both agents reported in
> TODAY/BLOCKED/TOMORROW, the CEO synthesised, and the modal reached *done*.
>
> Llama's report even referenced *"Mika's request for perspective"* — the
> handoff delivered in the earlier fan-out had become shared context. Two
> coworkers genuinely worked together and each knew it.
>
> Then the archive claimed **"✓ archived to Docs"**, and the cabinet had no
> `Docs/` folder at all. `archive()` builds a done TASK carrying the full
> report and hands it to `onArchiveStandup`, which does `setTasks(...)` —
> nothing goes near the vault. The archive is genuine and the report is
> readable; the signpost pointed at a place that does not exist.
>
> Same shape as the *Sent → Drafted* fix in §5, on the one artifact a boss
> would rely on at the end of a day. The copy now says **"✓ saved to your
> task board"**, verified by finding *"Stand-up — Aug 7"* on the board after
> a reload.
>
> **Swept the class.** A success message that names a *destination* is a
> checkable claim, so all five in the app were checked:
>
> | claim | verdict |
> |---|---|
> | `✓ archived to Docs` | **false** — fixed above |
> | `filed to <folder> 🗄` | true — six files on disk |
> | `N deliverables filed to the cabinet` | true — 6 = 6 |
> | `Clickable link filed at <file>` | honest — `url`/`file`/`mode` all come from the server's own response |
> | `✓ Key saved to your container` | honest — shown only when the server reports `serverStored`, with a separate *"Stored in this browser — your container will pick it up"* for the other case |
>
> The credential one is the one that would matter most and it is the most
> careful: it never claims server storage on the client's say-so. Recording
> the negatives so this isn't re-swept.
>
> **Left as a product decision, not made silently:** whether an end-of-day
> report *should* live in the cabinet (`Docs/`) rather than the task board.
> Filing it there is defensible — it is a document, and §3.6's machinery
> exists — but it needs the vault-unconfigured path handled, or the fix
> re-creates the very claim it removes.

> ✅ **Multi-agent verified — the north star's actual claim (2026-08-07).**
> Every run in this session until now used **one** coworker, which meant
> *"one office where all your AIs work together"* had never been tested.
> Hired a second free local coworker (Mika, on the same Ollama brain) and
> fanned one request to both.
>
> It works, and it stays honest under load:
>
> - **`2 WORKING`** while both ran, **`0 WORKING`** when they finished — the
>   §4 authority tracked two concurrent runs correctly.
> - Both replied into the same thread under distinct labels (*Llama ·
>   Generalist*, *Mika · Head of Inbox Wrangling*).
> - Each got its **own** attributed visit block — `🌐 Read
>   en.wikipedia.org/wiki/Blue` twice, one per coworker — so the office's
>   record of who did what survives concurrency.
> - Mika's empty bubble showed *"still waiting on that brain — it may be
>   warming up"* while the second local model cold-loaded. That fix was
>   built for one model and held for two.
>
> **One finding, recorded not fixed.** Llama tried to delegate:
> `[DM_TO: Mika] Can you provide your perspective on this request?` —
> written **inline**, with no newline and no closing `[/DM_TO]`. The parser
> requires the documented block form, so it never matched, was never
> dispatched, and remained on screen as raw syntax. The boss sees a handoff
> that reads as sent and never happened.
>
> The parser is right to be strict — a loose one would fire on prose that
> merely mentions the marker. The fix is to *notice*: the office knows the DM
> queue came back empty while the reply contains an opening `DM_TO`.
>
> ✅ **Shipped next pass (2026-08-07).** `unsentHandoff()` says one sentence —
> *"the handoff to Mika didn't go out … Nothing was sent; ask them yourself
> with @Mika"* — wired at all three agent paths. Same shape as
> `placeholderRefusal`: an unactioned request that says nothing invites a
> false belief.
>
> **Deliberately conservative:** if *anything* was delivered on that run it
> stays silent, so a well-formed handoff alongside a malformed one is missed
> rather than risking a false alarm on a run that really did delegate.
>
> Both directions verified live, which mattered: an ordinary reply produced
> **no** warning, and a genuine unsent handoff produced one. In between, a
> run that appeared to be a false negative turned out to be the conservatism
> working — that reply said *"[Llama · Generalist] was DM'd for context
> before this request"*, i.e. a handoff **had** been delivered, so the rule
> correctly stayed quiet. **I had labelled it a bug before reading the
> surrounding sentence.**

> 🚨 **The manual hire form ignored what the office knew (2026-08-07).** Set
> out to verify multi-agent — the north star is *"all your AIs work
> together"* and this session had only ever run **one** coworker — and hit
> this on the way to hiring a second.
>
> §3's front desk is honest: it offers only brains it **found on this
> machine** ("We found your Claude subscription…"). `NEW HIRE →`, the manual
> form behind it, offers all **27** and defaults to
> `anthropic:claude-haiku-4-5`. On a fresh install — the exact state where
> the topbar is already showing **⚠ ADD AI KEY** — a boss could build a
> coworker, hire them, drop a task on their desk, and only then learn the
> brain was never signed in. The one locally-runnable option was a single
> entry among 27, and nothing marked it.
>
> The office already had the answer: `hasUsableKey` is what drives that very
> chip. The form now asks it, and names the route out (§7).
>
> **The first version of this fix was wrong, and only checking cleared it.**
> `hasUsableKey({provider:'ollama'})` answers *"is Ollama configured as the
> DEFAULT provider"* — i.e. has a model been chosen in Settings — which is
> empty here. But a per-agent brain **pins its own model in the id**
> (`ollama:llama3.1:latest`), so the global setting is irrelevant. The
> warning therefore did **not** clear when the working local brain was
> selected: a false alarm on every hire, which is worse than no warning.
> Feeding the pinned model into the probe fixes it. Verified both states:
> the unsigned default warns, the local brain shows the ordinary hint.

> 🚨 **The morning report said the business produced nothing (2026-08-06).**
> Exercised the day-2 surface for the first time — the HQ Gazette, shown
> once on return after >4h away. Forced one by backdating `lastSeen`.
>
> Its headline tiles read **ACTIONS 27 · DELIVERABLES 0**. Six notes had
> been filed to `Deliveries/` in that window; the activity log held six
> `artifact` rows. The one screen whose entire job is *"what did my business
> produce while I was away"* reported that it produced nothing.
>
> `DELIVERABLES` counted `report.receipts.length` — **receipts**, which are
> approval and tool records, not things filed to the cabinet. It now counts
> `action: 'artifact'` events, the same source the Situation Wall's 📦
> counter uses, and those are logged only when `fileDelivery` really
> returned a path. The anchored sub-line stays on receipts, relabelled, since
> that one genuinely is about receipts. Verified: the same gazette now reads
> **DELIVERABLES 6**.
>
> **Verified negative, same surface:** `▶ REPLAY THE NIGHT` dispatches
> synthetic `cafresohq:agentTool` events to re-enact the night on the floor,
> which looked like a §4 violation ("a prop visit plays only while that tool
> is REALLY running"). Measured during a replay: `0 WORKING` stays 0 and the
> status pip stays `idle`. The re-enactment moves sprites but never touches
> `agent.status`, so the office never claims current work. Correct as built.
>
> Also, a smaller silent cap on the same screen: the per-coworker columns
> `slice(0, 4)` with nothing saying so, on the one screen meant to summarise
> the whole night. It now appends *"+N more coworkers were busy — full log in
> the Team inbox"*. **That branch is unverified** — reaching it needs five
> hires and a four-hour absence, and this session runs one free local model.
> The modal was confirmed to still render, and the line correctly stays
> hidden at one coworker. (The per-coworker event list also caps at 5, but
> is self-labelling: its header prints the true total, `LLAMA · 27`.)

> ✅ **Swept the dead-end class (2026-08-06).** The mission block turned out
> to be one of a family: **a refusal that states the reason and not the
> route**. Swept the other blocked and empty states.
>
> Mostly clean, and the negatives are worth recording. The stand-up's
> *"nobody participating"* case disables START over a list of agent rows the
> boss can click back on — the way out is already on screen. The
> `⚠ ADD AI KEY` chip opens Settings → Connections. The task board's empty
> inbox offers starter cards.
>
> One genuine dead end: **the stand-up with nobody hired.** START was not
> rendered at all, and the body showed a preflight reading *"0 of 0 agents ·
> cap 1200 tok/each · 45s timeout"* over an empty list — a technical readout
> about a meeting with nobody in it, and no way forward. It now reads *"No
> coworkers yet — a stand-up is your team reporting back; hire someone first
> and they'll have something to report"* with a **+ HIRE YOUR FIRST
> COWORKER** button that closes the modal and opens the front desk. Words
> would have been enough for §7, but every other empty state on the floor
> offers the *action* (a vacant room shows "+ HIRE", the empty board shows
> starter cards), so this one does too.
>
> Verified both branches, since the change split one conditional in two: with
> a hire, the preflight and `▶ START (1)` are unchanged; with none, the new
> empty state appears, the "0 of 0" readout is gone, and the button really
> lands on the front desk. Fixture restored by re-hiring afterwards.

> ✅ **The night shift refuses honestly — but was a dead end (2026-08-06).**
> Exercised the mission modal for the first time. The gating is **right**:
> with only a Generalist hired (`tools: ['web']`, no vault), the agent
> option renders `disabled`, `▶ START RESEARCH` renders `disabled`, and the
> requirement is stated on the form. The office will not launch an overnight
> mission it knows cannot write a single note — exactly the refusal the rest
> of this document argues for.
>
> *(`🌙 SCHEDULE` and `▶ RUN NOW` sit together above the submit as a
> when-to-run pair, not a second way in. Checked their coordinates before
> assuming a bypass existed.)*
>
> What was missing is §7's other half: *"every failure is one honest
> sentence **plus** try again / ask differently / pick another coworker."*
> The hint read `must have Web Search and Vault Notes tools enabled` and
> stopped there — a boss whose only hire lacks the tool met a disabled
> agent, a disabled button, and no route out. Tools are editable in
> **Settings → ROSTER** (the inspect panel shows them read-only), so the
> hint now names it: *"needs Web Search and Vault Notes — turn them on in
> Settings → Roster."* Verified the copy renders and START stays disabled.

> ✅ **Two copies of one deliverable (2026-08-06).** §3.6 files host-side
> because filing *"can't depend on the coworker cooperating"* — true for the
> front-desk hires, which hold no vault tools at all. But the **specialist**
> roles are the opposite case: Kip is told to save a research note to
> `Research/<topic>.md`, Sloan to render a real `.pptx`, Quill a `.docx`.
> They file deliberately, at a path they chose and named to the boss.
>
> The host then filed a **second** copy at `Deliveries/<slug>.md` and
> pointed `task.artifactPath` — the out-tray's "open the latest", the
> delivery sheet — at its own duplicate rather than the specialist's real
> file. `agentFiledPath()` now defers to the coworker when the run actually
> wrote to the cabinet.
>
> Only cabinet writes count. **`MEMORY_WRITE` / `MEMORY_APPEND` are
> excluded** (the coworker's private `Agents/<name>/` folder is not a
> deliverable) and so is `FILE_WRITE` (workspace, not vault). Getting that
> wrong would suppress filing for a task that produced no artifact at all —
> worse than a duplicate — so it is pinned by 9 checks.
>
> **Verification is partial, and honestly so.** The default path was
> confirmed live: a Llama task still filed to `Deliveries/` with
> `artifactPath` set. The *deferral* path was not — it needs a specialist on
> a cloud brain, and this session is restricted to the free local model. It
> rests on unit tests.
>
> Reading that run's real filename also turned up a small bug the function
> hid: `slugify` trimmed hyphens **before** capping at 56, so a title cut
> mid-word filed as `…the-boss-likes-bullet-.md`. It trims after the cap now.

> 🚨 **The office deleted the thing it demanded (2026-08-06).** Applied the
> same lens — *where else does the office ask a coworker for something it
> already has?* — to the ACK protocol, and found something worse than
> duplication.
>
> The instruction ended: *"ALWAYS end completed handoffs with a
> `[ACK: completed: …]` containing a 3-bullet result + risks + next-action
> so the boss can move fast."* The office then **stripped it**. `stripAcks`
> removes every marker before a reply is shown, stored or filed, and
> `visibleReply` only falls back to an ack note when everything else is
> empty. Run against the real helper:
>
> | given | boss sees |
> |---|---|
> | `Here is what I found.`<br>`[ACK: completed: • red • blue • yellow]` | `Here is what I found.` |
>
> The result, the risk and the next action — the three things the
> instruction demanded — deleted by the office that asked for them. Every
> coworker that obeyed faithfully lost its own summary.
>
> Applying the lens to the four states: **`in_progress` and `completed`
> duplicate `agent.status`**, which §4 makes the *only* authority on whether
> someone is working — and neither drives any UI (`extractAcks` is consulted
> solely to decide whether to clean the text; the code says "we do NOT
> re-transition here"). **`blocked` and `awaiting_reply` are the real half**:
> a coworker who needs vault access, or is waiting on someone, knows
> something the floor cannot see.
>
> ACK now asks only for that half, and ends with the correction that
> matters: *"Put your ANSWER in the reply itself, never inside a marker:
> markers are stripped before the boss reads it."* The old states stay
> **parseable** — histories contain them — but are no longer taught.
>
> Verified live on a task that invites a summary: the three bullets landed
> in the delivery, where they survive. A test now pins the *property* rather
> than the wording, so the instruction can never drift back toward a
> container the office empties.

> ✅ **Stopped asking coworkers to narrate (2026-08-06).** Read the filed
> notes as a boss opening them, and every one began the same way:
>
> > *I will look up a reliable source for colors to find one that is not blue.*
> > *The color "Green" is often cited as an example…*
>
> The answer was the **second** line, in every delivery, because the task
> prompt asked for it: *"Report: what you'll do (1 sentence), then deliver
> the result."*
>
> That clause was buying nothing. The office already reports what a coworker
> is doing, and reports it better: the desk bubble says what they are doing
> **now**, the visit block records **where they went** and cannot be forged,
> and the ticker carries both. Asking the coworker to narrate it as well
> produced a second, worse copy of a signal we already had — and the second
> copy is the one that gets **filed and kept**.
>
> The prompt now asks for the result and says why: *"that is what gets filed
> and kept. Don't narrate your steps; the office already shows the boss what
> you're doing."* Next delivery, in full:
>
> > `# Name the capital of Japan`
> > `*Delivered by Llama · 2026-08-06*`
> > `Tokyo is the capital of Japan.`
>
> **Counter-checked, because the claim was "the boss loses nothing":** the
> activity log for that same task still reads *picked up … 📁* → *finished …
> ✓* → *filed to Deliveries 🗄*. The office narrated the work; only the
> duplicate inside the artifact went away.

> ✅ **The cabinet works (2026-08-06).** Verified the payoff surface end to
> end for the first time: the vault tree expands `📁 Deliveries`, lists all
> three notes, and clicking one opens `vault-edit-pane` + `vault-preview`
> with the note rendered. Before a note is selected the graph pane takes the
> full width, which is why the layout first *looked* like a 3-column layout
> missing a column — it isn't. No changes needed.
>
> Method note, a third time: two readings during this check were taken
> against a precondition that was never established. Deleting the tasks
> "failed" and looked like a regression — the deletes were being refused by
> `window.confirm`, which guards tasks carrying agent output. **The guard is
> correct product behaviour**; the test was fighting it. Confirm the state
> you think you set up before trusting what you read from it.

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

> ✅ **Pass three — the character-creation form itself (2026-08-06).** Pass
> two covered the quick-hire front desk and the candidate cards; it never
> reached "NEW HIRE →", the manual form for building a coworker from
> scratch. Loaded it and found three violations in one screen: the persona
> field was labelled **`SYSTEM PROMPT`** (the exact never-say term — §2
> already calls this "job description" and has for a while, this form just
> never got the memo), the brain picker was labelled **`MODEL`** (the same
> "model as a selector" ban the coworker card was fixed for), and its hint
> read **"backend is encoded in the id (anthropic / lmstudio / ollama)"** —
> "backend" plus three raw driver names, in the single most core "grow
> your business" action in the app. Relabelled to `JOB DESCRIPTION` /
> `BRAIN`, hint rewritten to "each option is one real brain, grouped by
> who runs it" — same fact, no plumbing words. The picker's own dropdown
> options keep real model ids, same as Settings: you're choosing a
> specific one, that part genuinely needs the raw list.
>
> Verified live end to end: hired a candidate ("Vera") through the fixed
> form, watched her walk onto the floor for real, and her roster card
> reads `Brain · Sonnet` — clean, via the same `brainName()` every other
> surface already uses.

Raw model IDs, JSON, and driver names may appear in desktop-mode surfaces and
settings — never on the floor, the cards, or onboarding.

## 7. What newcomers never see

- A terminal (Living Floor desktop mode keeps it, behind the door).
- A blank prompt box as the primary call to action.
- Vendor logos as coworker identities.
- Settings as a prerequisite to the first task.
- Raw error dumps — every failure is one honest sentence plus "try again /
  ask differently / pick another coworker."

> ✅ **Shipped 2026-08-06 — one failure, one story, and the verb on the row.**
>
> A single real failed run (no brain configured) was watched across every
> surface it touches at once. All four told the boss something different:
>
> | surface | what it said |
> |---|---|
> | floor bubble | "hit a snag — that brain isn't signed in yet" ✅ |
> | inbox row | "**Kenji** that brain isn't signed in yet" — no verb |
> | escalation toast | "2× **unknown** failures across team / Last cause: unknown. **Inspect error and retry**" |
> | chat bubble | "The shared Cafreso brain isn't responding — it may be **waking up**" |
>
> Nothing was waking up and the cause was not unknown: two surfaces named it
> exactly while the loudest two claimed ignorance. The fix is one classifier,
> two shapes — **`snagCause()`** returns the clause, **`snagSentence()`** is
> exactly `'hit a snag — ' + snagCause()`. Surfaces that bring their own
> subject take the clause; nobody regexes the spine off the sentence again
> (that is what produced the verbless inbox row). Pinned by three tests.
>
> - **Escalation speaks office.** `kind`/`actionNeeded` never reach the boss;
>   the headline carries what escalation actually knows that a single row
>   doesn't ("*Sora has hit 2 snags in five minutes*", "*2 of the team are
>   hitting the same wall*") and the cause underneath is the same sentence
>   the floor gave. "Across team" now counts **coworkers, not messages** — it
>   was announcing one coworker failing twice as a floor-wide pattern, which
>   the per-agent rule already covered.
> - **Escalation lands in the room it's about.** Every note was filed under
>   TEAM "so the boss sees it in context" — including notes about one
>   coworker, raised seconds after the boss watched that coworker fail from
>   the DIRECT tab. One coworker → DIRECT; a pattern → TEAM. **An alert
>   nobody is in the room for isn't context, it's bookkeeping.** (Its
>   pointer also named "INBOX → Failed", a tab that does not exist.)
> - **Retry sits ON the row.** The one verb that answers a failure was hidden
>   until you clicked the row open — on the surface whose entire job is
>   "something needs you", and the same shape as the dead attention banner.
>   It now sits inline beside *What happened?* (which still holds the raw
>   cause, §7). Acting on a row marks it read, so the counter means "not
>   dealt with yet"; a retry that fails again lands a fresh unread row and
>   the count rises, which is the honest answer rather than a tidy one.
> - **The button now does what the row says.** Retry re-sent "the newest
>   failure for this agent" regardless of which row you clicked — tolerable
>   buried, a lie once it's on every row. Rows carry their `messageId`. And
>   because a retry mints a *child* dispatch (the parent stays `failed`
>   forever), "already dealt with?" is a question about the child: a second
>   click while the retry streams would otherwise quietly order the same
>   work twice.

> ✅ **A created workflow was invisible the instant it was created
> (2026-08-06).** Built one live for the first time this session — named
> it, chained two tasks, hit CREATE WORKFLOW. It worked: both tasks
> correctly gained `chainTo`/`dependsOn`/`workflowId`. Then closed the
> modal and reopened it, and there was no trace it had ever existed — no
> list, no count anywhere in the app, the nav chip just said "WORKFLOW"
> with nothing to distinguish zero from ten. `WorkflowModal` had been
> receiving a `workflows` prop, built for exactly this, since it shipped —
> nothing ever read it.
>
> This isn't a copy fix like the rest of this section; it's a half-built
> feature completed to match what it already promised ("chain tasks" —
> chaining that vanishes on close isn't that). Wired the prop up as a
> compact **YOUR WORKFLOWS** list at the top of the same modal: name and
> honest progress ("0/2 done", counting real task status, never invented).
> Nav chip now carries a count, the same pattern `MEETING`/`RESEARCH`
> already use. Also closed a correctness gap the missing list made easy to
> hit blind: a task already claimed by one workflow (`t.workflowId` set)
> could be silently re-added to a second, overwriting its `chainTo`/
> `dependsOn` with no warning — excluded from "available tasks" now.
>
> Verified live end to end: created "Draft Pipeline Test" (2 steps),
> confirmed it now lists with "0/2 done", dispatched step one to Miko in
> this no-brain test environment, watched it snag and correctly return to
> `inbox` with `chainTo`/`workflowId` intact (not orphaned), and confirmed
> the list still honestly reads "0/2 done" after — a snag is not progress.
> All 12 suites green.

> ✅ **The Calendar was a creation log, and Research was dead on load
> (2026-08-06).** Opened the Calendar as a boss would and found a view
> named for *when things happen* that only ever showed `createdAt` — every
> row a record of when someone typed something. Its header carried a
> standing IOU, "scheduling coming with stand-up", for a feature that had
> since shipped somewhere else entirely.
>
> Live missions are the scheduled work the app already has: a running one
> knows exactly when it ends (`startedAt + durationMs`). They now land on
> the day they wrap, marked as forward-looking so they don't read as one
> more past entry, and the header says what the view shows instead of what
> it might one day. Nothing is invented — a mission that isn't running
> contributes nothing, verified in both directions (row present while
> RUNNING, gone the moment it paused). Night-shift schedules carry a
> `nextRunAt` and belong here too, but they live behind the container
> bridge; they are left out rather than faked.
>
> ⚠️ **Setting out to test that turned up a much worse bug.** A research
> mission could not be started at all on a fresh page load. Both mission
> forms seeded `agentId` with a lazy `useState` initialiser — which runs
> once, at mount — and these modals mount *with the app*, below their own
> `if (!open) return null`. The roster loads asynchronously, so at that
> moment `agents` was `[]`, the seed resolved to `''`, and it never
> recovered.
>
> The failure was invisible and total. `<select value="">` with no matching
> option still **shows** a coworker, so the form read as complete while
> START stayed permanently disabled, with nothing on screen explaining
> why — the headline "put a coworker on a long-running job" action, dead,
> silently. The only escape was to re-pick the coworker the form already
> appeared to have. Diagnosed by reading React's own props off the fiber
> after the DOM and the state disagreed: `select.value` said `a_tir7pj`,
> React's `value` prop said `''`.
>
> `useValidAgentId` now re-seeds whenever the roster changes and the held
> id isn't in it — which also covers the case that made this dangerous
> rather than merely broken: **a coworker let go while selected**. The
> state always names someone who exists, so the select can never display a
> choice the app doesn't hold. Verified on a cold load: state resolves to a
> real agent (correctly preferring the only one with both web + vault),
> START is live untouched, and a mission runs end to end.

> ✅ **"21 need you" was one problem (2026-08-06).** Stopped grepping and
> just looked at the office as a boss would. The loudest thing on screen
> was the attention pill: **⚠ 21 need you**. Counted what was actually in
> it — 21 unread rows, every single one the same root cause ("that brain
> isn't signed in yet"), re-raised across seven coworkers and several runs
> each, in four different wordings (two of them left over from before the
> failure-language fixes).
>
> One decision to make. The wall said twenty-one. **A chief of staff who
> hands you the same note twenty-one times isn't being thorough — they're
> burying the one thing you have to do.** The counter was answering "how
> many times was something reported", not "how many things need me", and
> those diverge exactly when the office is in trouble, which is when the
> number matters most.
>
> `app/attention.jsx` (14 checks in `scripts/test_attention.py`) groups
> identical reports from the same coworker into one item carrying its own
> `×N`, and the count counts items. The honesty constraints are what the
> tests pin hardest:
>
> - **Different problems never merge.** The key is the whole sentence, so
>   `failed "Draft the brief"` and `failed "Ship the page"` stay two items
>   — two pieces of work stuck is not one thing repeated.
> - **Nothing is hidden.** The row states its own repeat count, and the
>   grouping applies *only* to the Needs-attention queue — Activity stays a
>   complete chronological log of every event (header still read 59 EVENTS
>   with the queue at 13).
> - **Clearing a group clears every occurrence.** Marking only the newest
>   read would drop the count by one and the row would return unread on the
>   next render — the loop this exists to end.
>
> One shared helper drives the office pill, the Team nav badge and the
> inbox tab, so the three can't drift. Verified live: 21 → 13 on all three
> at once, a `×2` row reads "latest of 2", opening it moves 13 → 12 (one
> item, not two), and both underlying entries persist as read.
>
> ✅ **…and most of the rest were ghosts (2026-08-06).** Grouping fixed the
> double-counting; it didn't ask whether the items were the boss's problem
> at all. The pill had climbed back to **⚠ 15 need you**. Counted them: 12
> belonged to **Aiko, Kenji, Sora, Miko, Taro and Hana** — six coworkers no
> longer on the roster.
>
> Every one was unactionable *by construction*: you cannot retry a run for
> someone who does not work here, and "that brain isn't signed in yet"
> pointed at a brain nobody uses any more. A queue that only grows, and
> mostly with things you can't act on, is a queue a boss stops reading —
> which costs them the one item that is real.
>
> `onRoster()` drops them from the **queue**, never from the log — the same
> split grouping already relies on: *"what needs me"* is a different
> question from *"what happened"*. Two deliberate refusals to over-filter:
> a missing roster changes nothing (under-claiming beats wrongly hiding the
> boss's work), and an entry with no coworker on it is office-level and
> always survives, because the office hasn't been let go.
>
> **The filter had to land on the list as well as the count.** A pill
> reading 3 over a list of 15 would be a worse bug than the one being
> fixed, so `onRoster` runs in `AgentInbox`'s attention tab too.
> Verified live, all four surfaces at once: office pill **15 → 3**, nav
> badge 3, tab "Needs attention · 3", and exactly 3 rows listed — every one
> of them Llama, who is still on the payroll and whose failures retry.

> ✅ **Walked §3 "first run" for real (2026-08-06).** Every check this
> session had been run against an environment full of accumulated test
> state — eight coworkers, 59 activity rows, old receipts. That is not
> what an MVP is judged on. Wiped both halves of the store (localStorage
> *and* the file-backed state dir) and opened the app as a brand-new boss.
>
> Most of it holds up: the Getting Started checklist, the CEO's welcome,
> a floor of vacant units each offering `+ HIRE`, an honest empty inbox.
> Hiring from the front desk asks for consent in plain language —
> *"Claude works with computer access — reading and writing files and
> running commands on this machine. Every action is logged and pauses for
> your approval. Bring them aboard?"* — and completing it advances the
> checklist 0/6 → 1/6, lands the room with a `reporting for duty` bubble,
> and marks the nameplate `🛡 CLAUDE · CODING AGENT`.
>
> One thing did not hold up, and it was the *first sentence the office
> ever spoke*: the ticker read **"All agents elevated · cafresohq:sonnet
> pinned"**. A raw model id and two internal words (§6 bans both), fired
> by a one-time schema migration whose flag lives in localStorage — so it
> runs for a **new** install too, where the roster is empty. The office's
> opening line, on a floor of vacant desks, was a developer migration
> notice about zero coworkers.
>
> The ticker is the office's news feed ("Kenji picked up …"). Schema
> housekeeping is not news, so it no longer says anything; the migration
> still runs, silently, which is what housekeeping should do. Swept the
> rest of the first-run surface for the same class of leak (`cafresohq:`,
> other driver prefixes, "system prompt", "API key", "backend") — clean.

> ✅ **The onboarding checklist's buttons were dead in windowed mode
> (2026-08-06).** Continued the first-run walkthrough to §3 step 5,
> "Create your first Project", and clicked its CTA. The breadcrumb moved
> to WORKSPACE — and nothing else happened. The Staff Roster stayed in
> front. `openWindows` held only `team`.
>
> Cause is the one this doc already names: **in windowed mode
> `setActiveView` is a silent no-op**, and four of the six checklist CTAs
> called it directly. The same failure as the dead attention banner
> (0d51159), on the surface whose entire job is walking a brand-new boss
> through their first five minutes — click "New Project →", see nothing,
> conclude the product is broken.
>
> Swept the rest of the file rather than patching the one button: **26
> navigation call sites** now route through `navTo` — the coach marks
> (same onboarding family, same bug), the inbox's "Open task board →",
> the 📁 MEMORY buttons, the notification-centre jump, both the vault
> open-note paths, the number-key and `m` shortcuts, and all 13 command
> palette entries. Four `setActiveView` calls remain and are correct:
> `navTo`'s own body, the deliberate workspace-state restore, the
> mobile-only mount redirect, and the mobile bottom nav (where
> `navTo` reduces to `setActiveView` anyway).
>
> Ordering trap worth recording: `navTo` is declared ~2800 lines below
> most of its new callers, so naming it in a `useMemo` deps array is a TDZ
> crash — one this file has sprung three times. `goTo` wraps a live
> `navToRef`, the same discipline `onApprovalRequestRef` already uses:
> never stale, safe to call from any handler declared above it.
>
> Verified live by reproducing the exact failure: with the roster window
> in front, "New Project →" now opens a WORKSPACE window and raises it
> (z:3 over z:2). Projects itself is sound — its empty state's inline
> "Classic" button does flip mode and reveals a working `+ ADD`. (An
> earlier read that it was dead was a stale screenshot frame, not a
> defect — the DOM had already re-rendered.)

> ✅ **Verifying the sweep found the half I'd missed (2026-08-06).** Went
> back to check the previous commit's 26-site navigation fix rather than
> trust it, and walked each family: the Getting Started CTAs raise the
> right window and "Open office →" correctly *minimises* every window to
> reveal the floor (openOrRaise treats `visual` as the wallpaper, not a
> window). The `m` and `1-8` shortcuts open windows now — they were
> silently dead in desktop mode too.
>
> Then the command palette's "Switch view: Vault" set `activeView` to
> `vault` and opened nothing. The 13 `action:` entries I had swept in
> `app.jsx` are the **onboarding tour**; the palette's 47 commands live in
> `app/commands.jsx` and were never touched — all eight Navigation
> entries still called the raw setter. The palette is the app's fastest
> path to anywhere, and its entire Navigation section was inert in the
> default mode.
>
> The prop is now named `navigate` rather than `setActiveView`, and takes
> `navTo`. The rename is the point: the old name invited exactly this bug
> in the next component that accepts it, because passing a raw state
> setter *looks* correct right up until desktop mode makes it a no-op.
>
> Two measurement traps worth recording, both of which nearly produced a
> false bug report:
> - Dispatching a synthetic `keydown` on `document` makes `e.target` a
>   non-Element, so the handler's `e.target.matches(…)` guard throws and
>   every shortcut looks broken. Dispatch on `document.body`.
> - A window-state snapshot that records only `w.view` cannot see a
>   minimise. "Open office" looked like a no-op until the snapshot
>   included `minimized`.

> ✅ **Finished the navigation sweep, then opened the Vault (2026-08-06).**
> Completing the audit found one last raw-setter navigation prop —
> `WorkspaceView`'s `onSwitchView`, feeding a "TALK ›" button. Routed
> through `navTo` for consistency, but **honestly: that button is
> mobile-only** (its block sits behind `mobileStep`, which stays `null`
> forever on desktop), and on mobile `navTo` already reduces to
> `setActiveView`. So this is hardening against the next person moving
> that block, not a live bug fixed. `Rail` and `MobileTabBar` were checked
> and are already correct — the Rail prefers its desktop-aware `onLaunch`.
> The codebase now has exactly one navigation verb.
>
> Then opened the **Vault** for the first time this session. Its graph
> analysis panel described the office's five main topics as:
>
> > `boss, You → Aiko, You → Aiko` · `You → Sora, You → Sora, You → Sora`
> > · `You → Kenji (2), You → Kenji (3), You → Kenji (2)`
>
> Distinct *nodes* can share a display *title* — many messages all render
> as "You → Sora" — and the label sliced `topNodes` to three **before**
> resolving titles, so collisions burned the slots. One topic, repeated,
> dressed up as three exemplars: the same shape as the attention counter
> that reported one problem twenty-one times.
>
> `topNodes` carries five candidates, so dedupe on the resolved title
> across all of them and take the first three that genuinely differ. A
> cluster with real variety now shows it; one that really is all about a
> single thing says so once. Verified live — labels became `boss, You →
> Sora` and `You → Kenji (2), You → Kenji (3), a5`, the Kenji cluster
> surfacing a real third member the old slice was spending on a duplicate.

> ✅ **The Vault said 38 notes; there were none (2026-08-06).** Opened the
> Vault's note list and it was empty — correctly, the vault directory holds
> zero files. The graph panel beside it read **"Notes: 38"**.
>
> Queried `/vault/graph` directly rather than guess: 38 nodes, every one
> `source: hq-state` — **19 message-threads, 12 agents, 5 decisions, 2
> tasks, 0 notes**. The endpoint returns the whole business (that is the
> feature: one map of everything the office knows), and the panel was
> labelling all of it with the name of the one kind that wasn't there.
> Same for each cluster row: "6 notes", "5 notes".
>
> Not jargon — a **wrong count of a real business asset**, which is worse.
> A boss reading that panel would believe they had 38 filed notes.
>
> The links map now reads **"On the map: 38"** with the true mix spelled
> out underneath — `19 conversations · 12 coworkers · 5 decisions · 2
> tasks` — built from the node types the component already had. A kind
> with none present simply isn't listed, so an empty vault never claims
> notes it doesn't have. Cluster rows say "items", true whatever they
> hold. Concept mode keeps "concepts" and its "over N notes" line: there
> the nodes really are concepts drawn from real note bodies.

> ✅ **"Folded into every prompt" had a ceiling (2026-08-06).** Opened the
> Memory Shelf, added a real entry, and traced the claim rather than
> trusting it: `HQ._memory` → `memorySummary()` → pushed into **both** the
> CEO system prompt and the per-agent prompt. The promise is real, and the
> wiring is sound — good.
>
> But `memorySummary` slices to the newest 24, and the header said
> "folded into every prompt" with no qualification. True at 5 entries;
> false at 30, silently, with the boss believing every note they had ever
> saved was still steering the team. Long-term memory is the one feature
> whose whole value is "the team remembers it forever" — an invisible
> ceiling is the worst place to keep one.
>
> The cap is now `HQ.MEMORY_PROMPT_CAP`, read by the copy, so the two
> cannot drift: under it the line is unchanged, over it it reads
> **"30 saved · the newest 24 go into every prompt"**. Verified at 30, at
> 1 and at 0. Fixed a plural bug found while checking — the header said
> "1 entries".
>
> Method note: memory is `useFileStored`, so seeding `localStorage` to
> test proves nothing — hydration from `memory/context.json` overwrites it
> on load. Seed the server file. (This is the storage layer working
> correctly, not a bug: the server is the source of truth.)

> ✅ **Audited the office banner's three claims (2026-08-06).** The strip
> under 🏢 AGENT OFFICE is on screen the entire time a boss is on the
> floor, which makes it the app's most-repeated sentence — so each clause
> was checked against what the control actually does, rather than read.
>
> - *"drop task cards on desks to delegate"* — **true**, driven end to end
>   earlier this session.
> - *"click guest chair for 1:1"* — **true**. The chair opens Focus Mode,
>   which streams only `ceoStream`, and the room is titled `1:1 WITH
>   CAFRESOHQ · quiet room · no distractions`. Confirmed live.
> - *"meeting door opens standup"* — **false**. The door calls
>   `onOpenMeeting`, which seats the team in the **Meeting Room**
>   (verified live earlier: `MEETING ROOM · 3 IN THE ROOM · CAFRESOHQ
>   MODERATING`). The stand-up is a different modal, reached from 🌅
>   STAND-UP or `u`.
>
> Fixed the copy, not the door: a door marked MEETING that opens a meeting
> room is the right mapping — the sentence was simply describing a
> different feature. It now reads *"meeting door seats the team"*.
>
> Worth stating as a rule, since three separate finds this session were
> the same shape (`Notes: 38` on an empty vault, "folded into every
> prompt" above its cap, and this): **any sentence that asserts what a
> control does, or what a number counts, is a claim — and claims decay.**
> The ones on always-visible chrome decay loudest.

> ✅ **Applied the claims rule as a sweep (2026-08-06).** Took the rule
> named above — *a sentence asserting what a control does is a claim* —
> and swept the `className="tag"` header copy, driving each control rather
> than reading it. Most held. One did not, and it was the Tasks header:
>
> > *"click → CHAT to fan out, 📋 ROOM to open a meeting"*
>
> Measured live. **→ CHAT drafts.** It prefills the composer with the task
> and sends nothing — the last chat message was still the CEO's welcome
> afterwards — and adds at most the assignee's `@mention`. In the run
> tested there wasn't even one, because that task's assignee had been let
> go. A fan-out happens only if the boss types more `@names` themselves.
> **📋 ROOM also drafts**: it opens the pre-filled NEW MEETING ROOM form
> and creates nothing (meeting count unchanged).
>
> Both behaviours are *right* — the handlers say so explicitly, and
> letting the boss review before work leaves the building is the correct
> design. Only the copy was wrong, promising two done deals. Now: *"click
> → CHAT to draft it in chat, 📋 ROOM to set up a meeting"*.
>
> The toast had the same fault and mattered more: `Sent "…" to chat`. A
> boss who reads "sent" can close the tab believing the work is away when
> it is sitting unsent in a composer. It now reads **`Drafted "…" in chat
> — press Enter to send`**, which also names the one thing still left to
> do. Verified live: header and toast both correct.

> ✅ **The Terminal blamed the wrong thing (2026-08-06).** Continued the
> claims sweep into `hint` copy — most of it is Settings-area and exempt,
> and two claims worth checking held up (*"A new desk will be assigned on
> spawn"* is true: the floor maps **all** senior agents and only fills the
> remainder with vacancies, so desks keep appearing past the 5 visible
> slots; the front-desk "found on this machine" lines matched the real
> detections).
>
> Then opened the Terminal, where failure is guaranteed in a container-less
> environment, to see whether it fails honestly. It printed:
>
> > `[connection error — is serve.py running?]`
>
> An internal filename on a user surface (§6) — and pointing at the one
> thing that **cannot** be the cause. This page is served *by* `serve.py`;
> if it weren't running there would be no window to read the message in.
> The boss is sent to check the single component they can prove is fine,
> while the thing that actually failed — the terminal's own socket — goes
> unnamed.
>
> Now: **`[couldn't reach the terminal service — retrying]`**. Names what
> failed, in office words, and states what happens next — the `onclose`
> handler was already retrying, so the boss never had anything to do.
> Swept the rest: every other `serve.py` mention is a code comment, none
> reach a user surface.

> ✅ **Assigning made the floor lie (2026-08-06).** Swept the toasts next —
> they fire at the moment of action, so a wrong one is read exactly when
> it matters. `Assigned "…" to X` looked innocent until the handler was
> read: assignment deliberately does **not** dispatch (the comment says
> so — starting work is a separate, explicit act), yet it wrote the task
> title into `agent.task`.
>
> `agent.task` is the **desk bubble**. Measured live: after assigning from
> the Tasks board, `status` stayed `idle` and the floor showed
> `🛡 CLAUDE · CODING AGENT / workflow step one — outline` — a coworker
> standing still, captioned with a job nobody had started.
>
> That is the exact invariant the coffee fix established earlier in this
> same document: **`task` is what they're working on, and an idle
> coworker's bubble must not claim a job that doesn't exist.** The rule
> was written down and the assign path still broke it — which is the
> argument for driving each surface rather than trusting that a stated
> rule is an enforced one.
>
> The assign path no longer touches `task` (the owner is already shown on
> the card's assignee chip, which is where it belongs), and the toast now
> names the step still outstanding: *"Assigned … to Claude — drop it on
> their desk to start"*.
>
> Verified both paths stay distinguishable: assigning leaves `idle` /
> "standing by"; dropping on a desk via the office inbox still goes
> `busy` / `thinking` with the title in the bubble — there, correctly,
> because a run really is in flight.

> ✅ **A coworker who SUCCEEDS never sat back down (2026-08-06).** Followed
> the assign-path fix by auditing every write to `agent.task`, then to
> `agent.status`. Two more violations of the same invariant, both on paths
> a failure-only test run can't reach:
>
> - **Missions.** A completed iteration leaves `active · on mission`, which
>   is honest while the mission runs. None of the four stop paths — budget
>   spent, auto-paused on repeated errors, self-declared complete, agent
>   removed — cleared it, so the mission ended and the coworker kept
>   standing there captioned "on mission". `standDown()` now runs on all
>   four. **STOP ALL** couldn't rescue them either: it filtered on
>   `status === 'busy'`, and missions produce `'active'` — the one button
>   whose whole job is "make it all stop" was blind to the state missions
>   create. It now covers both.
>
> - **Every successful run.** `status: 'active' · mood: 'done' · task:
>   'reporting back'` is set at three sites so §4's done-stretch can play
>   — and nothing ever took them out of it. `active` reads as *working*
>   everywhere on the floor: the sprite turns its back, the desk and
>   rooftop lights stay on, and the header counts it. So **`N WORKING`
>   was a high-water mark of completed tasks, not a count of live work.**
>   Measured: one finished chat run, nothing streaming, header still
>   reading `1 WORKING`. `settleAfterRun()` keeps the beat for 4s (the
>   order of the existing 2.5s error freeze and 1.6s prop return), then
>   hands the desk back — guarded so a re-dispatch inside the window is
>   left alone.
>
> The lesson is the sharper half of this: **every failure path already
> reset correctly.** A whole session of testing against a brain-less
> environment exercised nothing but failures, and this was invisible the
> entire time. Testing only the sad path hides every bug that lives on the
> happy one.

> ✅ **Verified the settle on a real success — for free (2026-08-06).** The
> previous entry's fix was reasoned, not watched, because the only agent
> with a working brain here runs on the boss's own paid subscription. The
> front desk had already detected a **local Ollama** ("already running on
> this machine — cheap and tireless"), which costs nothing but the
> machine's own electricity. Hired it and drove the success path properly.
>
> Sampled once a second across a real round trip:
>
> | t | status | bubble | header |
> |---|---|---|---|
> | 1s | `busy` | "Reply with exactly: OK" | **1 WORKING** |
> | 15s | `active` | "reporting back" | **1 WORKING** |
> | 19s | `idle` | "standing by" | **0 WORKING** |
>
> `tasksDone: 1`, 2 332 tokens — a genuine completion. The done-beat holds
> for its 4s and the desk is handed back. Before the fix that header stayed
> at 1 WORKING permanently. **First successful round trip verified end to
> end in this whole effort** — everything before it exercised failures.
>
> It also caught one more §6 leak immediately: the model's FIRST call
> cold-loaded past its budget and produced `backend did not start
> responding within 20s`. That matched no `SNAG_CAUSES` pattern, so it fell
> through to the raw first line and put **"backend"** — a banned word —
> straight into the floor bubble. Cold local models are a first-run
> normality, not an exotic edge, so it gets its own sentence: *"that brain
> didn't answer in time — it may still be warming up, so try again in a
> moment"* — and trying again did work. Pinned by a test using the exact
> string the live run produced.

> ✅ **Protocol markers were reaching the boss (2026-08-06).** With a free
> local brain the full success path finally ran end to end: task → `doing`
> → `done`, XP recorded, settle confirmed again on the task path. It also
> exposed a class of leak that **only** appears when runs succeed — small
> models emit bare protocol markers far more readily than large ones, so a
> session of failure-only testing never saw any of it.
>
> The task's stored `result` — the deliverable the boss opens — was
> literally `[ACK: in_progress: gathering context…]`. Three faults behind
> it:
>
> - the **task-dispatch path stripped nothing at all** (`extractAcks`
>   appeared exactly once in `app.jsx`, in the chat path);
> - the **chat path** stripped, then fell back with `cleaned || m.text`,
>   restoring the raw bracket precisely when the whole reply was one
>   marker — the case stripping exists for. The task-marker strip a few
>   lines below had the identical `stripped || m.text` shape;
> - the **third dispatch path** (delegation) also stripped nothing.
>
> One `visibleReply()` now serves all three, so they cannot drift. A bare
> ACK renders its own note (real information the agent wrote) instead of a
> bracket or an empty bubble.
>
> Two edges the tests found rather than the eye:
> - `stripAcks` matches any lowercase state while `extractAcks` allows only
>   four, so a typo'd `[ACK: banana: …]` was **deleted without being
>   understood** — the agent's whole reply vanished. Now only a *recognised*
>   marker is trusted; unrecognised text stays text. Silent deletion is
>   worse than an odd string.
> - Every strip here is conditional on a well-formed match. A live model
>   opened `[DM_TO: Claude]` and never closed it, so nothing matched and
>   the opener went out as prose. `stripOrphanTags` scrubs a known tag
>   **only when it stands alone on its line** — an agent writing *about*
>   `[DM_TO: name]` mid-sentence keeps it. Scaffolding goes, content stays.

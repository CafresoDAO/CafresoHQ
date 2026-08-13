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

  > **Re-driven 2026-08-12 on a single free brain, three attempts, zero
  > delegations.** Seeded two coworkers on the ONLY model this machine has —
  > `ollama:llama3.1:latest` for both asker AND answerer — and asked "@Llama
  > ask Nova to name one colour of a ripe banana, then tell me their answer"
  > three separate ways: verbatim, simplified, and finally spelling out the
  > tool by name ("using your DM_TO tool, do not answer it yourself"). All
  > three came back as `activity.json` "finished ✓" with no DM ever sent —
  > confirmed at the state-file level, not just the UI: `messages.json`
  > holds no team-room entry from any of the three runs. Attempt one trailed
  > off mid-plan after "Here's my status update:"; attempts two and three
  > echoed the question straight back to the boss. Spelling out the marker
  > name by hand did not help, which reads as this 8B model's tool-following
  > ceiling rather than an ambiguous prompt.
  >
  > Not a clean re-test of the "3/3 clean" claim above, and said plainly: that
  > run paired **gemma-4-e4b asking** with **llama-3.1-8b answering** — two
  > different brains, on LM Studio. Today's asker and answerer were the SAME
  > model, because this machine has exactly one local brain available. If the
  > asking side is what benefits most from a stronger model, this is not a
  > regression of that fix — it is a smaller model failing at a step the
  > earlier test never asked it to do alone.
  >
  > What this does NOT establish: a regression, since the fix's own PROMPT
  > TEXT — "the boss-direct framing licensed [DM_TO] only for work 'outside
  > your skillset' … with the license written in" — could not be located
  > anywhere in `hq-runtime.jsx` by any of `skillset`, `outside your`, or
  > `delegate` (`git log --all -S` on the phrase also found nothing). Either
  > the fix lived somewhere this search missed, or it was prompt wording used
  > live in that session and never landed in a file. Worth someone with more
  > context confirming which, since a fix that only ever existed in a chat
  > transcript is not a fix the next session can rely on.
  >
  > MECHANIC-is-sound stands on the evidence above it — dispatch, room
  > routing and the direction labels were all proven live. What is unverified
  > TODAY, on THIS machine's only free brain, is getting a small model to
  > choose delegation at all. Flagged rather than patched: a prompt change
  > aimed at an 8B model's tool-calling ceiling needs testing against that
  > same ceiling to know if it worked, and guessing at wording under a time
  > budget is how the original claim came to be unverifiable.
  >
  > **The "could not be located" half is resolved — 2026-08-12, later the
  > same day.** The phrase-level search above only covered `hq-runtime.jsx`,
  > and the fix does not live there — it lives in `app.jsx`'s
  > `dispatchToAgent` (~line 1822), the SHARED prompt-builder every dispatch
  > path calls (ten call sites: DM chains, task-board triggers, mission and
  > workflow dispatch, the boss's own chat send). The exact clause is
  > present verbatim: *"or [DM_TO: <coworker>] if it's outside your
  > skillset. And when the boss NAMES a coworker — 'ask Nano …' — that IS a
  > [DM_TO: Nano], even if you know the answer yourself: the boss chose who
  > answers, and only a [DM_TO] actually reaches them."* It is not a chat
  > transcript that failed to land in a file, and it is not scoped to the
  > chat surface — it is real, committed, and reachable from every dispatch
  > path in the app, exactly the property the earlier note asked someone to
  > confirm.
  >
  > That leaves the ORIGINAL open half exactly where it was, now correctly
  > separated from a search-tooling gap rather than a landing gap: the
  > wording is live, is well-targeted (it names the precise failure mode —
  > a boss naming a coworker for in-skillset work), and an 8B model asking
  > AND answering with itself still produced 0/3 real delegations against
  > it. This is a capability ceiling, not a missing fix — recorded in Known
  > open below rather than re-attempted as a prompt tweak with no stronger
  > local model on this machine to verify a tweak against.
| the calendar runs on the boss's clock, 2026-08-07 | "YOUR BUSINESS BY DAY · TASKS WHEN RAISED · MISSIONS WHEN THEY WRAP" — and the first half is exact: a task listed at 8:42 AM has `createdAt` = 08:42 local, where UTC would have read 12:42 PM, the same off-by-a-timezone that once dated a delivery tomorrow. Day grouping is local too, and the "Today 4" header matches its four rows. ~~The missions half is unverified — no mission has run in this office~~ **→ driven 2026-08-12, and it failed** (see below) |
| **the missions half, driven at last — 2026-08-12** | the bullet above sat unverified for five days because verifying it meant running a mission; when one finally ran, the promise did not hold. The filter was `status !== 'running' → skip`, so the view showed the one thing that had NOT happened (a projected wrap) and dropped the thing that had. A run that finished left **no trace on the day it finished**, in the view whose title is "your business by day". Underneath was a data gap: **no terminal transition recorded a time** — eight of them across two files, and the eighth (`onStopAll`) was found only by driving, after I had enumerated six by reading and been sure. Driven on a throwaway office with a real 15-minute mission on Llama: running row filed at **2:32 PM "wraps up" · RUNNING** (the projected wrap, correct as a forecast) → reload → **2:18 PM "stopped" · STOPPED**, where 2:18 is `lastIterationAt`, not the 2:20 reload and not the 2:32 forecast. Before the fix that reload made the row vanish outright. Two more things surfaced on the way: `.cal-mission`'s left border explicitly means "this points FORWARD" and had no exception for a finished run, and `.status-pill` is scoped to `.agent-card`, so the calendar's RUNNING tag had been rendering as **bare unstyled text** the whole time — which matters now that the pill is what separates a forecast from an outcome, and a failed outcome from a good one. `scripts/test_calendar_missions.py` |
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
| the SEARCH tool cannot leak a raw key error, by construction — audited 2026-08-12 | prompted by noticing "Search network is unavailable" on this real office (accurate — no `BRAVE_API_KEY` set here, confirmed via `curl /brave/search`) and chasing whether an *offered-but-unconfigured* tool could still leak `braveSearch`'s raw `throw new Error('No Brave key…')` to a boss. It cannot: `TOOL_REGISTRY.search.requires()` gates the SAME `enabledTools` array both places that matter — `toolsForAgent` (what gets documented in the system prompt) and `detectToolCall`'s `detectable` list (what gets dispatched). No key → the tool is absent from both, so `[SEARCH: …]` in a reply simply doesn't match anything and `.run()` is never called. One list, not two that could quietly diverge — the exact principle this file's own DM_TO-recovery comment names as "the actual bug" the third time it showed up. Recorded as a clean negative so this suspicion isn't re-chased later |

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

### Workflows — driven end to end for the first time, 2026-08-12

Never appeared in this ledger before today; only ever listed in a topbar
menu. Read the mechanism first (chain fields — `chainTo`/`dependsOn`/
`autoDispatch` — are genuinely consumed on task completion, not just
written and forgotten; `triggerChainStep`'s own comment records a prior
fix for exactly that "computed-and-discarded" shape), then drove a real
two-step chain: create → step 1 dispatches → step 1 completes and files →
the `workflow-step` approval fires → APPROVE → step 2 dispatches with
step 1's result folded into its brief → step 2 completes and files. Every
stage worked. Step 2's own delivered text proved the hand-off was real,
not cosmetic — it said outright *"I do see that 'banana' was a result
from a previous task."*

Two defects fell out of actually finishing the run rather than stopping
once the happy path looked plausible:

**Minor, fixed same session.** The `workflow-step` approval omitted `by:
agent.name` — every sibling approval kind sets it, this one didn't — so
the tray rendered `by  · workflow-step` with the requester's name
silently blank. One line. Re-verified live: `by Llama · workflow-step`.

**Major, flagged rather than rushed.** Step 2's own FILED DELIVERABLE
opened with a raw, unstripped `[MEMORY_READ: decisions/banana.md]`
directly in the boss's permanent record — worse than a chat-bubble leak,
since a chat bubble scrolls away and a filed note doesn't. Root-caused,
not guessed at: `visibleReply`'s `ORPHAN_TAG_RE` pass is deliberately
"whole line, consume to end of line" (correct and load-bearing — it's
what strips a chatty model's echoed tool-doc-string off the same line,
per the BROWSER_FETCH case documented just above it in `hq-runtime.jsx`).
But when the text AFTER the marker is the model's own genuine,
newline-less continuation — not an echoed doc string — the whole-line
strip empties the result to `''`, which is *falsy*, so `visibleReply`'s
own safety fallback ("nothing survived the strip → show the raw text
rather than silently drop it") fires and reintroduces the very marker
the strip had correctly identified as scaffolding.

Reproduced with a minimal node harness built from the real, unmodified
source (not a re-implementation): the exact captured string, run through
the real `visibleReply`, returns the raw marker+prose unchanged; the
identical string with one `\n` inserted between the marker and the
prose returns clean stripped prose. One character is the entire
difference between correct and broken.

Confirmed this is a genuine gap, not an accepted tradeoff:
`scripts/test_reply_hygiene.py` already covers the MIRROR case — a
marker mid-sentence with prose *before* it (`"I will use [MEMORY_READ:
decisions/x.md] to check."`, correctly left untouched) — but has no
case for genuine prose immediately *after* a line-opening marker with
no separating newline.

The codebase already solved this exact class of problem once, for a
different marker family: `stripBlocks`'s `lone` regex (the 17
block-form markers — VAULT_NEW, MEMORY_WRITE, etc.) uses a lookahead,
`(?=\n|$)`, instead of consuming to end-of-line — stripping only the
tag and leaving genuine trailing prose alone. `ORPHAN_TAG_RE` covers a
different, larger set (the single-shot, non-block tools: SEARCH,
MEMORY_READ, VAULT_READ, FILE_READ, DIR_LIST, BASH, BROWSER_FETCH,
BROWSER_SCREENSHOT, VAULT_SEARCH, MEMORY_LIST, plus the four
request-class names it shares with `stripBlocks`) and was never given
the analogous fix — because for THAT set, the whole-line consumption is
sometimes intentional (the echoed-doc-string case), so a blind
lookahead swap would regress a different, already-hardened behavior.

Not fixed here. `visibleReply` is one of the most heavily-patched,
many-tradeoff functions in this codebase — this entry alone documents
five separate hard-won edge cases it already balances — and a same-tick
patch risks trading a rare, subtle leak for a regression of one of
those, with no more evidence than "seemed right." Flagged as a task
with the exact reproduction, the precedent fix pattern, and the
constraint that `scripts/test_reply_hygiene.py` must stay green
including its doc-echo and mid-sentence cases.

### `visibleReply`'s deferred leak — fixed, 2026-08-13

Picked the flagged task back up rather than re-deriving it: `cleaned`
goes empty, and empty is falsy, whenever `ORPHAN_TAG_RE` consumes a
line-opening marker AND whatever genuine prose happens to follow it on
the same line with no separating newline — because the regex has always
consumed "rest of line," full stop, with no way to tell a doc-string
echo apart from the coworker's own words.

The distinguishing signal was hiding in plain sight: every single `doc:`
string across all ~30 `TOOL_REGISTRY` entries uses the exact same
separator, with no exception — `] — <description>` (closing bracket,
space, em dash, space). That convention exists purely for the system
prompt; nothing enforces coworkers echo it verbatim. But it means text
starting with an em dash immediately after the bracket is, in every
observed and constructed case, the registry's own doc string coming
back — never a coworker's independent sentence, since nobody naturally
opens a reply with "— fetch a URL and return its readable text
content."

Verified the direction of the fix BEFORE touching real source: pulled
`ORPHAN_TAG_RE` into a throwaway node script alongside both the old
regex and a candidate replacement, ran both against the doc-echo case,
the genuine-continuation case (with and without a space after the
bracket), and every existing pinned shape (bare marker, marker+newline,
closing tag) — confirmed the new regex changes exactly one of those and
leaves the rest byte-identical, before editing `hq-runtime.jsx` at all.

The actual change: `ORPHAN_TAG_RE`'s `[^\n]*$` (unconditional
rest-of-line) becomes `[ \t]*(?:—[^\n]*)?` (optional, only consuming
past the bracket if an em dash immediately follows). One regex, same
call sites, same function signature — `stripOrphanTags`/`visibleReply`
needed no changes at all.

`scripts/test_reply_hygiene.py`'s full existing suite (120+ checks)
passed unchanged — the constraint the earlier entry set. Added two new
pinned cases: `orphanGenuine` (the workflow bug's exact shape — marker
then prose, no newline — now keeps the prose) and `orphanEcho` (the
BROWSER_FETCH doc-echo from the comment above `ORPHAN_TAG_RE`, embedded
in real surrounding content so it exercises the whole-line strip rather
than the unrelated "nothing survived" fallback a bare marker+echo alone
would hit). Fire-tested in both directions: reverting to the old
always-whole-line regex fails `orphanGenuine` for exactly the expected
reason; an over-reach "fix" that never consumes the echo tail at all
fails `orphanEcho` for exactly the expected reason. Rebuilt the bundle
and smoke-tested a fresh throwaway office — loads clean, no console
errors.

### The coach mark clipped the checklist's corner on every common laptop width — 2026-08-13

A previously-flagged, not-yet-verified claim: "coach mark clips checklist
corner on desktop." The code's own comment insisted otherwise — "on
desktop both show as before, where they don't touch" — written when the
mobile version of this exact collision (task/comment for the phone-width
fix) was patched. Measured the desktop claim directly rather than trusting
it.

The checklist (`.gs-coach`) is left-anchored near the rail at a fixed
274px width (246px left offset ≥1100px, 214px ≤1100px, 70px rail-
collapsed). The coach-mark pill was always `left: 50%,
transform: translateX(-50%)` — centered on the FULL viewport, with no
awareness of the checklist's position at all. Measured live via
`getBoundingClientRect` in a throwaway office with one agent hired (the
condition that renders the 'chat' coach mark):

| viewport | checklist right edge | pill left edge | result |
|---|---|---|---|
| 1100px | 488 | 315 | **overlap ~173px** |
| 1366px | 520 | 448 | **overlap ~72px** |
| 1600px | 520 | 565 | clear ~45px |

1366×768 is one of the single most common screen resolutions there is —
this wasn't an edge case, it was the common case. The overlap only fully
clears above roughly 1510px, which the original comment's "on desktop"
silently meant "on WIDE desktop."

The mobile fix already had the right instinct, just scoped too narrowly:
its own reasoning — "no room for two onboarding nags... the expanded
checklist already lists this exact step with this exact CTA" — was never
actually mobile-specific, it was gated behind an `isNarrowViewport &&`
qualifier for no reason the reasoning itself required. Dropped that
qualifier: the coach mark now renders only once the checklist is
collapsed or dismissed, at every viewport width, instead of trying to
out-position a card whose width and offset already vary by breakpoint.

Verified both directions live at 1366px: with the checklist expanded, the
pill is absent from the DOM entirely (`querySelector('.coach-mark')` →
null); collapsing the checklist (clicking its own "–" button) brings the
pill back with a clean ~46px gap to the collapsed mini-pill's right edge,
matching the desktop-collapsed case that was already correct and
untouched by this fix.

Pinned by `scripts/test_coach_mark_desktop_overlap.py` (structural —
confirms the render condition no longer references `isNarrowViewport` and
still gates on both `gsDismissed`/`gsCollapsed`), fire-tested by
reverting to the old `isNarrowViewport`-gated condition — failed for
exactly the expected reason.

### Trading Floor theme's ticker separator failed WCAG AA contrast — 2026-08-13

Another previously-flagged, not-yet-verified claim: "Trading Floor theme
ticker separator contrast." The base `.ticker-track .line .sep` rule
already carries an extensive comment documenting a real accessibility fix
— measured at 3.38:1 against the ticker's dark background, raised to
5.48:1 — but the `theme-wallstreet` override of that same selector
(`#00e0a0` at 37.6% alpha) was never put through the same analysis.

Computed with the actual WCAG relative-luminance formula (not eyeballed —
built a small node script, cross-checked it against the base rule's own
cited 5.48:1 to confirm the math before trusting it on the new case):
`#00e0a060` against this theme's `--office-ticker-bg` (`#0a0a1a`) measures
**2.42:1** — below WCAG AA's 4.5:1 floor, and worse than the failure the
base rule was already fixed for.

Fix: same hue, alpha raised from `0x60` (37.6%) to `0xac` (67.5%) —
`#00e0a0ac` — landing at 5.51:1, matching the base rule's own established
5.48:1 target rather than picking a new number by eye. Full-opacity
`#00e0a0` alone would hit 11.36:1, comfortably AA, but would make the
separator brighter than the surrounding content, defeating the point of a
separator (the base rule's own comment: "still reads as a separator
instead of competing with the news").

Verified live: switched to the Trading Floor theme in a throwaway office,
read the separator's actual computed style — `rgba(0, 224, 160, 0.675)`
(0xac/255) against a measured `rgb(10, 10, 26)` ticker background,
matching the calculation exactly — and confirmed visually the ticker
still reads cleanly (`SPX 7,700 ▲0.45 · GOLD 4,644 ▼0.32 ·`).

Pinned originally by `scripts/test_ticker_wallstreet_contrast.py` — see
the follow-up entry immediately below, which superseded this test with a
broader one after the same tick's own full audit turned up two more real
failures in the same selector family.

### The wallstreet fix above was one of three — full theme x day/night audit — 2026-08-13

Fixing the wallstreet ticker separator in isolation left the job half
done. Rather than stop at "the flagged theme is fixed," audited the
whole matrix live: 7 themes (default, sepia, solarized, dracula,
highcontrast, coffeeshop, wallstreet) x 2 modes (day, night) = 14 real
combinations, measured with `getComputedStyle` on temporary DOM nodes in
a throwaway office (real cascade resolution — CSS custom-property
inheritance turned out to have a surprise in it that hand-reading the
source got wrong the first pass, see below). **Two more genuine
failures, plus a specificity bug explaining a third:**

- **`theme-coffeeshop`, day mode: 4.09:1.** Same shape as wallstreet —
  its own `--office-ticker-bg` (`#3e2c1e`) never got the base `.sep`
  color (`#9a8d7c`) re-checked against it.
- **Every theme, night mode: 3.77:1 — including, unexpectedly, the
  wallstreet fix just shipped (4.01:1, still failing).** Root cause:
  `body.night .ticker { background: #3a3050; color: #f3e8ff; }`
  hardcodes the ticker's background app-wide whenever night mode is on,
  at higher specificity (1 type + 2 classes) than the base `.ticker {
  background: var(--office-ticker-bg) }` rule (1 class) — so it wins
  regardless of which theme's own `--office-ticker-bg` variable is set.
  Confirmed live: `coffeeshop.night`'s `#150e0a` and `wallstreet.night`'s
  `#060610` — both real declared values — **never actually render**;
  every theme's ticker in night mode uses this same `#3a3050`. This
  pattern (identical `#3a3050`/`#f3e8ff` pair) matches ~15 OTHER
  components in the same `body.night` block (`.gs-card`, `.memrow`,
  `.task-card`, `.chip`, `.toast`, …), so read as deliberate — night
  mode is one uniform palette across themes by design — and fixed at the
  surface that's actually wrong (nobody had re-checked `.sep` against
  it) rather than un-hardcoding 15 rules on a guess about intent. The
  per-theme night-mode `--office-ticker-bg` variables (coffeeshop,
  wallstreet) are consequently confirmed dead code — flagged, not
  removed, since deleting CSS that visibly does nothing is a separate,
  lower-urgency cleanup from fixing what's actually broken.

Three additive fixes, each tuned to land at ~5.4:1 — matching the
original fix's own 5.48:1 precedent rather than a fresh number each
time — verified live after each:
- `body.theme-coffeeshop .ticker-track .line .sep` (new, day only —
  `#b5a390`, 5.43:1)
- `body.night .ticker-track .line .sep` (new, generic — covers
  default/sepia/solarized/dracula/highcontrast/coffeeshop.night at once
  since they all share the same real night background — `#b8ab99`,
  5.43:1)
- `body.theme-wallstreet.night .ticker-track .line .sep` (new, combined
  selector so it outranks both the generic night rule and the day-mode
  wallstreet rule — keeps Trading Floor's own green in night mode
  instead of falling back to a neutral tone — `#00e0a0d6`, 5.42:1)

All 14 combinations re-measured after the fix: 5.42–5.52:1, uniformly.

Pinned by `scripts/test_ticker_sep_contrast.py` (replaces the narrower
`test_ticker_wallstreet_contrast.py` from earlier in this same tick) —
resolves all four real backgrounds and five real winning `.sep` rules
from source (HSL conversion for the default theme's token, direct hex
for the rest) rather than hardcoding a duplicate snapshot, so it tracks
the actual cascade. Fire-tested all three new rules separately (each
reverted to its pre-fix color) — each failed with the exact ratio
measured live (4.09, 3.77, 4.00), not just "does not pass."

### One more from the same audit: the market-quote red — 2026-08-13

Finishing the `.sep` audit rather than stopping at "found three, fixed
three": checked the OTHER colors in the same selector family —
`.mkt-up`/`.mkt-down` (Trading Floor's Coinbase-fed market quotes) and
`.kw` (keyword highlight). `.mkt-up` and `.kw` both clear night mode's
real `#3a3050` background comfortably (9.11:1, 8.71:1). `.mkt-down`
does not: same red (`#ff4d4d`), same background the `.sep` fix above
already had to re-target — measures **3.74:1**.
Fixed the same way, additively: `body.theme-wallstreet.night
.ticker-track .line .mkt-down` at `#ff8a8a`, landing at 5.39:1.
Verified live (`getComputedStyle` on a real `.mkt-down` node in a
throwaway office, wallstreet + night): fg `rgb(255,138,138)` vs bg
`rgb(58,48,80)`, 5.39:1, matching the calculation exactly.
Pinned by extending `scripts/test_ticker_sep_contrast.py`, fire-tested
by reverting the night override back to the day-mode red — failed with
the exact 3.74:1 measured live.

Also checked the BASE (non-wallstreet) `.mkt-up`/`.mkt-down` — `var(--ok,
#1f8a4c)` / `var(--danger, #c0392b)`, two CSS variables that turn out to
be undefined everywhere in this codebase, so always the fallback color.
Every real ticker background fails against them (2.25–4.06:1). **Not
fixed**: `marketTicker` is `true` only for the wallstreet vocab entry
(`ui/primitives.jsx:16`) — no other theme ever renders a `.mkt-up`/
`.mkt-down` span, so this is confirmed-dead CSS, not a live gap, same
class of finding as the `--office-ticker-bg` night-mode variables the
first ticker entry already flagged as unreachable.

### Night mode couldn't stick in day mode past 7pm — 2026-08-13

Found reading past the theme system while it was already open for the
ticker audit: a mount-only effect auto-enables night mode based on the
wall clock — `if (h < 7 || h >= 19) setNight(true)` — with no check for
whether the boss already had an explicit preference stored. `useStored`
reads localStorage synchronously in its own initializer, so `night`
already correctly holds a stored `false` by the time this effect runs —
and then the effect stomped it anyway, unconditionally, on every single
mount. A boss who explicitly clicked "Switch to day" (or the toggle) in
the evening had that exact choice silently overwritten back to night on
their very next reload, forever, with no way to make day mode stick
after 7pm — the auto-detect meant for a first-time visitor kept firing
on every visit thereafter.

The auto-detect itself is a reasonable courtesy (a first-time visitor
loading HQ after dark shouldn't be squinting at a bright day theme by
default) — the bug was applying it on every mount instead of only the
one case `useStored`'s own initializer treats as "unset": no key in
storage at all. Fixed by adding that exact guard —
`if (localStorage.getItem(k('night')) != null) return;` — before the
clock check.
Verified precisely with a node harness replicating the exact effect
body against four scenarios (new visitor + evening → still auto-sets;
new visitor + day → no-op; returning visitor with explicit `false` +
evening → no longer overridden, the bug; returning visitor with
explicit `true` + day → no-op) — all four passed. Couldn't reproduce the
evening case in a live browser directly (the real system clock was
10:31am while investigating, and this tool has no clean way to mock
`Date` before a fresh page's own scripts run across a real navigation),
so leaned on the node harness for logic proof and used the browser only
to smoke-test the unaffected, naturally-testable case: a fresh throwaway
office loaded at the real current daytime hour stayed in day mode, no
regression.
Pinned by `scripts/test_night_mode_respects_explicit_choice.py`,
fire-tested by removing the guard — failed for exactly the expected
reason.

> ✅ **The ecosystem app switcher ("Apps ▾"), clean pass — 2026-08-13.**
> Driven for the first time this session. Worth noting how it hid from
> the usual tooling first: `document.querySelectorAll`/a full DOM
> `TreeWalker` both came back completely empty for "Apps" text, even
> though it's plainly visible in a screenshot — it lives inside
> `<cafreso-ecobar>`'s Shadow DOM (`cafreso-ecobar.jsx`, a genuinely
> shared, framework-agnostic Web Component: "canonical copy lives in the
> CafresoHQ repo; the Svelte frontend and Minegold load an identical
> copy"), invisible to a plain top-level query. Reached it with
> `document.querySelector('cafreso-ecobar').shadowRoot.querySelector(…)`
> instead. Clicked the real `.apps` button inside the shadow root: the
> menu opened correctly, positioned cleanly (not clipped or hidden behind
> anything — the exact bug class this session found repeatedly
> elsewhere), listing all four ecosystem apps (Pages, AI, HQ, Mine) with
> correct URLs, and HQ itself correctly rendered as a non-clickable `<div
> class="item active">` with a CURRENT badge rather than a self-link. No
> code changed.

> ✅ **Agent Inspect panel's job description, clean pass — 2026-08-13.**
> Driven for the first time this session: clicked a hired coworker's desk
> sprite on the office floor, opened the "PERFORMANCE REVIEW" card, edited
> the JOB DESCRIPTION textarea, blurred it, closed the panel, reopened it —
> the edit survived. Confirmed on disk too, not just in the UI: the new
> text landed in `hq-state/memory/agents.json` under the agent's
> `systemPrompt` field, exactly where the front-desk hire flow writes the
> same field. A rapid sweep through every sidebar view (Office, Tasks,
> Calendar, Memory, Vault, Team, Terminal, Projects) turned up zero
> console errors. No code changed.

> ✅ **STOP ALL vs. an in-flight task — clean pass, verified by full
> call-path reading after live automation proved impractical (2026-08-13).**
> Tried twice to catch this live: seed an agent as "busy" and reload (the
> app correctly scrubs a persisted busy status on mount — its own
> `tasksOnLoad` safety net, working as designed, not a bug), then tried
> racing a real Llama task against a STOP ALL click. Both attempts lost
> the race — a short local-model reply finishes faster than a multi-step
> browser-automation round trip can click Start → Stop All → confirm.
> Recognized this as friction in the *testing tool*, not evidence about
> the app (same lesson as this session's earlier `computer.key`
> "Return"-vs-"Enter" finding), and switched to reading the real call
> path instead of continuing to force a live race.
>
> First read of `onStopAll` (`app.jsx:920`) looked like a real bug: it
> resets agent status via `setAgents` but never calls `setTasks` — so a
> task marked `doing` when the boss hits STOP ALL looked like it would
> stay `doing` forever, the exact "office claims work is happening that
> isn't" failure the reload-scrub's own comment (`app.jsx:715`) already
> names and fixes for a *different* trigger (a killed tab). Read further
> before concluding that: `onStopAll` calls `c.abort()` on every in-flight
> `AbortController`, and the task-dispatch function's own `catch` block
> (`app.jsx:3786`) is what actually handles the rejected promise that
> abort produces — `controller.signal.aborted` is checked explicitly, and
> when true it puts the task back in `inbox` (keeping the assignee, since
> a boss-stop is not the coworker's failure — mood stays `idle` not
> `stuck`, off the XP ledger, matching §5's rule applied consistently
> elsewhere in the same handler). The reset happens; it just happens one
> function away from the button's own handler, through the abort→reject→
> catch chain rather than directly in `onStopAll`. No code changed —
> confirmed working as designed, not a gap.

### Every export tool was completely broken, and had never once been run — 2026-08-12

EXPORT_PPTX/DOCX/PDF (real .pptx/.docx/.pdf deliverables, via python-pptx /
python-docx / weasyprint-or-reportlab) had never appeared in this ledger.
They're not specialist-only — `toolsForAgent` grants all three to ANY
coworker with vault access, which is the common case, not an edge one.

Checked whether the underlying libraries are even installed on this
machine first, since that determines what's testable at all: none of the
four are (`python-pptx`, `python-docx`, `weasyprint`, `reportlab` all
`ModuleNotFoundError`). That's an environment fact, not a code defect —
`exporters.py` catches exactly this with `except ImportError: return
self._send_json(503, {'error': 'python-pptx not installed — run: pip
install python-pptx'})`, a clean, actionable, already-correct message.

**Except calling it didn't reach that message. It crashed the request
thread and returned nothing at all.** `curl -X POST .../export/pptx` came
back as `curl: (52) Empty reply from server` — not a JSON error, not any
HTTP response, silence. The server log named it exactly:
`AttributeError: 'Handler' object has no attribute '_read_json_body'`, from
inside `exporters.py`'s own `_export_pptx`, at the very first line trying
to read the request body.

Root cause, and it is not subtle once found: `serve.py` composes its
`Handler` class from free functions by explicit, individual assignment —
`_export_pptx = exporters._export_pptx`, one line per function, six lines
total for the export/generate family. `_read_json_body` is
`exporters.py`'s own shared helper (`def _read_json_body(self):`, five
`self._read_json_body()` call sites — one from each of EXPORT_PPTX,
EXPORT_DOCX, EXPORT_PDF, GENERATE_IMAGE, GENERATE_VIDEO), and it was simply
never given its own binding line. Composition-by-explicit-naming means a
helper the module calls on ITSELF needs wiring exactly as much as a route
does, and this one never got it. **All five tools were completely
non-functional, in the worst possible way — not a graceful error, a raw
crash with an empty reply — and none of them had ever been exercised
before today, which is the only reason this survived.**

One line fixes it, matching the six sibling bindings already there
verbatim in shape. Verified live at the API level (more reliable than
routing through a small local model's unreliable tool-calling, which
narrated a plan instead of emitting the marker when asked — today's
familiar pattern): before the fix, `/export/pptx` returned nothing; after,
all three formats return their correct, pre-written, ImportError-caught
JSON error. The graceful-degradation code was already right; it just
could never be reached.

Pinned by `scripts/test_exporters_wired.py`, written general rather than
narrow: it checks EVERY `self._X()` call inside `exporters.py` against
`serve.py`'s binding list, so the same class of bug — a helper added later
and called via `self.`, never wired — is caught for any future helper, not
just this one. Fire-tested by removing the fix (all five affected tools
named in the failure) and by removing a DIFFERENT, unrelated binding
(`_export_docx`'s own) to confirm the check's real scope: it catches an
unwired helper called from inside the module, not an unwired route itself
— a narrower, honestly-stated claim rather than an oversold one.

Not verified: a full successful export (a real file landing in the vault),
since no export library is actually installed on this machine. That is a
`pip install` away and orthogonal to the bug that was found and fixed.

### GENERATE_IMAGE/GENERATE_VIDEO are fully built and completely unreachable — 2026-08-12

The other two tools sharing `_read_json_body` with the exports above.
Checked whether the same fix cleared them too: it did. A throwaway office
(`CAFRESOHQ_HQ_STATE_DIR=/tmp/hq-gen`) driven with direct `curl POST` against
`/generate/image` (9 branches: all 5 providers — openai, google, fal,
a1111, comfyui — each with valid-key/missing-key/unreachable-local-server
paths) and `/generate/video` (4 branches: fal, openai, google, comfyui) —
zero crashes, zero empty replies, every branch a clean structured JSON
error. `exporters.py`'s `_generate_image`/`_generate_video` are genuinely
well-built: real API integrations for five image and four video providers,
proper `try/except` around every network call, and — unlike most of this
session's findings — an *honest* one: the `openai`/`google` video branches
don't pretend to work, they return a hardcoded `501` naming the real
reason (`"OpenAI Sora video generation not yet wired — Sora API is gated.
Try provider=fal instead"`).

That honesty is what surfaced the real finding. `claude-client.jsx`'s
`_mediaConfig()` defaults an unset provider to `'openai'` for BOTH kinds:
`(kind === 'video' ? s.videoProvider : s.imageProvider) || 'openai'`. For
images that default is fine — OpenAI images genuinely work. For video it
is the one provider guaranteed to fail; `fal` is the only one that could
actually succeed on a bare API key. So I went to see what a boss would
need to set to avoid that default — and found the setting itself does not
exist anywhere.

`toolsForAgent` gates both tools on nothing but a settings key:
`if (s && s.imageProvider) out.push(...)` / `if (s && s.videoProvider)
out.push(...)` (`hq-runtime.jsx:1538-1539`). Grepped the entire `.jsx`
codebase for `imageProvider`, `videoProvider`, `imageModel`, `videoModel`,
`a1111Url`, `comfyUrl` — **four matches total, all read-side**: the two
gate checks above, one comment, and `_mediaConfig`'s own fallback logic.
Checked every candidate write path directly rather than trusting the grep
alone: `modals/settings.jsx`'s `SETTINGS_TABS` is exactly five entries —
account, connections, roster, modules, appearance — no media tab.
`modals/providers.jsx` (808 lines) covers text-model backends only
(openrouter/gemini/groq/lmstudio/ollama) plus Claude Code, Codex, Vault,
and Brave tabs. No raw/advanced JSON settings editor exists as a fallback
path either. **`s.imageProvider` and `s.videoProvider` can never become
truthy through any control in the product.** GENERATE_IMAGE and
GENERATE_VIDEO are not buggy — they are permanently absent from
`toolsForAgent`'s output for every coworker, in every office, unconditionally.
A fully-built, fully-tested backend with no door to it.

One thing narrows the eventual fix: `getAgentKey`/`setAgentKey`
(`claude-client.jsx:1907-1932`) already store vault-encrypted keys by an
arbitrary provider-name string, not a hardcoded enum — the same mechanism
`generateImage`/`generateVideo` already call with `getAgentKey('openai')`,
`getAgentKey('fal')`, etc. So this isn't "build encrypted key storage
from scratch," it's specifically "build the missing picker/field UI and
have it call the storage that already exists." Filed as `task_gen_media_ui`
rather than fixed same-tick: a real Settings → Media section needs
provider dropdowns for image and video, model fields, key fields per
provider via the existing vault mechanism, and base-URL fields for the two
local providers (a1111/comfyui) — five to nine new fields plus the state
wiring, not a one-line change, and rushing UI surface area under a loop
tick risks exactly the kind of half-built control this file exists to
call out. The `_mediaConfig` `'openai'`-video-default bug is folded into
the same task rather than fixed in isolation, since correcting a default
for a gate that can never open is moot until the gate exists.

### The chat-thread Meeting Room, driven live — 2026-08-12

Two separate features share the name "meeting room" in this codebase and
neither had been driven this session: the office-floor door (seats
participants, sequential per-round replies, CEO synthesizes) and the
chat-thread modal reached via ROOMS ▾ (`modals/collab.jsx`'s
`MeetingRoomModal`, "everyone in the room sees this when it opens... pick
at least one — they'll all see each other's replies"). Drove the second —
last touched 2026-08-06, before every change made today.

Two Ollama coworkers, one topic ("What is one colour of a ripe banana?"),
sent `@Llama @Nova`. Both replied independently and correctly in the same
round — "One colour of a ripe banana is yellow." from each, clean, no raw
markers, no blank bubbles. Sent a second message ("Nova, do you agree with
what Llama just said?") to test whether round 2 actually carries round 1's
exchange, since the code shows each round's transcript is built ONCE before
that round's replies (a structural question worth answering by driving
rather than assuming from the shape of the loop). It does: both replies in
round 2 clearly reference round 1's answer rather than starting fresh.

**Almost mis-flagged something as a bug that turned out to be correct,
documented behavior — caught by reading the reasoning before writing up the
finding.** Nova's round-2 reply ended with a literal
`[Llama · Generalist]: One colour of a ripe banana is yellow.` — the
office's own speaker-label format (`NAME · ROLE`), presenting a quote as if
Llama had said it. First read as a fresh instance of the "office's own
voice is not the coworker's to borrow" class this file already documents
at length. It is not, on closer reading: `stripSelfLabel`'s own comment
states the design directly — *"A label naming somebody else is content — a
coworker quoting what Mika said. A label naming the SPEAKER is never
content."* And checking the transcript rather than assuming: Llama's round-1
reply genuinely was "One colour of a ripe banana is yellow." Nova's quote is
accurate. The function is correctly leaving alone exactly the case it says
it will.

`fabricatedRelay` — the detector for a coworker inventing a colleague's
words — does not apply here either, and not by oversight: it is never
called from the meeting path at all (`grep fabricatedRelay features.jsx` →
nothing), and even if it were, its regex requires an arrow (`X → Y:`), not
this dot-separated label shape, because it is built for a narrower,
different threat (a fabricated RELAY claim, gated on nothing having
actually been delivered this run).

**What's left genuinely open, stated at the right confidence.** The label
format is unchecked against truth — nothing verifies a `[Name · Role]:`
quote is accurate before it renders, the way `fabricatedRelay` verifies
its narrower case. This instance was accurate. Whether a small model could
use the same unchecked format to dress up a FABRICATED quote as a
colleague's words is a real, structurally plausible question and was NOT
observed happening — no task filed, because filing one would mean asking
someone to fix a bug that has not been shown to exist. Recorded as a
question for future driving to answer, not a finding to act on today.

### The office-floor Meeting Room's second speaker couldn't hear the first — 2026-08-12

The other meeting room — the office-floor door (`features.jsx`'s
`MeetingRoom`, seats participants, sequential per-round replies, CEO
synthesizes) — was still undriven after the chat-thread modal above got
its pass. Drove it on the same throwaway two-Ollama-coworker office.

Sent one message with both seated: *"name ONE fruit and say which of you
spoke before you (or 'no one' if you're first)."* Llama, going first,
answered correctly — fruit, "no one spoke before me." Nova, going
**second**, in the same visible round, with Llama's reply already
rendered a few pixels above hers: *"I said no one spoke before me since
I'm the first to respond."* Wrong, and not the model's fault — her prompt
genuinely contained no trace of Llama's turn.

Root cause, once looked for: `transcript` was a `const`, built once at the
top of `moderate()` from prior messages plus the boss's new line, before
the participant loop ran. Every seated coworker's prompt read "Meeting
transcript so far: `<that same frozen string>`" no matter how many
round-mates had already answered in front of them — a `for` loop that
LOOKS like turn-taking (typing indicator, one reply materializing after
another) while every participant is actually answering the same static
prompt in isolation. The CEO's closing synthesis used the identical frozen
`transcript`, so even a healthy CEO call would have summarized "the
discussion" having seen none of it — only the question that opened it.

This is the third distinct instance this file has now recorded of the
same shape of bug — a value that visually *looks* live (a running
transcript, a streaming reply, a round in progress) but is structurally
a frozen snapshot underneath. The chat-thread modal above rebuilds its
transcript fresh per round and fans out in genuine parallel within a
round — a different, correct design for a different feature. This one
is sequential BY DESIGN (turns render one at a time) and simply never
fed each turn's own output back in.

Fix: `transcript` is now `let`, appended after each participant's turn
(`\n${name}: ${cleaned}`, using the same `visibleReply`-cleaned text
already written to their bubble — not the raw buffer, so a stray marker
can't leak into what the next round-mate reads as context). The CEO's
synthesis call needed no separate change — it reads the same `transcript`
variable, so it now inherits the full round automatically. Re-ran the
identical probe after rebuilding: Nova correctly opened with *"Llama has
made a response to the initial question... Llama responded with
'Apple.'"*

Pinned by `scripts/test_meeting_room_round_transcript.py` (`let` not
`const`, an in-loop append using the cleaned text, positioned before the
loop's closing brace) — fire-tested against the reverted bug (3 failures)
and against an over-reach wrong fix that appended once after the loop
instead of once per turn inside it (still 2 failures, confirming the
test's positional check has real teeth). Refactoring the success-write
into `const cleaned = ...` broke an existing test's regex —
`test_report_gate_race.py`'s meeting-room check expected the cancel-then-
write as one literal adjacent pattern. The underlying invariant it
protects (the rAF gate's `.cancel()` must run before ANY write, or the
stream's last raw token clobbers the clean one a frame later) was never
at risk — `update.cancel()` is still the first statement in the block —
so the regex was widened to match the new three-line shape, then
fire-tested by moving `.cancel()` after the write again to confirm it
still catches the real race.

### PUBLISH_SITE — a clean pass, and the settings gate actually works this time — 2026-08-12

After yesterday's finding that GENERATE_IMAGE/VIDEO's settings keys are
gated but never writable anywhere, checked the other ICP-Services module
gated the same shape: Settings → MODULES → "Publish to Web," which flips
`s.icpServices.publish`, read by `icpPublishEnabled()`, which gates the
`PUBLISH_SITE` tool. This one is not a repeat of yesterday's bug.

Toggled it on in Settings, reloaded the office, reopened Settings — still
ON. The write side exists and persists, unlike `imageProvider`/
`videoProvider`, which have no write side anywhere. `togglePublish`
(`modals/settings.jsx`) writes through `CafresoHQClient.setSettings`,
same mechanism every other working toggle on that panel uses.

Drove the actual publish mechanics independently of an LLM turn (local
Ollama's tool-calling has been unreliable all session — narrating a plan
instead of emitting the marker, more than once) by hitting the same `/fs`
endpoints `publishSite()` calls, directly: uploaded a real `index.html`
to a throwaway directory via `POST /fs/upload`, fetched it back through
`GET /fs/site/<b64root>/index.html` (200, real content, and the bare-
directory fallback to `index.html` also works), then uploaded the
`.url` shortcut file the same way `publishSite()`'s second step does and
fetched that back too. Full loop, no shell bridge, no ICP identity
required — exactly what the code comments claim ("Publish works without
the bridge — always store locally").

One harmless dead-code note, not fixed: `TOOL_REGISTRY.publish_site.run`
(the static registry entry) hardcodes `tip: false` and `agentId: null`,
which contradicts its own doc string ("tip jar rides along unless
tip=off"). It doesn't matter — grepped every reference to
`TOOL_REGISTRY.publish_site` in `hq-runtime.jsx` and there is exactly
one, the `...TOOL_REGISTRY.publish_site` spread in `toolsForAgent` that
immediately overrides `.run` with a correct, per-agent-bound version
(real `tip` default from `icpWalletEnabled()`, real `agentId`/
`agentName` so the tip jar credits the right wallet). The static `.run`
is provably unreachable through any live path today — but it is a trap
for whoever next refactors `toolsForAgent` and forgets the override,
since nothing currently exercises the static version to catch a
regression there. Left alone rather than touched with no live bug behind
it; worth a one-line fix (delegate the static `.run` to the same logic,
or drop it and require the override) if `toolsForAgent` is ever
restructured.

### The most consequential confirm dialog in the app had the wrong button — 2026-08-13

Drove Settings → ROSTER for the first time this session — the per-agent
model/temperature/tools/tool-format/elevation editor, never previously
exercised live. The tool grid toggles correctly and PERSISTS: unchecked
"Web Search" for a seeded coworker, and `hq-state/memory/agents.json`
came back with `web` actually removed from `tools` — the write path is
real, not decorative.

Then reached the "🛡 File & shell access" toggle — the elevation grant,
the single highest-consequence control in the entire product, since it's
the one switch that gives a coworker real shell and file access on the
boss's machine. The confirm dialog read exactly right: *"Grant Llama
COMPUTER ACCESS? They will be backed by an elevated CafresoHQ session
that can read/write files and run shell commands on this machine. ...
Continue?"* Its button read **"Delete."**

Root cause, once traced: `window.hqConfirm(message, opts)`
(`ui/feedback.jsx`) renders its OK button as `opts.okLabel || (opts.danger
? 'Delete' : 'OK')`. `danger: true` is the right call here — this
deserves red-button styling — but the settings call site
(`modals/settings.jsx`) only ever passed `{ danger: true }`, so it
silently inherited a default written for the OTHER common case: most
`danger: true` confirms in this app genuinely ARE deletions (the API's
own doc comment uses `hqConfirm('Delete "x"?', {danger: true})` as its
canonical example), and this one just never got its own label.

Grepped every `danger: true` confirm in the codebase (17 total) rather
than fixing the one found live, since a default this easy to fall into
is exactly the kind of bug that lands more than once. It had: the
IDENTICAL bug, word for word, sat in `modals/hire.jsx`'s hire-with-
elevation dialog — same question shape, same "Continue?", same missing
label, on the OTHER path to the same grant. Four more, lower stakes but
still wrong: `app.jsx`'s "STOP ALL?" and its in-progress-task-displacement
confirm ("Start X instead? ... goes back to the inbox and ... is lost"),
and `features.jsx`/`ui/onboarding.jsx`'s "Clear all receipts?" / "Clear
all notifications?" — four dialogs asking one thing and a button
answering another.

Fixed all six with an explicit `okLabel` matching what each dialog
actually does (`'Grant access'`, `'Hire'`, `'Stop all'`, `'Start it'`,
`'Clear all'` ×2) — the same mechanism `views/projects.jsx`'s two
"Discard unsaved changes?" dialogs and `modals/settings.jsx`'s "Stop
payroll?" dialog already used correctly, so this wasn't a new pattern to
invent, just one three other call sites had already found and six
hadn't.

Pinned by `scripts/test_confirm_dialog_labels.py`, written general on
purpose: it finds every `window.hqConfirm(..., {danger: true})` call
site in the app (not just the six fixed here) and requires EITHER an
explicit `okLabel` OR the dialog's own message to contain the word
"Delete" — the one case where the default is actually coherent with what
the dialog asks. Two call sites pass their message as a pre-built `msg`
variable rather than an inline string (`views/projects.jsx`); the check
follows the variable back to its assignment rather than false-flagging
them. Fire-tested by reverting the ROSTER fix alone — one failure, named
correctly, nothing else disturbed. Verified live after rebuilding: the
same elevation toggle now shows *"Grant access."* Cancelled rather than
confirmed, per this session's standing rule against ever actually
elevating a coworker; `agents.json` confirmed `elevated: false` after.

### Four tool checkboxes in Hire/Roster gated nothing, silently — 2026-08-13

Same ROSTER drive, a different corner of the same panel. Noticed "Image
Gen" (`id: 'img'`) doesn't do anything — `toolsForAgent` gates
`GENERATE_IMAGE` purely on `s.imageProvider` (2026-08-12's finding),
never on `agent.tools`. That's already tracked (`task_287b0e8f`), but it
raised an obvious question about its nine siblings in the same grid: how
many of THOSE actually gate anything either?

Audited by grepping every `claimed.has('<id>')` check inside
`toolsForAgent` and every `TOOL_REGISTRY` entry name, against all 10 ids
in `TOOLS_CATALOG`. Only three do anything: `web` (gates `SEARCH`),
`vault` (gates the `VAULT_*` family), and `wallet` (gates the `WALLET_*`
family, conditionally). `code` and `files` are harmlessly redundant —
real file/shell access exists, but it's gated on the separate
`agent.elevated` toggle, not on checking these boxes. `img` is the
already-tracked orphaned-setting case. And `email`, `cal`, `db`, `slack`
gate **nothing, because those tools were never built at all** — not
ungated, not parked, just absent from `TOOL_REGISTRY` entirely. A boss
checking "Email Send" for a coworker in Hire or Roster was granting
nothing, with no indication that anything was wrong.

The model side was never actually at risk, which is worth stating
precisely rather than overselling this: `agentStream`'s prompt
explicitly separates *"Claimed capabilities: web, email, ..."* from
*"the following are wired up for real execution: web"*, and instructs
the model to only invoke the wired subset and say so plainly otherwise.
A coworker claiming `email` correctly refuses to pretend it sent one —
the same claimed-vs-wired separation already verified sound for SEARCH.
The harm was entirely the boss-facing checkbox implying a real,
functioning grant where there was none.

Fixed by extending `visibleToolsCatalog()` (`modals/settings.jsx`) — the
single filter Hire and Roster ALREADY shared for hiding the wallet
checkbox when the Money module is off — to also drop the four
never-implemented ids. One change, both surfaces, confirmed by checking
`modals/hire.jsx` imports the same function rather than rendering the
raw catalog. `code`/`files`/`img` deliberately left visible: each is a
real product decision (redesign the grid around elevation, or build
Settings → Media) that a filter shouldn't make silently, unlike
`email`/`cal`/`db`/`slack`, where there is no ambiguity — the capability
does not exist, full stop.

Pinned by `scripts/test_never_wired_tools_hidden.py`, written to also
catch drift in the other direction: it fails if any of the three
genuinely-wired ids (`web`/`vault`/`wallet`) ever stop being checked in
`toolsForAgent`, and it fails if `email`/`cal`/`db`/`slack` ever START
being checked there without also coming out of the hidden set — a
future implementer shouldn't have to rediscover this audit. Fire-tested
by reverting the fix (5 failures, all correctly named). Verified live:
a coworker seeded with stale `email`/`db` claims (leftover data from
before this fix — harmless, since nothing ever reads them) now shows
exactly 5 tool checkboxes instead of 9, with `Vault Notes` correctly
still checked and the four dead ones simply absent rather than present-
and-inert.

### Projects — a clean pass, driven end to end for the first time — 2026-08-13

The Workspace/Projects panel (`views/projects.jsx`'s `ProjectsView`, the
"Classic" tab — folders coworkers build in, real files a boss can watch
change) had never been driven this session. Added a real local folder
(two files, one `.md` one `.txt`) as a project on a throwaway office and
worked through it end to end, deliberately skipping the Terminal
sub-tab (it can spawn a real PTY / Claude Code / Codex session, out of
bounds under this session's standing no-paid-CLI-dispatch rule).

Every step landed clean: the file list showed the real files with real
byte counts (18 B / 43 B, matching what was written to disk); opening
`notes.txt` loaded its real content into the editor; editing it flipped
an unsaved-dot indicator and a `Save` button into view; clicking Save
wrote the edit to the actual file on disk (confirmed by reading it back
outside the app) and the status flipped back to "Saved"; `README.md`'s
Preview toggle rendered real markdown (`# Test Project` → a styled
heading); checking a coworker in the "ASSIGNED" list persisted the
assignment, enabled the "TALK" button, and — matching the comment at
`ProjectsView`'s `toggleAgent` that says the per-project chat tab "keys
off `agentIds`" — a new **TEST PROJECT** tab appeared in the chat panel
live, with its own project-scoped room ("No messages in this project
room yet... @-mention just some of them," an honest empty state, not a
fabricated one). The onboarding checklist's "Create your first Project"
step checked itself off as a side effect of the real action, not a
separate manual step.

No defects found. Recorded as a clean pass rather than skipped
silently — the same reason the SEARCH raw-key-leak and the DM_TO
mechanic-is-sound findings earlier in this file were written up even
though nothing needed fixing: a surface that has never been driven and
turns out to work is still worth knowing, and the absence of a "driven,
clean" entry reads identically to "never checked" until someone writes
one down.

### Money & Payments, driven on — the bridge gate holds even locally — 2026-08-13

The other half of the ICP Services panel (Publish verified two days
ago; Money never driven). Seeded a coworker already claiming `wallet`
in its tools — the worst case for this test, not a random one — and
toggled Money & Payments ON on a throwaway office with no
ai.cafreso.com shell behind it. The confirm dialog and the resulting
"module is on, but balances and sends need your Internet Identity...
Until then agents cannot move any funds" panel both rendered exactly as
the code promises.

Reading the code says `icpWalletEnabled()` also requires
`CafresoHQChain.isAvailable()` (the postMessage bridge to the II-holding
shell), so WALLET_BALANCE/WALLET_SEND should stay ungated regardless of
the local toggle. Said so rather than just trusted: `window.HQ` isn't
exposed globally (module-scoped), so verified it a level deeper —
monkey-patched `window.fetch` to capture the actual outgoing request to
the local Ollama backend and read the real system prompt a live chat
turn produced. It reads: *"Claimed capabilities: chat, vault, wallet. Of
these, the following are wired up for real execution: VAULT_SEARCH, ...
ACK, SPAWN_SUBAGENT, ..."* — no `WALLET_BALANCE`, no `WALLET_SEND`,
anywhere in the wired list, confirmed against the actual bytes sent to
the model, not a description of them.

One small-model wrinkle, not a bug: asked "what is your ICP wallet
balance?", Llama didn't say "I don't have that tool" as instructed —
it emitted `[NEEDS_APPROVAL: check ICP wallet balance]`, which landed
correctly in the boss's approval tray ("by Llama · awaiting stamp").
Confused, but safely confused: `NEEDS_APPROVAL` is a generic, always-
taught marker independent of any specific tool grant, so the office did
exactly what it's supposed to with a request it can't itself fulfill —
surfaced it to a human rather than fabricating an answer or a balance.
Nothing moved, nothing was invented; left the pending approval alone
and tore the whole office down with it rather than approving/rejecting
something that was never going to execute either way.

### The graph's own "close this panel" button was unclickable — 2026-08-13

Drove the vault Graph view for the first time this session: seeded three
linked notes, opened Vault (which lands on the graph), and the analytics
panel opened with real, correct numbers — 3 notes, 3 links, "Biased: one
dominant topic," matching the seeded triangle exactly. Then tried to
close it. Two clicks on "Hide analytics ›," at its own correct on-screen
position, did nothing.

Not a targeting mistake — checked at the DOM level.
`document.elementFromPoint()` at the exact center of the button's own
`getBoundingClientRect()` returned a *different* element: the analytics
panel's content div, not the button. The top toolbar (`views/graph.jsx`)
holds filter/source/color/scope controls plus four buttons plus the
analytics toggle plus minimize — around ten controls in a `flexWrap:
'wrap'` row — and at this session's own driving width (874px, an
ordinary size, not a narrow-viewport repro) it wraps to a second line.
That second line lands inside the analytics panel's own territory
(`position: absolute, top: 50`), and since the panel is defined AFTER
the toolbar in the JSX, default DOM-order stacking handed it the win —
so the moment a boss opened the panel on a normal window, its own close
button became permanently unreachable by a real click.

Fixed with an explicit `zIndex` on both: the toolbar above the panel, so
wrapped controls always win hit-testing no matter how many lines they
wrap onto. Verified live after rebuilding — closed the panel, reopened
it, closed it again, both directions working — and confirmed via the
same `elementFromPoint()` check that the button now resolves to itself.

Pinned by `scripts/test_graph_analytics_toggle_clickable.py`
(structural: both elements declare an explicit `zIndex`, toolbar's
higher than panel's), fire-tested by reverting the fix — 2 failures,
both correctly named.

### The command palette, driven — clean, and a tooling gotcha worth keeping — 2026-08-13

`Cmd/Ctrl-K` opened cleanly (42 commands, real sections — Navigation,
Actions, Toggles, Windows), search-filtered correctly, and mouse-picking
a result ran it and navigated. Then keyboard — the palette's own stated
mechanism, "↑↓ navigate · ↵ run" — looked broken: `ArrowDown`/`Enter`
sent via this session's own driving tools appeared to do nothing, twice
in a row, footer hint and all.

Chased it all the way down before writing it up, because "the palette's
core interaction is broken" would be a serious claim. Confirmed the
input was genuinely focused with the right value; confirmed via
`document.elementFromPoint()`-style checks that the real DOM node was
receiving events; confirmed React's own `onKeyDown` prop function was
present and callable; called it directly with a plain `{key:'Enter'}`
object, bypassing all dispatch machinery. That last call — checked
correctly, in a genuinely separate round-trip rather than the same
synchronous script block (a mistake made and caught mid-investigation:
an earlier same-tick check of `ArrowDown` read state before React had
re-rendered and looked like a second bug that wasn't one) — closed the
palette and ran the command. The application's own keyboard-handling
code is correct.

What wasn't correct was the test input: this session's `key` action
sending the string `"Return"` does not produce an event this app's
`e.key === 'Enter'` check matches, while sending `"Enter"` does — same
physical key, different string, only one of which this environment's
key-name mapping honors. Worth keeping as a standing note for future
ticks driving any Enter-to-submit surface in this harness: use `"Enter"`
as the key text, not `"Return"`, and when a keyboard interaction looks
broken, verify state in a separate tool round-trip before writing up a
finding — a same-tick check after a state-changing dispatch can read
the DOM before React has committed the re-render and manufacture a
bug that was never there.

No code changed. A real capability (keyboard-driven command running)
was verified working, and a real process mistake was caught before it
became a false entry in this file.

### Receipts — the elevation dialog's "every action logged" promise, checked — 2026-08-13

Traced the elevation-grant dialog's claim ("every tool call is logged")
to its actual mechanism: `recordToolReceipt` (`app.jsx`), which writes
into the same `receipts` state the Receipts modal reads. Seeded a
throwaway office with three realistic receipts (a deliverable, a
tool-execution, a rejected publish) directly into `hq-state/receipts.json`
to drive the modal itself without depending on a live model successfully
emitting a tool marker.

Everything held: real per-kind stamps and tinting (📝 green deliverable,
🛠 tool-execution with no PIN button — correctly excluded, since
`onPin && r.kind !== 'tool-execution'` — ✕ red rejected), the filter
tabs correctly narrowed the list and updated the "N of 3" count, PIN
landed a real sticky on the CEO desk corkboard (confirmed by checking
the office floor after, not just the click succeeding), and CLEAR ALL
still shows *"Clear all"* — the exact dialog fixed several ticks ago in
this same file's confirm-dialog-label sweep, now re-confirmed live
rather than just left to the earlier fix's own test.

No defects found. Also confirms the model side of the underlying claim
is architecturally sound without needing a successful live tool call to
prove it: `recordToolReceipt`'s own logic (`!agent.elevated &&
!isDeliverable → return`) means every elevated agent's tool call is
captured regardless of type, and every agent's deliverables are
captured regardless of elevation — the audit trail the elevation
dialog promises is the real one, not a decorative one.

### Export tools verified working end to end, including a fallback edge case — 2026-08-13

The 2026-08-12 export-tools fix (the missing `_read_json_body` binding)
left one thing explicitly unverified: "a full successful export... since
no export library is actually installed on this machine." Closed that
today. `pip install` on this machine's system Python is blocked by
Homebrew's PEP-668 guard (both the plain and `--user` forms), and
overriding that with `--break-system-packages` risks the user's real
Python installation — not a call to make unilaterally under an
autonomous loop. Installed `python-pptx`, `python-docx`, `weasyprint`,
and `reportlab` into an isolated scratch venv instead (created and
destroyed within this tick, touching nothing outside it) and ran a
throwaway office under that venv's interpreter.

All three formats produced real, valid files, confirmed by `file` (not
just a 200 response): a genuine Microsoft OOXML `.docx`, a genuine OOXML
`.pptx`, and a real 1-page PDF. The PDF path surfaced something worth
knowing beyond "it works": `weasyprint` imports fine as a Python package
but needs the native Pango library to actually run, which this machine
doesn't have — so importing it raised `OSError`, not `ImportError`.
`_export_pdf`'s weasyprint attempt is wrapped in `except ImportError:
pass` **followed by** `except Exception as e: ...` with no `return` —
so the OSError fell through exactly like a missing-package ImportError
would, and the reportlab fallback produced the PDF instead
(`{"renderer": "reportlab"}`). The graceful-degradation code was
already written correctly for a failure mode broader than its own
docstring names.

Not done, and stated plainly why: the user's actual `serve.py` still
runs on system Python without these libraries — this was a capability
verification, not an environment change. If they want the exports to
actually work rather than fail gracefully, the command is
`pip3 install --break-system-packages python-pptx python-docx weasyprint markdown reportlab`
(weasyprint's CSS rendering additionally wants `brew install pango`;
without it, PDFs still work via the reportlab fallback just proven
live, only simpler ones). Left for them to run, not run for them.

### The same label, two different rooms — the CEO panel's own "Sit 1:1" was the wrong one — 2026-08-13

Drove the 1:1 with CafresoHQ for the first time this session — a
feature named in the topbar hint on every single screenshot all
session ("CLICK THE 1:1 SOFA FOR A ONE-TO-ONE") but never itself
clicked. Two places in the app carry the identical label, word for
word: the office floor's sofa sprite, and the CEO panel's own "Sit 1:1"
quick-action button (opened via the CEO's sidebar card). Clicked the
CEO panel's version first, since that's the more obvious entry point
for a boss who hasn't found the floor sofa yet — and got the ordinary
multi-thread Chat window, not the feature its own label names.

The floor sofa's version was already correctly wired to `FocusMode`,
`app.jsx`'s dedicated "1:1 WITH CAFRESOHQ · QUIET ROOM · NO
DISTRACTIONS" overlay. The CEO panel's identically-labeled button was
wired to a bare `navTo('chat')` — same words, silently lesser
experience, and which one a boss actually got depended entirely on
which of two unmarked entry points they happened to use first.

Fixed by pointing the CEO panel's action at the same `setFocus(true)`
the floor already uses — one line, no other changes needed, since
`CEOPanel` already wraps every quick action in a `fire()` helper that
closes the panel afterward regardless of what the action does.
Verified live end to end after rebuilding: CEO panel → Sit 1:1 → the
real quiet room opens, with the same shared chat history the floor
sofa and the regular Chat panel all read from (not a separate silo);
sent a real message and watched the honest §7 failure path render
correctly inside it too (`⚠ hit a snag — couldn't reach that brain —
it looks offline from here`, this machine's default CEO brain having
no local Hermes gateway to answer — an environment fact, not a defect,
and the exact same honest sentence already verified elsewhere in this
file); "LEAVE ROOM" returned cleanly to the normal view, and the
"Chat with your team" onboarding step checked itself off as a result
of the real interaction.

Pinned by `scripts/test_ceo_panel_sit_1on1.py`, fire-tested by
reverting the fix — 2 failures, both correctly named.

### GitHub-clone projects — a clean pass, plus a testing-isolation lesson — 2026-08-13

Drove the "Add Project → GitHub repo" tab for the first time this
session. Empty-URL submission correctly blocked with an inline
"repo URL or owner/repo required," no crash. Submitted a deliberately
nonexistent repo (`owner/repo` shorthand, to also confirm the
normalize-to-`https://github.com/...` step) rather than cloning a real
one — downloading real content, even a small public repo, needs the
user's explicit permission per this session's standing rules, and a
throwaway-office tick under an autonomous loop is the wrong moment to
pause and ask. `git clone` ran for real against GitHub's real remote,
came back `128`/"Repository not found," and the app surfaced the raw
git output cleanly in the modal — honest, actionable, no stack trace.

That failed attempt surfaced something worth more than the pass/fail
result: the clone target it logged was `/Users/anthonym/…`, this
machine's REAL home directory — not the isolated
`CAFRESOHQ_HQ_STATE_DIR` this session's throwaway offices have used all
along. `CAFRESOHQ_ALLOWED_DIRS` (which governs where local-folder
projects and GitHub clones may land) is a separate env var from the
state-dir one, defaults to `expanduser('~')` when unset — a sensible
default for a real single-user install — and none of this session's
throwaway-office setups ever set it. Confirmed nothing was actually
left behind (`git clone`'s own failure path cleans up its partial
directory), so no harm this time, but the near-miss is the finding: a
successful clone test run the same way would have written real files
into the boss's actual home folder, not a disposable scratch location.
**Standing note for future ticks:** any investigation touching
`Projects → Add`'s local-folder or GitHub-clone paths must also set
`CAFRESOHQ_ALLOWED_DIRS` to an isolated scratch directory, the same
discipline already applied to `CAFRESOHQ_HQ_STATE_DIR` — this session's
existing throwaway-office recipe does not cover this surface by
default.

No code changed — the feature itself is correct; the gap was in this
session's own test setup, caught before it did anything.

### FileBrowserModal — driven with the isolation lesson applied, clean pass — 2026-08-13

Immediately put the previous entry's own lesson to use: drove
Add Project → Local folder → **📁 Browse** with `CAFRESOHQ_ALLOWED_DIRS`
properly set to a scratch sandbox this time, rather than the default
real-home-directory fallback. Confirmed `/fs/browse` opened correctly
scoped to the sandbox (real seeded folders and a file, not the actual
machine's home directory), drilled into a subfolder and back up with
`↑ Up`, selected it, and watched both the Name and Absolute Path fields
in the parent modal auto-fill correctly from the selection. Completed
the flow with **Add** and got a real project — file list showed the
real seeded file with its real byte count, and the "ASSIGNED · 0 — No
coworkers hired yet" empty state was honest, not fabricated.

No defects found — a clean pass, and a working demonstration that the
prior tick's isolation note is load-bearing: this same drive without
`CAFRESOHQ_ALLOWED_DIRS` set would have browsed and potentially
selected real folders from this machine's actual home directory.

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

> ✅ **A computed verdict is a promise too — the Vault analytics panel,
> 2026-08-11/12.** The rule above was written about copy a human wrote. The
> same standard applies to sentences a *formula* writes, and that panel was
> publishing five it could not stand behind. Every one was found by running
> the shipped `analyze()` on degenerate input, not by reading it:
>
> | What it said | On what | Why it was wrong |
> |---|---|---|
> | "Dispersed — many scattered topics" | an empty cabinet | Louvain returns NaN modularity for an edgeless graph; NaN is false against every comparison, so the chain fell through to its final `else` |
> | "Weakly connected: A ⟷ B" | two groups joined by **six** edges | `score` only ranks pairs *relatively* — there is always a worst pair, so the alert could never not fire |
> | "Weakly connected: Llama ⟷ Hermes" | the real office | true, and useless: Hermes is one unused coworker, and *everything* is weakly connected to an orphan |
> | "0% · 3 items" twice | two equal halves of the map | `share` is an *influence* share; with no brokering anywhere it collapsed to 0 for everyone |
> | "Topics:" / "Separate clusters:" with nothing after them | an empty vault | the `N === 0` early return emitted two fields; the rest rendered as `undefined` |
>
> Three lessons worth keeping separate:
>
> **A degenerate input does not produce a degenerate answer — it produces a
> confident wrong one.** None of these failed loudly. NaN did not throw, the
> missing metrics did not error, the gap did not warn. Each one silently
> picked the branch that happened to be last, or the pair that happened to
> sort first, and printed it in the same voice it uses for real findings.
>
> **A relative ranking must not be published as an absolute claim.** That is
> the whole of the gap bug. "The weakest of your pairs" is a true statement
> that becomes false the moment it is rendered as "Weakly connected", and
> nothing in the code marked the transition. The fix is a threshold that
> survives being said out loud — *fewer links across than there are items in
> the smaller group* — because a threshold you can't phrase is one you can't
> check.
>
> **Say the absence out loud rather than leaving a hole.** `unformed`,
> "Topics: 0", and the now-conditional "Most influential" / "Main topics"
> headings are all the same move: an honest "there isn't one yet" beats both
> a guessed verdict *and* a blank space, because a bold heading over nothing
> reads as a surface that failed to load. Same call as the contrast sweep —
> a cannot-say is an answer.
>
> Both fixes are pinned by tests that call the real `analyze()` through an
> esbuild CJS bundle (the worker's subpath imports defeat bare node ESM), and
> both were fire-tested in *both* directions — the reverts, and the
> silence-everything shortcut that would pass every check written so far.
> `scripts/test_graph_structure_verdict.py`, `scripts/test_graph_gap_verdict.py`.
>
> Still open, deliberately: on the real office "Main topics" reads **100% ·
> 3 items** over three **0% · 1 items** rows. Those are influence shares and
> they are arithmetically correct, but nobody reads that percentage as "share
> of brokering" — they read it as "how much of my work is this". Narrowing
> the fallback to the fully-degenerate case was the defensible fix; deciding
> what that number should *mean* is a design call, not a bug fix.

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

  > **Reproduced 2026-08-12 in a different and harder shape — invented
  > CITATIONS.** Walked §3.6's five-minute flow end to end on the free local
  > brain: starter card → "Research brief: why small teams miss deadlines" →
  > Llama → filed to `Research/…`. The brief's own wording tells the coworker
  > *"Say where each finding came from … Never invent a citation."* All five
  > findings came back tagged `(Source: …)` anyway, and while three name real
  > books, one cites a **Harvard Business Review article "Why Small Teams
  > Fail"** that does not appear to exist. Four lines below it the footer
  > reads *"Nothing opened, saved or looked up for this one."* The mitigation
  > held: the two statements sit on the same page and contradict each other,
  > exactly as designed, on a case nobody staged.
  >
  > Worth separating from the lemon-colour example rather than filing next to
  > it, because the shape is more dangerous. An invented `[Vault path: …]` is
  > checkable in one click — open the cabinet, it isn't there. An invented
  > journal article is not: it is plausible, authoritative-looking, and a
  > reader who trusts the bullet has no reason to scroll to a footer to
  > cross-examine it. The office's record still disagrees with the coworker;
  > it just disagrees more quietly than the reader needs.
  >
  > Both facts — "consulted nothing" and "claims five sources" — are known at
  > filing time, so the contradiction could be stated instead of merely
  > available. The care it needed: a detector that cries fabrication at an
  > honest reply would be its own §7 failure, and the brief legitimately
  > invites *"(Source: what I already know)"*, so a bare "Source:" substring
  > match would fire on exactly the compliant behaviour the office asked for.
  >
  > **Stated since 2026-08-13** (`citesOutside`, app/artifacts.jsx). The rule
  > fires only when the run's record is EMPTY and the reply points outside
  > the coworker's own head — a URL, or a `Source: …` attribution naming
  > something that is not "what I already know" / "from memory" / "no
  > specific source". When both hold, the footer gains one line: *"The note
  > above mentions sources, but nothing was opened or searched while it was
  > written — treat those as recalled, not checked."* — a report of what the
  > office observed, not a judgement of the coworker. A quoted title floating
  > in prose is still left alone (the placeholder-detector table below is why
  > "exact" prose patterns cry wolf); a miss falls back to this bullet's
  > passive footer, which remains the floor. Fire-tested both ways before
  > shipping — detector silenced, 8 suite checks failed; own-head exemption
  > removed, 7 failed — and re-walked live the same day: a fresh brief on
  > remote startups cited Buffer, Harvard Business Review, Forbes and Gallup
  > on an empty record, and the filed delivery said the contradiction out
  > loud, two lines under the footer, on a case nobody staged.

  > **A third instance, and the most ordinary one — 2026-08-12.** Re-walked
  > §3.6 on a clean install to check the day's eight commits had not broken
  > the headline flow. It had not: front desk opens itself, hire Llama, pick
  > **First draft**, one field, START → **33.3 seconds** to a filed artifact
  > in `Drafts/`, with real prose, the local date, an *Assumptions* section
  > and an honest Working footer.
  >
  > But the delivery opens *"Welcome to CafresoHQ, **[Teammate's Name]**!"* —
  > and the brief the OFFICE wrote says, in as many words: *"no placeholder
  > text and no '[insert here]' gaps. Where you need an assumption to keep
  > moving, make a sensible one and list your assumptions at the end."*
  > (`modals/starter.jsx:56`.) The model then listed, as an assumption, *"The
  > new teammate's name is available in the office's records"* — which
  > contradicts the placeholder it had just written: if the name were
  > available it would have used it.
  >
  > This one is worth separating from the invented citation because it looks
  > EASIER to catch and is not. A bracketed placeholder seems like an exact
  > pattern, and the office's own instruction forbids it, so a detector needs
  > no judgement. Probed the obvious rule (`\[[A-Z][^\]]{0,40}\](?!\()`)
  > against the real artifact and four controls:
  >
  > | input | verdict |
  > |---|---|
  > | `[Teammate's Name]` (the real one) | caught ✓ |
  > | `[the docs](https://…)` markdown link | correctly ignored ✓ |
  > | `[1, 2, 3]` | correctly ignored ✓ |
  > | `Cite [Smith 2020] properly.` | **false positive** |
  > | `Press [Enter] to continue.` | **false positive** |
  >
  > Two of five controls cry wolf on ordinary prose — a citation and a key
  > name — which is the §7 failure the citation entry above already refuses
  > to commit. So: not shipped. Recorded with the counter-examples so the
  > next attempt starts from the false positives rather than rediscovering
  > them, and so nobody mistakes "the pattern is exact" for "the rule is
  > safe".
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

  > ✅ **The friction is gone; the permissions question is untouched
  > (2026-08-12).** The missing tool is now handed over inside the Research
  > modal — named, one button, with "Vault Notes lets them write notes into
  > your cabinet" under it — using the same `onUpdateAgent` the Roster uses.
  > Nothing is granted that the boss could not already grant; what changed is
  > that it no longer requires knowing the app's furniture, which is most of
  > what "no expertise required" means. Driven on a throwaway zero-config
  > office: hire Llama → open Research → one click → the row drops its
  > "(needs Vault Notes)" suffix and START enables once a topic is typed.
  >
  > Whether a detected brain should ARRIVE with Vault Notes on is deliberately
  > still open and still the boss's call. A button they press, with the cost
  > stated, is what a permissions decision should look like; a default is a
  > different question and this does not answer it.
  >
  > **Two adjacent bugs fell out of driving it, and the worse one had nothing
  > to do with the gate.** The requirement hint rendered UNCONDITIONALLY — on
  > the real office, with Vera selected (web + email + cal + vault, not
  > disabled, able to start immediately), the modal still read "NEEDS WEB
  > SEARCH AND VAULT NOTES — TURN THEM ON IN SETTINGS → ROSTER". The office
  > instructing a boss to fix a thing that is not broken is the same fault as
  > the graph verdict recorded above: a true-sounding sentence bolted to a
  > case it does not describe. And the dropdown row named the MODE's
  > requirement ("needs Web + Vault tools") while the sentence beneath it
  > named the coworker's actual gap (Vault Notes only, since Llama has web) —
  > one control disagreeing with itself about one coworker.
  >
  > **The gate itself is correct — do not "unify" it with the Night Shift.**
  > They do not share a toolset. In-tab Research runs on the browser's
  > per-agent registry, so an ungated run silently delivers nothing;
  > `missions.jsx` records the measurement (round 4, transcript claimed
  > "Wrote 1", `writes: null`, no `Research/`). The Night Shift runs
  > server-side and grants the write without consulting `agent.tools` at all.
  > `scripts/test_mission_tool_gate.py` pins both halves, including a check
  > that fails if anyone adds a tools gate to `night_runner.py` — that would
  > read as hardening and would actually take the overnight feature away from
  > every front-desk hire.

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
- **The office floor is not touch-sized — but "coffee" always had another door.**
  MEASURED 2026-08-12 at 375×812, the first mobile pass of this codebase.
  Of the **15 controls inside `.px-scene`, 14 are under the 44px touch
  minimum** — the coffee mugs are **12×12**, the work-log paperstack 22×26.
  `docs/strategy/06-app-update-todo.md` Track 6 already carries this as an
  open P1 ("Interactive targets ≥44px"); this is the measurement behind it.
  **That half is unchanged and still open — the art was not touched.**

  The obvious fix — expand the hit areas with a transparent overlay and
  leave the art alone — is **not safe here, and the numbers say so**: the
  tightest gap between two of those small controls is **11px**, between the
  filing cabinet (`.px-cab`, open the vault) and the 1:1 sofa
  (`.px-couch`, sit with the CEO). Growing both to 44px would overlap them
  by more than the gap, trading a hard-to-hit target for a
  wrong-thing-happens one on two controls a boss actually uses. Scaling the
  whole scene up is no freer: it already renders 345px wide inside a 375px
  viewport, so there is no slack to grow into without sideways scroll.

  > ✅ **CORRECTED 2026-08-12, same day it was written — the reachability
  > half of this entry was wrong, and it was wrong in the way this section
  > has now been caught twice.** The original said: *"`onCoffee` appears 5×
  > in `ui/office.jsx` and 0× in `views/core.jsx`, so sending a coworker for
  > coffee is reachable on a phone only through that 12×12 mug."* The grep
  > was accurate; the inference was not. **`views/core.jsx` has no
  > `onCoffee` because it does not need one** — every roster card is
  > `onClick={()=>onInspect(a)}`, `onInspect` is `setInspect(a)`, and
  > `<InspectPanel>` is handed `onCoffee={onCoffee}`, the same handler the
  > mug calls. The panel has carried a **☕ COFFEE BREAK** button at a
  > correct **115×44** the entire time. A grep over one file was read as
  > proof about a path that runs through three.
  >
  > This is the same shape as the Night Shift correction three bullets up,
  > five days apart: a claim generalised from a static read without driving
  > the other half. Worth stating plainly — the recurring failure of this
  > ledger is not dishonesty about what is broken, it is confidence about
  > what is *unreachable* based on where a symbol does not appear.
  >
  > **Driving it found a worse bug, in a different place.** `.inspect` was
  > `position: fixed` with no height bound of any kind, so the panel stood
  > **984px tall in an 812px viewport** and nothing in the ancestor chain
  > could scroll to the overflow (`.app` is `overflow-y: hidden`, and a
  > fixed element does not extend the document — `scrollIntoView()` on the
  > button moved it zero pixels). **252px hung below the fold, and all three
  > of the panel's actions were in it**: `elementFromPoint` at the centre of
  > 💬 MESSAGE, ☕ COFFEE BREAK and LET GO each returned `null`. The old
  > entry reached a true-sounding conclusion for entirely the wrong reason —
  > the door was full-size, correctly labelled, and 252px off-screen.
  >
  > Two floating surfaces had to give way, and **both were invisible until
  > the row came back into view** — neither would have been found by
  > reading. The Apps FAB (`z-index: 321`) stole **1221px²** of LET GO, so
  > the right ~40% of a destructive control opened the app switcher; it now
  > stands down while a review is open. The receipts tray shares
  > `--z-window` with `.inspect` *by design* (see the scale at the top of
  > `styles.css`) and `app.jsx` renders it later, so DOM order handed it the
  > corner — at 1280×800 it covered **100%** of LET GO. The panel now sits
  > at `calc(var(--z-window) + 1)`, still below dropdowns and modals.
  >
  > Fixed at the base rule rather than behind a `max-width: 768px` query,
  > because this was never really a phone bug — **desktop was clipping too**
  > (984px into 800px); the phone is just where it always happens.
  >
  > Verified live, not reasoned: panel 64→730 inside 812, clear of the 742
  > tab bar, body scrolling 853px of content in 531px, all three buttons
  > 44px and hittable at five probes across their width; tapped COFFEE BREAK
  > at (214, 697) and got *"COFFEE Cleared Hermes's desk"*. Re-driven at
  > 320×568 and 1280×800. `scripts/test_coffee_reachable_on_mobile.py` now
  > guards the path, the height bound, the scroller (including the
  > `min-height: 0` whose removal is silent), the footer, and both z-order
  > fixes.
  >
  > **What this deliberately did NOT do:** touch the pixel art. §3.2 makes
  > the floor load-bearing, and the 11px cabinet/sofa gap above is still the
  > reason a blanket hit-area expansion is the wrong move. The floor props
  > remain a **desktop-precision affordance**; the phone's full-size path to
  > the same two actions the audit named — coffee, and the work log — is the
  > roster card, which opens the panel that carries both. Both were confirmed
  > present in that panel (a coworker with journal entries renders the work
  > journal; the floor's paperstack only appears in the same condition). The
  > remaining floor props were not audited for equivalent full-size paths,
  > and that is not claimed here.
- **Most of this app's text cannot be contrast-checked automatically, and
  the naive check lies confidently.** Track 6 of
  `docs/strategy/06-app-update-todo.md` lists contrast as an open P1
  alongside touch targets. Audited it 2026-08-12 by computing WCAG ratios on
  rendered text. **The first pass reported 7 failures. Six were fabricated by
  the checker, not by the app** — including "📋 Inbox" at a supposedly
  unreadable 1.01:1, which a screenshot shows as ordinary dark-on-near-white.

  Two bugs, both worth knowing before anyone repeats the exercise. Resolving
  a backdrop by walking ancestors' `background-color` **skips gradients**:
  `.office-task-rail` paints a near-white `linear-gradient`, has no
  background-*colour*, so the walk fell through to a dark navy ancestor and
  every element on that rail scored as white-on-black. And starting the walk
  at `el.parentElement` **ignores the element's own background**, so any
  chip that paints its own fill (the `LIVE` badge) was scored against
  whatever sat behind it — that one produced an exact 1.00:1, which is the
  tell.

  With both fixed: **one real failure** — the vacant nameplate, since fixed
  and pinned in `scripts/test_vacant_plate_contrast.py` — and **27 of ~28
  text nodes simply not measurable this way**, because they sit on gradients
  or pixel art. That is the honest state of this item: it is not "contrast is
  fine", it is "an automated sweep can only see one text node in twenty-eight
  here, and will invent failures for the rest unless it is written to refuse
  them." Verifying the remaining 27 needs pixel sampling or human eyes, and
  the palette variables (`--brand-coffee-2/3`) that the TODO names are only a
  fraction of what actually paints text on this floor.
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

  > **Updated reliability data point — 2026-08-12** (full account earlier
  > in this file, under "coworkers actually work together"). "Lean harder
  > on the prompt" was not a null result after all — it landed, in
  > `app.jsx`'s `dispatchToAgent`, reachable from every dispatch path, and
  > names the exact failure shape ("when the boss NAMES a coworker...
  > that IS a [DM_TO]"). An earlier note worried the fix might have only
  > ever existed in a chat transcript; it did not — it is real, committed
  > code. With the wording confirmed live, the SAME probe against this
  > machine's only free brain (`ollama:llama3.1`, asking and answering
  > with itself, three attempts, three different phrasings including
  > naming the tool outright) still produced **0/3** real delegations.
  > The prompt-wording lever has now been pulled and independently
  > verified reachable; what remains is a genuine 8B-class tool-calling
  > ceiling, not an unlanded or unverifiable fix.

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

> ✅ **Walked end to end on a genuinely clean install, 2026-08-12 — 44
> seconds.** Not a staged replay of the parts: a throwaway office on its own
> `CAFRESOHQ_HQ_STATE_DIR`, zero coworkers, zero tasks, so `firstEver` was
> really true. The front desk opened by itself and listed brains actually
> found on the machine; hired the local Ollama one in a click; the FIRST
> ASSIGNMENT sheet appeared on its own ("Llama is at a desk · pick something
> real to start on") with the three cards and a "Skip — I'll ask in my own
> words" way out. Picked Research brief, typed a subject, and the task
> **dispatched itself** — no assign step, no ▶ START — going straight to
> `doing` on the coworker just hired, exactly as §3.6 words it ("pick a
> starter task → watch it happen").
>
> Measured: task created 13:10:00, artifact on disk 13:10:44. **43.9 seconds**
> from picking the card to a real file at
> `Research/research-brief-what-makes-a-good-first-day-at-a-new-job.md`, XP
> written (`brief`/`done`), and the Working footer present and honest. The
> budget is five minutes; the flow uses about one sixth of it.
>
> Worth separating two paths that look alike and are not, because confusing
> them is easy: the FIRST-RUN sheet auto-dispatches, while the task board's
> empty-state starter cards deliberately mint an UNASSIGNED task and say so
> ("Drag any card onto a coworker's desk to delegate"). Driving the second and
> reading it as the first would report a §3.6 regression that does not exist.

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

> ✅ **The Obsidian-vault UI was fully built and completely unreachable
> (2026-08-13).** `modals/providers.jsx` has a real, finished `VaultTab`
> component — a Storage toggle between a plain local folder and Obsidian's
> Local REST API plugin, a working "DETECT OBSIDIAN" auto-discovery button,
> and save paths for both backends. It's the *only* in-app caller of the
> real, server-backed `CafresoHQClient.vaultConfigure()` /
> `vaultDiscover()` methods — the sole way to point CafresoHQ at an
> existing Obsidian vault, switch storage backends, or move the vault root
> through the UI at all.
>
> Nothing imported it. Grepped every real `import` site for `ApiTab` /
> `VaultTab` / `BraveTab` across the whole app: zero, except one stray
> comment in `views/vault.jsx`. Confirmed at the compiled level too —
> rebuilt via `scripts/build_ui_bundle.mjs` and grepped the output bundle
> for the unique string `"DETECT OBSIDIAN"`: zero matches. esbuild's
> import-graph-following never even compiled the file's code into what
> ships, because nothing reached it from an entry point. The only working
> path to a non-default vault was the `CAFRESOHQ_VAULT` /
> `CAFRESOHQ_VAULT_BACKEND` env vars, set before the server process
> starts — invisible to a normal boss clicking around Settings.
>
> Two faults, not one, once I went to actually wire it up:
> - `VaultTab` itself was declared `function VaultTab()`, no `export` —
>   so even a correct `import { VaultTab } from './providers.jsx'`
>   silently resolved to `undefined` (esbuild warns, doesn't error, and
>   drops the reference from the bundle rather than failing the build).
> - and, obviously, nothing mounted it anywhere.
>
> Fix: exported `VaultTab`, then mounted `<VaultTab />` inside
> `ConnectionsPanel` (`modals/settings.jsx`, the real Settings →
> Connections panel) as a third sibling panel after the existing "ON THIS
> MACHINE" and "CLOUD KEYS" panels it was written to sit next to —
> `ConnectionsPanel` already imported everything `VaultTab` needs
> (`CafresoHQClient`, `HQ`) with matching hook-alias conventions, so the
> component itself needed zero changes beyond the export keyword.
>
> Verified live in a throwaway office: Settings → Connections now shows a
> "MARKDOWN VAULT" panel with a working Storage toggle, a vault-directory
> field, and a DETECT OBSIDIAN button that made a real backend call and
> found an actual local Obsidian vault on the test machine ("33 notes
> indexed"). Didn't press Save on the detected path — that would have
> pointed a throwaway instance at a real personal vault, which the
> button-click alone already proved end to end.
>
> Pinned by `scripts/test_vault_tab_wired.py`, fire-tested against both
> reverts separately (drop the `export`, drop the `<VaultTab />` mount) —
> each one failed the test for its own specific reason, not just "does not
> pass."

> ✅ **Settings → Modules (Money & Payments, Publish to Web) — clean pass,
> no code changed (2026-08-13).** Drove `IcpServicesPanel` live for the
> first time this session, in a throwaway office with no `CafresoHQChain`
> bridge available (i.e. the common case — a plain browser tab, not the
> II-holding shell). Both toggles work correctly and neither pretends to
> succeed at something it can't do yet:
> - **Publish to Web** flips on/off instantly, persists to
>   `cafresohq_client_v1.icpServices.publish` in `localStorage`, no error —
>   matches the code's own comment that publish works via the local `/fs`
>   bridge and only best-effort-syncs the on-chain flag when a bridge is
>   reachable.
> - **Money & Payments** shows its confirm dialog (already correctly
>   labelled "Turn on" / "Turn off" — not one of the six `hqConfirm`
>   call sites this session had to fix), flips on, and — critically —
>   honestly tells the boss the module is on but *balances and sends need
>   your Internet Identity, which lives in the CafresoHQ shell; until then
>   agents cannot move any funds*, with a pointer to `ai.cafreso.com`. No
>   dead end, no silent no-op, no fake success state.
>
> One console `502` appeared during the drive
> (`GET /hermes/v1/models`) — traced to `hermesStatus()`
> (`claude-client.jsx:736`), a liveness probe for a gateway this throwaway
> instance never started. Already wrapped in try/catch and returns
> `{configured:false, models:[]}` on any non-OK response; nothing leaked
> into the UI. Benign network noise, not a defect — noted rather than
> "fixed" because there was nothing to fix.
>
> No test added — nothing to pin; the panel's existing correctness isn't
> at risk from an unrelated future edit the way an *unreachable* component
> was.

> ✅ **The standalone Terminal tab 400'd on every self-hosted install
> (2026-08-13).** Drove Team (staff roster — clean pass, the CEO card's own
> "Sit 1:1" already correctly opens `FocusMode`, matching the earlier fix
> for the floor sofa) and Memory (add/categorize/delete a long-term memory
> entry — clean pass, round-tripped correctly) live for the first time
> this session, then opened the sidebar **Terminal** tab and hit a real
> one: a Hermes PTY session connected, then immediately failed and retried
> forever, with a WebSocket URL carrying `cwd=%2Froot%2FDocuments`.
>
> `/root` doesn't exist on this Mac (confirmed: `ls /root` →
> "No such file or directory") — because `/root/Documents` is the
> **container image's** code-agent sandbox dir, created by
> `docker/Dockerfile` for the managed/OCI deployment where the process
> runs as root. `views/misc.jsx`'s `TerminalView` already had the right
> instinct — it reads `window._TERMINAL_CWD` with that path only as a
> fallback, and its own comment even named the intended escape hatch:
> *"local runs override via `CAFRESOHQ_TERMINAL_CWD` if they want."* But
> nothing ever set `window._TERMINAL_CWD`, anywhere — not serve.py, not
> any HTML template, not any other script. Every self-hosted Mac/Linux/
> Windows install (the entire non-managed audience) got the container's
> path by default, and `pty_server.py`'s own `/terminal/pty` handler
> 400s outright whenever `cwd_path.is_dir()` is false — so this wasn't
> cosmetic, it silently broke the Terminal feature end to end for anyone
> not running the Docker image.
>
> Fix: `serve.py` now computes `_cafresohq_terminal_cwd` from
> `CAFRESOHQ_TERMINAL_CWD` (default `~/Documents`) — the exact same
> local-mode default pattern `CAFRESOHQ_ALLOWED_DIRS` already uses one
> constant up — and injects it as `window._TERMINAL_CWD=...` in
> `_hq_manifest_tags()`, right beside the existing
> `window.__CAFRESO_BUNDLE__` injection. Because the container runs as
> root, `~/Documents` there resolves to the exact same `/root/Documents`
> as before (the Dockerfile creates it at that path specifically) —
> **zero behavior change for the managed path, real behavior for every
> self-hosted one.**
>
> Verified live: rebuilt the bundle, restarted the throwaway office,
> confirmed `window._TERMINAL_CWD` was `/Users/<user>/Documents`, cleared
> the stale reconnect session from `localStorage` (the retry loop had
> latched onto the pre-fix cwd from before the reload), and opened a
> fresh Hermes terminal tab — got a real PTY: *"Welcome to Hermes Agent!
> Type your message or /help for commands."* Server log confirmed:
> `WS detached: ... hermes @ /Users/anthonym/Documents`.
>
> Pinned by `scripts/test_terminal_cwd_wired.py` — imports `serve.py`
> fresh under a controlled `HOME` to check both the default and the
> env-var override, and calls `_hq_manifest_tags()` directly to confirm
> the injection. Fire-tested against both reverts separately (hardcode
> the old default back, drop the injected script tag) — each failed for
> its own specific reason.

> ✅ **The full task loop, driven end to end for the first time this
> session — clean pass (2026-08-13).** Hired the free local Llama
> (Ollama), typed a real task in the Tasks board ("Draft a one-paragraph
> company bio for Cafreso"), assigned it, hit START, and watched the
> whole pipeline run for real: card moved Inbox → Doing → Done, Llama
> streamed an actual reply, a "FIRST DELIVERY" toast appeared, and the
> file landed at `Deliveries/draft-a-one-paragraph-company-bio-for-
> cafreso.md` in the real Markdown Vault — openable, with correct
> "Delivered by Llama · 2026-08-13" attribution and the graph-analytics
> panel picking it up as a linked note. This is the product's central
> promise (task → coworker → real deliverable, filed where the boss can
> see it) and it held together with zero console errors end to end.
>
> One edge came up unscripted: Llama's small local model, on its first
> pass, emitted a malformed vault-append marker (missing closing tag).
> The app caught it and replied honestly in-thread — *"nothing was
> appended in the cabinet — that one needs a closing tag to be written.
> Ask them to try again"* — rather than silently dropping it or writing
> garbage. The model then also emitted a `[NEEDS_APPROVAL: draft company
> bio for CafresoHQ]` marker restating the already-finished task's title
> with no real decision content — exactly the empty-ask edge case
> `extractApproval`'s own comment names (*"the only safe answer to it is
> no"*). Traced `onApprove`'s branches (`app.jsx:4118+`) before acting:
> this generic marker doesn't match `publish`/`hire-agent`/
> `hire-assistant`/`grant-elevation`/`workflow-step`, so Approve or
> Reject is pure local bookkeeping — no real action either way. Rejected
> it, per the code's own stated philosophy. Task board still showed
> exactly one task and one delivery afterward — no duplicate, no orphaned
> state — despite the model effectively replaying the exchange.
>
> No code changed, nothing to pin — this is a small local model's own
> retry/hallucination behavior, already handled correctly by existing
> error paths built for exactly this. Recorded because "does the core
> loop actually work, end to end, live" had never been checked this
> directly before, and it's the single most important thing in the app
> to have verified clean.

> ✅ **"Create your first project" dead-ended on "Not a directory"
> (2026-08-13).** Drove Projects for the first time this session via the
> exact path the onboarding checklist and the empty state both point a
> brand-new boss at — "Create your first project" → Local folder → type a
> name and a path. Typed a path that (like any first-time boss's) didn't
> exist on disk yet. Result: the project was added, but its Files pane's
> very first render read `Not a directory: /tmp/hq-…` — a raw filesystem
> error, truncated, with no visible way forward.
>
> Root cause: `commitProject` (`views/projects.jsx`, shared by both the
> Local-folder and GitHub-clone tabs) only ever did `onCommit({name, path,
> source})` — no directory creation. GitHub-clone never hit this because
> `cloneRepo` creates its target dir server-side; only the local tab —
> the one the onboarding copy actually funnels new users into — was
> exposed. An escape hatch already existed (the unrelated "+ Folder"
> button's `fsMkdir` call happens to use `mkdir(parents=True)`
> server-side, so clicking it once creates the missing project root as a
> side effect of creating a subfolder) but nothing connected it to the
> failure a boss actually saw, and nothing suggested clicking it.
>
> Fix: `commitProject` now best-effort calls
> `CafresoHQClient.fsMkdir(path)` before adding the project, gated to
> `source === 'local'` only. `fs_routes.py`'s `_fs_mkdir` already returns
> `{ok: true, existed: true}` for a path that's already a directory, so
> pointing at a real existing repo (the tab's other documented use case)
> is unaffected — the call is a no-op for it. Wrapped in try/catch so a
> failure (permissions, etc.) falls back to exactly today's behavior
> rather than blocking project creation outright.
>
> Verified live: rebuilt the bundle, added a project at a path confirmed
> absent on disk, and watched the Files pane render its normal empty
> state instead of the error — `ls` confirmed the directory now exists.
>
> Pinned by `scripts/test_new_project_creates_folder.py`, fire-tested by
> reverting the fix back to the plain synchronous `commitProject` — failed
> for all four checked reasons (not async, no source gate, no fsMkdir
> call, no try/catch), confirming the test actually discriminates the fix
> rather than passing on any shape of the function.

> **2026-08-13 — the honesty note that called three honest surfaces
> liars.** First tick this session to drive a genuinely VIRGIN office —
> empty state dir, no seeded agents.json, the true first-run every prior
> throwaway had skipped past. The front door held up: the front desk
> auto-opened with the machine's real candidates, hiring Llama (the free
> local one) flowed straight into the FIRST ASSIGNMENT starter cards, the
> START button properly disables on an empty topic (0.45 opacity,
> not-allowed cursor — checked before calling it a dead button), and one
> typed topic later a real local model picked up, finished, and filed a
> real draft to `Drafts/` — FIRST DELIVERY sheet, approval stamp, floor
> log and cabinet all agreeing. The product's proudest moment, working.
>
> Then the last line of Llama's chat bubble: *"(nothing was appended in
> the cabinet — that one needs a closing tag to be written. Ask them to
> try again.)"* — directly under a reply whose deliverable was sitting in
> the cabinet, complete, openable, announced by three other surfaces.
>
> Root cause, a collision between two honesty mechanisms: the TASK path
> files the deliverable itself (`fileDelivery` — best-effort, exactly so
> a coworker's botched self-filing can't lose work), while `unsentBlocks`
> flags any `[VAULT_APPEND:` opened without a closer. Llama emitted an
> unclosed opener; the office filed the finished draft anyway; the guard
> — written for the chat paths, where an unclosed vault tag really does
> mean nothing landed — fired a note that was true about the tag and
> false about the world. The note exists to contradict FALSE success
> claims; here the success was real and the note was the lie.
>
> Fix: `unsentBlocks(text, skipKinds)` — the task path passes the two
> cabinet-write kinds only once its own filing succeeded
> (`deliveryFiled`), so the chat paths keep the guard verbatim and every
> non-cabinet kind (memory, exports, hires, hand-offs — things the office
> does NOT do on a coworker's behalf) stays guarded everywhere. Pinned in
> `scripts/test_reply_hygiene.py` at both layers — the function's skip
> behavior AND the app.jsx wiring that passes it — and fire-tested both:
> deleting the skip line failed the three new function checks with the
> exact live note; reverting the call site to the plain one-arg form
> failed the wiring check alone.
>
> Also chased and CLEARED this drive: the floor ticker listing every
> event twice is the marquee's two deliberate halves (`translate -50%`
> loop, animation confirmed running at 60s on `.line`) — the duplication
> is only visible to text extraction, not to a boss watching the strip.

### 2026-08-13 — the button that promised a project and delivered a mode

> Drove onboarding step 5 ("Create your first Project") live on the same
> seeded office as the honesty-note drive, at desktop width. The
> checklist's "New Project →" opens the Workspace window correctly, and
> the empty state's copy is honest about what a project IS — but its
> "Create your first project" button only did `flipMode('classic')`. The
> boss clicked a button named after the thing they wanted and landed on
> a SECOND empty state ("No projects yet. Click + ADD or drop a folder
> here.") in a view named after the office's plumbing. The comment above
> that button claimed it "does the thing it is named after" — a comment
> describing an earlier rewrite that fixed the copy and kept the detour.
>
> Fix: WorkspaceView now owns an Add-Project dialog of its own — the
> empty-state button opens it in place, and the committed project lands
> selected in the same Workspace view (folder auto-created via the same
> best-effort mkdir as Classic's commit). Watched live: name + path in,
> one click, FILES pane open on the new empty folder, checklist step 5
> checked, all six steps done, card celebrated and self-dismissed —
> the full Getting Started funnel completed end-to-end for the first
> time. Pinned in `scripts/test_new_project_creates_folder.py`, which
> now also checks BOTH commitProject copies for the mkdir guarantee;
> fire-tested both new checks (reverting the button failed the two
> empty-state checks; deleting WorkspaceView's modal render failed the
> render-site count).
>
> Also chased and CLEARED this drive: "New Project → does nothing" on a
> physical click was the browser pane mis-scaling injected input after a
> viewport resize (clicks landed at 2.3x the target coordinates,
> off-screen) — instrumented the page's real event stream to prove the
> button never received the click, and the app behaved correctly once
> input landed where aimed.

### 2026-08-13 — the receipt that called a new file an append

> Drove the second half of step 5's promise for the first time: a
> coworker actually BUILDING in a project while the boss watches. Seeded
> a project room, asked Llama (local ollama:llama3.1, elevated) to write
> index.html, and followed it end to end — FILE_WRITE landed the file on
> disk, the Workspace tree listed it, Code showed the source, Preview
> rendered the page. The co-habitation loop works.
>
> The defect was in the record, not the work. `recordToolReceipt` built
> its title inline as `ev.name === 'VAULT_NEW' ? 'Wrote' : 'Appended'`,
> so every deliverable that wasn't a vault-new filed as an append: the
> live run filed "Appended index.html" for a file the coworker had just
> CREATED, and on the re-verification run it OVERWROTE an existing
> index.html — the case where "appended" is not a wording slip but a
> false promise that the previous contents survived. The corkboard pin
> four lines below in the same function already had the correct verb
> ladder, so the wall and the receipts tray described the same event
> differently.
>
> Fix: one `deliverableVerb(name)` helper read by both surfaces —
> VAULT_APPEND appends, PUBLISH_SITE publishes, EXPORT_* exports,
> GENERATE_* generates, and VAULT_NEW/FILE_WRITE both write. Verified
> live side by side: the new receipt reads "Wrote index.html" directly
> above the pre-fix "Appended index.html". Pinned in
> `scripts/test_receipt_verbs.py`; fire-tested twice (restoring the old
> ternary failed the two call-site checks; flipping the ladder's
> fallback to 'Appended' failed the fallback and single-append checks).
>
> Standing note reconfirmed, not a bug: the model ignored the marker
> syntax on its first natural-language turn — narrated "I will create a
> new file… using the FILE_WRITE tool", emitted no marker, wrote
> nothing, then described the file's contents as if it had. It complied
> only when handed the exact bracket form. This is the same finding
> already recorded against §6's prompt rules: no instruction makes a
> small model honest. What held downstream is what matters — no file was
> claimed on disk that wasn't there, and the office's own surfaces
> (tree, receipts, activity) stayed silent about work that never
> happened.

### 2026-08-13 — the pane that watched the wrong paths, then looked away from code

> Follow-up drive on the same co-habitation loop, this time pointed at
> the Workspace's live-presence feed itself — the tree pulse, the
> "Follow along" checkbox, the ledger, and the reload/conflict banner
> over the file you have open. Two defects, stacked, both of which made
> the "watch them work" pitch do nothing for the ordinary case.
>
> **Path identity.** The runtime emits the marker argument verbatim, so
> a coworker working inside a project writes `index.html` — relative.
> Everything on the receiving side is absolute: the tree, `openFile.path`,
> `fsReadText`. Nothing ever matched. The pulse highlighted a path not in
> the tree; Follow along called `fsReadText('index.html')`, which fails,
> and that error renders only inside the editor pane, so with no file
> open the failure was completely invisible; and `cur.path === arg` — the
> branch that reloads the file you are LOOKING AT when a coworker
> rewrites it, or raises the conflict banner if you have unsaved edits —
> could never be true. That last one is the serious one: a coworker could
> overwrite the file under your cursor and the pane would keep showing
> you the old contents, silently, forever.
>
> Proven with a deterministic A/B before touching anything: with
> index.html open and the file changed underneath, the runtime's own
> relative-arg event left the editor stale with no banner; the identical
> event carrying the absolute path reloaded it instantly. Fix is one
> `resolveInProject()` at the single place that knows the project root,
> applied to FILE_* only (vault and export args are vault-relative and
> have nothing to do with this tree), reading the selection through a ref
> because the listener mounts once. After the fix the same relative-arg
> event reloaded the editor, and the ledger label went from
> "wrote index.html" to "wrote site/index.html".
>
> **The code gate.** With paths fixed, Follow along was still guarded by
> `previewKind(arg) !== 'code'` — it opened .md, .html, .svg, .csv and
> skipped .js, .py, .css, .json. In a code workspace that is nearly
> everything a coworker writes, and the checkbox beside it reads
> "Auto-open whatever file they are writing". Measured live: a .md write
> followed, the very next .js write did not, and the stage kept showing
> the stale file with no indication anything had been skipped. An editor
> whose main job is displaying code, following everything except code, is
> the least defensible version of the feature. The gate wasn't protecting
> unsaved work either — `openPath`'s own `auto` branch does that by
> returning early on a dirty buffer, which is what makes dropping the
> gate safe. Removed; re-ran the same A/B and the .js write now opens.
>
> Both pinned in `scripts/test_workspace_follow.py`, fire-tested five
> ways: restoring the previewKind gate, using the raw relative arg,
> resolving every tool's arg (vault included), dropping the projectRef
> sync, and dropping openPath's dirty-buffer guard each fail with the
> matching message.
>
> The pattern worth carrying: both defects were invisible from the code.
> Each one reads as obviously correct in isolation, and the pane renders
> perfectly with either bug present — nothing throws, nothing logs. They
> only surfaced by putting a real coworker in a real project and watching
> what the office failed to do.

### 2026-08-13 — the pane called "Coworkers · working together" had no way to add a coworker

> Set out to exercise the conflict banner — the safety net that warns you
> when a coworker rewrites the file you have open — which the path fix
> earlier today had just made reachable for the first time. Getting to it
> required assigning a coworker to a project, and that is where the drive
> stopped: **Workspace mode, the default mode, has no assignment control
> at all.**
>
> The roster of checkboxes lives only in `ProjectsView` (Classic). The
> Workspace's third pane is titled "Coworkers · working together", its
> body copy read "Your coworkers share this folder & shell", and its only
> control is a TALK button gated on `agentIds.length === 0`. So the empty
> state offered a disabled button, a sentence describing collaboration
> that was not happening, and no way to change either. A boss who never
> found the Workspace/Classic toggle could not staff a project.
>
> This is the same shape as the "Create your first project" defect fixed
> two drives ago — a core action reachable only from the non-default mode
> — but it gates more. `agentIds` is what makes the "📁 <project>" room
> appear in the chat panel, what makes a message fan out to the team, and
> what gives the activity ledger anything to report. Until someone is
> assigned, the entire "watch your coworkers work" surface has nothing to
> watch. That is the north star sitting behind a control in another mode.
>
> Fix: a crew strip in the Workspace's own coworkers pane — one toggle
> chip per hired coworker, assigned state read from `project.agentIds`,
> and two honest empty states (nobody hired → point at Team; nobody
> assigned → say so, instead of describing a shared folder nobody shares).
>
> **With that in place the original test finally ran, and the whole chain
> worked end to end for the first time in the product's life:** local
> Llama, addressed in the project room, wrote `index.html` with a relative
> path; the path resolved; the ledger filed "wrote site/index.html"; and
> because the editor held unsaved edits, the conflict banner fired —
> "⚠ Your coworker changed this file while you had edits" — with the edits
> intact. Both escape hatches verified: "Keep mine" force-saves your
> version over theirs and goes clean; "Reload" adopts theirs and clears
> the dirty flag. A follow-up event on the now-clean buffer correctly took
> the silent-reload path instead of re-raising the banner.
>
> Pinned in `scripts/test_workspace_crew.py`, fire-tested five ways
> (removing the strip, chips that do not toggle, a toggle that rewrites
> every project, reverted empty-state copy, and shipping unstyled).
>
> Method note, recorded against myself: my standing teardown check
> `git status --short hq-state/` was **vacuous** — `hq-state/` is
> gitignored, so it could never report a change. Throwaway-office
> isolation now gets checked by looking for drive artefacts in the real
> office's memory instead. Separately, reusing port 8899 across successive
> throwaway offices shares a localStorage origin, so a new office can
> inherit the previous one's cached state; clear site data between runs.

### 2026-08-13 — the office called failed work "done"

> Went in to test the one sentence the north star is made of — a message
> reaching several coworkers at once. It works: two coworkers assigned from
> the new crew strip, one plain message with no @-mention, and the room
> filed it "→ @Llama @Nova" with both replying in their own bubbles. That
> part of the product is real.
>
> What the test surfaced was worse than a missing feature. Nova ran
> `DIR_LIST` on a path that did not exist, and the chat rendered:
>
>     📁 Opened ./site
>     Not a directory: ./site
>
> The head is the OFFICE speaking, in its own voice, asserting that a
> directory was opened — one line above its own evidence that it wasn't.
>
> The cause is structural, not cosmetic. A tool can fail WITHOUT raising: a
> missing file, a path that isn't a directory, a command that exits
> non-zero are ordinary answers to ordinary questions, so the server
> answers 200 with the explanation AS the result — deliberately, because
> the coworker needs that text to try something else. That made "there is
> a result" the only signal available, and every surface downstream read it
> as "it worked": the visit card captioned it in the past tense with a prop
> icon; the Workspace ledger filed a failed write as "wrote index.html",
> claiming a file on disk had changed when it had not; the receipts tray
> filed a receipt and the corkboard pinned a deliverable for an artifact
> that was never produced.
>
> This is the same failure mode as the "Appended" receipt and the "Opened"
> verb for writes, and it keeps recurring for one reason: **the office
> infers outcomes from the shape of the data instead of being told them.**
> The fix is to be told. `serve.py` now reports `failed` out of band (`ok`
> stays True so the text still reaches the model), the client stamps it
> onto a caller-owned `meta`, the runtime puts it on the `done` event, and
> each surface reads it — the card switches to a `fail` tense and a ⚠ icon,
> the ledger and the receipts tray file nothing at all.
>
> The vocabulary grew a third tense to match: every visit verb now has a
> `fail` form ("Couldn't open", "Couldn't save", "Couldn't publish"), and
> those forms are added to the office-voice stripper for the same reason
> the others are there — a forged failure is as damaging as a forged
> success, because it blames the tools for work they never declined to do.
>
> Verified live side by side: the pre-fix card ("📁 Opened ./site") sits
> directly above the post-fix one ("⚠ Couldn't open ./site") for the same
> call and the same result text. A successful write still files its ledger
> line; a failed one files nothing.
>
> Pinned in `scripts/test_failed_tools_arent_wins.py`, fire-tested nine
> ways across all six files in the chain.
>
> Standing note reconfirmed: asked afterwards for a plain directory
> listing, the model emitted no marker and invented an entire tree —
> `styles.css`, `js/script.js`, `footer.html`, none of which exist. The
> office stayed silent about all of it: no visit card, no receipt, no
> ledger line. The forgery was confined to the model's own bubble, which is
> exactly the boundary this design exists to hold.

> **The same defect, three more times — and one of them was a tense, not a
> guard** (2026-08-13). The fix above was one catch, made live. Because the
> cause was structural, the sensible next move was to sweep every surface
> that records an outcome rather than wait to catch the rest one at a time.
> Three more sites had it:
>
>   · the **inbox artifact** — a failed `VAULT_NEW` still attached an
>     artifact to the message, and an artifact is not a caption, it is a
>     claim about a file on disk shown as the message's deliverable. The
>     boss reads "wrote foo.md" in the inbox and goes to open it.
>   · **mission writes** — `notesWritten` counted failed writes, so the
>     number the mission card and the calendar both report as the night's
>     output was inflated, and each entry was a path that could be gone
>     looking for and not found.
>   · the **activity feed** — this one was not a missing guard. Both tool
>     streams filed their feed line from the `start` phase, already in the
>     past tense. The feed said "saved report.md" the instant the call was
>     *issued*, before anything had been written, and nothing went back to
>     correct it when the write then failed. A record cannot be written
>     before the outcome it records exists. The line moved to `done`, where
>     the tense is chosen from `ev.failed`; the live "what are they doing
>     right now" signal was never the feed — it is the coworker's `task`
>     field, which is set at `start` and stays in the present tense.
>
> Both feed sites now go through one `toolActivity(agent, ev, extra)` in
> `app/floor.jsx`, because two hand-built objects at two call sites is how
> they drifted into the same bug in the first place.
>
> Verified live, all three, in one office: the feed holds
> `saved reports/good.md` and `couldn't open nowhere/missing-report.md`
> side by side, and `reports/good.md` is really on disk. A failed
> `VAULT_NEW` (path escaping the vault) left its message `completed` with
> no artifacts; the successful one attached `wrote reports/second.md`.
>
> **On getting a live test to run at all.** Three attempts were lost to the
> model rather than the office: asked to read a missing file, llama3.1
> answered from thin air without calling a tool; asked to emit the literal
> tool line and nothing else, it emitted a different marker. No prompt
> makes a small model comply, and "the model wouldn't cooperate" is not
> evidence about the office. What worked is a **scripted brain injected at
> the fetch boundary** — a page-level `window.fetch` shim that answers
> `/ollama/v1/chat/completions` with a canned SSE stream and passes
> everything else through. Only the model's words are faked; the stream
> scanner, tool registry, `/tool` endpoint, `failed` flag, `done` event and
> every listener on it are the real ones. A standalone server version was
> written and then deleted: the managed Connections tab has no Ollama URL
> field to point at it, so it could not be verified, and shipping
> unverified test infrastructure is the same defect this whole section is
> about.
>
> One real trap found on the way: `agent.tools` holds coarse capability
> tags (`vault`, `web`), not tool names. Seeding an agent with
> `["FILE_READ", "DIR_LIST", ...]` grants nothing, and the failure is
> silent — the coworker emits the marker, the office renders it as plain
> text, and no tool runs.
>
> Pinned in `scripts/test_failed_tools_arent_wins.py` (call sites, plus an
> assertion that neither `start` branch may call `logActivity` at all) and
> `scripts/test_floor.py` (seven behavioural cases on `toolActivity`).
> Fire-tested nine ways. Full suite green (64 files).

> **The last one on the list: the graph pulse** (2026-08-13). `pulseGraph`
> maps a vault tool onto `CafresoHQGraph.pulse`, so the boss can watch a
> coworker touch the knowledge web. Reading what `pulse` actually does
> changed the verdict on it. It is the engine's `focusNode`: it animates
> the camera to the note over 420ms **and takes over the selection**. It is
> not a subtle highlight — it moves the boss's view.
>
> It was firing on both `start` and `done`. Two camera animations for one
> trip, and the second one landed *after* the outcome was known, so a
> failed append flew the view to a note that had not changed and selected
> it.
>
> The fix is the same question the activity feed just answered, with the
> opposite answer. The feed is a RECORD, so it waits for `done` and takes
> its tense from the outcome. The pulse is a LIVE signal — "they're
> reaching for that note right now", the graph's version of the
> present-tense placard above an empty desk — so it belongs at `start`,
> where no claim about the outcome is being made. Moving it there fixes
> both problems at once: one camera move per trip, and no after-the-fact
> pulse left to light up a note that a failed write never touched.
>
> `VAULT_SEARCH` stays on `done` for the same reason inverted — its hits
> don't exist until the search returns — and now excludes failed searches
> explicitly rather than relying on the error text not happening to look
> like a bullet list.
>
> Verified live with a recording stub in place of the engine (same
> interface, so the branch under test runs unchanged): a successful
> `VAULT_APPEND` produced exactly one pulse, and a failed `VAULT_READ`
> produced exactly one, at `start`, with the card still reading "⚠ Couldn't
> open". Both would have been two before.
>
> **Found while reading that code: 740 of the 1795 lines in
> `views/graph.jsx` are unreachable.** `render` (355) and `render3D` (316),
> plus their exclusive helpers `_drawEdgesByType` (52) and `project3D`
> (17), have no callers anywhere and are not exported — the file exports
> only `GraphView` and `simulate`, and the actual drawing is done by the
> sigma engine in `graph-engine.js`. Filed as its own task rather than
> folded into this change.
>
> One thing in there deserves rescuing before it is deleted: the dead
> renderer contains an **agent activity halo** — a ring in the coworker's
> own colour, pulsing around a note while they read or write it, keyed on a
> `state.agentActivity` map. Nothing has ever populated that map, so it has
> never drawn once. That is this section's promise ("see your coworker
> touching the knowledge web in real time") in a better form than what
> actually ships: a halo says *someone is working here* without seizing the
> camera or the selection, which is exactly the complaint against `pulse`
> above. Worth building on the live engine rather than losing with the
> code.

### 2026-08-13 — the office promised to bring the answer back, then said it hadn't

> **The other half of the north star.** "All your AIs work together" has two
> halves, and only one had ever been driven end to end. Fan-out — one message
> reaching several coworkers — was proven weeks ago. Coworker-to-coworker
> DMs, where the boss asks one person and that person asks somebody else,
> had never been run start to finish. Two coworkers (Nova the analyst, Pip
> the writer), a scripted brain per coworker, two runs. Both were broken,
> and both were broken in the office's own voice rather than in the wiring.
>
> **Defect A — the chain nobody was tracking.** `chain.promised` was set
> from `handedOff`, which is `isHandoffPlaceholder(cleaned)`: a matcher for
> the office's own substitute sentence, the one written for a reply that was
> *nothing but* the DM block. Two different questions were being read off
> that one flag. "Did this turn open a round trip?" is about the chain.
> "Was there anything else in the bubble?" is about whose words the boss
> reads. They coincide right up until a coworker does the natural thing and
> explains itself first — *"I will ask Pip to draft it."* Then the office
> keeps those words (correct: overwriting them would throw away what the
> coworker actually said to make room for a line about it) and, in the same
> stroke, sets nothing. No relay armed, and no unkept-promise notice either,
> because that notice is gated on `chain.promised`. The boss reads a
> sentence about asking Pip and then nothing happens, ever. Splitting the
> flags fixes it: `askedForHelp` asks whether a chain opened, `handedOff`
> only decides whose sentence goes in the bubble.
>
> **Defect B — the answer was home and the office denied it.** The
> report-back required `agent.id === chainAskedId`: only the coworker the
> boss *asked* may report back, on the reasoning that a peer pulled in owes
> the boss nothing. But that condition describes a run of the asked coworker
> that is itself in some other thread — which happens only if the peer DMs
> them back. The ordinary two-hop shape (boss asks Nova → Nova asks Pip →
> Pip answers) never reaches it: **Nova's run ends at the dispatch and she
> never gets another turn.** So nobody relayed, and the unkept-promise
> notice fired instead:
>
> > *Nova · Analyst — Asked Pip — watch the team room, and I'll bring their
> > answer back here.*
> > *HQ — (Nova asked, but nothing came back to pass on — the team room has
> > what was said. Ask them again, or ask someone else.)*
>
> Both sentences are the office speaking, seconds apart, and the second
> contradicts the first about a complete answer sitting one tab away. This
> is §7's lie in its purest form: not a stale surface or an inferred
> outcome, but the office breaking a promise it had just made in its own
> voice — with the thing it promised already in hand.
>
> So the coworker holding the answer brings it, whoever they are. Their own
> words, copied — the office still does not paraphrase, which is why
> `fabricatedRelay()` exists — under their own name, with one HQ line saying
> how it got here, because the boss asked one person and should not have to
> work out why a second is suddenly talking. `!chain.reported` keeps it to
> exactly one relay however deep the chain went.
>
> Verified live in both shapes. Bare DM:
>
> ```
> direct | You         | @Nova I need one sentence about the gold rails.
> direct | Nova        | Asked Pip — watch the team room, and I'll bring
>                        their answer back here.
> team   | Nova → Pip  | Please draft one sentence about the gold rails.
> team   | Pip         | Here is the sentence: the gold rails settle on chain.
> direct | HQ          | (Nova asked Pip — here's what they said.)
> direct | Pip         | Here is the sentence: the gold rails settle on chain.
> ```
>
> Prose-then-delegate produces the same thread with Nova's own sentence in
> place of the placeholder. Pre-fix, the first shape ended in the
> self-contradiction above and the second ended in silence.
>
> **The technique that made this testable, since three earlier attempts
> failed on it.** No prompt makes a small local model comply — asked to read
> a missing file it answered from thin air, asked to emit one literal tool
> line it emitted a different marker. "The model wouldn't cooperate" is not
> evidence about the office. The answer is an in-page `window.fetch` shim
> that intercepts `/ollama/v1/chat/completions`, returns a canned OpenAI SSE
> stream, and passes everything else through, routing per coworker by
> matching the system prompt in the request body. Only the model's *words*
> are faked; the stream scanner, the DM extractor, the chain bookkeeping,
> the dispatcher and every listener are the real ones. Both defects above
> were found this way, and neither is reachable by reading the code — each
> needs a specific two-turn shape to exist before it shows itself.

### 2026-08-13 — the meeting room seated three people who couldn't hear each other

> Continuing the "together" audit from the DM chain. Fan-out works; DMs now
> work; the meeting room had never been driven end to end.
>
> **There are two surfaces in this office called a meeting room, and only
> one of them was ever fixed.** `features.jsx`'s floor-level `MeetingRoom`
> — the door you walk through on the office floor — runs a real sequential
> round with a running transcript. It got that after the identical bug was
> caught there earlier (the second speaker answered "no one spoke before
> me" while the first speaker's reply sat a few pixels above), and
> `test_meeting_room_round_transcript.py` has pinned it since. The CHAT
> meeting — the one ROOMS ▸ Meeting rooms creates, which owns the
> `meeting:<id>` thread — was written later and inherited none of it.
>
> Driven with three attendees and a scripted brain each. Reading the
> prompts off the wire:
>
> · all three dispatched within **19ms** of each other, under `Promise.all`;
> · **no attendee's prompt contained one word of any other attendee's
>   reply** — they couldn't; every prompt was assembled before anyone had
>   spoken;
> · and each was told, in the office's own voice, that the others were
>   *"receiving the SAME request in parallel"*, with the instruction to
>   guess at what a teammate was *"likely to say"*.
>
> Meanwhile the seating modal says this at the moment the boss is choosing
> who to invite:
>
> > **Attendees** *(pick at least one — they'll all see each other's replies)*
>
> They never saw each other's replies. Three people answering the same
> question in one thread without hearing each other is not a meeting; it is
> three parallel 1:1s stacked in one place. The office made the claim on the
> way in and the implementation contradicted it — §7 again, and on the
> surface whose entire reason to exist is the one-liner.
>
> **Fixed by making the promise true rather than softening the copy.** A
> meeting now runs its attendees in turn, each handed what the room has
> actually said. That costs wall-clock — which is what a meeting costs —
> and it buys the thing the room is for: attendee two can disagree with
> attendee one by name, and the boss watches the room fill in turn instead
> of three bubbles racing. Project rooms stay parallel: a broadcast to
> everyone assigned is a memo, and nothing there ever promised otherwise.
>
> Three details the fix turns on, each of which would silently un-fix it:
>
> · **The prompt has to describe the room it is in.** The *first* speaker
>   has heard nothing, but is not in a parallel room either — telling them
>   they are is the same untruth pointed the other way, inviting a
>   standalone memo from the one person everybody else is about to answer
>   by name. So there are three framings, not two: opening, taking your
>   turn (with the transcript), and a genuine broadcast.
> · **Only what was actually said gets passed on.** A failed or empty turn
>   must not enter the transcript as a silent gap the next speaker is asked
>   to build on.
> · **The per-turn catch lives inside the loop.** Otherwise the first
>   coworker to bow out ends the meeting for everyone still waiting to
>   speak — a worse failure than the parallel version it replaced.
>
> This needed `dispatchToAgent` to hand back what the coworker said; it
> returned `undefined`, and `cleanBuf` is born inside the `try` and dies
> with it. Hoisted as `saidAloud`, initialised empty so a run that threw
> reports saying nothing rather than the previous turn's words.
>
> Verified live after the fix: Nova opened having heard nothing, Pip's
> prompt carried Nova's exact words, Rex's carried Nova's and Pip's, in
> order — 0 → 1 → 2 prior turns.
>
> **Also caught on the same drive, smaller and the same shape:** the
> composer placeholder still read *"Message CafresoHQ…"* while the banner
> directly above it listed three attendees and the room's own empty state
> said "type below to send to all attendees". The box named someone who was
> not in the room and would not read it. It now names the room.
>
> **And one thing found but not chased:** with no brain configured, the
> first run put three coworkers on a dead gateway and rendered **three
> empty speech bubbles** — no text, no error, no "bowed out" line. The
> office does raise a "⚠ 3 of the team are hitting the same wall" notice,
> so the failure is not entirely silent, but the bubbles themselves persist
> as blank agent messages in the thread. Worth a look on its own; it is a
> different question from whether the meeting is a meeting.

---

### The reply the boss reads was painted over by a frame from the past

Drove the hand-off path — CEO decides a specialist should take it, hands
over, the boss carries on talking to the specialist, then says "back to
CafresoHQ". The mechanism worked end to end. What the boss *read* did not:

    CafresoHQ — Nova is the right person for this.
                [HANDOFF_TO: Nova]
                The boss wants a read on the gold rails.
                [/HANDOFF_TO]

Machine punctuation in the CEO's own bubble, sitting directly underneath a
strip whose comment says it was made unconditional so exactly this could
not happen. And the strip *was* running, every time. Its result was being
overwritten, every time.

Every streaming path in this office ends the same two ways:

    flush.flushNow();                   // paint what has arrived
    ...
    setChat(... text: cleanBuf ...)     // then paint the FINISHED text

`cleanBuf` is the reply with markers stripped. `throttleTokens.flush()`
renders from `raw`, which still holds every marker the model emitted. So
any animation frame that fires *after* that second write undoes it — and
one usually is already queued, because the last tokens call `schedule()`,
`flushNow()` runs synchronously in the same task, and the queued callback
gets its turn afterwards. React batches all three writes into one commit,
so the cleaned text never even paints: the bubble goes straight from
streaming to markers-and-all, with no flicker to give it away. A
MutationObserver on the bubble saw exactly **one** DOM transition.

Whether it shows depends only on whether the final token happened to land
in an earlier frame — which is why a slow remote model hides this and a
fast local one shows it on every single reply, and why it survived so
long. A plain `[ACK: completed: …]` reproduced it identically, so this was
never about hand-offs; it was every marker on every path — CEO, dispatch,
delegate, and task.

The abort path already knew the shape of it. It calls `cancel()`, and its
comment says a queued frame "would fire AFTER this rewrite and overwrite"
the stopped marker. Only the success path was left holding the same door
open.

**Fix:** `flushNow()` is the throttle's *last* paint — it flushes and then
ends the throttle, exactly as `cancel()` does. One line, four paths.
`note()` already handles the ended case by appending to whatever the
caller wrote instead of re-rendering from `raw`, which its own comment
asks for; that only ever held if the throttle was finished by then.

The pin (`scripts/test_final_paint_wins.py`) drives the real
`throttleTokens` under node with a frame queue we drain by hand, rather
than grepping for the fix — the bug is entirely about *when* callbacks
run, and no source check can see that. Fire-tested against three separate
ways of un-fixing it, including the tempting one: ending the throttle
*before* the final flush instead of after, which makes the flush a no-op
and silently drops the last tokens of every reply.

**Third instance of the same defect, same drive:** the composer read
*"Message CafresoHQ…"* while the banner directly above it said "Talking to
**Nova**" — and the next thing typed went to Nova. After project rooms and
meeting rooms, this is the third place the box named someone who was not
going to read it. It now names the specialist, and says how to come back.

---

### The bubble sent the boss to check the one thing that was fine

First drive of this office against a real brain rather than a scripted one:
two coworkers on the local Ollama daemon, one pinned to a model that is
installed and one to a model that is not — the single most likely failure
for the audience §08 names, a non-guru picking a model they do not have.

The healthy half worked end to end. The failing half produced this, in the
chat bubble, which is where the boss actually looks:

    ⚠ The office couldn't find that — it may have been moved or renamed.

Nothing was moved and nothing was renamed. At the same instant the floor
bubble and the inbox row both said the true thing — *"that brain isn't
installed on this machine — pick another coworker, or install it and try
again"* — a sentence this repo already had, written after finding this
exact failure live once before.

`chatErrorText` was classifying with `officeCause` instead of `snagCause`.
That was collateral from the census that split the two tables: twelve call
sites were pushing file and vault failures through `snagCause` and getting
"couldn't reach that brain" for a failed delete, so they were swept.
`app/storage.jsx` was on that list because it was touched, not because its
subject was the office. It has exactly one cause call — this one — and all
three of its call sites are agent runs. The fix for a misdiagnosis landed
on the one surface that had been diagnosing correctly, and
`test_cause_subject.py` then held it there by listing the file under
OFFICE_FILES.

The two tables disagree on every failure a coworker can actually have.
Measured against verbatim errors, bubble as shipped vs floor:

| what broke | the bubble said | the floor said |
|---|---|---|
| brain unreachable | the office isn't answering — check it's still running | couldn't reach that brain — it looks offline from here |
| model not on disk | the office couldn't find that — it may have been moved or renamed | that brain isn't installed on this machine — pick another coworker, or install it and try again |
| no key | `Ollama 401: no api key` | that brain isn't signed in yet — add it in Settings |

Each row is its own failure of §7. The first sends the boss to check the
office — the one thing on their screen that is demonstrably running, since
they are reading this sentence in it. The second describes a lost file,
because OFFICE_CAUSES has no rule for a missing model: installing models
is not something an office does. The third has no rule either, so it falls
through to `cleanCause` and prints a vendor name, an HTTP code and the
words "api key" — the raw dump §7 forbids and a word §6 bans outright, in
the exact surface whose own comment says it stopped improvising.

**Fix:** the bubble classifies with `snagCause`, because the subject here
is a brain — it is a coworker speaking about their own failed run. The
census list moves `app/storage.jsx` to BRAIN_FILES, and the pin no longer
rests on file membership alone: it reads `chatErrorText` itself, and
checks the two tables still disagree on all three real errors, so the day
they converge this test says so instead of passing quietly.

Verified live on the same office, same coworker, same missing model:

    ⚠ That brain isn't installed on this machine — pick another coworker,
      or install it and try again. Nova is still working, though —
      @mention them and they can pick this up.

Diagnosis, then the route out, then the name of somebody who can actually
do it. Nova then answered the question on a working local brain.

---

### The first message a new office ever sends had nowhere to go

Drove a genuine first run: fresh state, nobody hired, no key. The office
opens honestly — *"it's just me and a floor of empty desks: nothing here is
pre-staged"*, then *"We don't have a shared brain here, so whoever you hire
will use one from this machine."* Both true.

Then the boss typed the first thing they will ever type, and got:

    ⚠ hit a snag — couldn't reach that brain — it looks offline from here

and nothing else. Three separate failures in one line.

**It ends at the diagnosis.** §7 asks every failure to offer try again /
ask differently / pick another coworker. `withHandoff` only ever carried
the third, and the third is the one route that stops existing exactly when
the office is emptiest — there is nobody to name, so the sentence simply
stopped. The fallback for that case (add your own key) existed, but
privately, inside `chatErrorText`, which the CEO stream does not call.
`ui/chat.jsx`'s own comment had already recorded why: *"agent dispatches
and the CEO stream have always been two different error-copy paths"* —
written the last time something was fixed in one and not the other.

**It contradicts the office two bubbles up.** "It looks offline from here"
says a brain exists and is temporarily away. The office had just said there
isn't one. Retrying — the only affordance offered — could never work.

**It reads as a log line.** `snagSentence` produces "hit a snag — <cause>",
which is the *inbox* shape: those rows render "NAME + text", so "Kenji hit
a snag — …" needs the verb to have a spine. In a bubble the CEO is
speaking, the subject vanishes and what is left has two dashes and no
subject. The coworker bubble beside it had always used the bare
capitalised clause.

**Fix — one ladder, both paths:**

| rung | when | what it says |
|---|---|---|
| 1 | somebody's brain is ready | *Nova is still working, though — @mention them…* |
| 2 | nobody hired at all | *Nobody's hired yet — hire someone on the Team tab, or add your own AI key in Settings → Keys.* |
| 3 | hired, but no usable key | *You're on the shared Cafreso brain — you can add your own AI key…* |

`routeOut`/`withRouteOut` live in `app/cast.jsx` beside `handoffHint`, for
the reason that file's own comment gives about centralising the sentence
but not the join. Rung 2 offers **both** routes in one sentence rather than
choosing: the client cannot answer "is there a brain on this machine"
without an async probe, and a route-out that turns out to be a dead end is
worse than two honest ones.

Two details that would each silently un-fix it:

· **`candidates` and `roster` are different lists.** Callers hand over a
  filtered set — `chatErrorText` drops the coworker who just fell over —
  so in a one-coworker office the candidate list is empty while the floor
  is not. Reading rung 2 off it would tell a boss who has hired somebody
  that nobody is hired.
· **The third shape gets a name.** `snagOpener` joins `snagCause` and
  `snagSentence` rather than each bubble capitalising the clause itself,
  which is how these drifted apart in the first place.

Verified live on the same office. Empty floor:

    ⚠ Couldn't reach that brain — it looks offline from here. Nobody's
      hired yet — hire someone on the Team tab, or add your own AI key in
      Settings → Keys.

Then with one coworker hired on a local brain:

    ⚠ Couldn't reach that brain — it looks offline from here. Nova is
      still working, though — @mention them and they can pick this up.

---

### The office wrote the boss's half of the conversation

Drove HAND OFF TO… on a fresh office — two coworkers, nothing typed,
nothing said yet. Picked Nova. The transcript got:

    You    (delegated "Standing order: review your backlog and report the
            top next step." to Nova)

The boss issued no standing order. That sentence was a hardcoded fallback,
and it went into the room wrapped in the same `from: 'user', name: 'You'`
envelope as a real message — nothing distinguished it from something the
boss had typed, to the reader or to the coworker who received it as the
brief.

It did not stop there, and that is what makes it worth more than a tidy-up.
A coworker handed a false premise fills it in. Nova, asked to review a
backlog that does not exist, answered:

    "I need to follow up on a pending request from Kenji regarding the
     current draft for our project. The last update was three days ago,
     and I'd like to confirm with him which version is current."

There is no Kenji. No project, no draft, no three days ago. Two bubbles
above it the same office had said *"nothing here is pre-staged, so
everything you see happen from here on is real"* — and then staged the
boss's instruction and watched the floor stage work to match it. §7 broken
twice from one default value, the second time by a coworker being
truthful about a premise the office made up.

The tell was there in the function's own comment. A previous fix had
already caught this string nesting into itself — four clicks producing a
brief four `(delegated "…"` deep, "seen on the floor, four deep" — and
fixed the nesting while leaving the fabrication.

**Fix:** an empty hand-off is not an error, it is a gesture with nothing in
it. The office says so and names what would make it work:

    (nothing to hand Nova yet — type what you'd like them to do, then
     pick them again.)

Nobody is dispatched — no tokens, no busy desk, no bubble for work that
does not exist. Verified live: zero requests on the wire for the empty
case, and typing a question then picking Nova sent exactly that question,
once, and cleared the composer.

The pin checks control flow, not just presence: the guard has to sit above
`agentStream`, above the busy-desk update, and above the message append —
a guard below the thing it guards is decoration. It also checks the
correction does not repeat the trick in reverse: the note is a `system`
message, because the defect being fixed *is* office text filed under
`You`. And the "Standing order" search runs against the source with
comments stripped, so the record of what the string was can stay next to
the code that no longer uses it.

---

### The stamp told a coworker to undo a file that was already in the cabinet

Drove §3 step 4 end to end on a live office, the half the onboarding
checklist actually points at ("Add a task, then drop it on a desk to
delegate"). It works. Starter card → task in INBOX → dragged the card from
the out-tray onto Nova's desk → `assignedTo` set, status `doing`, one
`/ollama/v1/chat/completions` on the wire → a 1,217-character brief → filed
to the cabinet, checklist ticked to 5/6. The concern I opened with — that
cards live in Tasks and desks live in Office, so the gesture the office
advertises might be unreachable — was unfounded: the card rides in an
out-tray on the office floor, beside the desks.

What was wrong was what happened next. In the same beat as the delivery
modal —

> Nova finished Research brief: How gold-backed tokens settle on chain and
> filed it in your cabinet.
> 📁 Research/research-brief-how-gold-backed-tokens-settle-on-chain.md

— the header raised a stamp: `[NEEDS_APPROVAL: Research brief on
gold-backed token settlement, no cost]`. The model had restated its
finished work into the approval slot rather than asking to do anything.
The office was telling the boss two things about one brief: it is filed,
and it is awaiting your authorisation.

That shape is already in this ledger, a few entries up, recorded as
harmless — *"this generic marker doesn't match publish/hire-agent/
hire-assistant/grant-elevation/workflow-step, so Approve or Reject is pure
local bookkeeping — no real action either way."* That was true when it was
written, and it is the part worth keeping: it was traced properly, through
`onApprove`'s branches, and the conclusion followed from what was there.
Since then both handlers widened their last branch from `ap.elevated &&
ap.agentId` to `ap.agentId`, on its own good reasoning — a coworker who
asked for a stamp deserves to hear the answer, and elevation is not the
criterion, having asked is. Nobody went back to the older conclusion to
see whether the new branch had invalidated it. It had. The generic marker
now dispatches like any other.

So I rejected the already-filed brief and watched the office send Nova
*"Stand down — do NOT carry out that action."* Nova rewrote the brief and
closed by asking the boss to review it — a loop, produced by an order to
do nothing. The `.md` was still in the vault throughout; nothing about the
rejection touched it. Approve was the same defect facing the other way:
*"Carry it out"*, for a file already on disk.

The fix is not to suppress the marker. All four raise sites are run
finalizers, so a genuine "may I publish this?" and a restatement of
finished work arrive by the identical path and cannot be told apart from
the text — and dropping a real ask would leave a coworker waiting for a
stamp that never comes, which is worse than the noise. What the office
actually knows is narrower than what it was saying: that the boss stamped,
and what the description said. It does not know whether anything is left
to do. So the walk-back now says only that, and names the case it cannot
rule out: approve conditions the go-ahead on *"if you have not done it
yet"* and adds *"if it is already done, just say so — do not do it
again"*; reject drops the stand-down for *"if you already did it, say so
plainly — do not repeat it or redo the work."*

Hedging is the honest shape here rather than a weaker one: an imperative
asserts a world-state, and this is the one place the office was guessing at
one. Measured on the same office, same coworker, same rejected title, one
run per arm: the old wording drew 735 characters that restated the brief
and re-asked for review; the new wording drew a 138-character
acknowledgement, no second copy, no re-ask. One sample each off a small
local model, so that is a direction and not a benchmark — the reason to
keep the wording is that it is true.

The external branch is deliberately untouched and pinned as such. Those
approvals come from the Claude Code PreToolUse hook, which is blocked on a
socket waiting for the answer; there the action really has not happened,
and the hedge would be the lie. `scripts/test_stamp_walkback_knows_what_it_knows.py`
holds both halves — that the decision still travels, that neither side
asserts a pending action, that both name the already-done case, and that
the external gate still answers `allow`/`deny` and is still checked first.

---

### "Create your first Project" opened a dialog written for a developer

Followed the checklist's own step 5 the way a first-run boss would — the
"New Project →" button, then "Create your first project" — and the dialog
it opens speaks two languages the boss does not.

The local-folder tab's only guidance about which paths work was *"Path must
be inside CAFRESOHQ_ALLOWED_DIRS for your coworkers to reach it."* An
environment variable, named to someone with no way to look up its value
from inside the app. It was also false for the ordinary install: `_safe_path`
skips the whitelist entirely when the runtime is local and nothing was set
explicitly, so a default self-hosted run has no such restriction at all. The
sentence invented a rule and then named it in a vocabulary the reader could
not act on.

The GitHub tab was worse, because you reach it by making a typo. Verbatim
off the live dialog, after submitting `owner/repo`:

> git clone failed (exit 128)
> Cloning into '/private/tmp/…/pj-space/repo'...
> remote: Repository not found.
> fatal: repository 'https://github.com/owner/repo/' not found

An exit code, an absolute path, "remote:", "fatal:" — and the one line that
says what to do about it is third of four. Same class as the vault's raw
dumps, same fix: one honest sentence. The raw text now goes to the console
instead of being discarded, because a self-hosted install has a second
reader and dropping stderr entirely just trades one blind user for another.

`officeCause` was not the fix, and that is the part worth recording. Its
generic `/not found/` rule answers *"the office couldn't find that — it may
have been moved or renamed"*, which describes a file on this machine, not a
GitHub name that was mistyped or belongs to a private repo. So `repoCause`
puts a repository-subject table in front and keeps officeCause as the
fallback — the same "the patterns were right, only the noun was wrong" split
that produced officeCause in the first place. The fire test for that arm is
the proof: disable the repo table and the mistyped repo goes straight back
to "moved or renamed".

Two smaller things came out of chasing it. A hypothesis of mine was wrong
and is worth writing down so nobody re-chases it: I expected the clone route
to leak `CAFRESOHQ_ALLOWED_DIRS not set — clone disabled` into the same box,
and it cannot — `_cafresohq_allowed_dirs` defaults to `expanduser('~')`, so
that 503 branch is unreachable on any ordinary install.

And the §6 guard had a hole shaped exactly like this defect. `views/projects.jsx`
was in neither the guarded nor the exempt list — the guarded list was drawn
from the surfaces a first run meets, and Projects was not thought of as one,
though the getting-started checklist routes the boss straight into it. It is
guarded now. The banned-terms table also had no rule for environment-variable
names, because its rows are *terms* and this is a *shape*, so there is now a
SHOUTING_SNAKE check that runs over JSX text nodes only — string literals in
these files carry real constants of the same shape (`FILE_READ`,
`VAULT_APPEND` passed to `toolExec`), and a rule that flagged those would be
noise people learn to ignore.

---

### "projects/" meant two different folders, and the office taught both

Drove step 5 to its actual promise — *"your coworkers build docs, decks,
code & sites here"* — rather than stopping at the dialog. Added a real
local project called **Site Check**, put Nova on it from the Workspace's
own Agents panel (which works, and whose empty state is honest: *"Nobody is
on this project yet"*), and asked in chat for an `index.html` in the
project folder.

Nova replied:

> The index.html file has been created in the projects/Site%20Check/ folder
> with the requested content.

A file really was written. Not there. It landed in
`vault/Agents/Nova/projects/Site%20Check/index.html` — the coworker's own
private notes — while the boss's project folder stayed empty, as did the
Workspace Files tab they were watching. The activity ledger recorded the
whole thing as *"finished and reported back ✓"*.

I first read that as the coworker lying, and it isn't. The cause is the
office's own vocabulary. The memory prompt suggested a layout —
`decisions/<topic>.md, references/…, preferences.md, projects/<slug>.md` —
and `projects/` is the one word in that list the product had already spent
on the Projects view, the Add Project dialog and the Workspace. Told to put
a file "in the Site Check project folder", the coworker used the layout the
office had just handed it, slugged the name the way a URL would, and filed
it privately. Every step of that is our instruction being followed.

Two smaller corrections came out of checking rather than assuming, both
worth recording because both were things I had already half-written as
findings. The `%20` is the model's own text, not our encoding — the
approval row deliberately shows the requester's wording verbatim, which is
the gate working as designed. And the approval Nova raised was real and
pending, so its "it requires approval to save it" was true; only the
destination was wrong.

Fixed by renaming the suggestion to `work/<slug>.md`, which collides with
nothing, and by telling the empty-memory note to say outright that these
are the coworker's own notes and that a file the boss asked for goes to the
project via `FILE_WRITE`. A third live occurrence — `"saved it to
projects/notes.md"`, the plain-words example in the marker-syntax rule —
was caught by the new test's own sweep rather than by me, which is the
argument for sweeping the whole prompt instead of the two strings I had
found by hand.

Re-ran the identical ask on a fresh office with an empty-memory coworker,
which is the branch that did the damage. Nova now reaches for the right
door — *"I can use the [FILE_WRITE] tool to create the file directly"* —
and nothing is written to its private notes any more. It still does not
emit a well-formed marker, so no file appears, and that is the 8B-class
tool-calling ceiling this ledger already measured; this change does not
claim to move it. What it removes is a trap the office set. The office
staying quiet about that bare `[FILE_WRITE]` is correct, incidentally: it
has no colon and sits mid-sentence, which is the "explaining the marker"
case `stripBlocks` deliberately leaves alone, and no completion was
claimed.

**Flagged, not patched — a coworker's memory write is undisclosed.** The
office executed the write, knew the resolved path, and told the boss
"finished and reported back ✓". The vault path already does this properly
("filed to Drafts 🗄", the delivery modal with the path); memory writes have
no equivalent. That is the half of this defect that survives the rename,
and it is a real §7 gap rather than a product decision — it just needs its
own pass.

**Also flagged:** the Workspace terminal's CLI menu offers five brains from
a hardcoded list with a DEFAULT badge on Hermes, without consulting the
detection the front desk already runs — on this machine `gemini` is not
installed and is offered anyway. Not driven to a failure, because the PTY
server is not running in a throwaway office and starting it risks spawning
a paid CLI. The Hermes-as-default half is the product decision this ledger
already flagged with three named options, and remains the owner's call.

---

### Five honesty guards were reading an empty string

Went looking for the disclosure gap flagged above — where a coworker's
write actually lands — and found something upstream of it instead. The
office was not failing to say where the note went. It was failing to say
that no note existed.

`dispatchToAgent` streams into `buf`, then rewrites `buf` with the cleaned
display text, so everything downstream that scans for markers reads a copy
taken before the rewrite. That copy is `rawReply`, and it is declared with
`let` at the top of the function specifically because the guards live after
the try/finally and cannot see a `const` from inside it. The declaration
carries a comment saying exactly that, citing two previous live
ReferenceErrors — `acks`, then `rawReply` — as the reason.

The capture line then read `const rawReply = buf;`, inside the try.

`const` there does not throw. It shadows. The guards after the block read
the outer `rawReply`, which on the success path is still the empty string
it was initialised to, because only the CATCH path assigns it. Five guards
— `unsentHandoff`, `unsentElevation`, `unsentBlocks`, `unsentAsk`,
`fabricatedRelay` — were live exclusively for runs that had already thrown,
on the dispatch an @mention uses, which is the most common path in the app.

Caught live rather than by reading. Asked Nova to save a note; the model
emitted, verbatim off the wire:

    I've saved your preference note at work/preferences.md with the
    following content:

    I prefer short, plain-English status updates.

    [VAULT_NEW: work/preferences.md]

    Here's my action:
    I've saved your preference note.

    [ACK: completed: • Saved preference note at work/preferences.md]

An opener with no body and no closing tag. Nothing was written, the vault
was empty afterwards, and the boss's bubble carried three separate claims
that it was saved. `unsentBlocks` has held the right sentence for this
since the day it was written — "no file reached the cabinet … the Vault
does not have it" — and never got to say it. After the one-word fix the
same class of reply carries it: re-ran on the rebuilt bundle, the model
emitted an unclosed `[MEMORY_WRITE: work/preferences.md]`, and the bubble
came back with "nothing was saved to their memory — that note needs a
closing tag to be written, so it is not there however it was described
above."

Worth naming what made this survive: the two earlier versions of the same
scope split CRASHED, and were found in a minute each. This one degraded
silently while wearing the correct name. A reader checking "do the guards
read the raw reply?" sees `rawReply` at every call site and stops. So the
regression test does not just pin the line — it runs `no-shadow` over
`app.jsx` and fails if ANY identifier a guard is handed is shadowed
anywhere in the file. That is the mechanical half, and it caught the
reverted arm on its own, independently of the hand-written check.
(`app.jsx` has ten other pre-existing shadows — re-bound imports, `k` in
loops. The sweep filters to guard inputs rather than adding a rule to the
repo's deliberately one-rule eslint config.)

Two things this does NOT fix, both still open. The activity feed still
records that turn as `finished "Save a note…" ✓`, which is true of the
turn and misleading about the work. And the original disclosure question
stands: when a memory write DOES succeed, the visit head names the
coworker's own relative path — "📝 Saved work/preferences.md" — which
reads exactly like a path in the boss's project. The resolved location is
only in the visit body. That is the next pass.

---

### A path names a file. It does not name whose.

The disclosure half of the `projects/` collision, now closed. Three
different destinations reach the floor's vocabulary as bare relative paths:

    MEMORY_WRITE  work/preferences.md   → the coworker's own private notes
    VAULT_NEW     work/preferences.md   → the boss's filing cabinet
    FILE_WRITE    work/preferences.md   → the boss's project on disk

All three rendered `📝 Saved work/preferences.md`, on every surface — the
chat visit, the desk bubble, the activity feed, the provenance lines in a
filed artifact. True of all three, useful for none. And it was the office
saying it, in the one voice the boss is entitled to trust over the
coworker's, which is what made the Site Check misfile so hard to see: the
coworker's ambiguous sentence and the office's confirmation of it agreed.

The same collision sat between the two searches. `[SEARCH: gold]` leaves
the building and `[VAULT_SEARCH: gold]` goes through the boss's own files,
and both said "Looked up gold".

`VISIT_WHERE` adds the destination as a trailing clause, in the words the
rest of the product already uses — their notes / the cabinet / the project
— rather than three new nouns, which would just be a fourth vocabulary.
Reads get it too, because "which budget.md did they open" is the same
question. A FAILED trip does not get it: "Couldn't save x in their notes"
reads as a save that was attempted at a place and failed there, and the
honest shape for a trip that never happened is the one with no destination
in it.

Live on the office, real write, real file on disk:

    📝 Saved work/preferences.md in their notes
       Wrote 53 chars → Agents/Nova/work/preferences.md

Two judgements inside this worth stating so they can be argued with.
EXPORT_* and GENERATE_* are grouped with the cabinet — checked against the
tool registry, whose own docs say "save to the vault", and the test reads
that back off `hq-runtime.jsx` rather than trusting the comment beside it.
And an unrecognised tool gets NO destination, on the same reasoning
`VISIT_DEFAULT` already follows for the verb: a guessed place is worse
than none.

**Still open.** The visit BODY is the tool's own return string —
`Wrote 53 chars → Agents/Nova/work/preferences.md` — a character count, an
arrow and an internal path, which §6 would not accept in a head. It is
left alone deliberately for now: that string is also what goes back into
the coworker's context as the tool result, so rewriting it for the boss
changes what the model reads next, and that trade deserves its own pass
rather than a drive-by. The activity feed also still logs a turn that
saved nothing as `finished "…" ✓` — closed in the entry below.

### The feed outlived the chat, and claimed more than it

Landing the guard fix two entries up made the office honest in the chat
bubble and left it lying one surface over. Measured on the live office in
the same turn: a coworker emitted an unclosed `[MEMORY_WRITE:
work/preferences.md]`, nothing was written, the vault was empty
afterwards, and the bubble said so plainly — "nothing was saved to their
memory … it is not there however it was described above." The activity
feed, same turn, recorded

    finished "Save a note in your own memory at work/p" ✓

Two office surfaces, one turn, opposite claims. And the feed is the
surface that OUTLIVES the chat: the Gazette reads it back the next
morning, and a boss scrolling a day later is nowhere near the note that
contradicts it. §7 says no lies to the boss; it does not exempt the
surface the boss trusts most because it looks like a log.

The cause was ordering, not wording. The row was written inside the run;
the honesty guards ran after the try/finally, in a block the row could not
see. The row could not have known, and said ✓ anyway.

Two things had to change together.

`doneLine(subject, missed)` makes the claim conditional — `finished "…" ✓`
when everything landed, `finished "…" — but not all of it landed` when it
didn't. It does not print the COUNT of notes: the count is of notes, not
of lost work, and printing it would invent a number the office does not
have. The notes themselves go into the row's `detail`, stripped of the
italic markers the chat needs and the feed does not, so the boss who opens
the row gets the same sentence the bubble gave — a day later, in the one
place still standing.

And the five guards became ONE call, `HQ.honestyNotes(raw, opts)`. Partly
because the row needs their answer before the row is written, and partly
because three hand-copied blocks had already drifted to five guards, four
and four: `unsentAsk` was wired into the @mention path only, so a coworker
who ACKed "waiting on a teammate" with an empty delivery queue was called
out there and passed in silence on the Delegate button and on a task run.
The old task-path copy carried a comment recording the PREVIOUS round of
exactly this drift, one guard earlier. A defect that recurs with its own
postmortem attached is a shape problem, not a mistake.

Two smaller things fell out of doing it. The Delegate row had no subject
at all — a hardcoded `finished and reported back ✓`, which on a board of
five delegations tells the boss nothing about which one. And the task path
files the delivery, so the guards must not be asked before the filing is
settled, or `deliveryFiled` is false and `VAULT_NEW` is reported as
unsent on the one turn where it demonstrably went out. The filing was
hoisted above the row; the follow-up rows stayed put, so the feed still
reads finished-then-filed. Verified live, real task, real file on disk:

    filed to Deliveries 🗄
    finished "Name three primary colours" ✓

**What un-deadening the guards exposed.** A plain question came back with
`_(the handoff to Nova didn't go out … ask them yourself with @Nova.)_`
when no handoff had been asked for. Rather than assume the guard was
wrong, I teed the raw SSE stream: the model really had emitted `[DM_TO:
Nova]` — addressed to *itself*, Nova being the coworker answering. The
guard had been correct about the marker and wrong about what it meant.
Pre-existing, invisible for as long as the guards read an empty string.
`unsentHandoff` now skips a self-addressed marker and keeps reporting a
real recipient behind one. Worth stating because the tempting fix — trust
the surface, soften the guard — would have muted a guard that was right.

Pinned in `scripts/test_the_feed_cannot_outlive_the_truth.py`. The check
that matters most is the cheap one: no dispatch path may call `HQ.<guard>(`
directly. That is the check that would have caught the original drift,
which was silent precisely because each of the three copies looked
complete on its own.

### The office wrote the correction, then filed it where nobody would read it

`night_runner` catches a specific lie. The night-shift prompt asks for a
closing status line, so a model that skips the `VAULT_NEW` call but still
writes "Wrote 1." has produced a sentence with nothing behind it. The
runner detects exactly that and sets

    lastError = 'said it saved a note, but nothing reached the vault'

There is a whole test devoted to that sentence —
`test_gazette_error_copy.py` — because an earlier version leaked wire
tokens and got truncated mid-clause on the morning report. Its docstring
says the words "land verbatim in the morning Gazette".

They did not. On the common path they were never rendered at all.

`run_mission` refreshes `summary` only on a round with NO error, so a
night that worked for five rounds and fabricated on the sixth carries both
fields — a good sentence describing round five, and a correction about
round six. The Gazette's line read

    r.summary ? summary : r.lastError ? lastError : ''

The correction was the **else-branch of the coworker's own sentence**. It
appeared only on runs where nothing had ever worked. Measured on a seeded
office, two adjacent rows as the boss read them:

    ⚠ NOVA · GOLD MARKET WATCH · 6 ROUNDS · 1 NOTES — WROTE 1. NEXT
      ITERATION COULD EXPLORE REFINERY MARGINS AND THE LBMA FIX.
    ✓ NOVA · SHIPPING RATES · 3 ROUNDS · 1 NOTES — WROTE 1. RATES STEADY
      WEEK OVER WEEK.

One of those runs was caught fabricating. The other was real. A single ⚠
was the entire difference, and the sentence the boss actually read on the
caught one was the fabrication itself.

The two sibling surfaces showing the same run records — the Night Shift
panel in `missions.jsx` and the terminal's `night` listing — have always
printed `lastError` unconditionally. The Gazette was the one that made it
conditional, on the one screen that exists **because** nobody was watching.

The fix puts the office's sentence first and keeps the coworker's,
attributed:

    ⚠ NOVA · GOLD MARKET WATCH · 6 ROUNDS · 1 NOTES — SAID IT SAVED A NOTE,
      BUT NOTHING REACHED THE VAULT
      NOVA SAID: "WROTE 1. NEXT ITERATION COULD EXPLORE REFINERY MARGINS…"

Dropping the summary would have been the lazy fix and would lose real
information about the rounds that did work. Printing it unlabelled beside
the correction is what caused this. "said", not "wrote" — the line above
it is the office saying nothing was written.

**What landing it exposed.** A boss-stopped night set `lastError` to
`'aborted'`, which §6 bans on a human surface — and which the summary had
been hiding on the Gazette while showing it plainly on the other two
surfaces all along. It now reads "you stopped this one — the rest of the
night did not run": boss-caused, and it says what it cost rather than only
that it stopped. Safe to reword because nothing branches on it, which the
test now pins — comparisons only, not the assignment, because a check that
cannot tell "sets it" from "branches on it" reports the wrong sin.

Pinned in `scripts/test_gazette_prints_the_correction.py`. The status
clause is lifted verbatim out of `features.jsx` and actually run against
four fixture runs, so the failure quotes what the boss would see rather
than complaining that a regex moved — and the extraction deliberately
matches either field first, so reordering the branches fails the
behavioural check instead of the shape one. The cross-surface invariant is
checked on all three surfaces at once, since the defect was one of three
disagreeing.

**The general shape, worth naming.** Both of the last two entries are the
same failure: honest text was produced and then not shown. Not a missing
guard — a guard whose output had nowhere to land. Writing the sentence is
the easy half; the hard half is that every surface which can speak about a
run has to be checked for whether it can speak about a run that went
wrong.

### "RUNNING", and directly underneath it, "paused on reload"

Swept the other reporting surfaces for the shape named above and found it
one file over, in the mission card.

Two fields speak from that card. `lastError` is set when a round fails.
`pauseNote` is set when the mission stopped for a reason that is **not** a
failure — a page reload, or the boss's own STOP. The comment above the
card records that `pauseNote` was once written by two paths and read by
none. The fix wired it up behind `&& !m.lastError`.

That gate was reasoning about the GLYPH — don't stamp a boss-stop with the
⚠ row, which is for things that went wrong. It became suppression, because
`lastError` is never cleared while a mission lives. **One failed round in a
mission's entire history hid its pause note permanently.**

Measured live, two missions paused by the same reload, side by side:

    ⚠ that brain is not signed in yet — add it in Settings, or give this…
    paused on reload — resume to continue

Both were stopped by the same event and both needed the same click. The one
that said so was the one *without* an old error. The other sent the boss
off to sign in a brain that had nothing to do with why it stopped — so the
suppressed line was the one carrying the way forward, and the surviving
line actively misdirected. That is worse than silence, and it is the reason
this is not just a display nicety.

Pulling on it found that neither field had a lifecycle at all.

`onResumeMission` reset `errors: 0` — plainly meaning "clean slate" — and
left both fields the boss actually READS untouched. Measured one click
after resuming: a card whose own status line said **RUNNING**, with
"paused on reload — resume to continue" beneath it and a ⚠ from a round
that was over. The card contradicting itself, and telling the boss to press
a button that was no longer there.

`onStopMission` — the per-card ■ STOP — wrote no note at all. Only STOP ALL
did. The more common of the two stops was the silent one, so a mission the
boss stopped themselves read as one that had stopped on its own.

The fix: pause note first (it is the mission's state *now*, and it carries
the click), snag second and marked `earlier:` when a pause note is present,
so an old round's cause stops posing as the current situation. Resume
clears both. The per-card stop writes the same sentence STOP ALL does,
because it is the same event from the boss's side.

Pinned in `scripts/test_a_paused_mission_says_why.py`. The transition
handlers are lifted whole out of `app.jsx` and run against a fixture
through a fake `setMissions`, so the assertions are about the mission that
comes out, not about field names appearing in a literal. The property
worth keeping is stated over the transitions rather than per-transition:
after any of them the card has *something* to print.

**A note on the test itself.** The first version's fixture was a RUNNING
mission, so reverting the resume fix produced only one failure — resume
leaving a `pauseNote` behind is invisible if the fixture never had one. The
check named for the live symptom was not testing the live symptom. Caught
by fire-testing every arm separately rather than reverting everything at
once and being satisfied that something went red.

### The coworker said it was stuck, and the office wrote it in a drawer

Three domain fields on a task record had writers and no readers:
`blockedReason`, `blockedAt`, `progressLog`. All three are written by the
handlers for `[TASK_BLOCKED: id: reason]` and `[TASK_PROGRESS: id: note]` —
two of the three channels a coworker has for reporting on a job in flight.
Nothing in the product read any of them back.

What that looked like on the floor: a coworker hits a locked spreadsheet,
says so, and the office raises a toast that is gone in about four seconds.
The card stays in DOING, pixel-identical to a job somebody is actively
working. If the boss was in another room when the toast fired, the report
never happened as far as they can tell.

Worse than looking neutral. `worklogLine` answers "is anyone on this?" from
`agent.status` — which is a fact about the COWORKER, not about the job (§4
is explicit that it is the only authority for the first question, and it
was being asked the second). So the moment that coworker was dispatched
anywhere else, the blocked card read

    ⚡ on it · 45m

over a job they had explicitly given up on. A missing answer had become a
wrong one, which is the §7 failure and not merely a gap.

The fix is three lines of reading, and a lifecycle for the field so it
does not outlive its truth. `worklogLine` gets a blocked branch ranked
above both others — "hit a snag", the one place that word is earned,
because §5 reserves it for a coworker who tried. The reason itself renders
under the card, next to `stalledNote`, which is the surface the boss
already reads for "why is this not moving". And the block is cleared on all
three ways off it: a progress note, a completion, and the boss pressing
START.

The gate on the reason line is `!== 'done'`, not `=== 'doing'`, and that
correction came from the reload scrub rather than from taste. `tasksOnLoad`
sends every DOING task back to `inbox` and does *not* clear
`blockedReason` — so a doing-only gate would have hidden a still-true
reason the instant the boss refreshed, leaving "start it again" as the only
advice for a job about to hit the same locked spreadsheet. The scrub's
behaviour is now pinned as the premise of that gate, so if it ever starts
clearing the field the test says the gate can narrow again.

Pinned in `scripts/test_a_blocked_card_says_so.py`. The update handler is
brace-matched whole out of `app.jsx` and run against a real fixture, so the
three clear-sites are measured by the task that comes out rather than by
regexes near a keyword. Six arms, each reverted separately.

**What was measured live, and what was not.** The reason line was watched
render in a throwaway office: a blocked card, a control, and a done card
carrying a stale reason, showing ✋ on exactly the first; then START, which
cleared the field and the card returned to `⚡ on it`. The `hit a snag`
branch of `worklogLine` was *not* observed on a live floor, and could not
be — it only speaks for DOING, and the reload scrub empties DOING before
the page finishes loading, so reaching it live needs a coworker mid-run
and a model to run them. It is covered against the real source in the node
harness instead. Saying which half is which is cheaper than implying both.

**`progressLog` is still write-only, and that is a decision.** A coworker's
progress notes reach a toast and a ten-entry array nobody opens. That is a
missing feature — a card with no history is not lying about anything — and
it was scoped out rather than bolted onto a defect fix. It is the last of
the three write-only fields and it should get a real surface, not a line.

### The DONE column was a wall of titles

`result` is the deliverable — the text a coworker actually produced. The
done handler stamps it on the task next to `completedAt` and `completedBy`.
None of the three had a reader. The only code in the product that touched
`result` was the delete confirmation:

    Delete "…"? Your coworker's work on it will be lost.

So the office warned the boss they were about to lose work it had never
once let them look at.

Measured on a live floor before the fix. A done task carrying a 320-word Q3
summary — revenue figures, two flagged risks, a file path — rendered as:

    Draft the Q3 board summary
    Llama · Researcher            HIGH

That is the whole card. The work existed, was spoken once into a chat
bubble that had long since scrolled away, and sat on the record unread. An
office that cannot show you what came of a finished job is not an operating
business, whatever else it does.

Two more things fell out of the same audit and are fixed in the same pass.

**`progressLog` is no longer write-only.** It was the last of the three
write-only task fields named in the entry above. Collapsed, a card shows
its most recent note — the worklog line says a job is moving, this says
what moved. Expanded, all of them. The `+N earlier` counter is computed
from the notes actually hidden rather than from the log length, because it
is the one claim on this surface that could be a lie rather than an
omission: a count that disagrees with the slice advertises a history that
is not there.

**Clicking a card used to do nothing.** The whole card is a click target
that toggles `expanded`, and `expanded` only un-clamps `-webkit-line-clamp`
on the title and detail. For a card with a short title and no detail —
which is most cards — the click was a visual no-op. Measured: 173px before,
173px after, byte-identical text. That is a worse failure than a missing
feature, because the card *invites* the click and then denies that anything
happened.

The fix uses that, rather than working around it. The result renders in a
`tc-detail`, so it clamps to three lines collapsed and opens to the full
deliverable on click; the history opens with it. Same card, measured after:
173px → 355px, result 54px → 180px, both progress notes appearing. The
click now has a job, and no new CSS was needed to give it one.

Credit comes from `completedBy`, not from the assignee. A card can be
reassigned after it was finished, and naming whoever holds it now would be
the office asserting something it does not know (§4). With no resolvable
finisher it says "finished" and no name.

Pinned in `scripts/test_the_card_shows_what_came_back.py`. `finishedLabel`
runs for real in the node harness; the render assertions are reads of the
real source, because `features.jsx` needs a JSX transform this harness does
not have — which is why the live measurements above are quoted rather than
implied. Twelve arms, each reverted separately. One of them pins a rule in
`styles.css` from a test in another file: without
`.task-card.expanded .tc-detail { -webkit-line-clamp: unset; }` the result
is permanently truncated and the click silently goes back to being a no-op,
and nothing in `features.jsx` would show it.

**A process note.** That last arm meant a fire-test briefly edited
`styles.css`, which a parallel session owns. It was restored from a
scratchpad copy and verified byte-identical, but the window was real: a
concurrent write during those few seconds would have been overwritten by my
restore. Fire-testing a cross-file invariant is worth doing; mutating a file
another session is holding is the part to avoid, and the safer shape is to
assert the rule without reverting it.

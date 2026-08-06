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

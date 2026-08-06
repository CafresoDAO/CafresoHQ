# The Office as Interface — design system for the non-guru

> **Status:** Design doc · 2026-08-05 · implements North Star §3.2/§3.6
> (`strategy/08-north-star-real-product.md`).
> **Builds on** `OFFICE_REVAMP.md` (the continuous floor) and `LIVING_FLOOR.md`
> (desktop mode) — those cover how the office *renders*; this covers how it
> *teaches*. Scope: the metaphor as onboarding + UX for people who will never
> open a terminal, and the copy/animation rules that keep it honest.

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
   > Deferred: **share**. Vault notes have no publish path today
   > (`publishSite` takes a workspace directory, not a note), so rather than
   > ship a button that half-works this is left to the Ship-to-chain work
   > (`DRIVER_CONTRACT.md` §7), which is the real sharing surface.
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

Raw model IDs, JSON, and driver names may appear in desktop-mode surfaces and
settings — never on the floor, the cards, or onboarding.

## 7. What newcomers never see

- A terminal (Living Floor desktop mode keeps it, behind the door).
- A blank prompt box as the primary call to action.
- Vendor logos as coworker identities.
- Settings as a prerequisite to the first task.
- Raw error dumps — every failure is one honest sentence plus "try again /
  ask differently / pick another coworker."

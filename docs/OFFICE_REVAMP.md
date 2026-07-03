# The Open Floor — how the Office reads as a real HQ

> Shipped 2026-07 (feat/office-open-floor). This replaces the earlier draft of this
> doc, which described a flat "5 sprites + corkboard" office that no longer existed.
> Design chosen by a 3-way adversarial panel (Continuous Floorplan beat Living
> Dashboard and 2.5D Perspective), then grafted with the losers' best ideas.

## The idea

The office used to render as a **grid of separate bordered cards** — a character-select
screen. A real HQ is **one continuous place**. The revamp keeps the responsive CSS grid
for *positioning* (that's what survives every breakpoint) and dissolves the card look
purely with styling:

- **`.rooms` is now THE room**: it carries a shared carpet, a border, and a back-wall
  band (`::before`). The grid gaps read as walkable carpet, not wall-void.
- **Workstations, not cards**: `.room` cells are transparent and borderless, separated
  by low partition lines (`.room::before`). Nameplates became hanging desk signs
  (bordered chips, `align-self: center`) instead of full-width header bars.
- **The CEO keeps a real corner office**: bordered, own floor, and a **glass partition**
  (`.room.ceo::after`) looking onto the open floor. The contrast sells "HQ".
- **Depth without distortion**: rooms get `z-index` by DOM order (front rows overlap
  back rows) + a 6px stagger on even cells. No `rotateX` — the 16×16 sprites are
  front-facing and would distort.
- **Places on the floor**: a meeting table + "MEETING" decal on the left (where the
  meeting cluster already gathers), the couch + water cooler as a "KITCHEN" corner on
  the right. The existing walker animations commute to real destinations now.
- **Vacant desks** are unclaimed floor space (dashed outline) instead of boxed cards.

## The live-work layer (the office IS the dashboard)

`cafresohq:agentTool` events now carry `agentId`/`agentName`/`agentColor`
(app.jsx `pulseGraph(ev, agent)`), and the office listens:

- **Monitor glow + tool chip** — while an agent really runs a tool, its desk screen
  lights up (`.room.tool-live .desk::after`) and a chip shows the tool
  (`⚙ vault search`). `done` lingers 1.6s; a 45s safety clear covers error paths.
- **● LIVE wall pip** — appears whenever any desk is live (`.wall-live`).
- **Receipts pin themselves to the corkboard** — deliverable tools (VAULT_NEW,
  EXPORT_PPTX/DOCX/PDF, GENERATE_IMAGE/VIDEO, PUBLISH_SITE) auto-pin via the existing
  `onPin` mechanism (quiet, deduped by sourceId; app.jsx `recordToolReceipt`).
- **Wall P&L board** — `.pl-frame` shows per-agent wallet spend/cap (on-chain policy
  via `CafresoHQChain.wallet.list()`), rendered only when the Wallet ICP-Service is
  installed and the shell bridge is reachable.
- **Activity ticker** — the existing `<Ticker>` below the office (fed by
  `logActivity`) is the scrolling record of real actions; no duplicate was added.

## Modes

- **Night** (`body.night`): the shared carpet goes dark (`#141728`), open rooms stay
  borderless, the CEO office keeps its walls, screens glow blue when live.
- **Mobile** (≤768px): the open-plan illusion can't read on a phone — rooms revert to
  the compact bordered cards + the `.mobile-agent-strip`, all wall/floor fixtures hide.
- **Reduced motion**: glow animation is gated behind `prefers-reduced-motion:
  no-preference` (static highlight remains); all pre-existing gates untouched.

## Where things live

- `styles.css` — `.rooms`/`.room`/nameplate/CEO/glass/partition restyle (~line 2220+),
  open-floor fixtures + live layer + night + mobile revert (one section near EOF).
- `ui.jsx` — OfficeView: liveTools listener, P&L state, wall fixtures, meeting table +
  floor decals, per-room z-depth, tool chip (~line 1666+).
- `app.jsx` — event attribution (`pulseGraph`), quiet auto-pin (`recordToolReceipt`).

## Invariants (don't break these)

- Every existing handler still works: drag-drop task rail → desk, `onInspect`,
  `onCoffee`, `onSitWithCEO`, `onOpenMeeting`, `onOpenMemory`, sticky/pin handlers,
  subordinate desks, FOR-HIRE → HireModal.
- Drop-target feedback uses `outline` (survives the borderless rooms).
- No new JS animation loop; everything ambient is CSS.
- Pixel-art identity stays scoped to the Office (per docs/strategy/05-design-cohesion.md).

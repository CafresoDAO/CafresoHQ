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
- `ui/office.jsx` — OfficeView: liveTools listener, P&L state, wall fixtures, meeting
  table + floor decals, per-room z-depth, tool chip. (It used to live in `ui.jsx`;
  that file is now a 50-line barrel re-exporting `ui/*.jsx`, so the old ~line 1666
  anchor no longer exists.)
- `app.jsx` — event attribution (`pulseGraph`), quiet auto-pin (`recordToolReceipt`).

## Invariants (don't break these)

- Every existing handler still works: drag-drop task rail → desk, `onInspect`,
  `onCoffee`, `onSitWithCEO`, `onOpenMeeting`, `onOpenMemory`, sticky/pin handlers,
  subordinate desks, FOR-HIRE → HireModal.
- Drop-target feedback uses `outline` (survives the borderless rooms).
- No new JS animation loop; everything ambient is CSS.
- Pixel-art identity stays scoped to the Office (per docs/strategy/05-design-cohesion.md).

## 2026-09-12 · the office, lit (#431)

The building above was structurally right and visually flat: every
interior one tile fill, no light source, no ceiling, no floor under the
desks, the tower pasted on the sky. Night had atmosphere only because its
assets did. #431 is a light-and-depth pass in CSS alone — the last section
of `styles.css`, "the office, lit":

- **Rooms** — `.px-int::before`: a wall wash from above, a beam through
  the window, a baseboard line where wall meets floor, a floor shadow
  where the desks stand. z1: under the desk set, over the tiles, the plane
  the night overlay already used. By night the moon takes the window and a
  **lamp pools on the desk** — only where somebody sits; a vacant or away
  unit gets the moon and no lamp.
- **Building** — `.px-building::after` shades both edges so the tower
  stands in front of the sky; the sign throws a hard pixel shadow by day.
- **Sky** — a warm horizon haze between the sky and the far skyline (city
  glow, violet, at night), the sun and moon with a glow of their own, and
  the stars twinkling — the one animation added, behind
  `prefers-reduced-motion: no-preference` like every other ambient motion.
- **Desk signs** — a bevel and a one-pixel text shadow; colours untouched.
- **Lobby** — light spills from under the awning onto the doors at night.

Two promises, measured in a real headless browser by
`scripts/test_the_office_is_lit_and_nothing_moved.py`: every overlay is
`pointer-events: none` and a plate or a desk is still what is under the
pointer through it; and with the whole layer `display:none`'d, floors,
interiors, lobby, street and the scene's scroll height are identical to
the pixel — this layer can never be why a phone suite drifts.

Invariants above still hold: no JS loop, pixel identity stays in the
Office, mobile keeps the same rooms with the same light.

## 2026-09-12 · the office, alive (#432)

After the light, the three things the eye landed on:

- **"standing by" three times over.** An idle coworker's bubble is now
  `.px-bubble.quiet`: same words, same place, three-fifths the presence. A
  working coworker keeps the full bubble. (`ui/office.jsx` marks it from
  `status`; the words are untouched.)
- **A dark monitor on a thinking coworker.** `.px-glow` used to light only
  for a running tool; it now lights while `status === 'busy'` too, with a
  slower, softer `thinking` pulse behind `prefers-reduced-motion:
  no-preference`. A tool run keeps the flicker.
- **A sun nailed to one spot.** `skyArc()` places the sun (6→20) and the
  moon (19→7) on a low arc from the local hour — a `setInterval` tick a
  minute, which is a clock, not an animation loop; inline `left`/`top`
  only, size and layer stay the stylesheet's.

Same suite as #431 measures the quiet opacity on a placed bubble, the sun
and moon against the arc for the hour the browser is in, and the gating.


# The Living Floor — HQ desktop (window) mode

> Shipped 2026-07 (feat/living-floor), ported from the VM branch `feat/workspace-os`
> (built 2026-06-26) onto trunk after the Open Floor revamp. **On by default.**

## What it is

The HQ is an agentic workflow OS — this makes the "OS" literal. Instead of one
full-screen `activeView` at a time, the **office floor is the desktop wallpaper**
(always visible, with its live monitor glow / ● LIVE pip / ticker running), and
apps (Tasks, Calendar, Memory, Vault, Team, Terminal, Workspace) open as
**draggable, resizable, minimizable windows** over it, with a centered
macOS-style dock.

- **WindowFrame** (app.jsx): generic window — title-bar drag, 8-edge resize,
  minimize-to-dock (stays mounted, state survives), maximize (button /
  double-click titlebar / drag-to-top), **edge-snap** (drag to left/right edge
  tiles to that half). Gesture listeners attach only during a drag — N idle
  windows add zero listeners.
- **openWindows registry**: file-backed (`state/windows`) → sessions restore
  windows + geometry + z-order on reload; also captured by Workspaces save/apply.
- **Dock**: one icon per app (running/minimized dots), a "show the office floor"
  button (minimize all), and a power button (exit desktop mode).
- **Rail = launcher** in desktop mode; clicking **Office shows the floor**
  (minimizes all) — the office never opens inside a window over itself.
- **Command palette**: "Exit/Enable desktop (window) mode", "Open in window: …".
- **Mobile (≤768px)**: floating windows are suppressed; the same openWindows
  model renders as an iOS-style app switcher (FAB → card stack + launcher grid).
  The mobile tab bar is unchanged.
- **z-order**: windows live in the `--z-window` band (300–340), dock at 345 —
  under dropdowns (350) and modals (400).

## Defaults & escape hatches

`windowsEnabled` defaults to **true** (localStorage `k('windowsEnabled')`).
Users can exit via the dock power button, the command palette, or the mobile
switcher's "Exit desktop mode" — the choice persists per browser. Classic
single-view mode is unchanged and fully supported.

## Trunk integration notes (differences from the VM branch)

- `openclawToast` → `cafresohqToast` (naming unification landed in between).
- 'projects' nav id now renders the Cohabit **WorkspaceView** — labeled
  "Workspace" everywhere (dock, palette, switcher).
- Fixed a pre-existing chrome bug the wallpaper amplified: `.main` had no
  explicit `grid-template-columns`, so the topbar status strip's max-content
  width (~1490px) forced the whole page into horizontal scroll on ≤1500px
  screens. Now: `.main { grid-template-columns: minmax(0,1fr) }` and the status
  strip scrolls internally (hidden scrollbar).

## Invariants (don't break these)

- The office wallpaper is the real OfficeView — all Open Floor live-data grafts
  (tool glow, chips, corkboard receipts, P&L frame) must keep working behind
  windows (verified: synthetic `cafresohq:agentTool` events light desks over
  the wallpaper).
- Minimized windows stay mounted (`display: none` wrapper) — never unmount.
- Views must tolerate arbitrary window sizes: fix with `.hq-window-body`
  height rules in styles.css, not per-view viewport pins.
- Chat stays outside the window manager (ChatWindow popover / mobile chat view).

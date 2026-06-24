# CafresoHQ — Design System

> Single source of truth for visual language, components, and patterns.
> Started **Session 1** (foundations). Components and patterns sections grow each session.

---

## How to use this doc

- **Tokens are mandatory** — new code must use the token vars below, not hardcoded values.
- **Components are the ladder** — reach for an existing component before writing a new one.
- **When in doubt, follow the existing pixel-art identity** — Stardew-adjacent warm pastels, brutal-grid lines, square corners by default.

---

## 🎨 Tokens

All defined in [`styles.css`](./styles.css) at the top of `:root`. Override per-theme in `body.night`.

### Spacing

4px base, ~1.5× geometric step.

| Token | Value | Use |
|---|---|---|
| `--sp-1` | 2px | hairline gap |
| `--sp-2` | 4px | tight inline (icon → label) |
| `--sp-3` | 6px | compact pad (small button inner) |
| `--sp-4` | 8px | default gap (lists, toolbars) |
| `--sp-5` | 12px | card pad |
| `--sp-6` | 16px | section pad |
| `--sp-7` | 24px | group separator |
| `--sp-8` | 32px | major separator |
| `--sp-9` | 48px | hero spacing |

### Typography

Sized in absolute px — pixel-art identity benefits from crisp sub-pixel sizes.

| Token | Value | Use |
|---|---|---|
| `--text-9` | 9px | micro: badge counts, captions |
| `--text-10` | 10px | tiny: meta info, tag labels |
| `--text-11` | 11px | small: tabs, nav, pill buttons |
| `--text-12` | 12px | default body for compact UIs |
| `--text-13` | 13px | body — file tree, code editor, nav text |
| `--text-15` | 15px | prominent body / form input |
| `--text-18` | 18px | H3 — section headings |
| `--text-22` | 22px | H2 — view titles |
| `--text-28` | 28px | H1 — modal/page titles |

Line-heights: `--lh-tight` (1.25), `--lh-normal` (1.5), `--lh-loose` (1.7).

### Radii

| Token | Value | Use |
|---|---|---|
| `--radius-1` | 2px | hairline rounding |
| `--radius-2` | 4px | default — buttons, inputs |
| `--radius-3` | 6px | windows, panels |
| `--radius-4` | 8px | modals (with shadow-4) |
| `--radius-pill` | 999px | badges, chips |

### Shadows (elevation)

| Token | Day mode | Night mode | Use |
|---|---|---|---|
| `--shadow-1` | 0 1px 2px ·10 | 0 1px 2px ·40 | hairline lift (cards) |
| `--shadow-2` | 0 4px 12px ·18 | 0 4px 12px ·55 | dropdown / popover |
| `--shadow-3` | 0 8px 22px ·22 | 0 8px 22px ·60 | floating window (chat) |
| `--shadow-4` | 0 12px 36px ·28 | 0 12px 36px ·65 | modal |

### Z-index registry

**Never use raw z-index numbers in code — always reference these tokens.**

| Token | Value | Use |
|---|---|---|
| `--z-base` | 1 | default layer |
| `--z-dropdown` | 50 | menu dropdowns |
| `--z-overlay` | 100 | drawer overlays, lasso rect |
| `--z-toast` | 200 | status messages |
| `--z-window` | 320 | floating chat window, popouts |
| `--z-modal` | 400 | HireModal, SettingsModal, etc. |
| `--z-tooltip` | 500 | hover tooltips, last in front |

### Motion

| Token | Value | Use |
|---|---|---|
| `--motion-fast` | 120ms | hover state changes |
| `--motion-base` | 200ms | modal/popover entry, drawer slide |
| `--motion-slow` | 320ms | settling animations, button spinners |
| `--ease-out` | cubic-bezier(0.2, 0.8, 0.2, 1) | entry / settle |
| `--ease-in` | cubic-bezier(0.4, 0, 1, 1) | exit |
| `--ease-inout` | cubic-bezier(0.4, 0, 0.2, 1) | symmetric loops |

---

## 🧩 Components

### `<Modal>` — Dialog shell

Defined in [`modals.jsx`](./modals.jsx). Exposed as `window.CafresoHQModals.Modal`.

#### Variants
None directly — variation comes from the `size` prop.

#### Sizes
| `size` | Max width |
|---|---|
| `sm` | 420 px — confirmation prompts |
| `md` (default) | 560 px — small forms |
| `lg` | 760 px — most modals |
| `xl` | 980 px — full forms (Settings, Standup) |
| `fullscreen` | 100vw / 100vh — immersive (rare) |

#### Props
| Prop | Type | Default | Description |
|---|---|---|---|
| `open` | bool | — | Renders `null` when false |
| `onClose` | fn | — | Fired by ✕ / Esc / backdrop click |
| `title` | node | — | Main heading; sets `aria-labelledby` |
| `subtitle` | node | — | Kicker line below title |
| `headerActions` | node | — | Extra buttons in the header right side |
| `footer` | node | — | Sticky footer slot (auto-styled) |
| `size` | str | `'md'` | See sizes table |
| `dismissable` | bool | `true` | Set false to disable Esc/backdrop close |
| `children` | node | — | Body content |

#### States
| State | Visual | Behavior |
|---|---|---|
| Opening | Backdrop fades in, dialog slides+scales in over `--motion-base` | Focus moves to first focusable element after 30ms |
| Open | Standard | Tab cycles within dialog; Shift-Tab reverses; body scroll locked |
| Closing | (instant — no exit animation in v1) | Focus returns to the element that opened it |

#### Accessibility
- `role="dialog"`, `aria-modal="true"`
- `aria-labelledby` linked to title
- Esc to close (skipped when typing in inputs)
- Focus trap — Tab/Shift-Tab cycle within
- Body scroll locked while open
- Returns focus to trigger on close

#### Do's and Don'ts
| ✅ Do | ❌ Don't |
|---|---|
| Use for any blocking dialog | Use for transient toasts (use the toast system instead — Session 2) |
| Pass `footer` prop for actions | Inline a `<div className="modal-foot">` — use the prop |
| Use `size="xl"` for forms with 3+ columns | Use `fullscreen` unless the content genuinely needs the entire viewport |

#### Code example
```jsx
<Modal
  open={open}
  onClose={onClose}
  title="HIRE A SUB-AGENT"
  subtitle="character creation"
  size="lg"
  headerActions={<button>Templates</button>}
  footer={<><button>Cancel</button><button>HIRE ✓</button></>}
>
  <FormFields />
</Modal>
```

---

### `<Btn>` — Buttons

Defined in [`ui.jsx`](./ui.jsx). Exposed as `window.CafresoHQUI.Btn`.

Wraps the existing `.px-btn` CSS — same pixel-art identity (square corners, drop shadow, pop-up hover, push-down active) — but with a uniform JSX surface that handles sizes, loading state, and disabled state.

#### Variants
| Variant | Background | Color | Use |
|---|---|---|---|
| `primary` | `--ceo` (purple) | cream | Main CTA — "HIRE", "SAVE", "START" |
| `secondary` (default) | `--paper` | ink | Most actions |
| `ghost` | transparent | `--ink-2` | Tertiary, low-emphasis (topbar nav) |
| `danger` | `--error` (red) | cream | Destructive — "DELETE", "STOP ALL" |

#### Sizes
| Size | Padding | Font |
|---|---|---|
| `sm` | `--sp-2` × `--sp-4` | `--text-9` |
| `md` (default) | `--sp-3` × `--sp-5` | `--text-10` |
| `lg` | `--sp-4` × `--sp-6` | `--text-12` |

#### Props
| Prop | Type | Default | Description |
|---|---|---|---|
| `variant` | str | `'secondary'` | See variants |
| `size` | str | `'md'` | See sizes |
| `loading` | bool | `false` | Shows spinner, hides label, locks click |
| `disabled` | bool | `false` | Locks click, dims |
| `icon` | node | — | Rendered before label |
| `iconAfter` | node | — | Rendered after label |
| `full` | bool | `false` | `width: 100%` |
| `onClick` | fn | — | Click handler |
| `title` | str | — | Tooltip |
| `type` | str | `'button'` | `'submit'` for forms |

#### States
| State | Visual | Behavior |
|---|---|---|
| Default | Drop shadow + border | — |
| Hover | Lifts `(-1px, -1px)`, deeper shadow | — |
| Active | Pushes `(+1px, +1px)`, smaller shadow | — |
| Disabled | 45% opacity, `cursor: not-allowed` | onClick blocked |
| Loading | Label hidden, centered spinner | onClick blocked, `aria-busy="true"` |

#### Accessibility
- `<button type="button">` (or `submit` if specified)
- `aria-busy="true"` while loading
- `disabled` attribute when disabled or loading

#### Code example
```jsx
<Btn variant="primary" size="md" loading={busy} onClick={save}>
  Save
</Btn>

<Btn variant="ghost" size="sm" icon={<Ico kind="memory"/>}>
  📁 MEMORY
</Btn>

<Btn variant="danger" loading={stopping} onClick={onStopAll}>
  ■ STOP ALL
</Btn>
```

---

### `<Card>` — Layout primitive

Defined in [`ui.jsx`](./ui.jsx). Exposed as `window.CafresoHQUI.Card`.

#### Variants
| Variant | Visual | Use |
|---|---|---|
| `default` | hairline shadow + rule border | most "boxed group of stuff" |
| `raised` | `--shadow-2` | popovers, important callouts |
| `inset` | `--paper-2` background, no shadow | inside a card, secondary regions |
| `outline` | rule border, no shadow | low-emphasis groups |
| `interactive` | hover lifts, click pushes | clickable cards (auto-applied if `onClick` given) |

#### Props
| Prop | Type | Default | Description |
|---|---|---|---|
| `variant` | str | `default` (or `interactive` when onClick set) | See variants |
| `size` | str | `'md'` | `sm` / `md` / `lg` body padding |
| `selected` | bool | `false` | Adds outlined-active state |
| `onClick` | fn | — | If set, auto-applies `interactive` variant |
| `as` | str | `'div'` | Render tag — `'button'` for native semantics |
| `header` | node | — | Shorthand for `<Card.Header>` |
| `footer` | node | — | Shorthand for `<Card.Footer>` |

Composed via `<Card.Header actions={…}>`, `<Card.Body>`, `<Card.Footer>` slots when needed.

#### Code example
```jsx
<Card variant="raised" size="md" onClick={onSelect} selected={isActive}>
  <h3>Selvin · Code Gremlin</h3>
  <p>Tasks done: 47 · last seen just now</p>
</Card>

<Card header={<>📁 Memory <Card.Header.actions>{<Btn>Add</Btn>}</>}>
  <MemoryList />
</Card>
```

---

### Input primitives — `<Field>`, `<TextField>`, `<TextArea>`, `<Select>`, `<Checkbox>`, `<Toggle>`, `<SearchField>`

All in [`ui.jsx`](./ui.jsx), exposed via `window.CafresoHQUI`.

Every input is wrapped by `<Field>` which renders the label / hint / error structure. Input components compose `<Field>` + a styled HTML element.

#### Common props (all inputs)
| Prop | Type | Description |
|---|---|---|
| `label` | node | Visible label (auto-linked to input via `id`) |
| `hint` | node | Helper text below the control |
| `error` | node | Error text (red, replaces hint when set; sets `aria-invalid`) |
| `required` | bool | Adds red `*` to label |
| `id` | str | Auto-generated if not provided |
| `disabled` | bool | Visual + behavioral disable |

#### `<TextField>`
| Prop | Description |
|---|---|
| `value` / `onChange` | Standard React input pattern |
| `onEnter` | Fires on Enter key (skipped on Shift-Enter) |
| `placeholder` | — |
| `type` | `'text'`, `'password'`, `'email'`, etc. |
| `size` | `sm` / `md` / `lg` |
| `icon` / `iconAfter` | Leading / trailing icon node |

#### `<TextArea>`
| Prop | Description |
|---|---|
| `rows` | Default 4 |
| `resize` | `vertical` (default) / `none` |
| `mono` | Toggle JetBrains-Mono for code-like content |
| `onEnter` | Same as TextField |

#### `<Select>`
| Prop | Description |
|---|---|
| `options` | `[{ value, label, disabled }]` or array of strings |
| `placeholder` | Renders as empty-value first option |

You can also pass `<option>` children directly instead of `options`.

#### `<Checkbox>`
| Prop | Description |
|---|---|
| `checked` / `onChange` | Standard React checkbox API |
| `label` / `hint` | Inline label + helper text on the right of the box |

#### `<Toggle>`
| Prop | Description |
|---|---|
| `checked` / `onChange(next)` | Pass a `(boolean) → void` handler. Yes — different from native `onChange(event)` |
| `label` / `hint` | If both omitted, renders bare switch only |

Keyboard: Space / Enter toggle. Has `role="switch"` + `aria-checked`.

#### `<SearchField>`
A `<TextField>` preset with a 🔍 icon and an inline ✕ clear button when content exists.
```jsx
<SearchField value={q} onChange={e=>setQ(e.target.value)} onClear={() => setQ('')} placeholder="Search vault…" />
```

#### Focus ring
All inputs get a 2px gold accent ring (`--accent-sun`) on focus. Errors get a translucent red ring. Universal — replaces the previously-absent focus styling.

#### Code example
```jsx
<TextField
  label="Project name"
  hint="appears in the sidebar and search"
  required
  value={name}
  onChange={e => setName(e.target.value)}
  error={tooShort ? 'at least 3 characters' : null}
/>

<Toggle label="Enable mission auto-restart" hint="resume after browser reload" checked={auto} onChange={setAuto} />
```

---

### `<Tabs>` — Tab strip

Defined in [`ui.jsx`](./ui.jsx). Exposed as `window.CafresoHQUI.Tabs` + `Tab`.

#### Variants
| Variant | Visual | Use |
|---|---|---|
| `default` | bordered rectangles, drop-shadow on active | matches the pixel-art button identity |
| `underline` | flat with underline-bar active | inside modals, density-friendly |
| `pill` | rounded pills, tighter padding | header bars, filter chips |

#### Props
| Prop | Type | Description |
|---|---|---|
| `value` | any | Currently active tab's `value` |
| `onChange` | fn | Fired with the new value when a tab is clicked |
| `variant` | str | See variants |
| `stretched` | bool | Make tabs share remaining width equally |
| `items` | array | Pass `[{ value, label, badge, icon, disabled }]` instead of children |

Use `<Tab>` children for inline composition, or `items` array for data-driven tabs.

#### Accessibility
- `role="tablist"` on container, `role="tab"` on each
- Arrow Left/Right navigates between tabs
- Active tab has `aria-selected="true"` and `tabIndex={0}`; others `tabIndex={-1}`

#### Code example
```jsx
<Tabs value={tab} onChange={setTab} variant="underline">
  <Tab value="chat" label="Chat" badge={msgCount} icon="💬" />
  <Tab value="roster" label="Roster" badge={agents.length} />
</Tabs>

<Tabs value={tab} onChange={setTab} stretched
  items={[
    { value: 'agents', label: 'Per-agent' },
    { value: 'global', label: 'Global' },
    { value: 'keys',   label: 'API Keys' },
  ]} />
```

---

### Toast / status system — `<ToastProvider>` + `useToast()`

Defined in [`ui.jsx`](./ui.jsx). Mounted once at the app root.

#### Hook API
```js
const toast = useToast();

toast.info('Saved.');
toast.success('Created Inbox/idea.md');
toast.warn('No path between selected nodes');
toast.error('Save failed', { detail: err.message });
toast.action('Build complete', { actionLabel: 'Open log', onAction: () => openLog() });

toast.dismiss(id);    // dismiss specific
toast.dismissAll();   // clear queue + visible
```

#### Imperative escape hatch
For non-React callers (event listeners, runners, timers):
```js
window.cafresohqToast.info('Hello from outside React');
```

The provider sets/clears `window.cafresohqToast` on mount/unmount.

#### Toast object shape
| Field | Default | Description |
|---|---|---|
| `kind` | per call | `info` / `success` / `warn` / `error` / `action` |
| `title` | required | Main message line |
| `detail` | — | Smaller secondary line below |
| `icon` | per kind | Override the default icon |
| `duration` | per kind | Auto-dismiss in ms; `0` to persist |
| `actionLabel` + `onAction` | — | Render an action button on the right |
| `dismissable` | `true` | Show the ✕ close button |

#### Visual
- Bottom-center stack, max **3 visible**, older queued
- Each toast has a color-coded **6px left border**
- **Countdown bar** at bottom visualizes the auto-dismiss timer
- Enter animation: 200ms slide-up + scale
- Hover doesn't auto-pause yet — Session 3 polish

#### Migrated callers
- Vault Graph: `setStatusMsg({ text, kind })` now routes through `window.cafresohqToast` automatically (kept the same shape so call sites didn't need rewrites)
- Future migrations: Hire flow, agent runner errors, settings save confirmations

---

### `<CommandPaletteProvider>` + `useCommands()`

Defined in [`ui.jsx`](./ui.jsx). Mounted **once** at app root inside `<ToastProvider>`.

#### Opening
- **Cmd-K** (Mac) or **Ctrl-K** (Win/Linux) anywhere in the app
- Programmatically: `window.cafresohqPalette.open()`

#### Registering commands
Any component can register commands while it's mounted:
```js
useCommands([
  {
    id: 'my.action',
    label: 'Do the thing',
    section: 'My Section',
    icon: '✦',
    detail: 'optional secondary text on the right',
    shortcut: ['⌘', 'D'],
    when: () => isReady(),    // optional visibility check
    run: () => doTheThing(),
  },
], [isReady]);
```
Commands automatically deregister when the component unmounts. Section is optional — commands without one go into "Other".

#### Built-in commands (always available)
- **Navigation**: Switch view: Office / Tasks / Calendar / Memory / Vault / Team / Docs / Workflows / Projects / Content
- **Actions**: Hire agent · End-of-day stand-up · Open research missions · New workflow · Open memory shelf · Open settings · Stop all (when busy)
- **Toggles**: Day/night · Collapse/expand sidebar · Open/close chat window
- **Density**: Comfortable · Compact · Spacious
- **Help**: Keyboard shortcuts · Replay onboarding tour

#### Imperative escape hatch
```js
window.cafresohqPalette.open()
window.cafresohqPalette.close()
window.cafresohqPalette.run('nav.vault')
window.cafresohqPalette.list()  // → [{id, label, section}, …]
```

#### UX
- Fuzzy ranking: prefix > word-prefix > substring > section-substring
- Arrow keys navigate, Enter runs, Esc closes
- Auto-grouped by section when no query; flat ranked list when searching
- Mouse hover updates the selection cursor
- Backdrop click closes

---

### Density modes

Toggle via the palette (`Density: Compact` / `Spacious` / `Comfortable`) or programmatically. Persists to localStorage.

| Mode | Body class | Spacing scale |
|---|---|---|
| Comfortable (default) | _none_ | 1.0× — stock token values |
| Compact | `body.density-compact` | ~0.75× — tighter padding/gap everywhere |
| Spacious | `body.density-spacious` | ~1.25× — more breathing room |

Only **spacing** tokens scale — type stays constant so reading remains comfortable. Implemented as overrides of `--sp-*` vars at the body level. Every component that uses tokens scales for free. Anything still using hardcoded px values stays put — flag those for migration if you spot them.

---

### `<NotificationBell>` + `<NotificationCenter>`

Defined in [`ui.jsx`](./ui.jsx). Bell renders in the topbar; clicking opens a slide-in side panel from the right.

#### Sources
The app folds three streams into one:
- **Approvals** (top-priority unread) — pending approval requests
- **Receipts** — every approval/rejection + tool-execution audit entry
- **Live event feed** — `cafresohq:agentActivity` (throttled to one per node per 4s) + `cafresohq:agentRunnerError`

#### Notification shape
```js
{
  id, kind, msg, ts, unread, source,
  icon?,     // override default icon
  onClick?,  // optional row handler
}
```
`kind`: `approval` | `receipt` | `agent` | `mission` | `system`.

#### UX
- Filter chips along the top — `All / Approvals / Receipts / Agents / Missions / System` (chips with 0 items hide automatically)
- Click row to fire its `onClick` (e.g., approvals navigate to the office)
- "Mark all read" + "Clear all" actions
- Esc closes
- The `unread` set is cleared whenever the panel closes

Replaces the bottom-right collision of receipts tray + chat pill + status pills + agent activity dots.

---

### `<OnboardingTour>`

Defined in [`ui.jsx`](./ui.jsx). Multi-step coach-mark flow.

#### Step shape
```js
{
  id,
  title,           // step heading
  body,            // explanatory text
  target?,         // optional CSS selector or () => HTMLElement — spotlight ring + auto-anchor
  action?,         // optional fn — runs when the step is shown (e.g. switchView('vault'))
}
```

#### Behavior
- Backdrop dims the page; if `target` resolves, a yellow spotlight ring draws around the element with a glowing outline, and the card anchors itself near it (above or below depending on space)
- Without `target`, the card sits centered
- Arrow keys navigate (← back, → next), Enter advances, Esc skips
- Progress dots at the bottom
- Triggered once on first launch (with 800ms warm-up). Replay anytime via the palette command "Replay onboarding tour" (which fires `cafresohq:replayTour`).

#### Default tour (CafresoHQ)
6 steps: **Welcome** → **Rail** → **Topbar** → **Palette** → **Notifications** → **Hire** — each scoped to a real DOM target where useful.

---

### Toast hover-pause (polish)

Toasts now pause their auto-dismiss timer + countdown bar when the mouse hovers over them. Move the mouse off → countdown resumes from where it left off. Implemented by tracking `{ handle, remaining, startedAt, paused }` per toast and toggling a `.is-paused` class that animation-pauses the visual progress bar.

Important for actionable toasts — users get time to read and click the action button without racing the timer.

---

### Theme variants

Four optional palettes layered on top of the default warm-pastel theme. Each is a pure CSS class on `body` that overrides the color tokens (`--paper`, `--ink`, `--accent-*`, `--tag-*`). Switch via the palette ("Theme: …") or programmatically.

| Theme | Body class | Use |
|---|---|---|
| Default | (none) | Warm pastel — Stardew-adjacent default |
| Sepia | `body.theme-sepia` | Aged-paper warm tones for long reading sessions |
| Solarized | `body.theme-solarized` | Classic dev-tool palette (Schoonover) |
| Dracula | `body.theme-dracula` | High-contrast dark with vivid accents |
| High contrast | `body.theme-highcontrast` | A11y-first, day & night sub-variants |

Persists to localStorage. `body.night` still applies on top — for themes where light/dark variants make sense (default, high-contrast).

To add a new theme: add a `body.theme-foo { … }` block in styles.css overriding the color tokens, then register a palette command. ~30 lines per theme.

---

### Workspaces

A workspace is a snapshot of UI state: `{ activeView, railCollapsed, chatWinOpen, density, theme, night }`. Switching workspaces is a single state diff — no reload, no flicker.

**Built-in workspaces** (always available):
- **Coding** — Projects view · rail collapsed · density compact
- **Research** — Vault view · chat open · comfortable density
- **Standup** — Office view · default everything
- **Reading** — Docs view · sepia theme · spacious density · rail collapsed

**User workspaces**: any time, run "Save current state as workspace…" from the palette. Name it. The current `activeView, railCollapsed, chatWinOpen, density, theme, night` are captured. Apply via `Workspace: <name>` palette command. Delete via the auto-generated "Delete workspace …" command.

The active workspace ID persists; the saved-workspace list persists separately.

#### State APIs (in app.jsx)
```js
applyWorkspace(workspace)       // apply a workspace's state object
saveCurrentWorkspace()          // prompt + capture current state
deleteWorkspace(id)
```

---

### Drag-drop folder → Projects

The Projects view's left pane (the project list) accepts folder drops. **Browser security note**: drag-drop from the OS doesn't expose absolute paths, so the drop only suggests a folder name — the user still types/pastes the absolute path in a follow-up prompt. The `+ ADD` button in the section header opens the same flow without dragging.

Visual feedback: dashed yellow outline appears on the panel during dragover; clears on drop or dragleave.

---

### `<AgentInbox>`

Per-agent activity stream — a live feed of every `cafresohq:agentActivity` event grouped by agent. Lives in the right side of the Team view, toggleable via the **📥 INBOX** button in the section header (or the per-agent `📥` button on each agent card).

**Event shape** consumed:
```js
{ nodeId, agentId, agentName, color, kind: 'read'|'write'|'link' }
```

Renders the most recent ~250 events. Filter chips at the top let you narrow to one agent. Click any row → fires `cafresohq:openNote` so the vault opens that note in the active view. Time-ago labels (`5s` / `2m` / `4h` / `1d`).

This complements the **Notification Center** (which is throttled to one per node per 4s for high-level awareness). The inbox is the firehose — every event, ungrouped, surfaced where the user already manages the team.

---

### Popout Vault Graph

Multi-monitor support for the graph. Click **🪟 POP OUT** in the gear panel to open a separate window with only the graph in it. Pop the window onto a second monitor; click and explore freely.

**Architecture**:
- New window opens at `?popout=graph` on the same origin
- `app.jsx` checks the URL param and mounts a stripped-down `<GraphPopout>` component (just `<ToastProvider>` + a header bar + `<GraphView>` standalone)
- Both windows share state via `BroadcastChannel('cafresohq-graph')`:
  - **popout → parent**: `{ type: 'open-note', path }` when a node is clicked → parent switches to vault view + dispatches `cafresohq:openNote`
  - **parent → popout**: `{ type: 'set-active', path }` to sync the active note (future)
  - `{ type: 'close' }` to programmatically close the popout

**Limits**: each window is its own React tree, so component state isn't shared (deliberate — the popout has its own gear panel, settings, etc.). Data is fetched fresh from `vaultGraph()` in the popout, but the link sync makes it feel unified.

The popout button hides itself in the popout window (detected via `window.opener` being non-null) so users can't spawn a popout-of-a-popout.

---

## 🔮 Future ideas (post-Session-4)

| Idea | Notes |
|---|---|
| Hover preview tooltips on graph nodes (existing) → richer markdown render | Currently strips frontmatter and shows ~220 chars; could parse first heading + first paragraph |
| Workspace import/export | Share workspaces as JSON via clipboard or a saved-views file |
| Per-workspace chat history | Each workspace gets its own scoped chat thread |
| Agent inbox: drill into a specific event | Show the surrounding 5 events + the LLM trace if available |
| Voice input for chat | Add a 🎤 button in ChatWindow using SpeechRecognition |
| 3D graph in popout window | Already works via `is3D` toggle that persists per-window |

---

## 📜 Conventions

- **Class prefixes:** Existing utility classes (`.px-btn`, `.tree-row`, etc.) keep working. New global utilities should use the `oc-` prefix.
- **Inline styles:** Acceptable for one-off tweaks, but prefer token vars (`var(--sp-4)`) over magic numbers (`8px`). Migrate inline styles to classes when you touch a file.
- **Z-index:** Always reference the registry — `style={{zIndex: 'var(--z-modal)'}}`. Never write raw numbers.
- **Focus rings:** Custom focus styling per-component is fine, but every interactive element MUST have a visible focus indicator. Browser defaults are acceptable as a fallback.
- **Animation:** New animations should use the motion tokens. Don't introduce a new duration unless tokens don't fit.

---

## 🛠 Migration guide (for converting old code)

Common find-and-replace patterns:

| Find | Replace with |
|---|---|
| `fontSize: 9` | `fontSize: 'var(--text-9)'` |
| `fontSize: 10` | `fontSize: 'var(--text-10)'` |
| `fontSize: 11` | `fontSize: 'var(--text-11)'` |
| `gap: 8` | `gap: 'var(--sp-4)'` |
| `padding: '6px 10px'` | `padding: 'var(--sp-3) var(--sp-5)'` |
| `boxShadow: '0 6px 18px rgba(0,0,0,0.22)'` | `boxShadow: 'var(--shadow-3)'` |
| `zIndex: 60` | `zIndex: 'var(--z-window)'` |
| `<div className="backdrop">…<div className="modal">` | `<Modal open={open} onClose={onClose} title="…">` |
| `<button className="px-btn primary">` | `<Btn variant="primary">` |
| Bare `<input>` with inline borders/padding | `<TextField label hint />` |
| Bare `<textarea>` | `<TextArea label resize />` |
| Bare `<select>` | `<Select options={[…]} />` |
| `<input type="checkbox">` + manual label | `<Checkbox label />` |
| Custom `pxswitch` toggle | `<Toggle label checked onChange />` |
| Manual `setStatusMsg(…)` + auto-dismiss effect | `useToast().info(…)` or `window.cafresohqToast.info(…)` |
| Inline-styled tabs (3+ buttons + active class) | `<Tabs value onChange items={…}>` |
| Hand-rolled card divs | `<Card variant header footer>` |
| Per-view keyboard shortcuts | `useCommands([{ id, label, run }, …], deps)` — discoverable via Cmd-K |
| Hardcoded `padding: '8px 12px'` etc. | `var(--sp-4) var(--sp-5)` — automatically scales with density |
| Floating receipts tray + ad-hoc bottom-right widgets | `<NotificationBell>` + `<NotificationCenter>` |
| Single-color palette baked into components | `--paper` / `--ink` / `--accent-*` tokens — auto-respond to `body.theme-*` |
| Bookmarking layouts via screenshot/notes | `Save current state as workspace…` → palette command applies it cleanly |
| `event.dispatchEvent('cafresohq:agentActivity', …)` rendered as one-off pulses | Now also fed automatically into `<NotificationCenter>` and `<AgentInbox>` |

---

## 📝 Changelog

### Session 1 — 2026-05-01

- ✅ Added foundational tokens (spacing, type, radius, shadow, z-index, motion)
- ✅ Night-mode shadow overrides for legibility on dark paper
- ✅ Built `<Modal>` shell with focus trap, scroll lock, animated entry, header/footer slots
- ✅ Migrated 6 modals to the shell: `HireModal`, `SettingsModal`, `WorkflowModal`, `MemoryShelf`, `MeetingRoom`, `StandupModal`, `ReceiptsModal`, `MissionsModal`
- ⏸ `FocusMode` left as a deliberate fullscreen overlay (different visual pattern, not a dialog)
- ✅ Built `<Btn>` component with size variants, loading state, icon slots, full-width option
- ✅ Migrated topbar to `<Btn>` (Memory, Stand-up, Research, Workflow, Night, Stop-all, +Hire)
- ✅ Smoke test passed: app loads, all migrated modals open and Esc-close cleanly, no console errors

### Session 1.5 — Oracle OCA provider (between sessions)

- ✅ Added `OCA_MODELS` and Oracle OCA provider to `claude-client.jsx`
- ✅ Wired `streamOca()` reusing `streamOpenAICompat` with Bearer-key auth
- ✅ Added `oca:` prefix to `parseModelId` and `stream()` dispatcher
- ✅ Added `ocaProbe()` reachability check
- ✅ Surfaced 5 OCA models in the global model picker (gpt-5.5-pro, 5.5, 5.4, 5.3-codex, 4.1)
- ✅ Added `OcaPanel` to Settings → API tab with URL / API key / Model picker / Connection test

### Session 2 — 2026-05-01

- ✅ Built `<Card>` primitive with 5 variants (default / raised / inset / outline / interactive), 3 sizes, optional header/footer slots, selected state
- ✅ Built input primitives: `<TextField>`, `<TextArea>` (with mono variant for code), `<Select>`, `<Checkbox>`, `<Toggle>`, `<SearchField>` — all sharing label/hint/error structure via `<Field>`
- ✅ Universal **focus ring** for all inputs (2px `--accent-sun` outline) — first time the app has had consistent focus styling
- ✅ Built `<Tabs>` + `<Tab>` with 3 variants (default / underline / pill), arrow-key nav, badge support, items-array shorthand
- ✅ Built **toast system** — `<ToastProvider>` + `useToast()` hook + imperative `window.cafresohqToast` escape hatch
- ✅ 5 toast kinds (info/success/warn/error/action) with color-coded left borders, countdown progress bar, auto-dismiss queue (max 3 visible), action buttons
- ✅ Wired `<ToastProvider>` at app root
- ✅ Migrated Vault Graph's local `statusMsg` system to global toasts (kept the existing `setStatusMsg` shape so 24+ call sites didn't need rewrites — adapter delegates to the new toast queue)
- ✅ Smoke test passed: all primitives exposed, toast stack renders correctly with all 3 kinds visible, Hire modal still opens with focus trap intact, Esc still closes

### Session 3 — 2026-05-01

- ✅ Built **global Command Palette** — `<CommandPaletteProvider>` + `useCommands()` hook + `window.cafresohqPalette` escape hatch
- ✅ Cmd/Ctrl-K shortcut from anywhere · arrow-key + Enter run · Esc close · backdrop click closes · auto-grouped sections · fuzzy ranking
- ✅ 23 built-in commands across Navigation / Actions / Toggles / Density / Help sections
- ✅ Added **density modes** — Comfortable (default) / Compact / Spacious — token-multiplier overrides on the body class. Persists. Toggle via palette.
- ✅ Built `<NotificationBell>` + `<NotificationCenter>` — bell icon in topbar with unread badge, slide-in side panel combining approvals + receipts + live agent activity feed + system events. Filter chips. Mark all read. Clear all.
- ✅ Wired the agent-activity event stream and runner-error events into the notification feed (throttled to one entry per node per 4s to prevent flooding)
- ✅ Added **chat history search** — search bar above the chat screen filters across all four sub-threads (Direct / Team / Research / Projects). Match counter. Inline clear.
- ✅ Built `<OnboardingTour>` — multi-step coach marks with optional spotlight ring + auto-anchored card. Default 6-step tour fires on first launch. Replayable via the palette.
- ✅ **Toast hover-pause** — auto-dismiss timer + visual countdown freeze on hover, resume from where they left off when the cursor leaves
- ✅ Smoke test passed: 23 commands registered, palette opens from Cmd-K and via imperative API, density compact verified by computed-style check (`--sp-4: 6px`), notification bell shows unread badge of 56 with correct filter counts, onboarding tour renders STEP 1/6 with progress dots and SKIP/NEXT buttons

### Session 4 — 2026-05-01

- ✅ Added **4 theme variants** — Sepia · Solarized · Dracula · High contrast. Pure CSS class swaps on `body.theme-*` overriding all color/tag tokens. Each ~30 lines.
- ✅ Built **Workspaces** system — built-in (Coding, Research, Standup, Reading) + user-saved layouts. Each workspace captures `{ activeView, railCollapsed, chatWinOpen, density, theme, night }`. Switchable via palette in one diff.
- ✅ **Drag-drop folder → Projects** with visual dashed-outline feedback during dragover. Browser security limits absolute paths — drop suggests folder name, user confirms path. `+ ADD` button mirrors the same flow.
- ✅ Built **`<AgentInbox>`** — live per-agent activity stream in Team view. Filter chips by agent. Click rows to dispatch `cafresohq:openNote`. Toggleable via 📥 INBOX header button or the per-card icon.
- ✅ Implemented **Popout Vault Graph** — `?popout=graph` URL flag triggers a separate React tree in a new window. Two-way sync via `BroadcastChannel('cafresohq-graph')`. Popout-of-popout prevented via `window.opener` check.
- ✅ Smoke test passed: 32 palette commands registered (up from 23) across 7 sections (now including Theme + Workspaces). Dracula applied via palette → `--paper: #282a36`, `--ink: #f8f8f2`. Coding workspace applied → rail collapsed + density compact. `+ ADD`, `📥 INBOX`, `🪟 POP OUT` buttons all confirmed in the rendered DOM.

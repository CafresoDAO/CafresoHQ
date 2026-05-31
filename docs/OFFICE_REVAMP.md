# Office Revamp — "Make it feel like a real Headquarters"

> Goal: keep the **exact same UI, components, and pixel-art identity** — but make
> the office *read* as a living headquarters instead of a flat sprite rack.
> Everything here is additive: new CSS layers + small render tweaks to
> `OfficeView` (ui.jsx:1526). No new dependencies, no token changes.

---

## Design intent

The current office is **5 sprites in fixed slots on a flat floor** + a cork board.
It reads as a "character select" screen, not a workplace. Three changes make it a
headquarters without touching the art:

1. **Depth & zones** — give the room architecture: a back wall, a floor with
   perspective, and named *zones* (Engineering, Research, the CEO corner, a meeting
   nook). A real HQ has *places*, not just people.
2. **Ambient life** — agents breathe, idle-bob, and emit status (typing dots when
   streaming, a "zzz" when idle, a focus ring when assigned a task). The room should
   feel inhabited even when you're not looking.
3. **Status at a glance** — desk nameplates, a wall clock, a "now working on" ticker
   above each busy agent, and a day/night wash tied to the existing `body.night`.

---

## 1. Room architecture (CSS only — drop into styles.css)

```css
/* ── Office: real-HQ depth layer ─────────────────────────────────────────────
   Additive. Wrap the existing OfficeView grid in <div class="hq-room"> and these
   layers render behind the unchanged sprite slots. */
.hq-room {
  position: relative;
  border-radius: var(--radius-4, 14px);
  overflow: hidden;
  /* warm floor with subtle perspective gradient (uses existing brand tokens) */
  background:
    linear-gradient(180deg, var(--paper) 0%, var(--paper) 38%, #f3e7d2 38%, #efe0c8 100%);
  box-shadow: inset 0 1px 0 #fff8, inset 0 -24px 40px -24px #0002;
}
/* back wall: a band with a faint blueprint grid → "operations" feel */
.hq-room::before {
  content: "";
  position: absolute; inset: 0 0 62% 0;
  background-image:
    linear-gradient(#0000 0, #0000 calc(100% - 1px), #00000010 100%),
    linear-gradient(90deg, #0000 0, #0000 calc(100% - 1px), #00000010 100%);
  background-size: 22px 22px;
  opacity: .5;
}
/* floor seam */
.hq-room::after {
  content: ""; position: absolute; left: 0; right: 0; top: 38%;
  height: 2px; background: #0001;
}

/* Zone label chips on the back wall */
.hq-zone {
  position: absolute; top: 8px;
  font: 600 var(--text-10, 10px)/1 'Press Start 2P', monospace;
  letter-spacing: .04em; color: var(--ink-2);
  background: var(--bg); border: 1px solid var(--rule);
  border-radius: var(--radius-pill, 999px);
  padding: 4px 9px; box-shadow: var(--shadow-1);
}

/* Desk under each agent (gives them a workstation, not a void) */
.hq-desk {
  position: absolute; bottom: -6px; left: 50%; transform: translateX(-50%);
  width: 64px; height: 16px;
  background: linear-gradient(180deg, var(--brand-coffee) 0%, #5b4636 100%);
  border-radius: 3px 3px 5px 5px;
  box-shadow: 0 3px 0 #0003, inset 0 1px 0 #fff2;
}
.hq-desk::after {  /* monitor glow on the desk */
  content: ""; position: absolute; top: -7px; left: 50%; transform: translateX(-50%);
  width: 22px; height: 8px; border-radius: 2px;
  background: var(--brand-banana); box-shadow: 0 0 8px 1px var(--brand-banana);
  opacity: .85;
}

/* Nameplate */
.hq-nameplate {
  position: absolute; bottom: -22px; left: 50%; transform: translateX(-50%);
  font: 600 var(--text-9, 9px)/1 'Press Start 2P', monospace;
  color: var(--ink); background: var(--bg);
  border: 1px solid var(--rule); border-radius: var(--radius-2, 4px);
  padding: 3px 6px; white-space: nowrap; box-shadow: var(--shadow-1);
}

/* Wall clock — ambient "this is a workplace" cue */
.hq-clock {
  position: absolute; top: 10px; right: 12px;
  width: 26px; height: 26px; border-radius: 50%;
  background: var(--bg); border: 2px solid var(--brand-coffee);
  box-shadow: var(--shadow-2);
}
.hq-clock i { position: absolute; left: 50%; top: 50%; background: var(--ink);
  transform-origin: bottom center; border-radius: 2px; }
.hq-clock .h { width: 2px; height: 8px; transform: translate(-50%,-100%) rotate(var(--hr,0deg)); }
.hq-clock .m { width: 1px; height: 11px; transform: translate(-50%,-100%) rotate(var(--mn,0deg)); }
```

---

## 2. Ambient life (CSS animations — respect reduced-motion)

```css
@media (prefers-reduced-motion: no-preference) {
  /* gentle idle bob — apply to the sprite wrapper, not the sprite (keeps art crisp) */
  .hq-agent { animation: hq-bob 4.5s ease-in-out infinite; }
  .hq-agent[data-status="idle"]   { animation-duration: 6s; opacity: .92; }
  .hq-agent[data-status="working"]{ animation-duration: 2.4s; }
  @keyframes hq-bob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-2px); } }

  /* typing dots above a streaming agent */
  .hq-typing i { animation: hq-blink 1s steps(3,end) infinite; }
  @keyframes hq-blink { 0% { opacity:.2 } 50% { opacity:1 } 100% { opacity:.2 } }
}

/* status ring under a working agent (color-blind safe: ring + icon, not color alone) */
.hq-agent[data-status="working"] .hq-ring {
  box-shadow: 0 0 0 2px var(--brand-banana), 0 0 10px 2px #f5c84266;
}

/* "now working on" caption that fades in only when busy */
.hq-now {
  position: absolute; top: -16px; left: 50%; transform: translateX(-50%);
  max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font: var(--text-9,9px)/1.2 'Inter', sans-serif; color: var(--ink-2);
  background: var(--bg); border: 1px solid var(--rule);
  border-radius: var(--radius-pill,999px); padding: 2px 7px;
  box-shadow: var(--shadow-1); opacity: 0; transition: opacity var(--motion-base,200ms);
}
.hq-agent[data-status="working"] .hq-now { opacity: 1; }

/* idle "zzz" */
.hq-agent[data-status="idle"] .hq-zzz { opacity:.6; }
.hq-agent .hq-zzz { opacity:0; position:absolute; top:-10px; right:8px;
  font:var(--text-10,10px) monospace; color: var(--ink-3);
  transition: opacity var(--motion-base,200ms); }
```

---

## 3. Minimal `OfficeView` render changes (ui.jsx ~line 1526)

Keep every existing prop and click handler. Wrap and annotate — no behavior change:

```jsx
// BEFORE: agents map straight into fixed slots on a flat div.
// AFTER: same slots, wrapped in the room + per-agent HQ chrome.

function OfficeView({ agents, onHire, onAgentClick, onInspect, stickies, tasks, maxSlots = 5 }) {
  const ZONES = ['ENGINEERING', 'RESEARCH', 'CEO CORNER', 'MEETING', 'OPS']; // labels only
  const statusOf = (a) =>
    a.streaming ? 'working' : (a.activeTaskId ? 'assigned' : 'idle');
  const nowText = (a) => {
    const t = tasks?.find(t => t.id === a.activeTaskId);
    return t ? t.title : '';
  };
  const clock = hqClockAngles(); // {hr, mn} from new Date(); pure helper below

  return (
    <div className="hq-room" style={{ minHeight: 220 }}>
      {/* wall clock */}
      <div className="hq-clock" style={{ '--hr': clock.hr + 'deg', '--mn': clock.mn + 'deg' }}>
        <i className="h" /><i className="m" />
      </div>

      {/* zone chips spaced across the back wall */}
      {agents.slice(0, maxSlots).map((a, i) => (
        <span key={'z'+i} className="hq-zone" style={{ left: zoneX(i, maxSlots) }}>
          {ZONES[i] || 'TEAM'}
        </span>
      ))}

      {/* existing slot grid — UNCHANGED layout math, now each cell gets HQ chrome */}
      <div className="office-grid">{/* ← keep the current grid container */}
        {agents.slice(0, maxSlots).map((a, i) => (
          <div
            key={a.id}
            className="hq-agent"
            data-status={statusOf(a)}
            onClick={() => onAgentClick?.(a)}
            role="button" tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onAgentClick?.(a)}
            aria-label={`${a.name}, ${statusOf(a)}${nowText(a) ? ', working on ' + nowText(a) : ''}`}
          >
            {nowText(a) && <div className="hq-now">{nowText(a)}</div>}
            <div className="hq-zzz">z z</div>
            {statusOf(a) === 'working' && (
              <div className="hq-typing"><i>•</i><i>•</i><i>•</i></div>
            )}
            <div className="hq-ring">
              {/* EXISTING sprite render — unchanged */}
              <Sprite data={a.sprite || a.color || 'rose'} scale={3} />
            </div>
            <div className="hq-desk" />
            <div className="hq-nameplate">{a.name}</div>
          </div>
        ))}

        {/* keep the existing "hire" empty-slot + cork board exactly as-is */}
        {agents.length < maxSlots && <HireSlot onHire={onHire} />}
      </div>

      {/* existing cork board / stickies render — UNCHANGED */}
      <CorkBoard stickies={stickies} />
    </div>
  );
}

// pure helpers (add near OfficeView)
function hqClockAngles() {
  const d = new Date();
  return { hr: (d.getHours() % 12) * 30 + d.getMinutes() * 0.5, mn: d.getMinutes() * 6 };
}
function zoneX(i, n) { return `calc(${(i + 0.5) * (100 / n)}% - 28px)`; }
```

> Every existing handler (`onAgentClick`, `onInspect`, `onHire`), the `Sprite`
> component, the cork board, and the slot math are preserved. The revamp is the
> `hq-*` wrapper layers + status annotations.

---

## 4. Day/night + "open for business" polish

- Tie the floor wash to the existing `body.night` (already in styles.css) — add a
  `.hq-room` night override (cooler floor, warmer desk monitor glow) so the HQ
  visibly "settles" in the evening.
- When **any** agent is `working`, show a tiny `● LIVE` pip by the wall clock
  (reuses the Ticker's existing live-dot style) — the room signals activity.
- Empty state: instead of a bare floor, render a single "Reception" desk + a
  "Hire your first agent" call-to-action on the nameplate — the HQ is open even
  before you staff it.

---

## 5. Why this works (and stays safe)

- **Same UI**: no component renamed, no prop removed, no token added. A designer
  reviewing the diff sees only additive `hq-*` classes + status wrappers.
- **Same performance budget**: pure CSS transforms/animations (GPU-friendly),
  gated behind `prefers-reduced-motion`. No new JS loop, no canvas.
- **Accessibility improved, not regressed**: slots become real keyboard-focusable
  buttons with `aria-label` status (fixes the review's a11y finding M5), and status
  is conveyed by ring+icon+text, not color alone.
- **Incremental**: ship the CSS first (instant depth), then the `OfficeView`
  wrapper, then day/night. Each step is independently revertable.
```

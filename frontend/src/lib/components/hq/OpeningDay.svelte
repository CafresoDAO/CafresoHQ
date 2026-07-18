<script>
  /* OpeningDay — the cold-start checklist as a pixel "office opening day".
     Pure visual skin over the SAME four launchSteps reactives the old <ol>
     rendered (signin / container / session / open) — no state of its own.
     Scenes: badge scan → elevator ride → key turn → lights on.
     Any step in 'error' shows the "lights won't turn on" treatment; the
     actionable recovery cards below this component stay unchanged. */
  export let steps = [];

  const SCENES = {
    signin:    { icon: '🪪', doing: 'Scanning your badge…',        did: 'Badge accepted' },
    container: { icon: '🛗', doing: 'Elevator heading up…',        did: 'Arrived at your floor' },
    session:   { icon: '🔑', doing: 'Turning the key…',            did: 'Door unlocked' },
    open:      { icon: '💡', doing: 'Lights coming on…',           did: 'Office open' }
  };

  $: active = steps.find((s) => s.state === 'active');
  $: errored = steps.find((s) => s.state === 'error');
  $: doneCount = steps.filter((s) => s.state === 'done').length;
  $: caption = errored
    ? 'The lights won’t turn on — details below.'
    : active
      ? (SCENES[active.id]?.doing || active.label)
      : doneCount === steps.length && steps.length > 0
        ? 'Doors opening…'
        : 'Waiting at the lobby…';
</script>

<div class="od" class:od-error={!!errored} role="list" aria-label="Office launch progress">
  <div class="od-building" aria-hidden="true">
    {#each steps as s, i}
      {@const scene = SCENES[s.id] || { icon: '·' }}
      <div class="od-floor {s.state}" role="listitem" aria-label="{s.label}: {s.state}">
        <div class="od-window">
          <span class="od-icon">{s.state === 'error' ? '⚠' : scene.icon}</span>
        </div>
        <div class="od-label">{s.label}</div>
        {#if i < steps.length - 1}
          <div class="od-wire {s.state === 'done' ? 'lit' : ''}"></div>
        {/if}
      </div>
    {/each}
  </div>
  <p class="od-caption" aria-live="polite">
    {caption}
  </p>
</div>

<style>
  .od {
    margin-top: 1.25rem;
  }
  .od-building {
    display: flex;
    align-items: stretch;
    gap: 0;
  }
  .od-floor {
    position: relative;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 4px 6px 0;
  }
  .od-window {
    width: 52px;
    height: 44px;
    display: grid;
    place-items: center;
    border-radius: 8px;
    border: 2px solid hsl(var(--ink-600) / 0.6);
    background: hsl(240 12% 12%);          /* dark office before the lights */
    font-size: 20px;
    filter: grayscale(0.9) brightness(0.55);
    transition: background 0.4s, filter 0.4s, border-color 0.4s, box-shadow 0.4s;
  }
  .od-floor.active .od-window {
    filter: grayscale(0.2) brightness(0.95);
    border-color: hsl(38 80% 55% / 0.8);
    animation: od-warm 1.4s ease-in-out infinite;
  }
  .od-floor.done .od-window {
    background: linear-gradient(180deg, hsl(44 90% 80%), hsl(38 85% 64%));
    border-color: hsl(32 72% 45%);
    filter: none;
    box-shadow: 0 0 14px -2px hsl(44 90% 60% / 0.55);
  }
  .od-floor.error .od-window {
    background: hsl(4 40% 14%);
    border-color: hsl(4 72% 50%);
    filter: none;
    animation: od-flicker 1.1s steps(2) infinite;
  }
  .od-label {
    font-size: 11px;
    line-height: 1.3;
    text-align: center;
    color: hsl(var(--ink-400));
    max-width: 12ch;
  }
  .od-floor.active .od-label { color: hsl(var(--ink-200)); font-weight: 600; }
  .od-floor.done .od-label { color: hsl(var(--ink-300)); }
  .od-floor.error .od-label { color: hsl(4 72% 50%); font-weight: 600; }
  /* wire between floors — lights along it once the floor is done */
  .od-wire {
    position: absolute;
    top: 22px;
    left: calc(50% + 30px);
    width: calc(100% - 60px);
    height: 2px;
    background: hsl(var(--ink-600) / 0.5);
  }
  .od-wire.lit {
    background: linear-gradient(90deg, hsl(38 85% 60%), hsl(44 90% 70%));
    box-shadow: 0 0 6px hsl(44 90% 60% / 0.6);
  }
  .od-caption {
    margin: 14px 0 0;
    font-size: 13px;
    color: hsl(var(--ink-300));
  }
  .od-error .od-caption { color: hsl(4 72% 50%); }

  @keyframes od-warm {
    0%, 100% { box-shadow: 0 0 4px -1px hsl(44 90% 60% / 0.25); }
    50%      { box-shadow: 0 0 16px -2px hsl(44 90% 60% / 0.6); }
  }
  @keyframes od-flicker {
    0%, 100% { filter: brightness(1); }
    50%      { filter: brightness(0.55); }
  }

  @media (prefers-reduced-motion: reduce) {
    .od-window, .od-floor.active .od-window, .od-floor.error .od-window {
      animation: none !important;
      transition: none;
    }
  }
</style>

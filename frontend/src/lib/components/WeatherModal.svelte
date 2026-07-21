<script>
  /* Weather dapp popup — opened by the cloud button in PageHeader.
     Live data comes straight from Open-Meteo (no container needed), the same
     provider serve.py's weather-archive cron records hourly, so the saved
     regions here are exactly the ones the Search Network is archiving. */
  import Modal from './Modal.svelte';
  import Icon from './Icon.svelte';
  import { weatherOpen } from '$lib/stores/weather.js';
  import {
    SAVED_LOCATIONS, fetchForecast, fetchSavedCurrent, geocode,
    wmoText, wmoIcon, wmoScene
  } from '$lib/api/weather.js';

  const UNIT_KEY = 'cafreso.weather.unit';

  // Deterministic particle layouts (rain / snow / stars) — index-derived so
  // the scene renders identically every open, no per-frame JS.
  const DROPS = Array.from({ length: 16 }, (_, i) => ({
    left: (i * 61) % 97 + 1.5,
    delay: ((i * 37) % 90) / 100,
    dur: 0.75 + ((i * 23) % 40) / 100
  }));
  const FLAKES = Array.from({ length: 14 }, (_, i) => ({
    left: (i * 67) % 95 + 2,
    delay: ((i * 53) % 240) / 100,
    dur: 3.4 + ((i * 31) % 25) / 10,
    size: 3 + (i % 3) * 1.5
  }));
  const STARS = Array.from({ length: 18 }, (_, i) => ({
    left: (i * 47) % 96 + 2,
    top: (i * 29) % 55 + 4,
    delay: ((i * 41) % 300) / 100,
    size: 1.5 + (i % 3)
  }));

  const REGIONS = ['Mid-Atlantic', 'Northern Virginia', 'El Salvador'];

  let sel = $state(null);          // {label, lat, lon, key?} — place being shown
  let fc = $state(null);           // Open-Meteo forecast payload
  let fcErr = $state(null);
  let fcLoading = $state(false);
  let saved = $state({});          // key → {tempF, code, isDay} for region chips
  let geoDenied = $state(false);   // geolocation failed → nudge toward search

  let q = $state('');
  let results = $state([]);
  let searching = $state(false);
  let searchErr = $state(null);
  let searchTimer = null;
  let initialized = false;

  let unit = $state('F');
  if (typeof window !== 'undefined') {
    try { unit = localStorage.getItem(UNIT_KEY) === 'C' ? 'C' : 'F'; } catch {}
  }
  function toggleUnit() {
    unit = unit === 'F' ? 'C' : 'F';
    try { localStorage.setItem(UNIT_KEY, unit); } catch {}
  }
  function T(f) {
    if (f == null) return '—';
    return Math.round(unit === 'C' ? (f - 32) * 5 / 9 : f);
  }
  function wind(mph) {
    if (mph == null) return '—';
    return unit === 'C' ? `${Math.round(mph * 1.609)} km/h` : `${Math.round(mph)} mph`;
  }

  const cur = $derived(fc?.current ?? null);
  const scene = $derived(cur ? wmoScene(cur.weather_code, cur.is_day) : 'cloudy');

  // Next 12 hours starting from the location's current local hour. Open-Meteo
  // returns hourly.time as *location-local* ISO strings ("2026-07-21T15:00"),
  // so slice by matching the current-time prefix, never via Date/UTC math.
  const hours = $derived.by(() => {
    if (!fc?.hourly?.time || !cur?.time) return [];
    const nowPrefix = cur.time.slice(0, 13);              // "2026-07-21T15"
    let start = fc.hourly.time.findIndex((t) => t.slice(0, 13) >= nowPrefix);
    if (start < 0) start = 0;
    return fc.hourly.time.slice(start, start + 12).map((t, j) => {
      const i = start + j;
      const h = parseInt(t.slice(11, 13), 10);
      return {
        label: j === 0 ? 'Now' : (h === 0 ? '12a' : h < 12 ? `${h}a` : h === 12 ? '12p' : `${h - 12}p`),
        tempF: fc.hourly.temperature_2m?.[i],
        code: fc.hourly.weather_code?.[i],
        isDay: fc.hourly.is_day?.[i],
        pop: fc.hourly.precipitation_probability?.[i]
      };
    });
  });

  const days = $derived.by(() => {
    if (!fc?.daily?.time) return [];
    const lo = Math.min(...(fc.daily.temperature_2m_min || [0]));
    const hi = Math.max(...(fc.daily.temperature_2m_max || [1]));
    const span = Math.max(1, hi - lo);
    return fc.daily.time.map((d, i) => {
      const [y, m, dd] = d.split('-').map(Number);
      const min = fc.daily.temperature_2m_min?.[i];
      const max = fc.daily.temperature_2m_max?.[i];
      return {
        label: i === 0 ? 'Today'
          : new Date(y, m - 1, dd).toLocaleDateString(undefined, { weekday: 'short' }),
        code: fc.daily.weather_code?.[i],
        min, max,
        pop: fc.daily.precipitation_probability_max?.[i],
        // range-bar geometry, % of the week's full min→max spread
        barLeft: ((min - lo) / span) * 100,
        barWidth: Math.max(4, ((max - min) / span) * 100)
      };
    });
  });

  async function show(place) {
    sel = place;
    fcErr = null;
    fcLoading = true;
    try {
      fc = await fetchForecast(place.lat, place.lon);
    } catch (e) {
      fc = null;
      fcErr = String(e?.message || e);
    } finally {
      fcLoading = false;
    }
  }

  function init() {
    if (initialized) return;
    initialized = true;
    fetchSavedCurrent().then((s) => { saved = s; }).catch(() => {});
    // Try the visitor's own location first; fall back to DC and let them
    // search / pick a saved region instead.
    const fallback = () => {
      geoDenied = true;
      show(SAVED_LOCATIONS[0]);
    };
    if (typeof navigator !== 'undefined' && navigator.geolocation) {
      let settled = false;
      const t = setTimeout(() => { if (!settled) { settled = true; fallback(); } }, 4000);
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          if (settled) return;
          settled = true; clearTimeout(t);
          show({ label: 'Your location', lat: +pos.coords.latitude.toFixed(4), lon: +pos.coords.longitude.toFixed(4) });
        },
        () => { if (!settled) { settled = true; clearTimeout(t); fallback(); } },
        { timeout: 3500, maximumAge: 600000 }
      );
    } else fallback();
  }

  $effect(() => {
    if ($weatherOpen) init();
  });

  function onSearchInput() {
    clearTimeout(searchTimer);
    searchErr = null;
    if (q.trim().length < 2) { results = []; searching = false; return; }
    searching = true;
    searchTimer = setTimeout(async () => {
      const query = q;
      try {
        const r = await geocode(query);
        if (query === q) { results = r; searching = false; }
      } catch (e) {
        if (query === q) { searchErr = 'Search failed — try again'; searching = false; }
      }
    }, 350);
  }
  function pickResult(r) {
    results = [];
    q = '';
    show(r);
  }

  function close() { weatherOpen.set(false); }

  const savedByRegion = $derived(
    REGIONS.map((r) => ({ region: r, locs: SAVED_LOCATIONS.filter((l) => l.region === r) }))
  );
</script>

<Modal
  open={$weatherOpen}
  on:close={close}
  labelledby="weather-title"
  placement="center"
  z="modal"
  panelClass="weather-panel"
  panelStyle="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));"
>
  <!-- Header -->
  <div class="wx-head">
    <h2 id="weather-title" class="wx-title">
      <Icon name="cloud-sun" size={20} />
      Weather
    </h2>
    <div class="wx-head-actions">
      <button type="button" class="wx-unit" on:click={toggleUnit} title="Switch temperature unit">
        <span class:on={unit === 'F'}>°F</span><span class="wx-unit-sep">/</span><span class:on={unit === 'C'}>°C</span>
      </button>
      <button type="button" class="wx-close" on:click={close} aria-label="Close weather" data-autofocus>
        <Icon name="x" size={18} />
      </button>
    </div>
  </div>

  <!-- Search -->
  <div class="wx-search">
    <span class="wx-search-icon"><Icon name="magnifying-glass" size={16} /></span>
    <input
      type="search"
      placeholder={geoDenied ? "Your location didn't load — search any place…" : 'Search any city or place…'}
      bind:value={q}
      on:input={onSearchInput}
      aria-label="Search a place"
    />
    {#if searching}<span class="wx-spin" aria-hidden="true"></span>{/if}
    {#if results.length}
      <ul class="wx-results" role="listbox">
        {#each results as r}
          <li>
            <button type="button" on:click={() => pickResult(r)}>
              <Icon name="map-pin" size={14} />
              {r.label}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
  {#if searchErr}<p class="wx-err">{searchErr}</p>{/if}

  <div class="wx-scroll">
    <!-- Hero scene -->
    <div class="wx-hero wx-scene-{fcLoading ? 'loading' : scene}">
      {#if fcLoading}
        <div class="wx-hero-loading">
          <span class="wx-spin big" aria-hidden="true"></span>
          <span>Reading the sky…</span>
        </div>
      {:else if fcErr}
        <div class="wx-hero-loading">
          <Icon name="cloud-slash" size={28} />
          <span>Couldn't load the forecast ({fcErr}).</span>
          {#if sel}<button type="button" class="wx-retry" on:click={() => show(sel)}>Retry</button>{/if}
        </div>
      {:else if cur}
        <!-- animated layers -->
        {#if scene === 'clear-day' || scene === 'partly-day'}
          <div class="wx-sun" class:small={scene === 'partly-day'}><div class="wx-rays"></div></div>
        {/if}
        {#if scene === 'clear-night' || scene === 'partly-night'}
          <div class="wx-moon"></div>
          {#each STARS as s}
            <span class="wx-star" style="left:{s.left}%; top:{s.top}%; width:{s.size}px; height:{s.size}px; animation-delay:{s.delay}s;"></span>
          {/each}
        {/if}
        {#if scene !== 'clear-day' && scene !== 'clear-night'}
          <div class="wx-cloud c1"></div>
          <div class="wx-cloud c2"></div>
          <div class="wx-cloud c3"></div>
        {/if}
        {#if scene === 'rain' || scene === 'storm'}
          {#each DROPS as d}
            <span class="wx-drop" style="left:{d.left}%; animation-delay:{d.delay}s; animation-duration:{d.dur}s;"></span>
          {/each}
        {/if}
        {#if scene === 'snow'}
          {#each FLAKES as f}
            <span class="wx-flake" style="left:{f.left}%; width:{f.size}px; height:{f.size}px; animation-delay:{f.delay}s; animation-duration:{f.dur}s;"></span>
          {/each}
        {/if}
        {#if scene === 'storm'}<div class="wx-flash"></div>{/if}
        {#if scene === 'fog'}
          <div class="wx-fog f1"></div>
          <div class="wx-fog f2"></div>
        {/if}

        <div class="wx-hero-content">
          <div class="wx-place">
            <Icon name="map-pin" size={14} weight="fill" />
            {sel?.label ?? '—'}
          </div>
          <div class="wx-now">
            <span class="wx-temp">{T(cur.temperature_2m)}°</span>
            <div class="wx-now-side">
              <span class="wx-cond">{wmoText(cur.weather_code)}</span>
              <span class="wx-feels">Feels like {T(cur.apparent_temperature)}°</span>
            </div>
          </div>
        </div>
      {/if}
    </div>

    {#if cur && !fcLoading}
      <!-- Details -->
      <div class="wx-stats">
        <div class="wx-stat"><Icon name="drop" size={15} /><span>{cur.relative_humidity_2m ?? '—'}%</span><small>Humidity</small></div>
        <div class="wx-stat"><Icon name="wind" size={15} /><span>{wind(cur.wind_speed_10m)}</span><small>Wind</small></div>
        <div class="wx-stat"><Icon name="cloud-rain" size={15} /><span>{cur.precipitation ?? 0} mm</span><small>Precip</small></div>
        <div class="wx-stat"><Icon name="gauge" size={15} /><span>{cur.surface_pressure ? Math.round(cur.surface_pressure) : '—'}</span><small>hPa</small></div>
      </div>

      <!-- Hourly strip -->
      {#if hours.length}
        <div class="wx-section-label">Next hours</div>
        <div class="wx-hours">
          {#each hours as h}
            <div class="wx-hour">
              <span class="wx-hour-t">{h.label}</span>
              <Icon name={wmoIcon(h.code, h.isDay)} size={18} />
              <span class="wx-hour-temp">{T(h.tempF)}°</span>
              {#if h.pop >= 20}<span class="wx-hour-pop">{h.pop}%</span>{/if}
            </div>
          {/each}
        </div>
      {/if}

      <!-- 7-day -->
      {#if days.length}
        <div class="wx-section-label">7-day forecast</div>
        <div class="wx-days">
          {#each days as d}
            <div class="wx-day">
              <span class="wx-day-name">{d.label}</span>
              <span class="wx-day-icon"><Icon name={wmoIcon(d.code, 1)} size={17} /></span>
              <span class="wx-day-pop">{d.pop >= 20 ? `${d.pop}%` : ''}</span>
              <span class="wx-day-min">{T(d.min)}°</span>
              <div class="wx-day-bar"><div class="wx-day-fill" style="left:{d.barLeft}%; width:{d.barWidth}%;"></div></div>
              <span class="wx-day-max">{T(d.max)}°</span>
            </div>
          {/each}
        </div>
      {/if}
    {/if}

    <!-- Saved regions the Search Network archives hourly -->
    <div class="wx-section-label wx-saved-head">
      <span>Archived regions</span>
      <small>recorded hourly by the Search Network</small>
    </div>
    {#each savedByRegion as g}
      <div class="wx-region">{g.region}</div>
      <div class="wx-chips">
        {#each g.locs as l}
          <button
            type="button"
            class="wx-chip"
            class:active={sel?.key === l.key}
            on:click={() => show(l)}
          >
            {#if saved[l.key]}
              <Icon name={wmoIcon(saved[l.key].code, saved[l.key].isDay)} size={14} />
            {:else}
              <Icon name="map-pin" size={14} />
            {/if}
            <span>{l.label}</span>
            {#if saved[l.key]}<b>{T(saved[l.key].tempF)}°</b>{/if}
          </button>
        {/each}
      </div>
    {/each}

    <p class="wx-foot">Live data by Open-Meteo · archived hourly on the Cafreso Search Network</p>
  </div>
</Modal>

<style>
  :global(.weather-panel) {
    width: min(680px, calc(100vw - 32px));
    max-height: min(86vh, 780px);
    border-radius: 22px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 24px 60px -18px hsl(222 47% 11% / 0.55);
    animation: wx-pop 0.28s cubic-bezier(0.2, 0.9, 0.3, 1.15);
  }
  @keyframes wx-pop {
    from { opacity: 0; transform: translateY(14px) scale(0.97); }
    to   { opacity: 1; transform: none; }
  }

  /* ── header ── */
  .wx-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px 10px;
  }
  .wx-title {
    display: inline-flex; align-items: center; gap: 8px;
    margin: 0; font-size: 16px; font-weight: 700;
    color: hsl(var(--pg-fg));
  }
  .wx-head-actions { display: inline-flex; align-items: center; gap: 6px; }
  .wx-unit {
    border: 1px solid hsl(var(--pg-border)); background: transparent;
    border-radius: 999px; padding: 4px 10px; cursor: pointer;
    font-size: 12px; color: hsl(var(--pg-fg-muted));
    transition: background 0.2s;
  }
  .wx-unit:hover { background: hsl(var(--pg-hover) / 0.7); }
  .wx-unit .on { color: hsl(var(--pg-fg)); font-weight: 700; }
  .wx-unit-sep { margin: 0 3px; opacity: 0.5; }
  .wx-close {
    width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center;
    border: none; background: transparent; border-radius: 9px; cursor: pointer;
    color: hsl(var(--pg-fg-muted)); transition: background 0.2s, color 0.2s;
  }
  .wx-close:hover { background: hsl(var(--pg-hover) / 0.7); color: hsl(var(--pg-fg)); }

  /* ── search ── */
  .wx-search { position: relative; margin: 0 16px 4px; }
  .wx-search-icon {
    position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
    color: hsl(var(--pg-fg-muted)); pointer-events: none; display: inline-flex;
  }
  .wx-search input {
    width: 100%; box-sizing: border-box;
    padding: 10px 36px 10px 36px;
    border-radius: 12px; border: 1px solid hsl(var(--pg-border));
    background: hsl(var(--pg-elevated)); color: hsl(var(--pg-fg));
    font-size: 14px; outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .wx-search input:focus {
    border-color: hsl(var(--pg-accent-purple));
    box-shadow: 0 0 0 3px hsl(var(--pg-accent-purple) / 0.18);
  }
  .wx-results {
    position: absolute; left: 0; right: 0; top: calc(100% + 6px); z-index: 5;
    margin: 0; padding: 6px; list-style: none;
    background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));
    border-radius: 12px; box-shadow: 0 14px 34px -12px hsl(222 47% 11% / 0.4);
    animation: wx-pop 0.18s ease;
  }
  .wx-results button {
    width: 100%; display: flex; align-items: center; gap: 8px; text-align: left;
    padding: 8px 10px; border: none; background: transparent; border-radius: 8px;
    cursor: pointer; font-size: 13px; color: hsl(var(--pg-fg));
    transition: background 0.15s;
  }
  .wx-results button:hover { background: hsl(var(--pg-hover)); }
  .wx-err { margin: 4px 18px; font-size: 12px; color: hsl(var(--pg-danger-fg, 0 70% 50%)); }

  .wx-spin {
    position: absolute; right: 12px; top: 50%; margin-top: -7px;
    width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid hsl(var(--pg-fg-muted) / 0.3);
    border-top-color: hsl(var(--pg-fg-muted));
    animation: wx-rot 0.8s linear infinite;
  }
  .wx-spin.big {
    position: static; margin: 0; width: 22px; height: 22px;
    border-color: hsl(0 0% 100% / 0.3); border-top-color: #fff;
  }
  @keyframes wx-rot { to { transform: rotate(360deg); } }

  .wx-scroll { overflow-y: auto; padding: 10px 16px 14px; }

  /* ── hero scene ── */
  .wx-hero {
    position: relative; overflow: hidden;
    border-radius: 18px; min-height: 172px;
    display: flex; align-items: flex-end;
    color: #fff;
    transition: background 0.6s ease;
  }
  .wx-scene-loading   { background: linear-gradient(180deg, #5d6b85, #8894ab); }
  .wx-scene-clear-day { background: linear-gradient(180deg, #2f86d4 0%, #6db8ef 60%, #a8d8f7 100%); }
  .wx-scene-partly-day{ background: linear-gradient(180deg, #3d8ed2 0%, #7fb9e6 65%, #b6d7ee 100%); }
  .wx-scene-clear-night, .wx-scene-partly-night
                      { background: linear-gradient(180deg, #0b1030 0%, #1c2452 60%, #32406e 100%); }
  .wx-scene-cloudy    { background: linear-gradient(180deg, #5d6b85 0%, #8894ab 70%, #a9b3c6 100%); }
  .wx-scene-rain      { background: linear-gradient(180deg, #37455e 0%, #56688a 70%, #6f81a3 100%); }
  .wx-scene-snow      { background: linear-gradient(180deg, #7d8ba6 0%, #a8b4cb 60%, #cfd7e6 100%); }
  .wx-scene-storm     { background: linear-gradient(180deg, #1d2436 0%, #333f5c 70%, #47547a 100%); }
  .wx-scene-fog       { background: linear-gradient(180deg, #8b93a5 0%, #adb4c2 60%, #c8cdd8 100%); }

  .wx-hero-loading {
    width: 100%; min-height: 172px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 10px; font-size: 13px; color: hsl(0 0% 100% / 0.9);
  }
  .wx-retry {
    border: 1px solid hsl(0 0% 100% / 0.5); background: hsl(0 0% 100% / 0.12);
    color: #fff; border-radius: 999px; padding: 4px 14px; font-size: 12px; cursor: pointer;
  }

  .wx-sun {
    position: absolute; top: 18px; right: 26px; width: 52px; height: 52px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #ffe9a8, #ffc93d 70%);
    box-shadow: 0 0 34px 10px hsl(45 100% 62% / 0.55);
    animation: wx-breathe 4.5s ease-in-out infinite;
  }
  .wx-sun.small { width: 40px; height: 40px; top: 14px; right: 22%; }
  .wx-rays {
    position: absolute; inset: -16px; border-radius: 50%;
    background:
      repeating-conic-gradient(hsl(45 100% 70% / 0.35) 0deg 6deg, transparent 6deg 30deg);
    animation: wx-rot 26s linear infinite;
  }
  @keyframes wx-breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.06); }
  }

  .wx-moon {
    position: absolute; top: 18px; right: 30px; width: 42px; height: 42px;
    border-radius: 50%;
    background: radial-gradient(circle at 62% 38%, #fdfbf1, #d9d9c8 75%);
    box-shadow: 0 0 26px 6px hsl(50 40% 90% / 0.35), inset -8px -6px 0 hsl(50 15% 72% / 0.55);
    animation: wx-breathe 6s ease-in-out infinite;
  }
  .wx-star {
    position: absolute; border-radius: 50%; background: #fff;
    animation: wx-twinkle 2.6s ease-in-out infinite;
  }
  @keyframes wx-twinkle {
    0%, 100% { opacity: 0.25; }
    50% { opacity: 1; }
  }

  .wx-cloud {
    position: absolute; height: 22px; border-radius: 999px;
    background: hsl(0 0% 100% / 0.75);
    filter: blur(1px);
    box-shadow: 14px -9px 0 2px hsl(0 0% 100% / 0.65), -14px -6px 0 hsl(0 0% 100% / 0.55);
  }
  .wx-cloud.c1 { width: 74px; top: 30px; animation: wx-drift 26s linear infinite; }
  .wx-cloud.c2 { width: 52px; top: 66px; opacity: 0.8; animation: wx-drift 36s linear infinite; animation-delay: -14s; }
  .wx-cloud.c3 { width: 92px; top: 14px; opacity: 0.62; animation: wx-drift 44s linear infinite; animation-delay: -28s; }
  .wx-scene-storm .wx-cloud, .wx-scene-rain .wx-cloud { background: hsl(220 15% 82% / 0.8); box-shadow: 14px -9px 0 2px hsl(220 15% 82% / 0.7), -14px -6px 0 hsl(220 15% 82% / 0.55); }
  @keyframes wx-drift {
    from { transform: translateX(-140px); }
    to   { transform: translateX(760px); }
  }

  .wx-drop {
    position: absolute; top: -14px; width: 1.5px; height: 12px;
    border-radius: 2px; background: hsl(200 80% 88% / 0.75);
    animation: wx-fall linear infinite;
  }
  @keyframes wx-fall {
    from { transform: translateY(0); opacity: 0.9; }
    to   { transform: translateY(210px); opacity: 0.15; }
  }

  .wx-flake {
    position: absolute; top: -8px; border-radius: 50%;
    background: hsl(0 0% 100% / 0.9);
    animation: wx-snowfall linear infinite;
  }
  @keyframes wx-snowfall {
    0%   { transform: translate(0, 0); opacity: 0.95; }
    50%  { transform: translate(10px, 105px); }
    100% { transform: translate(-6px, 210px); opacity: 0.2; }
  }

  .wx-flash {
    position: absolute; inset: 0; background: #fff; opacity: 0; pointer-events: none;
    animation: wx-lightning 6s ease-in-out infinite;
  }
  @keyframes wx-lightning {
    0%, 91%, 95%, 100% { opacity: 0; }
    92% { opacity: 0.55; }
    93% { opacity: 0.08; }
    94% { opacity: 0.4; }
  }

  .wx-fog {
    position: absolute; left: -20%; right: -20%; height: 34px; border-radius: 999px;
    background: hsl(0 0% 100% / 0.4); filter: blur(8px);
  }
  .wx-fog.f1 { top: 46px; animation: wx-fogdrift 14s ease-in-out infinite alternate; }
  .wx-fog.f2 { top: 96px; animation: wx-fogdrift 18s ease-in-out infinite alternate-reverse; }
  @keyframes wx-fogdrift {
    from { transform: translateX(-4%); }
    to   { transform: translateX(4%); }
  }

  .wx-hero-content {
    position: relative; z-index: 2; width: 100%;
    padding: 18px;
    text-shadow: 0 1px 8px hsl(222 47% 11% / 0.35);
  }
  .wx-place {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 13px; font-weight: 600; opacity: 0.95;
  }
  .wx-now { display: flex; align-items: center; gap: 14px; margin-top: 2px; }
  .wx-temp { font-size: 54px; font-weight: 800; line-height: 1; letter-spacing: -2px; }
  .wx-now-side { display: flex; flex-direction: column; gap: 2px; }
  .wx-cond { font-size: 15px; font-weight: 700; }
  .wx-feels { font-size: 12px; opacity: 0.85; }

  /* ── stats ── */
  .wx-stats {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
    margin-top: 10px;
  }
  .wx-stat {
    display: flex; flex-direction: column; align-items: center; gap: 2px;
    padding: 10px 6px; border-radius: 14px;
    background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));
    color: hsl(var(--pg-fg));
  }
  .wx-stat span { font-size: 13px; font-weight: 700; }
  .wx-stat small { font-size: 10px; color: hsl(var(--pg-fg-muted)); text-transform: uppercase; letter-spacing: 0.04em; }

  .wx-section-label {
    margin: 16px 2px 8px;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
    color: hsl(var(--pg-fg-muted));
  }

  /* ── hourly ── */
  .wx-hours {
    display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px;
    scrollbar-width: thin;
  }
  .wx-hour {
    flex: 0 0 auto; min-width: 52px;
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    padding: 10px 6px; border-radius: 14px;
    background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));
    color: hsl(var(--pg-fg));
  }
  .wx-hour-t { font-size: 11px; color: hsl(var(--pg-fg-muted)); }
  .wx-hour-temp { font-size: 13px; font-weight: 700; }
  .wx-hour-pop { font-size: 10px; color: hsl(205 80% 55%); font-weight: 600; }

  /* ── 7-day ── */
  .wx-days { display: flex; flex-direction: column; }
  .wx-day {
    display: grid;
    grid-template-columns: 46px 26px 34px 34px 1fr 34px;
    align-items: center; gap: 8px;
    padding: 7px 4px;
    border-top: 1px solid hsl(var(--pg-border) / 0.6);
    color: hsl(var(--pg-fg)); font-size: 13px;
  }
  .wx-day:first-child { border-top: none; }
  .wx-day-name { font-weight: 600; }
  .wx-day-icon { display: inline-flex; color: hsl(var(--pg-fg-muted)); }
  .wx-day-pop { font-size: 11px; color: hsl(205 80% 55%); font-weight: 600; }
  .wx-day-min { text-align: right; color: hsl(var(--pg-fg-muted)); }
  .wx-day-max { font-weight: 700; }
  .wx-day-bar {
    position: relative; height: 4px; border-radius: 999px;
    background: hsl(var(--pg-border));
  }
  .wx-day-fill {
    position: absolute; top: 0; bottom: 0; border-radius: 999px;
    background: linear-gradient(90deg, hsl(205 85% 60%), hsl(35 95% 58%));
  }

  /* ── saved chips ── */
  .wx-saved-head { display: flex; align-items: baseline; gap: 8px; }
  .wx-saved-head small { font-weight: 400; text-transform: none; letter-spacing: 0; font-size: 11px; }
  .wx-region { margin: 8px 2px 5px; font-size: 12px; font-weight: 700; color: hsl(var(--pg-fg)); }
  .wx-chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .wx-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 11px; border-radius: 999px;
    border: 1px solid hsl(var(--pg-border));
    background: hsl(var(--pg-elevated)); color: hsl(var(--pg-fg));
    font-size: 12px; cursor: pointer;
    transition: background 0.18s, border-color 0.18s, transform 0.18s;
  }
  .wx-chip:hover { background: hsl(var(--pg-hover)); transform: translateY(-1px); }
  .wx-chip.active {
    border-color: hsl(var(--pg-accent-purple));
    background: hsl(var(--pg-accent-purple) / 0.12);
  }
  .wx-chip b { font-weight: 700; }

  .wx-foot {
    margin: 16px 2px 2px; font-size: 11px; text-align: center;
    color: hsl(var(--pg-fg-muted));
  }

  @media (prefers-reduced-motion: reduce) {
    :global(.weather-panel), .wx-sun, .wx-rays, .wx-moon, .wx-star, .wx-cloud,
    .wx-drop, .wx-flake, .wx-flash, .wx-fog, .wx-results {
      animation: none !important;
    }
  }
  @media (max-width: 480px) {
    .wx-temp { font-size: 44px; }
    .wx-stats { grid-template-columns: repeat(2, 1fr); }
    .wx-day { grid-template-columns: 44px 24px 30px 30px 1fr 30px; gap: 6px; font-size: 12px; }
  }
</style>

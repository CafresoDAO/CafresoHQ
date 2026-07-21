// ── Weather popup state ─────────────────────────────────────────────────────
// Same open-via-store pattern as aiSearchOpen: the cloud button in PageHeader
// sets this true; WeatherModal (mounted once per layout) subscribes.
import { writable } from 'svelte/store';

export const weatherOpen = writable(false);

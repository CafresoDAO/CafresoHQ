import { browser } from '$app/environment';
import { writable } from 'svelte/store';

// How the HQ header's surface links behave: 'tabs' navigates the current
// window like any link; 'windows' opens/refocuses a dedicated OS window per
// surface. Mirrors the theme.js store shape (STORAGE_KEY + browser-guarded
// read + writable + setter).
const STORAGE_KEY = 'cafreso-hq-nav-mode'; // 'tabs' | 'windows'

function storedMode() {
  if (!browser) return 'tabs';
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'windows' ? 'windows' : 'tabs'; // default = today's behavior
}

export const navMode = writable(storedMode());

export function setNavMode(value) {
  const next = value === 'windows' ? 'windows' : 'tabs';
  if (browser) localStorage.setItem(STORAGE_KEY, next);
  navMode.set(next);
}

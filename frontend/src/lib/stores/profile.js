// User profile store — display name + handle, persisted locally.
//
// For the launch we keep profile metadata client-side (localStorage) so users
// can customize without a new write path on the canister. A follow-up can
// promote this to a canister-backed profile (the minegold backend already
// has `saveCallerUserProfile` if we want cross-canister persistence).

import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const KEY = 'cafreso:profile';
const DEFAULT = { name: '', bio: '', accent: 'banana' };

function loadInitial() {
  if (!browser) return DEFAULT;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT;
    return { ...DEFAULT, ...JSON.parse(raw) };
  } catch {
    return DEFAULT;
  }
}

export const profile = writable(loadInitial());

if (browser) {
  profile.subscribe((v) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(v));
    } catch {}
  });
}

export const ACCENTS = [
  { key: 'banana',   label: 'Banana',   hue: 45 },
  { key: 'espresso', label: 'Espresso', hue: 24 },
  { key: 'farm',     label: 'Farm',     hue: 130 },
  { key: 'dao',      label: 'DAO',      hue: 262 },
  { key: 'community',label: 'Community',hue: 320 }
];

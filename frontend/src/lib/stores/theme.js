import { browser } from '$app/environment';
import { writable } from 'svelte/store';

const STORAGE_KEY = 'cafreso-theme';
const META_COLOR = {
  light: '#f2dfc8',
  dark: '#1b100b'
};

function systemTheme() {
  if (!browser) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function storedTheme() {
  if (!browser) return 'light';
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'dark' || stored === 'light' ? stored : systemTheme();
}

function applyTheme(value) {
  if (!browser) return;
  document.documentElement.classList.toggle('dark', value === 'dark');
  document.documentElement.dataset.theme = value;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', META_COLOR[value] || META_COLOR.light);
}

export const theme = writable(storedTheme());

export function initTheme() {
  const value = storedTheme();
  theme.set(value);
  applyTheme(value);
}

export function setTheme(value) {
  const next = value === 'dark' ? 'dark' : 'light';
  if (browser) localStorage.setItem(STORAGE_KEY, next);
  theme.set(next);
  applyTheme(next);
}

export function toggleTheme() {
  theme.update((current) => {
    const next = current === 'dark' ? 'light' : 'dark';
    if (browser) localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
    return next;
  });
}

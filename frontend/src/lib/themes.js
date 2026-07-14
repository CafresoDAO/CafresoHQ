// Post theme configs — each theme drives the hero, body, stats bar, and
// chart palette for both the composer preview and the live post renderer.
// banking-brave keeps its own full-page layout (BankingBravePost.svelte);
// all other themes render through PostRenderer.svelte.

export const THEMES = {
  standard: {
    key: 'standard',
    label: 'Standard',
    emoji: '📄',
    description: 'Clean editorial, warm beige canvas',
    layout: 'standard',
    hero: {
      bg: 'linear-gradient(180deg, hsl(26 45% 96%), hsl(26 38% 90%))',
      text: 'hsl(222 47% 11%)',
      accent: 'hsl(32 72% 50%)',
      sub: 'hsl(215 16% 40%)',
      border: 'hsl(26 30% 82%)',
      label: 'hsl(32 56% 35%)',
    },
    body: {
      bg: 'white',
      border: 'hsl(26 30% 85%)',
      text: 'hsl(222 47% 15%)',
      heading: 'hsl(222 47% 11%)',
    },
    stats: {
      bg: 'hsl(26 40% 96%)',
      border: 'hsl(26 30% 85%)',
      value: 'hsl(222 47% 11%)',
      label: 'hsl(215 16% 47%)',
    },
    accent: 'hsl(32 72% 50%)',
    accentFg: 'white',
    dropCap: false,
    chartColor: 'hsl(32 72% 50%)',
    calloutBg: 'hsl(32 60% 94%)',
    calcCardBg: 'hsl(26 20% 92%)',
    previewBg: 'hsl(26 40% 94%)',
  },

  'banking-brave': {
    key: 'banking-brave',
    label: 'Banking.Brave',
    emoji: '🏛️',
    description: 'Navy + gold, editorial finance',
    layout: 'banking-brave',
    hero: {
      bg: 'linear-gradient(180deg, hsl(220 78% 14%), hsl(220 72% 22%))',
      text: 'hsl(42 40% 96%)',
      accent: 'hsl(43 74% 54%)',
      sub: 'hsl(42 25% 75%)',
      border: 'hsl(43 74% 54%)',
      label: 'hsl(43 74% 54%)',
    },
    body: {
      bg: 'hsl(42 40% 96%)',
      border: 'hsl(42 35% 90%)',
      text: 'hsl(222 30% 20%)',
      heading: 'hsl(220 72% 16%)',
    },
    stats: {
      bg: 'hsl(220 78% 14%)',
      border: 'hsl(43 74% 54%)',
      value: 'hsl(43 74% 54%)',
      label: 'hsl(42 20% 70%)',
    },
    accent: 'hsl(43 74% 54%)',
    accentFg: 'hsl(220 78% 14%)',
    dropCap: true,
    chartColor: 'hsl(43 74% 54%)',
    calloutBg: 'hsl(42 55% 92%)',
    calcCardBg: 'hsl(220 50% 18%)',
    previewBg: 'hsl(220 72% 20%)',
  },

  farm: {
    key: 'farm',
    label: 'Farm',
    emoji: '🌱',
    description: 'Earth greens, organic harvest',
    layout: 'standard',
    hero: {
      bg: 'linear-gradient(180deg, hsl(130 40% 16%), hsl(112 43% 26%))',
      text: 'hsl(112 30% 95%)',
      accent: 'hsl(45 95% 62%)',
      sub: 'hsl(112 20% 78%)',
      border: 'hsl(112 40% 38%)',
      label: 'hsl(45 95% 62%)',
    },
    body: {
      bg: 'hsl(112 12% 98%)',
      border: 'hsl(112 20% 88%)',
      text: 'hsl(130 20% 18%)',
      heading: 'hsl(130 40% 14%)',
    },
    stats: {
      bg: 'hsl(130 40% 16%)',
      border: 'hsl(112 40% 30%)',
      value: 'hsl(112 55% 72%)',
      label: 'hsl(112 20% 65%)',
    },
    accent: 'hsl(112 43% 40%)',
    accentFg: 'white',
    dropCap: true,
    chartColor: 'hsl(112 43% 45%)',
    calloutBg: 'hsl(112 30% 92%)',
    calcCardBg: 'hsl(130 32% 21%)',
    previewBg: 'hsl(130 40% 20%)',
  },

  dao: {
    key: 'dao',
    label: 'DAO',
    emoji: '⚡',
    description: 'Indigo authority, governance-first',
    layout: 'standard',
    hero: {
      bg: 'linear-gradient(180deg, hsl(262 55% 14%), hsl(262 45% 22%))',
      text: 'hsl(260 40% 96%)',
      accent: 'hsl(260 90% 75%)',
      sub: 'hsl(260 25% 76%)',
      border: 'hsl(260 60% 44%)',
      label: 'hsl(260 90% 75%)',
    },
    body: {
      bg: 'white',
      border: 'hsl(260 20% 90%)',
      text: 'hsl(260 15% 18%)',
      heading: 'hsl(262 55% 16%)',
    },
    stats: {
      bg: 'hsl(262 55% 14%)',
      border: 'hsl(260 50% 38%)',
      value: 'hsl(260 90% 75%)',
      label: 'hsl(260 25% 68%)',
    },
    accent: 'hsl(262 52% 44%)',
    accentFg: 'white',
    dropCap: false,
    chartColor: 'hsl(260 70% 62%)',
    calloutBg: 'hsl(260 40% 94%)',
    calcCardBg: 'hsl(262 45% 20%)',
    previewBg: 'hsl(262 52% 20%)',
  },

  community: {
    key: 'community',
    label: 'Community',
    emoji: '☕',
    description: 'Warm peach, open & welcoming',
    layout: 'standard',
    hero: {
      bg: 'linear-gradient(180deg, hsl(18 79% 88%), hsl(26 60% 80%))',
      text: 'hsl(24 48% 12%)',
      accent: 'hsl(24 48% 28%)',
      sub: 'hsl(24 30% 35%)',
      border: 'hsl(26 40% 72%)',
      label: 'hsl(24 48% 28%)',
    },
    body: {
      bg: 'white',
      border: 'hsl(26 30% 88%)',
      text: 'hsl(24 20% 20%)',
      heading: 'hsl(24 48% 12%)',
    },
    stats: {
      bg: 'hsl(18 79% 92%)',
      border: 'hsl(26 40% 78%)',
      value: 'hsl(24 48% 20%)',
      label: 'hsl(24 30% 42%)',
    },
    accent: 'hsl(24 48% 28%)',
    accentFg: 'white',
    dropCap: false,
    chartColor: 'hsl(18 72% 52%)',
    calloutBg: 'hsl(18 60% 93%)',
    calcCardBg: 'hsl(18 50% 87%)',
    previewBg: 'hsl(18 60% 78%)',
  },

  'build-log': {
    key: 'build-log',
    label: 'Build Log',
    emoji: '🔧',
    description: 'Dark header, code-forward',
    layout: 'standard',
    hero: {
      bg: 'hsl(222 47% 11%)',
      text: 'hsl(210 40% 96%)',
      accent: 'hsl(45 95% 62%)',
      sub: 'hsl(215 20% 62%)',
      border: 'hsl(215 30% 24%)',
      label: 'hsl(45 95% 62%)',
    },
    body: {
      bg: 'white',
      border: 'hsl(214 32% 91%)',
      text: 'hsl(222 47% 15%)',
      heading: 'hsl(222 47% 11%)',
    },
    stats: {
      bg: 'hsl(222 47% 11%)',
      border: 'hsl(215 30% 24%)',
      value: 'hsl(45 95% 62%)',
      label: 'hsl(215 20% 62%)',
    },
    accent: 'hsl(222 47% 11%)',
    accentFg: 'hsl(45 95% 62%)',
    dropCap: false,
    chartColor: 'hsl(210 80% 58%)',
    calloutBg: 'hsl(214 30% 93%)',
    calcCardBg: 'hsl(222 40% 17%)',
    previewBg: 'hsl(222 47% 15%)',
  },
};

export const THEME_LIST = Object.values(THEMES);

// The canister Post type has no `theme` field, so the theme key is persisted
// in `layout` (free-form text on the canister). banking-brave keeps its
// dedicated full-page layout; every other theme key round-trips as-is so a
// post published with "Farm" still renders Farm after reload.
export function layoutFromTheme(themeKey) {
  return THEMES[themeKey] ? themeKey : 'standard';
}

// Inverse mapping when reading a post back from the canister: old posts have
// layout 'standard'/'banking-brave'; new ones may carry any theme key.
export function themeFromLayout(layout) {
  return THEMES[layout] ? layout : 'standard';
}

// Resolve a theme config, falling back to standard if not found.
export function getTheme(key) {
  return THEMES[key] ?? THEMES.standard;
}

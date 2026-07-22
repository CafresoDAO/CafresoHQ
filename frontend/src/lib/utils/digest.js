// ─────────────────────────────────────────────────────────────────────────────
// "What the network learned this week" — pure client-side digest over the
// library index the page already fetches every 60s (no new endpoint, no
// canister change, no per-entry graph fetches). Deliberately honest about
// what it is: real counts over real timestamps, plus a naive keyword-frequency
// "themes" pass — NOT the sigma.js community/cluster detection (that's
// computed client-side at graph-render time and never persisted, so it isn't
// available here without re-running Louvain over 900+ nodes on every page
// load). If real topic clusters get persisted server-side one day, only
// `themes()` below needs to change — the digest shape stays the same.
import { nsToDate } from './time.js';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

const STOPWORDS = new Set([
  'the', 'a', 'an', 'of', 'in', 'on', 'to', 'for', 'and', 'or', 'is', 'are', 'was', 'were',
  'be', 'been', 'being', 'as', 'at', 'by', 'from', 'with', 'that', 'this', 'these', 'those',
  'it', 'its', "it's", 'their', 'his', 'her', 'they', 'them', 'what', 'why', 'how', 'when',
  'where', 'who', 'whom', 'which', 'will', 'would', 'could', 'should', 'can', 'do', 'does',
  'did', 'has', 'have', 'had', 'about', 'into', 'onto', 'over', 'under', 'after', 'before',
  'during', 'between', 'than', 'then', 'there', 'here', 'if', 'but', 'not', 'no', 'yes',
  'new', 'latest', 'recent', 'current', 'now', 'today', 'still', 'also', 'more', 'most',
  'many', 'much', 'some', 'any', 'all', 'each', 'other', 'such', 'just', 'like', 'per',
  'you', 'your', 'we', 'our', 'i', 'my', 'me',
  // Question-boilerplate that scores high by sheer frequency without being a
  // "theme" — every query has some of these regardless of subject.
  'regarding', 'details', 'detail', 'specific', 'specifics', 'against', 'provide', 'provided',
  'according', 'reported', 'reports', 'report', 'said', 'according', 'following', 'since',
  'due', 'amid', 'amidst', 'including', 'involving', 'related', 'affect', 'affects', 'affected',
  'impact', 'impacts'
]);

function tokenize(query) {
  return String(query || '')
    .toLowerCase()
    .replace(/[’‘“”]/g, "'")
    .replace(/[^a-z0-9'\s]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 2 && !STOPWORDS.has(w));
}

/** Entries with ts inside [now - windowMs, now]. `ts` is canister ns. */
function inWindow(entries, windowMs) {
  const cutoff = Date.now() - windowMs;
  return entries.filter((e) => {
    const d = nsToDate(e.ts);
    return d && d.getTime() >= cutoff;
  });
}

/** Top keyword themes by DISTINCT-ENTRY frequency (each word counted once per
    query, so one repetitive question can't fake a trend). Returns
    [{word, count}], highest first. */
export function themes(entries, { limit = 6 } = {}) {
  const counts = new Map();
  for (const e of entries) {
    const seen = new Set(tokenize(e.query));
    for (const w of seen) counts.set(w, (counts.get(w) || 0) + 1);
  }
  return [...counts.entries()]
    .filter(([, n]) => n >= 2)   // a "theme" needs at least 2 questions, not 1
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([word, count]) => ({ word, count }));
}

/** Entry counts per day for the last `days` days, oldest first — a 7-bar
    sparkline of research velocity. */
function dailyCounts(entries, days) {
  const buckets = Array.from({ length: days }, (_, i) => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - (days - 1 - i));
    return { day: d, count: 0 };
  });
  for (const e of entries) {
    const d = nsToDate(e.ts);
    if (!d) continue;
    const dayStart = new Date(d); dayStart.setHours(0, 0, 0, 0);
    const b = buckets.find((x) => x.day.getTime() === dayStart.getTime());
    if (b) b.count += 1;
  }
  return buckets;
}

/**
 * Full weekly digest over the already-fetched library index.
 *   { total, deep, gaps, avgSources, topEntry, daily, themes }
 * Returns null if there's nothing to report (index empty / too young).
 */
export function weeklyDigest(entries, { days = 7 } = {}) {
  if (!entries || !entries.length) return null;
  const week = inWindow(entries, days * 24 * 60 * 60 * 1000);
  if (!week.length) return null;

  const deep = week.filter((e) => e.mode === 'deep').length;
  const gaps = week.filter((e) => e.askedBy === 'ai-gap').length;
  const totalSources = week.reduce((s, e) => s + (e.sources || 0), 0);
  const topEntry = [...week].sort((a, b) => (b.sources || 0) - (a.sources || 0))[0];

  return {
    total: week.length,
    deep,
    gaps,
    avgSources: Math.round((totalSources / week.length) * 10) / 10,
    topEntry,
    daily: dailyCounts(week, days),
    themes: themes(week)
  };
}

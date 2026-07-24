/* IC timestamp helpers.

   Canister timestamps are NANOSECONDS since the epoch (Time.now()), while JS
   Date wants milliseconds — so every read site has to divide by 1e6. That
   conversion was open-coded in at least five places (library, the vault
   builder, AISearchModal, SearchNetworkCard, devlog), each re-deriving the
   magnitude by hand. Getting it wrong by a factor of 1000 doesn't throw, it
   just silently renders 1970 or a date ~50,000 years out, so it's worth one
   home.

   Note `fmtDate` in $lib/data/blog.js is a different thing that shares the
   name: it takes an ISO *string* (post front-matter), not canister ns. Don't
   confuse them — these take BigInt/number ns off the wire. */

/** ns (BigInt | number | string) → JS Date. Invalid input → null, never throws. */
export function nsToDate(ns) {
  try {
    if (ns === null || ns === undefined || ns === '') return null;
    const ms = Number(ns) / 1e6;
    if (!Number.isFinite(ms)) return null;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

/* Named formats rather than a free-form options bag, so the same kind of
   timestamp reads the same everywhere. `short` is the list/card default;
   `long` is for a document header (the vault's Overview.md). */
const FORMATS = {
  short: { month: 'short', day: 'numeric', year: 'numeric' },
  long: { month: 'long', day: 'numeric', year: 'numeric' },
  dateTime: { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }
};

/** ns → localized date string. Unparseable input → '' so callers can `||` a
    fallback rather than rendering "Invalid Date" at a user. */
export function fmtNsDate(ns, format = 'short') {
  const d = nsToDate(ns);
  if (!d) return '';
  try {
    return d.toLocaleDateString(undefined, FORMATS[format] || FORMATS.short);
  } catch {
    return '';
  }
}

/** ns → "3m ago" / "2h ago" / "5d ago", falling back to a date past a week.
    Used for freshness signals (worker last-seen, recent answers). */
export function fmtNsRelative(ns) {
  const d = nsToDate(ns);
  if (!d) return '';
  const secs = (Date.now() - d.getTime()) / 1000;
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  if (secs < 604800) return `${Math.floor(secs / 86400)}d ago`;
  return fmtNsDate(ns, 'short');
}

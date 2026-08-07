/* ── How long the office waits for a brain ────────────────────────────────
   Every stream has a HEAD timeout: how long we wait for the first byte
   before deciding the backend is not coming. One number served every
   provider — 20s — and that number is right for a hosted API and wrong for
   a local one.

   Measured, repeatedly, on a real floor: a task dropped on a local
   llama3.1 came back "that brain didn't answer in time" three times in a
   row while Ollama was healthy and answering a one-word prompt in 0.8s.
   The difference is cold weights. The first call after the model is
   evicted loads ~5GB from disk before it can emit a token, which is not a
   hang — it is the coworker walking to the archive. Failing them at 20s
   makes the zero-config first hire, the one most users will make, look
   broken on its first job.

   Kept import-free so scripts/test_patience.py runs this file verbatim. */

/* Loopback, IPv6 loopback, the RFC1918 LAN ranges, and .local — someone
   running Ollama on the box under the desk is as local as localhost, and
   their weights load off the same kind of disk.

   Parsed as a URL rather than substring-matched: "https://localhost.evil.com"
   and "https://evil.com/#localhost" both contain the word and neither is
   local. A relative path ('/ollama/v1', the same-origin proxy serve.py
   sets up) has no host of its own and is judged by the caller, which knows
   which daemon sits behind it. */
const PRIVATE_HOST = [
  /^localhost$/i,
  /^127\./,
  /^\[?::1\]?$/,
  /^10\./,
  /^192\.168\./,
  /^172\.(1[6-9]|2\d|3[01])\./,   // 172.16.0.0/12 — NOT 172.32+
  /\.local$/i,
];

function isLocalEndpoint(url) {
  const raw = String(url || '').trim();
  if (!raw) return false;
  if (raw.charAt(0) === '/') return false;          // relative — caller decides
  let host;
  try {
    host = new URL(raw).hostname;
  } catch (_e) {
    return false;                                    // unparseable is not a claim
  }
  if (!host) return false;
  for (const re of PRIVATE_HOST) if (re.test(host)) return true;
  return false;
}

/* 20s is plenty for a hosted API — past that something really is wrong.
   90s covers a cold multi-GB local load with room to spare, and still
   fails rather than hanging forever. */
const REMOTE_HEAD_MS = 20000;
const LOCAL_HEAD_MS = 90000;

/* When to admit we are still waiting. Below this the dots are honest on
   their own; past it, silence starts to read as broken. Deliberately far
   below even the REMOTE budget, because "is this thing working?" is the
   question being answered, not "has it failed?". */
const SLOW_HEAD_MS = 6000;

/* `local` is what the caller KNOWS (the ollama/lmstudio drivers proxy to a
   daemon on this machine and say so); `url` is the fallback for a custom
   OpenAI-compatible endpoint the user pointed at their own box. Either is
   enough — neither is required. */
function headTimeoutMs(opts) {
  const o = opts || {};
  if (o.local === true) return LOCAL_HEAD_MS;
  return isLocalEndpoint(o.url) ? LOCAL_HEAD_MS : REMOTE_HEAD_MS;
}

export { headTimeoutMs, isLocalEndpoint, LOCAL_HEAD_MS, REMOTE_HEAD_MS, SLOW_HEAD_MS };

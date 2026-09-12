# Your own office on this machine, reachable from the Cafreso sign-in

The shell at **https://ai.cafreso.com** is where you sign in (Internet
Identity) and where money moves. The office itself — `serve.py`, the pixel
floor, your coworkers' brains — can run anywhere the shell can reach. On
the fleet that is a container behind the gateway; on your own machine it
is a **Local machine** office the shell finds on `localhost`.

## One command

```
scripts/local_hq.sh install
```

That writes a per-user LaunchAgent (`~/Library/LaunchAgents/com.cafreso.hq.plist`)
that starts `serve.py` at login and restarts it if it dies, then waits for
`/health`. Nothing system-wide, no admin password. `uninstall` removes it;
`status`, `restart` (rebuilds the UI first) and `logs` do what they say.

- Port: `8787` by default — the shell probes 8787 and 8788 on its own. If
  another program holds the port (on this Mac, Docker Desktop forwards 8787
  and 8788 for the search-worker container), install with another one:
  `PORT=8789 scripts/local_hq.sh install`, then type that port once in the
  shell's **custom port** field — it remembers it.
- State: `<repo>/hq-state` by default (`CAFRESOHQ_HQ_STATE_DIR` to move it).
  The roster, tasks and chat live in the browser's storage for the shell's
  origin, so the same office looks the same from ai.cafreso.com every time.
- The script probes `127.0.0.1`, not `localhost`: `localhost` resolves to
  `::1` first, and a Docker port forward on the IPv6 side answers nothing
  for a port it holds. Browsers fall back to IPv4 when `::1` refuses, so the
  shell still finds the office; a script has to ask the right address.

## Connecting, once

1. Sign in at https://ai.cafreso.com → **HQ**.
2. Choose **💻 Local machine**. The shell probes for the office; on a custom
   port, type it in the field and press **Connect**.
3. Chrome, Brave and Edge (138+) ask once for **Local network access** for
   ai.cafreso.com → **Allow**, then **Re-check**. The shell says *Local HQ
   detected* and opens the floor.

The shell embeds `http://localhost:<port>/hq.html`; Chromium-family
browsers treat `localhost` as a secure origin even from an https page.
**Safari does not.** For Safari, install mkcert once (`brew install mkcert
&& mkcert -install` — yours to run, it adds a local CA to your keychain);
`serve.py` then issues a browser-trusted `https://localhost` cert on its
own at the next start, and the shell probes https first.

## What the office can reach from here

`serve.py` on your Mac sees your local brains directly: the Claude Code,
Codex and Gemini CLIs you are signed into, Ollama and LM Studio on this
machine, and the Hermes gateway through its tunnel. That is the one office
that can seat all of them at once (a cloud office cannot see LM Studio on
your desk). The hall (`AGENT_MARKETPLACE.md`) works from here as well: this
office's worker key is in `hq-state/market/worker-key.json`.

## Verified 2026-09-12

`scripts/local_hq.sh install` on this Mac (port 8789), `/health` answering
`status: ok` with `Access-Control-Allow-Origin: https://ai.cafreso.com` to
the shell's probe, the lit office rendering from the LaunchAgent's serve.py
in a headless browser, and `scripts/test_the_local_office_answers_at_the_door_the_shell_knocks_on.py`
pinning the LaunchAgent's shape, the port refusal, the loopback probe and
the uninstall. **Not verified by me:** the sign-in itself and the Connect
click at ai.cafreso.com — those need your Internet Identity.

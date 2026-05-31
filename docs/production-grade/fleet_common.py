"""
CafresoHQ — shared fleet utilities (reference refactor).

PROBLEM (finding D3):
  `_principal_slug()` and `_render_caddyfile()` are implemented TWICE — in
  fleet-manager.py and fleet-api.py — and have ALREADY DIVERGED: fleet-api's
  Caddyfile renderer is missing the `/u/<slug>` → `/hq.html` redirect rules, so
  a gateway-side re-render (on provision) can silently overwrite the correct
  routes with broken ones.

SOLUTION:
  One module imported by both. Single source of truth for the slug algorithm and
  the Caddy route block. Import this from BOTH fleet-manager.py and fleet-api.py
  and delete their private copies.

Stdlib only.
"""

from __future__ import annotations

import hashlib


def principal_slug(principal: str) -> str:
    """Stable URL-safe slug for a principal. MUST match the frontend
    (config.js gatewayUrlForPrincipal) and the canister-side derivation."""
    return hashlib.sha256(principal.encode()).hexdigest()[:16]


def render_user_route(slug: str, ip: str, port: int = 8787) -> str:
    """Render ONE user's Caddy route block.

    Includes the `/u/<slug>` (no trailing slash) redirect AND the `/` → /hq.html
    rewrite — the rules fleet-api.py's copy was missing. Both manager and api
    call this so they can never drift again.

    NOTE: in the secured architecture (CONTAINER_AUTH_DESIGN.md) the
    `reverse_proxy` line is wrapped in `forward_auth` + targets a PRIVATE ip.
    Pass secured=True once the verifier is deployed.
    """
    return (
        f"    handle /u/{slug} {{\n"
        f"        redir * /u/{slug}/hq.html\n"
        f"    }}\n"
        f"    handle_path /u/{slug}/* {{\n"
        f"        @approot path /\n"
        f"        rewrite @approot /hq.html\n"
        f"        reverse_proxy {ip}:{port}\n"
        f"    }}"
    )


def render_user_route_secured(slug: str, ip: str, port: int = 8787,
                              verifier: str = "localhost:9090") -> str:
    """Secured variant: gate every request through the JWT verifier
    (forward_auth) before proxying to the container's PRIVATE ip."""
    return (
        f"    handle /u/{slug} {{\n"
        f"        redir * /u/{slug}/hq.html\n"
        f"    }}\n"
        f"    handle_path /u/{slug}/* {{\n"
        f"        forward_auth {verifier} {{\n"
        f"            uri /verify?slug={slug}\n"
        f"            copy_headers X-Cafreso-Principal\n"
        f"        }}\n"
        f"        @approot path /\n"
        f"        rewrite @approot /hq.html\n"
        f"        reverse_proxy {ip}:{port}\n"
        f"    }}"
    )


def render_caddyfile(template: str, fleet: dict, *, secured: bool = False) -> str:
    """Render the full Caddyfile from the template + fleet registry.

    Single implementation for BOTH fleet-manager.py (scp/ssh path) and
    fleet-api.py (local gateway path). Replaces the two diverged copies.
    """
    render = render_user_route_secured if secured else render_user_route
    blocks = []
    for principal, info in (fleet.get("users") or {}).items():
        ip = info.get("ip")
        if not ip:
            continue
        blocks.append(render(principal_slug(principal), ip, info.get("port", 8787)))

    gw = fleet.get("gateway") or {}
    user_routes = "\n\n".join(blocks) or "    # (no users yet)"
    return (
        template
        .replace("__PRIMARY_HOST__", gw.get("public_hostname") or "hq.cafreso.com")
        .replace("__GATEWAY_IP__", gw.get("public_ip") or "<unset>")
        .replace("__USER_ROUTES__", user_routes)
        .replace("__USER_ROUTES_HTTP__", user_routes)
    )

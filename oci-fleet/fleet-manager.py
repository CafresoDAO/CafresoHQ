#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   CafresoAI -- OCI Fleet Manager                            ║
║   Manage per-user OCI Container Instances                    ║
╚══════════════════════════════════════════════════════════════╝

Commands:
  list                        List all fleet users + container status
  provision <principal>       Create a new container for a user
  start     <principal>       Start a stopped container
  stop      <principal>       Stop a running container (saves cost)
  delete    <principal>       Permanently delete a user's container
  status    <principal>       Show detailed status + health check
  health    <principal>       Hit /health on the container
  logs      <principal>       Tail recent logs (OCI Logging)
  costs                       Show cycle/cost summary for the fleet
  bucket-init                 Create the vault Object Storage bucket
  image-push                  Build + push Docker image to OCIR
  config                      Show current fleet config

Usage:
  cd C:\\Users\\Anthony\\Documents\\openclawhq
  python oci-fleet/fleet-manager.py list
  python oci-fleet/fleet-manager.py provision 2vxsx-fae3l-principal
  python oci-fleet/fleet-manager.py stop 2vxsx-fae3l-principal

Requirements:
  pip install -r oci-fleet/requirements-fleet.txt
  ~/.oci/config must be set up (run: oci setup config)
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

# ── Optional deps ────────────────────────────────────────────────────────────
try:
    import oci
    HAS_OCI = True
except ImportError:
    HAS_OCI = False

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ── ANSI colours ─────────────────────────────────────────────────────────────
RESET  = '\033[0m'
BOLD   = '\033[1m'
GREEN  = '\033[32m'
YELLOW = '\033[33m'
RED    = '\033[31m'
CYAN   = '\033[36m'
GREY   = '\033[90m'

def c(text, colour): return f'{colour}{text}{RESET}'
def ok(s):   return c(s, GREEN)
def warn(s): return c(s, YELLOW)
def err(s):  return c(s, RED)
def dim(s):  return c(s, GREY)
def hi(s):   return c(s, CYAN)


# ── Fleet registry ───────────────────────────────────────────────────────────
FLEET_FILE = pathlib.Path(os.environ.get('FLEET_REGISTRY',
    pathlib.Path(__file__).parent / 'fleet.json'))

FLEET_DEFAULTS = {
    'version': '1',
    'compartment_id': os.environ.get('OCI_COMPARTMENT_ID', ''),
    'region':         os.environ.get('OCI_REGION', 'us-chicago-1'),
    'subnet_id':      os.environ.get('OCI_SUBNET_ID', ''),
    'availability_domain': os.environ.get('OCI_AVAILABILITY_DOMAIN', 'AD-1'),
    'vault_namespace':os.environ.get('OCI_VAULT_NAMESPACE', ''),
    'vault_bucket':   os.environ.get('OCI_VAULT_BUCKET', 'cafresoai-fleet-vault'),
    'ocir_region_key':os.environ.get('OCIR_REGION_KEY', 'iad'),
    'ocir_namespace': os.environ.get('OCIR_TENANCY_NAMESPACE', ''),
    'ocir_repo':      os.environ.get('OCIR_REPO', 'cafresoai-serve'),
    'fleet_ocpus':    float(os.environ.get('FLEET_OCPUS', '1')),
    'fleet_memory_gb':float(os.environ.get('FLEET_MEMORY_GB', '6')),
    'users': {},
}


def load_fleet() -> dict:
    if FLEET_FILE.exists():
        try:
            data = json.loads(FLEET_FILE.read_text(encoding='utf-8'))
            # Merge defaults for any missing top-level keys
            merged = {**FLEET_DEFAULTS, **data}
            merged['users'] = data.get('users', {})
            return merged
        except Exception as e:
            print(err(f'Error reading fleet.json: {e}'))
            sys.exit(1)
    return dict(FLEET_DEFAULTS)


def save_fleet(fleet: dict):
    FLEET_FILE.parent.mkdir(parents=True, exist_ok=True)
    FLEET_FILE.write_text(
        json.dumps(fleet, indent=2, default=str),
        encoding='utf-8')


def require_oci():
    if not HAS_OCI:
        print(err('OCI SDK not installed.'))
        print('Run:  pip install -r oci-fleet/requirements-fleet.txt')
        sys.exit(1)


def get_oci_config(fleet: dict) -> dict:
    try:
        return oci.config.from_file()
    except Exception as e:
        print(err(f'OCI config error: {e}'))
        print('Run:  oci setup config')
        sys.exit(1)


def container_client(fleet: dict):
    cfg = get_oci_config(fleet)
    return oci.container_instances.ContainerInstanceClient(cfg)


def object_client(fleet: dict):
    cfg = get_oci_config(fleet)
    return oci.object_storage.ObjectStorageClient(cfg)


# ── Principal → safe name ────────────────────────────────────────────────────
def principal_to_name(principal: str) -> str:
    """Convert a principal to a safe OCI display name (max 64 chars)."""
    safe = principal.replace(':', '-').replace(' ', '-').lower()
    # Use last 20 chars which are most unique
    short = safe[-20:] if len(safe) > 20 else safe
    return f'cafresoai-{short}'


def principal_to_prefix(principal: str) -> str:
    """Object Storage prefix for this user's vault files."""
    import hashlib
    h = hashlib.sha256(principal.encode()).hexdigest()[:16]
    return f'user-{h}/'


# ── Image URL ─────────────────────────────────────────────────────────────────
def image_url(fleet: dict) -> str:
    return (f"{fleet['ocir_region_key']}.ocir.io"
            f"/{fleet['ocir_namespace']}"
            f"/{fleet['ocir_repo']}:latest")


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_list(args, fleet: dict):
    """List all users and their container status."""
    users = fleet.get('users', {})
    if not users:
        print(dim('No users provisioned yet.'))
        print(f'  Run:  {hi("python oci-fleet/fleet-manager.py provision <principal>")}')
        return

    if HAS_OCI:
        require_oci()
        cli = container_client(fleet)
        # Refresh status from OCI for each user
        for principal, info in users.items():
            cid = info.get('container_instance_id')
            if cid:
                try:
                    ci = cli.get_container_instance(cid).data
                    info['_live_status'] = ci.lifecycle_state
                    info['_live_shape'] = getattr(ci.shape_config, 'ocpus', '?')
                except Exception:
                    info['_live_status'] = 'UNKNOWN'
    else:
        for info in users.values():
            info['_live_status'] = info.get('status', '?')

    rows = []
    for principal, info in users.items():
        state = info.get('_live_status', info.get('status', '?'))
        state_str = (ok('ACTIVE') if state == 'ACTIVE'
                     else warn(state) if state in ('INACTIVE', 'STOPPED')
                     else err(state) if state in ('FAILED', 'UNKNOWN')
                     else dim(state))
        rows.append([
            dim(principal[:40] + ('…' if len(principal) > 40 else '')),
            info.get('display_name', '')[:30],
            state_str,
            info.get('ip', dim('–')),
            info.get('created_at', '')[:10],
        ])

    headers = [BOLD+'Principal'+RESET, BOLD+'Name'+RESET,
               BOLD+'Status'+RESET, BOLD+'IP'+RESET, BOLD+'Created'+RESET]
    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt='simple'))
    else:
        print('  '.join(headers))
        for row in rows:
            print('  '.join(str(c) for c in row))
    print(f'\n{dim(str(len(users)))} users  ·  registry: {dim(str(FLEET_FILE))}')


def _read_ocir_pull_secret(fleet: dict):
    """Read OCIR credentials from the Docker config written by `ocir-login`,
    return a BasicImagePullSecret ready to attach to a container instance.
    Returns None if no credentials are found (image must be public)."""
    import base64 as _b64
    key = fleet.get('ocir_region_key', 'iad')
    registry = f'{key}.ocir.io'

    # Try native ~/.docker/config.json first (works on gateway VM without Docker)
    docker_cfg = None
    cfg_path = pathlib.Path.home() / '.docker' / 'config.json'
    if cfg_path.exists():
        try:
            docker_cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        except Exception:
            pass

    # Fall back to WSL Docker config (Windows dev machine)
    if not docker_cfg and sys.platform == 'win32':
        try:
            r = subprocess.run(['wsl', '-d', 'Ubuntu-24.04', '--', 'cat', '/home/anthony/.docker/config.json'],
                               capture_output=True, timeout=15)
            if r.returncode == 0:
                docker_cfg = json.loads(r.stdout.decode('utf-8', 'replace'))
        except Exception:
            pass

    if not docker_cfg:
        return None
    auths = docker_cfg.get('auths', {})
    entry = auths.get(registry) or auths.get(f'https://{registry}')
    if not entry or not entry.get('auth'):
        return None

    # The 'auth' field is base64(username:password). Split it and re-encode each part.
    raw = _b64.b64decode(entry['auth']).decode('utf-8', 'replace')
    if ':' not in raw:
        return None
    user, _, pwd = raw.partition(':')
    return oci.container_instances.models.CreateBasicImagePullSecretDetails(
        secret_type        = 'BASIC',
        registry_endpoint  = registry,
        username           = _b64.b64encode(user.encode()).decode(),
        password           = _b64.b64encode(pwd.encode()).decode(),
    )


def cmd_provision(args, fleet: dict):
    """Provision a new OCI Container Instance for a user principal."""
    principal = args.principal
    if not principal:
        print(err('principal is required'))
        sys.exit(1)

    if principal in fleet['users']:
        print(warn(f'User already provisioned: {principal}'))
        existing = fleet['users'][principal]
        print(f"  Container: {existing.get('container_instance_id', '?')}")
        print(f"  Status:    {existing.get('status', '?')}")
        return

    require_oci()
    cli = container_client(fleet)

    # Validate required fleet config
    for key in ('compartment_id', 'subnet_id', 'vault_namespace', 'ocir_namespace'):
        if not fleet.get(key):
            print(err(f'fleet.json missing: {key}'))
            print(f'  Set it in oci-fleet/.env or run:  {hi("python oci-fleet/fleet-manager.py config")}')
            sys.exit(1)

    display_name = principal_to_name(principal)
    vault_prefix = principal_to_prefix(principal)
    img          = image_url(fleet)

    print(f'\n{BOLD}Provisioning container for:{RESET}')
    print(f'  Principal:    {hi(principal)}')
    print(f'  Display name: {display_name}')
    print(f'  Image:        {img}')
    print(f'  Vault prefix: {vault_prefix}')
    print(f'  Shape:        CI.Standard.A1.Flex  '
          f'({fleet["fleet_ocpus"]} OCPU / {fleet["fleet_memory_gb"]} GB)')
    print()

    # ── OCI API key credentials for the container's Object Storage client ────
    # The container's serve.py needs OCI creds to call Object Storage.
    # We pass them as env vars so it doesn't need to rely on Instance Principal
    # IMDS (which can hang if the IAM dynamic group isn't propagated yet).
    _oci_key_b64 = ''
    _oci_cfg = {}
    try:
        import configparser, base64 as _b64
        _cp = configparser.ConfigParser()
        _oci_cfg_path = os.path.expanduser('~/.oci/config')
        _cp.read(_oci_cfg_path)
        _sec = _cp['DEFAULT'] if 'DEFAULT' in _cp else {}
        _key_file = os.path.expanduser(_sec.get('key_file', '~/.oci/oci_api_key.pem'))
        with open(_key_file, 'rb') as _kf:
            _oci_key_b64 = _b64.b64encode(_kf.read()).decode()
        _oci_cfg = {
            'tenancy':     _sec.get('tenancy', ''),
            'user':        _sec.get('user', ''),
            'fingerprint': _sec.get('fingerprint', ''),
            'region':      _sec.get('region', 'us-ashburn-1'),
        }
    except Exception as _e:
        print(warn(f'  Could not read OCI credentials for container: {_e}'))
        print(f'  {dim("Container will fall back to Instance Principal auth")}')

    env_vars = {
        'OPENCLAW_FLEET_MODE':    'oci-fleet',
        'OPENCLAW_VAULT_BACKEND': 'oci',
        'OCI_VAULT_NAMESPACE':    fleet['vault_namespace'],
        'OCI_VAULT_BUCKET':       fleet['vault_bucket'],
        'OCI_VAULT_PREFIX':       vault_prefix,
        'USER_PRINCIPAL':         principal,
        'OPENCLAW_HQ_STATE_DIR':  '/data/hq-state',
        'OPENCLAW_VAULT':         '/data/vault',
        # OCI credentials for serve.py Object Storage client
        'OCI_TENANCY_OCID':       _oci_cfg.get('tenancy', ''),
        'OCI_USER_OCID':          _oci_cfg.get('user', ''),
        'OCI_FINGERPRINT':        _oci_cfg.get('fingerprint', ''),
        'OCI_REGION':             _oci_cfg.get('region', 'us-ashburn-1'),
        'OCI_KEY_B64':            _oci_key_b64,
    }

    pull_secret = _read_ocir_pull_secret(fleet)
    if pull_secret:
        print(f'  OCIR pull:    {dim("BasicImagePullSecret from ~/.docker/config.json")}')
    else:
        print(f'  OCIR pull:    {warn("no credentials found — image must be public")}')
        print(f'                {dim("Run: python oci-fleet/fleet-manager.py ocir-login")}')

    details = oci.container_instances.models.CreateContainerInstanceDetails(
        compartment_id     = fleet['compartment_id'],
        display_name       = display_name,
        availability_domain= fleet['availability_domain'],
        shape              = 'CI.Standard.A1.Flex',
        shape_config       = oci.container_instances.models.CreateContainerInstanceShapeConfigDetails(
            ocpus          = fleet['fleet_ocpus'],
            memory_in_gbs  = fleet['fleet_memory_gb'],
        ),
        image_pull_secrets = [pull_secret] if pull_secret else None,
        containers         = [
            oci.container_instances.models.CreateContainerDetails(
                image_url            = img,
                display_name         = 'cafresoai-serve',
                environment_variables= env_vars,
                resource_config      = oci.container_instances.models.CreateContainerResourceConfigDetails(
                    vcpus_limit       = fleet['fleet_ocpus'],
                    memory_limit_in_gbs= fleet['fleet_memory_gb'],
                ),
            )
        ],
        vnics              = [
            oci.container_instances.models.CreateContainerVnicDetails(
                subnet_id           = fleet['subnet_id'],
                is_public_ip_assigned=True,   # set False if behind API Gateway
                display_name        = f'{display_name}-vnic',
            )
        ],
        freeform_tags      = {
            'cafresoai': 'true',
            'principal': principal[:256],
        },
    )

    print('Creating container instance… ', end='', flush=True)
    try:
        resp = cli.create_container_instance(
            create_container_instance_details=details)
        ci_id = resp.data.id
        print(ok('created'))
    except Exception as e:
        print(err('FAILED'))
        print(f'  {e}')
        sys.exit(1)

    # Wait for ACTIVE state (up to 3 minutes)
    print('Waiting for ACTIVE state ', end='', flush=True)
    ip = None
    for _ in range(36):
        time.sleep(5)
        try:
            ci = cli.get_container_instance(ci_id).data
            state = ci.lifecycle_state
            if state == 'ACTIVE':
                # Resolve the public IP via the network client.
                # ContainerInstance.vnics[i] is just {vnic_id}; the IP lives on the VNIC itself.
                try:
                    if ci.vnics:
                        net_cli = oci.core.VirtualNetworkClient(get_oci_config(fleet))
                        vnic = net_cli.get_vnic(ci.vnics[0].vnic_id).data
                        ip = vnic.public_ip or vnic.private_ip
                except Exception as ip_err:
                    print(f'\n  {warn(f"could not resolve IP: {ip_err}")}')
                print(ok(' ACTIVE'))
                break
            elif state in ('FAILED', 'DELETED'):
                print(err(f' {state}'))
                print(err('Container failed to start. Check OCI Console logs.'))
                sys.exit(1)
            print('.', end='', flush=True)
        except Exception:
            print('.', end='', flush=True)
    else:
        print(warn(' timed out (still provisioning)'))

    # Record in fleet registry
    fleet['users'][principal] = {
        'container_instance_id': ci_id,
        'display_name':          display_name,
        'vault_prefix':          vault_prefix,
        'ip':                    ip or '',
        'port':                  8787,
        'status':                'ACTIVE',
        'created_at':            datetime.now(timezone.utc).isoformat(),
        'principal':             principal,
    }
    save_fleet(fleet)
    print(f'\n{ok("Provisioned!")}')
    if ip:
        print(f'  Endpoint:  http://{ip}:8787/health')
    print(f'  Container: {dim(ci_id)}')
    print(f'  Registry:  {dim(str(FLEET_FILE))}')


def cmd_stop(args, fleet: dict):
    """Stop a running container (keeps config, stops billing compute)."""
    principal = args.principal
    info = fleet['users'].get(principal)
    if not info:
        print(err(f'Unknown principal: {principal}'))
        sys.exit(1)

    require_oci()
    cid = info.get('container_instance_id')
    cli = container_client(fleet)
    print(f'Stopping {hi(info["display_name"])}… ', end='', flush=True)
    try:
        cli.stop_container_instance(cid)
        info['status'] = 'INACTIVE'
        save_fleet(fleet)
        print(ok('stopped'))
    except Exception as e:
        print(err(f'FAILED: {e}'))


def cmd_start(args, fleet: dict):
    """Start a stopped container."""
    principal = args.principal
    info = fleet['users'].get(principal)
    if not info:
        print(err(f'Unknown principal: {principal}'))
        sys.exit(1)

    require_oci()
    cid = info.get('container_instance_id')
    cli = container_client(fleet)
    print(f'Starting {hi(info["display_name"])}… ', end='', flush=True)
    try:
        cli.start_container_instance(cid)
        info['status'] = 'ACTIVE'
        save_fleet(fleet)
        print(ok('started'))
    except Exception as e:
        print(err(f'FAILED: {e}'))


def cmd_delete(args, fleet: dict):
    """Permanently delete a user's container. Vault data in Object Storage is kept."""
    principal = args.principal
    info = fleet['users'].get(principal)
    if not info:
        print(err(f'Unknown principal: {principal}'))
        sys.exit(1)

    print(warn(f'\nThis will permanently DELETE the container for:'))
    print(f'  {hi(principal)}')
    print(f'  Container: {info.get("container_instance_id")}')
    print(warn('Vault data in Object Storage is NOT deleted.\n'))
    confirm = input('Type DELETE to confirm: ').strip()
    if confirm != 'DELETE':
        print('Aborted.')
        return

    require_oci()
    cid = info.get('container_instance_id')
    cli = container_client(fleet)
    print('Deleting… ', end='', flush=True)
    try:
        cli.delete_container_instance(cid)
        del fleet['users'][principal]
        save_fleet(fleet)
        print(ok('deleted'))
    except Exception as e:
        print(err(f'FAILED: {e}'))


def cmd_status(args, fleet: dict):
    """Show detailed status for one user."""
    principal = args.principal
    info = fleet['users'].get(principal)
    if not info:
        print(err(f'Unknown principal: {principal}'))
        sys.exit(1)

    print(f'\n{BOLD}Container Status{RESET}')
    print(f'  Principal:  {hi(principal)}')
    print(f'  Name:       {info.get("display_name")}')
    print(f'  Container:  {dim(info.get("container_instance_id", "?"))}')
    print(f'  IP:         {info.get("ip", dim("unknown"))}')
    print(f'  Port:       {info.get("port", 8787)}')
    print(f'  Vault PFX:  {info.get("vault_prefix")}')
    print(f'  Created:    {info.get("created_at", "?")[:19]}')

    if HAS_OCI:
        require_oci()
        cid = info.get('container_instance_id')
        cli = container_client(fleet)
        try:
            ci = cli.get_container_instance(cid).data
            state = ci.lifecycle_state
            state_str = ok(state) if state == 'ACTIVE' else warn(state)
            print(f'  OCI State:  {state_str}')
            print(f'  Shape:      {ci.shape}  '
                  f'{getattr(ci.shape_config, "ocpus", "?")} OCPU  '
                  f'{getattr(ci.shape_config, "memory_in_gbs", "?")} GB')

            # Refresh IP if missing
            if not info.get('ip') and ci.vnics:
                try:
                    net_cli = oci.core.VirtualNetworkClient(get_oci_config(fleet))
                    vnic = net_cli.get_vnic(ci.vnics[0].vnic_id).data
                    ip = vnic.public_ip or vnic.private_ip
                    if ip:
                        info['ip'] = ip
                        save_fleet(fleet)
                        print(f'  IP:         {hi(ip)} {dim("(refreshed)")}')
                except Exception as ip_err:
                    print(f'  IP:         {warn(f"resolve failed: {ip_err}")}')
        except Exception as e:
            print(f'  OCI State:  {err(str(e))}')

    # Hit the /health endpoint
    ip = info.get('ip')
    if ip:
        print(f'\n{BOLD}/health probe{RESET}')
        url = f'http://{ip}:{info.get("port", 8787)}/health'
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                health = json.loads(r.read())
            print(f'  Status:     {ok(health.get("status", "?"))}')
            print(f'  Mode:       {health.get("mode")}')
            print(f'  Uptime:     {health.get("uptime_seconds")}s')
            print(f'  Claude CLI: {ok("yes") if health.get("claude_code") else warn("no")}')
            print(f'  Codex CLI:  {ok("yes") if health.get("codex") else warn("no")}')
            print(f'  OCI Vault:  {ok("ready") if health.get("oci_vault_ready") else warn("not ready")}')
        except Exception as e:
            print(f'  {err(str(e))}')


def cmd_health(args, fleet: dict):
    """Quick /health check for a user's container."""
    principal = args.principal
    info = fleet['users'].get(principal)
    if not info:
        print(err(f'Unknown principal: {principal}'))
        sys.exit(1)
    ip = info.get('ip')
    if not ip:
        print(err('No IP recorded. Run status to refresh.'))
        sys.exit(1)
    url = f'http://{ip}:{info.get("port", 8787)}/health'
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            health = json.loads(r.read())
        print(json.dumps(health, indent=2))
    except Exception as e:
        print(err(str(e)))
        sys.exit(1)


def cmd_costs(args, fleet: dict):
    """Estimate monthly compute cost for the fleet."""
    users = fleet['users']
    ocpus     = fleet.get('fleet_ocpus', 1)
    memory_gb = fleet.get('fleet_memory_gb', 6)

    # OCI A1.Flex pricing (us-chicago-1): $0.01/OCPU-hr, $0.0015/GB-hr
    hourly_ocpu   = 0.01
    hourly_mem_gb = 0.0015

    active = sum(1 for u in users.values() if u.get('status') == 'ACTIVE')
    total  = len(users)

    hourly_per_container = (ocpus * hourly_ocpu) + (memory_gb * hourly_mem_gb)
    monthly_per_container = hourly_per_container * 24 * 30

    print(f'\n{BOLD}Fleet Cost Estimate{RESET}')
    print(f'  Shape:              CI.Standard.A1.Flex  '
          f'{ocpus} OCPU / {memory_gb} GB')
    print(f'  $/container/month:  ${monthly_per_container:.2f}  '
          f'(${hourly_per_container:.4f}/hr)')
    print(f'  Total containers:   {total}  ({active} ACTIVE)')
    print(f'  Active cost/month:  {ok(f"${active * monthly_per_container:.2f}")}')
    print(f'  All-on cost/month:  ${total * monthly_per_container:.2f}')
    print()
    print(dim('Notes:'))
    print(dim('  · Stopped containers are NOT billed for compute'))
    print(dim('  · Object Storage: first 20 GB free, then $0.023/GB-month'))
    print(dim('  · Inbound traffic free; outbound ~$0.0085/GB after 10 TB'))
    print(dim('  · Pricing: https://www.oracle.com/cloud/price-list/'))


def cmd_bucket_init(args, fleet: dict):
    """Create the shared vault Object Storage bucket if it doesn't exist."""
    require_oci()
    cli = object_client(fleet)
    ns   = fleet['vault_namespace']
    name = fleet['vault_bucket']
    if not ns:
        print(err('vault_namespace not set in fleet.json / .env'))
        sys.exit(1)

    print(f'Checking bucket {hi(name)} in namespace {hi(ns)}… ', end='', flush=True)
    try:
        cli.get_bucket(ns, name)
        print(ok('already exists'))
        return
    except Exception:
        pass  # bucket doesn't exist, create it

    try:
        cli.create_bucket(
            namespace_name=ns,
            create_bucket_details=oci.object_storage.models.CreateBucketDetails(
                name              = name,
                compartment_id    = fleet['compartment_id'],
                storage_tier      = 'Standard',
                versioning        = 'Disabled',
                freeform_tags     = {'cafresoai': 'fleet-vault'},
            )
        )
        print(ok('created'))
        print(f'  Bucket ARN: {dim(f"oci:///{ns}/{name}")}')
    except Exception as e:
        print(err(f'FAILED: {e}'))
        sys.exit(1)


def _docker_cmd() -> list:
    """Return a docker command prefix that works on this machine.
    Prefers native docker, but only if the daemon is actually responding.
    Falls back to WSL Ubuntu-24.04 docker (no Docker Desktop needed).

    On Windows the Docker Desktop CLI is in PATH even when the daemon is
    stopped — `docker version` then hangs/fails. We probe `docker info`
    with a short timeout to detect this case."""
    import shutil
    if shutil.which('docker'):
        try:
            r = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'],
                               capture_output=True, timeout=8)
            if r.returncode == 0 and r.stdout.strip():
                return ['docker']
        except Exception:
            pass
        # Native CLI present but daemon not responding — try WSL.
    try:
        r = subprocess.run(['wsl', '-d', 'Ubuntu-24.04', '--', 'docker', 'info', '--format', '{{.ServerVersion}}'],
                           capture_output=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return ['wsl', '-d', 'Ubuntu-24.04', '--']
    except Exception:
        pass
    print(err('docker daemon not reachable. Start Docker Desktop, or run:'))
    print('  wsl -d Ubuntu-24.04 -- sudo systemctl start docker')
    sys.exit(1)


def _win_to_wsl(path: pathlib.Path) -> str:
    """Convert a Windows path to a WSL path (e.g. C:\\foo → /mnt/c/foo)."""
    s = str(path).replace('\\', '/')
    if len(s) >= 2 and s[1] == ':':
        drive = s[0].lower()
        s = f'/mnt/{drive}' + s[2:]
    return s


def cmd_ocir_login(args, fleet: dict):
    """Log Docker into OCIR using an OCI auth token.
    Writes credentials directly to Docker config.json (bypasses docker login
    which has shell escaping issues with special-char tokens in WSL)."""
    require_oci()
    import base64 as _b64
    cfg   = get_oci_config(fleet)
    ns    = fleet.get('ocir_namespace') or fleet.get('vault_namespace', '')
    key   = fleet.get('ocir_region_key', 'iad')
    registry = f'{key}.ocir.io'

    # Generate an auth token via OCI Identity
    id_client = oci.identity.IdentityClient(cfg)
    user_id   = cfg['user']
    token_desc = 'cafresoai-fleet-docker-token'

    if getattr(args, 'token', None):
        token = args.token.strip()
        print(f'Using provided auth token (len={len(token)}) {ok("done")}')
    else:
        print(f'Generating OCI auth token for OCIR… ', end='', flush=True)
        try:
            token_resp = id_client.create_auth_token(
                create_auth_token_details=oci.identity.models.CreateAuthTokenDetails(
                    description=token_desc),
                user_id=user_id)
            token = token_resp.data.token
            print(ok('done'))
        except Exception as e:
            print(err(f'FAILED: {e}'))
            print(dim('You can create one manually: OCI Console -> Profile -> Auth Tokens -> Generate Token'))
            print(dim('Then run:  python oci-fleet/fleet-manager.py ocir-login --token <paste>'))
            sys.exit(1)

    username = f'{ns}/{cfg.get("user", "").split("/")[-1]}'
    try:
        user = id_client.get_user(user_id).data
        username = f'{ns}/{user.name}'
    except Exception:
        pass

    # Write credentials directly to Docker config.json
    # (bypasses `docker login` which breaks with special-char tokens in WSL)
    auth_b64 = _b64.b64encode(f'{username}:{token}'.encode()).decode()
    docker_config = json.dumps({'auths': {registry: {'auth': auth_b64}}}, indent=2)

    docker = _docker_cmd()
    using_wsl = docker[0] == 'wsl'

    if using_wsl:
        import tempfile as _tmp
        tmp = os.path.join(_tmp.gettempdir(), 'write_docker_config.sh')
        with open(tmp, 'w', newline='\n') as f:
            f.write('#!/bin/bash\nmkdir -p ~/.docker\n')
            f.write("cat > ~/.docker/config.json <<'CONFIGEOF'\n")
            f.write(docker_config + '\n')
            f.write('CONFIGEOF\n')
        wsl_path = _win_to_wsl(pathlib.Path(tmp))
        result = subprocess.run(['wsl', '-d', 'Ubuntu-24.04', '--', 'bash', wsl_path],
                                capture_output=True, timeout=15)
        os.unlink(tmp)
    else:
        docker_dir = pathlib.Path.home() / '.docker'
        docker_dir.mkdir(exist_ok=True)
        (docker_dir / 'config.json').write_text(docker_config, encoding='utf-8')
        result = type('R', (), {'returncode': 0})()

    if result.returncode == 0:
        print(f'Credentials written for {hi(registry)} as {hi(username)}')
        print(ok('logged in'))
    else:
        print(err('FAILED to write Docker config'))
        print(result.stderr.decode('utf-8', 'replace')[:500])
        sys.exit(1)


def cmd_image_push(args, fleet: dict):
    """Build the Docker image and push it to OCIR.
    Uses WSL Ubuntu-24.04 Docker if native docker isn't available."""
    img       = image_url(fleet)
    repo_root = pathlib.Path(__file__).parent.parent  # openclawhq/
    docker    = _docker_cmd()
    using_wsl = docker[0] == 'wsl'

    # For WSL, paths must be /mnt/c/... style
    build_ctx    = _win_to_wsl(repo_root) if using_wsl else str(repo_root)
    dockerfile   = (_win_to_wsl(repo_root / 'oci-fleet' / 'Dockerfile')
                    if using_wsl else 'oci-fleet/Dockerfile')

    # OCI A1.Flex (free tier) is ARM64. Build for ARM64 by default.
    # Override with --platform=linux/amd64 if running on E-shape x86 instances.
    platform = getattr(args, 'platform', None) or 'linux/arm64'

    print(f'\n{BOLD}Build + push to OCIR (buildx){RESET}')
    print(f'  Image:    {hi(img)}')
    print(f'  Platform: {hi(platform)} {dim("(matches CI.Standard.A1.Flex ARM)" if platform == "linux/arm64" else "")}')
    print(f'  Context:  {dim(build_ctx)}')
    print(f'  Docker:   {dim("WSL Ubuntu-24.04" if using_wsl else "native")}\n')

    # Use docker buildx for cross-arch + integrated push.
    # --provenance=false: OCI Container Instances reject image indexes (multi-manifest);
    #   provenance off forces a plain single-platform manifest.
    # Builder selection:
    #   * On WSL we created the `cafresoai-builder` docker-container driver
    #     (which has its own auth store; ocir-login writes to WSL ~/.docker/config.json
    #     so buildx forwards correctly).
    #   * On native Docker Desktop the default builder shares the host's auth
    #     directly with the Docker daemon, so we don't pass --builder. A custom
    #     docker-container builder there would NOT inherit auth and push fails 401.
    print(f'{BOLD}docker buildx build…{RESET}')
    builder_args = ['--builder', 'cafresoai-builder'] if using_wsl else []
    build_cmd = docker + [
        'docker', 'buildx', 'build',
        *builder_args,
        '--platform', platform,
        '--provenance=false',
        '-t', img,
        '-f', dockerfile,
        '--push',
        build_ctx,
    ] if using_wsl else [
        'docker', 'buildx', 'build',
        *builder_args,
        '--platform', platform,
        '--provenance=false',
        '-t', img,
        '-f', 'oci-fleet/Dockerfile',
        '--push',
        '.',
    ]
    result = subprocess.run(build_cmd, cwd=None if using_wsl else str(repo_root))
    if result.returncode != 0:
        print(err('docker buildx build --push failed'))
        print(dim('  Tip: run ocir-login first if auth errors appear in the build output'))
        sys.exit(1)

    print(ok(f'\nImage pushed: {img}'))


# ── Caddy gateway sync ──────────────────────────────────────────────────────
def _principal_slug(principal: str) -> str:
    """Stable, URL-safe slug for a principal — matches principal_to_prefix()."""
    import hashlib
    return hashlib.sha256(principal.encode()).hexdigest()[:16]


def _render_caddyfile(fleet: dict, primary_host: str) -> str:
    """Render the Caddyfile for the gateway from fleet.json."""
    template_path = pathlib.Path(__file__).parent / 'caddyfile.template'
    template = template_path.read_text(encoding='utf-8')

    user_blocks = []
    user_blocks_http = []
    for principal, info in fleet.get('users', {}).items():
        ip = info.get('ip')
        if not ip:
            continue
        slug = _principal_slug(principal)
        port = info.get('port', 8787)
        user_blocks.append(
            f'    handle_path /u/{slug}/* {{\n'
            f'        reverse_proxy {ip}:{port}\n'
            f'    }}'
        )
        # Same routes also exposed over plain :80 (for IP-based debugging)
        user_blocks_http.append(
            f'    handle_path /u/{slug}/* {{\n'
            f'        reverse_proxy {ip}:{port}\n'
            f'    }}'
        )

    gateway_ip = (fleet.get('gateway') or {}).get('public_ip') or '<unset>'
    # Use simple placeholder replace — `.format()` clashes with Caddy's {...} blocks.
    return (template
        .replace('__PRIMARY_HOST__',     primary_host)
        .replace('__GATEWAY_IP__',       gateway_ip)
        .replace('__USER_ROUTES__',      '\n\n'.join(user_blocks)      or '    # (no users yet)')
        .replace('__USER_ROUTES_HTTP__', '\n\n'.join(user_blocks_http) or '    # (no users yet)')
    )


def cmd_caddy_sync(args, fleet: dict):
    """Render Caddyfile from fleet.json and push it to the gateway VM via SSH."""
    gw = fleet.get('gateway')
    if not gw or not gw.get('public_ip'):
        print(err('No gateway VM in fleet.json. Provision one first.'))
        sys.exit(1)

    host         = gw['public_ip']
    user         = gw.get('ssh_user', 'ubuntu')
    key          = gw.get('ssh_key')
    primary_host = args.host or 'hq.cafreso.com'

    print(f'\n{BOLD}Caddy sync → {hi(host)}{RESET}')
    print(f'  Primary host:  {hi(primary_host)}')
    print(f'  Users routed:  {len([u for u in fleet.get("users", {}).values() if u.get("ip")])}')

    rendered = _render_caddyfile(fleet, primary_host)
    if args.dry_run:
        print(f'\n{BOLD}DRY RUN — Caddyfile contents:{RESET}\n')
        print(rendered)
        return

    # Upload via scp, then reload Caddy via ssh
    import tempfile as _tmp
    tmp = pathlib.Path(_tmp.gettempdir()) / 'cafresoai_Caddyfile'
    tmp.write_text(rendered, encoding='utf-8')

    ssh_opts = ['-o', 'StrictHostKeyChecking=accept-new',
                '-o', 'BatchMode=yes',
                '-o', 'ConnectTimeout=10']
    if key:
        ssh_opts += ['-i', key]

    print('  Uploading Caddyfile…', end=' ', flush=True)
    r = subprocess.run(
        ['scp', *ssh_opts, str(tmp), f'{user}@{host}:/tmp/Caddyfile.new'],
        capture_output=True)
    if r.returncode != 0:
        print(err('FAILED'))
        print(r.stderr.decode('utf-8', 'replace')[:500])
        sys.exit(1)
    print(ok('done'))

    print('  Installing + reloading Caddy…', end=' ', flush=True)
    cmd = ('sudo cp /tmp/Caddyfile.new /etc/caddy/Caddyfile && '
           'sudo caddy validate --config /etc/caddy/Caddyfile && '
           'sudo systemctl reload caddy && '
           'sudo systemctl is-active caddy')
    r = subprocess.run(['ssh', *ssh_opts, f'{user}@{host}', cmd],
                       capture_output=True)
    out = (r.stdout + r.stderr).decode('utf-8', 'replace')
    if r.returncode != 0 or 'active' not in out:
        print(err('FAILED'))
        print(out[:500])
        sys.exit(1)
    print(ok('reloaded'))

    print(f'\n  Probe:  curl http://{host}/healthz   →  expect "ok"')
    print(f'  Once DNS is set:  https://{primary_host}/u/<slug>/hq.html')


def cmd_config(args, fleet: dict):
    """Show current fleet configuration (no secrets)."""
    print(f'\n{BOLD}Fleet Configuration{RESET}')
    skip = {'users', 'version'}
    for k, v in fleet.items():
        if k in skip: continue
        print(f'  {k:25s} {hi(str(v)) if v else dim("(not set)")}')
    print(f'\n  {BOLD}Users:{RESET} {len(fleet.get("users", {}))} provisioned')
    print(f'  {BOLD}Registry:{RESET} {dim(str(FLEET_FILE))}')


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='fleet-manager',
        description='Openclaw HQ — OCI Fleet Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest='command', metavar='COMMAND')

    sub.add_parser('list',       help='List all fleet users + container status')
    sub.add_parser('costs',      help='Show monthly cost estimate for the fleet')
    sub.add_parser('bucket-init',help='Create the vault Object Storage bucket')
    ocir_p = sub.add_parser('ocir-login', help='Log Docker into OCIR (generates auth token automatically)')
    ocir_p.add_argument('--token', help='Use this auth token instead of generating a new one '
                                        '(useful when API token creation hits IDCS limits — '
                                        'paste a token from OCI Console -> Profile -> Auth Tokens)')
    sub.add_parser('config',     help='Show fleet configuration')

    def add_principal(p):
        p.add_argument('principal', help='ICP Internet Identity principal')

    add_principal(sub.add_parser('provision', help='Create a new container for a user'))
    add_principal(sub.add_parser('start',     help='Start a stopped container'))
    add_principal(sub.add_parser('stop',      help='Stop a running container'))
    add_principal(sub.add_parser('delete',    help='Delete a user\'s container'))
    add_principal(sub.add_parser('status',    help='Show detailed container status'))
    add_principal(sub.add_parser('health',    help='Hit /health on the container'))

    push_p = sub.add_parser('image-push', help='Build + push Docker image to OCIR')
    push_p.add_argument('--platform', default='linux/arm64',
                        help='Target platform for the image (default: linux/arm64 to match A1.Flex ARM '
                             'shape). Use linux/amd64 for E-shape x86 instances.')

    cad = sub.add_parser('caddy-sync',
                         help='Render Caddyfile from fleet.json and reload the gateway VM')
    cad.add_argument('--host', default=None,
                     help='Primary HTTPS hostname (default: hq.cafreso.com)')
    cad.add_argument('--dry-run', action='store_true',
                     help='Print the rendered Caddyfile without uploading')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Load .env if present
    env_file = pathlib.Path(__file__).parent / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip())

    fleet = load_fleet()

    dispatch = {
        'list':        cmd_list,
        'provision':   cmd_provision,
        'start':       cmd_start,
        'stop':        cmd_stop,
        'delete':      cmd_delete,
        'status':      cmd_status,
        'health':      cmd_health,
        'costs':       cmd_costs,
        'bucket-init': cmd_bucket_init,
        'ocir-login':  cmd_ocir_login,
        'image-push':  cmd_image_push,
        'caddy-sync':  cmd_caddy_sync,
        'config':      cmd_config,
    }

    fn = dispatch.get(args.command)
    if fn:
        fn(args, fleet)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

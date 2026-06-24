#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CafresoHQ -- OCI Fleet Setup Wizard
Runs AFTER you've added the API key to OCI Console.

Usage:
  cd cafresohq
  python oci-fleet/oci-setup-wizard.py

What it does:
  1. Reads ~/.oci/config
  2. Discovers your tenancy, compartments, VCN subnets, Object Storage namespace
  3. Writes fleet.json and oci-fleet/.env with real values
"""

import json
import os
import pathlib
import sys

try:
    import oci
except ImportError:
    print('ERROR: pip install oci')
    sys.exit(1)

FLEET_DIR  = pathlib.Path(__file__).parent
FLEET_FILE = FLEET_DIR / 'fleet.json'
ENV_FILE   = FLEET_DIR / '.env'

RESET  = '\033[0m'; BOLD = '\033[1m'; GREEN = '\033[32m'
YELLOW = '\033[33m'; RED = '\033[31m'; CYAN = '\033[36m'; GREY = '\033[90m'

def c(t, col): return f'{col}{t}{RESET}'
def ok(s):  return c(s, GREEN)
def hi(s):  return c(s, CYAN)
def dim(s): return c(s, GREY)
def hd(s):  return c(s, BOLD)

print(f'\n{hd("CafresoHQ — OCI Fleet Setup Wizard")}\n')

# ── Load OCI config ───────────────────────────────────────────────────────────
print('Loading ~/.oci/config… ', end='', flush=True)
try:
    cfg = oci.config.from_file()
    print(ok('OK'))
    tenancy_id = cfg['tenancy']
    region     = cfg.get('region', 'us-chicago-1')
    user_id    = cfg['user']
except Exception as e:
    print(f'\n{RED}ERROR:{RESET} {e}')
    print('\nRun the API key setup first:')
    print('  1. Go to OCI Console -> Profile (top-right) -> My Profile')
    print('  2. Left menu -> API Keys -> Add API Key')
    print('  3. Choose "Paste a Public Key"')
    print('  4. Paste the contents of:')
    print(f'     {CYAN}~\\.oci\\oci_api_key_public.pem{RESET}')
    print('  5. Click Add — copy the config snippet shown')
    print('  6. Paste it into ~/.oci/config')
    sys.exit(1)

print(f'  Tenancy:  {hi(tenancy_id[:30])}…')
print(f'  User:     {hi(user_id[:30])}…')
print(f'  Region:   {hi(region)}')


# ── Clients ───────────────────────────────────────────────────────────────────
identity_client  = oci.identity.IdentityClient(cfg)
network_client   = oci.core.VirtualNetworkClient(cfg)
os_client        = oci.object_storage.ObjectStorageClient(cfg)


# ── Object Storage namespace ──────────────────────────────────────────────────
print('\nGetting Object Storage namespace… ', end='', flush=True)
try:
    namespace = os_client.get_namespace().data
    print(ok(namespace))
except Exception as e:
    print(f'{RED}ERROR:{RESET} {e}')
    namespace = ''


# ── Compartments ──────────────────────────────────────────────────────────────
print('\nListing compartments… ', end='', flush=True)
try:
    comps_resp = identity_client.list_compartments(
        tenancy_id, compartment_id_in_subtree=True,
        access_level='ACCESSIBLE', lifecycle_state='ACTIVE')
    compartments = comps_resp.data
    # Add root/tenancy itself
    root = type('C', (), {
        'id': tenancy_id, 'name': '(root tenancy)', 'description': 'Root compartment'
    })()
    all_comps = [root] + compartments
    print(ok(f'{len(all_comps)} found'))
    for i, comp in enumerate(all_comps):
        print(f'  [{i}] {comp.name[:50]:50s}  {dim(comp.id[:30])}…')
except Exception as e:
    print(f'{RED}ERROR:{RESET} {e}')
    all_comps = []

comp_choice = 0
if len(all_comps) > 1:
    try:
        comp_choice = int(input(f'\nSelect compartment number [{0}]: ').strip() or '0')
    except ValueError:
        comp_choice = 0
compartment_id = all_comps[comp_choice].id if all_comps else tenancy_id
print(f'  Using: {hi(all_comps[comp_choice].name if all_comps else "(root)")}')


# ── VCN + Subnets ─────────────────────────────────────────────────────────────
print('\nListing VCNs… ', end='', flush=True)
try:
    vcns = network_client.list_vcns(compartment_id).data
    if not vcns and compartment_id != tenancy_id:
        # also try root
        vcns = network_client.list_vcns(tenancy_id).data
    print(ok(f'{len(vcns)} found'))
    for i, vcn in enumerate(vcns):
        print(f'  [{i}] {vcn.display_name[:40]:40s}  {dim(vcn.id[:30])}…')
except Exception as e:
    print(f'{RED}ERROR:{RESET} {e}')
    vcns = []

subnet_id = ''
availability_domain = 'AD-1'

if vcns:
    vcn_choice = 0
    if len(vcns) > 1:
        try:
            vcn_choice = int(input(f'\nSelect VCN number [0]: ').strip() or '0')
        except ValueError:
            vcn_choice = 0
    vcn = vcns[vcn_choice]

    print(f'\nListing subnets in {vcn.display_name}… ', end='', flush=True)
    try:
        subnets = network_client.list_subnets(compartment_id, vcn_id=vcn.id).data
        if not subnets and compartment_id != tenancy_id:
            subnets = network_client.list_subnets(tenancy_id, vcn_id=vcn.id).data
        print(ok(f'{len(subnets)} found'))
        for i, sn in enumerate(subnets):
            ad = getattr(sn, 'availability_domain', 'regional') or 'regional'
            print(f'  [{i}] {sn.display_name[:35]:35s}  {sn.cidr_block:18s}  {dim(ad)}')
    except Exception as e:
        print(f'{RED}ERROR:{RESET} {e}')
        subnets = []

    if subnets:
        sn_choice = 0
        if len(subnets) > 1:
            try:
                sn_choice = int(input(f'\nSelect subnet number [0]: ').strip() or '0')
            except ValueError:
                sn_choice = 0
        subnet = subnets[sn_choice]
        subnet_id = subnet.id
        ad_raw = getattr(subnet, 'availability_domain', '') or ''
        if ad_raw:
            availability_domain = ad_raw.split(':')[-1] if ':' in ad_raw else ad_raw
        print(f'  Using: {hi(subnet.display_name)}  {subnet.cidr_block}')
    else:
        print(f'\n{YELLOW}No subnets found. You need a VCN + subnet for Container Instances.{RESET}')
        print('  OCI Console -> Networking -> Virtual Cloud Networks -> Create VCN')
        print('  Use "Start VCN Wizard" -> "Create VCN with Internet Connectivity"')
else:
    print(f'\n{YELLOW}No VCNs found. Container Instances need a VCN subnet.{RESET}')
    print('  OCI Console -> Networking -> Virtual Cloud Networks -> Start VCN Wizard')


# ── OCIR region key ───────────────────────────────────────────────────────────
OCIR_KEYS = {
    'us-ashburn-1':    'iad',
    'us-phoenix-1':    'phx',
    'us-chicago-1':    'ord',
    'eu-frankfurt-1':  'fra',
    'eu-amsterdam-1':  'ams',
    'uk-london-1':     'lhr',
    'ap-tokyo-1':      'nrt',
    'ap-sydney-1':     'syd',
    'ca-toronto-1':    'yyz',
    'sa-saopaulo-1':   'gru',
}
ocir_key = OCIR_KEYS.get(region, region.split('-')[1] if '-' in region else 'ord')


# ── Availability Domain ───────────────────────────────────────────────────────
if availability_domain == 'AD-1':
    try:
        ads = identity_client.list_availability_domains(compartment_id).data
        if ads:
            availability_domain = ads[0].name
    except Exception:
        pass


# ── Write fleet.json ──────────────────────────────────────────────────────────
fleet = {
    'version':              '1',
    'compartment_id':       compartment_id,
    'region':               region,
    'subnet_id':            subnet_id,
    'availability_domain':  availability_domain,
    'vault_namespace':      namespace,
    'vault_bucket':         'cafresoai-fleet-vault',
    'ocir_region_key':      ocir_key,
    'ocir_namespace':       namespace,
    'ocir_repo':            'cafresoai-serve',
    'fleet_ocpus':          1.0,
    'fleet_memory_gb':      6.0,
    'users':                {},
}

FLEET_FILE.write_text(json.dumps(fleet, indent=2), encoding='utf-8')
print(f'\n{ok("fleet.json written:")} {dim(str(FLEET_FILE))}')


# ── Write .env ────────────────────────────────────────────────────────────────
env_content = f"""# CafresoHQ OCI Fleet — generated by oci-setup-wizard.py
OCI_TENANCY_ID={tenancy_id}
OCI_COMPARTMENT_ID={compartment_id}
OCI_REGION={region}
OCIR_REGION_KEY={ocir_key}
OCIR_TENANCY_NAMESPACE={namespace}
OCIR_REPO=cafresoai-serve
OCI_SUBNET_ID={subnet_id}
OCI_AVAILABILITY_DOMAIN={availability_domain}
OCI_VAULT_NAMESPACE={namespace}
OCI_VAULT_BUCKET=cafresoai-fleet-vault
FLEET_OCPUS=1
FLEET_MEMORY_GB=6
FLEET_REGISTRY=oci-fleet/fleet.json
"""
ENV_FILE.write_text(env_content, encoding='utf-8')
print(f'{ok(".env written:")} {dim(str(ENV_FILE))}')


# ── Summary ───────────────────────────────────────────────────────────────────
print(f'\n{hd("Setup complete!")}')
print(f'\nNext steps:')
print(f'  1. {hi("python oci-fleet/fleet-manager.py config")}       — verify config')
print(f'  2. {hi("python oci-fleet/fleet-manager.py bucket-init")}   — create vault bucket')
print(f'  3. {hi("python oci-fleet/fleet-manager.py image-push")}    — build + push Docker image')
print(f'  4. {hi("python oci-fleet/fleet-manager.py provision <principal>")}')
print()
if not subnet_id:
    print(f'{YELLOW}WARNING:{RESET} No subnet selected — Container Instances will fail.')
    print('  Create a VCN first, then re-run this wizard.')

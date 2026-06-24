#!/usr/bin/env python3
"""
Regression test for the Fleet API admin-auth gate (_check_auth).

Guards the fail-closed contract: with no FLEET_API_SECRET, admin-gated routes are
DENIED unless FLEET_DEV_MODE=1 is explicitly set. A forgotten secret in prod must
never silently open provision/delete to the world.

Runs under pytest or plain `python3 oci-fleet/test_fleet_auth.py`.
"""
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(env):
    """Import a fresh copy of fleet-api.py with the given env vars."""
    for k in ('FLEET_API_SECRET', 'FLEET_DEV_MODE'):
        os.environ.pop(k, None)
    os.environ.update(env)
    spec = importlib.util.spec_from_file_location(
        "fleetapi_%d" % (len(env) + sum(len(v) for v in env.values())),
        os.path.join(HERE, "fleet-api.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _FakeHeaders(dict):
    def get(self, k, d=None):
        return super().get(k, d)


def _auth(m, hdr=None):
    h = types.SimpleNamespace(headers=_FakeHeaders(hdr or {}))
    return m.Handler._check_auth(h)


def test_no_secret_no_dev_denies():
    assert _auth(_load({})) is False


def test_dev_mode_allows():
    assert _auth(_load({'FLEET_DEV_MODE': '1'})) is True


def test_secret_requires_matching_header():
    m = _load({'FLEET_API_SECRET': 'supersecret'})
    assert _auth(m) is False                                   # no header
    assert _auth(m, {'X-Fleet-Auth': 'nope'}) is False         # wrong header
    assert _auth(m, {'X-Fleet-Auth': 'supersecret'}) is True   # correct header


if __name__ == '__main__':
    test_no_secret_no_dev_denies()
    test_dev_mode_allows()
    test_secret_requires_matching_header()
    print('OK — fleet-api _check_auth fails closed without a secret')

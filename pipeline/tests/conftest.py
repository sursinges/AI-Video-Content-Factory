"""Test isolation from the owner's local runtime flags.

config/ui_settings.yaml is a local, gitignored file — the suite must not
depend on it. By default every test sees the local single-owner mode
(hosted machinery off) when running against the real workspace; tests that
need hosted mode patch srv.WORKSPACE to their own tmp workspace and keep
their own flags (test_tenants, test_workers, test_editions).
"""

from pathlib import Path

import pytest

_REAL_WS = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _force_local_mode_on_real_workspace(monkeypatch):
    from core import tenants

    orig = tenants.read_flags

    def _patched(workspace):
        try:
            if Path(workspace).resolve() == _REAL_WS.resolve():
                return {"hosted_mode": False, "registration_open": False}
        except Exception:  # noqa: BLE001
            pass
        return orig(workspace)

    monkeypatch.setattr(tenants, "read_flags", _patched)

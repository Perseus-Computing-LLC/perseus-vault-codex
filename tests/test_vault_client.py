"""Regression tests for vault subprocess transport recovery."""

from __future__ import annotations

import io

import pytest

from perseus_vault_codex._vault_client import VaultClient, VaultError


class _ClosingProcess:
    """A process whose stdout closes while the process still appears live."""

    def __init__(self) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("")
        self.terminated = False

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None) -> int:
        return 0

    def kill(self) -> None:
        self.terminated = True


def test_closed_stdout_tears_down_process_for_next_call():
    """EOF must clear the process so a later call can auto-respawn it."""
    client = VaultClient(binary="perseus-vault", db_path="unused.db")
    proc = _ClosingProcess()
    client._proc = proc

    with pytest.raises(VaultError, match="closed stdout unexpectedly"):
        client._request("tools/list", {})

    assert proc.terminated is True
    assert client._proc is None

"""Protocol-level tests for the MCP stdio server (Codex-facing side)."""

from __future__ import annotations

import io
import json

from perseus_vault_codex import __version__
from perseus_vault_codex.server import CodexMemoryServer
from perseus_vault_codex.tools import Tools

from tests.conftest import FakeVaultClient


def _server(fake_config, client=None):
    srv = CodexMemoryServer(config=fake_config)
    # Inject the fake vault so no binary is spawned.
    client = client or FakeVaultClient()
    srv._client = client
    srv._tools = Tools(client, fake_config)
    return srv, client


def test_initialize_advertises_protocol_and_server(fake_config):
    srv, _ = _server(fake_config)
    resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "perseus-vault-codex"
    assert result["serverInfo"]["version"] == __version__
    assert "tools" in result["capabilities"]


def test_initialized_notification_has_no_response(fake_config):
    srv, _ = _server(fake_config)
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_exposes_exactly_five_curated_tools(fake_config):
    srv, _ = _server(fake_config)
    resp = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {
        "perseus_remember",
        "perseus_recall",
        "perseus_forget",
        "perseus_reflect",
        "perseus_status",
    }
    # Every tool has a JSON Schema with a type.
    for t in resp["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"


def test_tools_call_roundtrip_remember_then_recall(fake_config):
    srv, _ = _server(fake_config)
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "perseus_remember",
            "arguments": {"text": "Deploy with make ship", "key": "deploy"},
        },
    }
    resp = srv.handle(call)
    payload = resp["result"]["structuredContent"]
    assert payload["status"] == "ok"
    # The text block mirrors the structured content (MCP envelope contract).
    assert "Deploy with make ship" not in payload  # sanity: payload is the summary
    assert resp["result"]["content"][0]["type"] == "text"

    recall = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "perseus_recall", "arguments": {"query": "deploy"}},
    }
    r2 = srv.handle(recall)["result"]["structuredContent"]
    assert r2["count"] == 1
    assert r2["memories"][0]["text"] == "Deploy with make ship"


def test_unknown_method_returns_method_not_found(fake_config):
    srv, _ = _server(fake_config)
    resp = srv.handle({"jsonrpc": "2.0", "id": 9, "method": "does/not/exist", "params": {}})
    assert resp["error"]["code"] == -32601


def test_malformed_jsonrpc_request_returns_invalid_request(fake_config):
    srv, _ = _server(fake_config)
    resp = srv.handle(
        {"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": []}
    )
    assert resp["id"] is None
    assert resp["error"]["code"] == -32600


def test_tool_error_becomes_jsonrpc_error_not_crash(fake_config):
    srv, _ = _server(fake_config)
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "perseus_remember", "arguments": {"text": ""}},
        }
    )
    assert "error" in resp
    assert resp["error"]["code"] == -32603


def test_serve_loop_over_stdio_streams(fake_config):
    """Drive the full serve() loop with fake stdin/stdout streams."""
    srv, _ = _server(fake_config)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    stdout = io.StringIO()
    srv.serve(stdin=stdin, stdout=stdout)
    out_lines = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
    # initialize + tools/list => 2 responses (the notification produced none).
    assert len(out_lines) == 2
    assert out_lines[0]["id"] == 1
    assert out_lines[1]["id"] == 2

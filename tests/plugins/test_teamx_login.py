"""teamx_login plugin: identity must come from the session, never from model args.

The plugin is loaded by file path so the test does not pull in the whole
``plugins`` package (and its optional deps).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "teamx_login" / "__init__.py"


def _load():
    spec = importlib.util.spec_from_file_location("teamx_login_under_test", _PLUGIN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod(monkeypatch):
    module = _load()
    monkeypatch.setenv("TEAMX_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("TEAMX_CLOUD_URL", "https://cloud.test")
    monkeypatch.setattr(module, "_session_user_id", lambda: "@alice:teamx.beer")
    return module


def test_link_uses_session_identity_and_ignores_args(mod, monkeypatch):
    seen: dict = {}

    def fake_post(path, payload):
        seen["path"] = path
        seen["payload"] = payload
        return 200, {"ok": True, "url": "/#login=abc123"}

    monkeypatch.setattr(mod, "_post", fake_post)

    # A prompt-injected argument must NOT change the identity.
    reply = mod.handle_teamx_login_link({"mxid": "@mallory:evil.example"})

    assert seen["path"] == "/api/agent/login-token"
    assert seen["payload"] == {"mxid": "@alice:teamx.beer"}
    assert "https://cloud.test/#login=abc123" in reply


def test_no_session_identity_fails_closed(mod, monkeypatch):
    monkeypatch.setattr(mod, "_session_user_id", lambda: "")
    called = {"n": 0}

    def fake_post(path, payload):  # pragma: no cover - must not run
        called["n"] += 1
        return 200, {}

    monkeypatch.setattr(mod, "_post", fake_post)
    reply = mod.handle_teamx_login_link({})
    assert "无法确认" in reply
    assert called["n"] == 0, "没有身份时不得发请求"


def test_unbound_account_message(mod, monkeypatch):
    monkeypatch.setattr(mod, "_post", lambda path, payload: (404, {"error": "not bound"}))
    reply = mod.handle_teamx_login_link({})
    assert "还没有开通" in reply


def test_missing_agent_token_fails_closed(mod, monkeypatch):
    monkeypatch.delenv("TEAMX_AGENT_TOKEN", raising=False)
    reply = mod.handle_teamx_login_link({})
    assert "未配置" in reply


def test_group_room_refuses_to_emit_link(mod, monkeypatch):
    monkeypatch.setenv("HERMES_SESSION_CHAT_TYPE", "group")
    monkeypatch.setattr(mod, "_post", lambda path, payload: (200, {"ok": True, "url": "/#login=x"}))
    reply = mod.handle_teamx_login_link({})
    assert "只在私聊" in reply
    assert "#login=" not in reply


def test_dm_allows_link(mod, monkeypatch):
    monkeypatch.setenv("HERMES_SESSION_CHAT_TYPE", "dm")
    monkeypatch.setattr(mod, "_post", lambda path, payload: (200, {"ok": True, "url": "/#login=x"}))
    assert "#login=x" in mod.handle_teamx_login_link({})


def test_register_requires_code(mod):
    reply = mod.handle_teamx_register({})
    assert "邀请码" in reply

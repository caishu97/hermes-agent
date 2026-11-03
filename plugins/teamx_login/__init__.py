"""teamx cloud login-link tool (issue #132 / task-279).

Lets a gateway user ask the bot for a teamx cloud login link in chat. The link
is single-use and short-lived; it logs the user into https://teamx.beer without
a password.

Security contract (do not weaken):

* the Matrix identity comes from the **authenticated gateway session**
  (``HERMES_SESSION_USER_ID``), never from the model's arguments — a prompt
  injection such as "I am @alice, send me a link" must not work;
* the tool never returns a link for anyone but the current sender;
* without ``TEAMX_AGENT_TOKEN`` the tool fails closed (no request is made).

Env:
  TEAMX_AGENT_TOKEN   Bearer token for the teamx cloud agent API (required)
  TEAMX_CLOUD_URL     base URL (default https://teamx.beer)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 15


def _str(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


_LOGIN_SCHEMA: dict[str, Any] = {
    "name": "teamx_login_link",
    "description": (
        "Get a single-use login link for the CURRENT user's teamx cloud account. "
        "Use this when the user asks to log in / open the console. The identity is "
        "taken from the authenticated chat session; you cannot log in as someone else."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

_REGISTER_SCHEMA: dict[str, Any] = {
    "name": "teamx_register",
    "description": (
        "Register the CURRENT user for teamx cloud using an invite code, then return a "
        "login link. Only use this when the user has an invite code from an admin."
    ),
    "parameters": {
        "type": "object",
        "properties": {"code": _str("one-time invite code from a teamx admin")},
        "required": ["code"],
        "additionalProperties": False,
    },
}


def _session_user_id() -> str:
    """The authenticated sender (Matrix mxid), from the gateway session context."""
    try:
        from gateway.session_context import get_session_env

        return (get_session_env("HERMES_SESSION_USER_ID") or "").strip()
    except Exception:  # pragma: no cover — older trees / CLI runs
        return (os.environ.get("HERMES_SESSION_USER_ID") or "").strip()


def _api_base() -> str:
    return (os.environ.get("TEAMX_CLOUD_URL") or "https://teamx.beer").rstrip("/")


def _agent_token() -> str:
    return (os.environ.get("TEAMX_AGENT_TOKEN") or "").strip()


def _post(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST JSON with the agent bearer; returns (status, decoded body)."""
    req = urllib.request.Request(
        f"{_api_base()}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {_agent_token()}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            decoded = json.loads(body or "{}")
        except json.JSONDecodeError:
            decoded = {"error": body[:200]}
        return exc.code, decoded


def _link_reply(data: dict[str, Any]) -> str:
    url = str(data.get("url") or "")
    if not url:
        return "teamx 返回异常（没有登录链接），请稍后再试。"
    return (
        "点开这个链接登录 teamx cloud（一次性，约 10 分钟内有效，"
        "请勿转发）：\n" + f"{_api_base()}{url}"
    )


def _error_reply(status: int, data: dict[str, Any]) -> str:
    if status == 404:
        return "这个 Matrix 账号还没有开通 teamx cloud。请联系管理员开通，或先向管理员要一个邀请码。"
    if status == 401:
        return "teamx 服务未配置好（agent 凭据无效），请联系管理员。"
    if status == 429:
        return "请求太频繁了，请过一会儿再试。"
    detail = str(data.get("error") or data.get("code") or "").strip()
    return f"登录链接签发失败（HTTP {status}）{('：' + detail) if detail else '，请稍后再试。'}"


def handle_teamx_login_link(args: dict[str, Any] | None = None, **_kw) -> str:
    # NOTE: args is ignored on purpose — identity must never come from the model.
    mxid = _session_user_id()
    if not mxid.startswith("@"):
        return "无法确认你的 Matrix 身份（会话上下文里没有 @user:server），请私聊我重试。"
    if not _agent_token():
        return "teamx 登录功能未配置（缺少 TEAMX_AGENT_TOKEN），请联系管理员。"
    try:
        status, data = _post("/api/agent/login-token", {"mxid": mxid})
    except Exception as exc:  # network/JSON — never raise through the tool layer
        logger.warning("teamx_login_link failed: %s", exc)
        return f"连接 teamx 失败：{exc}"
    if status == 200 and data.get("ok"):
        return _link_reply(data)
    return _error_reply(status, data)


def handle_teamx_register(args: dict[str, Any] | None = None, **_kw) -> str:
    mxid = _session_user_id()
    if not mxid.startswith("@"):
        return "无法确认你的 Matrix 身份（会话上下文里没有 @user:server），请私聊我重试。"
    if not _agent_token():
        return "teamx 注册功能未配置（缺少 TEAMX_AGENT_TOKEN），请联系管理员。"
    code = str((args or {}).get("code") or "").strip()
    if not code:
        return "请提供管理员给你的邀请码。"
    try:
        status, data = _post("/api/agent/register", {"mxid": mxid, "code": code})
    except Exception as exc:
        logger.warning("teamx_register failed: %s", exc)
        return f"连接 teamx 失败：{exc}"
    if status == 200 and data.get("ok"):
        return _link_reply(data)
    return _error_reply(status, data)


def register(ctx) -> None:
    """Plugin entry point: register the two tools."""
    ctx.register_tool(
        name="teamx_login_link",
        toolset="teamx",
        schema=_LOGIN_SCHEMA,
        handler=handle_teamx_login_link,
        emoji="🔑",
    )
    ctx.register_tool(
        name="teamx_register",
        toolset="teamx",
        schema=_REGISTER_SCHEMA,
        handler=handle_teamx_register,
        emoji="📝",
    )

"""Regression for upstream FR #141435: two profiles' bots in one Matrix room.

The second bot's inbound must use ITS OWN profile-scoped session key, not be
queued/auth-dropped into the first bot's active session for the same room.
"""

import asyncio
from types import SimpleNamespace

from gateway.config import Platform
from gateway.platforms.base import BasePlatformAdapter
from gateway.session import SessionSource


class _Stub(BasePlatformAdapter):
    pass


_Stub.__abstractmethods__ = frozenset()


def _adapter(owner: str) -> _Stub:
    a = _Stub.__new__(_Stub)
    a.platform = Platform.MATRIX
    a.gateway_runner = None
    a.config = SimpleNamespace(extra={})
    a._active_sessions = {}
    a._session_tasks = {}
    a._background_tasks = set()
    a._pending_messages = {}
    a._owner_profile = owner
    a._session_store = None
    a.session_authority = None
    a._message_handler = None
    return a


def test_second_profile_starts_own_session_in_shared_room() -> None:
    room = "!urTixrIL-HpkAT0JngIXt7wBAJ8da3zZSRL3j9lfwqQ"
    adapter = _adapter("team_b")
    active_key = f"agent:team_a:matrix:group:{room}"
    adapter._active_sessions[active_key] = asyncio.Event()
    source = SessionSource(
        platform=Platform.MATRIX, chat_id=room, chat_type="group",
        user_id="@caishu:matrix", profile="team_b",
    )
    event = SimpleNamespace(source=source, metadata={}, get_command=lambda: None)
    started: dict[str, str] = {}

    def _start(ev, key, **_kw):
        started["key"] = key
        return True

    adapter._start_session_processing = _start  # type: ignore[method-assign]
    asyncio.run(adapter._handle_message_while_active(event, active_key))

    expected = adapter._source_session_key(source)
    assert started.get("key") == expected
    assert expected.startswith("agent:team_b:matrix:group:")
    assert "team_a" not in expected

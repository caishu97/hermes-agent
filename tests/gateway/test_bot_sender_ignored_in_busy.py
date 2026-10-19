"""Bot-to-bot messages must be ignored before the human auth gate (#141435)."""

import asyncio
from types import SimpleNamespace

from gateway.run_busy import GatewayBusySessionMixin


def test_bot_message_is_silently_ignored_while_busy() -> None:
    runner = object.__new__(GatewayBusySessionMixin)
    event = SimpleNamespace(
        source=SimpleNamespace(is_bot=True, platform="matrix", user_id="@hermes-ent:matrix")
    )
    handled = asyncio.run(
        runner._handle_active_session_busy_message(event, "agent:teamx-cloud-ops:matrix:group:!r")
    )
    assert handled is True

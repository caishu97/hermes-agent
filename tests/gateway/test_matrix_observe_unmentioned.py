"""observe_unmentioned: unmentioned room messages are kept as context, never replied to."""

from gateway.authz_mixin import _ALLOW_BOTS_ENV
from gateway.config import Platform
from plugins.platforms.matrix.adapter import MatrixAdapter


def _bare_adapter() -> MatrixAdapter:
    adapter = object.__new__(MatrixAdapter)
    adapter._observed_messages = {}
    return adapter


def test_observed_messages_become_context_once() -> None:
    adapter = _bare_adapter()
    adapter._record_observed("!room", "botA", "hello")
    adapter._record_observed("!room", "botB", "world")

    context = adapter._take_observed("!room")
    assert "[room context" in context
    assert "botA: hello" in context
    assert "botB: world" in context
    assert adapter._take_observed("!room") == ""  # consumed, no duplicate context


def test_matrix_bots_can_be_admitted_by_mention() -> None:
    assert _ALLOW_BOTS_ENV[Platform.MATRIX] == "MATRIX_ALLOW_BOTS"

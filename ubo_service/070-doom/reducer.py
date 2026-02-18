from __future__ import annotations

from immutable import Immutable
from redux import InitAction, InitializationActionError


class DoomState(Immutable):
    is_loaded: bool = False


def reducer(state: DoomState | None, action: object) -> DoomState:
    if state is None:
        if isinstance(action, InitAction):
            return DoomState(is_loaded=True)
        raise InitializationActionError(action)
    return state

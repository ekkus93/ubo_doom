from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ubo_handle import ReducerRegistrar, register


async def setup(register_reducer: ReducerRegistrar) -> list[object]:
    """Register the reducer, then return service cleanup subscriptions to Ubo."""
    from reducer import reducer

    register_reducer(reducer)

    from setup import init_service

    return init_service()


register(
    service_id="doom",
    label="Doom",
    setup=setup,
    is_enabled=True,
)

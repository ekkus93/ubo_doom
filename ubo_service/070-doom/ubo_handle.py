from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ubo_handle import ReducerRegistrar, register


async def setup(register_reducer: ReducerRegistrar) -> None:
    # Minimal reducer registration to satisfy service startup barriers.
    from reducer import reducer

    register_reducer(reducer)

    from setup import init_service

    init_service()


register(
    service_id="doom",
    label="Doom",
    setup=setup,
    # Enabled for initial testing. Disable if you don't want it loaded by default.
    is_enabled=True,
)

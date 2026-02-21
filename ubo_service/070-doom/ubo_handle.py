from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ubo_handle import ReducerRegistrar, register


async def setup(register_reducer: ReducerRegistrar) -> None:
    # Minimal reducer registration to satisfy service startup barriers.
    from reducer import reducer

    register_reducer(reducer)

    import traceback

    try:
        from setup import init_service
        print("[doom] calling init_service()", flush=True)
        init_service()
        print("[doom] init_service() completed OK", flush=True)
    except Exception:
        print("[doom] init_service() FAILED:\n" + traceback.format_exc(), flush=True)


register(
    service_id="doom",
    label="Doom",
    setup=setup,
    # Enabled for initial testing. Disable if you don't want it loaded by default.
    is_enabled=True,
)

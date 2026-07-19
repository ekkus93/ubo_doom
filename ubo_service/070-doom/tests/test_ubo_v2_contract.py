"""Contract tests for the Ubo v2 service-facing API used by setup.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


class ValueObject:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class FakeLogger:
    def debug(self, *_args: Any, **_kwargs: Any) -> None: ...
    def info(self, *_args: Any, **_kwargs: Any) -> None: ...
    def error(self, *_args: Any, **_kwargs: Any) -> None: ...
    def exception(self, *_args: Any, **_kwargs: Any) -> None: ...


class FakeStore:
    def __init__(self) -> None:
        self.dispatched: list[object] = []
        self.subscriptions: list[tuple[type, object]] = []

    def dispatch(self, *actions: object) -> None:
        self.dispatched.extend(actions)

    def _dispatch(self, actions: list[object]) -> None:
        self.dispatched.extend(actions)

    def subscribe_event(self, event_type: type, handler: object):
        self.subscriptions.append((event_type, handler))
        return lambda: None


class FakeSession:
    def __init__(self) -> None:
        self.is_visible = False
        self.calls: list[object] = []

    def resume(self) -> None:
        self.is_visible = True
        self.calls.append("resume")

    def pause(self) -> None:
        self.is_visible = False
        self.calls.append("pause")

    def close(self) -> None:
        self.calls.append("close")

    def go_up(self) -> None:
        self.calls.append("up")

    def go_down(self) -> None:
        self.calls.append("down")

    def button(self, index: int) -> None:
        self.calls.append(("button", index))


@pytest.fixture()
def contract_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    service_dir = Path(__file__).parents[1]
    monkeypatch.syspath_prepend(str(service_dir))
    monkeypatch.setenv("UBO_DOOM_CWD", str(tmp_path / "doom"))
    monkeypatch.setenv("UBO_DOOM_CONFIG", str(tmp_path / "doom" / "doomrc.cfg"))

    fake_store = FakeStore()
    action_registry: dict[str, object] = {}

    modules = {
        "ubo_app": ModuleType("ubo_app"),
        "ubo_app.logger": ModuleType("ubo_app.logger"),
        "ubo_app.store": ModuleType("ubo_app.store"),
        "ubo_app.store.core": ModuleType("ubo_app.store.core"),
        "ubo_app.store.core.action_registry": ModuleType(
            "ubo_app.store.core.action_registry"
        ),
        "ubo_app.store.core.types": ModuleType("ubo_app.store.core.types"),
        "ubo_app.store.main": ModuleType("ubo_app.store.main"),
    }
    modules["ubo_app.logger"].logger = FakeLogger()

    def register_action(
        action_id: str,
        handler: object,
        *,
        allow_reregister: bool = False,
    ) -> object:
        if action_id in action_registry and not allow_reregister:
            raise ValueError(action_id)
        action_registry[action_id] = handler
        return handler

    def unregister_action(action_id: str) -> bool:
        return action_registry.pop(action_id, None) is not None

    modules["ubo_app.store.core.action_registry"].register_action = register_action
    modules["ubo_app.store.core.action_registry"].unregister_action = unregister_action

    type_names = (
        "ApplicationScrollEvent",
        "FrameStreamDataEvent",
        "MenuChooseByIndexEvent",
        "MenuItemData",
        "OpenRenderAction",
        "RegisterRegularAppAction",
        "RenderStackItem",
        "StackChangedEvent",
        "StackPopAction",
        "UpdateRenderPropsAction",
    )
    for name in type_names:
        setattr(
            modules["ubo_app.store.core.types"], name, type(name, (ValueObject,), {})
        )

    modules["ubo_app.store.main"].store = fake_store
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "doom_setup_contract"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, service_dir / "setup.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    yield module, fake_store, action_registry

    sys.modules.pop(module_name, None)


def test_service_registration_uses_serializable_v2_action(
    contract_module: tuple[ModuleType, FakeStore, dict[str, object]],
) -> None:
    module, store, registry = contract_module

    cleanup = module.init_service()

    registration = store.dispatched[-1]
    assert type(registration).__name__ == "RegisterRegularAppAction"
    assert registration.key == "doom"
    assert registration.label == "Doom"
    assert registration.action_id == "doom:open"
    assert not hasattr(registration, "menu_item")
    assert "doom:open" in registry
    assert len(cleanup) == 5


def test_open_action_uses_generic_frame_stream(
    contract_module: tuple[ModuleType, FakeStore, dict[str, object]],
) -> None:
    module, store, registry = contract_module
    fake_session = FakeSession()
    module._session = fake_session
    module.init_service()

    registry["doom:open"]()

    action = store.dispatched[-1]
    assert type(action).__name__ == "OpenRenderAction"
    assert action.kind == "frame_stream"
    assert action.stream_id == "doom:video"
    assert len(action.items) == 3
    assert fake_session.calls == ["resume"]


def test_current_view_guards_key_and_scroll_events(
    contract_module: tuple[ModuleType, FakeStore, dict[str, object]],
) -> None:
    module, _store, _registry = contract_module
    fake_session = FakeSession()
    module._session = fake_session

    doom_item = module.RenderStackItem(stream_id="doom:video")
    other_item = module.RenderStackItem(stream_id="camera:viewfinder")

    module._handle_stack_changed(module.StackChangedEvent(stack=(doom_item,)))
    module._handle_scroll(module.ApplicationScrollEvent(direction="up"))
    module._handle_scroll(module.ApplicationScrollEvent(direction="down"))
    module._handle_button(module.MenuChooseByIndexEvent(index=2))
    module._handle_stack_changed(module.StackChangedEvent(stack=(other_item,)))
    module._handle_button(module.MenuChooseByIndexEvent(index=1))

    assert fake_session.calls == [
        "resume",
        "up",
        "down",
        ("button", 2),
        "pause",
    ]


class FakeDoom:
    """Records key_down/key_up so _drain_inputs behavior can be asserted."""

    def __init__(self) -> None:
        self.events: list[tuple[str, int]] = []

    def key_down(self, key: int) -> None:
        self.events.append(("down", int(key)))

    def key_up(self, key: int) -> None:
        self.events.append(("up", int(key)))


def test_reverse_turn_releases_opposite_turn_key(
    contract_module: tuple[ModuleType, FakeStore, dict[str, object]],
) -> None:
    # Turning left then quickly right must release LEFT before RIGHT goes down,
    # otherwise both turn keys are held at once and the player doesn't turn.
    module, _store, _registry = contract_module
    session = module.DoomSession()
    doom = FakeDoom()
    UboKey = module.UboKey

    session._queue.put_nowait((UboKey.LEFT, 12))
    session._queue.put_nowait((UboKey.RIGHT, 12))
    session._drain_inputs(doom)

    assert doom.events == [
        ("down", int(UboKey.LEFT)),
        ("up", int(UboKey.LEFT)),
        ("down", int(UboKey.RIGHT)),
    ]
    assert UboKey.LEFT not in session._held
    assert session._held[UboKey.RIGHT] == 12

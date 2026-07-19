"""Ubo v2 service integration for embedded Doom."""

from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Final

import numpy as np
from ubo_app.logger import logger
from ubo_app.store.core.action_registry import register_action, unregister_action
from ubo_app.store.core.types import (
    ApplicationScrollEvent,
    FrameStreamDataEvent,
    MenuChooseByIndexEvent,
    MenuItemData,
    OpenRenderAction,
    RegisterRegularAppAction,
    RenderStackItem,
    StackChangedEvent,
    StackPopAction,
)
from ubo_app.store.main import store

from doom_controller import DoomController
from doom_video import OUT_H, OUT_W, DoomVideoPipe
from native.doom_lib import DoomLib, UboKey

DOOM_STREAM_ID: Final = "doom:video"
DOOM_OPEN_ACTION_ID: Final = "doom:open"
DOOM_RENDER_ITEMS: Final = (
    MenuItemData(key="doom:mode", label="MODE", icon=""),
    MenuItemData(key="doom:left-use", label="LEFT/USE", icon=""),
    MenuItemData(key="doom:right-fire", label="RIGHT/FIRE", icon=""),
)
_OPPOSITE: Final = {
    UboKey.UP: UboKey.DOWN,
    UboKey.DOWN: UboKey.UP,
    # Turning: releasing the opposite turn key first keeps a quick reverse-turn
    # from being swallowed while the previous turn is still held (12-tick hold).
    UboKey.LEFT: UboKey.RIGHT,
    UboKey.RIGHT: UboKey.LEFT,
}


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric, got {raw!r}") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _paths() -> tuple[Path, Path, Path]:
    iwad = Path(
        os.environ.get("UBO_DOOM_IWAD", str(Path.home() / "doom" / "doom2.wad"))
    ).expanduser().resolve()
    cwd_raw = os.environ.get("UBO_DOOM_CWD", "").strip()
    cwd = Path(cwd_raw).expanduser().resolve() if cwd_raw else iwad.parent
    config_raw = os.environ.get("UBO_DOOM_CONFIG", "").strip()
    config = (
        Path(config_raw).expanduser().resolve()
        if config_raw
        else cwd / "doomrc.cfg"
    )
    return iwad, cwd, config


def _is_doom_top(stack: tuple[object, ...]) -> bool:
    return bool(stack) and isinstance(stack[-1], RenderStackItem) and (
        stack[-1].stream_id == DOOM_STREAM_ID
    )


class DoomSession:
    """Own the native engine and publish frames while the Doom view is visible."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._queue: queue.Queue[tuple[UboKey, int]] = queue.Queue()
        self._controller = DoomController(tap_fn=self._tap)
        self._held: dict[UboKey, int] = {}
        self._stop = threading.Event()
        self._tick_thread: threading.Thread | None = None
        self._init_thread: threading.Thread | None = None
        self._doom: DoomLib | None = None
        self._video: DoomVideoPipe | None = None
        self._rgba: np.ndarray | None = None
        self._visible = False
        self._closed = False

        self._fps = _positive_float("UBO_DOOM_FPS", 30.0)
        render_fps = min(self._fps, _positive_float("UBO_DOOM_RENDER_FPS", 15.0))
        self._render_every = max(1, round(self._fps / render_fps))
        self._lib = Path(
            os.environ.get(
                "UBO_DOOM_LIB", str(Path.home() / "doom" / "libubodoom.so")
            )
        ).expanduser().resolve()
        self._iwad, self._cwd, self._config = _paths()
        self._cwd.mkdir(parents=True, exist_ok=True)
        self._config.parent.mkdir(parents=True, exist_ok=True)
        os.environ["UBO_DOOM_CWD"] = str(self._cwd)
        os.environ["UBO_DOOM_CONFIG"] = str(self._config)

    @property
    def is_visible(self) -> bool:
        with self._lock:
            return self._visible

    def resume(self) -> None:
        with self._lock:
            if self._closed:
                logger.error("[doom] cannot resume closed session")
                return
            self._visible = True
            ready = self._doom is not None and self._video is not None
            initializing = self._init_thread is not None and self._init_thread.is_alive()
        if ready:
            self._start_tick()
        elif not initializing:
            thread = threading.Thread(target=self._initialize, daemon=True, name="doom-init")
            with self._lock:
                self._init_thread = thread
            thread.start()

    def pause(self) -> None:
        with self._lock:
            self._visible = False
            self._stop.set()
            thread = self._tick_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if thread.is_alive():
                logger.error("[doom] tick thread did not stop")
            else:
                self._release_all()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            init_thread = self._init_thread
        self.pause()
        if init_thread and init_thread is not threading.current_thread():
            init_thread.join(timeout=5.0)
        with self._lock:
            doom = self._doom
            self._doom = None
            self._video = None
            self._rgba = None
        if doom:
            try:
                doom.shutdown()
            except Exception:
                logger.exception("[doom] shutdown failed")

    def go_up(self) -> None:
        self._controller.go_up()

    def go_down(self) -> None:
        self._controller.go_down()

    def button(self, index: int) -> None:
        if index == 0:
            self._controller.toggle_mode()
        elif index == 1:
            self._controller.btn_l2()
        elif index == 2:
            self._controller.btn_l3()

    def _initialize(self) -> None:
        doom: DoomLib | None = None
        try:
            if not self._lib.is_file():
                raise FileNotFoundError(f"libubodoom.so not found: {self._lib}")
            if not self._iwad.is_file():
                raise FileNotFoundError(f"Doom IWAD not found: {self._iwad}")
            logger.info(
                "[doom] initializing: lib=%s iwad=%s cwd=%s",
                self._lib,
                self._iwad,
                self._cwd,
            )
            doom = DoomLib(self._lib)
            if not doom.has_usergame:
                logger.warning(
                    "[doom] libubodoom.so lacks doom_get_usergame — attract demos "
                    "will be treated as gameplay and the menu button may not open "
                    "the menu; rebuild and redeploy the native library"
                )
            doom.init(str(self._iwad))
            fb = doom.framebuffer_info()
            if fb.width <= 0 or fb.height <= 0:
                raise RuntimeError(f"invalid framebuffer: {fb.width}x{fb.height}")
            flat = np.ctypeslib.as_array(
                doom.rgba_ptr(), shape=(fb.width * fb.height * 4,)
            )
            rgba = flat.reshape((fb.height, fb.width, 4))
            video = DoomVideoPipe.create(src_w=fb.width, src_h=fb.height)
        except Exception:
            logger.exception("[doom] initialization failed")
            if doom:
                try:
                    doom.reset()
                except Exception:
                    logger.exception("[doom] reset after init failure failed")
            with self._lock:
                self._init_thread = None
            self._close_view()
            return

        with self._lock:
            if self._closed:
                shutdown = True
                start = False
            else:
                self._doom, self._video, self._rgba = doom, video, rgba
                shutdown = False
                start = self._visible
            self._init_thread = None
        if shutdown:
            doom.shutdown()
        elif start:
            self._start_tick()

    def _start_tick(self) -> None:
        with self._lock:
            if (
                self._closed
                or not self._visible
                or self._doom is None
                or self._video is None
                or self._rgba is None
            ):
                return
            if self._tick_thread and self._tick_thread.is_alive():
                return
            self._stop.clear()
            self._tick_thread = threading.Thread(
                target=self._tick_loop, daemon=True, name="doom-tick"
            )
            self._tick_thread.start()

    def _tick_loop(self) -> None:
        with self._lock:
            doom, video, rgba = self._doom, self._video, self._rgba
        if doom is None or video is None or rgba is None:
            logger.error("[doom] tick started without initialized engine")
            return
        interval = 1.0 / self._fps
        frame = 0
        failed = False
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                self._drain_inputs(doom)
                self._expire_inputs(doom)
                doom.tick()
                frame += 1
                alive = doom.is_alive()
                left_level = self._controller.update_game_state(
                    alive=alive,
                    gamestate=doom.gamestate() if alive else -1,
                    menuactive=doom.menuactive() if alive else False,
                    usergame=doom.usergame() if alive else False,
                )
                if left_level:
                    self._controller.exit_level()
                if not alive:
                    raise RuntimeError("native Doom engine stopped")
                if frame % self._render_every == 0:
                    store._dispatch(
                        [
                            FrameStreamDataEvent(
                                stream_id=DOOM_STREAM_ID,
                                data=video.rgba_to_rgb888(rgba),
                                width=OUT_W,
                                height=OUT_H,
                            )
                        ]
                    )
                remaining = interval - (time.monotonic() - started)
                if remaining > 0:
                    self._stop.wait(remaining)
        except Exception:
            failed = True
            logger.exception("[doom] tick loop failed")
        finally:
            self._release_all(doom)
            with self._lock:
                if self._tick_thread is threading.current_thread():
                    self._tick_thread = None
        if failed:
            try:
                doom.reset()
            except Exception:
                logger.exception("[doom] native reset failed")
            with self._lock:
                self._doom = self._video = self._rgba = None
            self._close_view()

    def _drain_inputs(self, doom: DoomLib) -> None:
        while True:
            try:
                key, ticks = self._queue.get_nowait()
            except queue.Empty:
                return
            opposite = _OPPOSITE.get(key)
            if opposite in self._held:
                doom.key_up(opposite)
                del self._held[opposite]
            if key not in self._held:
                doom.key_down(key)
            self._held[key] = ticks

    def _expire_inputs(self, doom: DoomLib) -> None:
        for key in list(self._held):
            self._held[key] -= 1
            if self._held[key] <= 0:
                doom.key_up(key)
                del self._held[key]

    def _release_all(self, doom: DoomLib | None = None) -> None:
        doom = doom or self._doom
        if doom:
            for key in list(self._held):
                try:
                    doom.key_up(key)
                except Exception:
                    logger.exception("[doom] failed to release key")
        self._held.clear()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _tap(self, key: UboKey, hold_ticks: int = 2) -> None:
        with self._lock:
            if not self._visible or self._doom is None:
                return
        self._queue.put_nowait((key, hold_ticks))

    def _close_view(self) -> None:
        with self._lock:
            visible = self._visible
            self._visible = False
        if visible:
            store.dispatch(StackPopAction())


_session = DoomSession()


def _open_doom() -> None:
    store.dispatch(
        OpenRenderAction(
            kind="frame_stream",
            title="Doom",
            stream_id=DOOM_STREAM_ID,
            items=DOOM_RENDER_ITEMS,
        )
    )
    _session.resume()


def _handle_stack_changed(event: StackChangedEvent) -> None:
    _session.resume() if _is_doom_top(event.stack) else _session.pause()


def _handle_scroll(event: ApplicationScrollEvent) -> None:
    if not _session.is_visible:
        return
    if event.direction == "up":
        _session.go_up()
    elif event.direction == "down":
        _session.go_down()


def _handle_button(event: MenuChooseByIndexEvent) -> None:
    if _session.is_visible:
        _session.button(event.index)


def init_service() -> list[object]:
    """Register the Doom launcher and Ubo v2 event subscriptions."""
    logger.info("[doom] registering Ubo v2 application")
    register_action(DOOM_OPEN_ACTION_ID, _open_doom, allow_reregister=True)
    store.dispatch(
        RegisterRegularAppAction(
            key="doom",
            label="Doom",
            icon="󰺵",
            action_id=DOOM_OPEN_ACTION_ID,
            app_category="__apps_root__",
        )
    )
    return [
        store.subscribe_event(StackChangedEvent, _handle_stack_changed),
        store.subscribe_event(ApplicationScrollEvent, _handle_scroll),
        store.subscribe_event(MenuChooseByIndexEvent, _handle_button),
        lambda: unregister_action(DOOM_OPEN_ACTION_ID),
        _session.close,
    ]

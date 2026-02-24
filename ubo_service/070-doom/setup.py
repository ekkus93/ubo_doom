\
"""
ubo_service/070-doom/setup.py

External ubo service that runs classic Doom (linuxdoom-1.10) embedded as a shared
library (`libubodoom.so`) without forking ubo_app.

Video:
- Doom exports an RGBA8888 framebuffer (expected 320x200) via the patch API.
- This service scales it to 240x150 and letterboxes to 240x240 (45px top/bottom).
- Converts to RGB565 (big-endian) and writes directly to the LCD via:
    ubo_app.display.display.render_block(..., bypass_pause=True)

Audio:
- Doom outputs directly to ALSA inside the shared library (Option A).
- This service does not route/mix audio through ubo_app; Doom owns ALSA output while active.

Input:
- Uses ubo_app menu button mechanics with a two-mode toggle:
  Normal mode (default):
    - UP => forward, DOWN => backward  (always, in both modes)
    - L1 => toggle to ALT mode  (in-game only; ignored in menus)
    - L2 => turn left
    - L3 => turn right (in-game) / confirm/select (in menus)
    - BACK => fire (in-game, no menu) / escape/back (in menus) / enter (demo/intermission)
  ALT mode (L1 toggled, in-game only):
    - UP => forward, DOWN => backward  (unchanged)
    - L1 => toggle back to normal mode
    - L2 => use, L3 => escape/menu
    - BACK => fire (always)
  ALT mode auto-resets to normal when leaving a level (entering menus/intermission).
  HOME => exit Doom (handled by ubo; always active)

Environment:
- UBO_DOOM_LIB  : path to libubodoom.so (default: ~/doom/libubodoom.so)
- UBO_DOOM_IWAD : path to IWAD (.wad)   (default: ~/doom/doom2.wad)
- UBO_DOOM_FPS  : target fps (default: 30)

This file is aligned with the exported symbols from the pre-modified
`third_party/DOOM-master/linuxdoom-1.10` source build,
as wrapped by `ubo_service/070-doom/native/doom_lib.py`:
  - doom_init
  - doom_tick
  - doom_shutdown
  - doom_key_down / doom_key_up   (takes ubo_key_t / UboKey)
  - doom_get_rgba_ptr
  - doom_get_rgba_width / doom_get_rgba_height
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from kivy.clock import Clock

from ubo_gui.menu.types import ActionItem

from ubo_app.display import display as lcd_display
from ubo_app.store.core.types import CloseApplicationEvent, RegisterRegularAppAction
from ubo_app.store.main import store
from ubo_app.store.services.display import DisplayPauseAction, DisplayResumeAction
from ubo_app.store.ubo_actions import UboApplicationItem
from ubo_app.utils.gui import UboPageWidget

# service_thread loads this file as a standalone module (no package context),
# so relative imports don't work — insert the service dir and import absolutely.
_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)
from doom_controller import DoomController
from native.doom_lib import DoomLib, UboKey


# LCD geometry (ubo display uses inclusive rectangle coords: (x0,y0,x1,y1))
OUT_W: Final[int] = 240
OUT_H: Final[int] = 240
RECT_FULL: Final[tuple[int, int, int, int]] = (0, 0, OUT_W - 1, OUT_H - 1)

# Letterbox parameters for 320x200 -> 240x150 centered
ACTIVE_H: Final[int] = 150
PAD_TOP: Final[int] = (OUT_H - ACTIVE_H) // 2  # 45


def _resolve_launch_paths(iwad_path_raw: str) -> tuple[str, str, str]:
    """Resolve canonical Doom launch paths.

    Returns:
        (iwad_path_abs, launch_cwd_abs, config_path_abs)
    """
    iwad_path = Path(iwad_path_raw).expanduser().resolve()

    launch_cwd_env = os.environ.get("UBO_DOOM_CWD", "").strip()
    if launch_cwd_env:
        launch_cwd = Path(launch_cwd_env).expanduser().resolve()
    else:
        launch_cwd = iwad_path.parent

    config_path_env = os.environ.get("UBO_DOOM_CONFIG", "").strip()
    if config_path_env:
        config_path = Path(config_path_env).expanduser().resolve()
    else:
        config_path = launch_cwd / "doomrc.cfg"

    return str(iwad_path), str(launch_cwd), str(config_path)


@dataclass
class _VideoPipe:
    """
    Converts Doom RGBA (src_w x src_h) -> 240x240 RGB565 (big-endian), letterboxed.

    Uses numpy views + precomputed nearest-neighbor index maps.
    """

    src_w: int
    src_h: int
    x_src: np.ndarray
    y_src: np.ndarray
    out_rgb: np.ndarray
    out_rgb565: np.ndarray

    @classmethod
    def create(cls, *, src_w: int, src_h: int) -> "_VideoPipe":
        # Nearest-neighbor mapping indices:
        #  - 240 samples across width
        #  - 150 samples across height
        x_src = (np.arange(OUT_W, dtype=np.int32) * src_w) // OUT_W
        y_src = (np.arange(ACTIVE_H, dtype=np.int32) * src_h) // ACTIVE_H

        out_rgb = np.zeros((OUT_H, OUT_W, 3), dtype=np.uint8)      # RGB888
        out_rgb565 = np.zeros((OUT_H, OUT_W), dtype=np.uint16)     # RGB565

        return cls(
            src_w=src_w,
            src_h=src_h,
            x_src=x_src,
            y_src=y_src,
            out_rgb=out_rgb,
            out_rgb565=out_rgb565,
        )

    def rgba_to_rgb565_be(self, rgba_view: np.ndarray) -> bytes:
        """
        rgba_view: numpy view shaped (src_h, src_w, 4) uint8

        Returns bytes length = 240*240*2, RGB565 big-endian, ready for render_block.
        """
        # clear to black (letterbox bars)
        self.out_rgb.fill(0)

        # scale + place active region
        scaled_rgb = rgba_view[self.y_src[:, None], self.x_src[None, :], :3]  # (150,240,3)
        self.out_rgb[PAD_TOP:PAD_TOP + ACTIVE_H, :, :] = scaled_rgb

        # pack to RGB565
        r = self.out_rgb[:, :, 0].astype(np.uint16)
        g = self.out_rgb[:, :, 1].astype(np.uint16)
        b = self.out_rgb[:, :, 2].astype(np.uint16)

        self.out_rgb565[:, :] = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

        # ST7789 expects big-endian bytes
        return self.out_rgb565.byteswap().tobytes()


class DoomPage(UboPageWidget):
    """
    Owns the LCD while active.
    """

    def __init__(self, **kwargs: object) -> None:
        # _key_queue must exist before any _tap call; create it before _controller.
        self._key_queue: queue.Queue[tuple[UboKey, int]] = queue.Queue()
        # Controller owns all input-routing state; DoomPage is a thin shell.
        self._controller = DoomController(tap_fn=self._tap)
        # Footer: L1=mode toggle, L2/L3 depend on mode (alt_mode starts False).
        kwargs.setdefault("items", self._make_items())
        super().__init__(**kwargs)

        self._fps = float(os.environ.get("UBO_DOOM_FPS", "30"))
        self._doom: DoomLib | None = None
        self._video: _VideoPipe | None = None
        self._rgba_view: "np.ndarray | None" = None
        # Held-key countdown dict — only accessed by the tick thread.
        self._held: dict[UboKey, int] = {}
        # Stop signal and thread handle for the tick loop.
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

        self._lib_path = Path(os.environ.get("UBO_DOOM_LIB", str(Path.home() / "doom" / "libubodoom.so")))
        iwad_default = os.environ.get("UBO_DOOM_IWAD", str(Path.home() / "doom" / "doom2.wad"))
        self._iwad_path, self._launch_cwd, self._config_path = _resolve_launch_paths(iwad_default)

        # Enforce a single canonical config location and launch cwd for libubodoom.
        Path(self._launch_cwd).mkdir(parents=True, exist_ok=True)
        Path(self._config_path).parent.mkdir(parents=True, exist_ok=True)
        os.environ["UBO_DOOM_CWD"] = self._launch_cwd
        os.environ["UBO_DOOM_CONFIG"] = self._config_path

        # Pause ubo display so it doesn't interfere with Doom's LCD output.
        # We intentionally do NOT mute OUTPUT audio here — muting the hardware
        # output device would silence Doom's own ALSA sound output too.
        store.dispatch(DisplayPauseAction())

        # Init Doom in a background thread so the Kivy main thread isn't blocked.
        threading.Thread(target=self._init_doom, daemon=True).start()

    def _init_doom(self) -> None:
        try:
            print(
                f"[doom] launch paths: cwd={self._launch_cwd} config={self._config_path} iwad={self._iwad_path}",
                flush=True,
            )
            self._doom = DoomLib(self._lib_path)
            self._doom.init(self._iwad_path)

            fb = self._doom.framebuffer_info()
            if fb.width <= 0 or fb.height <= 0:
                raise RuntimeError(f"Invalid Doom framebuffer size: {fb.width}x{fb.height}")

            rgba_ptr = self._doom.rgba_ptr()
            flat = np.ctypeslib.as_array(rgba_ptr, shape=(fb.width * fb.height * 4,))
            self._rgba_view = flat.reshape((fb.height, fb.width, 4))
            self._video = _VideoPipe.create(src_w=fb.width, src_h=fb.height)

            # Schedule tick start back on the Kivy main thread.
            Clock.schedule_once(lambda _dt: self._start_tick(), 0)
        except Exception:
            print("[doom] DoomPage._init_doom FAILED:\n" + traceback.format_exc(), flush=True)
            store.dispatch(DisplayResumeAction())
            # Close the DoomPage so ubo returns to the main menu instead of
            # leaving a black screen with no way out.
            _instance_id = self.id
            Clock.schedule_once(
                lambda _dt: store.dispatch(CloseApplicationEvent(application_instance_id=_instance_id)), 0
            )

    def _start_tick(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop_evt.clear()
            self._thread = threading.Thread(
                target=self._tick_loop, daemon=True, name="doom-tick"
            )
            self._thread.start()

    # ------------
    # Input mapping
    # ------------
    def go_up(self) -> None:
        self._controller.go_up()

    def go_down(self) -> None:
        self._controller.go_down()

    def go_back(self) -> bool:
        return self._controller.go_back()

    def _make_items(self) -> list:
        """Build footer ActionItems for the current mode."""
        if self._controller.alt_mode:
            return [
                ActionItem(label="NRM", icon="", action=self._toggle_mode),
                ActionItem(label="USE", icon="", action=self._btn_l2),
                ActionItem(label="ESC", icon="", action=self._btn_l3),
            ]
        return [
            ActionItem(label="ALT", icon="", action=self._toggle_mode),
            ActionItem(label="◄", icon="", action=self._btn_l2),
            ActionItem(label="►/OK", icon="", action=self._btn_l3),
        ]

    def _toggle_mode(self) -> None:
        if self._controller.toggle_mode():
            self.items = self._make_items()

    def _exit_level(self) -> None:
        """Called on Kivy main thread when the game leaves GS_LEVEL."""
        if self._controller.exit_level():
            self.items = self._make_items()

    def _btn_l2(self) -> None:
        self._controller.btn_l2()

    def _btn_l3(self) -> None:
        self._controller.btn_l3()

    def _tap(self, key: UboKey, hold_ticks: int = 2) -> None:
        # Non-blocking: enqueue the event for the tick thread to process.
        # The tick thread calls key_down and manages the hold countdown.
        if self._doom is None:
            return
        self._key_queue.put_nowait((key, hold_ticks))

    # ----------
    # Tick thread
    # ----------
    def _tick_loop(self) -> None:
        """Runs entirely on the doom-tick background thread."""
        doom = self._doom
        video = self._video
        rgba_view = self._rgba_view
        if doom is None or video is None or rgba_view is None:
            return

        interval = 1.0 / self._fps
        frame = 0
        _MOVEMENT_OPPOSITE: dict[UboKey, UboKey] = {
            UboKey.UP: UboKey.DOWN,
            UboKey.DOWN: UboKey.UP,
        }
        while not self._stop_evt.is_set():
            t0 = time.monotonic()

            # Drain key events posted by the main thread.
            while True:
                try:
                    key, hold_ticks = self._key_queue.get_nowait()
                    # Cancel the opposite movement direction immediately so
                    # a lingering hold_ticks countdown can't cause both UP
                    # and DOWN to be active in gamekeydown simultaneously.
                    opposite = _MOVEMENT_OPPOSITE.get(key)
                    if opposite is not None and opposite in self._held:
                        doom.key_up(opposite)
                        del self._held[opposite]
                    if key not in self._held:
                        doom.key_down(key)
                    self._held[key] = hold_ticks  # (re)set countdown
                except queue.Empty:
                    break

            # Release any held keys whose countdown has expired.
            # Runs BEFORE doom.tick() so key_up is in the event queue when
            # D_ProcessEvents drains it on this same tick.
            for key in list(self._held):
                self._held[key] -= 1
                if self._held[key] <= 0:
                    doom.key_up(key)
                    del self._held[key]

            doom.tick()
            frame += 1

            # Update controller's cached state (tick thread → main-thread reads).
            # update_game_state() returns True when the game just left a level,
            # which triggers an exit_level() call on the Kivy main thread.
            alive = doom.is_alive()
            just_left_level = self._controller.update_game_state(
                alive=alive,
                gamestate=doom.gamestate() if alive else -1,
                menuactive=bool(doom.menuactive()) if alive else False,
            )
            if just_left_level:
                Clock.schedule_once(lambda _dt: self._exit_level(), 0)

            # If I_Error or SIGSEGV fired mid-tick the engine marks itself dead.
            if not doom.is_alive():
                self._held.clear()
                doom.reset()
                Clock.schedule_once(lambda _dt: self._on_doom_died(), 0)
                return

            # Render to LCD every other game tick (~15fps LCD vs 30fps physics).
            # This halves SPI DMA bandwidth, reducing contention with the WiFi
            # SDIO controller on the RPi4 AXI bus (known SPI/SDIO DMA conflict).
            if frame % 2 == 0:
                rgb565_be = video.rgba_to_rgb565_be(rgba_view)
                lcd_display.render_block(
                    rectangle=RECT_FULL,
                    data_bytes=rgb565_be,
                    bypass_pause=True,
                )

            # Sleep for whatever is left of the frame budget.
            elapsed = time.monotonic() - t0
            remaining = interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def _on_doom_died(self) -> None:
        """Called on the Kivy main thread when the engine dies mid-tick."""
        store.dispatch(DisplayResumeAction())
        _instance_id = self.id
        store.dispatch(CloseApplicationEvent(application_instance_id=_instance_id))

    def on_close(self) -> None:
        # Signal the tick thread to stop and wait briefly for it to exit.
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        # Release every held key in Doom before clearing our tracking dict.
        # The tick thread may have exited while a key was still held, leaving
        # gamekeydown[key] = true in the C engine permanently.  Sending
        # key_up() for each held key here resets that state so re-entering
        # Doom doesn't inherit stale pressed keys (e.g. perpetual UP/forward).
        if self._doom is not None:
            for key in list(self._held):
                self._doom.key_up(key)
        self._held.clear()
        # Drain any queued key events so they don't linger across re-opens.
        while not self._key_queue.empty():
            try:
                self._key_queue.get_nowait()
            except queue.Empty:
                break

        # Restore ubo display so the rest of the UI works normally while Doom
        # is not visible.  We do NOT call doom_shutdown here because the Doom
        # engine is not designed to be re-initialised within the same process
        # (it re-adds WAD lumps and corrupts zone/tic state on second init).
        # Leaving it warm means re-entering Doom just restarts the tick loop
        # and resumes from where the user left off.
        store.dispatch(DisplayResumeAction())


def init_service() -> None:
    """
    Register Doom as a regular application item in the main menu.
    """
    store.dispatch(
        RegisterRegularAppAction(
            key="doom",
            menu_item=UboApplicationItem(
                application_id="doom",
                label="Doom",
                icon="󰺵",
                application=DoomPage,
            ),
        ),
    )

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
- This service mutes ubo_app OUTPUT while Doom runs to reduce contention.

Input:
- Uses ubo_app menu button mechanics:
  - UP/DOWN => forward/back (tap)
  - L1 => fire (tap)
  - L2 => use (tap)
  - L3 => escape/menu (tap)
  - BACK => exit (handled by ubo navigation / menu stack)

Environment:
- UBO_DOOM_LIB  : path to libubodoom.so (default: ~/doom/libubodoom.so)
- UBO_DOOM_IWAD : path to IWAD (.wad)   (default: ~/doom/doom2.wad)
- UBO_DOOM_FPS  : target fps (default: 30)

This file is aligned with the *actual* exported symbols from ubodoom_linuxdoom110.patch,
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
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from kivy.clock import Clock

from ubo_gui.menu.types import ActionItem

from ubo_app.display import display as lcd_display
from ubo_app.store.core.types import RegisterRegularAppAction
from ubo_app.store.main import store
from ubo_app.store.services.audio import AudioDevice, AudioSetMuteStatusAction
from ubo_app.store.services.display import DisplayPauseAction, DisplayResumeAction
from ubo_app.store.ubo_actions import UboApplicationItem
from ubo_app.utils.gui import UboPageWidget

# service_thread loads this file as a standalone module (no package context),
# so relative imports don't work — insert the service dir and import absolutely.
_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)
from native.doom_lib import DoomLib, UboKey


# LCD geometry (ubo display uses inclusive rectangle coords: (x0,y0,x1,y1))
OUT_W: Final[int] = 240
OUT_H: Final[int] = 240
RECT_FULL: Final[tuple[int, int, int, int]] = (0, 0, OUT_W - 1, OUT_H - 1)

# Letterbox parameters for 320x200 -> 240x150 centered
ACTIVE_H: Final[int] = 150
PAD_TOP: Final[int] = (OUT_H - ACTIVE_H) // 2  # 45


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
        # Footer button mapping: L1/L2/L3 => choose index 0/1/2
        kwargs.setdefault(
            "items",
            [
                ActionItem(label="FIRE", icon="", action=self._btn_fire),
                ActionItem(label="USE", icon="", action=self._btn_use),
                ActionItem(label="MENU", icon="", action=self._btn_menu),
            ],
        )
        super().__init__(**kwargs)

        self._fps = float(os.environ.get("UBO_DOOM_FPS", "30"))
        self._evt = None
        self._doom: DoomLib | None = None
        self._video: _VideoPipe | None = None
        self._rgba_view: "np.ndarray | None" = None

        self._lib_path = Path(os.environ.get("UBO_DOOM_LIB", str(Path.home() / "doom" / "libubodoom.so")))
        self._iwad_path = os.environ.get("UBO_DOOM_IWAD", str(Path.home() / "doom" / "doom2.wad"))

        # Pause ubo display/audio eagerly so they don't interfere during init.
        store.dispatch(DisplayPauseAction())
        store.dispatch(AudioSetMuteStatusAction(is_mute=True, device=AudioDevice.OUTPUT))

        # Init Doom in a background thread so the Kivy main thread isn't blocked.
        threading.Thread(target=self._init_doom, daemon=True).start()

    def _init_doom(self) -> None:
        try:
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

    def _start_tick(self) -> None:
        if self._evt is None:
            self._evt = Clock.schedule_interval(self._tick, 1.0 / self._fps)

    # ------------
    # Input mapping
    # ------------
    def go_up(self) -> None:
        self._tap(UboKey.UP)

    def go_down(self) -> None:
        self._tap(UboKey.DOWN)

    def go_left(self) -> None:  # if ubo routes it
        self._tap(UboKey.LEFT)

    def go_right(self) -> None:  # if ubo routes it
        self._tap(UboKey.RIGHT)

    def _btn_fire(self) -> None:
        self._tap(UboKey.FIRE)

    def _btn_use(self) -> None:
        self._tap(UboKey.USE)

    def _btn_menu(self) -> None:
        self._tap(UboKey.ESCAPE)

    def _tap(self, key: UboKey) -> None:
        # Keypad is discrete presses; model as tap (down+up).
        self._doom.key_down(key)
        self._doom.key_up(key)

    # ----------
    # Main loop
    # ----------
    def _tick(self, _dt: float) -> None:
        if self._doom is None or self._video is None or self._rgba_view is None:
            return
        self._doom.tick()
        rgb565_be = self._video.rgba_to_rgb565_be(self._rgba_view)

        # ubo_app display.render_block uses inclusive rectangle
        lcd_display.render_block(
            rectangle=RECT_FULL,
            data_bytes=rgb565_be,
            bypass_pause=True,
        )

    def on_close(self) -> None:
        if self._evt is not None:
            self._evt.cancel()
            self._evt = None

        # Restore ubo state
        store.dispatch(AudioSetMuteStatusAction(is_mute=False, device=AudioDevice.OUTPUT))
        store.dispatch(DisplayResumeAction())

        # Shut down Doom (best effort)
        try:
            if self._doom is not None:
                self._doom.shutdown()
        except Exception:
            pass


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

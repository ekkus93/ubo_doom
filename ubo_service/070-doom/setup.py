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
- Uses ubo_app menu button mechanics with a two-mode toggle:
  Normal mode (default):
    - UP => forward, DOWN => backward
    - L1 => toggle to ALT mode
    - L2 => turn left, L3 => turn right
    - BACK => fire (intercepted; stays in Doom)
  ALT mode (L1 toggled):
    - UP => turn left, DOWN => turn right
    - L1 => toggle back to normal mode
    - L2 => use, L3 => escape/menu
    - BACK => fire (always)
  HOME => exit Doom (handled by ubo; always active)

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
        self._alt_mode = False
        # Footer: L1=mode toggle, L2/L3 depend on mode
        kwargs.setdefault("items", self._make_items())
        super().__init__(**kwargs)

        self._fps = float(os.environ.get("UBO_DOOM_FPS", "30"))
        self._evt = None
        self._doom: DoomLib | None = None
        self._video: _VideoPipe | None = None
        self._rgba_view: "np.ndarray | None" = None
        # Keys held for N more ticks: key_down already sent, key_up will be sent
        # in _tick once the counter hits 0.  This guarantees key_up is only posted
        # AFTER doom_tick has run G_BuildTiccmd at least once with the key held,
        # avoiding the race where Clock.schedule_once fired key_up before doom_tick
        # had a chance to drain the event queue.
        self._held: dict[UboKey, int] = {}

        self._lib_path = Path(os.environ.get("UBO_DOOM_LIB", str(Path.home() / "doom" / "libubodoom.so")))
        self._iwad_path = os.environ.get("UBO_DOOM_IWAD", str(Path.home() / "doom" / "doom2.wad"))

        # Pause ubo display so it doesn't interfere with Doom's LCD output.
        # We intentionally do NOT mute OUTPUT audio here — muting the hardware
        # output device would silence Doom's own ALSA sound output too.
        store.dispatch(DisplayPauseAction())

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
            store.dispatch(DisplayResumeAction())
            # Close the DoomPage so ubo returns to the main menu instead of
            # leaving a black screen with no way out.
            _instance_id = self.id
            Clock.schedule_once(
                lambda _dt: store.dispatch(CloseApplicationEvent(application_instance_id=_instance_id)), 0
            )

    def _start_tick(self) -> None:
        if self._evt is None:
            self._evt = Clock.schedule_interval(self._tick, 1.0 / self._fps)

    # ------------
    # Input mapping
    # ------------
    def go_up(self) -> None:
        # Normal: forward.  ALT: turn left.
        self._tap(UboKey.LEFT if self._alt_mode else UboKey.UP)

    def go_down(self) -> None:
        # Normal: backward.  ALT: turn right.
        self._tap(UboKey.RIGHT if self._alt_mode else UboKey.DOWN)

    def go_back(self) -> bool:
        # Intercept BACK so it fires instead of exiting Doom.
        print(f"[doom] go_back called, alt_mode={self._alt_mode}", flush=True)
        self._tap(UboKey.FIRE)
        return True

    def _make_items(self) -> list:
        """Build footer ActionItems for the current mode."""
        if self._alt_mode:
            return [
                ActionItem(label="NRM", icon="", action=self._toggle_mode),
                ActionItem(label="USE", icon="", action=self._btn_l2),
                ActionItem(label="MENU", icon="", action=self._btn_l3),
            ]
        return [
            ActionItem(label="ALT", icon="", action=self._toggle_mode),
            ActionItem(label="◄", icon="", action=self._btn_l2),
            ActionItem(label="►", icon="", action=self._btn_l3),
        ]

    def _toggle_mode(self) -> None:
        self._alt_mode = not self._alt_mode
        self.items = self._make_items()

    def _btn_l2(self) -> None:
        # Normal: turn left.  ALT: use (open doors/switches).
        self._tap(UboKey.USE if self._alt_mode else UboKey.LEFT)

    def _btn_l3(self) -> None:
        # Normal: turn right.  ALT: escape/menu.
        self._tap(UboKey.ESCAPE if self._alt_mode else UboKey.RIGHT)

    def _tap(self, key: UboKey) -> None:
        # Post key_down immediately.  Key_up is sent in _tick after the held
        # counter counts down to 0 — this guarantees at least 2 doom_tick calls
        # see the key held before it's released, with no Clock timer race.
        if self._doom is None:
            return
        print(f"[doom] _tap: key={key}, doom_alive={self._doom.is_alive()}", flush=True)
        if key not in self._held:
            self._doom.key_down(key)
        self._held[key] = 2  # hold for 2 ticks

    # ----------
    # Main loop
    # ----------
    def _tick(self, _dt: float) -> None:
        if self._doom is None or self._video is None or self._rgba_view is None:
            return
        # Decrement held-key counters and release any that have expired.
        # This runs BEFORE doom.tick() so that key_up events are in the queue
        # when D_ProcessEvents drains it — but only after the previous tick
        # already saw the key held.
        for key in list(self._held):
            self._held[key] -= 1
            if self._held[key] <= 0:
                print(f"[doom] _tick: releasing key={key}", flush=True)
                if self._doom:
                    self._doom.key_up(key)
                del self._held[key]
        self._doom.tick()
        # If I_Error or SIGSEGV fired mid-tick the engine marks itself dead.
        # Stop the tick loop, reset the engine so it can be restarted next
        # time the user opens Doom, and close the page cleanly.
        if not self._doom.is_alive():
            print("[doom] engine died mid-tick, stopping loop", flush=True)
            self._held.clear()
            self._doom.reset()
            if self._evt is not None:
                self._evt.cancel()
                self._evt = None
            store.dispatch(DisplayResumeAction())
            _instance_id = self.id
            Clock.schedule_once(
                lambda _dt: store.dispatch(CloseApplicationEvent(application_instance_id=_instance_id)), 0
            )
            return
        rgb565_be = self._video.rgba_to_rgb565_be(self._rgba_view)

        # ubo_app display.render_block uses inclusive rectangle
        lcd_display.render_block(
            rectangle=RECT_FULL,
            data_bytes=rgb565_be,
            bypass_pause=True,
        )

    def on_close(self) -> None:
        self._held.clear()
        if self._evt is not None:
            self._evt.cancel()
            self._evt = None

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

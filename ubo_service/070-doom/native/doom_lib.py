from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Final


class UboKey(IntEnum):
    """
    Key enum exported by the Doom embedding patch (see doom_api.h in the patch).

    These are NOT doomkeys.h keycodes. They are a small stable interface that the
    shared library maps internally to Doom keycodes.

    Values (from patch):
      UBO_KEY_UP = 1
      UBO_KEY_DOWN = 2
      UBO_KEY_LEFT = 3
      UBO_KEY_RIGHT = 4
      UBO_KEY_FIRE = 5     (maps to Ctrl)
      UBO_KEY_USE = 6      (maps to Space)
      UBO_KEY_ESCAPE = 7   (maps to Esc)
    """
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4
    FIRE = 5
    USE = 6
    ESCAPE = 7


@dataclass(frozen=True)
class DoomFramebufferInfo:
    width: int
    height: int
    bytes_per_pixel: int = 4  # RGBA8888


class DoomLib:
    """
    ctypes wrapper for libubodoom.so produced by ubodoom_linuxdoom110.patch.

    Exported C API (from the patch):
      int  doom_init(const char* iwad_path);
      void doom_tick(void);
      void doom_shutdown(void);

      void doom_key_down(ubo_key_t key);
      void doom_key_up(ubo_key_t key);

      const uint8_t* doom_get_rgba_ptr(void);
      int  doom_get_rgba_width(void);   // expected 320
      int  doom_get_rgba_height(void);  // expected 200
    """

    def __init__(self, lib_path: Path) -> None:
        if not lib_path.exists():
            raise FileNotFoundError(f"libubodoom.so not found: {lib_path}")

        self._lib = ctypes.CDLL(str(lib_path))

        # int doom_init(const char* iwad_path);
        self._lib.doom_init.argtypes = [ctypes.c_char_p]
        self._lib.doom_init.restype = ctypes.c_int

        # void doom_tick(void);
        self._lib.doom_tick.argtypes = []
        self._lib.doom_tick.restype = None

        # void doom_shutdown(void);
        self._lib.doom_shutdown.argtypes = []
        self._lib.doom_shutdown.restype = None

        # void doom_key_down(ubo_key_t key);
        self._lib.doom_key_down.argtypes = [ctypes.c_int]
        self._lib.doom_key_down.restype = None

        # void doom_key_up(ubo_key_t key);
        self._lib.doom_key_up.argtypes = [ctypes.c_int]
        self._lib.doom_key_up.restype = None

        # const uint8_t* doom_get_rgba_ptr(void);
        self._lib.doom_get_rgba_ptr.argtypes = []
        self._lib.doom_get_rgba_ptr.restype = ctypes.POINTER(ctypes.c_uint8)

        # int doom_get_rgba_width(void);
        self._lib.doom_get_rgba_width.argtypes = []
        self._lib.doom_get_rgba_width.restype = ctypes.c_int

        # int doom_get_rgba_height(void);
        self._lib.doom_get_rgba_height.argtypes = []
        self._lib.doom_get_rgba_height.restype = ctypes.c_int

        # Optional globals exported by the patch:
        #   extern int ubo_library_mode;
        #   extern uint8_t ubo_rgba[320 * 200 * 4];
        # Not required for normal usage, but can be handy for debugging.
        try:
            self.ubo_library_mode = ctypes.c_int.in_dll(self._lib, "ubo_library_mode")
        except Exception:
            self.ubo_library_mode = None

        try:
            self.ubo_rgba = (ctypes.c_uint8 * (320 * 200 * 4)).in_dll(self._lib, "ubo_rgba")
        except Exception:
            self.ubo_rgba = None

    def init(self, iwad_path: str) -> None:
        rc = int(self._lib.doom_init(iwad_path.encode("utf-8")))
        if rc != 0:
            raise RuntimeError(f"doom_init failed rc={rc} (iwad_path={iwad_path!r})")

    def shutdown(self) -> None:
        self._lib.doom_shutdown()

    def tick(self) -> None:
        self._lib.doom_tick()

    def key_down(self, key: UboKey | int) -> None:
        self._lib.doom_key_down(int(key))

    def key_up(self, key: UboKey | int) -> None:
        self._lib.doom_key_up(int(key))

    def framebuffer_info(self) -> DoomFramebufferInfo:
        w = int(self._lib.doom_get_rgba_width())
        h = int(self._lib.doom_get_rgba_height())
        return DoomFramebufferInfo(width=w, height=h, bytes_per_pixel=4)

    def rgba_ptr(self) -> ctypes.POINTER(ctypes.c_uint8):
        return self._lib.doom_get_rgba_ptr()

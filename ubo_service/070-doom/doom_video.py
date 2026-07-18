"""Pure NumPy conversion for the Ubo v2 RGB frame-stream renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

OUT_W: Final[int] = 240
OUT_H: Final[int] = 240
ACTIVE_H: Final[int] = 150
PAD_TOP: Final[int] = (OUT_H - ACTIVE_H) // 2


@dataclass
class DoomVideoPipe:
    """Scale Doom RGBA8888 frames to letterboxed 240x240 RGB888 frames."""

    src_w: int
    src_h: int
    x_src: np.ndarray
    y_src: np.ndarray
    out_rgb: np.ndarray

    @classmethod
    def create(cls, *, src_w: int, src_h: int) -> "DoomVideoPipe":
        if src_w <= 0 or src_h <= 0:
            raise ValueError(f"invalid source dimensions: {src_w}x{src_h}")

        x_src = (np.arange(OUT_W, dtype=np.int32) * src_w) // OUT_W
        y_src = (np.arange(ACTIVE_H, dtype=np.int32) * src_h) // ACTIVE_H
        return cls(
            src_w=src_w,
            src_h=src_h,
            x_src=x_src,
            y_src=y_src,
            out_rgb=np.zeros((OUT_H, OUT_W, 3), dtype=np.uint8),
        )

    def rgba_to_rgb888(self, rgba_view: np.ndarray) -> bytes:
        """Return one 240x240 RGB888 frame suitable for FrameStreamDataEvent."""
        expected_shape = (self.src_h, self.src_w, 4)
        if rgba_view.shape != expected_shape:
            raise ValueError(
                f"unexpected RGBA shape: {rgba_view.shape}; expected {expected_shape}",
            )
        if rgba_view.dtype != np.uint8:
            raise TypeError(f"unexpected RGBA dtype: {rgba_view.dtype}; expected uint8")

        self.out_rgb.fill(0)
        scaled_rgb = rgba_view[
            self.y_src[:, None],
            self.x_src[None, :],
            :3,
        ]
        self.out_rgb[PAD_TOP : PAD_TOP + ACTIVE_H, :, :] = scaled_rgb
        return self.out_rgb.tobytes()

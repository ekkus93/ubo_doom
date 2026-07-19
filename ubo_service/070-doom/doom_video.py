"""Pure NumPy conversion for the Ubo v2 RGB frame-stream renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

OUT_W: Final[int] = 240
OUT_H: Final[int] = 240
ACTIVE_H: Final[int] = 150
PAD_TOP: Final[int] = (OUT_H - ACTIVE_H) // 2

# Mode-indicator HUD tag, drawn inside the Doom image (the top/bottom letterbox
# bands belong to Ubo's own title/footer chrome, so a tag there could be hidden).
_LABEL_SCALE: Final[int] = 2
_LABEL_X: Final[int] = 3
_LABEL_Y: Final[int] = 3  # offset below the top of the active area
_WHITE: Final = np.array([255, 255, 255], dtype=np.uint8)

# Minimal 5x5 uppercase font — only the glyphs used by the DOWN-mode names
# (FIRE / USE / BACK / WEAPON). Each row is 5 bits, MSB = leftmost pixel.
_GLYPHS: Final[dict[str, tuple[int, int, int, int, int]]] = {
    "F": (31, 16, 30, 16, 16),
    "I": (31, 4, 4, 4, 31),
    "R": (30, 17, 30, 20, 19),
    "E": (31, 16, 30, 16, 31),
    "U": (17, 17, 17, 17, 14),
    "S": (15, 16, 14, 1, 30),
    "B": (30, 17, 30, 17, 30),
    "A": (14, 17, 31, 17, 17),
    "C": (15, 16, 16, 16, 15),
    "K": (17, 18, 28, 18, 17),
    "W": (17, 17, 21, 21, 10),
    "P": (30, 17, 30, 16, 16),
    "O": (14, 17, 17, 17, 14),
    "N": (17, 25, 21, 19, 17),
}
_GLYPH_W: Final[int] = 5
_GLYPH_H: Final[int] = 5


@dataclass
class DoomVideoPipe:
    """Scale Doom RGBA8888 frames to letterboxed 240x240 RGB888 frames."""

    src_w: int
    src_h: int
    x_src: np.ndarray
    y_src: np.ndarray
    out_rgb: np.ndarray

    @classmethod
    def create(cls, *, src_w: int, src_h: int) -> DoomVideoPipe:
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

    def rgba_to_rgb888(
        self,
        rgba_view: np.ndarray,
        *,
        label: str = "",
        label_color: tuple[int, int, int] | None = None,
    ) -> bytes:
        """Return one 240x240 RGB888 frame suitable for FrameStreamDataEvent.

        When ``label`` is set, draw it as a small HUD tag in the top-left of the
        Doom image (used to show the current DOWN-button mode without touching
        the render view's title, which would force a full-screen refresh).
        """
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
        if label:
            color = _WHITE if label_color is None else np.array(label_color, dtype=np.uint8)
            self._draw_label(label, color)
        return self.out_rgb.tobytes()

    def _draw_label(self, text: str, color: np.ndarray) -> None:
        scale = _LABEL_SCALE
        advance = (_GLYPH_W + 1) * scale
        text_w = advance * len(text) - scale  # drop the trailing inter-glyph gap
        if text_w <= 0:
            return
        x0 = _LABEL_X
        y0 = PAD_TOP + _LABEL_Y
        # Dark backing box so the text stays legible over any Doom background.
        by1 = min(OUT_H, y0 + _GLYPH_H * scale + scale)
        bx1 = min(OUT_W, x0 + text_w + scale)
        self.out_rgb[max(0, y0 - scale) : by1, max(0, x0 - scale) : bx1] = 0
        x = x0
        for ch in text:
            glyph = _GLYPHS.get(ch)
            if glyph is not None:
                for ry in range(_GLYPH_H):
                    bits = glyph[ry]
                    for cx in range(_GLYPH_W):
                        if bits & (1 << (_GLYPH_W - 1 - cx)):
                            yy = y0 + ry * scale
                            xx = x + cx * scale
                            self.out_rgb[yy : yy + scale, xx : xx + scale] = color
            x += advance

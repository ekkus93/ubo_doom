"""Tests for Doom's RGBA-to-Ubo-frame-stream conversion."""

from __future__ import annotations

import numpy as np
import pytest

from doom_video import ACTIVE_H, OUT_H, OUT_W, PAD_TOP, DoomVideoPipe


def test_output_is_letterboxed_rgb888() -> None:
    pipe = DoomVideoPipe.create(src_w=2, src_h=2)
    rgba = np.array(
        [
            [[255, 0, 0, 255], [0, 255, 0, 255]],
            [[0, 0, 255, 255], [255, 255, 255, 255]],
        ],
        dtype=np.uint8,
    )

    output = np.frombuffer(pipe.rgba_to_rgb888(rgba), dtype=np.uint8).reshape(
        OUT_H,
        OUT_W,
        3,
    )

    assert np.all(output[:PAD_TOP] == 0)
    assert np.all(output[PAD_TOP + ACTIVE_H :] == 0)
    assert output[PAD_TOP, 0].tolist() == [255, 0, 0]
    assert output[PAD_TOP, -1].tolist() == [0, 255, 0]
    assert output[PAD_TOP + ACTIVE_H - 1, 0].tolist() == [0, 0, 255]
    assert output[PAD_TOP + ACTIVE_H - 1, -1].tolist() == [255, 255, 255]


def test_output_payload_size_matches_rgb888_frame() -> None:
    pipe = DoomVideoPipe.create(src_w=320, src_h=200)
    rgba = np.zeros((200, 320, 4), dtype=np.uint8)
    assert len(pipe.rgba_to_rgb888(rgba)) == OUT_W * OUT_H * 3


@pytest.mark.parametrize("src_w,src_h", [(0, 200), (320, 0), (-1, 200)])
def test_invalid_source_dimensions_are_rejected(src_w: int, src_h: int) -> None:
    with pytest.raises(ValueError):
        DoomVideoPipe.create(src_w=src_w, src_h=src_h)


def test_unexpected_frame_shape_is_rejected() -> None:
    pipe = DoomVideoPipe.create(src_w=320, src_h=200)
    with pytest.raises(ValueError):
        pipe.rgba_to_rgb888(np.zeros((200, 320, 3), dtype=np.uint8))


def test_unexpected_frame_dtype_is_rejected() -> None:
    pipe = DoomVideoPipe.create(src_w=320, src_h=200)
    with pytest.raises(TypeError):
        pipe.rgba_to_rgb888(np.zeros((200, 320, 4), dtype=np.float32))

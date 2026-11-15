"""An uploaded keyframe cut to the frame (M5.5 step 10, ``media/image.py``)."""

from __future__ import annotations

import pytest

from drama_series_agent.media.image import BadCrop, Rect, fit, frame_rect, image_info
from drama_series_agent.modelhub.adapters.mock import solid_png


def test_the_largest_box_of_the_frame_inside_the_cut() -> None:
    assert frame_rect(1000, 1000, 1080, 1920) == Rect(219, 0, 562, 1000)  # centred, full height
    assert frame_rect(1080, 4000, 1080, 1920) == Rect(0, 1040, 1080, 1920)  # full width
    assert frame_rect(2000, 1000, 1080, 1920, Rect(100, 0, 400, 1000)) == Rect(100, 144, 400, 711)
    for bad in (Rect(0, 0, 0, 10), Rect(-1, 0, 10, 10), Rect(900, 0, 200, 100)):
        with pytest.raises(BadCrop):
            frame_rect(1000, 1000, 9, 16, bad)


async def test_fit_crops_and_scales_to_a_png() -> None:
    out = await fit(solid_png(1000, 1000, (200, 30, 30)), Rect(219, 0, 562, 1000), 1080, 1920)
    info = image_info(out)
    assert (info.mime, info.w, info.h) == ("image/png", 1080, 1920)

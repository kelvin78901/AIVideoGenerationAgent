from __future__ import annotations

import pytest

from drama_series_agent.spec.dims import ASPECTS, Aspect, Tier, all_tiers, dims, is_vertical

# SPEC 13.1; drafts use the 768p tier (short side 768).
EXPECTED: dict[Aspect, dict[Tier, tuple[int, int]]] = {
    "9:16": {"1080p": (1080, 1920), "2k": (1440, 2560), "draft": (768, 1366)},
    "16:9": {"1080p": (1920, 1080), "2k": (2560, 1440), "draft": (1366, 768)},
    "3:4": {"1080p": (1080, 1440), "2k": (1440, 1920), "draft": (768, 1024)},
    "1:1": {"1080p": (1080, 1080), "2k": (1440, 1440), "draft": (768, 768)},
    # 21:9 2K is capped at H3's limit.
    "21:9": {"1080p": (2520, 1080), "2k": (2976, 1248), "draft": (1792, 768)},
}


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("tier", ["1080p", "2k", "draft"])
def test_dims_table(aspect: Aspect, tier: Tier) -> None:
    d = dims(aspect, tier)
    assert (d.w, d.h) == EXPECTED[aspect][tier]
    assert d.w % 2 == 0 and d.h % 2 == 0


def test_all_tiers_and_orientation() -> None:
    assert set(all_tiers("9:16")) == {"1080p", "2k", "draft"}
    assert [a for a in ASPECTS if is_vertical(a)] == ["9:16", "3:4"]

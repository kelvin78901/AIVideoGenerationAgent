"""图片超分 (M5.5 step 15, ``iup``): a picture made larger with its detail filled in, nothing
else changed. A new version of the same product (origin ``upscale``), as with 以这张为底重画
(``redraw.py``, which it extends).

- **What it works on**: what a redraw does — a keyframe candidate, a reference picture, one of
  the six views, an uploaded picture of any of these.
- **How large**: a keyframe at the delivery size of the output spec (hard rule 10); a reference
  picture or a view at a long edge of 2048, its own shape kept.
- **Only locally**: SeedVR2 7B (``workflows/seedvr2-img``, the same weights as the video 2K
  finishing). No API model; on a machine that cannot run it the request is refused with the
  reason (``upscale_unavailable``: no CUDA, or what is still to install), and 「模型与兜底」's
  catalog gives the same reason for the greyed-out button.
- An upscaled keyframe is a final (``stage = final``, at the delivery size), as an API final
  made from a draft is.
"""

from __future__ import annotations

from typing import Any, ClassVar

from drama_series_agent.core.capabilities import Capabilities
from drama_series_agent.core.config import StudioConfig
from drama_series_agent.modelhub.catalog import catalog
from drama_series_agent.pipeline.component import Inputs
from drama_series_agent.pipeline.components.redraw import KEYFRAME, RedrawComponent, nearest_aspect
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.spec.dims import Dims, dims

LONG_EDGE = 2048


def larger(w: int, h: int, long_edge: int = LONG_EDGE) -> Dims:
    """``w`` × ``h`` scaled to ``long_edge`` on its longer side, both edges even."""
    scale = long_edge / max(w, h)
    return Dims(w=max(2, round(w * scale / 2) * 2), h=max(2, round(h * scale / 2) * 2))


class IupComponent(RedrawComponent):
    id = "iup"
    slot = "iup"
    origin: ClassVar[str | None] = "upscale"

    def _size(self, inputs: Inputs, f: dict[str, Any], where: str) -> tuple[Dims, str]:
        frame = inputs.context["frame"]
        if inputs.context["slot"] == KEYFRAME:
            return dims(frame["aspect"], frame["delivery"]), str(frame["aspect"])
        size = larger(int(f.get("w") or 1024), int(f.get("h") or 1024))
        return size, nearest_aspect(size.w, size.h)

    def _refs(self, base: str) -> list[str]:
        return []

    def _extra(self, params: dict[str, Any], base: str) -> dict[str, Any]:
        return {"base_image": base}

    def _blocks(self, params: dict[str, Any]) -> list[Block]:
        return []

    def _record(self, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _stage(self, where: str) -> str | None:
        return "final"


def why_not(cfg: StudioConfig, caps: Capabilities | None) -> dict[str, Any] | None:
    """Why this machine cannot upscale a picture (the catalog's reason: ``machine_cuda`` or
    ``machine_missing`` with a count); None when it can."""
    comp = next((c for c in catalog(cfg, caps).components if c.id == IupComponent.id), None)
    if comp is None or comp.api_models or "local" not in comp.unavailable:
        return None
    reason = comp.unavailable["local"]
    return {"reason": reason.code, **reason.params}


def refuse_if_unavailable(cfg: StudioConfig, caps: Capabilities | None) -> None:
    """409 ``upscale_unavailable`` with the reason when no model here can run it."""
    why = why_not(cfg, caps)
    if why is not None:
        raise PipelineError(409, "upscale_unavailable", **why)

"""局部修复 (M5.5 step 14, ``inpaint``): the part of a picture the user painted over, drawn
again from an instruction; the rest stays. A new version of the same product (origin
``inpaint``), as with 以这张为底重画 (``redraw.py``, which it extends).

- **What it works on**: what a redraw does — a keyframe candidate, a reference picture, one of
  the six views, an uploaded picture of any of these.
- **The mask**: the request's painted picture (light = change, of the picture's shape) is made
  the picture's size and black or white (``media/image.py:mask_for``) when the request comes
  in, and stored in two forms: grayscale, white = change, for ComfyUI's ``LoadImageMask``; and
  RGBA, transparent = change, for OpenAI's image edits. A picture that is not PNG is sent as a
  PNG of it (OpenAI wants the picture and the mask in the same format and size).
- **Locally** FLUX 3 Klein (``workflows/klein-inpaint``) noises only the masked part of the
  picture, samples it fully, and pastes the result back through the mask grown by 8 pixels:
  what is outside stays as it was, pixel for pixel. **On the API** GPT Image 2 takes the mask
  as guidance and may stray from its shape (OpenAI's guide says so); it redraws the whole
  picture.
- No strength: the masked part is drawn anew.
"""

from __future__ import annotations

from typing import Any

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import BadMask, NotAnImage, as_png, image_info, mask_for
from drama_series_agent.pipeline.components.redraw import RedrawComponent
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block

AREA = "只改遮罩里的部分（参考图 1 上要改的地方），遮罩外保持原样，接缝自然"


class InpaintComponent(RedrawComponent):
    id = "inpaint"
    slot = "inpaint"

    def _base(self, params: dict[str, Any], sha: str) -> str:
        return str(params.get("inpaint_base") or sha)

    def _extra(self, params: dict[str, Any], base: str) -> dict[str, Any]:
        return {
            "base_image": base,
            "mask": str(params["inpaint_mask"]),
            "mask_alpha": str(params["inpaint_alpha"]),
        }

    def _blocks(self, params: dict[str, Any]) -> list[Block]:
        return [Block("范围", AREA)]

    def _record(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"mask": str(params["inpaint_mask"]), "share": params.get("inpaint_share")}


async def inpaint_params(
    store: BlobStore, picture: dict[str, Any], mask: bytes, version_id: str, idx: int
) -> dict[str, Any]:
    """The run's params for painting over picture ``idx`` (its file entry ``picture``): the
    mask at the picture's size in both forms and the picture as PNG, in the store. 422
    ``not_an_image`` / ``bad_mask`` (another shape, nothing painted)."""
    sha = str(picture["sha256"])
    data = store.read_bytes(sha)
    try:
        info = image_info(data)
        made = await mask_for(mask, info.w, info.h)
    except BadMask as exc:
        raise PipelineError(422, "bad_mask", reason=str(exc)) from None
    except NotAnImage as exc:
        raise PipelineError(422, "not_an_image", reason=str(exc)) from None
    base = sha if info.mime == "image/png" else store.put_bytes(await as_png(data))
    return {
        "inpaint_version_id": version_id,
        "inpaint_idx": idx,
        "inpaint_base": base,
        "inpaint_mask": store.put_bytes(made.gray),
        "inpaint_alpha": store.put_bytes(made.alpha),
        "inpaint_share": round(made.share, 4),
    }

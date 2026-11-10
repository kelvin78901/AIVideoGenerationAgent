"""画面文字 (SPEC 5 ``text``): pictures of text that has to be exact on screen (a handwritten
note, a phone's lock screen, a sign), each checked by OCR.

Two ways to make it, the product's setting ``text.method``:
- **后期贴字** (``composite``): a base picture with room for the text and none on it; the
  characters go on in post (M7), so they are always right. OCR checks the base is blank.
- **模型直接出字** (``model``): the model draws the characters, so perspective and handwriting
  look natural. The Mock draws them from ``params.text``; real models read them in the prompt.
  OCR reads each candidate back and compares it character for character (``qa/ocr.py``).

Otherwise a run is a reference picture's (``img``): 4 candidates, the local draft and the API
final from one of them, nothing adopted until one is locked. Each candidate carries its OCR
(``payload.candidates[i]``: ``ocr``, ``ocr_ok``, ``ocr_issue``) and the version the settings it
was made with (``payload.text``). A mismatch only warns (M5.5). Writing on a prop is the
prop's own picture's (``img.prop_text``), read back the same way.
"""

from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.models_db import Asset, Product
from drama_series_agent.pipeline.component import Inputs
from drama_series_agent.pipeline.components.img import (  # re-exported
    STYLE_GUIDE as STYLE_GUIDE,
)
from drama_series_agent.pipeline.components.img import (
    ImgComponent,
    lettering,
)
from drama_series_agent.pipeline.components.img import text_settings as text_settings
from drama_series_agent.pipeline.components.media import output_frame
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block

TEXT_IMAGE_SLOT = "text_image"
# Where the characters go on in post (后期贴字).
STYLE_PLACE = {"handwritten": "写在纸面上", "printed": "印在平整的表面上", "screen": "显示在屏幕上"}
COMPOSITE_GUIDE = (
    "画面里不要出现任何文字、数字或符号。留出一块干净的位置，后期会把「{exact}」{place}。"
)


class TextComponent(ImgComponent):
    id = "text"
    slot = TEXT_IMAGE_SLOT

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        asset = await session.get(Asset, product.owner_id)
        if asset is None or asset.retired or asset.kind != "text":
            raise PipelineError(404, "asset_not_found", id=product.owner_id)
        text = text_settings(asset, product.settings_json)
        frame = await output_frame(session, product.series_id)
        if text["method"] == "model":
            blocks = [
                Block("文字，必须逐字一致", text["exact"]),
                Block("字体", lettering(text)),
            ]
        else:
            place = STYLE_PLACE.get(text["style"], "贴上去")
            blocks = [Block("后期贴字", COMPOSITE_GUIDE.format(exact=text["exact"], place=place))]
        return Inputs(
            blocks=[*blocks, Block("画幅", frame["aspect"])],
            context={"kind": asset.kind, "frame": frame, "characters": [], "text": text},
        )

    def picture_params(self, inputs: Inputs) -> dict[str, Any]:
        text = inputs.context["text"]
        return {"text": text["exact"]} if text["method"] == "model" else {}

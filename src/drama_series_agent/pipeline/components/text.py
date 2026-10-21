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
was made with (``payload.text``). Locking a mismatch takes ``force`` (``AssetService.lock``).
"""

from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.models_db import Asset, Product
from drama_series_agent.modelhub.adapters.base import CallContext
from drama_series_agent.pipeline.component import Inputs, RunContext
from drama_series_agent.pipeline.components.img import ImgComponent
from drama_series_agent.pipeline.components.media import output_frame
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.qa import ocr

TEXT_IMAGE_SLOT = "text_image"
STYLE_GUIDE = {
    "handwritten": "手写：圆珠笔写在纸上，笔画自然，有一点倾斜和深浅变化。",
    "printed": "印刷：清楚的黑体或宋体，排得整齐。",
    "screen": "屏幕界面：手机或电脑的系统字体，清晰、发光，界面简洁。",
}
# Where the characters go on in post (后期贴字).
STYLE_PLACE = {"handwritten": "写在纸面上", "printed": "印在平整的表面上", "screen": "显示在屏幕上"}
COMPOSITE_GUIDE = (
    "画面里不要出现任何文字、数字或符号。留出一块干净的位置，后期会把「{exact}」{place}。"
)


def text_settings(asset: Asset, settings: dict[str, Any] | None) -> dict[str, str]:
    """The characters, how they are made and the lettering: the product's settings over what
    the analysis found."""
    seed = (asset.seed_json or {}).get("text") or {}
    mine = (settings or {}).get("text") or {}
    return {"exact": "", "method": "composite", "style": "printed", **seed, **mine}


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
                Block("字体", STYLE_GUIDE.get(text["style"], "")),
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

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        draft = await super().run(ctx, inputs)
        text = inputs.context["text"]
        call_ctx = self._call_ctx(ctx, None)
        candidates = []
        for f in draft.files:
            if f.get("role") == "candidate":
                read = await ocr.read(
                    self.services.router, self.services.store, f["sha256"], call_ctx
                )
                candidates.append(ocr.check(text["exact"], read, text["method"]))
        draft.payload = {**draft.payload, "candidates": candidates, "text": text}
        return draft

    async def check_upload(
        self, asset: Asset, product: Product, sha256: str
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """An uploaded picture's OCR against the text's settings now, and those settings."""
        text = text_settings(asset, product.settings_json)
        ctx = CallContext(component_id=self.id, series_id=product.series_id, product_id=product.id)
        read = await ocr.read(self.services.router, self.services.store, sha256, ctx)
        return ocr.check(text["exact"], read, text["method"]), text

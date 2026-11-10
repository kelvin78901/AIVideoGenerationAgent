"""改写看首帧 (M5 step 15g): what a local H3 take's first frame really shows, for the prompt
rewrite.

The rewrite (``vprompt``) used to be told the plan's intent for the first frame; a continuous
shot got nothing at all. In run8 the rewrite of 1-09 put her in the hall with the door shut and
a red umbrella, while the frame it started from (1-08's last) had her indoors, the door open, a
black umbrella by the wall; H3 shut the door first and picked up the black one. Now a vision
model of the ``vlook`` route describes the picture itself (a shot's locked keyframe, or the last
frame of the take a continuous shot follows):

- sent small (``compact_picture``: the uplink may be slow, step 15a), as an OpenAI-style image
  part, with ``templates/vid/first_frame_look.j2``;
- cached by picture, model and prompt (``LlmCache``), so every take and rerun from the same
  frame shares one call;
- a call that fails is not the take's failure: the rewrite goes on with the plan's intent
  (budget and confirmations still stop the run).
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from loguru import logger

from drama_series_agent.core.models_db import LlmCache
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    ModelError,
    ModelRequest,
)
from drama_series_agent.modelhub.adapters.upload import compact_picture
from drama_series_agent.modelhub.router import BudgetExceeded, NeedsConfirm
from drama_series_agent.pipeline.component import Services

VLOOK = "vlook"  # the route (config/components.yaml)
TASK = "first_frame_look"
TEMPLATE = "vid/first_frame_look.j2"
MAX_TOKENS = 400
MOCK_TEXT = (
    "Mock: a medium shot of a young woman in a beige trench coat standing in a doorway, "
    "facing the camera; a red umbrella leans on the wall to her left; warm lamp light."
)


@dataclass(frozen=True)
class Look:
    text: str
    model_key: str
    where: str
    cost_usd: float
    cached: bool


def request(services: Services, sha256: str) -> ModelRequest:
    """The question for picture ``sha256`` (a PNG or JPEG in the store)."""
    data = services.store.path_for(sha256).read_bytes()
    mime = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
    small, mime = compact_picture(data, mime)
    url = f"data:{mime};base64,{base64.b64encode(small).decode('ascii')}"
    prompt = services.compiler.render(TEMPLATE)
    content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]
    return ModelRequest(
        kind="vlm",
        messages=[{"role": "user", "content": content}],
        max_tokens=MAX_TOKENS,
        meta={"component": "vid", "task": TASK},
    )


def _cache_key(model: str, sha256: str, prompt: str) -> str:
    raw = f"{model}\n{sha256}\n{prompt}".encode()
    return f"{TASK}:{hashlib.sha256(raw).hexdigest()}"


async def describe(
    services: Services, sha256: str, item: str | None, ctx: CallContext
) -> Look | None:
    """The first frame described by the route's model; None when the call failed or the
    route is off."""
    router = services.router
    try:
        model = router.primary_model(await router.settings(VLOOK, item))
    except ModelError as exc:
        logger.info("no first-frame look ({})", exc.code)
        return None
    key = _cache_key(model, sha256, services.compiler.render(TEMPLATE))
    async with services.db.session() as session:
        row = await session.get(LlmCache, key)
    if row is not None:
        where = services.registry.spec(row.model_key).where
        return Look(str(row.value_json["text"]), row.model_key, where, 0.0, cached=True)
    try:
        routed = await router.call(VLOOK, request(services, sha256), ctx, model=model)
    except (BudgetExceeded, NeedsConfirm):
        raise
    except ModelError as exc:
        logger.warning("first-frame look failed ({}); the rewrite uses the plan's words", exc.code)
        return None
    text = (routed.text or "").strip()
    if not text:
        return None
    async with services.db.session() as session:
        if await session.get(LlmCache, key) is None:
            session.add(LlmCache(key=key, model_key=routed.model_key, value_json={"text": text}))
            await session.commit()
    return Look(text, routed.model_key, routed.where, routed.cost_usd, cached=False)


def estimate(services: Services, model: str | None) -> Estimate | None:
    """What one look costs on ``model`` (the route's default; estimates cannot read the
    series' own route), priced with a stand-in picture."""
    if model is None:
        return None
    prompt = services.compiler.render(TEMPLATE)
    content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": ""}}]
    req = ModelRequest(
        kind="vlm", messages=[{"role": "user", "content": content}], max_tokens=MAX_TOKENS
    )
    return services.registry.get(model).estimate(req)


def mock_look(_: ModelRequest) -> str:
    return MOCK_TEXT

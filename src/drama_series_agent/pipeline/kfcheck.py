"""关键帧检查 (M5.5 step 6, route ``kfcheck``): each keyframe candidate looked at by a vision model
against what its shot promised, and its drawn words read back by OCR. Only a warning (Kelvin
2026-11-10): the card says what is off, confirming goes on.

What is asked comes from the shot (``kf.gather`` puts it in ``context["checks"]``):

- ``start``: how people and things are when the shot begins (the contract);
- ``scale``: the props with a real size (the umbrella reaches her hip, not the door handle);
- ``text``: the words on a prop or on screen the model draws, and whether handwritten ones look
  handwritten; OCR (``qa/ocr.py``) checks the characters themselves;
- ``mouth``: who speaks only in their head (内心独白: lips closed);
- ``people``: an insert with nobody in it;
- ``light``: the light of the scene's time (no daylight at night; ``kf.LIGHT``);
- ``place``: the camera inside the scene's place (not on the other side of its door);
- ``hands``: a close-up of part of someone: every hand hers, nobody else, not her face
  (``kf.PART_VIEW``; run 19 1-05 had her behind a second hand);
- ``facing``: what she looks at turned to her, not to the camera (run 19 1-07's phone).

The answer is JSON (``{"items": [{"check", "ok", "note"}]}``); a picture is asked once per model and
question (``LlmCache``), and a call that fails is not the keyframe's failure (budget and
confirmations still stop the run), like ``vlook``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

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

KFCHECK = "kfcheck"  # the route (config/components.yaml)
TASK = "keyframe_check"
TEMPLATE = "kf/check.j2"
MAX_TOKENS = 600
CHECKS = ("start", "scale", "text", "mouth", "people", "light", "place", "hands", "facing")


def has_asks(asks: dict[str, Any] | None) -> bool:
    given = asks or {}
    return any(
        given.get(k)
        for k in (
            "start",
            "scale",
            "texts",
            "inner",
            "no_people",
            "light",
            "place",
            "part",
            "facing",
        )
    )


def request(services: Services, sha256: str, asks: dict[str, Any]) -> ModelRequest:
    data = services.store.path_for(sha256).read_bytes()
    mime = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
    small, mime = compact_picture(data, mime)
    url = f"data:{mime};base64,{base64.b64encode(small).decode('ascii')}"
    prompt = services.compiler.render(TEMPLATE, **asks)
    content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]
    return ModelRequest(
        kind="vlm",
        messages=[{"role": "user", "content": content}],
        max_tokens=MAX_TOKENS,
        meta={"component": "kf", "task": TASK},
    )


def parse(text: str) -> list[dict[str, Any]]:
    """The answer's items (unknown checks and anything unreadable dropped)."""
    m = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return []
    out = []
    for x in data.get("items") or [] if isinstance(data, dict) else []:
        if isinstance(x, dict) and x.get("check") in CHECKS and isinstance(x.get("ok"), bool):
            out.append({"check": x["check"], "ok": x["ok"], "note": str(x.get("note") or "")})
    return out


async def look(
    services: Services, sha256: str, asks: dict[str, Any], item: str | None, ctx: CallContext
) -> tuple[list[dict[str, Any]], str] | None:
    """The vision model's items for picture ``sha256`` and the model that answered; None when the
    route is off or the call failed."""
    router = services.router
    try:
        model = router.primary_model(await router.settings(KFCHECK, item))
    except ModelError as exc:
        logger.info("no keyframe check ({})", exc.code)
        return None
    prompt = services.compiler.render(TEMPLATE, **asks)
    key = f"{TASK}:{hashlib.sha256(f'{model}\n{sha256}\n{prompt}'.encode()).hexdigest()}"
    async with services.db.session() as session:
        row = await session.get(LlmCache, key)
    if row is not None:
        return list(row.value_json["items"]), row.model_key
    try:
        routed = await router.call(KFCHECK, request(services, sha256, asks), ctx, model=model)
    except (BudgetExceeded, NeedsConfirm):
        raise
    except ModelError as exc:
        logger.warning("keyframe check failed ({}); the candidate is left unchecked", exc.code)
        return None
    items = parse(routed.text or "")
    async with services.db.session() as session:
        if await session.get(LlmCache, key) is None:
            session.add(LlmCache(key=key, model_key=routed.model_key, value_json={"items": items}))
            await session.commit()
    return items, routed.model_key


def estimate(services: Services, model: str | None, asks: dict[str, Any]) -> Estimate | None:
    """One look on ``model`` (the route's default), priced with a stand-in picture."""
    if model is None:
        return None
    prompt = services.compiler.render(TEMPLATE, **asks)
    content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": ""}}]
    req = ModelRequest(
        kind="vlm", messages=[{"role": "user", "content": content}], max_tokens=MAX_TOKENS
    )
    return services.registry.get(model).estimate(req)


def mock_check(req: ModelRequest) -> str:
    """Mock: every check asked passes."""
    text = req.text()
    asked = [c for c in CHECKS if f"[{c}]" in text]
    return json.dumps({"items": [{"check": c, "ok": True, "note": ""} for c in asked]})

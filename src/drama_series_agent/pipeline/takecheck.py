"""take 检查 (M5.5 step 7, route ``takecheck``): each take's contact sheet looked at by a vision
model against its shot's contract, with what the take's own measures already say. Only a
warning (Kelvin 2026-11-10); the automatic reruns on a failed check are M6's.

Run 17 showed what to look for: a door opened, shut and opened again (``repeat``); water poured
over a still note (``event``); writing that changed between frames (``text``); lips moving on an
inner voice (``mouth``); a take that does not end where the next shot starts (``end``). Two more
need no model: a cut inside the take (``cut``, ``payload.cuts``) and a still opening longer than
a second (``hold``, ``payload.window``).

The sheet (``media/video.py:contact_sheet``, six frames, rows of three) is kept as the take's
``sheet`` file so the take card can show the frames; the answer's ``frame`` (1–6) says where.
Cached by sheet, model and question; a failed call leaves the take unchecked by the model.
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

TAKECHECK = "takecheck"  # the route (config/components.yaml)
TASK = "take_check"
TEMPLATE = "vid/take_check.j2"
MAX_TOKENS = 700
CHECKS = ("repeat", "event", "text", "mouth", "end")
HOLD_S = 1.0  # a still opening longer than this is flagged


def request(services: Services, sha256: str, asks: dict[str, Any]) -> ModelRequest:
    data = services.store.path_for(sha256).read_bytes()
    small, mime = compact_picture(data, "image/png")
    url = f"data:{mime};base64,{base64.b64encode(small).decode('ascii')}"
    prompt = services.compiler.render(TEMPLATE, **asks)
    content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]
    return ModelRequest(
        kind="vlm",
        messages=[{"role": "user", "content": content}],
        max_tokens=MAX_TOKENS,
        meta={"component": "vid", "task": TASK},
    )


def parse(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return []
    out = []
    for x in data.get("items") or [] if isinstance(data, dict) else []:
        if isinstance(x, dict) and x.get("check") in CHECKS and isinstance(x.get("ok"), bool):
            frame = x.get("frame")
            out.append(
                {
                    "check": x["check"],
                    "ok": x["ok"],
                    "note": str(x.get("note") or ""),
                    "frame": frame if isinstance(frame, int) and 1 <= frame <= 6 else None,
                }
            )
    return out


def measured(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """What the take's own measures say: a cut inside it, a still opening."""
    cuts = list(payload.get("cuts") or [])
    hold = float((payload.get("window") or {}).get("in_s") or 0.0)
    return [
        {
            "check": "cut",
            "ok": not cuts,
            "note": "、".join(f"{c:g} 秒" for c in cuts),
            "frame": None,
        },
        {"check": "hold", "ok": hold <= HOLD_S, "note": f"{hold:g} 秒", "frame": None},
    ]


async def look(
    services: Services, sha256: str, asks: dict[str, Any], item: str | None, ctx: CallContext
) -> tuple[list[dict[str, Any]], str] | None:
    """The model's items for sheet ``sha256`` and who answered; None when off or failed."""
    router = services.router
    try:
        model = router.primary_model(await router.settings(TAKECHECK, item))
    except ModelError as exc:
        logger.info("no take check ({})", exc.code)
        return None
    prompt = services.compiler.render(TEMPLATE, **asks)
    key = f"{TASK}:{hashlib.sha256(f'{model}\n{sha256}\n{prompt}'.encode()).hexdigest()}"
    async with services.db.session() as session:
        row = await session.get(LlmCache, key)
    if row is not None:
        return list(row.value_json["items"]), row.model_key
    try:
        routed = await router.call(TAKECHECK, request(services, sha256, asks), ctx, model=model)
    except (BudgetExceeded, NeedsConfirm):
        raise
    except ModelError as exc:
        logger.warning("take check failed ({}); the take is left unchecked", exc.code)
        return None
    items = parse(routed.text or "")
    async with services.db.session() as session:
        if await session.get(LlmCache, key) is None:
            session.add(LlmCache(key=key, model_key=routed.model_key, value_json={"items": items}))
            await session.commit()
    return items, routed.model_key


def estimate(services: Services, model: str | None, asks: dict[str, Any]) -> Estimate | None:
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

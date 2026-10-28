"""按镜头选工作流 (SPEC 6.4.8; M5 step 12a): which local workflow a shot's takes go to.

A take whose route is a local model of the video component goes to, in order:

1. the model the caller named or the user picked for this shot (Inspector: an item override of
   ``local_model``);
2. the first rule of the series' table the shot meets (``Rules``; per series in ``app_setting``
   under ``vid.select.<series id>``, the config's ``select_rules`` while never saved);
3. with ``suggest`` on and more than one workflow to pick from, the ``vselect`` route's answer:
   asked before the shot's first take (estimates only read the cache), cached by what it was
   told, so a changed shot or another set of workflows asks again; a failed or odd answer is
   skipped;
4. the route's local model.

Only workflows of 平台推荐 and 我的工作流 this machine can run are picked: unverified ones run
only when picked by hand. A rule whose model cannot be picked is passed over. What decided it
(``Choice.select``) goes on the take's ``model_call.select_json``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import Resolved, SelectRule, get_config
from drama_series_agent.core.models_db import AppSetting, LlmCache, utcnow
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.pipeline.component import Inputs, Services
from drama_series_agent.pipeline.components.kf import local_workflow
from drama_series_agent.pipeline.hashing import canonical_json

VIDEO = "vid"
VSELECT = "vselect"  # the route of the suggestion (config/components.yaml)
LANGUAGE = {"zh-CN": "Chinese", "en": "English"}


class Rules(BaseModel):
    """A series' rules table and whether the LLM suggests when none matches."""

    model_config = ConfigDict(extra="forbid")

    rules: list[SelectRule] = Field(default_factory=list)
    suggest: bool = False


@dataclass(frozen=True)
class Choice:
    model: str
    select: dict[str, Any] | None = None  # by, and the rule / reason (model_call.select_json)


def _key(series_id: str) -> str:
    return f"vid.select.{series_id}"


def default_rules() -> Rules:
    try:
        comp = get_config().components.component(VIDEO)
    except KeyError:
        return Rules()
    return Rules(rules=list(comp.select_rules), suggest=comp.select_suggest)


async def load_rules(session: AsyncSession, series_id: str) -> tuple[Rules, bool]:
    """The series' table, and whether it was saved (False: the config's)."""
    row = await session.get(AppSetting, _key(series_id))
    if row is None:
        return default_rules(), False
    return Rules.model_validate(row.value_json), True


async def save_rules(session: AsyncSession, series_id: str, rules: Rules | None) -> None:
    """Replace the series' table; None goes back to the config's."""
    row = await session.get(AppSetting, _key(series_id))
    if rules is None:
        if row is not None:
            await session.delete(row)
            await session.commit()
        return
    row = row or AppSetting(key=_key(series_id))
    row.value_json = rules.model_dump(mode="json", exclude_none=True)
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()


def pickable(registry: Registry, settings: Resolved | None = None) -> list[str]:
    """The video component's local models a rule or the LLM may pick, in config order:
    ones with a workflow, not unverified, runnable here."""
    cfg = get_config()
    try:
        local = cfg.components.component(VIDEO).local
    except KeyError:
        return []
    unavailable = settings.unavailable if settings is not None else {}
    return [
        key
        for key in local
        if key not in cfg.unverified
        and key not in unavailable
        and local_workflow(registry, key) is not None
    ]


def features(inputs: Inputs) -> dict[str, Any]:
    """What a rule's conditions read off a shot (``vid.gather``'s context)."""
    context = inputs.context
    shot = context.get("shot") or {}
    return {
        "shot_type": shot.get("shot_type"),
        "framing": shot.get("framing"),
        "dialogue": bool(context.get("dialogue")),
        "audio_mode": context.get("audio_mode"),
        "refs": bool(context.get("refs")),
        "voices": bool(context.get("voices")),
    }


def matches(rule: SelectRule, facts: dict[str, Any]) -> bool:
    wanted = rule.when.model_dump(exclude_none=True)
    return all(facts.get(name) == value for name, value in wanted.items())


async def choose(
    services: Services,
    inputs: Inputs,
    model: str,
    settings: Resolved,
    *,
    series_id: str,
    lang: str,
    named: bool,
    ask: bool,
    ctx: CallContext,
) -> Choice:
    """The local model a shot's take goes to and why (the order in the module doc). ``named``:
    the caller chose ``model``. ``ask``: the LLM may be asked (else only its cached answer)."""
    try:
        local = get_config().components.component(VIDEO).local
    except KeyError:
        return Choice(model)
    if model not in local:
        return Choice(model)  # an API route: nothing to pick between
    if named or (
        settings.sources.get("local_model") == "item"
        and settings.values.get("local_model") == model
    ):
        return Choice(model, {"by": "manual"})
    candidates = pickable(services.registry, settings)
    async with services.db.session() as session:
        table, _saved = await load_rules(session, series_id)
    facts = features(inputs)
    for i, rule in enumerate(table.rules):
        if rule.model in candidates and matches(rule, facts):
            return Choice(rule.model, {"by": "rule", "rule": i})
    if table.suggest and len(candidates) > 1:
        suggested = await _suggest(services, inputs, model, candidates, lang, ask=ask, ctx=ctx)
        if suggested is not None:
            return suggested
    return Choice(model, {"by": "default"})


# ---------------------------------------------------------------------- the LLM's suggestion


def _workflow_facts(services: Services, key: str, default: str) -> dict[str, Any]:
    wf = local_workflow(services.registry, key)
    assert wf is not None  # pickable() only lists models with one
    caps = wf.meta.caps
    durations = caps.get("duration_s") or []
    return {
        "key": key,
        "name": wf.meta.name.get("en") or wf.meta.name.get("zh") or wf.slug,
        "tier": wf.meta.tier,
        "is_default": key == default,
        "max_seconds": max(durations) if durations else None,
        "max_reference_pictures": len(wf.bindings("ref_image")),
        "takes_voice_samples": wf.has("ref_audio"),
        "takes_dialogue_audio": wf.has("dialogue_audio"),
    }


def suggest_messages(
    services: Services, inputs: Inputs, default: str, candidates: list[str], lang: str
) -> list[dict[str, Any]]:
    context = inputs.context
    shot = {
        **{k: v for k, v in features(inputs).items() if k not in ("dialogue", "refs", "voices")},
        "seconds": context.get("seconds"),
        "look": context.get("look") or [],
        "dialogue_lines": len(context.get("dialogue") or []),
        "reference_pictures": len(context.get("refs") or []),
        "voice_samples": len(context.get("voices") or []),
    }
    user = {
        "shot": shot,
        "workflows": [_workflow_facts(services, key, default) for key in candidates],
    }
    system = services.compiler.render(
        "vid/select_system.j2", language=LANGUAGE.get(lang, "Chinese")
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False, indent=1)},
    ]


def _answer(data: Any, text: str, candidates: list[str]) -> tuple[str, str] | None:
    if not isinstance(data, dict):
        found = re.search(r"\{.*\}", text or "", re.S)
        try:
            data = json.loads(found.group(0)) if found else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        return None
    model, reason = data.get("model"), data.get("reason")
    if model not in candidates or not isinstance(reason, str) or not reason.strip():
        return None
    return str(model), reason.strip()[:300]


async def _suggest(
    services: Services,
    inputs: Inputs,
    default: str,
    candidates: list[str],
    lang: str,
    *,
    ask: bool,
    ctx: CallContext,
) -> Choice | None:
    router = services.router
    settings = await router.settings(VSELECT, None)
    try:
        writer = router.primary_model(settings)
    except ModelError:
        return None
    messages = suggest_messages(services, inputs, default, candidates, lang)
    digest = hashlib.sha256(
        canonical_json({"model": writer, "messages": messages}).encode("utf-8")
    ).hexdigest()
    key = f"vselect:{digest}"
    async with services.db.session() as session:
        row = await session.get(LlmCache, key)
    if row is not None:
        cached = row.value_json
        return Choice(
            str(cached["model"]),
            {"by": "suggest", "reason": cached["reason"], "suggested_by": row.model_key},
        )
    if not ask:
        return None
    req = ModelRequest(
        kind="llm",
        messages=messages,
        json_mode=True,
        max_tokens=300,
        meta={"component": VIDEO, "task": "select"},
    )
    try:
        routed = await router.call(VSELECT, req, replace(ctx, component_id=VSELECT))
    except ModelError as exc:  # no suggestion this time; the default stands
        logger.warning("workflow suggestion failed ({}); the shot keeps its route", exc.code)
        return None
    answer = _answer(routed.json, routed.text or "", candidates)
    if answer is None:
        logger.warning("workflow suggestion did not name one of {}", candidates)
        return None
    model, reason = answer
    async with services.db.session() as session:
        if await session.get(LlmCache, key) is None:
            session.add(
                LlmCache(
                    key=key,
                    model_key=routed.model_key,
                    value_json={"model": model, "reason": reason},
                )
            )
            await session.commit()
    return Choice(model, {"by": "suggest", "reason": reason, "suggested_by": routed.model_key})


def mock_suggest(req: ModelRequest) -> dict[str, Any]:
    """Mock mode: the workflow that takes the most, else the default; a fixed reason."""
    user = json.loads(str((req.messages or [{}, {}])[1].get("content") or "{}"))
    flows = list(user.get("workflows") or [])
    shot = user.get("shot") or {}
    pick = next((w for w in flows if w.get("is_default")), flows[0] if flows else {})
    if shot.get("voice_samples") and shot.get("audio_mode") == "native":
        pick = next((w for w in flows if w.get("takes_voice_samples")), pick)
    return {"model": pick.get("key"), "reason": "Mock：按镜头的声音和参考图选的"}

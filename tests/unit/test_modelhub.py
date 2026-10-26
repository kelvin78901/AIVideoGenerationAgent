from __future__ import annotations

import io
import json
import wave
from collections.abc import AsyncIterator

import pytest

from drama_series_agent.core.config import Defaults, Resolved, get_config
from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.overrides import put_override, save_defaults
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub import calllog
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    Pricing,
    Usage,
)
from drama_series_agent.modelhub.adapters.mock import (
    MOCK_TEXT_KEY,
    MockAdapter,
    MockSettings,
    gradient_png,
    png_texts,
    solid_png,
)
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.modelhub.registry import Registry, UnavailableAdapter, is_mock_mode
from drama_series_agent.modelhub.router import BudgetExceeded, Router


def _llm_req(text: str = "林晚撑着红伞走进楼道。", **params: object) -> ModelRequest:
    return ModelRequest(kind="llm", messages=[{"role": "user", "content": text}], params=params)


# --------------------------------------------------------------------------- pricing


def test_token_pricing_and_offpeak() -> None:
    p = Pricing(unit="token", price_in=1.32, price_out=3.96, offpeak={"factor": 0.5})
    usage = Usage(tokens_in=1_000_000, tokens_out=500_000)
    assert cost_usd(p, usage) == pytest.approx(1.32 + 1.98)
    assert cost_usd(p, usage, offpeak=True) == pytest.approx((1.32 + 1.98) / 2)


def test_media_pricing_units() -> None:
    assert cost_usd(Pricing(unit="image", price=0.14), Usage(images=3)) == pytest.approx(0.42)
    h3 = Pricing(unit="second", price_by_res={"768p": 0.08, "2k": 0.13})
    assert cost_usd(h3, Usage(output_seconds=10), resolution="2k") == pytest.approx(1.3)
    seedance = Pricing(unit="minute", price=24.6)
    assert cost_usd(seedance, Usage(output_seconds=30)) == pytest.approx(12.3)
    regen = Pricing(unit="second", price=0.05, input_price_per_second=0.05)
    assert cost_usd(regen, Usage(output_seconds=10, input_seconds=10)) == pytest.approx(1.0)
    cny = Pricing(unit="call", price=7.1, currency="CNY")
    assert cost_usd(cny, Usage(), rates={"CNY_per_USD": 7.1}) == pytest.approx(1.0)
    assert cost_usd(Pricing(unit="free"), Usage(tokens_in=10**9)) == 0
    pro = Pricing(unit="image", price=0.134, price_by_res={"4K": 0.24})
    assert cost_usd(pro, Usage(images=2), resolution="4K") == pytest.approx(0.48)
    assert cost_usd(pro, Usage(images=2), resolution="2K") == pytest.approx(0.268)


def test_extras_are_billed_per_use() -> None:
    """MiniMax's voice design ($3) on top of the characters (M3)."""
    speech = Pricing(unit="char", price=100 / 1e6, extras={"voice_design": 3.0})
    usage = Usage(chars=1000, calls={"voice_design": 1})
    assert cost_usd(speech, usage) == pytest.approx(3.1)
    assert cost_usd(speech, Usage(chars=1000)) == pytest.approx(0.1)


# --------------------------------------------------------------------------- registry


def test_registry_reads_all_model_sections() -> None:
    reg = Registry.from_config(get_config(), mock=False)
    llm = reg.spec("deepseek/v4-pro")
    assert llm.kind == "llm" and llm.where == "api" and llm.provider_id == "deepseek"
    assert llm.pricing.price_in == pytest.approx(1.32)
    assert reg.spec("local/qwen3.6-27b").where == "local"
    h3 = reg.spec("minimax/h3-api")
    assert h3.pricing.unit == "second" and h3.pricing.price_by_res == {"768p": 0.08, "2k": 0.13}
    tts = reg.spec("minimax/speech-2.8-hd")
    assert tts.pricing.unit == "char" and tts.pricing.price == pytest.approx(350 / 1e6)
    assert tts.pricing.currency == "CNY" and tts.base_url == "https://api.minimax.cn/v1"
    assert tts.pricing.extras == {
        "voice_design": 9.9,
        "voice_clone": 9.9,
        "design_preview_char": 0.0002,
    }
    assert tts.adapter == "minimax_speech" and tts.model_id == "speech-2.8-hd"
    # Media models use their account's key (one MiniMax / Google key for everything).
    assert tts.key_name == "MINIMAX_API_KEY" and tts.base_url
    assert reg.spec("google/nano-banana-pro").key_name == "GEMINI_API_KEY"
    assert reg.spec("comfy/h3").caps.aspects and reg.spec("comfy/h3").workflow == "h3-i2v"
    assert reg.spec("comfy/h3").where == "local" and reg.spec("comfy/h3").pricing.unit == "free"
    assert isinstance(reg.get("deepseek/v4-pro"), UnavailableAdapter)
    with pytest.raises(ModelError) as err:
        reg.spec("nope/model")
    assert err.value.code == "unknown_model"


def test_mock_mode_swaps_every_adapter() -> None:
    assert is_mock_mode()  # conftest sets DRAMA_MOCK=1
    reg = Registry.from_config(get_config())
    adapter = reg.get("minimax/h3-api")
    assert isinstance(adapter, MockAdapter)
    assert adapter.spec.pricing.price_by_res  # real prices kept


def test_mock_mode_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRAMA_MOCK")
    assert is_mock_mode()
    monkeypatch.setenv("DRAMA_MOCK", "0")
    assert not is_mock_mode()


# --------------------------------------------------------------------------- mock outputs


def _spec(kind: str, key: str = "mock/x") -> ModelSpec:
    return ModelSpec(key=key, kind=kind, where="api", display=key)


async def test_mock_llm_is_deterministic_and_json() -> None:
    adapter = MockAdapter(_spec("llm"))
    a = await adapter.run(_llm_req(), CallContext())
    b = await adapter.run(_llm_req(), CallContext())
    assert a.text == b.text and a.text and "Mock" in a.text
    assert a.usage.tokens_in and a.usage.tokens_out
    j = await adapter.run(ModelRequest(kind="llm", prompt="x", json_mode=True), CallContext())
    assert json.loads(j.text or "")["mock"] is True


async def test_mock_media_outputs() -> None:
    img = await MockAdapter(_spec("image")).run(
        ModelRequest(kind="image", prompt="p", params={"width": 90, "height": 160, "n": 2}),
        CallContext(),
    )
    assert len(img.files) == 2 and img.usage.images == 2
    assert img.files[0].data is not None and img.files[0].data.startswith(b"\x89PNG")
    assert img.files[0].w == 90

    audio = await MockAdapter(_spec("tts")).run(
        ModelRequest(kind="tts", prompt="你好", params={"duration_s": 0.5}), CallContext()
    )
    data = audio.files[0].data
    assert data is not None
    with wave.open(io.BytesIO(data)) as wav:
        assert wav.getframerate() == 48000
        assert wav.getnframes() == 24000

    video = await MockAdapter(_spec("video")).run(
        ModelRequest(
            kind="video", prompt="p", params={"duration_s": 0.5, "width": 64, "height": 64}
        ),
        CallContext(),
    )
    vdata = video.files[0].data
    assert vdata is not None and vdata[4:8] == b"ftyp"
    assert video.usage.output_seconds == 0.5


def test_mock_pictures_carry_the_text_they_were_asked_to_show() -> None:
    data = gradient_png(4, 6, (100, 120, 140), (130, 150, 170), {MOCK_TEXT_KEY: "等你到十二点。"})
    assert data.startswith(b"\x89PNG") and png_texts(data) == {MOCK_TEXT_KEY: "等你到十二点。"}
    assert png_texts(solid_png(2, 2, (1, 2, 3))) == {}


def test_solid_png_header() -> None:
    png = solid_png(3, 2, (255, 0, 0))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert png[16:24] == (3).to_bytes(4, "big") + (2).to_bytes(4, "big")


# --------------------------------------------------------------------------- router


@pytest.fixture
async def hub(studio_db: Database) -> AsyncIterator[tuple[Router, Registry, EventBus]]:
    bus = EventBus(studio_db)
    reg = Registry.from_config(get_config(), mock=True, mock_settings=MockSettings())
    yield Router(studio_db, bus, reg, store=BlobStore()), reg, bus


async def test_call_uses_component_default_and_logs(hub: tuple[Router, Registry, EventBus]) -> None:
    router, _, bus = hub
    ctx = CallContext(component_id="script", series_id="s1", episode_id="e1", job_id="j1")
    routed = await router.call("script", _llm_req(), ctx)
    assert routed.model_key == "deepseek/v4-pro" and routed.where == "api"
    assert not routed.is_fallback
    rows = await calllog.recent(router.db)
    assert len(rows) == 1
    row = rows[0]
    assert row.id == routed.call_id
    assert (row.series_id, row.episode_id, row.job_id, row.component_id) == (
        "s1",
        "e1",
        "j1",
        "script",
    )
    assert row.status == "success" and row.billed and row.provider_id == "deepseek"
    assert row.tokens_in and row.tokens_out
    prices = dict(row.unit_prices_json or {})
    assert prices.pop("offpeak")["factor"] == 0.5  # its note is providers.yaml's wording
    assert prices == {
        "unit": "token",
        "price_in": 1.32,
        "price_out": 3.96,
        "currency": "USD",
        "as_of": "2026-10-14",
    }
    expected = (row.tokens_in * 1.32 + row.tokens_out * 3.96) / 1e6
    assert row.cost_usd == pytest.approx(expected)
    assert row.started_at and row.finished_at and row.started_at <= row.finished_at
    assert await calllog.total_cost(router.db, episode_id="e1") == pytest.approx(expected)
    cost_events = [e for e in await bus.replay(0) if e.type == "cost.updated"]
    assert cost_events[0].data["call_id"] == routed.call_id


async def test_a_local_workflow_call_logs_the_workflow(
    hub: tuple[Router, Registry, EventBus], monkeypatch: pytest.MonkeyPatch
) -> None:
    """SPEC 6.4.5: model_call says which workflow file and which ComfyUI made it."""
    router, reg, _ = hub
    adapter = reg.get("comfy/flux3-klein")
    real_run = adapter.run

    async def run(req: ModelRequest, ctx: CallContext) -> ModelResult:
        result = await real_run(req, ctx)
        comfy = {"workflow_id": "flux3-klein", "workflow_sha256": "ab" * 32, "comfy_env_hash": "e1"}
        return ModelResult(files=result.files, usage=result.usage, raw={"comfy": comfy})

    monkeypatch.setattr(adapter, "run", run)
    req = ModelRequest(kind="image", prompt="林晚站在楼道口", params={"n": 1})
    await router.call("kf", req, model="comfy/flux3-klein")
    row = (await calllog.recent(router.db))[0]
    assert (row.workflow_id, row.workflow_sha256, row.comfy_env_hash) == (
        "flux3-klein",
        "ab" * 32,
        "e1",
    )
    # An API model has none of them.
    await router.call("kf", req, model="google/nano-banana-2.1")
    api = next(r for r in await calllog.recent(router.db) if r.where == "api")
    assert (api.workflow_id, api.workflow_sha256, api.comfy_env_hash) == (None, None, None)


async def test_hybrid_defaults_to_local_draft_and_api_on_request(
    hub: tuple[Router, Registry, EventBus],
) -> None:
    router, _, _ = hub
    draft = await router.call("img", ModelRequest(kind="image", prompt="林晚"))
    assert draft.model_key == "comfy/qwen-image" and draft.where == "local"
    assert draft.cost_usd == 0
    assert router.store.exists(draft.files[0].sha256)
    final = await router.call("img", ModelRequest(kind="image", prompt="林晚"), where="api")
    assert final.model_key == "google/nano-banana-pro"
    assert final.cost_usd == pytest.approx(0.134)


async def test_override_and_explicit_model(hub: tuple[Router, Registry, EventBus]) -> None:
    router, _, _ = hub
    async with router.db.session() as s:
        await put_override(
            s, scope="component", component_id="script", data={"api_model": "moonshot/kimi-k2.6"}
        )
        await put_override(
            s,
            scope="item",
            scope_id="shot:1-05",
            component_id="script",
            data={"api_model": "qwen/qwen3.8-max"},
        )
    assert (await router.call("script", _llm_req())).model_key == "moonshot/kimi-k2.6"
    assert (
        await router.call("script", _llm_req(), item="shot:1-05")
    ).model_key == "qwen/qwen3.8-max"
    picked = await router.call("script", _llm_req(), model="zhipu/glm-5.3")
    assert picked.model_key == "zhipu/glm-5.3"


async def test_fallback_on_error_is_logged(hub: tuple[Router, Registry, EventBus]) -> None:
    router, reg, _ = hub
    reg.mock_settings.fail_keys.add("deepseek/v4-pro")
    routed = await router.call("script", _llm_req())
    assert routed.model_key == "qwen/qwen3.8-max"  # components.yaml balanced.fallback_to
    assert routed.is_fallback and routed.fallback_reason == "mock_failure"
    rows = sorted(await calllog.recent(router.db), key=lambda r: r.id or 0)
    assert [(r.model_key, r.status, r.billed) for r in rows] == [
        ("deepseek/v4-pro", "error", False),
        ("qwen/qwen3.8-max", "success", True),
    ]
    assert rows[0].error_code == "mock_failure" and rows[0].cost_usd == 0
    assert rows[1].is_fallback and rows[1].fallback_reason == "mock_failure"


async def test_fallback_disabled_raises(hub: tuple[Router, Registry, EventBus]) -> None:
    router, reg, _ = hub
    async with router.db.session() as s:
        await put_override(
            s, scope="component", component_id="script", data={"fallback": {"enabled": False}}
        )
    reg.mock_settings.fail_keys.add("deepseek/v4-pro")
    with pytest.raises(ModelError) as err:
        await router.call("script", _llm_req())
    assert err.value.code == "mock_failure"
    assert len(await calllog.recent(router.db)) == 1


async def test_a_step_of_a_flow_does_not_fall_back(hub: tuple[Router, Registry, EventBus]) -> None:
    """``fallback=False``: the component falls back for the whole flow (a voice's design and
    its variants), never one piece of it."""
    router, reg, _ = hub
    reg.mock_settings.fail_keys.add("deepseek/v4-pro")
    with pytest.raises(ModelError) as err:
        await router.call("script", _llm_req(), fallback=False)
    assert err.value.code == "mock_failure"
    assert len(await calllog.recent(router.db)) == 1


async def test_timeout_falls_back_and_logs_timeout(hub: tuple[Router, Registry, EventBus]) -> None:
    router, reg, _ = hub
    router.api_timeout_s = 0.05
    reg.mock_settings.hang_keys.add("deepseek/v4-pro")
    routed = await router.call("script", _llm_req())
    assert routed.fallback_reason == "timeout"
    first = sorted(await calllog.recent(router.db), key=lambda r: r.id or 0)[0]
    assert first.status == "timeout" and first.error_code == "timeout"


async def test_all_models_fail(hub: tuple[Router, Registry, EventBus]) -> None:
    router, reg, _ = hub
    reg.mock_settings.fail_keys.update({"deepseek/v4-pro", "qwen/qwen3.8-max"})
    with pytest.raises(ModelError):
        await router.call("script", _llm_req())
    assert [r.status for r in await calllog.recent(router.db)] == ["error", "error"]


async def test_budget_guard_blocks_before_spending(hub: tuple[Router, Registry, EventBus]) -> None:
    router, _, _ = hub

    class Cap:
        async def check(
            self, spec: ModelSpec, estimate: Estimate, settings: Resolved, ctx: CallContext
        ) -> None:
            raise BudgetExceeded(estimate.cost_usd, 0.0, "call")

    router.budget = Cap()
    with pytest.raises(BudgetExceeded):
        await router.call("script", _llm_req())
    assert await calllog.recent(router.db) == []


async def test_unknown_component_and_model(hub: tuple[Router, Registry, EventBus]) -> None:
    router, _, _ = hub
    with pytest.raises(KeyError):
        await router.call("nope", _llm_req())
    with pytest.raises(ModelError) as err:
        await router.call("script", _llm_req(), model="nope/x")
    assert err.value.code == "unknown_model"


async def test_component_switched_off(hub: tuple[Router, Registry, EventBus]) -> None:
    """全本地 turns 3D 场景 off (no local version): calling it is an error, not a guess."""
    router, _, _ = hub
    async with router.db.session() as s:
        await save_defaults(s, Defaults(preset="local"))
    with pytest.raises(ModelError) as err:
        await router.call("world", _llm_req())
    assert err.value.code == "component_off"
    assert await calllog.recent(router.db) == []

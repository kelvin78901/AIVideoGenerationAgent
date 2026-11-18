"""自动质检 (M6 step 3; SPEC 4.2, 5 ``qa``): every new take measured, then held to the series'
thresholds.

**When.** Each version a run appends to a shot's video product with a clip in it (a take, a
fallback, an API final; M6's repairs too) queues a ``qa.take`` job on the ``cpu`` queue, so QA
never holds up the video queue; 「重新质检」 (``POST /versions/{id}/qa``) queues one by hand.

**What** (one check per metric; ``ok: None`` where it does not apply or could not run):

- ``face``: each character the shot films against their locked reference picture (the tool's
  per-character median similarity); the take's value is the lowest. No character: n/a.
- ``lipsync``: SyncNet confidence that the take's own sound fits its picture as it is (within
  2 frames; ``in_sync``, M6 step 5c); only a shot with a line said on screen and sound in the
  take.
- ``asr``: the take's speech read back and compared with the lines said on screen (character
  error rate, NFKC, punctuation and spaces out); only a 原生同步 take speaks them itself. The
  series' character names go to the recogniser as a hint (Whisper writes 周屿 as 周瑜 without
  it). A 原生同步 shot with no line said on screen is read too: speech heard there (an inner
  line the take says aloud) fails it, nothing heard is n/a (M6 step 5c).
- ``speaker``: each line's voice against the speaker's locked voice (the lowest similarity);
  原生同步 takes with locked voices only.
- ``ocr``: the on-screen text the model draws (``method: model``) read once a second. Only
  frames that read something like one of the texts are compared (two of its characters at
  least: a shop sign or OCR noise is not the text), punctuation left out (OCR drops a comma in
  one frame of five); each must read one of the texts whole. Nothing read: n/a, the text too
  small in a medium shot (M6 step 5c).
- ``vlm``: the take check (M5.5 ``pipeline/takecheck.py``, its route merged into this one): the
  take's six-frame sheet looked at against its contract and the 连续性账本, with the take's own
  measures (a cut inside it, a still opening). Cached by sheet and question, so the look the run
  already made costs nothing again.

Every tool is a ``router.call()`` on the route ``qa`` with the tool's model (``tools`` in
``components.yaml``; local, on the CPU, $0, each logged in ``model_call``). Mock answers each
with stable passing values; a take's ``params.mock_qa`` (``{"face": 0.1, "ocr": "23:58"}``) says
what Mock should measure instead — only Mock reads it (the demo's bad takes, tests).

**Measured, then judged.** The checks keep what was measured; ``judge`` holds it to the series'
thresholds and switches (generate rules), so changing a threshold judges the takes again without
measuring (``rejudge``). A check turned off is still shown but fails nothing. The result is the
version's ``qa_json`` ``{checks, score, thresholds, qa_on, ran_at}`` and ``qa_pass`` (metadata,
the content hash stays), copied to the ``model_call`` that made the clip (``params.call_id``) as
``qa_scores_json`` / ``qa_pass``. ``score``: the mean of the counted checks, each scaled to 0–1;
推荐 is the passing take with the highest (SPEC 4.2, ``web/src/lib/takes.ts``). Nothing counted
(every tool missing, the look off): ``qa_pass`` None, 未检查.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlmodel import col, select

from drama_series_agent.core.config import get_config
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.jobs import JobContext, JobError, JobQueue
from drama_series_agent.core.models_db import (
    Asset,
    Job,
    ModelCall,
    Product,
    ProductVersion,
    Shot,
    utcnow,
)
from drama_series_agent.media.video import VideoError, contact_sheet
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.pipeline import takecheck
from drama_series_agent.pipeline.component import ComponentError, Inputs, Services
from drama_series_agent.pipeline.components.vid import take_asks
from drama_series_agent.pipeline.drafts import file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.generate import GenerateRules, load_rules
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.runs import item_of
from drama_series_agent.qa.ocr import normalize

if TYPE_CHECKING:
    from drama_series_agent.pipeline.component import ComponentRegistry
    from drama_series_agent.pipeline.qa_policy import QaPolicy

QA = "qa"  # the route and its config (components.yaml)
QA_JOB = "qa.take"
QA_QUEUE = "cpu"
VIDEO_COMPONENT = "vid"
VIDEO_SLOT = "video"
METRICS = ("face", "lipsync", "asr", "speaker", "ocr", "vlm")
OCR_EVERY_S = 1.0
FACE_EVERY_S = 0.5


# --------------------------------------------------------------------------- judging


def cer(said: str, expected: str) -> float:
    """Character error rate of ``said`` against ``expected``: NFKC, punctuation and spaces
    out, edits over the expected length."""
    a, b = _plain(said), _plain(expected)
    if not b:
        return 0.0 if not a else 1.0
    return round(_distance(a, b) / len(b), 4)


def _plain(text: str) -> str:
    return "".join(
        ch for ch in normalize(text) if not unicodedata.category(ch).startswith(("P", "S"))
    )


def _like(read: str, want: str) -> bool:
    """``read`` is trying to be ``want``: two of its characters at least (all, if fewer)."""
    return len(set(read) & set(want)) >= min(2, len(set(want)))


def _distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def _limit(metric: str, rules: GenerateRules) -> float | None:
    t = rules.thresholds
    return {
        "face": t.face_sim,
        "lipsync": t.syncnet_conf,
        "asr": t.cer_max,
        "speaker": t.speaker_sim,
    }.get(metric)


def _verdict(check: dict[str, Any], limit: float | None) -> bool | None:
    if check.get("na") or check.get("error"):
        return None
    metric, value = check["metric"], check.get("value")
    if metric in ("ocr", "vlm"):
        match = check.get("match")
        return None if match is None else bool(match)
    if value is None or limit is None:
        return None
    v = float(value)
    return v <= limit if metric == "asr" else v >= limit


def _scaled(check: dict[str, Any]) -> float:
    """A counted check on 0–1 for the total."""
    metric, value = check["metric"], check.get("value")
    if metric == "vlm":
        items = check.get("items") or []
        return sum(1 for x in items if x.get("ok")) / len(items) if items else float(check["ok"])
    if metric == "ocr" or value is None:
        return float(check["ok"])
    v = float(value)
    raw = {"lipsync": v / 4, "asr": 1 - v}.get(metric, v)  # in_sync: 1–3 in sync (5c)
    return min(1.0, max(0.0, raw))


ISSUES = {"face": "face_mismatch", "ocr": "text_mismatch"}


def judge(
    raw: list[dict[str, Any]], rules: GenerateRules
) -> tuple[list[dict[str, Any]], float, bool | None]:
    """The checks held to ``rules`` (``ok``, ``off``, ``threshold``, ``issue``), the total and
    whether the take passes (None: nothing could be counted)."""
    checks = []
    for c in raw:
        metric = c["metric"]
        limit = _limit(metric, rules)
        ok = _verdict(c, limit)
        checks.append(
            {
                **c,
                "ok": ok,
                "off": not getattr(rules.qa_on, metric, True),
                "threshold": limit,
                "issue": ISSUES.get(metric) if ok is False else None,
            }
        )
    counted = [c for c in checks if c["ok"] is not None and not c["off"]]
    if not counted:
        return checks, 0.0, None
    score = round(sum(_scaled(c) for c in counted) / len(counted), 3)
    return checks, score, all(c["ok"] for c in counted)


def result(
    raw: list[dict[str, Any]], rules: GenerateRules, **extra: Any
) -> tuple[dict[str, Any], bool | None]:
    """``qa_json`` and ``qa_pass`` for measured ``raw`` checks."""
    checks, score, passed = judge(raw, rules)
    qa = {
        "checks": checks,
        "score": score,
        "thresholds": rules.thresholds.model_dump(),
        "qa_on": rules.qa_on.model_dump(),
        **extra,
    }
    return qa, passed


def scores(qa: dict[str, Any]) -> dict[str, Any]:
    """What ``model_call.qa_scores_json`` keeps: each check's value and verdict, the total."""
    return {
        "checks": {
            c["metric"]: {"value": c.get("value"), "ok": c.get("ok"), "off": c.get("off")}
            for c in qa.get("checks") or []
        },
        "score": qa.get("score"),
    }


# --------------------------------------------------------------------------- measuring


def tool_model(metric: str) -> str | None:
    try:
        return get_config().components.component(QA).tools.get(metric)
    except KeyError:
        return None


def _check(metric: str, **fields: Any) -> dict[str, Any]:
    return {"metric": metric, "value": None, "text": None, "model": None, **fields}


def _file(version: ProductVersion, role: str) -> dict[str, Any] | None:
    return next((f for f in version.files_json if f.get("role") == role), None)


def has_clip(version: ProductVersion) -> bool:
    return _file(version, "video") is not None


class Measure:
    """The tools run on one take (``run``)."""

    def __init__(
        self,
        services: Services,
        product: Product,
        version: ProductVersion,
        inputs: Inputs,
        ctx: CallContext,
        *,
        take_asks: Callable[[dict[str, Any]], dict[str, Any]],
        item: str | None,
    ) -> None:
        self.services = services
        self.product = product
        self.version = version
        self.context = inputs.context
        self.ctx = ctx
        self.take_asks = take_asks
        self.item = item
        self.mock_qa = dict((version.params_json or {}).get("mock_qa") or {})
        video = _file(version, "video")
        assert video is not None
        self.video = str(video["sha256"])
        self.sheet: str | None = None

    def _path(self, sha256: str) -> str:
        return str(self.services.store.path_for(sha256))

    async def run(self) -> list[dict[str, Any]]:
        return [
            await self.face(),
            await self.lipsync(),
            await self.asr(),
            await self.speaker(),
            await self.ocr(),
            await self.vlm(),
        ]

    async def _tool(
        self, metric: str, params: dict[str, Any], **meta: Any
    ) -> tuple[Any, str | None, str | None]:
        """(the tool's answer, its model, an error code)."""
        model = tool_model(metric)
        if model is None:
            return None, None, "no_tool"
        try:
            kind = self.services.registry.spec(model).kind
            req = ModelRequest(
                kind=kind,
                params={"video": self.video, "path": self._path(self.video), **params},
                meta={
                    "component": QA,
                    "task": metric,
                    "version": self.version.id,
                    "mock_qa": self.mock_qa,
                    **meta,
                },
            )
            routed = await self.services.router.call(QA, req, self.ctx, model=model, fallback=False)
        except ModelError as exc:
            logger.info("QA {} of {} not done: {}", metric, self.version.id, exc.code)
            return None, model, exc.code
        return routed, routed.model_key, None

    def _spoken(self) -> bool:
        return bool(self.context.get("dialogue")) and self.context.get("audio_mode") != "none"

    def _native(self) -> bool:
        return bool(self.context.get("dialogue")) and self.context.get("audio_mode") == "native"

    async def face(self) -> dict[str, Any]:
        refs = [
            {"asset_id": r.get("asset_id"), "name": r["name"], "path": self._path(r["sha256"])}
            for r in self.context.get("refs") or []
            if r.get("kind") == "character"
        ]
        if not refs:
            return _check("face", na=True)
        routed, model, error = await self._tool("face", {"refs": refs, "every_s": FACE_EVERY_S})
        if error:
            return _check("face", model=model, error=error)
        faces = [f for f in (routed.json or {}).get("faces") or [] if f.get("sim") is not None]
        if not faces:
            return _check("face", model=model, na=True, detail={"faces": []})
        value = round(min(float(f["sim"]) for f in faces), 4)
        return _check("face", value=value, model=model, detail={"faces": faces})

    async def lipsync(self) -> dict[str, Any]:
        if not self._spoken():
            return _check("lipsync", na=True)
        routed, model, error = await self._tool("lipsync", {})
        if error:
            return _check("lipsync", model=model, error=error)
        data = routed.json or {}
        here = data.get("in_sync")
        detail = {"offset": data.get("offset"), "conf": data.get("conf")}
        if here is None:
            return _check("lipsync", model=model, na=True, detail=detail)
        return _check("lipsync", value=round(float(here), 3), model=model, detail=detail)

    async def asr(self) -> dict[str, Any]:
        if self.context.get("audio_mode") != "native":  # dubbed or silent: nobody speaks in it
            return _check("asr", na=True)
        expected = "".join(str(d["text"]) for d in self.context.get("dialogue") or [])
        params: dict[str, Any] = {"lang": "zh"}
        names = await self._names()
        if names:
            params["prompt"] = f"人物：{'、'.join(names)}。"
        routed, model, error = await self._tool("asr", params, expect=expected)
        if error:
            return _check("asr", model=model, error=error)
        said = str(routed.text or "")
        if not expected and not _plain(said):  # no line, nothing heard
            return _check("asr", model=model, na=True, detail={"expected": ""})
        return _check(
            "asr", value=cer(said, expected), text=said, model=model, detail={"expected": expected}
        )

    async def _names(self) -> list[str]:
        """The series' characters, for the recogniser's hint."""
        async with self.services.db.session() as session:
            rows = await session.exec(
                select(Asset.name).where(
                    Asset.series_id == self.product.series_id, Asset.kind == "character"
                )
            )
            return sorted({str(n) for n in rows if n})

    async def speaker(self) -> dict[str, Any]:
        voices = [
            {"who": v["who"], "path": self._path(v["sha256"])}
            for v in self.context.get("voices") or []
        ]
        if not self._native() or not voices:
            return _check("speaker", na=True)
        routed, model, error = await self._tool("speaker", {"voices": voices})
        if error:
            return _check("speaker", model=model, error=error)
        sims = [s for s in (routed.json or {}).get("sims") or [] if s.get("sim") is not None]
        if not sims:
            return _check("speaker", model=model, na=True, detail={"sims": []})
        value = round(min(float(s["sim"]) for s in sims), 4)
        return _check("speaker", value=value, model=model, detail={"sims": sims})

    async def ocr(self) -> dict[str, Any]:
        expected = [
            str(t["exact"])
            for t in self.context.get("texts") or []
            if t.get("method") == "model" and t.get("exact")
        ]
        if not expected:
            return _check("ocr", na=True)
        routed, model, error = await self._tool("ocr", {"every_s": OCR_EVERY_S}, expect=expected)
        if error:
            return _check("ocr", model=model, error=error)
        frames = [
            {"t": f.get("t"), "text": str(f.get("text") or "")}
            for f in (routed.json or {}).get("frames") or []
        ]
        detail = {"expected": expected, "frames": frames}
        wants = [_plain(e) for e in expected]
        read = [f for f in frames if any(_like(_plain(f["text"]), w) for w in wants)]
        if not read:
            return _check("ocr", model=model, na=True, detail=detail)
        wrong = [f for f in read if not any(w in _plain(f["text"]) for w in wants)]
        text = wrong[0]["text"] if wrong else None
        return _check("ocr", text=text, model=model, match=not wrong, detail=detail)

    async def vlm(self) -> dict[str, Any]:
        payload = self.version.payload_json or {}
        items = takecheck.measured(payload)
        sheet = _file(self.version, "sheet")
        times = list(payload.get("sheet_times") or [])
        sha = str(sheet["sha256"]) if sheet else None
        if sha is None:
            data = self.services.store.path_for(self.video).read_bytes()
            try:
                png, times = await contact_sheet(data)
            except VideoError as exc:
                logger.warning("no contact sheet for QA ({})", exc.code)
            else:
                sha = self.sheet = self.services.store.put_bytes(png)
        model = None
        if sha is not None:
            asks = {**self.take_asks(self.context), "times": times}
            seen = await takecheck.look(self.services, sha, asks, self.item, self.ctx)
            if seen is not None:
                items, model = [*seen[0], *items], seen[1]
        fails = [x for x in items if not x["ok"]]
        return _check(
            "vlm",
            text=fails[0]["note"] or None if fails else None,
            model=model,
            match=not fails,
            items=items,
        )


# --------------------------------------------------------------------------- Mock


def _stable(req: ModelRequest, lo: float, hi: float) -> float:
    # By the take, not its clip: a Mock clip's bytes differ between FFmpeg builds.
    key = req.meta.get("version") or req.params.get("video", "")
    d = hashlib.sha256(str(key).encode()).digest()
    return round(lo + (hi - lo) * int.from_bytes(d[:4], "big") / 0xFFFFFFFF, 3)


def _given(req: ModelRequest, metric: str) -> Any:
    return (req.meta.get("mock_qa") or {}).get(metric)


def mock_face(req: ModelRequest) -> dict[str, Any]:
    sim = _given(req, "face")
    value = float(sim) if sim is not None else _stable(req, 0.8, 0.92)
    return {
        "faces": [
            {"asset_id": r.get("asset_id"), "name": r.get("name"), "sim": value}
            for r in req.params.get("refs") or []
        ]
    }


def mock_lipsync(req: ModelRequest) -> dict[str, Any]:
    given = _given(req, "lipsync")
    here = float(given) if given is not None else _stable(req, 2.0, 3.0)
    return {"in_sync": here, "conf": here, "offset": 0}


def mock_asr(req: ModelRequest) -> str:
    said = _given(req, "asr")
    return str(said) if said is not None else str(req.meta.get("expect") or "")


def mock_speaker(req: ModelRequest) -> dict[str, Any]:
    sim = _given(req, "speaker")
    value = float(sim) if sim is not None else _stable(req, 0.7, 0.85)
    return {"sims": [{"who": v.get("who"), "sim": value} for v in req.params.get("voices") or []]}


def mock_ocr(req: ModelRequest) -> dict[str, Any]:
    read = _given(req, "ocr")
    texts = [str(read)] if read is not None else list(req.meta.get("expect") or [])
    return {"frames": [{"t": float(i), "text": t} for i, t in enumerate(texts)]}


MOCKS: dict[str, Callable[[ModelRequest], Any]] = {
    "face": mock_face,
    "lipsync": mock_lipsync,
    "asr": mock_asr,
    "speaker": mock_speaker,
    "ocr": mock_ocr,
}


# --------------------------------------------------------------------------- the service


class QaService:
    def __init__(
        self,
        components: ComponentRegistry,
        products: ProductService,
        jobs: JobQueue,
        bus: EventBus,
    ) -> None:
        self.components = components
        self.services = components.services
        self.products = products
        self.jobs = jobs
        self.bus = bus
        # 不达标自动重跑和兜底 (step 4), told after each take's QA.
        self.policy: QaPolicy | None = None
        jobs.register(QA_JOB, self._handle)
        products.on_created(VIDEO_SLOT, self._take_made)
        for metric, responder in MOCKS.items():
            self.services.registry.add_mock_responder(QA, metric, responder)

    async def _take_made(self, product: Product, version: ProductVersion) -> None:
        if product.component_id == VIDEO_COMPONENT and has_clip(version):
            await self._enqueue(product, version)

    async def _enqueue(self, product: Product, version: ProductVersion) -> Job:
        async with self.services.db.session() as session:
            shot = await session.get(Shot, product.owner_id)
        return await self.jobs.enqueue(
            QA_JOB,
            QA_QUEUE,
            {"version_id": version.id},
            series_id=product.series_id,
            episode_id=shot.episode_id if shot is not None else None,
            product_id=product.id,
            component_id=QA,
            max_attempts=1,
        )

    async def request(self, version_id: str) -> Job:
        """「重新质检」: measure the take again."""
        async with self.services.db.session() as session:
            version = await session.get(ProductVersion, version_id)
            if version is None:
                raise PipelineError(404, "version_not_found", id=version_id)
            product = await session.get(Product, version.product_id)
        if product is None or product.component_id != VIDEO_COMPONENT or not has_clip(version):
            raise PipelineError(409, "qa_not_a_take", id=version_id)
        return await self._enqueue(product, version)

    async def _handle(self, jctx: JobContext) -> dict[str, Any]:
        job = jctx.job
        version_id = str(jctx.params["version_id"])
        comp = self.components.get(VIDEO_COMPONENT)
        async with self.services.db.session() as session:
            version = await session.get(ProductVersion, version_id)
            product = await session.get(Product, version.product_id) if version else None
            if version is None or product is None or comp is None:
                raise JobError("version_not_found", {"id": version_id})
            try:
                inputs = await comp.inputs(session, product)
            except (ComponentError, PipelineError) as exc:
                raise JobError(exc.code, dict(exc.params)) from exc
            rules = await load_rules(session, product.series_id)
        ctx = CallContext(
            component_id=QA,
            series_id=product.series_id,
            episode_id=inputs.episode_id,
            shot_id=product.owner_id,
            product_id=product.id,
            version_id=version.id,
            job_id=job.id,
            attempt=job.attempt,
        )
        measure = Measure(
            self.services,
            product,
            version,
            inputs,
            ctx,
            take_asks=take_asks,
            item=item_of(product),
        )
        raw = await measure.run()
        extra: dict[str, Any] = {"ran_at": utcnow().isoformat()}
        if measure.sheet is not None:
            extra["sheet"] = file_entry("sheet", measure.sheet, "image/png")
        qa, passed = result(raw, rules, **extra)
        await self._write(version.id, qa, passed)
        await self.bus.publish(
            EventType.VERSION_QA,
            {
                "product_id": product.id,
                "version_id": version.id,
                "qa_pass": passed,
                "score": qa["score"],
            },
        )
        await self.products.announce(product.id)
        if self.policy is not None:
            await self.policy.after_qa(product.id)
        return {"version_id": version.id, "qa_pass": passed, "score": qa["score"]}

    async def _write(self, version_id: str, qa: dict[str, Any], passed: bool | None) -> None:
        async with self.services.db.session() as session:
            version = await session.get(ProductVersion, version_id)
            if version is None:
                return
            version.qa_json = qa
            version.qa_pass = passed
            session.add(version)
            call_id = (version.params_json or {}).get("call_id")
            call = await session.get(ModelCall, int(call_id)) if call_id else None
            if call is not None:
                call.qa_scores_json = scores(qa)
                call.qa_pass = passed
                session.add(call)
            await session.commit()

    async def rejudge(self, series_id: str) -> int:
        """The series' measured takes held to its rules again (thresholds or switches changed);
        → how many."""
        async with self.services.db.session() as session:
            rules = await load_rules(session, series_id)
            rows = (
                await session.exec(
                    select(ProductVersion, Product)
                    .join(Product, col(Product.id) == col(ProductVersion.product_id))
                    .where(
                        Product.series_id == series_id,
                        Product.component_id == VIDEO_COMPONENT,
                        col(ProductVersion.qa_json).is_not(None),
                    )
                )
            ).all()
        touched: set[str] = set()
        for version, product in rows:
            old = dict(version.qa_json or {})
            raw = [
                {k: v for k, v in c.items() if k not in ("ok", "off", "threshold", "issue")}
                for c in old.get("checks") or []
            ]
            judged = ("checks", "score", "thresholds", "qa_on")
            keep = {k: v for k, v in old.items() if k not in judged}
            qa, passed = result(raw, rules, **keep)
            if qa != old or passed != version.qa_pass:
                await self._write(version.id, qa, passed)
                touched.add(product.id)
        for product_id in sorted(touched):
            await self.products.announce(product_id)
        return len(rows)

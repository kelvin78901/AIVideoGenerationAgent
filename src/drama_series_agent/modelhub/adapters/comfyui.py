"""Local pictures from the user's ComfyUI (plan M3 「ComfyUI 最小适配器」, SPEC 6.4.3).

One adapter per workflow folder (``workflows/<slug>/``, ``modelhub/workflows.py``):

- **Flow**: references → ``POST /upload/image`` (into ``input/dramastudio/``, named by sha256),
  the graph with its slots filled → ``POST /prompt``, ``GET /history/{id}`` every second until
  it is done (no WebSocket progress before M5), the output node's pictures → ``GET /view``.
  ``n`` pictures are n prompts, seeds ``seed``, ``seed + 1`` …
- **Stopping**: the router's local timeout (or a cancel) interrupts our prompt
  (``POST /interrupt`` with its id, so a run the user started in ComfyUI by hand is left alone)
  and takes it off the queue (``POST /queue {"delete": [id]}``). A prompt that vanishes from
  both the queue and the history (the user cleared the queue) fails with ``comfy_lost``.
- **VRAM lease**: each workflow holds the lease for its run; when another model (a TTS worker,
  another workflow) asks for it, ComfyUI is told to let go (``POST /free``).
- **Where**: the ComfyUI the last scan found (its port), and that scan's environment hash; the
  version records ``workflow_id``, ``workflow_sha256`` and ``comfy_env_hash`` (SPEC 6.4.5),
  passed back in ``ModelResult.raw["comfy"]``.
- **Sizes**: the workflow's ``caps.sizes`` for the frame's aspect (the sizes the model was
  trained at), else the frame scaled to ``caps.max_pixels`` in steps of 16.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import NotAnImage, image_info
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    OutputFile,
    Usage,
)
from drama_series_agent.modelhub.adapters.images import fit_size, load_refs
from drama_series_agent.modelhub.vram import VramLease, shared_lease
from drama_series_agent.modelhub.workflows import (
    Slot,
    Workflow,
    WorkflowError,
    load_workflow,
    shipped_workflow,
)

DEFAULT_URL = "http://127.0.0.1:8188"
UPLOAD_FOLDER = "dramastudio"
DEFAULT_MAX_PIXELS = 1_600_000
# Every this many polls, check the prompt is still queued or running.
QUEUE_CHECK_EVERY = 10
EXTS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@dataclass(frozen=True)
class ComfyTarget:
    url: str
    env_hash: str | None = None  # the scan's ``comfy_env`` hash (SPEC 6.4.5)


TargetGetter = Callable[[], Awaitable[ComfyTarget]]
Sleep = Callable[[float], Awaitable[None]]


def _not_running(exc: BaseException) -> ModelError:
    return ModelError("comfy_not_running", type(exc).__name__)


def prompt_error(body: Any) -> ModelError:
    """``/prompt`` refused the graph (HTTP 400): a model file or a node class it does not
    have, else something else wrong with the graph."""
    body = body if isinstance(body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    types = {str(error.get("type") or "")}
    details: list[str] = [str(error.get("message") or "")]
    for node in (body.get("node_errors") or {}).values():
        for e in (node or {}).get("errors") or []:
            types.add(str(e.get("type") or ""))
            details.append(f"{node.get('class_type')}: {e.get('details') or e.get('message')}")
    detail = " | ".join(d for d in details if d)[:500]
    if "missing_node_type" in types:
        return ModelError("comfy_node_missing", detail)
    if "value_not_in_list" in types:
        return ModelError("comfy_model_missing", detail)
    return ModelError("workflow_invalid", detail)


def run_error(status: dict[str, Any]) -> ModelError:
    """A prompt that ran and failed (``/history`` status ``error``)."""
    for message in status.get("messages") or []:
        if not isinstance(message, list) or len(message) != 2:
            continue
        kind, data = message
        data = data if isinstance(data, dict) else {}
        if kind == "execution_interrupted":
            return ModelError("comfy_interrupted", str(data.get("node_type") or ""))
        if kind == "execution_error":
            text = f"{data.get('exception_type')}: {data.get('exception_message')}"
            if "OutOfMemory" in str(data.get("exception_type")) or "out of memory" in text.lower():
                return ModelError("out_of_memory", text[:500])
            return ModelError("comfy_failed", f"{data.get('node_type')}: {text}"[:500])
    return ModelError("comfy_failed", "ComfyUI reported an error")


class ComfyUIAdapter:
    def __init__(
        self,
        spec: ModelSpec,
        *,
        target: TargetGetter,
        store: BlobStore,
        lease: VramLease | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        workflows_dir: Path | None = None,
        poll_s: float = 1.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.spec = spec
        self._target = target
        self._store = store
        self._lease = lease or shared_lease()
        self._transport = transport
        self._workflows_dir = workflows_dir
        self._poll_s = poll_s
        self._sleep = sleep
        self._client_id = uuid.uuid4().hex
        self._last_url = DEFAULT_URL
        self._lease.register(self._owner, self.free)

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def _owner(self) -> str:
        return f"comfy:{self.spec.workflow}"

    def workflow(self) -> Workflow:
        slug = self.spec.workflow
        if not slug:
            raise ModelError("workflow_invalid", f"{self.key}: no workflow in providers.yaml")
        try:
            if self._workflows_dir is None:
                return shipped_workflow(slug)
            return load_workflow(slug, self._workflows_dir)
        except (WorkflowError, ValueError) as exc:
            raise ModelError("workflow_invalid", str(exc)) from exc

    # ------------------------------------------------------------------ protocol

    def estimate(self, req: ModelRequest) -> Estimate:
        n = max(1, int(req.params.get("n") or 1))
        per = float(self._caps().get("est_seconds") or 30)
        return Estimate(cost_usd=0.0, seconds=n * per)

    async def health(self) -> Health:
        """ComfyUI answers and has every model file the workflow's loaders name."""
        try:
            wf = self.workflow()
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        target = await self._target()
        try:
            async with self._client(target.url, timeout=10) as client:
                if not (await client.get("/system_stats")).is_success:
                    return Health(ok=False, detail="comfy_not_running")
                for folder in sorted({m.folder for m in wf.meta.models}):
                    res = await client.get(f"/models/{folder}")
                    names = res.json() if res.is_success else []
                    have = {str(n).replace("\\", "/") for n in names or []}
                    if any(m.name not in have for m in wf.meta.models if m.folder == folder):
                        return Health(ok=False, detail="comfy_model_missing")
        except (httpx.HTTPError, ValueError):
            return Health(ok=False, detail="comfy_not_running")
        return Health(ok=True, models=[self.key])

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        wf = self.workflow()
        target = await self._target()
        self._last_url = target.url
        n = max(1, int(req.params.get("n") or 1))
        width, height = self.size_for(wf, req)
        seed = req.seed if req.seed is not None else random.randrange(2**31)
        files: list[OutputFile] = []
        async with self._lease.hold(self._owner), self._client(target.url) as client:
            refs = await self._upload_refs(client, wf, req)
            for i in range(n):
                values: dict[Slot, Any] = {
                    "prompt": req.prompt or "",
                    "width": width,
                    "height": height,
                    "seed": seed + i,
                }
                if req.params.get("negative"):
                    values["negative"] = str(req.params["negative"])
                filled = {k: v for k, v in values.items() if wf.has(k)}
                try:
                    graph = wf.fill(filled, refs)
                except WorkflowError as exc:
                    raise ModelError("ref_missing", str(exc)) from exc
                files += await self._one(client, target.url, wf, graph)
        raw = {
            "comfy": {
                "workflow_id": wf.slug,
                "workflow_sha256": wf.sha256,
                "comfy_env_hash": target.env_hash,
            },
            "seeds": [seed + i for i in range(n)],
            "size": [width, height],
        }
        return ModelResult(files=files, usage=Usage(images=len(files)), raw=raw)

    async def free(self) -> None:
        """Let go of the GPU (the VRAM lease asks): ComfyUI unloads its models."""
        async with self._client(self._last_url, timeout=30) as client:
            res = await client.post("/free", json={"unload_models": True, "free_memory": True})
            res.raise_for_status()

    # ------------------------------------------------------------------ internals

    def _caps(self) -> dict[str, Any]:
        try:
            return self.workflow().meta.caps
        except ModelError:
            return {}

    def size_for(self, wf: Workflow, req: ModelRequest) -> tuple[int, int]:
        sizes = wf.meta.caps.get("sizes") or {}
        fixed = sizes.get(str(req.params.get("aspect") or ""))
        if fixed:
            return int(fixed[0]), int(fixed[1])
        w = int(req.params.get("width") or 1080)
        h = int(req.params.get("height") or 1920)
        max_pixels = int(wf.meta.caps.get("max_pixels") or DEFAULT_MAX_PIXELS)
        return fit_size(w, h, multiple=16, min_pixels=max_pixels // 2, max_pixels=max_pixels)

    def _client(self, url: str, timeout: float = 60) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=url.rstrip("/"), timeout=timeout, trust_env=False, transport=self._transport
        )

    async def _upload_refs(
        self, client: httpx.AsyncClient, wf: Workflow, req: ModelRequest
    ) -> list[str]:
        slots = len(wf.bindings("ref_image"))
        shas = list(req.params.get("refs") or [])[:slots]
        names: list[str] = []
        for sha, (data, mime) in zip(shas, load_refs(self._store, shas, slots), strict=True):
            name = f"{sha}.{EXTS.get(mime, 'png')}"
            try:
                res = await client.post(
                    "/upload/image",
                    files={"image": (name, data, mime)},
                    data={"subfolder": UPLOAD_FOLDER, "type": "input", "overwrite": "true"},
                )
            except httpx.HTTPError as exc:
                raise _not_running(exc) from exc
            if not res.is_success:
                raise ModelError("comfy_failed", f"upload: {res.status_code} {res.text[:200]}")
            body = res.json()
            sub = str(body.get("subfolder") or "")
            names.append(f"{sub}/{body['name']}" if sub else str(body["name"]))
        return names

    async def _one(
        self, client: httpx.AsyncClient, url: str, wf: Workflow, graph: dict[str, Any]
    ) -> list[OutputFile]:
        prompt_id = await self._submit(client, graph)
        try:
            entry = await self._wait(client, prompt_id)
        except asyncio.CancelledError:
            await asyncio.shield(self._stop(url, prompt_id))
            raise
        return await self._fetch(client, wf, entry)

    async def _submit(self, client: httpx.AsyncClient, graph: dict[str, Any]) -> str:
        try:
            res = await client.post("/prompt", json={"prompt": graph, "client_id": self._client_id})
        except httpx.HTTPError as exc:
            raise _not_running(exc) from exc
        try:
            body = res.json()
        except ValueError:
            body = {}
        if res.status_code == 400:
            raise prompt_error(body)
        if not res.is_success or not body.get("prompt_id"):
            raise ModelError("comfy_failed", f"/prompt: {res.status_code} {res.text[:200]}")
        return str(body["prompt_id"])

    async def _wait(self, client: httpx.AsyncClient, prompt_id: str) -> dict[str, Any]:
        polls = 0
        while True:
            entry = await self._history(client, prompt_id)
            if entry is not None:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    raise run_error(status)
                if status.get("completed") or (entry.get("outputs") and not status):
                    return entry
            polls += 1
            if (
                polls % QUEUE_CHECK_EVERY == 0
                and not await self._queued(client, prompt_id)
                and await self._history(client, prompt_id) is None
            ):
                raise ModelError("comfy_lost", f"prompt {prompt_id} left the queue")
            await self._sleep(self._poll_s)

    async def _history(self, client: httpx.AsyncClient, prompt_id: str) -> dict[str, Any] | None:
        try:
            res = await client.get(f"/history/{prompt_id}")
        except httpx.HTTPError as exc:
            raise _not_running(exc) from exc
        if not res.is_success:
            return None
        entry = (res.json() or {}).get(prompt_id)
        return entry if isinstance(entry, dict) else None

    async def _queued(self, client: httpx.AsyncClient, prompt_id: str) -> bool:
        try:
            res = await client.get("/queue")
            body = res.json() if res.is_success else {}
        except (httpx.HTTPError, ValueError):
            return True  # cannot tell; keep waiting
        for key in ("queue_running", "queue_pending"):
            for item in body.get(key) or []:
                if isinstance(item, list) and len(item) > 1 and item[1] == prompt_id:
                    return True
        return False

    async def _fetch(
        self, client: httpx.AsyncClient, wf: Workflow, entry: dict[str, Any]
    ) -> list[OutputFile]:
        outputs = entry.get("outputs") or {}
        files: list[OutputFile] = []
        for node_id in wf.output_nodes("image_out"):
            for img in (outputs.get(node_id) or {}).get("images") or []:
                params = {
                    "filename": str(img.get("filename") or ""),
                    "subfolder": str(img.get("subfolder") or ""),
                    "type": str(img.get("type") or "output"),
                }
                try:
                    res = await client.get("/view", params=params)
                except httpx.HTTPError as exc:
                    raise _not_running(exc) from exc
                if not res.is_success:
                    raise ModelError("comfy_failed", f"/view: {res.status_code}")
                try:
                    info = image_info(res.content)
                except NotAnImage as exc:
                    raise ModelError("invalid_response", str(exc)) from exc
                files.append(
                    OutputFile(role="image", mime=info.mime, data=res.content, w=info.w, h=info.h)
                )
        if not files:
            raise ModelError("no_image", f"{wf.slug}: no picture from its output node")
        return files

    async def _stop(self, url: str, prompt_id: str) -> None:
        """Interrupt our prompt if it is running and take it off the queue."""
        try:
            async with self._client(url, timeout=10) as client:
                await client.post("/interrupt", json={"prompt_id": prompt_id})
                await client.post("/queue", json={"delete": [prompt_id]})
        except httpx.HTTPError as exc:
            logger.warning("comfy: could not stop prompt {}: {}", prompt_id, exc)

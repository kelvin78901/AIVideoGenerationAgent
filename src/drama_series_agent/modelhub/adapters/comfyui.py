"""Local pictures and videos from the user's ComfyUI (SPEC 6.4.1 / 6.4.3; M3 pictures, M5 video).

One adapter per workflow folder (``workflows/<slug>/``, ``modelhub/workflows.py``):

- **Flow**: the input files (references, first frame, input video, dialogue audio: sha256s in
  the blob store, ``params["refs"]`` / ``["first_frame"]`` / ``["video_in"]`` /
  ``["dialogue_audio"]``) → ``POST /upload/image`` (into ``input/dramastudio/``, named by
  sha256; ComfyUI takes any file there), the graph with its slots filled → ``POST /prompt``,
  wait, the output nodes' files → ``GET /view``. ``n`` takes are n prompts, seeds ``seed``,
  ``seed + 1`` …
- **Waiting**: progress comes over ``/ws?clientId=`` (``progress`` → ``CallContext.on_progress``;
  ``executing`` with no node, or ``execution_*``: look in the history now). ``/history/{id}``
  is read every ``poll_s`` without a socket and every ``WS_POLL_EVERY`` × that with one; a
  socket that cannot be opened or drops leaves the polling.
- **Video**: ``seconds`` is the shot's length (``params["duration_s"]``) clamped into
  ``caps.duration_s``; ``fps`` is ``caps.fps`` (the model's own rate) else the frame's. A video
  that comes back is probed: unreadable is ``invalid_response``, much shorter than asked
  ``video_too_short``, another aspect ``video_wrong_size``. A trial run (``params["trial"]``)
  makes up the input files the workflow needs and was not given.
- **Stopping**: the router's local timeout (or a cancel) interrupts our prompt
  (``POST /interrupt`` with its id, so a run the user started in ComfyUI by hand is left alone)
  and takes it off the queue (``POST /queue {"delete": [id]}``). A prompt that vanishes from
  both the queue and the history (the user cleared the queue) fails with ``comfy_lost``.
- **VRAM lease**: each workflow holds the lease for its run; when another model (a TTS worker,
  a workflow on other weights) asks for it, ComfyUI is told to let go (``POST /free``).
  Workflows on the same weights (FLUX 3 Klein's edit and text-to-image) share one owner: freeing
  between them only reads the same 20 GB again, and that reread is where ComfyUI failed with
  ``hostbuf_file_reader_read failed`` (M4 keyframe bake-off).
- **Where**: the ComfyUI the last scan found (its port), and that scan's environment hash; the
  version records ``workflow_id``, ``workflow_sha256`` and ``comfy_env_hash`` (SPEC 6.4.5),
  passed back in ``ModelResult.raw["comfy"]``.
- **Sizes**: the workflow's ``caps.sizes`` for the frame's aspect (the sizes the model was
  trained at), else the frame scaled to ``caps.max_pixels`` in steps of ``caps.multiple`` (16).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import uuid
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import NotAnImage, image_info
from drama_series_agent.media.video import VideoError, probe
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
from drama_series_agent.modelhub.adapters.mock import mock_picture, sine_wav, solid_mp4
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
# With a progress socket, the history is read this many times less often.
WS_POLL_EVERY = 5
EXTS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
# The input files besides references: slot → what it holds.
INPUT_FILES: tuple[tuple[Slot, str], ...] = (
    ("first_frame", "image"),
    ("video_in", "video"),
    ("dialogue_audio", "audio"),
)
FILE_EXTS = {
    "image": EXTS,
    "video": {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"},
    "audio": {"audio/wav": "wav", "audio/mpeg": "mp3", "audio/flac": "flac"},
}
MEDIA_TYPES = {
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "mkv": "video/x-matroska",
    "wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac", "opus": "audio/ogg",
    "ogg": "audio/ogg",
}  # fmt: skip
OUTPUTS: tuple[tuple[Slot, str], ...] = (
    ("image_out", "image"),
    ("video_out", "video"),
    ("audio_out", "audio"),
)
# Where an output node lists its files (SaveVideo: ``images``; VideoHelperSuite: ``gifs``).
OUTPUT_KEYS = ("images", "gifs", "videos", "video", "audio")
# A take may be this much shorter than asked (H3 snaps to 17k + 5 frames, rounding up).
SHORT_BY_S = 0.5


@dataclass(frozen=True)
class ComfyTarget:
    url: str
    env_hash: str | None = None  # the scan's ``comfy_env`` hash (SPEC 6.4.5)


TargetGetter = Callable[[], Awaitable[ComfyTarget]]
Sleep = Callable[[float], Awaitable[None]]
# Opens ComfyUI's ``/ws``: its messages, text (JSON) or binary (previews).
WsConnect = Callable[[str], AbstractAsyncContextManager[AsyncIterable[str | bytes]]]
ProgressFn = Callable[[int, int], Awaitable[None]]


@contextlib.asynccontextmanager
async def ws_connect(url: str) -> AsyncIterator[AsyncIterable[str | bytes]]:
    from websockets.asyncio.client import connect

    async with connect(url, max_size=None, open_timeout=5, proxy=None) as conn:
        yield conn


@dataclass
class ProgressSocket:
    """One run's ``/ws``: forwards ``progress`` for the prompts being watched and marks prompts
    done. ``alive`` turns false when the socket drops (the waiters go back to polling)."""

    messages: AsyncIterable[str | bytes]
    alive: bool = True
    _done: dict[str, asyncio.Event] = field(default_factory=dict)
    _watch: dict[str, ProgressFn] = field(default_factory=dict)

    def watch(self, prompt_id: str, on_progress: ProgressFn) -> asyncio.Event:
        self._watch[prompt_id] = on_progress
        done = self._done.setdefault(prompt_id, asyncio.Event())
        if not self.alive:
            done.set()
        return done

    async def read(self) -> None:
        try:
            async for raw in self.messages:
                if isinstance(raw, str):
                    await self._message(raw)
        except Exception as exc:  # any socket error means: poll instead
            logger.info("comfy: progress socket closed: {}", exc)
        finally:
            self.alive = False
            for event in self._done.values():
                event.set()

    async def _message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if not isinstance(msg, dict) or not isinstance(msg.get("data"), dict):
            return
        kind, data = msg.get("type"), msg["data"]
        if not data.get("prompt_id"):
            return
        pid = str(data["prompt_id"])
        if kind == "progress":
            callback = self._watch.get(pid)
            if callback is not None:
                try:
                    await callback(int(data.get("value") or 0), int(data.get("max") or 0))
                except Exception as exc:  # progress is best effort
                    logger.warning("comfy: progress callback failed: {}", exc)
        elif (kind == "executing" and data.get("node") is None) or kind in (
            "execution_success",
            "execution_error",
            "execution_interrupted",
        ):
            self._done.setdefault(pid, asyncio.Event()).set()


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
        websocket: WsConnect | None = ws_connect,
    ) -> None:
        self.spec = spec
        self._target = target
        self._store = store
        self._lease = lease or shared_lease()
        self._transport = transport
        self._workflows_dir = workflows_dir
        self._poll_s = poll_s
        self._sleep = sleep
        self._websocket = websocket
        self._client_id = uuid.uuid4().hex
        self._last_url = DEFAULT_URL
        self._lease.register(self._owner, self.free)

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def _owner(self) -> str:
        """The lease owner: the weights the workflow loads (its slug when it names none)."""
        try:
            files = sorted(f"{m.folder}/{m.name}" for m in self.workflow().meta.models)
        except ModelError:
            files = []
        return "comfy:" + ("+".join(files) if files else str(self.spec.workflow))

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
        caps = self._caps()
        if caps.get("est_seconds_per_s"):
            per = float(caps["est_seconds_per_s"]) * seconds_for(caps, req)
        else:
            per = float(caps.get("est_seconds") or 30)
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
        seconds = seconds_for(wf.meta.caps, req)
        fps = float(wf.meta.caps.get("fps") or req.params.get("fps") or 24)
        seed = req.seed if req.seed is not None else random.randrange(2**31)
        files: list[OutputFile] = []
        async with (
            self._lease.hold(self._owner),
            self._client(target.url) as client,
            self._socket(target.url) as socket,
        ):
            refs = await self._upload_refs(client, wf, req)
            inputs = await self._upload_inputs(client, wf, req, (width, height), seconds)
            for i in range(n):
                values: dict[Slot, Any] = {
                    "prompt": req.prompt or "",
                    "width": width,
                    "height": height,
                    "seed": seed + i,
                    "seconds": seconds,
                    "fps": fps,
                    **inputs,
                }
                if req.params.get("negative"):
                    values["negative"] = str(req.params["negative"])
                filled = {k: v for k, v in values.items() if wf.has(k)}
                try:
                    graph = wf.fill(filled, refs, req.params.get("branches"))
                except WorkflowError as exc:
                    raise ModelError("ref_missing", str(exc)) from exc
                progress = _take_progress(ctx, i, n)
                await progress(0, 0)
                take = await self._one(client, socket, target.url, wf, graph, progress)
                files += await self._checked(wf, take, (width, height), seconds)
        raw: dict[str, Any] = {
            "comfy": {
                "workflow_id": wf.slug,
                "workflow_sha256": wf.sha256,
                "comfy_env_hash": target.env_hash,
            },
            "seeds": [seed + i for i in range(n)],
            "size": [width, height],
        }
        videos = [f for f in files if f.role == "video"]
        if videos:
            raw["seconds"] = seconds
            usage = Usage(output_seconds=round(sum(f.duration_s or 0 for f in videos), 3))
        else:
            usage = Usage(images=len(files))
        return ModelResult(files=files, usage=usage, raw=raw)

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
        multiple = int(wf.meta.caps.get("multiple") or 16)
        return fit_size(w, h, multiple=multiple, min_pixels=max_pixels // 2, max_pixels=max_pixels)

    def _client(self, url: str, timeout: float = 60) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=url.rstrip("/"), timeout=timeout, trust_env=False, transport=self._transport
        )

    @contextlib.asynccontextmanager
    async def _socket(self, url: str) -> AsyncIterator[ProgressSocket | None]:
        """ComfyUI's progress socket for this run; None when it cannot be opened."""
        if self._websocket is None:
            yield None
            return
        ws_url = url.rstrip("/").replace("http", "ws", 1) + f"/ws?clientId={self._client_id}"
        opened = self._websocket(ws_url)
        try:
            messages = await opened.__aenter__()
        except Exception as exc:  # no socket: poll the history instead
            logger.info("comfy: no progress socket ({}), polling", exc)
            yield None
            return
        socket = ProgressSocket(messages)
        reader = asyncio.create_task(socket.read())
        try:
            yield socket
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
            with contextlib.suppress(Exception):
                await opened.__aexit__(None, None, None)

    async def _upload(self, client: httpx.AsyncClient, name: str, data: bytes, mime: str) -> str:
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
        return f"{sub}/{body['name']}" if sub else str(body["name"])

    async def _upload_refs(
        self, client: httpx.AsyncClient, wf: Workflow, req: ModelRequest
    ) -> list[str]:
        slots = len(wf.bindings("ref_image"))
        shas = list(req.params.get("refs") or [])[:slots]
        names: list[str] = []
        for sha, (data, mime) in zip(shas, load_refs(self._store, shas, slots), strict=True):
            names.append(await self._upload(client, f"{sha}.{EXTS.get(mime, 'png')}", data, mime))
        if not names and req.params.get("trial") and wf.needs_refs():
            w, h = self.size_for(wf, req)
            sample = mock_picture(w, h, "trial", wf.slug)
            names.append(await self._upload(client, "trial-ref.png", sample, "image/png"))
        return names

    async def _upload_inputs(
        self,
        client: httpx.AsyncClient,
        wf: Workflow,
        req: ModelRequest,
        size: tuple[int, int],
        seconds: float,
    ) -> dict[Slot, Any]:
        """The first frame, input video, dialogue audio and voice samples (``ref_audio``, a
        list) the workflow takes, uploaded."""
        names: dict[Slot, Any] = {}
        for slot, kind in INPUT_FILES:
            bound = wf.bindings(slot)
            if not bound:
                continue
            sha = req.params.get(slot)
            if sha:
                names[slot] = await self._upload_blob(client, slot, str(sha), kind)
            elif req.params.get("trial") and not all(b.optional for b in bound):
                data, mime, name = await _sample(kind, size, seconds)
                names[slot] = await self._upload(client, name, data, mime)
        voices = list(req.params.get("ref_audio") or [])[: len(wf.bindings("ref_audio"))]
        if voices:
            names["ref_audio"] = [
                await self._upload_blob(client, "ref_audio", str(sha), "audio") for sha in voices
            ]
        return names

    async def _upload_blob(self, client: httpx.AsyncClient, slot: str, sha: str, kind: str) -> str:
        path = self._store.path_for(sha)
        if not path.is_file():
            raise ModelError("ref_missing", f"{slot}: {sha} is not in the store")
        data = path.read_bytes()
        mime = _sniff(data, kind)
        return await self._upload(client, f"{sha}.{FILE_EXTS[kind].get(mime, 'bin')}", data, mime)

    async def _one(
        self,
        client: httpx.AsyncClient,
        socket: ProgressSocket | None,
        url: str,
        wf: Workflow,
        graph: dict[str, Any],
        progress: ProgressFn,
    ) -> list[OutputFile]:
        prompt_id = await self._submit(client, graph)
        done = socket.watch(prompt_id, progress) if socket is not None else None
        try:
            entry = await self._wait(client, prompt_id, socket, done)
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

    async def _wait(
        self,
        client: httpx.AsyncClient,
        prompt_id: str,
        socket: ProgressSocket | None = None,
        done: asyncio.Event | None = None,
    ) -> dict[str, Any]:
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
            await self._pause(socket, done)

    async def _pause(self, socket: ProgressSocket | None, done: asyncio.Event | None) -> None:
        """Until the next history read: the poll interval; with a live socket, until it says
        the prompt is done (at most ``WS_POLL_EVERY`` intervals). Once it has said so, the
        history may still be a moment behind: plain intervals again."""
        if socket is None or done is None or not socket.alive or done.is_set():
            await self._sleep(self._poll_s)
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(done.wait(), self._poll_s * WS_POLL_EVERY)

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
        """The output nodes' files: pictures (``image_out``), videos (``video_out``), audio
        (``audio_out``)."""
        outputs = entry.get("outputs") or {}
        files: list[OutputFile] = []
        for slot, role in OUTPUTS:
            for node_id in wf.output_nodes(slot):
                node_out = outputs.get(node_id) or {}
                for key in OUTPUT_KEYS:
                    for item in node_out.get(key) or []:
                        if isinstance(item, dict) and item.get("filename"):
                            files.append(await self._view(client, item, role))
        if wf.has("video_out") and not any(f.role == "video" for f in files):
            raise ModelError("no_video", f"{wf.slug}: no video from its output node")
        if wf.has("image_out") and not any(f.role == "image" for f in files):
            raise ModelError("no_image", f"{wf.slug}: no picture from its output node")
        return files

    async def _view(self, client: httpx.AsyncClient, item: dict[str, Any], role: str) -> OutputFile:
        filename = str(item.get("filename") or "")
        params = {
            "filename": filename,
            "subfolder": str(item.get("subfolder") or ""),
            "type": str(item.get("type") or "output"),
        }
        try:
            res = await client.get("/view", params=params, timeout=600)
        except httpx.HTTPError as exc:
            raise _not_running(exc) from exc
        if not res.is_success:
            raise ModelError("comfy_failed", f"/view: {res.status_code}")
        if role == "image":
            try:
                info = image_info(res.content)
            except NotAnImage as exc:
                raise ModelError("invalid_response", str(exc)) from exc
            return OutputFile(role="image", mime=info.mime, data=res.content, w=info.w, h=info.h)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        fallback = "video/mp4" if role == "video" else "audio/wav"
        return OutputFile(role=role, mime=MEDIA_TYPES.get(ext, fallback), data=res.content)

    async def _checked(
        self, wf: Workflow, files: list[OutputFile], size: tuple[int, int], seconds: float
    ) -> list[OutputFile]:
        """Videos probed (size, length) and held against what was asked."""
        for f in files:
            if f.role != "video" or f.data is None:
                continue
            try:
                info = await probe(f.data)
            except VideoError as exc:
                raise ModelError("invalid_response", f"{wf.slug}: {exc}") from exc
            f.w, f.h, f.duration_s = info.w, info.h, round(info.duration_s, 3)
            if wf.has("seconds") and info.duration_s < seconds - SHORT_BY_S:
                raise ModelError(
                    "video_too_short", f"{wf.slug}: {info.duration_s:.2f}s, asked {seconds}s"
                )
            w, h = size
            if abs(info.w / info.h - w / h) > 0.02 * (w / h):
                raise ModelError("video_wrong_size", f"{wf.slug}: {info.w}x{info.h}, asked {w}x{h}")
        return files

    async def _stop(self, url: str, prompt_id: str) -> None:
        """Interrupt our prompt if it is running and take it off the queue."""
        try:
            async with self._client(url, timeout=10) as client:
                await client.post("/interrupt", json={"prompt_id": prompt_id})
                await client.post("/queue", json={"delete": [prompt_id]})
        except httpx.HTTPError as exc:
            logger.warning("comfy: could not stop prompt {}: {}", prompt_id, exc)


def seconds_for(caps: dict[str, Any], req: ModelRequest) -> float:
    """The shot's length, into the range the model makes (``caps.duration_s``)."""
    span = caps.get("duration_s") or []
    lo, hi = (float(span[0]), float(span[-1])) if span else (0.0, float("inf"))
    asked = req.params.get("duration_s")
    return min(max(float(asked) if asked is not None else lo, lo), hi)


def _take_progress(ctx: CallContext, take: int, takes: int) -> ProgressFn:
    """The sampler steps of take ``take`` (from 0) as the call's progress."""

    async def report(step: int, steps: int) -> None:
        if ctx.on_progress is None:
            return
        part = step / steps if steps else 0.0
        await ctx.on_progress(
            {
                "take": take + 1,
                "takes": takes,
                "step": step,
                "steps": steps,
                "pct": round((take + part) / takes, 3),
            }
        )

    return report


def _sniff(data: bytes, kind: str) -> str:
    """An input file's media type from its first bytes."""
    if kind == "image":
        try:
            return image_info(data).mime
        except NotAnImage:
            return "image/png"
    if kind == "audio":
        if data[:4] == b"RIFF":
            return "audio/wav"
        return "audio/flac" if data[:4] == b"fLaC" else "audio/mpeg"
    if data[4:8] == b"ftyp":
        return "video/quicktime" if data[8:10] == b"qt" else "video/mp4"
    return "video/webm" if data[:4] == b"\x1aE\xdf\xa3" else "video/mp4"


async def _sample(kind: str, size: tuple[int, int], seconds: float) -> tuple[bytes, str, str]:
    """A made-up input for a trial run: a picture, a clip or a tone of the right size."""
    w, h = size
    if kind == "image":
        return mock_picture(w, h, "trial"), "image/png", "trial-frame.png"
    if kind == "audio":
        return sine_wav(min(seconds, 5.0)), "audio/wav", "trial-audio.wav"
    clip = await solid_mp4(w, h, max(seconds, 1.0), 24, "556677")
    return clip, "video/mp4", "trial-video.mp4"

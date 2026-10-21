"""The ComfyUI adapter against a fake ComfyUI (httpx MockTransport): upload, prompt, history,
view; interrupts on timeout; the VRAM lease's /free; the shipped workflows' bindings."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    ModelError,
    ModelRequest,
    ModelSpec,
)
from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget, ComfyUIAdapter
from drama_series_agent.modelhub.adapters.mock import solid_png
from drama_series_agent.modelhub.vram import VramLease
from drama_series_agent.modelhub.workflows import WorkflowError, load_workflow, shipped_workflow

URL = "http://127.0.0.1:8188"

GRAPH: dict[str, Any] = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["9", 0]},
          "_meta": {"title": "Prompt"}},
    "3": {"class_type": "EmptySD3LatentImage",
          "inputs": {"width": 1024, "height": 1024, "batch_size": 1}, "_meta": {"title": "Size"}},
    "4": {"class_type": "KSampler", "inputs": {"seed": 0, "model": ["1", 0]},
          "_meta": {"title": "Sampler"}},
    "5": {"class_type": "LoadImage", "inputs": {"image": "x.png"},
          "_meta": {"title": "Reference 1"}},
    "6": {"class_type": "LoadImage", "inputs": {"image": "x.png"},
          "_meta": {"title": "Reference 2"}},
    "7": {"class_type": "TextEncodeEdit",
          "inputs": {"prompt": "", "image1": ["5", 0], "image2": ["6", 0]}},
    "8": {"class_type": "PreviewImage", "inputs": {"images": ["4", 0]},
          "_meta": {"title": "Output"}},
}  # fmt: skip

META = """
kind: image
bindings:
  - { slot: prompt, node: Prompt, field: text }
  - { slot: width, node: Size, field: width }
  - { slot: height, node: Size, field: height }
  - { slot: seed, node: Sampler, field: seed }
  - { slot: ref_image, index: 1, node: Reference 1, field: image }
  - { slot: ref_image, index: 2, node: Reference 2, field: image, optional: true }
  - { slot: image_out, node: Output }
models:
  - { folder: diffusion_models, name: m.safetensors }
caps:
  sizes: { "9:16": [928, 1664] }
"""


class FakeComfy:
    """Enough of ComfyUI's HTTP API. ``polls``: /history answers empty this many times first;
    ``hang``: never finishes; ``refuse``: /prompt answers 400 with this body; ``fail``: the run
    ends with this status; ``lost``: the prompt is neither queued nor in the history."""

    def __init__(self) -> None:
        self.polls = 0
        self.hang = False
        self.lost = False
        self.refuse: dict[str, Any] | None = None
        self.fail: dict[str, Any] | None = None
        self.models: dict[str, list[str]] = {"diffusion_models": ["m.safetensors"]}
        self.prompts: list[dict[str, Any]] = []
        self.uploads: list[tuple[str, str]] = []  # (subfolder, filename)
        self.calls: list[tuple[str, str, Any]] = []
        self._seen: dict[str, int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = (
            json.loads(request.content)
            if request.headers.get("content-type") == ("application/json")
            else None
        )
        self.calls.append((method, path, body))
        if path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.42.1"}})
        if path.startswith("/models/"):
            return httpx.Response(200, json=self.models.get(path.split("/")[-1], []))
        if path == "/upload/image":
            text = request.content.decode("latin-1")
            name = text.split('filename="', 1)[1].split('"', 1)[0]
            self.uploads.append(("dramastudio", name))
            return httpx.Response(200, json={"name": name, "subfolder": "dramastudio",
                                             "type": "input"})  # fmt: skip
        if path == "/prompt":
            if self.refuse is not None:
                return httpx.Response(400, json=self.refuse)
            assert body is not None
            self.prompts.append(body["prompt"])
            return httpx.Response(200, json={"prompt_id": f"p{len(self.prompts)}", "number": 1})
        if path.startswith("/history/"):
            pid = path.rsplit("/", 1)[1]
            seen = self._seen[pid] = self._seen.get(pid, 0) + 1
            if self.hang or self.lost or seen <= self.polls:
                return httpx.Response(200, json={})
            if self.fail is not None:
                return httpx.Response(200, json={pid: {"outputs": {}, "status": self.fail}})
            out = {"images": [{"filename": f"{pid}.png", "subfolder": "", "type": "temp"}]}
            status = {"status_str": "success", "completed": True, "messages": []}
            return httpx.Response(200, json={pid: {"outputs": {"8": out}, "status": status}})
        if path == "/queue" and method == "GET":
            running = [] if self.lost else [[1, f"p{len(self.prompts)}", {}, {}, []]]
            return httpx.Response(200, json={"queue_running": running, "queue_pending": []})
        if path == "/view":
            return httpx.Response(200, content=solid_png(928, 1664, (10, 20, 30)))
        if path in ("/interrupt", "/queue", "/free"):
            return httpx.Response(200)
        return httpx.Response(404)

    def posted(self, path: str) -> list[Any]:
        return [b for m, p, b in self.calls if m == "POST" and p == path]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "workflows" / "fake-edit"
    folder.mkdir(parents=True)
    (folder / "workflow.api.json").write_text(json.dumps(GRAPH), encoding="utf-8")
    (folder / "workflow.yaml").write_text(META, encoding="utf-8")
    return tmp_path / "workflows"


@pytest.fixture
def store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


SPEC = ModelSpec(
    key="comfy/fake-edit", kind="image", where="local", display="Fake", runtime="comfyui",
    workflow="fake-edit",
)  # fmt: skip


def _adapter(
    fake: FakeComfy,
    root: Path,
    store: BlobStore,
    lease: VramLease | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ComfyUIAdapter:
    async def target() -> ComfyTarget:
        return ComfyTarget(url=URL, env_hash="env123")

    async def no_sleep(_s: float) -> None:
        await asyncio.sleep(0)

    return ComfyUIAdapter(
        SPEC,
        target=target,
        store=store,
        lease=lease or VramLease(),
        transport=transport or httpx.MockTransport(fake.handler),
        workflows_dir=root,
        sleep=no_sleep,
    )


def _req(store: BlobStore, n: int = 1, refs: int = 1, seed: int | None = 7) -> ModelRequest:
    shas = [store.put_bytes(solid_png(64, 64, (i, 0, 0))) for i in range(refs)]
    params: dict[str, Any] = {"n": n, "width": 1080, "height": 1920, "aspect": "9:16"}
    if shas:
        params["refs"] = shas
    return ModelRequest(kind="image", prompt="雨夜的便利店门口", seed=seed, params=params)


# --------------------------------------------------------------------------- workflows


def test_bindings_must_point_at_one_node_and_a_real_input(root: Path) -> None:
    wf = load_workflow("fake-edit", root)
    assert wf.node_id("Size") == "3" and len(wf.sha256) == 64
    twice = {**GRAPH, "9": {"class_type": "X", "inputs": {}, "_meta": {"title": "Prompt"}}}
    (root / "fake-edit" / "workflow.api.json").write_text(json.dumps(twice), encoding="utf-8")
    with pytest.raises(WorkflowError, match="2 nodes titled 'Prompt'"):
        load_workflow("fake-edit", root)
    renamed = json.loads(json.dumps(GRAPH))
    renamed["3"]["inputs"] = {"w": 1, "height": 1}
    (root / "fake-edit" / "workflow.api.json").write_text(json.dumps(renamed), encoding="utf-8")
    with pytest.raises(WorkflowError, match="no input 'width'"):
        load_workflow("fake-edit", root)


def test_an_unfilled_optional_reference_goes_with_its_links(root: Path) -> None:
    graph = load_workflow("fake-edit", root).fill({"prompt": "雨"}, ["dramastudio/a.png"])
    assert graph["5"]["inputs"]["image"] == "dramastudio/a.png"
    assert "6" not in graph and "image2" not in graph["7"]["inputs"]
    assert graph["7"]["inputs"]["image1"] == ["5", 0] and graph["2"]["inputs"]["text"] == "雨"
    with pytest.raises(WorkflowError, match="at least 1 reference"):
        load_workflow("fake-edit", root).fill({}, [])


@pytest.mark.parametrize("slug", ["qwen-image", "qwen-image-edit"])
def test_shipped_workflows_load(slug: str) -> None:
    wf = shipped_workflow(slug)
    assert wf.meta.kind == "image" and wf.output_nodes("image_out")
    assert wf.meta.caps["sizes"]["9:16"] and wf.meta.models
    names = [m.name for m in wf.meta.models]
    for node in wf.graph.values():
        for key in ("unet_name", "clip_name", "vae_name", "lora_name"):
            if key in node["inputs"]:
                assert node["inputs"][key] in names, (slug, key)


# --------------------------------------------------------------------------- runs


async def test_n_pictures_are_n_prompts_with_the_frame_size(root: Path, store: BlobStore) -> None:
    fake = FakeComfy()
    fake.polls = 2
    req = _req(store, n=2)
    result = await _adapter(fake, root, store).run(req, CallContext())
    assert [p["4"]["inputs"]["seed"] for p in fake.prompts] == [7, 8]
    sizes = {(p["3"]["inputs"]["width"], p["3"]["inputs"]["height"]) for p in fake.prompts}
    assert sizes == {(928, 1664)}  # the workflow's size for 9:16, not the 1080×1920 frame
    assert fake.prompts[0]["2"]["inputs"]["text"] == "雨夜的便利店门口"
    sha = req.params["refs"][0]
    assert fake.uploads == [("dramastudio", f"{sha}.png")]
    assert fake.prompts[0]["5"]["inputs"]["image"] == f"dramastudio/{sha}.png"
    assert [(f.mime, f.w, f.h) for f in result.files] == [("image/png", 928, 1664)] * 2
    assert result.usage.images == 2
    comfy = result.raw["comfy"]
    assert comfy["workflow_id"] == "fake-edit" and comfy["comfy_env_hash"] == "env123"
    assert comfy["workflow_sha256"] == load_workflow("fake-edit", root).sha256


async def test_a_refused_graph_says_what_is_missing(root: Path, store: BlobStore) -> None:
    fake = FakeComfy()
    adapter = _adapter(fake, root, store)
    fake.refuse = {
        "error": {"type": "prompt_outputs_failed_validation", "message": "failed"},
        "node_errors": {"1": {"class_type": "UNETLoader", "errors": [
            {"type": "value_not_in_list", "message": "not in list", "details": "m.safetensors"}
        ]}},
    }  # fmt: skip
    with pytest.raises(ModelError) as err:
        await adapter.run(_req(store), CallContext())
    assert err.value.code == "comfy_model_missing" and "m.safetensors" in str(err.value)
    fake.refuse = {"error": {"type": "missing_node_type", "message": "TextEncodeEdit"}}
    with pytest.raises(ModelError) as err:
        await adapter.run(_req(store), CallContext())
    assert err.value.code == "comfy_node_missing"


async def test_a_failed_run_out_of_memory(root: Path, store: BlobStore) -> None:
    fake = FakeComfy()
    error = {"node_type": "KSampler", "exception_type": "torch.OutOfMemoryError",
             "exception_message": "CUDA out of memory"}  # fmt: skip
    fake.fail = {"status_str": "error", "completed": False,
                 "messages": [["execution_start", {}], ["execution_error", error]]}  # fmt: skip
    with pytest.raises(ModelError) as err:
        await _adapter(fake, root, store).run(_req(store), CallContext())
    assert err.value.code == "out_of_memory"


async def test_a_timeout_interrupts_our_prompt_and_unqueues_it(
    root: Path, store: BlobStore
) -> None:
    fake = FakeComfy()
    fake.hang = True
    adapter = _adapter(fake, root, store)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.2):
            await adapter.run(_req(store), CallContext())
    assert fake.posted("/interrupt") == [{"prompt_id": "p1"}]
    assert fake.posted("/queue") == [{"delete": ["p1"]}]


async def test_a_prompt_gone_from_the_queue_fails(root: Path, store: BlobStore) -> None:
    fake = FakeComfy()
    fake.lost = True
    with pytest.raises(ModelError) as err:
        await _adapter(fake, root, store).run(_req(store), CallContext())
    assert err.value.code == "comfy_lost"


async def test_comfy_not_running(root: Path, store: BlobStore) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter = _adapter(FakeComfy(), root, store, transport=httpx.MockTransport(down))
    with pytest.raises(ModelError) as err:
        await adapter.run(_req(store), CallContext())
    assert err.value.code == "comfy_not_running"
    assert (await adapter.health()).detail == "comfy_not_running"


async def test_health_checks_the_model_files(root: Path, store: BlobStore) -> None:
    fake = FakeComfy()
    adapter = _adapter(fake, root, store)
    assert (await adapter.health()).ok
    fake.models = {"diffusion_models": []}
    assert (await adapter.health()).detail == "comfy_model_missing"


async def test_another_model_taking_the_gpu_frees_comfy(root: Path, store: BlobStore) -> None:
    fake = FakeComfy()
    lease = VramLease()
    await _adapter(fake, root, store, lease=lease).run(_req(store), CallContext())
    assert lease.resident == "comfy:fake-edit" and fake.posted("/free") == []
    async with lease.hold("python:local/indextts2"):
        pass
    assert fake.posted("/free") == [{"unload_models": True, "free_memory": True}]

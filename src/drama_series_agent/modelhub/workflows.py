"""ComfyUI workflows shipped with the studio (SPEC 6.4.2): one folder per workflow,
``workflows/<slug>/workflow.api.json`` (ComfyUI's API format) and ``workflow.yaml``.

``workflow.yaml`` says how the studio talks to the graph:

- ``bindings``: a slot (``prompt``, ``width``, ``ref_image`` 1, 2 … ``image_out``; SPEC 6.4.3) →
  the node's title (``_meta.title``, never its id) and the input field. A bound title must be
  unique in the graph and the field must be one of the node's inputs. ``optional: true`` on a
  file slot (``first_frame``, ``video_in``, ``ref_image``, ``dialogue_audio``): without a file
  (for ``ref_image``: fewer pictures than nodes) the bound node is removed together with the
  inputs that read from it (those inputs must be optional on their nodes). ``bypass`` names
  nodes that go too but pass one of their inputs on: whatever read the bypassed node now reads
  what that input read (H3's audio guide hands its ``positive`` on when there is no audio).
- ``models``: the files its loaders name, by ComfyUI model folder (the health check asks the
  running ComfyUI for them).
- ``caps``: like ``providers.yaml`` caps; ``sizes`` maps an aspect to the width and height the
  model was trained for.

The graph's sha256 goes on every version it makes (SPEC 6.4.5).
"""

from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.core.config import _read_yaml
from drama_series_agent.core.paths import REPO_ROOT, drama_home

if TYPE_CHECKING:
    from drama_series_agent.modelhub.adapters.base import ModelSpec

WORKFLOWS_DIR = REPO_ROOT / "workflows"


def user_workflows_dir() -> Path:
    """Where imported workflows go (SPEC 6.4.2): ``~/.drama-studio/workflows/<slug>/``."""
    return drama_home() / "workflows"


def spec_workflows_dir(spec: ModelSpec) -> Path | None:
    """The folder a model's workflow is in; None for the repo's ``workflows/``."""
    return Path(spec.workflow_root) if spec.workflow_root else None


Slot = Literal[
    "first_frame",
    "video_in",
    "ref_image",
    "ref_audio",
    "prompt",
    "negative",
    "dialogue_audio",
    "width",
    "height",
    "fps",
    "seconds",
    "seed",
    "video_out",
    "image_out",
    "audio_out",
]
OUTPUT_SLOTS = frozenset({"video_out", "image_out", "audio_out"})
# Slots filled with an uploaded file's name (``input/dramastudio/…``).
FILE_SLOTS = frozenset({"first_frame", "video_in", "ref_image", "ref_audio", "dialogue_audio"})
# Numbered file slots (1, 2 …): a list of names, filled in order.
LIST_SLOTS: tuple[Slot, ...] = ("ref_image", "ref_audio")


class WorkflowError(ValueError):
    pass


class Bypass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: str  # the node's title
    input: str  # the input whose link its readers take over


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: Slot
    index: int | None = None  # ref_image 1, 2, 3 …
    node: str  # the node's title
    field: str | None = None  # the input; None for an output node
    optional: bool = False
    bypass: list[Bypass] = Field(default_factory=list)  # with an optional slot left empty


class ModelFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str  # diffusion_models, text_encoders, vae, loras …
    name: str


class WorkflowMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: dict[str, str] = Field(default_factory=dict)
    kind: str
    tier: Literal["recommended", "mine", "unverified"] = "recommended"
    bindings: list[Binding]
    models: list[ModelFile] = Field(default_factory=list)
    caps: dict[str, Any] = Field(default_factory=dict)


class Workflow:
    """One workflow folder, checked: every binding points at one node and one of its inputs."""

    def __init__(self, slug: str, graph: dict[str, Any], meta: WorkflowMeta, sha256: str) -> None:
        self.slug = slug
        self.graph = graph
        self.meta = meta
        self.sha256 = sha256
        self._ids: dict[str, str] = {}
        titles: dict[str, list[str]] = {}
        for node_id, node in graph.items():
            title = (node.get("_meta") or {}).get("title")
            if isinstance(title, str):
                titles.setdefault(title, []).append(node_id)
        for b in meta.bindings:
            ids = titles.get(b.node, [])
            if len(ids) != 1:
                found = "no node" if not ids else f"{len(ids)} nodes"
                raise WorkflowError(f"{slug}: {found} titled {b.node!r} ({b.slot})")
            inputs = graph[ids[0]].get("inputs") or {}
            if b.field is not None and b.field not in inputs:
                raise WorkflowError(f"{slug}: {b.node!r} has no input {b.field!r}")
            if b.field is None and b.slot not in OUTPUT_SLOTS:
                raise WorkflowError(f"{slug}: {b.slot} needs a field")
            self._ids[b.node] = ids[0]
            for by in b.bypass:
                found_ids = titles.get(by.node, [])
                if len(found_ids) != 1:
                    raise WorkflowError(f"{slug}: bypass {by.node!r} is not one node")
                if not _is_link((graph[found_ids[0]].get("inputs") or {}).get(by.input)):
                    raise WorkflowError(f"{slug}: bypass {by.node!r} has no link {by.input!r}")
                self._ids[by.node] = found_ids[0]

    def bindings(self, slot: Slot) -> list[Binding]:
        return sorted((b for b in self.meta.bindings if b.slot == slot), key=lambda b: b.index or 0)

    def has(self, slot: Slot) -> bool:
        return any(b.slot == slot for b in self.meta.bindings)

    def needs_refs(self) -> bool:
        """It cannot run without a reference picture (an edit-only model, Qwen-Image-Edit
        2511): a ``ref_image`` slot that is not optional."""
        return any(not b.optional for b in self.bindings("ref_image"))

    def node_id(self, title: str) -> str:
        return self._ids[title]

    def output_nodes(self, slot: Slot) -> list[str]:
        return [self._ids[b.node] for b in self.bindings(slot)]

    def fill(self, values: dict[Slot, Any], refs: list[str] | None = None) -> dict[str, Any]:
        """A copy of the graph with the slots filled. ``refs``: the uploaded reference names,
        for ``ref_image`` 1, 2 … (``values["ref_audio"]``: the voice samples', a list too);
        the other file slots take theirs from ``values``. An optional file slot left without
        one is removed (with its bypasses); a required one is an error."""
        graph = copy.deepcopy(self.graph)
        for slot, value in values.items():
            if slot in LIST_SLOTS:
                continue
            for b in self.bindings(slot):
                graph[self._ids[b.node]]["inputs"][str(b.field)] = value
        lists: dict[Slot, list[str]] = {
            "ref_image": list(refs or []),
            "ref_audio": list(values.get("ref_audio") or []),
        }
        for slot, names in lists.items():
            for i, b in enumerate(self.bindings(slot)):
                if i < len(names):
                    graph[self._ids[b.node]]["inputs"][str(b.field)] = names[i]
                elif b.optional:
                    self._drop(graph, b)
                else:
                    raise WorkflowError(f"{self.slug}: needs at least {i + 1} of {slot}")
        for b in self.meta.bindings:
            if b.slot in FILE_SLOTS and b.slot not in LIST_SLOTS and values.get(b.slot) is None:
                if not b.optional:
                    raise WorkflowError(f"{self.slug}: needs {b.slot}")
                self._drop(graph, b)
        return graph

    def _drop(self, graph: dict[str, Any], b: Binding) -> None:
        for by in b.bypass:
            _bypass(graph, self._ids[by.node], by.input)
        _remove(graph, self._ids[b.node])


def _remove(graph: dict[str, Any], node_id: str) -> None:
    """Drop a node and every input that reads one of its outputs."""
    del graph[node_id]
    for node in graph.values():
        inputs = node.get("inputs") or {}
        for name in [k for k, v in inputs.items() if _links_to(v, node_id)]:
            del inputs[name]


def _bypass(graph: dict[str, Any], node_id: str, input_name: str) -> None:
    """Drop a node; whatever read it now reads what its ``input_name`` read."""
    source = graph[node_id]["inputs"][input_name]
    del graph[node_id]
    for node in graph.values():
        inputs = node.get("inputs") or {}
        for name in [k for k, v in inputs.items() if _links_to(v, node_id)]:
            inputs[name] = list(source)


def _is_link(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[1], int)


def _links_to(value: Any, node_id: str) -> bool:
    return isinstance(value, list) and len(value) == 2 and str(value[0]) == node_id


def load_workflow(slug: str, root: Path | None = None) -> Workflow:
    folder = (root or WORKFLOWS_DIR) / slug
    api = folder / "workflow.api.json"
    try:
        raw = api.read_bytes()
        meta = WorkflowMeta.model_validate(_read_yaml(folder / "workflow.yaml"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"{slug}: {exc.filename} not found") from None
    graph = json.loads(raw.decode("utf-8"))
    if not isinstance(graph, dict) or not all(isinstance(n, dict) for n in graph.values()):
        raise WorkflowError(f"{slug}: not a workflow in ComfyUI's API format")
    return Workflow(slug, graph, meta, hashlib.sha256(raw).hexdigest())


@lru_cache(maxsize=32)
def shipped_workflow(slug: str) -> Workflow:
    """A workflow in the repo's ``workflows/`` (read once)."""
    return load_workflow(slug)


def has_workflow(slug: str | None, root: Path | None = None) -> bool:
    if not slug:
        return False
    folder = (root or WORKFLOWS_DIR) / slug
    return (folder / "workflow.api.json").is_file() and (folder / "workflow.yaml").is_file()


def workflow_sha256(spec: ModelSpec) -> str | None:
    """The hash of a ComfyUI model's workflow file as it is now (read each time, unlike
    ``shipped_workflow``): what its results depend on besides the request. None without one."""
    root = spec_workflows_dir(spec)
    if not spec.workflow or not has_workflow(spec.workflow, root):
        return None
    api = (root or WORKFLOWS_DIR) / spec.workflow / "workflow.api.json"
    return hashlib.sha256(api.read_bytes()).hexdigest()

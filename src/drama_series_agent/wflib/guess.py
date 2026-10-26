"""Guess an imported workflow's bindings (SPEC 6.4.3): which node is the first frame, the
prompt, the seed, the size, the output.

The rules read the graph the way a person would:
- ``LoadImage`` → first frame (a second one → reference picture 1, 2 …); ``LoadAudio`` →
  dialogue audio; ``LoadVideo`` → video in;
- the ``CLIPTextEncode`` that feeds a sampler's ``positive`` input (followed upstream through
  conditioning nodes) → prompt, the one on ``negative`` → negative;
- a sampler's ``seed`` / ``noise_seed`` → seed;
- an ``Empty…Latent…`` node's ``width`` / ``height`` → size; a ``fps`` / ``frame_rate`` input →
  frame rate;
- ``SaveVideo`` / ``VHS_VideoCombine`` → video out, ``SaveImage`` → image out, ``SaveAudio`` →
  audio out.

A binding finds its node by title, so the guessed nodes get unique titles first (an imported
graph often has two nodes titled ``CLIP Text Encode``). DramaStudio's own input and output
nodes need no guess: their class says what they are.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

DRAMASTUDIO_PREFIX = "DramaStudio"
SAMPLER_SEEDS = ("seed", "noise_seed")
SIZE_FIELDS = ("width", "height")
FPS_FIELDS = ("fps", "frame_rate")
VIDEO_OUT = {"SaveVideo", "VHS_VideoCombine", "SaveAnimatedWEBP", "SaveWEBM"}
IMAGE_OUT = {"SaveImage"}
AUDIO_OUT = {"SaveAudio", "SaveAudioMP3", "SaveAudioOpus"}


@dataclass
class Guessed:
    """One binding, in the contract's shape (``web/src/api/schemas/workflows.ts``)."""

    slot: str
    index: int | None
    node_title: str
    node_class: str
    field: str | None
    state: str  # dramastudio / confirmed / guessed

    def out(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "index": self.index,
            "node_title": self.node_title,
            "node_class": self.node_class,
            "field": self.field,
            "state": self.state,
        }


def is_api_format(data: Any) -> bool:
    """ComfyUI's API format: ``{node id: {class_type, inputs}}``."""
    return (
        isinstance(data, dict)
        and bool(data)
        and all(isinstance(n, dict) and "class_type" in n and "inputs" in n for n in data.values())
    )


def title_of(node: dict[str, Any]) -> str:
    meta = node.get("_meta") or {}
    title = meta.get("title")
    return title if isinstance(title, str) and title else str(node.get("class_type"))


def nodes_of(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """The nodes a binding can point at: title, class and input fields (not links)."""
    out = []
    for node in graph.values():
        fields = [k for k, v in (node.get("inputs") or {}).items() if not _is_link(v)]
        out.append({"title": title_of(node), "class_type": node["class_type"], "fields": fields})
    return out


def uses_dramastudio(graph: dict[str, Any]) -> bool:
    return any(str(n.get("class_type", "")).startswith(DRAMASTUDIO_PREFIX) for n in graph.values())


def _is_link(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[1], int)


def _upstream_text_encoders(graph: dict[str, Any], start: Any, name: str) -> list[str]:
    """Node ids of the ``CLIPTextEncode`` nodes a conditioning link comes from. Through a
    node that takes both (``LTXVConditioning``: ``positive`` and ``negative`` in, the same
    out), only its input of the same ``name`` is followed."""
    found: list[str] = []
    seen: set[str] = set()
    todo = [str(start[0])] if _is_link(start) else []
    while todo:
        node_id = todo.pop()
        if node_id in seen or node_id not in graph:
            continue
        seen.add(node_id)
        node = graph[node_id]
        if "TextEncode" in str(node["class_type"]):
            found.append(node_id)
            continue
        inputs = node.get("inputs") or {}
        if _is_link(inputs.get(name)):
            todo.append(str(inputs[name][0]))
        else:
            todo += [str(v[0]) for v in inputs.values() if _is_link(v)]
    return found


def unique_titles(graph: dict[str, Any], ids: list[str]) -> dict[str, Any]:
    """A copy of the graph where each of ``ids`` has a title no other node has."""
    graph = copy.deepcopy(graph)
    counts: dict[str, int] = {}
    for node in graph.values():
        counts[title_of(node)] = counts.get(title_of(node), 0) + 1
    for node_id in ids:
        node = graph[node_id]
        title = title_of(node)
        if counts[title] > 1:
            new = f"{title} #{node_id}"
            counts[title] -= 1
            counts[new] = 1
            node.setdefault("_meta", {})["title"] = new
        else:
            node.setdefault("_meta", {})["title"] = title
    return graph


def guess_bindings(graph: dict[str, Any]) -> tuple[dict[str, Any], list[Guessed]]:
    """The graph with unique titles on the guessed nodes, and the guessed bindings."""
    picks: list[tuple[str, int | None, str, str | None]] = []  # slot, index, node id, field
    positive: list[str] = []
    negative: list[str] = []
    for node in graph.values():
        inputs = node.get("inputs") or {}
        positive += _upstream_text_encoders(graph, inputs.get("positive"), "positive")
        negative += _upstream_text_encoders(graph, inputs.get("negative"), "negative")
    images = 0
    for node_id, node in sorted(graph.items(), key=lambda kv: _order(kv[0])):
        cls = str(node["class_type"])
        inputs = node.get("inputs") or {}
        if cls.startswith(DRAMASTUDIO_PREFIX):
            continue  # its class says what it is (step 11)
        if cls == "LoadImage":
            if images == 0:
                picks.append(("first_frame", None, node_id, "image"))
            else:
                picks.append(("ref_image", images, node_id, "image"))
            images += 1
        elif cls == "LoadAudio":
            picks.append(("dialogue_audio", None, node_id, "audio"))
        elif cls in ("LoadVideo", "VHS_LoadVideo"):
            picks.append(("video_in", None, node_id, "video" if "video" in inputs else None))
        elif node_id in positive and "text" in inputs and not _is_link(inputs["text"]):
            picks.append(("prompt", None, node_id, "text"))
        elif node_id in negative and "text" in inputs and not _is_link(inputs["text"]):
            picks.append(("negative", None, node_id, "text"))
        elif cls in VIDEO_OUT:
            picks.append(("video_out", None, node_id, None))
        elif cls in IMAGE_OUT:
            picks.append(("image_out", None, node_id, None))
        elif cls in AUDIO_OUT:
            picks.append(("audio_out", None, node_id, None))
        for field in SAMPLER_SEEDS:
            if field in inputs and not _is_link(inputs[field]):
                picks.append(("seed", None, node_id, field))
                break
        if "Latent" in cls and cls.startswith("Empty"):
            for field in SIZE_FIELDS:
                if field in inputs and not _is_link(inputs[field]):
                    picks.append((field, None, node_id, field))
        for field in FPS_FIELDS:
            if field in inputs and not _is_link(inputs[field]):
                picks.append(("fps", None, node_id, field))
                break
    # One of each slot (reference pictures excepted): the first node in graph order wins.
    seen: set[tuple[str, int | None]] = set()
    kept = []
    for slot, index, node_id, bound in picks:
        if (slot, index) in seen:
            continue
        seen.add((slot, index))
        kept.append((slot, index, node_id, bound))
    titled = unique_titles(graph, list(dict.fromkeys(p[2] for p in kept)))
    return titled, [
        Guessed(
            slot=slot,
            index=index,
            node_title=title_of(titled[node_id]),
            node_class=str(titled[node_id]["class_type"]),
            field=field,
            state="guessed",
        )
        for slot, index, node_id, field in kept
    ]


def _order(node_id: str) -> tuple[int, str]:
    return (int(node_id), "") if node_id.isdigit() else (1 << 30, node_id)


def kind_of(bindings: list[Guessed]) -> str:
    """What the workflow makes, from its output bindings."""
    slots = {b.slot for b in bindings}
    if "video_out" in slots:
        return "video"
    if "audio_out" in slots and "image_out" not in slots:
        return "audio"
    return "image"


# A loader input → the ComfyUI model folder its file is in (the health check, SPEC 6.4.4-1).
MODEL_FIELDS = {
    "ckpt_name": "checkpoints",
    "unet_name": "diffusion_models",
    "vae_name": "vae",
    "lora_name": "loras",
    "clip_name": "text_encoders",
    "clip_name1": "text_encoders",
    "clip_name2": "text_encoders",
    "clip_name3": "text_encoders",
    "control_net_name": "controlnet",
    "model_name": "upscale_models",
}
MODEL_EXTENSIONS = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin", ".sft")


def model_files(graph: dict[str, Any]) -> list[dict[str, str]]:
    """The model files the graph's loaders name: ``[{folder, name}]``, each once."""
    out: list[dict[str, str]] = []
    for node in graph.values():
        for field, value in (node.get("inputs") or {}).items():
            folder = MODEL_FIELDS.get(field)
            if folder and isinstance(value, str) and value.lower().endswith(MODEL_EXTENSIONS):
                entry = {"folder": folder, "name": value}
                if entry not in out:
                    out.append(entry)
    return out

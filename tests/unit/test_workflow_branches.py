"""Switchable workflow branches (SPEC 6.4.8, M5 step 12b): ``workflow.yaml``'s ``branches``,
removed when off the way an optional slot's node is."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from drama_series_agent.modelhub.workflows import WorkflowError, load_workflow


def _node(cls: str, title: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": cls, "inputs": inputs, "_meta": {"title": title}}


GRAPH = {
    "1": _node("CheckpointLoaderSimple", "模型", ckpt_name="x.safetensors"),
    "2": _node("LoraLoader", "LoRA", model=["1", 0], clip=["1", 1], lora_name="style.safetensors"),
    "3": _node("CLIPTextEncode", "提示词", text="", clip=["2", 1]),
    "4": _node("LoadImage", "控制图", image="pose.png"),
    "5": _node("ControlNetApply", "ControlNet", conditioning=["3", 0], image=["4", 0]),
    "6": _node("KSampler", "采样", model=["2", 0], positive=["5", 0], seed=0),
    "7": _node("SaveImage", "输出", images=["6", 0]),
}
META: dict[str, Any] = {
    "kind": "image",
    "bindings": [
        {"slot": "prompt", "node": "提示词", "field": "text"},
        {"slot": "seed", "node": "采样", "field": "seed"},
        {"slot": "image_out", "node": "输出"},
    ],
    "branches": [
        {
            "id": "lora",
            "kind": "lora",
            "nodes": [],
            "bypass": [
                {"node": "LoRA", "input": "model", "output": 0},
                {"node": "LoRA", "input": "clip", "output": 1},
            ],
            "default": True,
        },
        {
            "id": "controlnet",
            "kind": "controlnet",
            "nodes": ["控制图"],
            "bypass": [{"node": "ControlNet", "input": "conditioning"}],
        },
    ],
}


def _write(root: Path, meta: dict[str, Any]) -> Path:
    folder = root / "branchy"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "workflow.api.json").write_text(json.dumps(GRAPH), encoding="utf-8")
    (folder / "workflow.yaml").write_text(yaml.safe_dump(meta, allow_unicode=True), "utf-8")
    return root


def test_branches_follow_their_defaults_and_the_shots_choice(tmp_path: Path) -> None:
    wf = load_workflow("branchy", _write(tmp_path, META))
    assert wf.branch_states() == {"lora": True, "controlnet": False}
    assert wf.branch_states({"controlnet": True, "lora": None}) == {
        "lora": True,
        "controlnet": True,
    }
    # Defaults: the LoRA stays, ControlNet goes and the sampler reads the prompt itself.
    graph = wf.fill({"prompt": "雨", "seed": 3})
    assert "2" in graph and "4" not in graph and "5" not in graph
    assert graph["6"]["inputs"]["positive"] == ["3", 0]
    assert graph["3"]["inputs"]["text"] == "雨" and graph["6"]["inputs"]["seed"] == 3
    # LoRA off: each reader takes the link of the matching input (model ← 0, clip ← 1).
    graph = wf.fill({"prompt": "雨"}, branches={"lora": False, "controlnet": True})
    assert "2" not in graph
    assert graph["6"]["inputs"]["model"] == ["1", 0]
    assert graph["3"]["inputs"]["clip"] == ["1", 1]
    assert graph["5"]["inputs"] == {"conditioning": ["3", 0], "image": ["4", 0]}
    assert wf.graph["6"]["inputs"]["model"] == ["2", 0]  # the stored graph is untouched


def test_a_branch_names_real_nodes_and_never_a_bound_one(tmp_path: Path) -> None:
    bad = {**META, "branches": [{"id": "x", "kind": "lora", "nodes": ["没有"]}]}
    with pytest.raises(WorkflowError, match="not one node"):
        load_workflow("branchy", _write(tmp_path, bad))
    bad = {**META, "branches": [{"id": "x", "kind": "upscale", "nodes": ["输出"]}]}
    with pytest.raises(WorkflowError, match="bound node"):
        load_workflow("branchy", _write(tmp_path, bad))
    not_a_link = [{"node": "LoRA", "input": "lora_name"}]
    bad = {**META, "branches": [{"id": "x", "kind": "lora", "nodes": [], "bypass": not_a_link}]}
    with pytest.raises(WorkflowError, match="no link"):
        load_workflow("branchy", _write(tmp_path, bad))

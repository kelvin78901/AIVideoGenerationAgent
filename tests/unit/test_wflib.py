"""Workflow import (M5 step 2): guessed bindings and UI → API conversion (``wflib``)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from drama_series_agent.wflib.comfy import DEMO_DIR
from drama_series_agent.wflib.convert import ConvertError, is_ui_format, ui_to_api
from drama_series_agent.wflib.guess import (
    guess_bindings,
    is_api_format,
    kind_of,
    model_files,
    nodes_of,
)


def _demo(path: str) -> dict[str, Any]:
    data = json.loads((DEMO_DIR / "workflows" / path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _object_info() -> dict[str, Any]:
    data = json.loads((DEMO_DIR / "object_info.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_guess_reads_the_ltx_graph_like_a_person() -> None:
    graph, guessed = guess_bindings(_demo("我的/雨夜氛围-ltx2.json"))
    got = {(g.slot, g.node_class, g.field) for g in guessed}
    assert got == {
        ("first_frame", "LoadImage", "image"),
        ("prompt", "CLIPTextEncode", "text"),  # feeds positive through LTXVConditioning
        ("negative", "CLIPTextEncode", "text"),
        ("width", "EmptyLTXVLatentVideo", "width"),
        ("height", "EmptyLTXVLatentVideo", "height"),
        ("seed", "RandomNoise", "noise_seed"),
        ("fps", "LTXVConditioning", "frame_rate"),  # the first frame-rate input in graph order
        ("video_out", "SaveVideo", None),
    }
    assert all(g.state == "guessed" for g in guessed)
    # The two CLIP Text Encode nodes now have titles of their own; the bindings use them.
    by_slot = {g.slot: g.node_title for g in guessed}
    assert by_slot["prompt"] != by_slot["negative"]
    titles = [n["title"] for n in nodes_of(graph)]
    assert by_slot["prompt"] in titles and titles.count(by_slot["prompt"]) == 1
    assert kind_of(guessed) == "video"
    assert model_files(graph) == [
        {"folder": "checkpoints", "name": "ltx-2-19b-distilled-fp8.safetensors"}
    ]


def test_a_second_load_image_is_a_reference_picture() -> None:
    graph = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "b.png"}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "x"}},
    }
    _, guessed = guess_bindings(graph)
    assert [(g.slot, g.index) for g in guessed] == [
        ("first_frame", None),
        ("ref_image", 1),
        ("image_out", None),
    ]
    assert kind_of(guessed) == "image"


def test_ui_format_becomes_the_api_format() -> None:
    ui = _demo("sdxl_basic.json")
    assert is_ui_format(ui) and not is_api_format(ui)
    api = ui_to_api(ui, _object_info())
    assert is_api_format(api)
    assert "10" not in api  # the note is dropped
    sampler = api["3"]
    assert sampler["class_type"] == "KSampler"
    # 「randomize」 after the seed is the control widget, not the next input.
    assert sampler["inputs"] == {
        "seed": 156680208700286,
        "steps": 25,
        "cfg": 7,
        "sampler_name": "euler",
        "scheduler": "normal",
        "denoise": 1,
        "model": ["4", 0],
        "positive": ["6", 0],
        "negative": ["7", 0],
        "latent_image": ["5", 0],
    }
    assert api["6"]["_meta"]["title"] == "Positive"
    assert api["4"]["_meta"]["title"] == "Load Checkpoint"  # no title: the display name
    assert api["5"]["inputs"] == {"width": 832, "height": 1216, "batch_size": 1}
    # Converted, it guesses like any other graph.
    _, guessed = guess_bindings(api)
    assert {g.slot for g in guessed} >= {"prompt", "negative", "seed", "width", "image_out"}


def test_bypassed_nodes_pass_through_and_muted_ones_drop() -> None:
    ui = _demo("sdxl_basic.json")
    for node in ui["nodes"]:
        if node["id"] == 8:  # VAE Decode, bypassed: SaveImage reads the latent's source…
            node["mode"] = 4
    api = ui_to_api(ui, _object_info())
    assert "8" not in api
    assert api["9"]["inputs"]["images"] == ["3", 0]  # its first input of a linked type


def test_unknown_node_classes_cannot_be_converted() -> None:
    ui = _demo("sdxl_basic.json")
    ui["nodes"][0]["type"] = "SomeCustomLoader"
    with pytest.raises(ConvertError) as err:
        ui_to_api(ui, _object_info())
    assert err.value.code == "workflow_unknown_nodes"
    assert err.value.classes == ["SomeCustomLoader"]


def test_dramastudio_nodes_bind_by_class_and_nothing_else_is_guessed() -> None:
    graph = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "x.png"}},  # not ours: ignored
        "2": {"class_type": "DramaStudioRefImage", "inputs": {"image": "a.png"}},  # no index
        "3": {"class_type": "DramaStudioRefImage", "inputs": {"index": 3, "image": "b.png"}},
        "4": {"class_type": "DramaStudioRefImage", "inputs": {"image": "c.png"}},
        "5": {"class_type": "DramaStudioAudioOut", "inputs": {"audio": ["1", 0]}},
        "6": {"class_type": "DramaStudioShot", "inputs": {}},  # a later node (M9): no slot
    }
    titled, bindings = guess_bindings(graph)
    assert [(b.slot, b.index, b.field, b.state) for b in bindings] == [
        ("ref_image", 1, "image", "dramastudio"),
        ("ref_image", 3, "image", "dramastudio"),
        ("ref_image", 4, "image", "dramastudio"),
        ("audio_out", None, None, "dramastudio"),
    ]
    assert len({b.node_title for b in bindings}) == 4  # unique titles for the three refs
    assert kind_of(bindings) == "audio"
    assert titled["1"] == graph["1"]

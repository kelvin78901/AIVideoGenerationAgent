"""DramaStudio's ComfyUI nodes (``integrations/comfyui-dramastudio``, M5 step 11).

The pack runs inside ComfyUI; here it loads without it: ``folder_paths`` is a stand-in over a
temp folder and the media-loading parts are left to the manual check in ComfyUI's own Python
(DECISIONS「M5 第 11 步」). What the studio relies on is checked against ``wflib.dramastudio``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from drama_series_agent.wflib import dramastudio


@pytest.fixture
def comfy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """A ``folder_paths`` over ``tmp_path/input`` and ``tmp_path/output``."""
    inp, out = tmp_path / "input", tmp_path / "output"
    inp.mkdir()
    out.mkdir()
    fp = types.ModuleType("folder_paths")
    fp.get_input_directory = lambda: str(inp)  # type: ignore[attr-defined]
    fp.get_output_directory = lambda: str(out)  # type: ignore[attr-defined]
    fp.get_annotated_filepath = lambda name: str(inp / name)  # type: ignore[attr-defined]
    fp.exists_annotated_filepath = lambda name: (inp / name).is_file()  # type: ignore[attr-defined]

    def save_path(prefix: str, root: str, w: int, h: int) -> tuple[str, str, int, str, str]:
        sub, stem = prefix.rsplit("/", 1)
        (Path(root) / sub).mkdir(parents=True, exist_ok=True)
        return str(Path(root) / sub), stem, 1, sub, prefix

    fp.get_save_image_path = save_path  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "folder_paths", fp)
    return types.SimpleNamespace(input=inp, output=out)


@pytest.fixture
def pack() -> Iterator[types.ModuleType]:
    folder = dramastudio.PACK_DIR
    spec = importlib.util.spec_from_file_location(
        "comfyui_dramastudio", folder / "__init__.py", submodule_search_locations=[str(folder)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_dramastudio"] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        for name in [n for n in sys.modules if n.startswith("comfyui_dramastudio")]:
            del sys.modules[name]


def _required(cls: Any) -> dict[str, Any]:
    required: dict[str, Any] = cls.INPUT_TYPES()["required"]
    return required


def test_the_pack_has_the_nodes_the_studio_binds(pack: types.ModuleType, comfy: Any) -> None:
    classes: dict[str, Any] = pack.NODE_CLASS_MAPPINGS
    assert set(classes) == set(dramastudio.NODES)
    assert set(pack.NODE_DISPLAY_NAME_MAPPINGS) == set(classes)
    assert all(t.startswith("DramaStudio ▸ ") for t in pack.NODE_DISPLAY_NAME_MAPPINGS.values())
    for name, slots in dramastudio.NODES.items():
        cls = classes[name]
        assert name.startswith(dramastudio.PREFIX)
        assert callable(getattr(cls(), cls.FUNCTION))
        inputs = _required(cls)
        for ns in slots:
            if ns.field is None:  # an output node: ComfyUI runs it and lists its files
                assert cls.OUTPUT_NODE is True
            else:  # the input the studio fills, with a default to run by hand
                assert ns.field in inputs
                if not isinstance(inputs[ns.field][0], list):
                    assert "default" in inputs[ns.field][1]
        if any(ns.slot in dramastudio.NUMBERED for ns in slots):
            assert inputs[dramastudio.INDEX_FIELD][0] == "INT"


def test_file_inputs_list_the_input_folder_and_check_the_file(
    pack: types.ModuleType, comfy: Any
) -> None:
    (comfy.input / "dramastudio").mkdir()
    (comfy.input / "dramastudio" / "frame.png").write_bytes(b"png")
    (comfy.input / "top.JPG").write_bytes(b"jpg")
    (comfy.input / "line.wav").write_bytes(b"wav")
    (comfy.input / "clip.mp4").write_bytes(b"mp4")
    first = pack.NODE_CLASS_MAPPINGS["DramaStudioFirstFrame"]
    files, opts = _required(first)["image"]
    assert files == ["dramastudio/frame.png", "top.JPG"] and opts == {"image_upload": True}
    assert _required(pack.NODE_CLASS_MAPPINGS["DramaStudioDialogueAudio"])["audio"][0] == [
        "line.wav"
    ]
    assert _required(pack.NODE_CLASS_MAPPINGS["DramaStudioVideoIn"])["video"] == (
        ["clip.mp4"],
        {"video_upload": True},
    )
    # The studio's upload need not be in the list ComfyUI built when it started.
    assert first.VALIDATE_INPUTS(image="dramastudio/frame.png") is True
    assert "no image file" in first.VALIDATE_INPUTS(image="dramastudio/gone.png")
    # A changed file reruns the node.
    assert first.IS_CHANGED(image="top.JPG") == hashlib.sha256(b"jpg").hexdigest()


def test_value_nodes_pass_their_values_on(pack: types.ModuleType) -> None:
    nodes = pack.NODE_CLASS_MAPPINGS
    assert nodes["DramaStudioPrompt"]().run("雨夜") == ("雨夜",)
    assert nodes["DramaStudioNegative"]().run("模糊") == ("模糊",)
    assert nodes["DramaStudioSize"]().run(768, 1344) == (768, 1344)
    assert nodes["DramaStudioSeed"]().run(42) == (42,)
    assert nodes["DramaStudioDuration"]().run(24.0, 5.0) == (24.0, 24, 5.0, 120)
    assert nodes["DramaStudioDuration"]().run(23.976, 0.01) == (23.976, 24, 0.01, 1)


def test_video_out_lists_its_file_like_comfyuis_save_video(
    pack: types.ModuleType, comfy: Any
) -> None:
    saved: list[str] = []

    class Clip:
        def get_dimensions(self) -> tuple[int, int]:
            return 768, 1344

        def save_to(self, path: str) -> None:
            saved.append(path)
            Path(path).write_bytes(b"mp4")

    out = pack.NODE_CLASS_MAPPINGS["DramaStudioVideoOut"]().save(Clip(), "dramastudio/out")
    clip = {"filename": "out_00001_.mp4", "subfolder": "dramastudio", "type": "output"}
    assert out == {"ui": {"images": [clip], "animated": (True,)}}
    assert saved == [str(comfy.output / "dramastudio" / "out_00001_.mp4")]

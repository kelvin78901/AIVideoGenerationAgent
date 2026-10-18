from __future__ import annotations

from typing import Any

import pytest

from drama_series_agent.setup.manifest import Manifest, Message, load_manifest, topo_order


def _item(item_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": item_id,
        "group": "rt",
        "name": {"zh": item_id, "en": item_id},
        "detect": {"type": "command", "cmd": f"{item_id} --version"},
        **extra,
    }


def test_real_manifest_parses() -> None:
    m = load_manifest()
    ids = [x.id for x in m.items]
    assert len(ids) == 29
    assert len(set(ids)) == len(ids)
    assert {"official", "cn", "auto"} <= set(m.mirrors)


def test_platform_rows() -> None:
    m = load_manifest()
    win = [x.id for x in m.for_platform("windows")]
    mac = [x.id for x in m.for_platform("macos")]
    assert len(win) == 29
    assert len(mac) == 28
    assert "driver" in win and "driver" not in mac
    assert [x for x in win if x != "driver"] == mac  # manifest order kept


def test_install_steps_filtered_by_platform() -> None:
    m = load_manifest()
    win = {x.id: x for x in m.for_platform("windows")}
    mac = {x.id: x for x in m.for_platform("macos")}
    assert [s.model_extra.get("note") for s in win["torch"].install] == [None]
    assert [s.model_extra.get("note") for s in mac["torch"].install] == ["MPS 版"]


def test_macos_overrides() -> None:
    m = load_manifest()
    win = {x.id: x for x in m.for_platform("windows")}
    mac = {x.id: x for x in m.for_platform("macos")}

    assert win["comfy"].required and not mac["comfy"].required
    assert mac["comfy"].fix["optional"] == Message(code="comfy_images_only")

    llm = mac["w_llm"]
    assert llm.required and llm.variant == "MLX"
    assert llm.name.en == "Qwen3.6-27B (MLX)"
    # Override fixes are merged over the item's own.
    assert llm.fix["optional"] == Message(code="llm_optional")
    assert llm.fix["missing"] == Message(code="download_local_writing")
    assert not win["w_llm"].required

    assert mac["keys"].if_missing == "warn" and win["keys"].if_missing is None
    assert mac["w_tts"].name.zh == "本地配音模型"
    assert mac["torch"].fix["old"] == Message(code="torch_cuda", params={"cuda": "13.0"})


def test_not_required_when_a_dependency_is_not() -> None:
    m = load_manifest()
    win = {x.id: x for x in m.for_platform("windows")}
    mac = {x.id: x for x in m.for_platform("macos")}
    # ComfyUI is optional on the Mac, so its nodes are too.
    assert win["node_dramastudio"].required
    assert not mac["node_dramastudio"].required
    assert mac["torch"].required  # python and uv stay required


def test_dependencies_dropped_with_their_platform() -> None:
    m = Manifest.model_validate(
        {
            "items": [
                _item("a", platforms=["windows"]),
                _item("b", depends_on=["a"], required=True),
            ]
        }
    )
    mac = {x.id: x for x in m.for_platform("macos")}
    assert list(mac) == ["b"]
    assert mac["b"].depends_on == [] and mac["b"].required


def test_optional_shorthand_and_installable() -> None:
    m = Manifest.model_validate(
        {
            "items": [
                _item("a", required=True, macos="optional", install=[{"type": "script"}]),
                _item("b", installable=False, install=[{"type": "script"}]),
                _item("c"),
            ]
        }
    )
    mac = {x.id: x for x in m.for_platform("macos")}
    assert not mac["a"].required and mac["a"].can_install
    assert not mac["b"].can_install
    assert not mac["c"].can_install


def test_topo_order_puts_dependencies_first() -> None:
    m = Manifest.model_validate(
        {"items": [_item("c", depends_on=["b"]), _item("a"), _item("b", depends_on=["a"])]}
    )
    assert [x.id for x in topo_order(m.items)] == ["a", "b", "c"]


def test_message_from_code() -> None:
    assert Message.model_validate("download").public() == {"code": "download", "params": {}}


@pytest.mark.parametrize(
    ("items", "error"),
    [
        ([_item("a"), _item("a")], "duplicate item ids: a"),
        ([_item("a", depends_on=["zzz"])], "a: unknown depends_on zzz"),
        (
            [
                _item("a", depends_on=["c"]),
                _item("b", depends_on=["a"]),
                _item("c", depends_on=["b"]),
            ],
            "dependency cycle: a -> c -> b -> a",
        ),
        ([_item("a", depends_on=["a"])], "dependency cycle: a -> a"),
        ([_item("a", macos={"colour": "red"})], "colour"),
        ([_item("a", detect={"type": "telepathy"})], "telepathy"),
        ([_item("a", group="misc")], "misc"),
        ([_item("a", install=[{"type": "rsync"}])], "rsync"),
    ],
)
def test_invalid_manifests(items: list[dict[str, Any]], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        Manifest.model_validate({"items": items})

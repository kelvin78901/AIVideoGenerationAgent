"""镜头参考图 and 风格板 (M5.5 step 12), in Mock mode.

- ``POST /shots/{id}/refs`` (``composition`` / ``pose`` / ``light`` / ``style``) and
  ``POST /series/{id}/style-board``: picture sets like 多参考图, a new version adopted each time.
- A keyframe sends the assets' pictures, then the shot's, then the style board, as far as the
  model takes; each added picture is said to be only for its purpose; it depends on the sets it
  sent, so changing one makes it 「待更新」.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_asset_more_api import V1, _add, _code, _keyframe, _png, _prompt, _rows, _shot, client

from drama_series_agent.core.models_db import Dependency
from drama_series_agent.pipeline.components import kf

__all__ = ["client"]


def _shot_ref(client: TestClient, label: str, purpose: str, data: bytes) -> Any:
    return client.post(
        f"{V1}/shots/{_shot(client, label)['id']}/refs",
        files={"file": ("ref.png", data, "image/png")},
        data={"purpose": purpose},
    )


def _style(client: TestClient, data: bytes, series: str = "demo") -> Any:
    return client.post(
        f"{V1}/series/{series}/style-board", files={"file": ("look.png", data, "image/png")}
    )


def test_a_shots_pictures_and_the_style_board(client: TestClient) -> None:
    resp = _shot_ref(client, "1-04", "composition", _png(1))
    assert resp.status_code == 200, resp.text
    refs = resp.json()
    assert refs["slot"] == "shot_refs" and refs["owner_id"] == _shot(client, "1-04")["id"]
    refs = _shot_ref(client, "1-04", "light", _png(2)).json()
    v = refs["versions"][-1]
    assert refs["adopted_version_id"] == v["id"]
    assert [(f["idx"], f["purpose"]) for f in v["files"]] == [(0, "composition"), (1, "light")]
    sid = _shot(client, "1-04")["id"]
    v = client.delete(f"{V1}/shots/{sid}/refs/0").json()["versions"][-1]
    assert [(f["idx"], f["purpose"]) for f in v["files"]] == [(0, "light")]

    board = _style(client, _png(3)).json()
    assert board["slot"] == "style_board" and board["owner_type"] == "series"
    assert [f["purpose"] for f in board["versions"][-1]["files"]] == ["style"]
    gone = client.delete(f"{V1}/series/demo/style-board/0").json()
    assert gone["versions"][-1]["files"] == []


def test_they_refuse(client: TestClient) -> None:
    assert _code(_shot_ref(client, "1-04", "face", _png(1))) == "invalid_purpose"
    assert _code(_shot_ref(client, "1-08", "pose", _png(1))) == "no_keyframe"  # continuous
    assert _code(_shot_ref(client, "1-04", "pose", b"nope")) == "not_an_image"
    missing = client.post(
        f"{V1}/shots/nope/refs", files={"file": ("x.png", _png(1))}, data={"purpose": "pose"}
    )
    assert missing.status_code == 404
    for i in range(4):
        assert _shot_ref(client, "1-04", "pose", _png(i)).status_code == 200
        assert _style(client, _png(i)).status_code == 200
    assert _code(_shot_ref(client, "1-04", "pose", _png(9))) == "too_many_refs"
    assert _code(_style(client, _png(9))) == "too_many_refs"
    assert _style(client, _png(1), series="nope").status_code == 404
    assert _code(client.delete(f"{V1}/series/demo/style-board/7")) == "ref_not_found"


def test_a_keyframe_sends_assets_then_the_shot_then_the_look(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kf, "ref_limit", lambda *_: None)
    first = _keyframe(client, "1-06")["versions"][-1]["payload"]["refs"]
    n = len(first)
    _style(client, _png(3)).raise_for_status()
    shot_refs = _shot_ref(client, "1-06", "composition", _png(2)).json()
    _add(client, "linwan", "face", _png(1)).raise_for_status()
    product = _keyframe(client, "1-06")
    v = product["versions"][-1]
    assert v["payload"]["refs"] == [*first, "林晚·正脸", "镜头参考·构图", "风格板"]
    sent = _prompt(client, v)
    assert f"参考图 {n + 2}：镜头参考（构图）；参考图 {n + 3}：风格板。" in sent
    assert f"参考图 {n + 2} 只参考构图，里面的人和东西不照搬" in sent
    assert f"参考图 {n + 3} 只参考画面风格（色调、质感、光影），里面的人和东西不照搬。" in sent
    deps = {
        d.upstream_product_id for d in _rows(client, Dependency, Dependency.version_id == v["id"])
    }
    assert shot_refs["id"] in deps
    # Another picture on the board: the keyframe follows an older one.
    look = _style(client, _png(4)).json()
    assert look["id"] in deps
    assert client.get(f"{V1}/products/{product['id']}").json()["status"] == "stale"
    # A model taking one more than the main pictures: her 正脸; the shot's and the board's are
    # left out without being called missing.
    monkeypatch.setattr(kf, "ref_limit", lambda *_: n + 1)
    v = _keyframe(client, "1-06")["versions"][-1]
    assert v["payload"]["refs"] == [*first, "林晚·正脸"]
    missing = _prompt(client, v).split("[没传的参考]", 1)[-1].strip().split("（", 1)[0]
    assert not {"镜头参考", "风格板"} & set(missing.split("、"))


def test_a_shots_pictures_are_its_own(client: TestClient) -> None:
    """1-04's pictures stay out of 1-06's keyframe."""
    _shot_ref(client, "1-04", "pose", _png(1)).raise_for_status()
    refs = _keyframe(client, "1-06")["versions"][-1]["payload"]["refs"]
    assert not any(r.startswith("镜头参考") for r in refs)

"""连续性账本 (M6 step 2): worked out from the plan, the contract, the top view and the assets;
what a shot does not say is carried from its scene's earlier shots, a new scene starts over."""

from __future__ import annotations

from typing import Any

from drama_series_agent.shots import ledger

KINDS = {
    "lin": "character",
    "zhou": "character",
    "umbrella": "prop",
    "note": "prop",
    "phone": "text",
}
NAMES = {
    "lin": "林晚",
    "zhou": "周屿",
    "umbrella": "红色长柄伞",
    "note": "黄色便利贴",
    "phone": "手机屏幕",
}
PROPS = {"umbrella": ["红色长柄伞", "红伞"], "note": ["黄色便利贴"]}
DESC = {"lin": "二十多岁，短发，米色针织衫，牛仔裤", "zhou": "高个子，深色风衣"}
TEXTS = {"phone": "23:52 周屿：到楼下了", "note": "楼下便利店，等你到十二点。"}


def _shot(
    sid: str,
    scene: str = "s1",
    refs: list[str] | None = None,
    start: list[dict[str, str]] | None = None,
    end: list[dict[str, str]] | None = None,
    props: list[dict[str, str]] | None = None,
    blocking: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": sid,
        "scene_id": scene,
        "asset_ids": refs or [],
        "blocking": blocking or [],
        "contract": {
            "kind": "performance",
            "beats": 1,
            "start": start or [],
            "end": end or [],
            "props": props or [],
            "delivery": {},
        },
    }


def _build(shot: dict[str, Any], shots: list[dict[str, Any]], time: str | None = "night") -> Any:
    return ledger.build(
        shot,
        shot["contract"],
        shots,
        kinds=KINDS,
        names=NAMES,
        prop_names=PROPS,
        descriptions=DESC,
        texts=TEXTS,
        time_of_day=time,
    )


def test_position_and_depth_come_from_the_top_view_as_the_camera_sees_it() -> None:
    shot = _shot(
        "a",
        refs=["lin", "zhou"],
        blocking=[
            {"id": "lin", "kind": "character", "label": "林晚", "x": 0.8, "y": 0.9},
            {"id": "zhou", "kind": "character", "label": "周屿", "x": 0.2, "y": 0.2},
            {"id": "camera", "kind": "camera", "label": "", "x": 0.5, "y": 1.0},
        ],
    )
    people = {c["asset_id"]: c for c in _build(shot, [shot])["characters"]}
    assert (people["lin"]["position"], people["lin"]["depth"]) == ("right", "near")
    assert (people["zhou"]["position"], people["zhou"]["depth"]) == ("left", "far")


def test_the_shot_says_what_is_in_hand_where_they_face_and_what_they_wear() -> None:
    shot = _shot(
        "a",
        refs=["lin", "umbrella"],
        start=[{"subject": "林晚", "state": "站在门口，朝门外，右手握着红伞，没穿外套"}],
    )
    (lin,) = _build(shot, [shot])["characters"]
    assert lin["holding"] == ["umbrella"]
    assert lin["holding_names"] == ["红色长柄伞"]
    assert lin["holding_from"] is None
    assert lin["facing"] == "朝门外"
    assert lin["outfit"] == "没穿外套"
    assert lin["outfit_from"] is None


def test_a_prop_whose_state_puts_it_in_a_hand_is_held() -> None:
    shot = _shot(
        "a", refs=["lin", "umbrella"], props=[{"asset_id": "umbrella", "state": "在林晚手里"}]
    )
    (lin,) = _build(shot, [shot])["characters"]
    assert lin["holding"] == ["umbrella"]


def test_what_a_shot_does_not_say_is_carried_from_the_scene() -> None:
    one = _shot(
        "a",
        refs=["lin", "umbrella"],
        end=[{"subject": "林晚", "state": "右手拎着红伞，外套搭在臂弯"}],
    )
    two = _shot("b", refs=["lin"])
    (lin,) = _build(two, [one, two])["characters"]
    assert lin["holding"] == ["umbrella"]
    assert lin["holding_from"] == "a"
    assert lin["outfit"] == "外套搭在臂弯"
    assert lin["outfit_from"] == "a"
    assert ledger.sources(_build(two, [one, two])) == ["a"]
    assert ledger.carried(_build(two, [one, two])) == [
        "林晚手里还拿着：红色长柄伞",
        "林晚的穿着：外套搭在臂弯",
    ]


def test_the_shot_own_start_wins_over_the_scene() -> None:
    one = _shot("a", refs=["lin"], end=[{"subject": "林晚", "state": "右手拎着红伞"}])
    two = _shot("b", refs=["lin"], start=[{"subject": "林晚", "state": "两手空着，靠在墙上"}])
    (lin,) = _build(two, [one, two])["characters"]
    assert lin["holding"] == []
    assert lin["holding_from"] is None


def test_a_new_scene_starts_over_and_the_description_gives_the_clothes() -> None:
    one = _shot("a", refs=["lin"], end=[{"subject": "林晚", "state": "右手拎着红伞，外套搭在臂弯"}])
    two = _shot("b", scene="s2", refs=["lin"])
    (lin,) = _build(two, [one, two])["characters"]
    assert lin["holding"] == []
    assert lin["outfit"] == "米色针织衫，牛仔裤"
    assert lin["outfit_from"] is None
    assert ledger.carried(_build(two, [one, two])) == []


def test_only_the_people_the_shot_films_are_listed() -> None:
    shot = _shot("a", refs=["lin", "umbrella"])
    assert [c["asset_id"] for c in _build(shot, [shot])["characters"]] == ["lin"]


def test_props_keep_their_state_and_where_it_came_from() -> None:
    shot = _shot("b", refs=["note"], props=[{"asset_id": "note", "state": "贴在伞柄上，边角湿"}])
    contract = {**shot["contract"], "props_from": {"note": "a"}}
    out = ledger.build(
        shot,
        contract,
        [shot],
        kinds=KINDS,
        names=NAMES,
        prop_names=PROPS,
        descriptions=DESC,
        texts=TEXTS,
        time_of_day="night",
    )
    assert out["props"] == [
        {"asset_id": "note", "name": "黄色便利贴", "state": "贴在伞柄上，边角湿", "from_shot": "a"}
    ]


def test_the_clock_is_read_off_the_screen_and_carried_to_the_next_shot() -> None:
    one = _shot("a", refs=["lin", "phone"])
    two = _shot("b", refs=["lin"])
    three = _shot("c", scene="s2", refs=["lin"])
    assert _build(one, [one, two])["time"] == {
        "time_of_day": "night",
        "clock": "23:52",
        "clock_from": None,
    }
    assert _build(two, [one, two])["time"]["clock"] == "23:52"
    assert _build(two, [one, two])["time"]["clock_from"] == "a"
    assert _build(three, [one, two, three], time="day")["time"] == {
        "time_of_day": "day",
        "clock": None,
        "clock_from": None,
    }


def test_clock_and_outfit_rules() -> None:
    assert ledger.clock_in("现在 9：05 了") == "09:05"
    assert ledger.clock_in("房间号 1205") is None
    assert ledger.outfit_in("短发，二十多岁") is None
    assert ledger.holding_in("看着手里的红伞", PROPS) == []  # no hand verb: looking, not holding

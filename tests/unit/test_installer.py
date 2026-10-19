from __future__ import annotations

from typing import Any

import pytest

from drama_series_agent.setup.installer import (
    FAKE_BPS,
    FakeRunner,
    InstallEnv,
    InstallError,
    Transfer,
    confirm_reasons,
    install_order,
    size_bytes,
    work_s,
)
from drama_series_agent.setup.manifest import Item, Manifest, Message, Step, load_manifest


@pytest.fixture(autouse=True)
def _no_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "0")


ENV = InstallEnv(os="windows", mirror="auto", models="D:/M", envs="C:/e", comfy="D:/ComfyUI")


transfers: list[Transfer] = []


async def _run(runner: FakeRunner, item: Item) -> tuple[list[float], Exception | None]:
    seen: list[float] = []
    transfers.clear()

    async def progress(pct: float, transfer: Transfer | None = None) -> None:
        seen.append(pct)
        if transfer is not None:
            transfers.append(transfer)

    async def log(level: str, code: str, params: dict[str, Any]) -> None:
        return None

    try:
        await runner.install(item, ENV, log, progress)
    except InstallError as exc:
        return seen, exc
    return seen, None


def _items(os: str = "windows") -> dict[str, Item]:
    return {x.id: x for x in load_manifest().for_platform(os)}  # type: ignore[arg-type]


async def test_fake_runner_pace() -> None:
    items = _items()
    assert await _run(FakeRunner(), items["ffmpeg"]) == ([34, 68], None)
    assert (await _run(FakeRunner(), items["w_h3"]))[0] == [10, 20, 30, 40, 50, 60, 70, 80, 90, 99]
    # Downloads show bytes at the demo's speed, and a moment of checking at the end.
    total = 49_300_000_000
    assert transfers[0] == Transfer(done=total // 10, total=total, speed=FAKE_BPS)
    assert transfers[-1] == Transfer(done=total, total=total, speed=None, verifying=True)
    seen, err = await _run(FakeRunner(), items["sage"])
    assert seen == [34, 60]
    assert isinstance(err, InstallError) and err.message() == Message(code="no_wheel")
    assert (await _run(FakeRunner(failing=None), items["sage"]))[1] is None


def test_what_each_item_costs() -> None:
    """For the estimates: download size from the manifest, the other steps by rule of thumb."""
    items = _items()
    assert (size_bytes(items["w_h3"]), work_s(items["w_h3"])) == (49_300_000_000, 0)
    assert (size_bytes(items["node_vhs"]), work_s(items["node_vhs"])) == (None, 80)  # clone, pip
    assert (size_bytes(items["ffmpeg"]), work_s(items["ffmpeg"])) == (None, 60)


def test_install_order_puts_dependencies_first() -> None:
    items = list(_items().values())
    order = install_order(items, ["node_vhs", "sage", "comfy", "torch", "ffmpeg"])
    assert order.index("torch") < order.index("comfy") < order.index("node_vhs")
    assert order.index("torch") < order.index("sage")
    assert sorted(order) == sorted(["node_vhs", "sage", "comfy", "torch", "ffmpeg"])
    assert install_order(items, ["nope"]) == []


def test_confirm_reasons() -> None:
    win, mac, linux = _items("windows"), _items("macos"), _items("linux")
    assert confirm_reasons([win["git"], win["ffmpeg"], win["llmsrv"]], "windows") == [
        Message(code="admin", params={"item": "git"})
    ]
    assert confirm_reasons([mac["git"], mac["ffmpeg"]], "macos") == []
    # apt always goes through sudo.
    assert [m.params["item"] for m in confirm_reasons([linux["ffmpeg"]], "linux")] == ["ffmpeg"]
    big = win["w_h3"].model_copy(update={"size_gb": 24.0})
    small = win["w_tts"].model_copy(update={"size_gb": 4.0})
    assert confirm_reasons([big, small], "windows") == [
        Message(code="large_download", params={"item": "w_h3", "gb": 24.0})
    ]


def test_needs_admin_only_with_a_package_for_this_manager() -> None:
    step = Step.model_validate({"type": "pkg", "brew": "uv", "admin": ["winget"]})
    assert not step.needs_admin("windows")  # no winget package named
    assert not Step.model_validate({"type": "script", "admin": ["apt"]}).needs_admin("linux")
    m = Manifest.model_validate(
        {
            "items": [
                {
                    "id": "x",
                    "group": "rt",
                    "name": {"zh": "x", "en": "x"},
                    "detect": {"type": "command", "cmd": "x"},
                    "install": [{"type": "pkg", "winget": "X.X", "admin": ["winget"]}],
                }
            ]
        }
    )
    assert m.items[0].install[0].needs_admin("windows")
    with pytest.raises(ValueError, match="pacman"):
        Step.model_validate({"type": "pkg", "admin": ["pacman"]})

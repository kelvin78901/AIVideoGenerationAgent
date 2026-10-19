"""ComfyUI-Manager 4's snapshot API, as comfyui_manager 4.2.2 serves it (step 5c)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from drama_series_agent.setup.comfy import ComfyEnvInfo, NodePack
from drama_series_agent.setup.manifest import Message
from drama_series_agent.setup.snapshots import (
    FakeSnapshots,
    ManagerSnapshots,
    SnapshotError,
    env_diff,
    prepare_restore,
    restore_check,
)

URL = "http://127.0.0.1:8188"


class FakeManager:
    """Manager's /v2/snapshot/* routes, with its guards (no form posts; restore needs a level)."""

    def __init__(self, *, restore_allowed: bool = True) -> None:
        self.names = ["2026-10-16_16-20-04_snapshot"]
        self.restore_allowed = restore_allowed
        self.restored: list[str] = []
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if method == "POST" and request.headers.get("content-type", "").startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data", "text/plain")
        ):
            return httpx.Response(400)
        if (method, path) == ("GET", "/v2/snapshot/getlist"):
            return httpx.Response(200, json={"items": sorted(self.names, reverse=True)})
        if (method, path) == ("POST", "/v2/snapshot/save"):
            self.names.append("2026-10-18_21-00-00_snapshot")
            return httpx.Response(200)
        if (method, path) == ("POST", "/v2/snapshot/restore"):
            if not self.restore_allowed:
                return httpx.Response(403)
            target = request.url.params["target"]
            if target not in self.names:
                return httpx.Response(400)
            self.restored.append(target)
            return httpx.Response(200)
        return httpx.Response(404)


async def test_save_finds_the_new_name_and_restore_schedules_it() -> None:
    manager = FakeManager()
    client = ManagerSnapshots(URL, httpx.MockTransport(manager))
    name = await client.save()
    assert name == "2026-10-18_21-00-00_snapshot"
    saves = [r for r in manager.requests if r.url.path == "/v2/snapshot/save"]
    assert len(saves) == 1 and saves[0].content == b""  # no body, so no form content type
    await client.restore(name)
    assert manager.restored == [name]


async def test_what_goes_wrong() -> None:
    def no_manager(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(SnapshotError) as err:
        await ManagerSnapshots(URL, httpx.MockTransport(no_manager)).save()
    assert err.value.reason == "no_manager"

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(SnapshotError) as err:
        await ManagerSnapshots(URL, httpx.MockTransport(down)).save()
    assert err.value.reason == "not_running"

    locked = ManagerSnapshots(URL, httpx.MockTransport(FakeManager(restore_allowed=False)))
    with pytest.raises(SnapshotError) as err:
        await locked.restore("2026-10-16_16-20-04_snapshot")
    assert err.value.reason == "forbidden"

    with pytest.raises(SnapshotError) as err:  # Manager answered but nothing new appeared
        manager = FakeManager()
        manager.names = []

        def silent(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v2/snapshot/save":
                return httpx.Response(200)
            return manager(request)

        await ManagerSnapshots(URL, httpx.MockTransport(silent)).save()
    assert err.value.reason == "failed"


async def test_fake_snapshots() -> None:
    fake = FakeSnapshots()
    a, b = await fake.save(), await fake.save()
    assert a != b and a.endswith("_snapshot")
    await fake.restore(a)
    assert fake.restored == [a]
    with pytest.raises(SnapshotError):
        await FakeSnapshots(fail="not_running").save()


def _env(comfy: str = "abcdef0123", **packs: tuple[str | None, str | None]) -> ComfyEnvInfo:
    return ComfyEnvInfo(
        comfyui_version="0.3.40",
        comfyui_commit=comfy,
        python="3.12.9",
        torch="2.7.1+cu128",
        node_packs=[
            NodePack(name=n, source="git", commit=c, version=v) for n, (c, v) in packs.items()
        ],
    )


def test_env_diff_is_what_a_rollback_restores() -> None:
    then = _env(VHS=("4d907be" + "0" * 33, None), KJ=(None, "1.1.0"))
    now = _env("1234567890", KJ=(None, "1.2.0"), FlashVSR=("8877fdd" + "0" * 33, None)).model_copy(
        update={"torch": "2.12.1+cu130"}
    )  # Manager does not downgrade pip packages
    assert env_diff(now, then) == [
        Message(code="comfyui", params={"now": "1234567", "then": "abcdef0"}),
        Message(code="pack_extra", params={"name": "FlashVSR"}),
        Message(code="pack_missing", params={"name": "VHS"}),
        Message(code="pack_version", params={"name": "KJ", "now": "1.2.0", "then": "1.1.0"}),
    ]
    assert env_diff(then, then) == []


def test_restore_check() -> None:
    then = _env(VHS=("a" * 40, None))
    after_install = _env(VHS=("a" * 40, None), FlashVSR=("b" * 40, None))
    # Back at the snapshot: done, whatever it was at the request.
    assert restore_check("h-then", then, "h-installed", then) == ("done", [])
    # As at the request: ComfyUI not restarted yet.
    assert restore_check("h-installed", after_install, "h-installed", then) == ("pending", [])
    # Changed, not back: what still differs.
    state, diff = restore_check("h-other", after_install, "h-installed", then)
    assert state == "incomplete" and [m.code for m in diff] == ["pack_extra"]


def test_restore_finds_the_disabled_folder_in_place(tmp_path: Path) -> None:
    """Manager moves node packs the snapshot lacks into custom_nodes/.disabled; without it the
    move turns into copy + delete, which stops at git's read-only files on Windows."""
    (tmp_path / "custom_nodes").mkdir()
    prepare_restore(str(tmp_path))
    prepare_restore(str(tmp_path))  # already there: fine
    assert (tmp_path / "custom_nodes" / ".disabled").is_dir()

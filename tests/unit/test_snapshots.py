"""ComfyUI-Manager 4's snapshot API, as comfyui_manager 4.2.2 serves it (step 5c)."""

from __future__ import annotations

import httpx
import pytest

from drama_series_agent.setup.snapshots import FakeSnapshots, ManagerSnapshots, SnapshotError

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

"""The workflow library (SPEC 6.4.2, 6.4.4, 6.4.6): folders on disk, a row each in
``comfy_workflow``, a local model each in the config.

- **Folders**: the repo's ``workflows/<slug>/`` (platform recommended, ``selfhost/`` is the
  upstream's old format and is skipped) and the user's ``~/.drama-studio/workflows/<slug>/``
  (imported). ``sync()`` reads both at startup: new folders get a row, rows without a folder go.
- **Rows** keep what the library adds: tier, bindings with their state (DramaStudio node /
  confirmed / guessed), the last check and trial, the file hash they were made on, and where an
  import came from. A user workflow whose file changed since is shown ``file_changed`` and loses
  我的工作流 until a trial passes again.
- **Config**: every workflow not already in ``providers.yaml`` becomes local model
  ``comfy/<slug>`` in the components that serve its kind (a repo workflow a ``providers.yaml``
  model names, like ``comfy/h3`` → ``h3-i2v``, is that model) (``core.config.set_library``); the
  registry gets its spec. Unverified workflows only run when picked by hand.

Tier rules (SPEC 6.4.4; the M1 contract): recommended cannot change; 我的工作流 needs every
binding confirmed, a passed trial and an unchanged file; editing the bindings demotes it.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from loguru import logger
from sqlmodel import select

from drama_series_agent.core.config import (
    Library,
    LocalModel,
    get_config,
    load_config,
    set_library,
)
from drama_series_agent.core.db import Database
from drama_series_agent.core.jobs import JobContext
from drama_series_agent.core.models_db import ComfyWorkflowRow, utcnow
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.modelhub.registry import Registry, local_spec
from drama_series_agent.modelhub.workflows import (
    WORKFLOWS_DIR,
    Binding,
    Workflow,
    WorkflowError,
    has_workflow,
    load_workflow,
    user_workflows_dir,
)
from drama_series_agent.setup.manifest import Message
from drama_series_agent.setup.schema import NodePackSource
from drama_series_agent.setup.service import NoComfy, SetupBusy, SnapshotFailed
from drama_series_agent.spec.dims import ASPECTS, dims
from drama_series_agent.wflib.comfy import ComfyAccess, ComfyUnavailable, DemoComfy
from drama_series_agent.wflib.convert import ConvertError, is_ui_format, ui_to_api
from drama_series_agent.wflib.guess import (
    DRAMASTUDIO_PREFIX,
    guess_bindings,
    is_api_format,
    kind_of,
    model_files,
    nodes_of,
    uses_dramastudio,
)
from drama_series_agent.wflib.schema import (
    BindingOut,
    CapsOut,
    CheckOut,
    ClassCount,
    ComfyWorkflowFile,
    DepsInstalled,
    ImportIn,
    MissingModel,
    MissingPack,
    NodeOut,
    Tier,
    TrialOut,
    WorkflowOut,
)

if TYPE_CHECKING:
    from drama_series_agent.core.jobs import JobQueue
    from drama_series_agent.modelhub.router import Router
    from drama_series_agent.setup.service import SetupService

SKIP_REPO = frozenset({"selfhost"})
# Which components a workflow of each kind serves when providers.yaml does not place it.
KIND_COMPONENTS: dict[str, tuple[str, ...]] = {
    "video": ("vid",),
    "image": ("kf", "img"),
    "upscale": ("up",),
    "lipsync": ("lip",),
}
BOARD_PREFIX = "DramaStudio 素材板"  # the studio's own asset board in ComfyUI's list (M9)


class LibraryError(Exception):
    """A request the library refuses; the route turns it into ``ApiError(status, code)``."""

    def __init__(self, status: int, code: str, **params: Any) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.params = params


def _name_of(path: str) -> str:
    """「我的/雨夜氛围-ltx2.json」 → 「雨夜氛围-ltx2」."""
    return re.sub(r"\.json$", "", path.replace("\\", "/").rsplit("/", 1)[-1], flags=re.I)


def _slug_base(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workflow"


class WorkflowLibrary:
    def __init__(
        self,
        db: Database,
        registry: Registry,
        comfy: Callable[[], ComfyAccess],
        *,
        repo_dir: Path = WORKFLOWS_DIR,
        user_dir: Callable[[], Path] = user_workflows_dir,
        setup: SetupService | None = None,
        jobs: JobQueue | None = None,
        router: Router | None = None,
    ) -> None:
        self.db = db
        self.registry = registry
        self.comfy = comfy
        self.repo_dir = repo_dir
        self.user_dir = user_dir
        self.setup = setup
        self.jobs = jobs
        self.router = router
        # The snapshot taken before the last node-pack install: a workflow that worked before
        # it and is broken after points back to it (SPEC 6.4.5).
        self.install_snapshot: str | None = None
        if jobs is not None:
            jobs.register(WORKFLOW_TRIAL, self._run_trial)

    # ------------------------------------------------------------------ folders → rows

    def _folders(self) -> dict[str, tuple[str, Path, Workflow]]:
        found: dict[str, tuple[str, Path, Workflow]] = {}
        for source, root in (("repo", self.repo_dir), ("user", self.user_dir())):
            if not root.is_dir():
                continue
            for folder in sorted(root.iterdir()):
                slug = folder.name
                if slug in found or slug in SKIP_REPO or not has_workflow(slug, root):
                    continue
                try:
                    found[slug] = (source, root, load_workflow(slug, root))
                except (WorkflowError, ValueError) as exc:
                    logger.warning("workflow {} skipped: {}", slug, exc)
        return found

    async def sync(self) -> None:
        """Read the folders into the table and the config (startup, after an import)."""
        found = self._folders()
        async with self.db.session() as s:
            rows = {r.slug: r for r in (await s.exec(select(ComfyWorkflowRow))).all()}
            for slug, (source, root, wf) in found.items():
                row = rows.get(slug)
                if row is None:
                    s.add(self._new_row(source, root, wf))
                elif source == "repo":  # the repo's files are the truth for its workflows
                    if wf.sha256 != row.file_sha256:  # a new graph: the old check says nothing
                        row.check_json = None
                        row.deps_json = {
                            **row.deps_json,
                            "models": [m.model_dump() for m in wf.meta.models],
                        }
                    row.model_key = _repo_key(wf.slug)
                    row.file_sha256 = wf.sha256
                    row.bindings_json = _meta_bindings(wf)
                    row.caps_json = dict(wf.meta.caps)
                    row.name_json = dict(wf.meta.name)
                    row.kind = wf.meta.kind
                    row.tier = wf.meta.tier
                    s.add(row)
                elif wf.sha256 != row.file_sha256 and row.tier == "mine":
                    row.tier = "unverified"  # SPEC 6.4.5: a changed file is a new workflow
                    row.updated_at = utcnow()
                    s.add(row)
            for slug, row in rows.items():
                if slug not in found:
                    await s.delete(row)
            await s.commit()
        await self._publish()

    def _new_row(self, source: str, root: Path, wf: Workflow) -> ComfyWorkflowRow:
        extra = wf.meta.model_extra or {}
        pending = {(p.get("slot"), p.get("index")) for p in extra.get("pending") or []}
        bindings = _meta_bindings(wf)
        for b in bindings:
            if (b["slot"], b["index"]) in pending:
                b["state"] = "guessed"
        return ComfyWorkflowRow(
            id=f"wf_{wf.slug}",
            slug=wf.slug,
            model_key=_repo_key(wf.slug) if source == "repo" else f"comfy/{wf.slug}",
            name_json=dict(wf.meta.name),
            kind=wf.meta.kind,
            tier=wf.meta.tier if source == "repo" else "unverified",
            source=source,
            dir=str(root / wf.slug),
            origin=extra.get("origin"),
            file_sha256=wf.sha256,
            bindings_json=bindings,
            deps_json={"models": [m.model_dump() for m in wf.meta.models], "packs": []},
            caps_json=dict(wf.meta.caps),
        )

    async def rows(self) -> list[ComfyWorkflowRow]:
        async with self.db.session() as s:
            return list((await s.exec(select(ComfyWorkflowRow))).all())

    async def _publish(self) -> None:
        """The library into the config and the registry."""
        rows = await self.rows()
        factory = {m.key for m in load_config().providers.local_models}
        models: list[LocalModel] = []
        serves: list[tuple[str, str]] = []
        for row in rows:
            if row.model_key in factory:
                continue  # providers.yaml places it already
            local = LocalModel(
                key=row.model_key,
                kind=row.kind,
                display=_name(row),
                runtime="comfyui",
                workflow=row.slug,
                workflow_root=str(Path(row.dir).parent) if row.source == "user" else None,
                tier=row.tier,
                needs=["comfy"],
                caps=dict(row.caps_json),
            )
            models.append(local)
            serves += [(c, row.model_key) for c in KIND_COMPONENTS.get(row.kind, ())]
            self.registry.add_spec(local_spec(local))
        set_library(
            Library(
                models=tuple(models),
                serves=tuple(serves),
                mine=frozenset(r.model_key for r in rows if r.tier == "mine"),
                unverified=frozenset(r.model_key for r in rows if r.tier == "unverified"),
            )
        )

    # ------------------------------------------------------------------ read

    async def _row(self, workflow_id: str) -> ComfyWorkflowRow:
        async with self.db.session() as s:
            row = await s.get(ComfyWorkflowRow, workflow_id)
        if row is None:
            raise LibraryError(404, "workflow_not_found", id=workflow_id)
        return row

    def load(self, row: ComfyWorkflowRow) -> Workflow | None:
        try:
            return load_workflow(row.slug, Path(row.dir).parent)
        except (WorkflowError, ValueError, OSError):
            return None

    def out(self, row: ComfyWorkflowRow) -> WorkflowOut:
        wf = self.load(row)
        graph = wf.graph if wf is not None else {}
        cfg_components = get_config().components.components
        components = [c.id for c in cfg_components if row.model_key in c.local] or list(
            KIND_COMPONENTS.get(row.kind, ())
        )
        caps = row.caps_json
        sizes = caps.get("sizes")
        durations = caps.get("duration_s")
        refs = sum(1 for b in row.bindings_json if b.get("slot") == "ref_image")
        return WorkflowOut(
            id=row.id,
            slug=row.slug,
            model_key=row.model_key,
            name=_name(row),
            tier=row.tier,
            source=row.source,
            origin=row.origin,
            components=components,
            caps=CapsOut(
                aspects=sorted(sizes) if isinstance(sizes, dict) else list(caps.get("aspects", [])),
                max_seconds=max(durations) if isinstance(durations, list) and durations else None,
                refs=refs or None,
                vram_gb=caps.get("vram_gb"),
            ),
            file_sha256=row.file_sha256,
            file_changed=wf is not None and wf.sha256 != row.file_sha256,
            uses_dramastudio_nodes=uses_dramastudio(graph),
            bindings=[BindingOut.model_validate(b) for b in row.bindings_json],
            nodes=[NodeOut.model_validate(n) for n in nodes_of(graph)],
            check=CheckOut.model_validate(row.check_json) if row.check_json else None,
            trial=TrialOut.model_validate(row.trial_json) if row.trial_json else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def all(self) -> list[WorkflowOut]:
        order = {"recommended": 0, "mine": 1, "unverified": 2}
        rows = sorted(await self.rows(), key=lambda r: (order.get(r.tier, 3), r.created_at, r.id))
        return [self.out(r) for r in rows]

    async def get(self, workflow_id: str) -> WorkflowOut:
        return self.out(await self._row(workflow_id))

    # ------------------------------------------------------------------ change

    async def _save(self, row: ComfyWorkflowRow) -> WorkflowOut:
        row.updated_at = utcnow()
        async with self.db.session() as s:
            s.add(row)
            await s.commit()
            await s.refresh(row)
        await self._publish()
        return self.out(row)

    async def set_tier(self, workflow_id: str, tier: Tier) -> WorkflowOut:
        row = await self._row(workflow_id)
        if tier == "recommended" or row.source == "repo":
            raise LibraryError(409, "workflow_tier_repo")
        if tier == "mine":
            pending = _pending(row)
            if pending:
                raise LibraryError(409, "workflow_bindings_pending", count=pending)
            wf = self.load(row)
            trial = row.trial_json or {}
            if trial.get("status") != "passed" or wf is None or wf.sha256 != row.file_sha256:
                raise LibraryError(409, "workflow_needs_trial")
        row.tier = tier
        return await self._save(row)

    async def put_bindings(self, workflow_id: str, bindings: list[BindingOut]) -> WorkflowOut:
        """Saving confirms them all (the page sends only after the user said yes)."""
        row = await self._row(workflow_id)
        wf = self.load(row)
        if wf is None:
            raise LibraryError(409, "workflow_invalid")
        if uses_dramastudio(wf.graph):
            raise LibraryError(409, "workflow_dramastudio_bindings")
        if row.source == "repo":
            raise LibraryError(409, "workflow_tier_repo")
        classes = {_title(n): str(n["class_type"]) for n in wf.graph.values()}
        for b in bindings:
            if b.node_title not in classes:
                raise LibraryError(422, "workflow_unknown_node", title=b.node_title)
        saved = [
            b.model_copy(update={"state": "confirmed", "node_class": classes[b.node_title]})
            for b in bindings
        ]
        try:
            _write_meta(Path(row.dir), wf.graph, row, saved)
        except WorkflowError as exc:
            raise LibraryError(422, "workflow_binding_invalid", reason=str(exc)) from None
        row.bindings_json = [b.model_dump() for b in saved]
        if row.tier == "mine":
            row.tier = "unverified"  # a different binding is a different workflow
        return await self._save(row)

    # ------------------------------------------------------------------ import

    async def comfy_files(self) -> list[ComfyWorkflowFile]:
        try:
            files = await self.comfy().files()
        except ComfyUnavailable:
            raise LibraryError(409, "comfy_not_running") from None
        imported = {r.origin: r.id for r in await self.rows() if r.origin}
        return [
            ComfyWorkflowFile(
                path=f.path,
                modified_at=f.modified_at,
                imported_as=imported.get(f.path),
                board=_name_of(f.path).startswith(BOARD_PREFIX),
            )
            for f in files
        ]

    async def import_(self, body: ImportIn) -> WorkflowOut:
        rows = await self.rows()
        if body.comfy_path:
            origin = body.comfy_path
            if _name_of(origin).startswith(BOARD_PREFIX):
                raise LibraryError(409, "workflow_is_board")
            try:
                data: dict[str, Any] = await self.comfy().read(origin)
            except ComfyUnavailable:
                raise LibraryError(409, "comfy_not_running") from None
        elif body.file_name and body.workflow is not None:
            origin, data = body.file_name, body.workflow
        else:
            raise LibraryError(422, "invalid_request")
        same = next((r for r in rows if r.origin == origin), None)
        if same is not None:
            raise LibraryError(409, "workflow_imported", id=same.id)
        if ((data.get("extra") or {}).get("dramastudio") or {}).get("board"):
            raise LibraryError(409, "workflow_is_board")
        if is_ui_format(data):
            try:
                data = ui_to_api(data, await self.comfy().object_info())
            except ComfyUnavailable:
                raise LibraryError(409, "comfy_not_running") from None
            except ConvertError as exc:
                raise LibraryError(409, exc.code, classes=", ".join(exc.classes)) from None
        if not is_api_format(data):
            raise LibraryError(422, "workflow_not_api")
        graph, guessed = guess_bindings(data)
        slug = self._free_slug(_slug_base(_name_of(origin)), {r.slug for r in rows})
        name = _name_of(origin)
        folder = self.user_dir() / slug
        folder.mkdir(parents=True, exist_ok=True)
        row = ComfyWorkflowRow(
            id=f"wf_{slug}",
            slug=slug,
            model_key=f"comfy/{slug}",
            name_json={"zh": name, "en": name},
            kind=kind_of(guessed),
            tier="unverified",
            source="user",
            dir=str(folder),
            origin=origin,
            file_sha256="",
            bindings_json=[],
            deps_json={"models": model_files(graph), "packs": []},
            caps_json={},
        )
        bindings = [BindingOut.model_validate(g.out()) for g in guessed]
        row.file_sha256 = _write_meta(folder, graph, row, bindings)
        row.bindings_json = [b.model_dump() for b in bindings]
        async with self.db.session() as s:
            s.add(row)
            await s.commit()
            await s.refresh(row)
        try:  # checked right away when ComfyUI answers (the page shows what is missing)
            access, info = await self._object_info()
            row.check_json = await self._checked(row, access, info)
        except LibraryError:
            pass
        return await self._save(row)

    # ------------------------------------------------------------------ health check

    async def _object_info(self) -> tuple[ComfyAccess, dict[str, Any]]:
        access = self.comfy()
        try:
            return access, await access.object_info()
        except ComfyUnavailable:
            raise LibraryError(409, "comfy_not_running") from None

    async def _checked(
        self, row: ComfyWorkflowRow, access: ComfyAccess, info: dict[str, Any]
    ) -> dict[str, Any]:
        """SPEC 6.4.4-1: node classes ComfyUI does not have (and the packs that provide them),
        model files its loaders do not list, bindings that no longer fit the graph."""
        problems: list[Message] = []
        wf = self.load(row)
        if wf is not None:
            graph = wf.graph
        else:
            problems.append(Message(code="binding_broken"))
            try:
                graph = json.loads((Path(row.dir) / "workflow.api.json").read_text("utf-8"))
            except (OSError, ValueError):
                graph = {}
        classes = sorted({str(n.get("class_type")) for n in graph.values()})
        missing = [c for c in classes if c not in info]
        packs, unknown = _packs_for(missing, await _node_map(access))
        problems += [Message(code="unknown_node", params={"class": c}) for c in unknown]
        models = _missing_models(graph, info, row.deps_json.get("models") or [])
        status = "broken" if problems else "missing" if packs or models else "ok"
        before = (row.check_json or {}).get("status")
        if status != "ok" and before == "ok" and self.install_snapshot:
            problems.append(
                Message(code="broke_after_install", params={"snapshot": self.install_snapshot})
            )
            status = "broken"
        return CheckOut(
            at=utcnow(),
            status=status,
            node_classes=ClassCount(found=len(classes) - len(missing), total=len(classes)),
            missing_packs=packs,
            missing_models=models,
            problems=problems,
        ).model_dump(mode="json")

    async def check(self, workflow_id: str) -> WorkflowOut:
        row = await self._row(workflow_id)
        access, info = await self._object_info()
        row.check_json = await self._checked(row, access, info)
        return await self._save(row)

    async def check_all(self) -> list[WorkflowOut]:
        access, info = await self._object_info()
        for row in await self.rows():
            row.check_json = await self._checked(row, access, info)
            row.updated_at = utcnow()
            async with self.db.session() as s:
                s.add(row)
                await s.commit()
        await self._publish()
        return await self.all()

    async def deps(self, workflow_id: str) -> list[Message]:
        """The change list installing what is missing would make (the 6.4.1 dialog)."""
        row = await self._row(workflow_id)
        check = CheckOut.model_validate(row.check_json) if row.check_json else None
        if check is None:
            return []
        out = [
            Message(
                code="comfy_change",
                params={
                    "item": p.name,
                    "action": "install",
                    **({"to": p.version} if p.version else {}),
                    **({"source": p.url} if p.url else {}),
                },
            )
            for p in check.missing_packs
        ]
        out += [
            Message(
                code="comfy_change",
                params={"item": f"{m.folder}/{m.name}", "action": "install", **_gb(m.size_bytes)},
            )
            for m in check.missing_models
        ]
        return out

    async def install_deps(self, workflow_id: str) -> DepsInstalled:
        """Approved: snapshot, then the missing node packs. Model files without a download
        address stay listed (the user puts them in place). A real ComfyUI loads new packs
        when it restarts; until then the check still shows them missing."""
        row = await self._row(workflow_id)
        check = CheckOut.model_validate(row.check_json) if row.check_json else None
        if self.setup is None or check is None or not check.missing_packs:
            raise LibraryError(409, "workflow_nothing_to_install")
        sources = [NodePackSource(name=p.name, url=p.url or "") for p in check.missing_packs]
        try:
            result = await self.setup.install_node_packs([s for s in sources if s.url])
        except NoComfy:
            raise LibraryError(409, "comfy_not_found") from None
        except SetupBusy:
            raise LibraryError(409, "setup_busy") from None
        except SnapshotFailed as exc:
            raise LibraryError(409, "comfy_snapshot_failed", reason=exc.reason) from None
        self.install_snapshot = result.snapshot.manager_name
        access = self.comfy()
        if isinstance(access, DemoComfy):
            access.add_classes(
                [c for p in check.missing_packs if p.name in result.installed for c in p.classes]
            )
        if not access.needs_restart:  # SPEC 6.4.5: every workflow checked after an install
            await self.check_all()
        return DepsInstalled(
            workflow=await self.get(workflow_id),
            packs=len(result.installed),
            models=0,
            snapshot=result.snapshot.manager_name,
            restart_required=access.needs_restart,
            failed=result.failed,
        )

    # ------------------------------------------------------------------ trial run

    async def trial(self, workflow_id: str) -> WorkflowOut:
        """SPEC 6.4.4-3: the sample inputs at the draft size and the shortest duration, on the
        GPU queue (a job; its progress is ``job.updated``)."""
        row = await self._row(workflow_id)
        if self.jobs is None:
            raise LibraryError(409, "workflow_trial_unavailable")
        if _pending(row):
            raise LibraryError(409, "workflow_bindings_pending", count=_pending(row))
        if (row.check_json or {}).get("status") != "ok":
            raise LibraryError(409, "workflow_check_failed")
        w, h, seconds = _trial_size(row)
        job = await self.jobs.enqueue(
            WORKFLOW_TRIAL,
            "gpu",
            {"workflow_id": row.id, "model_key": row.model_key},
            max_attempts=1,
        )
        row.trial_json = TrialOut(
            at=utcnow(), status="running", job_id=job.id, w=w, h=h, seconds=seconds
        ).model_dump(mode="json")
        return await self._save(row)

    async def _run_trial(self, ctx: JobContext) -> dict[str, Any]:
        row = await self._row(str(ctx.params["workflow_id"]))
        assert self.router is not None
        component = self.out(row).components[0] if self.out(row).components else "kf"
        w, h, seconds = _trial_size(row)
        kind = row.kind if row.kind in ("image", "video", "upscale", "lipsync") else "image"
        req = ModelRequest(
            kind=kind,
            prompt=TRIAL_PROMPT,
            seed=1,
            params={"width": w, "height": h, "duration_s": seconds, "n": 1, "trial": True},
        )
        call = CallContext(
            component_id=component,
            job_id=ctx.job.id,
            attempt=ctx.job.attempt,
            on_progress=ctx.progress,  # ComfyUI's sampler steps → job.updated
        )
        started = time.monotonic()
        trial = TrialOut(at=utcnow(), status="passed", job_id=ctx.job.id, w=w, h=h, seconds=seconds)
        try:
            await self.router.call(component, req, call, model=row.model_key, fallback=False)
            trial.duration_s = round(time.monotonic() - started, 1)
            wf = self.load(row)
            if wf is not None:
                row.file_sha256 = wf.sha256  # it passed on this file
        except ModelError as exc:
            trial.status = "failed"
            trial.error = Message(code=exc.code)
        row = await self._row(row.id)  # the bindings may have been saved meanwhile
        row.trial_json = trial.model_dump(mode="json")
        await self._save(row)
        return {"workflow_id": row.id, "status": trial.status}

    def _free_slug(self, base: str, taken: set[str]) -> str:
        taken = taken | {p.name for p in self.repo_dir.iterdir() if p.is_dir()}
        user = self.user_dir()
        if user.is_dir():
            taken |= {p.name for p in user.iterdir() if p.is_dir()}
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        return slug


def _repo_key(slug: str) -> str:
    """A repo workflow's model: the ``providers.yaml`` one that runs it, else ``comfy/<slug>``."""
    for m in load_config().providers.local_models:
        if m.runtime == "comfyui" and m.workflow == slug:
            return m.key
    return f"comfy/{slug}"


def _title(node: dict[str, Any]) -> str:
    title = (node.get("_meta") or {}).get("title")
    return title if isinstance(title, str) and title else str(node.get("class_type"))


def _name(row: ComfyWorkflowRow) -> str:
    return row.name_json.get("zh") or row.name_json.get("en") or row.slug


def _pending(row: ComfyWorkflowRow) -> int:
    return sum(1 for b in row.bindings_json if b.get("state") == "guessed")


def _meta_bindings(wf: Workflow) -> list[dict[str, Any]]:
    out = []
    for b in wf.meta.bindings:
        cls = str(wf.graph[wf.node_id(b.node)]["class_type"])
        state = "dramastudio" if cls.startswith(DRAMASTUDIO_PREFIX) else "confirmed"
        out.append(
            BindingOut(
                slot=b.slot, index=b.index, node_title=b.node, node_class=cls, field=b.field,
                state=state,
            ).model_dump()
        )  # fmt: skip
    return out


def _write_meta(
    folder: Path, graph: dict[str, Any], row: ComfyWorkflowRow, bindings: list[BindingOut]
) -> str:
    """Write ``workflow.api.json`` and ``workflow.yaml``; returns the graph's sha256.

    Only bindings the graph can take go into the yaml (a guess pointing at no input field is
    left for the user to fix); the guessed ones are listed under ``pending``.
    """
    usable: list[Binding] = []
    for b in bindings:
        candidate = Binding(slot=b.slot, index=b.index, node=b.node_title, field=b.field)
        try:
            Workflow(row.slug, graph, _meta(row, [*usable, candidate]), "")
        except WorkflowError:
            continue
        usable.append(candidate)
    meta = {
        "name": row.name_json,
        "kind": row.kind,
        "tier": "unverified",
        "origin": row.origin,
        "bindings": [b.model_dump(exclude_none=True, exclude_defaults=True) for b in usable],
        "pending": [{"slot": b.slot, "index": b.index} for b in bindings if b.state == "guessed"],
        "models": row.deps_json.get("models", []),
        "caps": row.caps_json,
    }
    raw = json.dumps(graph, ensure_ascii=False, indent=1).encode("utf-8")
    (folder / "workflow.api.json").write_bytes(raw)
    with open(folder / "workflow.yaml", "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)
    return load_workflow(row.slug, folder.parent).sha256


def _meta(row: ComfyWorkflowRow, bindings: list[Binding]) -> Any:
    from drama_series_agent.modelhub.workflows import WorkflowMeta

    return WorkflowMeta(name=row.name_json, kind=row.kind, tier="unverified", bindings=bindings)


WORKFLOW_TRIAL = "workflow_trial"
TRIAL_PROMPT = "雨夜的楼道，一个撑红伞的女人慢慢走上台阶，镜头缓缓推近。"


def _trial_size(row: ComfyWorkflowRow) -> tuple[int, int, float]:
    """The draft tier of the first aspect it supports (9:16 when it says nothing), and its
    shortest duration (3 s when it says nothing; pictures have none)."""
    sizes = row.caps_json.get("sizes")
    aspects = [a for a in ASPECTS if not isinstance(sizes, dict) or a in sizes]
    d = dims(aspects[0] if aspects else "9:16", "draft")
    durations = row.caps_json.get("duration_s")
    if row.kind != "video":
        return d.w, d.h, 0
    seconds = float(min(durations)) if isinstance(durations, list) and durations else 3.0
    return d.w, d.h, seconds


async def _node_map(access: ComfyAccess) -> dict[str, Any]:
    try:
        return await access.node_map()
    except ComfyUnavailable:
        return {}


def _packs_for(missing: list[str], node_map: dict[str, Any]) -> tuple[list[MissingPack], list[str]]:
    """Group missing node classes by the pack that provides them; classes no pack lists."""
    by_class: dict[str, tuple[str, str]] = {}
    for url, entry in node_map.items():
        if not isinstance(entry, list) or not entry or not isinstance(entry[0], list):
            continue
        info = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
        name = str(info.get("title_aux") or url.rstrip("/").rsplit("/", 1)[-1])
        for cls in entry[0]:
            by_class.setdefault(str(cls), (name, url))
    packs: dict[str, MissingPack] = {}
    unknown: list[str] = []
    for cls in missing:
        if cls not in by_class:
            unknown.append(cls)
            continue
        name, url = by_class[cls]
        pack = packs.setdefault(
            url, MissingPack(name=name, classes=[], source="git", version=None, url=url)
        )
        pack.classes.append(cls)
    return list(packs.values()), unknown


def _missing_models(
    graph: dict[str, Any], info: dict[str, Any], wanted: list[dict[str, Any]]
) -> list[MissingModel]:
    """A model file a loader names that is not among the loader's choices in ComfyUI."""
    out: list[MissingModel] = []
    names = {str(m.get("name")): str(m.get("folder")) for m in wanted}
    for node in graph.values():
        spec = (info.get(str(node.get("class_type"))) or {}).get("input") or {}
        for field, value in (node.get("inputs") or {}).items():
            if not isinstance(value, str) or value not in names:
                continue
            entry = (spec.get("required") or {}).get(field) or (spec.get("optional") or {}).get(
                field
            )
            choices = entry[0] if isinstance(entry, list) and entry else None
            if isinstance(choices, list) and value not in choices:
                model = MissingModel(folder=names[value], name=value)
                if model not in out:
                    out.append(model)
    return out


def _gb(size_bytes: int | None) -> dict[str, float]:
    return {"gb": round(size_bytes / 1024**3, 1)} if size_bytes else {}

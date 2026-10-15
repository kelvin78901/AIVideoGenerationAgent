"""The setup manifest (``config/setup-manifest.yaml``, SPEC 12.1).

``load_manifest()`` parses and validates the whole file (unique ids, known dependencies, no
cycles). ``Manifest.for_platform()`` gives the items one machine sees: items for other platforms
dropped, the platform's overrides (``macos: {...}``) applied, install steps for other platforms
removed, and ``required`` cleared on items whose dependencies are not required there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from drama_series_agent.core.config import _read_yaml
from drama_series_agent.core.paths import config_dir

OS = Literal["windows", "macos", "linux"]
OSES: tuple[OS, ...] = ("windows", "macos", "linux")
Group = Literal["sys", "rt", "comfy", "w", "svc"]
Status = Literal["checking", "ok", "missing", "old", "optional", "warn", "skip"]
DetectType = Literal[
    "platform",
    "nvml",
    "command",
    "py_import",
    "file",
    "comfy",
    "comfy_node",
    "http",
    "service",
    "service_model",
    "keyring",
    "resolve",
]
StepType = Literal["uv_venv", "uv_pip", "git_clone", "download", "pkg", "script", "copy"]

TODO = "TODO"


class ManifestError(ValueError):
    pass


class _Loose(BaseModel):
    """Manifest rows carry notes and step-specific fields; keep them."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Localized(BaseModel):
    zh: str
    en: str


class Message(BaseModel):
    """A ``code + params`` the front end translates (``setup:fix.<code>``)."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _from_code(cls, data: Any) -> Any:
        return {"code": data} if isinstance(data, str) else data

    def public(self) -> dict[str, Any]:
        return {"code": self.code, "params": dict(self.params)}


FixMap = dict[Status, Message | None]


class Detect(_Loose):
    type: DetectType
    verify: bool = False
    field: str | None = None
    fallback: str | None = None
    path: str | None = None
    cmd: str | None = None
    version_regex: str | None = None
    env: str | None = None
    module: str | None = None
    url: str | None = None
    urls: list[str] = Field(default_factory=list)
    dir: str | None = None
    classes: list[str] | str | None = None
    speedtest: list[str] = Field(default_factory=list)
    max_latency_ms: int | None = None
    server: str | None = None
    model: str | None = None
    names_from: str | None = None


class Step(_Loose):
    type: StepType
    platforms: list[OS] | None = None


class PlatformOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: bool | None = None
    name: Localized | None = None
    variant: str | None = None
    fix: FixMap | None = None
    if_missing: Status | None = None
    installable: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, data: Any) -> Any:
        if data == "optional":
            return {"required": False}
        return data


class Item(_Loose):
    id: str
    group: Group
    name: Localized
    platforms: list[OS] | None = None
    requires_cuda: bool = False
    required: bool = False
    depends_on: list[str] = Field(default_factory=list)
    detect: Detect
    require: dict[str, Any] = Field(default_factory=dict)
    fix: FixMap = Field(default_factory=dict)
    if_missing: Status | None = None
    installable: bool | None = None
    install: list[Step] = Field(default_factory=list)
    variant: str | None = None
    windows: PlatformOverride | None = None
    macos: PlatformOverride | None = None
    linux: PlatformOverride | None = None

    @property
    def can_install(self) -> bool:
        """Has install steps here and is not switched off (``installable: false``)."""
        return bool(self.install) and self.installable is not False

    def on(self, os: OS) -> Item | None:
        """This item as ``os`` sees it, or None when it does not apply there."""
        if self.platforms is not None and os not in self.platforms:
            return None
        update: dict[str, Any] = {
            "install": [s for s in self.install if s.platforms is None or os in s.platforms],
            "windows": None,
            "macos": None,
            "linux": None,
        }
        override: PlatformOverride | None = getattr(self, os)
        if override is not None:
            for key in ("required", "name", "variant", "if_missing", "installable"):
                value = getattr(override, key)
                if value is not None:
                    update[key] = value
            if override.fix is not None:
                update["fix"] = {**self.fix, **override.fix}
        return self.model_copy(update=update)


class Manifest(BaseModel):
    version: int = 1
    mirrors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    items: list[Item]

    @field_validator("items")
    @classmethod
    def _check_graph(cls, items: list[Item]) -> list[Item]:
        ids = [x.id for x in items]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ManifestError(f"duplicate item ids: {', '.join(dupes)}")
        known = set(ids)
        for x in items:
            unknown = [d for d in x.depends_on if d not in known]
            if unknown:
                raise ManifestError(f"{x.id}: unknown depends_on {', '.join(unknown)}")
        topo_order(items)  # raises on a cycle
        return items

    def item(self, item_id: str) -> Item:
        for x in self.items:
            if x.id == item_id:
                return x
        raise KeyError(item_id)

    def for_platform(self, os: OS) -> list[Item]:
        """Items for ``os`` in manifest order, overrides applied and dependencies resolved."""
        here = {x.id: y for x in self.items if (y := x.on(os)) is not None}
        resolved: dict[str, Item] = {}
        for x in topo_order(list(here.values())):
            deps = [d for d in x.depends_on if d in here]
            required = x.required and all(resolved[d].required for d in deps)
            resolved[x.id] = x.model_copy(update={"depends_on": deps, "required": required})
        return [resolved[x.id] for x in self.items if x.id in resolved]


def topo_order(items: list[Item]) -> list[Item]:
    """Dependencies first, otherwise manifest order. Dependencies not in ``items`` are ignored."""
    by_id = {x.id: x for x in items}
    order: list[Item] = []
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(x: Item, path: list[str]) -> None:
        if state.get(x.id) == 2:
            return
        if state.get(x.id) == 1:
            raise ManifestError(f"dependency cycle: {' -> '.join([*path, x.id])}")
        state[x.id] = 1
        for dep in x.depends_on:
            if dep in by_id:
                visit(by_id[dep], [*path, x.id])
        state[x.id] = 2
        order.append(x)

    for x in items:
        visit(x, [])
    return order


def load_manifest(path: Path | None = None) -> Manifest:
    data = _read_yaml(path or config_dir() / "setup-manifest.yaml")
    return Manifest.model_validate(data)

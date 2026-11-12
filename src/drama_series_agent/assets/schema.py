"""API shapes of assets (front-end contract ``web/src/api/schemas/assets.ts``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AssetKind = Literal["character", "scene", "prop", "text", "voice"]
AssetStatus = Literal["locked", "choosing", "not_generated"]
TextMethod = Literal["composite", "model"]
TextStyle = Literal["handwritten", "printed", "screen"]
TextPen = Literal["ballpoint", "marker", "pencil"]  # what handwriting is written with (M5.5)
VoiceMethod = Literal["design", "clone", "local"]


class MessageOut(BaseModel):
    """Translated by the front end: ``components:asset.source.<code>``."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class TextOut(BaseModel):
    exact: str
    method: TextMethod
    style: TextStyle
    pen: TextPen = "ballpoint"


class PhysicalOut(BaseModel):
    """A prop's real size, material and wear (M5.5; content, any may be empty)."""

    size: str = ""
    material: str = ""
    wear: str = ""


class VoiceLineOut(BaseModel):
    text: str
    tone: str


class VoiceOut(BaseModel):
    method: VoiceMethod
    lines: list[VoiceLineOut]


class AssetSceneOut(BaseModel):
    """A scene the asset appears in: its series-wide 场号 and the lines in it."""

    scene_id: str
    episode_id: str
    number: int
    line_ids: list[str]


class AssetOut(BaseModel):
    id: str
    series_id: str
    kind: AssetKind
    name: str
    intent: str  # the description = the intent layer of the asset's prompt
    source: MessageOut
    shots: list[str]  # 出现在: the shots that reference it, 「1-04」
    scenes: list[AssetSceneOut]  # in the episode asked for
    product_id: str
    status: AssetStatus
    pick: int
    text: TextOut | None
    voice: VoiceOut | None
    note: str | None
    # The analysis now describes it differently from what its product was made from.
    seed_changed: bool
    physical: PhysicalOut | None = None  # a prop's (M5.5); None for other kinds


class TextPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exact: str | None = Field(default=None, max_length=200)
    method: TextMethod | None = None
    style: TextStyle | None = None
    pen: TextPen | None = None


class PhysicalPatch(BaseModel):
    """A prop's 真实尺寸 / 材质 / 新旧 (M5.5); an empty string clears one."""

    model_config = ConfigDict(extra="forbid")

    size: str | None = Field(default=None, max_length=200)
    material: str | None = Field(default=None, max_length=200)
    wear: str | None = Field(default=None, max_length=200)


class VoicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: VoiceMethod


class AssetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str | None = Field(default=None, max_length=2000)
    pick: int | None = Field(default=None, ge=0)
    text: TextPatch | None = None
    voice: VoicePatch | None = None
    physical: PhysicalPatch | None = None  # a prop's (M5.5)


class AssetCreateIn(BaseModel):
    """``POST /series/{id}/assets`` 「新建素材」 (M5.5): one the analysis did not find."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["character", "scene", "prop", "text"]
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=2000)


class AssetLockIn(BaseModel):
    """``POST /assets/{id}/lock``: by default the picked candidate of the version on screen;
    ``force`` locks on-screen text OCR read differently."""

    model_config = ConfigDict(extra="forbid")

    version_id: str | None = Field(default=None, max_length=64)
    idx: int | None = Field(default=None, ge=0)
    force: bool = False


class MatrixSceneOut(BaseModel):
    id: str
    number: int
    heading: str


class MatrixAssetOut(BaseModel):
    id: str
    kind: AssetKind
    name: str


class MatrixCellOut(BaseModel):
    asset_id: str
    scene_id: str
    line_ids: list[str]


class MatrixOut(BaseModel):
    """出场矩阵: one row per scene of the episode, one column per asset it uses."""

    episode_id: str
    scenes: list[MatrixSceneOut]
    assets: list[MatrixAssetOut]
    cells: list[MatrixCellOut]

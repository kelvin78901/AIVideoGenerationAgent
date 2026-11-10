"""DramaStudio's own input and output nodes (SPEC 6.4.3), as the studio sees them.

The pack is ``integrations/comfyui-dramastudio``. A workflow built with its nodes needs no
bindings from the user: each node's class says which slot it is and which input takes the value,
so importing one writes the bindings from this table (state ``dramastudio``) and running it
goes through the same ``workflow.yaml`` as any other workflow.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache

from drama_series_agent.core.paths import REPO_ROOT

PREFIX = "DramaStudio"
PACK_DIR = REPO_ROOT / "integrations" / "comfyui-dramastudio"
PACK_NAME = "DramaStudio"
MANIFEST_ITEM = "node_dramastudio"


@dataclass(frozen=True)
class NodeSlot:
    slot: str
    field: str | None  # None for an output node


NODES: dict[str, tuple[NodeSlot, ...]] = {
    "DramaStudioFirstFrame": (NodeSlot("first_frame", "image"),),
    "DramaStudioRefImage": (NodeSlot("ref_image", "image"),),
    "DramaStudioVideoIn": (NodeSlot("video_in", "video"),),
    "DramaStudioDialogueAudio": (NodeSlot("dialogue_audio", "audio"),),
    "DramaStudioRefAudio": (NodeSlot("ref_audio", "audio"),),
    "DramaStudioPrompt": (NodeSlot("prompt", "text"),),
    "DramaStudioNegative": (NodeSlot("negative", "text"),),
    "DramaStudioSize": (NodeSlot("width", "width"), NodeSlot("height", "height")),
    "DramaStudioDuration": (NodeSlot("fps", "fps"), NodeSlot("seconds", "seconds")),
    "DramaStudioSeed": (NodeSlot("seed", "seed"),),
    "DramaStudioVideoOut": (NodeSlot("video_out", None),),
    "DramaStudioImageOut": (NodeSlot("image_out", None),),
    "DramaStudioAudioOut": (NodeSlot("audio_out", None),),
}
# Numbered by the node's ``index`` input (reference picture 1, 2 …). A shot with fewer files
# than the workflow has nodes leaves the rest out (``optional``, SPEC 6.4.2).
NUMBERED = frozenset({"ref_image", "ref_audio"})
INDEX_FIELD = "index"


def is_ours(node_class: str) -> bool:
    return node_class.startswith(PREFIX)


@lru_cache(maxsize=1)
def pack_version() -> str | None:
    """The version in the pack's ``pyproject.toml`` (for the change list)."""
    try:
        data = tomllib.loads((PACK_DIR / "pyproject.toml").read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    version = data.get("project", {}).get("version")
    return str(version) if version else None

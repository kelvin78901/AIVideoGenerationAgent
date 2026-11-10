"""DramaStudio's input and output nodes (SPEC 6.4.3).

A workflow built with these needs no bindings in AI Drama Studio: the studio fills each input
node by its class and reads the output nodes by theirs. Every input has a default, so the
workflow also runs by hand in ComfyUI.

The file inputs (first frame, reference picture, video, audio) name a file under ComfyUI's
``input`` folder, like ``LoadImage``; the studio uploads into ``input/dramastudio/``. The outputs
save into ``output/dramastudio/`` and list their files the way ComfyUI's own save nodes do.

ComfyUI's modules (``folder_paths``, ``torch``, ``comfy_api``) are imported where they are used,
so this file loads without ComfyUI (the studio's tests read the node definitions).
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

CATEGORY = "DramaStudio"
OUTPUT_PREFIX = "dramastudio/out"
MAX_SEED = 0xFFFFFFFFFFFFFFFF
MAX_SIDE = 8192

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv")
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a")


# --------------------------------------------------------------------------- files


def input_files(exts: tuple[str, ...]) -> list[str]:
    """The files under ComfyUI's input folder with one of ``exts``, as ``sub/name`` paths
    (the studio's uploads are in ``dramastudio/``)."""
    import folder_paths

    root = folder_paths.get_input_directory()
    out: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        for name in files:
            if name.lower().endswith(exts):
                out.append(name if rel == "." else f"{rel}/{name}".replace(os.sep, "/"))
    return sorted(out)


def file_hash(name: str) -> str:
    import folder_paths

    digest = hashlib.sha256()
    with open(folder_paths.get_annotated_filepath(name), "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_file(name: str, what: str) -> bool | str:
    import folder_paths

    if not folder_paths.exists_annotated_filepath(name):
        return f"DramaStudio: no {what} file {name!r} in ComfyUI's input folder"
    return True


def frames_for(fps: float, seconds: float) -> int:
    """The frame count for a length: at least one."""
    return max(1, round(fps * seconds))


# --------------------------------------------------------------------------- loading


def load_image(name: str) -> Any:
    """An IMAGE (``[1, H, W, 3]`` floats in 0–1) from a file in the input folder."""
    import folder_paths
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    with Image.open(folder_paths.get_annotated_filepath(name)) as img:
        rgb = ImageOps.exif_transpose(img).convert("RGB")
        array = np.asarray(rgb, dtype=np.float32) / 255.0
    return torch.from_numpy(array)[None,]


def load_video(name: str) -> Any:
    import folder_paths
    from comfy_api.latest import InputImpl

    return InputImpl.VideoFromFile(folder_paths.get_annotated_filepath(name))


def load_audio(name: str) -> Any:
    """An AUDIO (``{"waveform": [1, C, T], "sample_rate": n}``), decoded as ``LoadAudio`` does."""
    import folder_paths
    from comfy_extras.nodes_audio import load

    waveform, rate = load(folder_paths.get_annotated_filepath(name))
    return {"waveform": waveform.unsqueeze(0), "sample_rate": rate}


# --------------------------------------------------------------------------- inputs


class _FileInput:
    """One file from the input folder; its widget lists them and takes uploads."""

    KIND = ""  # image / video / audio: the widget's upload type
    EXTS: tuple[str, ...] = ()
    FIELD = ""
    CATEGORY = CATEGORY
    FUNCTION = "load"

    @classmethod
    def file_input(cls) -> tuple[list[str], dict[str, Any]]:
        return (input_files(cls.EXTS), {f"{cls.KIND}_upload": True})

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> str:
        return file_hash(kwargs[cls.FIELD])

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs: Any) -> bool | str:
        return check_file(kwargs[cls.FIELD], cls.KIND)


class DramaStudioFirstFrame(_FileInput):
    """The shot's first frame (slot ``first_frame``)."""

    KIND, EXTS, FIELD = "image", IMAGE_EXTS, "image"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"image": cls.file_input()}}

    def load(self, image: str) -> tuple[Any]:
        return (load_image(image),)


class DramaStudioRefImage(_FileInput):
    """Reference picture ``index`` (slot ``ref_image`` 1, 2 …): one node per picture."""

    KIND, EXTS, FIELD = "image", IMAGE_EXTS, "image"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "index": ("INT", {"default": 1, "min": 1, "max": 16}),
                "image": cls.file_input(),
            }
        }

    def load(self, index: int, image: str) -> tuple[Any]:
        return (load_image(image),)


class DramaStudioVideoIn(_FileInput):
    """The video an upscale or lip-sync workflow works on (slot ``video_in``)."""

    KIND, EXTS, FIELD = "video", VIDEO_EXTS, "video"
    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"video": cls.file_input()}}

    def load(self, video: str) -> tuple[Any]:
        return (load_video(video),)


class DramaStudioDialogueAudio(_FileInput):
    """The shot's dialogue (slot ``dialogue_audio``)."""

    KIND, EXTS, FIELD = "audio", AUDIO_EXTS, "audio"
    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"audio": cls.file_input()}}

    def load(self, audio: str) -> tuple[Any]:
        return (load_audio(audio),)


class DramaStudioRefAudio(_FileInput):
    """Voice sample ``index`` (slot ``ref_audio`` 1, 2 …)."""

    KIND, EXTS, FIELD = "audio", AUDIO_EXTS, "audio"
    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "index": ("INT", {"default": 1, "min": 1, "max": 16}),
                "audio": cls.file_input(),
            }
        }

    def load(self, index: int, audio: str) -> tuple[Any]:
        return (load_audio(audio),)


class DramaStudioPrompt:
    """The prompt (slot ``prompt``); wire it into a text encoder's ``text``."""

    CATEGORY = CATEGORY
    FUNCTION = "run"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"text": ("STRING", {"multiline": True, "default": ""})}}

    def run(self, text: str) -> tuple[str]:
        return (text,)


class DramaStudioNegative(DramaStudioPrompt):
    """The negative prompt (slot ``negative``)."""


class DramaStudioSize:
    """The output size, from the episode's output spec (slots ``width`` and ``height``)."""

    CATEGORY = CATEGORY
    FUNCTION = "run"
    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        side = {"min": 16, "max": MAX_SIDE, "step": 8}
        return {
            "required": {
                "width": ("INT", {"default": 768, **side}),
                "height": ("INT", {"default": 1344, **side}),
            }
        }

    def run(self, width: int, height: int) -> tuple[int, int]:
        return (width, height)


class DramaStudioDuration:
    """Frame rate and length (slots ``fps`` and ``seconds``); ``frames`` is the two multiplied,
    rounded (a model that wants 4n + 1 frames needs its own math node after it)."""

    CATEGORY = CATEGORY
    FUNCTION = "run"
    RETURN_TYPES = ("FLOAT", "INT", "FLOAT", "INT")
    RETURN_NAMES = ("fps", "fps_int", "seconds", "frames")

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.001}),
                "seconds": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 600.0, "step": 0.1}),
            }
        }

    def run(self, fps: float, seconds: float) -> tuple[float, int, float, int]:
        return (fps, round(fps), seconds, frames_for(fps, seconds))


class DramaStudioSeed:
    """The seed (slot ``seed``); each take of a shot gets the next one."""

    CATEGORY = CATEGORY
    FUNCTION = "run"
    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("seed",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"seed": ("INT", {"default": 0, "min": 0, "max": MAX_SEED})}}

    def run(self, seed: int) -> tuple[int]:
        return (seed,)


# --------------------------------------------------------------------------- outputs


def save_path(prefix: str, width: int, height: int) -> tuple[str, str, str, int]:
    """Folder, file stem, subfolder and counter for a new file in ComfyUI's output folder."""
    import folder_paths

    folder, stem, counter, subfolder, _prefix = folder_paths.get_save_image_path(
        prefix, folder_paths.get_output_directory(), width, height
    )
    return folder, stem, subfolder, counter


class _Output:
    CATEGORY = CATEGORY
    FUNCTION = "save"
    OUTPUT_NODE = True
    RETURN_TYPES = ()


class DramaStudioVideoOut(_Output):
    """The result video (slot ``video_out``), saved as MP4."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "video": ("VIDEO",),
                "filename_prefix": ("STRING", {"default": OUTPUT_PREFIX}),
            }
        }

    def save(self, video: Any, filename_prefix: str) -> dict[str, Any]:
        width, height = video.get_dimensions()
        folder, stem, subfolder, counter = save_path(filename_prefix, width, height)
        name = f"{stem}_{counter:05}_.mp4"
        video.save_to(os.path.join(folder, name))
        result = {"filename": name, "subfolder": subfolder, "type": "output"}
        return {"ui": {"images": [result], "animated": (True,)}}


class DramaStudioImageOut(_Output):
    """The result picture(s) (slot ``image_out``), saved as PNG."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": OUTPUT_PREFIX}),
            }
        }

    def save(self, images: Any, filename_prefix: str) -> dict[str, Any]:
        from comfy_api.latest import ui

        saved = ui.ImageSaveHelper.get_save_images_ui(images, filename_prefix, None)
        return {"ui": saved.as_dict()}


class DramaStudioAudioOut(_Output):
    """The result audio (slot ``audio_out``), saved as FLAC."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "audio": ("AUDIO",),
                "filename_prefix": ("STRING", {"default": OUTPUT_PREFIX}),
            }
        }

    def save(self, audio: Any, filename_prefix: str) -> dict[str, Any]:
        from comfy_api.latest import ui

        saved = ui.AudioSaveHelper.get_save_audio_ui(audio, filename_prefix, None, format="flac")
        return {"ui": saved.as_dict()}


NODES: dict[str, tuple[type, str]] = {
    "DramaStudioFirstFrame": (DramaStudioFirstFrame, "DramaStudio ▸ First frame"),
    "DramaStudioRefImage": (DramaStudioRefImage, "DramaStudio ▸ Reference picture"),
    "DramaStudioVideoIn": (DramaStudioVideoIn, "DramaStudio ▸ Video in"),
    "DramaStudioDialogueAudio": (DramaStudioDialogueAudio, "DramaStudio ▸ Dialogue audio"),
    "DramaStudioRefAudio": (DramaStudioRefAudio, "DramaStudio ▸ Voice sample"),
    "DramaStudioPrompt": (DramaStudioPrompt, "DramaStudio ▸ Prompt"),
    "DramaStudioNegative": (DramaStudioNegative, "DramaStudio ▸ Negative prompt"),
    "DramaStudioSize": (DramaStudioSize, "DramaStudio ▸ Size"),
    "DramaStudioDuration": (DramaStudioDuration, "DramaStudio ▸ Frame rate and length"),
    "DramaStudioSeed": (DramaStudioSeed, "DramaStudio ▸ Seed"),
    "DramaStudioVideoOut": (DramaStudioVideoOut, "DramaStudio ▸ Video out"),
    "DramaStudioImageOut": (DramaStudioImageOut, "DramaStudio ▸ Image out"),
    "DramaStudioAudioOut": (DramaStudioAudioOut, "DramaStudio ▸ Audio out"),
}

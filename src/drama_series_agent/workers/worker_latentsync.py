"""LatentSync 1.6 lip sync (口型修复 locally, M6 step 7b; ``pipeline/components/lip.py``).

Follows the repo's ``scripts/inference.py`` (commit a229c39, checked 2026-11-18) with the model
kept loaded between requests:

- **init** args: ``src`` (the cloned repo, put on ``sys.path``), ``unet`` (``latentsync_unet.pt``),
  ``whisper`` (``whisper/tiny.pt``), ``vae`` (the ``sd-vae-ft-mse`` folder: the repo fetches it
  from the Hub at run time; here it is downloaded by setup), ``faces`` (buffalo_l's two ONNX
  files, ``latentsync_faces``), ``steps`` (20), ``guidance`` (1.5), ``deepcache`` (the repo's
  ``--enable_deepcache``: cache interval 3). U-Net config ``configs/unet/stage2_512.yaml``
  (512 px, 16 frames a window, 25 fps, 16 kHz).
- **run** ``kind: lipsync``: ``params.video`` / ``params.audio`` (paths), ``fps`` (the take's),
  ``seed``. Inputs are copied into the request's folder under plain names (LatentSync builds
  shell commands with unquoted paths) and it runs there (it writes ``temp/`` next to itself).
  LatentSync resamples the picture to 25 fps and makes as many frames as the audio lasts (the
  picture played back and forth when the audio is longer); the result is brought back to the
  take's ``fps`` with its sound.
- **ffmpeg**: LatentSync shells out to ``ffmpeg``; imageio-ffmpeg's binary is copied into the
  environment as ``ffmpeg(.exe)`` and put first on ``PATH`` (another ``ffmpeg`` on the machine's
  ``PATH`` is never used).
- A frame without a face stops LatentSync (``Face not detected``): ``lipsync_no_face``.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from worker_protocol import WorkerError, out_path, serve

UNET_CONFIG = "configs/unet/stage2_512.yaml"
DEEPCACHE_INTERVAL = 3


def ffmpeg_first() -> str:
    """imageio-ffmpeg's binary as ``ffmpeg`` in the environment, first on ``PATH``."""
    import imageio_ffmpeg

    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    folder = Path(sys.prefix) / "ffmpeg-bin"
    folder.mkdir(exist_ok=True)
    target = folder / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
    return str(target)


def init(args: dict[str, Any]) -> dict[str, Any]:
    src = Path(str(args["src"]))
    if not (src / "latentsync").is_dir():
        raise WorkerError("not_installed", f"no LatentSync source at {src} (setup rt_latentsync)")
    sys.path.insert(0, str(src))
    import latentsync_faces

    latentsync_faces.install(str(args["faces"]))
    ffmpeg = ffmpeg_first()

    import torch
    from diffusers import AutoencoderKL, DDIMScheduler
    from latentsync.models.unet import UNet3DConditionModel
    from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
    from latentsync.whisper.audio2feature import Audio2Feature
    from omegaconf import OmegaConf

    if not torch.cuda.is_available():
        raise WorkerError("no_cuda", "LatentSync needs an NVIDIA GPU")
    config = OmegaConf.load(src / UNET_CONFIG)
    fp16 = torch.cuda.get_device_capability()[0] > 7
    dtype = torch.float16 if fp16 else torch.float32
    scheduler = DDIMScheduler.from_pretrained(str(src / "configs"))
    audio_encoder = Audio2Feature(
        model_path=str(args["whisper"]),
        device="cuda",
        num_frames=config.data.num_frames,
        audio_feat_length=config.data.audio_feat_length,
    )
    vae = AutoencoderKL.from_pretrained(str(args["vae"]), torch_dtype=dtype)
    vae.config.scaling_factor = 0.18215
    vae.config.shift_factor = 0
    unet, _ = UNet3DConditionModel.from_pretrained(
        OmegaConf.to_container(config.model), str(args["unet"]), device="cpu"
    )
    unet = unet.to(dtype=dtype)
    pipeline = LipsyncPipeline(
        vae=vae, audio_encoder=audio_encoder, unet=unet, scheduler=scheduler
    ).to("cuda")
    if args.get("deepcache", True):
        from DeepCache import DeepCacheSDHelper

        helper = DeepCacheSDHelper(pipe=pipeline)
        helper.set_params(cache_interval=DEEPCACHE_INTERVAL, cache_branch_id=0)
        helper.enable()
    return {
        "pipeline": pipeline,
        "config": config,
        "dtype": dtype,
        "src": src,
        "ffmpeg": ffmpeg,
        "steps": int(args.get("steps", 20)),
        "guidance": float(args.get("guidance", 1.5)),
    }


def _seed(seed: int) -> None:
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed % 2**32)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def lipsync(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    params = msg.get("params") or {}
    work = Path(str(msg["out"])) / "work"
    work.mkdir(parents=True, exist_ok=True)
    video, audio = work / "in.mp4", work / "in.wav"
    shutil.copyfile(str(params["video"]), video)
    shutil.copyfile(str(params["audio"]), audio)
    _seed(int(params.get("seed") or 1247))
    config = state["config"]
    synced = work / "synced.mp4"
    here = os.getcwd()
    os.chdir(work)  # read_video writes ./temp
    try:
        state["pipeline"](
            video_path=str(video),
            audio_path=str(audio),
            video_out_path=str(synced),
            num_frames=config.data.num_frames,
            num_inference_steps=state["steps"],
            guidance_scale=state["guidance"],
            weight_dtype=state["dtype"],
            width=config.data.resolution,
            height=config.data.resolution,
            mask_image_path=str(state["src"] / config.data.mask_image_path),
            temp_dir=str(work / "temp"),
        )
    except RuntimeError as exc:
        if "Face not detected" in str(exc):
            raise WorkerError("lipsync_no_face", str(exc)) from exc
        raise
    finally:
        os.chdir(here)
    if not synced.is_file():
        raise WorkerError("worker_error", "LatentSync wrote no video")
    out = out_path(msg, ".mp4")
    fps = str(int(params.get("fps") or 25))
    subprocess.run(
        [state["ffmpeg"], "-y", "-loglevel", "error", "-nostdin", "-i", str(synced), "-r", fps,
         "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "copy",
         "-movflags", "+faststart", out],
        check=True,
    )  # fmt: skip
    return {"files": [{"path": out, "role": "video", "mime": "video/mp4"}]}


if __name__ == "__main__":
    serve({"lipsync": lipsync}, init)

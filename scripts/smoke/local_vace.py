"""Local check (M6 step 8a): video inpaint of a real take with Wan2.1 VACE 14B on this machine's
ComfyUI, straight through ComfyUI's HTTP API with ``workflows/vace-inpaint`` (no studio, nothing
spent). Answers: does it run at the take's own size and frame rate, how long, how much GPU
memory, and is everything outside the mask kept.

    uv run --no-sync python scripts/smoke/local_vace.py [--take <mp4>] [--box x0,y0,x1,y1]
        [--prompt "..."] [--steps 4] [--seed 1] [--fps 0] [--tag name] [--comfy http://127.0.0.1:8188]

- The mask is a white box on black at the take's size (one mask for the whole take, as the
  take card's mask dialog will send). ``--fps 16`` resamples the take to 16 fps first (Wan's
  native rate) instead of running it at its own rate.
- Checked: size, frame rate, frame count, sound stream byte for byte, and the mean difference
  outside the mask (grown and feathered by the workflow, plus a margin) against the take.
- Pictures (left: the take, right: the inpaint; whole frame and a 1:1 crop of the box) and the
  clip go to ``docs/studio/reports/m6-vace-local/`` (clips are not in git); one line per run is
  appended to its ``README.txt``.

ComfyUI must be running; it is freed (``/free``) before and after. Do not run next to the full
pytest.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from drama_series_agent.media.audio import ffmpeg_exe
from drama_series_agent.media.video import _frame_count, _probe_file

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows" / "vace-inpaint" / "workflow.api.json"
TAKE = ROOT / "docs/studio/reports/m5-local-smoke/originals/m6-lipsync/1-04-T9-take.mp4"
OUT = ROOT / "docs" / "studio" / "reports" / "m6-vace-local"
CLIPS = ROOT / "docs" / "studio" / "reports" / "m5-local-smoke" / "originals" / "m6-vace"
PROMPT = (
    "A dim, damp apartment hallway at night. A closed black umbrella leans against the grey "
    "wall beside a young woman in a beige trench coat. Cinematic, realistic."
)


def ffmpeg(*args: str) -> bytes:
    cmd = [ffmpeg_exe(), "-hide_banner", "-v", "error", *args]
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def sound(path: Path) -> bytes:
    return ffmpeg("-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "data", "-")


def gray(path: Path, at: float) -> bytes:
    """One frame as 8-bit grey pixels, row by row."""
    return ffmpeg(
        "-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    )  # fmt: skip


def inside_box(x: int, y: int, box: tuple[int, int, int, int]) -> bool:
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def mean_diff(a: bytes, b: bytes, w: int, h: int, keep: Callable[[int, int], bool]) -> float:
    total = count = 0
    for y in range(0, h, 2):
        row = y * w
        for x in range(0, w, 2):
            if keep(x, y):
                total += abs(a[row + x] - b[row + x])
                count += 1
    return total / count if count else 0.0


class GpuPeak(threading.Thread):
    """Polls nvidia-smi for the used memory while the job runs."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak = 0
        self.stop = threading.Event()

    def used(self) -> int:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return int(out.split()[0]) if out.strip() else 0

    def run(self) -> None:
        while not self.stop.is_set():
            self.peak = max(self.peak, self.used())
            time.sleep(1)


def upload(client: httpx.Client, path: Path, name: str) -> str:
    with path.open("rb") as f:
        r = client.post(
            "/upload/image",
            files={"image": (name, f)},
            data={"subfolder": "dramastudio", "type": "input", "overwrite": "true"},
        )
    r.raise_for_status()
    body = r.json()
    return f"{body['subfolder']}/{body['name']}" if body.get("subfolder") else body["name"]


def by_title(graph: dict[str, Any], title: str) -> dict[str, Any]:
    for node in graph.values():
        if node.get("_meta", {}).get("title") == title:
            inputs: dict[str, Any] = node["inputs"]
            return inputs
    raise KeyError(title)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--take", default=str(TAKE))
    ap.add_argument("--box", default="0,720,260,1344", help="x0,y0,x1,y1 in the take's pixels")
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--fps", type=float, default=0, help="resample to this rate first (0: keep)")
    ap.add_argument("--no-lora", action="store_true", help="plain VACE (cfg 6) instead of CausVid")
    ap.add_argument("--tag", default="")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument(
        "--collect",
        default="",
        help="a prompt id already queued with the same options: wait for "
        "it and check it (when this script was stopped mid-run; GPU memory is then not measured)",
    )
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vace-"))
    take = Path(args.take)
    if args.fps:
        resampled = tmp / "take.mp4"
        ffmpeg("-i", str(take), "-vf", f"fps={args.fps}", "-c:a", "copy", "-y", str(resampled))
        take = resampled
    info = _probe_file(take)
    frames = _frame_count(take)
    length = ((frames - 1 + 3) // 4) * 4 + 1  # VACE wants 4n+1 frames; extra ones are cut after
    w16, h16 = info.w // 16 * 16, info.h // 16 * 16
    x0, y0, x1, y1 = (int(v) for v in args.box.split(","))
    tag = args.tag or f"s{args.steps}-{'f' + str(int(args.fps)) if args.fps else 'native'}"
    name = f"{take.stem.replace('-take', '')}-{tag}"

    mask_path = tmp / "mask.png"
    ffmpeg(
        "-f", "lavfi", "-i", f"color=black:s={info.w}x{info.h}",
        "-vf", f"drawbox=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0}:color=white:t=fill,format=gray",
        "-frames:v", "1", "-y", str(mask_path),
    )  # fmt: skip

    graph = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    client = httpx.Client(base_url=args.comfy, timeout=60)
    stamp = uuid.uuid4().hex[:8]
    if not args.collect:
        client.post("/free", json={"unload_models": True, "free_memory": True})
        by_title(graph, "Video in")["file"] = upload(client, take, f"vace-{stamp}.mp4")
        by_title(graph, "Mask")["image"] = upload(client, mask_path, f"vace-{stamp}-mask.png")
    by_title(graph, "Prompt")["text"] = args.prompt
    vace = by_title(graph, "VACE")
    vace.update({"width": w16, "height": h16, "length": length})
    by_title(graph, "Mask per frame")["amount"] = length
    by_title(graph, "Frames")["length"] = frames
    sampler = by_title(graph, "Sampler")
    sampler.update({"steps": args.steps, "seed": args.seed})
    if args.no_lora:
        by_title(graph, "Shift")["model"] = ["8", 0]
        sampler["cfg"] = 6.0
    by_title(graph, "Output")["filename_prefix"] = f"dramastudio/vace-{stamp}"

    gpu = GpuPeak()
    before = gpu.used()
    gpu.start()
    started = time.monotonic()
    if args.collect:
        pid = args.collect
    else:
        r = client.post("/prompt", json={"prompt": graph, "client_id": f"vace-{stamp}"})
        if r.status_code != 200:
            print(r.text[:2000])
            return 1
        pid = r.json()["prompt_id"]
    print(f"{name}: queued {pid} · {info.w}×{info.h} → {w16}×{h16}, {frames} frames → {length}")
    while True:
        time.sleep(3)
        hist = client.get(f"/history/{pid}").json().get(pid)
        if hist and hist.get("status", {}).get("completed") is not None:
            if hist["status"].get("status_str") != "success" or not hist.get("outputs"):
                print(json.dumps(hist.get("status"), ensure_ascii=False)[:3000])
                gpu.stop.set()
                return 1
            break
    took = time.monotonic() - started
    if args.collect:  # ComfyUI's own clock: from the start of the run to its end
        stamps = {m[0]: m[1].get("timestamp") for m in hist["status"].get("messages", [])}
        took = (stamps["execution_success"] - stamps["execution_start"]) / 1000
    gpu.stop.set()
    gpu.join()
    client.post("/free", json={"unload_models": True, "free_memory": True})

    out_files = [
        item
        for node in hist["outputs"].values()
        for key in ("images", "videos", "gifs")
        for item in node.get(key, [])
        if item.get("type") == "output"
    ]
    item = out_files[0]
    data = client.get(
        "/view",
        params={"filename": item["filename"], "subfolder": item["subfolder"], "type": "output"},
        timeout=300,
    ).content
    clip = CLIPS / f"{name}.mp4"
    clip.write_bytes(data)
    got = _probe_file(clip)
    got_frames = _frame_count(clip)

    checks = [
        ("size kept", (got.w, got.h) == (info.w, info.h)),
        ("frame rate kept", got.fps == info.fps),
        (f"frames kept ({frames})", got_frames == frames),
        ("sound kept byte for byte", info.has_audio and sound(clip) == sound(take)),
    ]
    # Outside the box plus a margin for the grown, feathered mask: the take, up to the encoder.
    margin = 16 + 16
    hole = (x0 - margin, y0 - margin, x1 + margin, y1 + margin)
    cx0, cy0 = max(0, x0 - 64), max(0, y0 - 64)
    cx1, cy1 = min(info.w, x1 + 64), min(info.h, y1 + 64)
    diffs = []
    lines = []
    for pct in (10, 50, 90):
        at = info.duration_s * pct / 100
        a, b = gray(take, at), gray(clip, at)
        outside = mean_diff(a, b, info.w, info.h, lambda x, y: not inside_box(x, y, hole))
        inside = mean_diff(a, b, info.w, info.h, lambda x, y: inside_box(x, y, (x0, y0, x1, y1)))
        diffs.append(outside)
        lines.append(f"{pct}%: outside {outside:.2f}, inside {inside:.1f}")
        for kind, crop, scale in (
            ("whole", None, f"{info.w // 2}:{info.h // 2}"),
            ("crop", f"{cx1 - cx0}:{cy1 - cy0}:{cx0}:{cy0}", None),
        ):
            pre = f"crop={crop}," if crop else ""
            post = f",scale={scale}" if scale else ""
            graph_ = (
                f"[0:v]{pre}setsar=1{post}[a];[1:v]{pre}setsar=1{post}[b];[a][b]hstack=inputs=2"
            )
            ffmpeg(
                "-ss", f"{at:.3f}", "-i", str(take), "-ss", f"{at:.3f}", "-i", str(clip),
                "-filter_complex", graph_, "-frames:v", "1", "-q:v", "2", "-y",
                str(OUT / f"{name}-{pct}-{kind}.jpg"),
            )  # fmt: skip
    checks.append(("outside the mask kept (mean diff < 1)", max(diffs) < 1.0))

    report = [
        f"{datetime.now():%Y-%m-%d %H:%M} · {name} · {info.w}×{info.h} {info.fps} fps "
        f"{frames} frames · box {args.box} · steps {args.steps} · seed {args.seed}"
        f"{' · no LoRA, cfg 6' if args.no_lora else ' · CausVid 0.3, cfg 1'}",
        f"  took {took:.0f} s · GPU memory peak {gpu.peak} MiB (before {before} MiB)",
        f"  out {got.w}×{got.h} {got.fps} fps {got_frames} frames audio={got.has_audio}",
        *(f"  {'ok ' if ok else 'BAD'} {label}" for label, ok in checks),
        *(f"  diff {line}" for line in lines),
        f"  prompt: {args.prompt}",
    ]
    print("\n".join(report))
    with (OUT / "README.txt").open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report) + "\n")
    return 0 if all(ok for _, ok in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())

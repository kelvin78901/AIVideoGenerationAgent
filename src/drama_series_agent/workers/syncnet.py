"""SyncNet (VGG, ``syncnet_v2.model``) and its MFCC, for ``worker_qa``'s ``sync`` tool: imports
torch and numpy, so only the ``qa`` environment loads it (when that worker starts).

Adapted from:

- joonson/syncnet_python (https://github.com/joonson/syncnet_python, master 2024):
  ``SyncNetModel.py`` (the network, layer for layer: the weights load by these names) and
  ``SyncNetInstance.evaluate`` (5-frame windows, distances over ±``vshift`` audio offsets, the
  offset with the smallest mean distance, ``conf = median − min``). MIT License,
  Copyright (c) 2016-present Joon Son Chung.
- python_speech_features 0.6 (``base.mfcc`` with its defaults; ``sigproc.framesig`` /
  ``powspec`` / ``preemphasis``), which syncnet_python calls on 16 kHz int16 samples. MIT License,
  Copyright (c) 2013 James Lyons. ``scipy.fftpack.dct(type=2, norm="ortho")`` is written out as
  a matrix, so the environment needs no scipy.

Changed: no ffmpeg or temporary files (frames and samples come in as arrays); the model is built
once and run on the CPU; the distance math is the original's, batched.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions: The above copyright notice and this
permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import decimal
import math
from typing import Any

import numpy as np
import torch
from torch import nn

RATE = 16000
FPS = 25
MFCC_PER_FRAME = 4  # 10 ms MFCC steps per 40 ms video frame
WINDOW = 5  # video frames per SyncNet window (20 MFCC steps)


class S(nn.Module):  # SyncNetModel.S, unchanged
    def __init__(self, num_layers_in_fc_layers: int = 1024) -> None:
        super().__init__()
        self.netcnnaud = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1)),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(1, 1), stride=(1, 1)),
            nn.Conv2d(64, 192, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1)),
            nn.BatchNorm2d(192),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(3, 3), stride=(1, 2)),
            nn.Conv2d(192, 384, kernel_size=(3, 3), padding=(1, 1)),
            nn.BatchNorm2d(384),
            nn.ReLU(inplace=True),
            nn.Conv2d(384, 256, kernel_size=(3, 3), padding=(1, 1)),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, 256, kernel_size=(3, 3), padding=(1, 1)),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(3, 3), stride=(2, 2)),
            nn.Conv2d(256, 512, kernel_size=(5, 4), padding=(0, 0)),
            nn.BatchNorm2d(512),
            nn.ReLU(),
        )
        self.netfcaud = nn.Sequential(
            nn.Linear(512, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Linear(512, num_layers_in_fc_layers),
        )
        self.netfclip = nn.Sequential(
            nn.Linear(512, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Linear(512, num_layers_in_fc_layers),
        )
        self.netcnnlip = nn.Sequential(
            nn.Conv3d(3, 96, kernel_size=(5, 7, 7), stride=(1, 2, 2), padding=0),
            nn.BatchNorm3d(96),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=(1, 3, 3), stride=(1, 2, 2)),
            nn.Conv3d(96, 256, kernel_size=(1, 5, 5), stride=(1, 2, 2), padding=(0, 1, 1)),
            nn.BatchNorm3d(256),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=(1, 3, 3), stride=(1, 2, 2), padding=(0, 1, 1)),
            nn.Conv3d(256, 256, kernel_size=(1, 3, 3), padding=(0, 1, 1)),
            nn.BatchNorm3d(256),
            nn.ReLU(inplace=True),
            nn.Conv3d(256, 256, kernel_size=(1, 3, 3), padding=(0, 1, 1)),
            nn.BatchNorm3d(256),
            nn.ReLU(inplace=True),
            nn.Conv3d(256, 256, kernel_size=(1, 3, 3), padding=(0, 1, 1)),
            nn.BatchNorm3d(256),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=(1, 3, 3), stride=(1, 2, 2)),
            nn.Conv3d(256, 512, kernel_size=(1, 6, 6), padding=0),
            nn.BatchNorm3d(512),
            nn.ReLU(inplace=True),
        )

    def forward_aud(self, x: torch.Tensor) -> torch.Tensor:
        mid = self.netcnnaud(x)
        return self.netfcaud(mid.view((mid.size(0), -1)))

    def forward_lip(self, x: torch.Tensor) -> torch.Tensor:
        mid = self.netcnnlip(x)
        return self.netfclip(mid.view((mid.size(0), -1)))


# --------------------------------------------------------------------------- MFCC


def _round_half_up(x: float) -> int:
    return int(decimal.Decimal(x).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def _filterbanks(nfilt: int, nfft: int, rate: int) -> np.ndarray:
    def hz2mel(hz: Any) -> Any:
        return 2595 * np.log10(1 + hz / 700.0)

    def mel2hz(mel: Any) -> Any:
        return 700 * (10 ** (mel / 2595.0) - 1)

    points = np.linspace(hz2mel(0), hz2mel(rate / 2), nfilt + 2)
    bins = np.floor((nfft + 1) * mel2hz(points) / rate)
    fb = np.zeros([nfilt, nfft // 2 + 1])
    for j in range(nfilt):
        for i in range(int(bins[j]), int(bins[j + 1])):
            fb[j, i] = (i - bins[j]) / (bins[j + 1] - bins[j])
        for i in range(int(bins[j + 1]), int(bins[j + 2])):
            fb[j, i] = (bins[j + 2] - i) / (bins[j + 2] - bins[j + 1])
    return fb


def _dct_ortho(n: int, keep: int) -> np.ndarray:
    """``scipy.fftpack.dct(x, type=2, norm="ortho")[:keep]`` as a (keep, n) matrix."""
    k = np.arange(keep)[:, None]
    i = np.arange(n)[None, :]
    m = np.sqrt(2.0 / n) * np.cos(np.pi * k * (2 * i + 1) / (2 * n))
    m[0] /= np.sqrt(2.0)
    return m


def mfcc(signal: np.ndarray, rate: int = RATE) -> np.ndarray:
    """python_speech_features 0.6 ``mfcc(signal, rate)`` with its defaults: 25 ms windows every
    10 ms, 26 filters, nfft 512, pre-emphasis 0.97, 13 coefficients, lifter 22, the first one
    replaced by the log frame energy. ``signal`` on the int16 scale. → (frames, 13)."""
    nfft, nfilt, numcep = 512, 26, 13
    sig = np.asarray(signal, np.float64)
    sig = np.append(sig[0], sig[1:] - 0.97 * sig[:-1])
    flen, fstep = _round_half_up(0.025 * rate), _round_half_up(0.01 * rate)
    n = len(sig)
    count = 1 if n <= flen else 1 + math.ceil((n - flen) / fstep)
    pad = np.concatenate((sig, np.zeros((count - 1) * fstep + flen - n)))
    idx = np.arange(flen)[None, :] + (np.arange(count) * fstep)[:, None]
    frames = pad[idx]
    pspec = 1.0 / nfft * np.square(np.abs(np.fft.rfft(frames, nfft)))
    energy = np.sum(pspec, 1)
    energy = np.where(energy == 0, np.finfo(float).eps, energy)
    feat = pspec @ _filterbanks(nfilt, nfft, rate).T
    feat = np.where(feat == 0, np.finfo(float).eps, feat)
    feat = np.log(feat) @ _dct_ortho(nfilt, numcep).T
    feat = feat * (1 + 11.0 * np.sin(np.pi * np.arange(numcep) / 22))  # lifter, L = 22
    feat[:, 0] = np.log(energy)
    return feat


# --------------------------------------------------------------------------- scoring


class SyncNet:
    """``score(crops, samples)``: crops are 224×224 BGR uint8 face crops at 25 fps, samples the
    same stretch of sound (float32 16 kHz in [-1, 1]). → ``{conf, offset, min_dist, voiced,
    windows, conf_all}`` or None when there are too few frames for one window.

    Changed from ``evaluate``: ``conf`` / ``offset`` / ``min_dist`` average only the windows with
    sound (RMS ≥ ``min_rms`` over the window's 0.2 s; fewer than ``min_voiced`` → ``conf`` None).
    A short line in a long take is mostly silence, where no offset fits better than another: over
    the whole take a well-synced 1 s line in a 4.8 s take scored 0.7, its spoken windows 9–13
    (M6 step 5b, round 19 shot 1-04). ``conf_all`` is the original's whole-take value."""

    def __init__(
        self,
        weights: str,
        threads: int = 4,
        vshift: int = 15,
        batch: int = 20,
        min_rms: float = 0.01,
        min_voiced: int = 10,
    ) -> None:
        torch.set_num_threads(threads)
        self.net = S()
        state = torch.load(weights, map_location="cpu", weights_only=True)
        self.net.load_state_dict(state)
        self.net.eval()
        self.vshift, self.batch = vshift, batch
        self.min_rms, self.min_voiced = min_rms, min_voiced

    @torch.no_grad()
    def score(self, crops: list[Any], samples: Any) -> dict[str, Any] | None:
        raw = np.asarray(samples, np.float32)
        audio = raw * 32768.0  # the original reads int16 wav
        if len(audio) < 400:
            return None
        cc = mfcc(audio).T  # (13, steps)
        frames = min(len(crops), len(audio) // (RATE // FPS))
        last = frames - WINDOW
        if last <= 0:
            return None
        video = torch.from_numpy(np.stack(crops[:frames], 0).astype(np.float32))  # T,H,W,C
        video = video.permute(3, 0, 1, 2).unsqueeze(0)  # 1,C,T,H,W
        sound = torch.from_numpy(cc.astype(np.float32))[None, None]  # 1,1,13,steps
        lip, aud = [], []
        for i in range(0, last, self.batch):
            span = range(i, min(last, i + self.batch))
            lip.append(self.net.forward_lip(torch.cat([video[:, :, v : v + WINDOW] for v in span])))
            aud.append(
                self.net.forward_aud(
                    torch.cat(
                        [sound[:, :, :, v * MFCC_PER_FRAME : v * MFCC_PER_FRAME + 20] for v in span]
                    )
                )
            )
        im, au = torch.cat(lip), torch.cat(aud)
        win = 2 * self.vshift + 1
        aup = nn.functional.pad(au, (0, 0, self.vshift, self.vshift))
        dists = torch.stack(
            [
                nn.functional.pairwise_distance(im[[i], :].repeat(win, 1), aup[i : i + win, :])
                for i in range(len(im))
            ],
            1,
        )
        per = RATE // FPS
        loud = [
            float(np.sqrt(np.mean(np.square(raw[i * per : (i + WINDOW) * per])))) >= self.min_rms
            for i in range(len(im))
        ]
        voiced = sum(loud)

        def best(d: torch.Tensor) -> tuple[float, int, float]:
            mdist = torch.mean(d, 1)
            minval, minidx = torch.min(mdist, 0)
            conf = float(torch.median(mdist) - minval)
            return conf, int(self.vshift - int(minidx)), float(minval)

        conf_all = best(dists)[0]
        out: dict[str, Any] = {"voiced": voiced, "windows": len(im), "conf_all": conf_all}
        if voiced < self.min_voiced:
            return {**out, "conf": None, "offset": None, "min_dist": None}
        # Only pairs with real sound on both sides: the original's zero padding stands in for the
        # sound past the take's ends, and a line at the very end (the usual place) would be
        # compared with it for half of the offsets.
        shift = torch.arange(win)[:, None] - self.vshift + torch.arange(len(im))[None, :]
        real = (shift >= 0) & (shift < len(au)) & torch.tensor(loud)[None, :]
        counts = real.sum(1)
        if int(counts.min()) < self.min_voiced:
            real &= (counts >= self.min_voiced)[:, None]  # offsets with too few pairs drop out
            counts = real.sum(1)
        mdist = (dists * real).sum(1) / counts.clamp(min=1)
        mdist = torch.where(counts > 0, mdist, torch.full_like(mdist, float("nan")))
        ok = ~torch.isnan(mdist)
        minval, minidx = torch.min(torch.where(ok, mdist, torch.inf), 0)
        conf = float(torch.median(mdist[ok]) - minval)
        offset, min_dist = int(self.vshift - int(minidx)), float(minval)
        return {**out, "conf": conf, "offset": offset, "min_dist": min_dist}

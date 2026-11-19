"""Stands in for ``insightface.app.FaceAnalysis`` in the LatentSync worker (M6 step 7b).

LatentSync 1.6 finds the face with InsightFace's buffalo_l pack: SCRFD ``det_10g.onnx`` for the
box and ``2d106det.onnx`` for 106 landmarks (``latentsync/utils/face_detector.py``). The
insightface package is a source distribution only (a C++ build on Windows), so this module runs
the same two models with onnxruntime, on the CPU, and answers ``FaceAnalysis(...).get(frame)``
the way insightface 0.7.3 does: faces with ``bbox``, ``det_score`` and ``landmark_2d_106``.

Ported from insightface 0.7.3 (MIT licence, (c) insightface.ai / Jia Guo):
``model_zoo/scrfd.py`` (``SCRFD.forward / detect / nms``), ``model_zoo/landmark.py``
(``Landmark``) and ``utils/face_align.py`` (``transform`` with no rotation, ``trans_points2d``).
The weights are InsightFace's (non-commercial research licence; DECISIONS「M6 第 7b 步」).

``install(faces_dir)`` puts ``insightface`` and ``insightface.app`` into ``sys.modules`` before
LatentSync is imported; ``faces_dir`` holds the two ONNX files.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime

DETECTOR = "det_10g.onnx"
LANDMARKS = "2d106det.onnx"
_FACES_DIR: Path | None = None


def _session(path: Path) -> onnxruntime.InferenceSession:
    opts = onnxruntime.SessionOptions()
    opts.log_severity_level = 3
    return onnxruntime.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


class Face(dict[str, Any]):
    """insightface's ``Face``: a dict read as attributes."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def _distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


class Scrfd:
    """SCRFD as ``insightface.model_zoo.scrfd.SCRFD`` (det_10g: 9 outputs, strides 8/16/32, two
    anchors, keypoints; the keypoints are not needed and not decoded)."""

    def __init__(self, path: Path) -> None:
        self.session = _session(path)
        cfg = self.session.get_inputs()[0]
        self.input_name = cfg.name
        shape = cfg.shape
        self.input_size: tuple[int, int] | None = (
            None if isinstance(shape[2], str) else (int(shape[3]), int(shape[2]))
        )
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.batched = len(self.session.get_outputs()[0].shape) == 3
        outputs = len(self.output_names)
        if outputs in (6, 9):
            self.fmc, self.strides, self.anchors = 3, [8, 16, 32], 2
        elif outputs in (10, 15):
            self.fmc, self.strides, self.anchors = 5, [8, 16, 32, 64, 128], 1
        else:
            raise ValueError(f"{path.name}: {outputs} outputs is no SCRFD model")
        self.mean, self.std = 127.5, 128.0
        self.nms_thresh, self.det_thresh = 0.4, 0.5
        self._centers: dict[tuple[int, int, int], np.ndarray] = {}

    def prepare(self, input_size: tuple[int, int], det_thresh: float) -> None:
        if self.input_size is None:
            self.input_size = input_size
        self.det_thresh = det_thresh

    def _forward(self, img: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
        size = (img.shape[1], img.shape[0])
        blob = cv2.dnn.blobFromImage(
            img, 1.0 / self.std, size, (self.mean, self.mean, self.mean), swapRB=True
        )
        outs = self.session.run(self.output_names, {self.input_name: blob})
        height, width = blob.shape[2], blob.shape[3]
        scores_list, boxes_list = [], []
        for idx, stride in enumerate(self.strides):
            scores = outs[idx][0] if self.batched else outs[idx]
            preds = (outs[idx + self.fmc][0] if self.batched else outs[idx + self.fmc]) * stride
            h, w = height // stride, width // stride
            key = (h, w, stride)
            centers = self._centers.get(key)
            if centers is None:
                centers = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32)
                centers = (centers * stride).reshape((-1, 2))
                if self.anchors > 1:
                    centers = np.stack([centers] * self.anchors, axis=1).reshape((-1, 2))
                if len(self._centers) < 100:
                    self._centers[key] = centers
            keep = np.where(scores >= threshold)[0]
            scores_list.append(scores[keep])
            boxes_list.append(_distance2bbox(centers, preds)[keep])
        return np.vstack(scores_list), np.vstack(boxes_list)

    def detect(self, img: np.ndarray) -> np.ndarray:
        """Boxes ``[x1, y1, x2, y2, score]`` in the image's pixels, best first after NMS."""
        assert self.input_size is not None
        in_w, in_h = self.input_size
        if img.shape[0] / img.shape[1] > in_h / in_w:
            new_h = in_h
            new_w = int(new_h / (img.shape[0] / img.shape[1]))
        else:
            new_w = in_w
            new_h = int(new_w * (img.shape[0] / img.shape[1]))
        scale = new_h / img.shape[0]
        det_img = np.zeros((in_h, in_w, 3), dtype=np.uint8)
        det_img[:new_h, :new_w, :] = cv2.resize(img, (new_w, new_h))
        scores, boxes = self._forward(det_img, self.det_thresh)
        order = scores.ravel().argsort()[::-1]
        pre = np.hstack((boxes / scale, scores)).astype(np.float32, copy=False)[order, :]
        return pre[self._nms(pre), :]

    def _nms(self, dets: np.ndarray) -> list[int]:
        x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep: list[int] = []
        while order.size > 0:
            i = int(order[0])
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            order = order[np.where(ovr <= self.nms_thresh)[0] + 1]
        return keep


def _normalisation(path: Path) -> tuple[float, float]:
    """insightface ``Landmark.__init__``: a model that subtracts and scales in its own first
    nodes takes raw pixels (0, 1), others (127.5, 128)."""
    import onnx

    graph = onnx.load(str(path)).graph
    sub = mul = False
    for nid, node in enumerate(graph.node[:8]):
        if node.name.startswith("Sub") or node.name.startswith("_minus"):
            sub = True
        if node.name.startswith("Mul") or node.name.startswith("_mul"):
            mul = True
        if nid < 3 and node.name == "bn_data":
            sub = mul = True
    return (0.0, 1.0) if sub and mul else (127.5, 128.0)


class Landmark106:
    """``insightface.model_zoo.landmark.Landmark`` for the 2D 106-point model."""

    def __init__(self, path: Path) -> None:
        self.session = _session(path)
        cfg = self.session.get_inputs()[0]
        self.input_name = cfg.name
        self.size = int(cfg.shape[3])
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.mean, self.std = _normalisation(path)
        self.points = int(self.session.get_outputs()[0].shape[1]) // 2

    def get(self, img: np.ndarray, bbox: np.ndarray) -> np.ndarray:
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        cx, cy = (bbox[2] + bbox[0]) / 2, (bbox[3] + bbox[1]) / 2
        scale = self.size / (max(w, h) * 1.5)
        m = np.array(
            [[scale, 0.0, self.size / 2 - cx * scale], [0.0, scale, self.size / 2 - cy * scale]],
            dtype=np.float64,
        )
        aimg = cv2.warpAffine(img, m, (self.size, self.size), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(
            aimg, 1.0 / self.std, (self.size, self.size), (self.mean,) * 3, swapRB=True
        )
        pred = self.session.run(self.output_names, {self.input_name: blob})[0][0]
        pred = pred.reshape((-1, 2))[-self.points :, :].astype(np.float32)
        pred += 1
        pred *= self.size // 2
        im = cv2.invertAffineTransform(m)
        ones = np.ones((pred.shape[0], 1), dtype=np.float32)
        return (np.hstack([pred, ones]) @ im.T).astype(np.float32)


class FaceAnalysis:
    """``insightface.app.FaceAnalysis`` with ``allowed_modules=["detection",
    "landmark_2d_106"]``; ``root`` / ``providers`` / ``name`` are LatentSync's and ignored."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if _FACES_DIR is None:
            raise RuntimeError("latentsync_faces.install() was not called")
        self.det_model = Scrfd(_FACES_DIR / DETECTOR)
        self.landmark = Landmark106(_FACES_DIR / LANDMARKS)

    def prepare(
        self, ctx_id: int = 0, det_thresh: float = 0.5, det_size: tuple[int, int] = (640, 640)
    ) -> None:
        self.det_model.prepare(tuple(det_size), det_thresh)  # type: ignore[arg-type]

    def get(self, img: np.ndarray, max_num: int = 0) -> list[Face]:
        faces: list[Face] = []
        for row in self.det_model.detect(img):
            face = Face(bbox=row[0:4], det_score=row[4], kps=None)
            face["landmark_2d_106"] = self.landmark.get(img, face.bbox)
            faces.append(face)
        return faces


def install(faces_dir: str | Path) -> None:
    """Make ``from insightface.app import FaceAnalysis`` find this module's class."""
    global _FACES_DIR
    _FACES_DIR = Path(faces_dir)
    for name in (DETECTOR, LANDMARKS):
        if not (_FACES_DIR / name).is_file():
            raise FileNotFoundError(f"{_FACES_DIR / name} (setup item w_latentsync)")
    package = types.ModuleType("insightface")
    app = types.ModuleType("insightface.app")
    app.FaceAnalysis = FaceAnalysis  # type: ignore[attr-defined]
    package.app = app  # type: ignore[attr-defined]
    sys.modules["insightface"] = package
    sys.modules["insightface.app"] = app

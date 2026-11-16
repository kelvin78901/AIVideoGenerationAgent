# M6 自动质检本地工具调研（CPU、`runtimes/qa`）

日期：2026-11-15。只读调研：没装包、没下权重（权重的大小和 sha256 来自 Hugging Face API、GitHub Release API、Git LFS 指针和 HEAD 请求）。
每条事实后面标了出处；**标「未核实」的是我没在一手资料里找到的，别当事实用。**

## 1. 结论一览

| 工具 | 包 / 版本（cp312，win_amd64 · manylinux x86_64 · macOS arm64 都有 wheel） | 模型文件 + 大小 | 许可（代码 / 权重） | CPU 速度 | 结论 |
|---|---|---|---|---|---|
| 人脸检测 YuNet | `opencv-python-headless==4.14.0.94`（abi3） | `face_detection_yunet_2023mar.onnx`，232,589 B | MIT / MIT | i7-12700K 上 160×120 输入 0.69 ms（官方基准）；768p 帧缩到长边 640 后估计 < 10 ms（未核实） | **可用**。qa 环境用 OpenCV 4.x；OpenCV 5 的官方示例已改用 `2026may` |
| 人脸特征 AuraFace | `onnxruntime==1.31.0`（不装 `insightface`） | 只要 `glintr100.onnx`，260,694,151 B | 仓库 Apache-2.0 / Apache-2.0（只限这一个文件） | ResNet100、112×112，每张脸估计 50–150 ms（未核实） | **可用，但仓库里另外 4 个 onnx 是 InsightFace 原文件（非商用），不能下、不能用** |
| ASR | `faster-whisper==1.2.1` + `ctranslate2==4.8.5` + `av==19.0.2` | `Systran/faster-whisper-large-v3` 的 `model.bin`，3,087,284,237 B（fp16，加载时转 int8） | MIT / MIT | 没有 large-v3 在 CPU 上的一手数据；5 秒片段也要跑一次 30 秒窗口，估计几秒到十几秒（未核实） | **可用**；mp4 直接读，不需要 ffmpeg |
| 说话人 CAM++ | `sherpa-onnx==2.0.1` | `3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx`，28,281,138 B | Apache-2.0 / Apache-2.0 | 模型小（28 MB），估计每段 < 100 ms（未核实） | **可用，不用 torch**。官方判定阈值是 0.31，我们的配置写的是 0.6 |
| 口型 SyncNet | `torch==2.14.1`（CPU 版）+ `scipy` + MFCC | `syncnet_v2.model`，54,573,114 B | 代码 MIT / **权重写着“for research purposes”，CC BY** | 未核实 | **技术上可用，许可要 Kelvin 定**（见 6.5） |
| 画面文字 | 留在现有 `ocr` 环境（已锁 `opencv-python-headless 5.0.0.93`） | 不用新文件 | — | 每秒一帧 | 用 `cv2.VideoCapture` 抽帧，不用加 ffmpeg |

**要改的计划**：(1) AuraFace 只下 `glintr100.onnx`；(2) qa 环境的 OpenCV 锁在 4.14（或者改用 `2026may` 模型，两种都要实机冒烟）；(3) SyncNet 权重许可写的是“research purposes”，不满足“权重必须能商用”这条硬约束，要 Kelvin 决定；(4) `speaker_sim: 0.6` 和 `face_sim: 0.75` 两个阈值和模型的实际分值范围对不上，要标定。

---

## 2. 人脸检测：YuNet（OpenCV Zoo）

**包**：`opencv-python-headless`。PyPI 上最新是 5.0.0.93（2026-07-02）和 4.14.0.94（2026-07-28），都是 `cp37-abi3`，三个平台都有 wheel：`win_amd64`、`manylinux_2_28_x86_64`、`macosx_13_0_arm64`。代码 Apache 2.0，**所有 wheel 都带 FFmpeg（LGPL 2.1）**。
出处：https://pypi.org/project/opencv-python-headless/ ，https://pypi.org/pypi/opencv-python-headless/4.14.0.94/json ，https://raw.githubusercontent.com/opencv/opencv-python/4.x/README.md （第 235 行：“All wheels ship with FFmpeg licensed under the LGPLv2.1”）

**模型**：目录里现在有 `2026may`（默认，输入尺寸可变）、`2023mar`（输入尺寸固定）、`2023mar_int8`、`2023mar_int8bq` 四个文件，全部 MIT。README 原话：`2026may` “compatible with OpenCV 5.x ONNX Runtime engine”；`2023mar` “has fixed input shape”，OpenCV 4.x 的 DNN 按实际输入尺寸推理。OpenCV 5.x 自带的 `samples/dnn/face_detect.py` 默认用的就是 `2026may`。
出处：https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet ，https://raw.githubusercontent.com/opencv/opencv/5.x/samples/dnn/face_detect.py

| 文件 | 大小 | sha256 | 下载 |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | 232,589 | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | HF `opencv/face_detection_yunet` @ `3cc26e7f1014a5ee5d74a42acee58bafc9d0a310`（OpenCV 官方组织，sha 和 GitHub LFS 一致）；或 `https://github.com/opencv/opencv_zoo/raw/eb9f4f2d4b79b58e5513b5d25d5f0243a8357bf4/models/face_detection_yunet/face_detection_yunet_2023mar.onnx` |
| `face_detection_yunet_2026may.onnx` | 229,738 | `ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0` | 只在 GitHub（同一 commit）；HF 仓库里没有 |

sha256 取自 Git LFS 指针（`raw.githubusercontent.com/.../eb9f4f2.../face_detection_yunet_2023mar.onnx`）和 HF API（https://huggingface.co/api/models/opencv/face_detection_yunet?blobs=true）。

**OpenCV 版本选哪个**：本机 `ocr` 环境里的 OpenCV 5.0.0 有 `cv2.FaceDetectorYN`（实测 `hasattr` 为 True），但 **`2023mar` 在 5.0 上能不能用，我没法不下权重去验证**。一手资料能支持的组合只有两个：OpenCV 4.x + `2023mar`（Zoo README），或者 OpenCV 5.x + `2026may`（5.x 官方示例）。建议 qa 环境锁 `opencv-python-headless==4.14.0.94` + `2023mar`（HF 上有，cn 镜像能用），第 5 步第一件事是实机冒烟。

**输出格式**（`face.hpp`，5.x 分支）：`detect()` 返回 `[num_faces, 15]`：0–1 框左上角 x,y；2–3 宽高；4–5 右眼；6–7 左眼；8–9 鼻尖；10–11 右嘴角；12–13 左嘴角；14 分数。`create(model, config, input_size, score_threshold=0.9, nms_threshold=0.3, top_k=5000, backend_id=0, target_id=0)`；图片尺寸和创建时不一样就先调 `setInputSize`。
出处：https://raw.githubusercontent.com/opencv/opencv/5.x/modules/objdetect/include/opencv2/objdetect/face.hpp
这里的“右眼”指人物自己的右眼，也就是画面左边那只，和 ArcFace 模板的点序一样（见第 3 节），**不用重排**。

**注意**：
- README 说能检测的人脸大小“around 10x10 to 300x300” pixels。768p 的特写里脸可能超过 300 px，所以**先把帧缩到长边约 640 再检测**，再把关键点换算回原图做对齐。
- 速度：Zoo 基准里 i7-12700K 上 `2023mar` 输入 160×120 用 0.69 ms（https://raw.githubusercontent.com/opencv/opencv_zoo/main/benchmark/README.md 第 75 行）。按像素数推算，640×360 大约 8 ms（未核实）。

## 3. 人脸特征：AuraFace（fal）

**仓库**：HF `fal/AuraFace-v1`，revision `af6d057c9b0ec4071d4c49c80e3539258798b609`，`license: apache-2.0`，`LICENSE.md` 是标准 Apache 2.0，没有给第三方文件写例外。模型卡说它是“Resnet100 with Additive Angular Margin Loss (based on ArcFace)”，训练用的是“commercially and publicly available data sources to enable its usage in commercial setting”。
出处：https://huggingface.co/fal/AuraFace-v1 ，https://huggingface.co/fal/AuraFace-v1/raw/main/LICENSE.md ，https://huggingface.co/api/models/fal/AuraFace-v1?blobs=true

**哪个文件是识别模型，以及一个大坑**：仓库里有 5 个 onnx。拿 sha256 和 InsightFace `antelopev2` 的镜像（`DIAMONIK7777/antelopev2`）逐个对比：

| 文件 | AuraFace 仓库 sha256 | antelopev2 sha256 | 结论 |
|---|---|---|---|
| `glintr100.onnx` | `a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60`（260,694,151 B） | `4ab1d643…`（260,665,334 B） | **不一样：这是 AuraFace 自己的识别模型** |
| `scrfd_10g_bnkps.onnx` | `5838f7fe…` | `5838f7fe…` | 完全相同，是 InsightFace 的检测模型 |
| `1k3d68.onnx`、`2d106det.onnx`、`genderage.onnx` | `df5c06b8…`、`f001b856…`、`4fde69b1…` | 相同 | 完全相同，是 InsightFace 的模型 |

出处：https://huggingface.co/api/models/DIAMONIK7777/antelopev2?blobs=true 。InsightFace 的预训练模型只许非商用，不会因为 fal 的仓库标了 Apache 就变成可商用。所以：**只下 `glintr100.onnx`（和 `LICENSE.md`），不装 `insightface` 包，也不用 `FaceAnalysis(name="auraface")`**（它会把整个目录的 onnx 都加载进来）。检测换成 YuNet。

**预处理**：模型卡没写（官方示例走 InsightFace 的 `FaceAnalysis`，而且示例代码本身有 bug：对 ndarray 调了 `.convert`）。InsightFace 的做法（MIT 代码，可以照抄）：
- 对齐：`norm_crop` 按 5 个关键点估计相似变换（`skimage SimilarityTransform`），映射到 `arcface_dst = [[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]]`，再 `warpAffine` 成 112×112。出处：https://raw.githubusercontent.com/deepinsight/insightface/master/python-package/insightface/utils/face_align.py
- 归一化：`blobFromImages(imgs, 1/input_std, (112,112), (input_mean,)*3, swapRB=True)`，也就是 BGR 转 RGB。如果图的前 8 个节点里同时有 `Sub`/`_minus` 和 `Mul`/`_mul`（老的 MXNet 导出），就用 mean 0、std 1，否则用 127.5 / 127.5。出处：https://raw.githubusercontent.com/deepinsight/insightface/master/python-package/insightface/model_zoo/arcface_onnx.py
- OpenCV 自己的 `FaceRecognizerSF::alignCrop` 用的是同一组 5 点模板，输出也是 112×112（`modules/objdetect/src/face_recognize.cpp` 第 80 行）。这说明 YuNet 的 5 个点可以直接套 ArcFace 模板，**纯 numpy / cv2 就能对齐**。

**嵌入维度**：模型卡没写。ResNet100 ArcFace 通常是 512 维，worker 里从 `session.get_outputs()[0].shape` 读，别写死（未核实）。
**相似度**：L2 归一化后点积就是余弦，范围 [-1, 1]。fal 的博客评论里有人问“同一张图才 0.6”，没人给出答案（https://huggingface.co/blog/isidentical/auraface ）。**`face_sim: 0.75` 没有任何一手依据**，ArcFace 类模型同一个人的余弦分常常在 0.4–0.7 之间（未核实），必须用示例项目标定。

```python
ARC = np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]], np.float32)
det = cv2.FaceDetectorYN.create(yunet, "", (320, 320), 0.8, 0.3, 5000)        # init
so = ort.SessionOptions(); so.intra_op_num_threads = threads
rec = ort.InferenceSession(glintr100, so, providers=["CPUExecutionProvider"]); inp = rec.get_inputs()[0].name

def detect(bgr):                       # -> [(box, kps[5,2], score)] in full-res coords
    s = min(1.0, 640 / max(bgr.shape[:2])); small = cv2.resize(bgr, None, fx=s, fy=s) if s < 1 else bgr
    det.setInputSize((small.shape[1], small.shape[0])); _, f = det.detect(small)
    return [] if f is None else [(r[:4] / s, r[4:14].reshape(5, 2) / s, float(r[14])) for r in f]

def embed(bgr, kps):                   # unit 512-d (dim from the model)
    M, _ = cv2.estimateAffinePartial2D(kps.astype(np.float32), ARC, method=cv2.LMEDS)  # 4-DoF similarity
    crop = cv2.warpAffine(bgr, M, (112, 112), borderValue=0)
    e = rec.run(None, {inp: cv2.dnn.blobFromImage(crop, 1/127.5, (112, 112), (127.5,)*3, swapRB=True)})[0][0]
    return e / np.linalg.norm(e)
```

要和 InsightFace 的结果完全一致，就用 numpy 写 Umeyama 最小二乘（大约 10 行），代替 LMEDS。
**建议的输出**：每张参考图取最大的那张脸做嵌入；视频每 `every_s` 秒抽一帧，帧里每张脸都和每张参考图算余弦。`faces[{asset_id, name, sim}]` 里的 `sim` 取这个参考图在所有帧上的最高分（或者取前 3 高的平均，抗单帧误检）。参考图里找不到脸、或者视频里一张脸都没有，就给 `sim: null`（qa.py 会当成 na）。

## 4. ASR：faster-whisper large-v3

**包**：`faster-whisper` 1.2.1（2025-10-31，`py3-none-any`，MIT）。v1.2.1 的 `requirements.txt`：`ctranslate2>=4.0,<5`、`huggingface_hub>=0.21`、`tokenizers>=0.13,<1`、`onnxruntime>=1.14,<2`、`av>=11`、`tqdm`。
- `ctranslate2`：4.9.0 是 2026-11-10 刚发的；建议锁 **4.8.5**（2026-11-02）。三个平台的 cp312 wheel 都有（`win_amd64`、`manylinux_2_27/2_28_x86_64`、`macosx_11_0_arm64`），MIT。
- `av`（PyAV）19.0.2：`cp312-abi3`，`win_amd64`、`manylinux_2_28_x86_64`、`macosx_14_0_arm64`，BSD-3；“Binary wheels … with FFmpeg bundled”。
出处：https://pypi.org/project/faster-whisper/ ，https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/requirements.txt ，https://pypi.org/project/ctranslate2/#history ，https://pypi.org/project/av/

**模型**：HF `Systran/faster-whisper-large-v3` @ `edaa852ec7e145841d8ffdb056a99866b5f0a478`，MIT。文件：`config.json`（2,394 B）、`model.bin`（3,087,284,237 B，sha256 `69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1`）、`preprocessor_config.json`、`tokenizer.json`、`vocabulary.json`。
出处：https://huggingface.co/api/models/Systran/faster-whisper-large-v3?blobs=true

**能不能直接读 mp4**：能。README：“Unlike openai-whisper, FFmpeg does not need to be installed on the system”。`decode_audio(input_file, sampling_rate=16000, split_stereo=False)` 用 `av.open` 打开文件，只解码 `container.decode(audio=0)`，再重采样成 16 kHz 单声道 s16，最后转成 float32、范围 [-1, 1]。`transcribe(audio)` 接受路径、文件对象或 ndarray。出处：https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/faster_whisper/audio.py
**参数**：`WhisperModel(model_size_or_path, device="auto", compute_type="default", cpu_threads=0, local_files_only=False, …)`；`transcribe(language=None, beam_size=5, vad_filter=False, condition_on_previous_text=True, initial_prompt=None, …)`；传 `language="zh"` 就不做语言检测。VAD 用的 `silero_vad_v6.onnx`（1.2 MB）在 wheel 自带的 `faster_whisper/assets/` 里，不联网。出处：https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/faster_whisper/transcribe.py ，https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1/faster_whisper/assets

```python
model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=8, local_files_only=True)  # init
segments, info = model.transcribe(mp4_path, language="zh", beam_size=5, vad_filter=True,
                                  condition_on_previous_text=False)
text = "".join(s.text for s in segments)   # a generator: decoding happens while iterating
```

**注意**：
- 速度：README 只有 small 模型在 CPU 上的数据（13 分钟音频，i7-12700K 8 线程，int8 用 1m42s、1477 MB 内存）。**large-v3 在 CPU 上没有一手数据。** 5 秒的片段也要跑一整个 30 秒窗口的编码器，第 5 步要实测。fp16 的 `model.bin` 在加载时转成 int8，第一次加载会慢一些；worker 常驻，只加载一次。
- Whisper 输出中文时可能夹繁体，`cer()` 只做 NFKC，繁简不同会算成错字。可以用简体的 `initial_prompt` 引导，或者在算 CER 前做繁简归一（未核实效果）。
- `local/whisper-large-v3` 也是 `asr` 组件 `balanced` 预设的本地模型（components.yaml 第 405–406 行），worker 的 `asr` 处理要兼容那边发来的请求。

## 5. 说话人相似度：CAM++（3D-Speaker）走 sherpa-onnx，不用 torch

**原模型**：ModelScope `iic/speech_campplus_sv_zh-cn_16k-common`，README 写着 `license: Apache License 2.0`；训练用了“约200k个说话人”的中文数据，CN-Celeb 测试集 EER 4.32%。`configuration.json`：`sample_rate 16000`、`fbank_dim 80`、`emb_size 192`、**`yesOrno_thr: 0.31`**（示例里也是 `thr=0.31`），权重文件是 `campplus_cn_common.bin`。3D-Speaker 仓库本身是 Apache 2.0。
出处：https://www.modelscope.cn/models/iic/speech_campplus_sv_zh-cn_16k-common/resolve/master/README.md ，…/resolve/master/configuration.json ，https://github.com/alibaba-damo-academy/3D-Speaker

**ONNX 导出**：sherpa-onnx 的 `scripts/3dspeaker/export-onnx.py` 直接从 ModelScope 导出这个模型（支持列表里有 `iic/speech_campplus_sv_zh-cn_16k-common`）。它会写入元数据：`sample_rate`、`normalize_samples=1`（输入是 [-1, 1] 的浮点数）、`feature_normalize_type=global-mean`、`output_dim`。出处：https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/master/scripts/3dspeaker/export-onnx.py

| 文件 | 大小 | sha256 | 下载 |
|---|---|---|---|
| `3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx` | 28,281,138 | `f682b514c05d947ee3fa91cd6ec6c5c7543479a128373fa29b1faedccd21fd11` | `https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx`（tag 名里的拼写错误是官方原样）；HF `csukuangfj/speaker-embedding-models` @ `0743f301363dec56491a490f6d6cbc9d67f9a3bf` 有同一个文件，sha 相同（csukuangfj 是 sherpa-onnx 的维护者） |

sha256 取自 Release 里的 `checksum.txt` 和 HF API；文件大小用 HEAD 请求核对过。

**包**：`sherpa-onnx` 2.0.1（2026-10-26，Apache），cp312 wheel：`win_amd64`、`manylinux2014_x86_64`、`macosx_11_0_arm64`（另有 universal2），PyPI 上没声明依赖（自带 onnxruntime 的 C 库）。出处：https://pypi.org/project/sherpa-onnx/

```python
cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=campplus_onnx, num_threads=2, provider="cpu")
ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)                    # init (cfg.validate() first)
def emb(x):                                                          # float32 mono 16 kHz in [-1, 1]
    st = ext.create_stream(); st.accept_waveform(sample_rate=16000, waveform=x); st.input_finished()
    v = np.asarray(ext.compute(st), np.float32); return v / np.linalg.norm(v)   # 192-d
clip = faster_whisper.audio.decode_audio(mp4_path, sampling_rate=16000)    # PyAV, same env
```

接口调用顺序照抄 `python-api-examples/speaker-identification.py`（https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/master/python-api-examples/speaker-identification.py ，那里用 `SpeakerEmbeddingManager.search(threshold=0.6)` 判断，但那是 sherpa 自己示例的默认值，不是 CAM++ 的标定值）。
**建议的输出**：`sims[{who, sim}]`，`sim` 是余弦，范围 [-1, 1]。一个镜头里可能有好几个人说话，整段音频的嵌入会混在一起。建议把音频切成约 1.5 秒的窗口、步长 0.75 秒，每个 `who` 取各窗口里的最高分（窗口长度未核实，要标定）。**我们配置里的 `speaker_sim: 0.6` 比模型卡的 0.31 严格得多，要标定。**

## 6. 口型同步：SyncNet（`joonson/syncnet_python`）

### 6.1 代码和权重
- 代码：MIT（`LICENSE.md`：“Copyright (c) 2016-present Joon Son Chung”）。https://github.com/joonson/syncnet_python
- 权重：`download_model.sh` 从 `http://www.robots.ox.ac.uk/~vgg/software/lipsync/data/syncnet_v2.model` 下载；HEAD 结果是 54,573,114 B，Last-Modified 2019-02-22。官方没发布 sha256。HF `ByteDance/LatentSync-1.6` @ `c42c7e6c8e9c213626389fa7d9a3c444b8536353` 里的 `auxiliary/syncnet_v2.model` 大小一样，sha256 是 `961e8696f888fce4f3f3a6c3d5b3267cf5b343100b238e79b2659bff2c605442`（https://huggingface.co/api/models/ByteDance/LatentSync-1.6?blobs=true ）。两边是不是同一个文件，我推断是，但没核实。
- 另外还有 `sfd_face.pth`（S3FD 检测器），我们用 YuNet 代替，不下。

### 6.2 conf 是什么意思
`SyncNetInstance.evaluate`：每个 5 帧的视频窗口和 ±`vshift` 个音频偏移算欧氏距离，按偏移在所有帧上取平均得到 `mdist`；`minval, minidx = min(mdist)`；`offset = vshift - minidx`（单位是 25 fps 的帧）；**`conf = median(mdist) - minval`**，也就是最佳偏移比“随便一个偏移”近多少。`run_syncnet.py` 的默认值是 `vshift=15`、`batch_size=20`。官方示例视频的结果是 offset 3、min dist 5.353、conf 10.021。出处：https://raw.githubusercontent.com/joonson/syncnet_python/master/SyncNetInstance.py ，…/run_syncnet.py ，README。
**conf ≥ 6 这个阈值在 syncnet_python 里找不到**，它是业界的经验值（LatentSync 等用 SyncNet 置信度当 Sync-C 指标），未核实。

### 6.3 输入
- 视频：25 fps（文件头注释写着“Video 25 FPS, Audio 16000HZ”；`run_pipeline.py` 先用 ffmpeg 转成 `-r 25`）。人脸裁剪：框中心 (mx, my)，`bs` 是框尺寸的一半（经过中值滤波），`cs=0.4`，取 `frame[my-bs : my+bs*(1+2cs), mx-bs*(1+cs) : mx+bs*(1+cs)]`（四周先填充 110），再 resize 成 **224×224 的整张脸（不是只裁嘴）**；**BGR、0–255、不归一化**；张量形状 `(1, 3, T, 224, 224)`，每个窗口 5 帧。
- 音频：16 kHz 单声道 **int16**（`wavfile.read`），`python_speech_features.mfcc(audio, 16000)` 用默认参数（13 维，10 ms 步长）。每个视频帧对应 4 个 MFCC 帧，每个窗口 20 个，形状 `(N, 1, 13, 20)`。`decode_audio` 给的是 [-1, 1] 的浮点数，**要乘 32768 才能和原实现对上**（因为有对数能量项）。
- 设备：`self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')`；`torch.load(..., map_location=..., weights_only=True)`。没有写死 `.cuda()`，CPU 能跑。

我们的视频不是 25 fps 的话，按时间戳 k×40 ms 取最近的一帧，不用 ffmpeg 转码；帧用 `cv2.VideoCapture` 读，音频用 PyAV 读。画面里有几张脸时，每条人脸轨迹（按 IoU 连起来）各算一次，取 conf 最高的那条（相当于原实现里的 active speaker）。

### 6.4 torch 和 ONNX
- 必须用 torch（网络在 `SyncNetModel.py`，Conv3d 和 Conv2d）。最小的 CPU 版：PyTorch 的 CPU 源 `https://download.pytorch.org/whl/cpu` 上的 `torch 2.14.1`：`+cpu-cp312-win_amd64` 124.0 MB，`+cpu-manylinux_2_28_x86_64` 196.3 MB，`cp312-macosx_14_0_arm64` 127.2 MB（三个都 HEAD 过）。不要 torchvision 和 torchaudio。Linux 上要是直接从 PyPI 装 torch，会带上 CUDA 依赖，体积是好几 GB。uv 的写法参照 https://docs.astral.sh/uv/guides/integration/pytorch/ 和仓库里的 `runtimes/qwentts/pyproject.toml`。
- `python_speech_features` 只在 PyPI 上发了 0.6 的 sdist（2017 年，没有 wheel，代码 import numpy 和 scipy），uv 能从 sdist 构建，但这个包已经不维护了。**建议把 `SyncNetModel.py`（约 110 行）和 MFCC（约 40 行 numpy + `scipy.fft.dct`）抄进 worker，保留 MIT 版权声明**，不 clone 仓库，也不装 `python_speech_features`。
- ONNX：在一手来源里**没找到可信的导出版本**（HF 上只有 PyTorch 权重的转存）。可以自己用 `torch.onnx.export` 导出 `forward_lip` 和 `forward_aud` 两个图，这样 qa 环境就不需要 torch 了。但导出的文件要有地方放（比如 Kelvin 自己的 HF 仓库），这又牵涉到重新分发权重的许可，见下一节。

### 6.5 许可：硬约束不满足（要 Kelvin 决定）
VGG 官方页面原话：“The model can be used for research purposes under Creative Commons Attribution License”，页面还感谢 BBC Research 帮忙“in obtaining the dataset”（https://www.robots.ox.ac.uk/~vgg/software/lipsync/ ）。BBC 的 LRS2 数据集只许“non-commercial, academic research”（https://www.robots.ox.ac.uk/~vgg/data/lip_reading/lrs2.html ）。CC BY 本身允许商用，但“research purposes”这个限定写在前面，所以**权重能不能商用不明确**，性质和 InsightFace 的情况接近。LatentSync 仓库把同一个文件放在 `openrail++` 下，这不改变 VGG 原来的条款。
可选的路：(a) Kelvin 认为质检度量不进成片、可以接受，照用并在 DECISIONS 里记一笔；(b) 本地口型检查先关掉（`tools.lipsync` 不配），靠 VLM 看；(c) 换 LatentSync 的 `stable_syncnet.pt`（1.6 GB，openrail++，要 torch，输入和打分口径完全不同，conf 6 的阈值不能用），我不推荐。

## 7. 画面文字：给 `worker_rapidocr` 加视频输入

- `ocr` 环境的锁里已经有 `opencv-python-headless 5.0.0.93`（rapidocr 间接依赖），wheel 自带 FFmpeg。本机实测 `cv2.videoio_registry.getStreamBackends()` 里有 `FFMPEG`（Windows 上还有 `MSMF`）。
- RapidOCR 收到 3 通道 `np.ndarray` 时**按 BGR 原样用**（`rapidocr/utils/load_image.py` 的 `convert_img`：只有 str/Path/bytes/PIL 才做 RGB→BGR），所以 `VideoCapture` 读出来的帧可以直接交给它。
- 抽帧：`cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)`，顺序 `grab()`，用 `CAP_PROP_POS_MSEC` 判断有没有到下一个 `k*every_s`，到了才 `retrieve()`。5 秒的片段不用 seek，顺序读最稳（seek 在部分编码下不精确，这条未核实）。返回 `{"frames": [{"t": 0.0, "text": ...}, ...], "text": 所有帧的文字拼起来}`。
- 怎么区分图片和视频：`params` 里有 `every_s` 就当视频处理（QA 只在视频上传 `every_s`），否则保持现在的图片行为。
- **留在 `ocr` 环境**：不用新依赖，也不用新权重；`rt_ocr` 是必装项，而且没有 API 兜底。放进 qa 环境反而要再装一份 rapidocr。建议在 `runtimes/ocr/pyproject.toml` 里把 `opencv-python-headless==5.0.0.93` 写成显式依赖，免得 rapidocr 以后换掉依赖时 `cv2` 跟着消失。

---

## 8. 建议的 `runtimes/qa/pyproject.toml`

```toml
# QA tools worker environment, CPU only (setup item rt_qa, worker workers/worker_qa.py): YuNet + AuraFace
# (onnxruntime), faster-whisper (CTranslate2 int8), CAM++ (sherpa-onnx), SyncNet (CPU torch).
[project]
name = "drama-studio-rt-qa"
version = "0"
requires-python = "==3.12.*"
dependencies = [
    "opencv-python-headless==4.14.0.94",  # YuNet 2023mar is the OpenCV 4.x model (opencv_zoo README)
    "onnxruntime==1.31.0",                # same as the ocr env; faster-whisper wants >=1.14,<2
    "faster-whisper==1.2.1",
    "ctranslate2==4.8.5",                 # 4.9.0 is days old
    "av==19.0.2",                         # PyAV with FFmpeg bundled: audio from the mp4, no ffmpeg
    "sherpa-onnx==2.0.1",
    "torch==2.14.1",                      # SyncNet only; CPU build (matches 2.14.1+cpu)
    "scipy==1.18.1",                      # SyncNet MFCC dct + medfilt
    "numpy>=2,<3",
]

[tool.uv]
package = false
environments = [
    "sys_platform == 'win32' and platform_machine == 'AMD64'",
    "sys_platform == 'linux' and platform_machine == 'x86_64'",
    "sys_platform == 'darwin' and platform_machine == 'arm64'",
]

[tool.uv.sources]
torch = { index = "pytorch-cpu" }         # the CPU index also carries the macOS arm64 wheel

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

所有包在三个平台上都核对过有 cp312（或 abi3）wheel（PyPI JSON 和 PyTorch CPU 源的索引）。**macOS 的下限是 14**（onnxruntime 1.31、av 19、torch 2.14.1 的 arm64 wheel 都标的 `macosx_14_0`）。如果 Kelvin 选 6.5 的 (b)，就删掉 torch、scipy 和 `[tool.uv.sources]`。

## 9. 建议的清单和路由项

`config/setup-manifest.yaml`（`rt_qa` 接在 `rt_ocr` 后面，`w_qa` 放进 `w` 组。`url:` 下载不走镜像，见第 10 节，所以能走 HF 的都走 HF）：

```yaml
  - id: rt_qa
    group: rt
    name: { zh: 自动质检运行环境（人脸、口型、语音）, en: QA tools runtime (face, lip sync, speech) }
    required: true
    depends_on: [uv]
    # YuNet + AuraFace（onnxruntime）、faster-whisper（CTranslate2 int8）、CAM++（sherpa-onnx）、SyncNet（CPU 版 PyTorch），只用 CPU。
    detect: { type: py_import, env: qa, module: sherpa_onnx }
    install:
      - { type: uv_sync, env: qa, project: runtimes/qa, python: "3.12" }
  - id: w_qa
    group: w
    name: { zh: 自动质检模型, en: QA models }
    required: true
    # 不走 ComfyUI，放 {models}/qa；AuraFace 只下 glintr100.onnx（同仓库另外 4 个 onnx 是 InsightFace 的非商用原文件）。
    detect: { type: downloads }
    size_gb: 3.4
    install:
      - type: download
        hf_repo: opencv/face_detection_yunet
        revision: 3cc26e7f1014a5ee5d74a42acee58bafc9d0a310
        dest: "{models}/qa"
        files:
          - { path: face_detection_yunet_2023mar.onnx, sha256: 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 }   # 0.00 GB
      - type: download
        hf_repo: fal/AuraFace-v1
        revision: af6d057c9b0ec4071d4c49c80e3539258798b609
        dest: "{models}/qa/auraface"
        files:
          - { path: LICENSE.md }
          - { path: glintr100.onnx, sha256: a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60 }   # 0.26 GB
      - type: download
        hf_repo: csukuangfj/speaker-embedding-models
        revision: 0743f301363dec56491a490f6d6cbc9d67f9a3bf
        dest: "{models}/qa"
        files:
          - { path: 3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx, sha256: f682b514c05d947ee3fa91cd6ec6c5c7543479a128373fa29b1faedccd21fd11 }   # 0.03 GB
      - type: download                     # 许可见 DECISIONS（6.5）；sha256 取自 HF LatentSync-1.6 的同名文件，VGG 没发布
        url: https://www.robots.ox.ac.uk/~vgg/software/lipsync/data/syncnet_v2.model
        dest: "{models}/qa"
        sha256: 961e8696f888fce4f3f3a6c3d5b3267cf5b343100b238e79b2659bff2c605442   # 0.05 GB
      - type: download
        hf_repo: Systran/faster-whisper-large-v3
        revision: edaa852ec7e145841d8ffdb056a99866b5f0a478
        dest: "{models}/faster-whisper-large-v3"
        files:
          - { path: config.json }
          - { path: model.bin, sha256: 69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1 }   # 3.09 GB
          - { path: preprocessor_config.json }
          - { path: tokenizer.json }
          - { path: vocabulary.json }
```

Whisper 也给 `asr` 组件用，可以考虑单独拆成 `w_asr`（3.1 GB）。这样 `w_qa` 只有 0.35 GB，Mac 上只想要质检的人不用下 3 GB。

`config/providers.yaml`（每个模型 key 起一个 worker 进程，`local_python.py`：“One worker per model”。worker 在 `init` 时按 `args.tool` **只 import 自己用的库**，faster-whisper 的 onnxruntime 和 sherpa-onnx 自带的 onnxruntime 就不会进同一个进程）：

```yaml
  - { key: local/auraface, kind: qa_face, display: AuraFace 人脸（本地）, runtime: python, worker: worker_qa, env: qa, gpu: false,
      args: { tool: face, detector: "{models}/qa/face_detection_yunet_2023mar.onnx", recognizer: "{models}/qa/auraface/glintr100.onnx", threads: 4 },
      needs: [rt_qa, w_qa] }
  - { key: local/syncnet, kind: qa_sync, display: SyncNet 口型（本地）, runtime: python, worker: worker_qa, env: qa, gpu: false,
      args: { tool: sync, detector: "{models}/qa/face_detection_yunet_2023mar.onnx", weights: "{models}/qa/syncnet_v2.model", vshift: 15, batch: 20, threads: 4 },
      needs: [rt_qa, w_qa] }
  - { key: local/campplus, kind: qa_speaker, display: CAM++ 说话人（本地）, runtime: python, worker: worker_qa, env: qa, gpu: false,
      args: { tool: speaker, model: "{models}/qa/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx", window_s: 1.5, hop_s: 0.75 },
      needs: [rt_qa, w_qa] }
  - { key: local/whisper-large-v3, kind: asr, display: Whisper large-v3（本地）, runtime: python, worker: worker_qa, env: qa, gpu: false,
      args: { tool: asr, model_dir: "{models}/faster-whisper-large-v3", compute_type: int8, beam_size: 5, vad: true, threads: 8 },
      needs: [rt_qa, w_qa] }
  # local/rapidocr 不变（worker_rapidocr 加视频分支）
```

worker 的 handler 按 `kind` 注册：`{"qa_face": …, "qa_sync": …, "qa_speaker": …, "asr": …}`。返回值对齐 `pipeline/qa.py` 的 `Measure`：`qa_face → json.faces[{asset_id,name,sim}]`；`qa_sync → json{conf, offset, min_dist}`；`asr → text`（`json.segments` 可选）；`qa_speaker → json.sims[{who,sim}]`；`ocr → json.frames[{t,text}]`。

## 10. 待定问题和风险（没核实的都在这里）

1. **SyncNet 权重许可**（6.5）：要 Kelvin 拍板，(a)、(b)、(c) 三选一。没定之前建议 `tools.lipsync` 在真实模式下显示「未检查」。
2. **YuNet `2023mar` 和 OpenCV 5.0**：没验证（不能下权重）。建议的组合（4.14 + 2023mar）有一手资料支持；第 5 步先冒烟，失败就换成 5.0 + `2026may`（只在 GitHub 上，`url:` 下载在国内不走镜像）。
3. **AuraFace 的输入归一化**：InsightFace 靠扫图里的 `Sub`/`Mul` 节点来决定用 mean 0 / std 1 还是 127.5 / 127.5。我没法不下文件去看。第 5 步用 `onnx.load` 在开发机上看一次（不进运行环境），再把结果写死在 args 里；还要确认嵌入维度。
4. **阈值**：`face_sim 0.75`、`speaker_sim 0.6` 都没有一手依据（CAM++ 官方是 0.31）；`syncnet_conf 6` 是经验值。要用示例项目里的正例和反例标定，产品默认值请 Kelvin 确认。
5. **两份 onnxruntime**：`onnxruntime` 包和 sherpa-onnx 自带的 C 库在 Windows 上放进同一个进程，可能会撞 DLL，没找到一手说明（sherpa FAQ 只提到过机器上有两份 `onnxruntime.dll` 的问题：https://csukuangfj.github.io/sherpa/onnx/faqs/index.html ）。按工具分进程、只 import 自己用的库就能避开，Windows 上第 5 步还要实测一次。
6. **CPU 速度**：large-v3、AuraFace、SyncNet 在桌面 CPU 上跑 5 秒 768p 片段，都没有一手数据。第 5 步在 5090 那台机器的 CPU 上计时，写进报告。
7. **`url:` 下载不走镜像**（`steps.py` 里 `download_plan` 只对 `hf_repo` 套镜像）。SyncNet 的 VGG 地址在国内可能很慢；换成 HF `ByteDance/LatentSync-1.6` 的 `auxiliary/syncnet_v2.model` 能走镜像，但那个仓库标的是 openrail++ 许可，而且两个文件是不是完全相同还没核实（只知道大小一样）。
8. **说话人混音**：多人对白时整段嵌入不可靠，窗口切分的参数要标定（第 5 节）。
9. **Whisper 繁简**（第 4 节）：CER 可能被繁简差异放大。
10. **python_speech_features 默认参数**：master 上的 `mfcc(signal, samplerate=16000, winlen=0.025, winstep=0.01, numcep=13, nfilt=26, nfft=None, lowfreq=0, highfreq=None, preemph=0.97, ceplifter=22, appendEnergy=True)`，DCT 用的是 `scipy.fftpack.dct`（https://raw.githubusercontent.com/jameslyons/python_speech_features/master/python_speech_features/base.py ）。master 的 `nfft=None` 会按窗长算（16 kHz 时是 512）；PyPI 0.6 那一版写死的是不是 512，没核实。照抄时用 0.6 sdist 里的源码，再拿官方 `example.avi` 对一下 conf 是不是 10.021 左右。

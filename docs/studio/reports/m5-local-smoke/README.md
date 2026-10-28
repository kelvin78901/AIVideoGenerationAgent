# M5 本机检查（Kelvin 的 PC：RTX 5090、Comfy Desktop 0.41.2；都没调视频 API）

仓库里只放每轮的说明和压缩过的对照图（JPEG，每张 ≤ 300 KB）。**原片和原图不进 git**（`.gitignore` 挡着 `originals/`），在 Kelvin 本机：

`C:\dev\drama-studio\docs\studio\reports\m5-local-smoke\originals\<轮次>\`，文件名和这里的 JPEG 同名（`.mp4` 是片子，`.png` 是原图）。

| 轮次 | 做了什么 | 说明 |
|---|---|---|
| `run1-1-01_1-04/` | 第 14a 步：工作台第一次在本机出 1-01（`comfy/h3`）、1-04（`comfy/h3-r2v`），Turbo 8 步 / 4 步 | `../m5-local-smoke.txt` |
| `run2-1-04-ab/` | 1-04 同种子 A/B：3 个种子 × 原提示词 / 加「一镜到底」 | `../m5-local-smoke.txt` 末尾 |
| `run3-workflows/` | 关 Turbo，换社区热度高的工作流：官方 20 步、SEED HUNTER、SEEDVR2 超分、关 SageAttention | `run3-workflows/README.md` |
| `run4-1-04-cut/` | 1-04 为什么第 2 秒就切走：去场景图、改参考图写法、钉首帧、按官方写法重写，各 2 个种子 | `run4-1-04-cut/README.md` |

每张 `*.jpg` 的拼图是每秒两帧，从左到右、从上到下；`kf-*` 是关键帧候选，`take-*-poster` / `last_frame` 是首帧和尾帧，`1-04-face-*` 是 1:1 裁的脸部对比（左右两张）。

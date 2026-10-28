# 第三轮：换工作流、不开 Turbo（2026-10-27，本机 ComfyUI，没调 API）

输入和第一轮一样：同一个首帧、同一个提示词、同一个配音和音色样本、同一个种子（1-01 是 325085565，1-04 是 191503631），从 ComfyUI 的历史记录里原样取出，只改采样配方。片子是 `*.mp4`（不进 git），每两帧一秒的拼图是同名 `.png`。耗时记录见 `runs.txt`。

| 文件后缀 | 来源 | 配方 | 输出 | 1-01 / 1-04 耗时 |
|---|---|---|---|---|
| `official20` | 官方模板（docs.comfy.org 的 H3 指南） | 关 Turbo，res_multistep + simple，20 步 | 768×1344 | 153 / 184 秒 |
| `official20_pt` | 同上 | 再把 SageAttention 换成 PyTorch 注意力 | 768×1344 | 274 / 346 秒 |
| `seedhunter20` | Civitai 下载量第一 SEED HUNTER v2.5.1（3.67 万次） | 关它默认的 DMAD 4 步 LoRA，er_sde + beta，20 步 | 768×1344 | 156 / 184 秒 |
| `seedhunter_full` | 同上，完整两段 | 上一行 + H3 潜空间放大到 2 MP + er_sde / linear_quadratic 6 步、去噪 0.4 精修；声音取第一段 | 1088×1920 | 301 / 352 秒 |
| `seedvr2` | Civitai「MiniMax H3 with SEEDVR2 upscaler」v5（4.7k） | `official20` 的片子 + SeedVR2 7B（int8）一步修复放大，lab 调色 | 1080×1920 | 另加 194 / 211 秒 |

第一轮（Turbo，8 步 / 4 步）的片子在 `../run1-1-01_1-04/`，用来对照。

## 看到的

- **1-04 跑走不是步数的问题**：不开 Turbo 的 4 种配方，第 2 秒左右都会切走（官方配方镜头转到空楼梯，SEED HUNTER 的跳成楼梯全景），和 Turbo 那条后半段跑到门口一样。换采样器、换注意力都改不了，问题在提示词或 R2V 这条路线上。
- **SageAttention 不是元凶**：换成 PyTorch 注意力后，构图和动作几乎一模一样（1-01 PSNR 39.5 dB），只是慢了 1.8 倍。
- **清晰度**：SeedVR2 一步修复放大后，睫毛、发丝、皮肤纹理明显变清楚，脸没变；SEED HUNTER 的潜空间放大和精修只比直接放大清楚一点。
- **声音**：不开 Turbo 时声音走 20 步（官方说说话和音色要 12 步以上，8 步时声音常是短板），乱码是不是因此消失，要 Kelvin 听一下 1-04。

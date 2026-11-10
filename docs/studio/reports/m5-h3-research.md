# MiniMax H3 本地生成：口型、流畅度、长视频一致性调研（M5，2026-11-09）

起因：Kelvin 看完第 1 集 9 个镜头后反馈「口型和台词对不上、动作不顺、画面乱跳」，并问长视频怎么保持一致、流畅。
这份报告只调研，没改代码。

**标记**：
- 【官方】MiniMax 的模型卡 / GitHub / 提示词指南，或 Comfy-Org 的文档、模板、仓库（ComfyUI 是官方集成方）。
- 【本机代码】直接读本机 ComfyUI 0.41.2 源码核对过：`C:\Users\kelvin\AppData\Local\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\`。
- 【社区】个人的 HF 讨论、GitHub issue、博客、节点包。作者自测，没有独立复现。
- 【未核实】页面打不开，或只有二手转述。

我们现在的配置（对照用）：20 步、`res_multistep` + `simple`、BasicGuider、不开 Turbo、768×1344、24 fps、长度 17k+5 帧（124 帧 = 5.17 s、175 帧 = 7.29 s）。权重：DiT `minimax_h3_fl2va_pruned_int8_convrot`，文本编码器 `qwen3vl_32b_minimax_h3_nvfp4_awq`，视频 VAE `minimax_h3_video_vae_int8_convrot`，音频 VAE fp32。本机 torch 2.12.1+cu130，启用 SageAttention（见 ComfyUI 日志）。

---

## 0. 结论先说

1. **口型对不上，最可能的原因是走法本身。** `先配音`（tts）那条路把台词音频接到 `MiniMaxH3AddGuide` 上，这只是**条件引导**，不是锁定：模型会重新生成自己的音轨，嘴型跟着它自己生成的那条走。官方文档写明 AddGuide「不是视频到视频」。社区的做法是**音频锁定**：把编码好的台词音频放进 AV 潜变量的音频流，再用 `noise_mask = 0` 冻结，只生成画面，最后混音时用原始的配音文件。本机 0.41.2 用核心节点就能拼出来（`VAEEncodeAudio` + `SetLatentNoiseMask` + `LTXVConcatAVLatent`，后者的说明里写了支持 MiniMax H3），见第 3 节。
2. **「乱跳」大多是镜头内的意外硬切，加上动作分配不当。** 官方指南：FL2VA/I2V 尽量一个镜头到底；只是景别或角度小变化时，用运镜代替切镜头；只有明确需要时才写多个 `[Shot N]`。社区实测：用「then」串起来的动作会被切成多个镜头；模型常在约 1.2 s 内做完一个小动作然后定住。我们每拍都写、350–500 词的长提示词，很可能把一个镜头拆成了好几段。见第 4、6 节。
3. **画质规格不是主要原因。** 剪枝（pruned）是数学上的等价折叠，作者说偏差和换一个注意力内核差不多；int8+ConvRot 和 bf16 的差距也小。**反而**在本机 0.41.2 上，未剪枝的完整 checkpoint（bf16 / int8）有每 17 帧一次的闪暗 / 卡顿 bug，剪枝版不受影响，所以别换回完整版。int8 视频 VAE 和 fp16 版的差距是 67.7 dB PSNR，看不出来。值得换的是**文本编码器**：nvfp4 编码器处理长提示词时，中文约每 100 词错 3.1 个，可能读错台词。int8_convrot 编码器 25.3 GB，32 GB 卡放得下。见第 1 节。
4. **长视频衔接**：官方只给了「上一段最后 22 帧连声音，钉在第 0 帧」这一种用法（和我们一样）。本机那个叫 `video_minimax_h3_i2v_continuation` 的官方模板，实际只是首帧 / 尾帧图生视频，没有片段引导。社区成熟的做法有：直接传潜变量，不经 mp4 和 VAE 来回编码，避免色偏和接缝；音频上下文比画面短一点（18 帧）；每段换种子；每段都用 Ref2VA 带同一张角色参考；一条链最多 4 段左右，场景切换时重开一条链。见第 5 节。

---

## 1. 权重版本、精度损失、显存

### 1.1 有哪些权重

- 【官方】MiniMax 只发了两套 **BF16、已做 CFG 蒸馏**的 checkpoint：`FL2VA`（t2va / fl2va）和 `Ref2VA`（ref2va）。模型卡原文是「The released checkpoints are CFG-distilled Omni Transformer model weights」。33B 稠密模型，其中约 13B 在 AdaLN 分支里。H3-Context-IR（提示词预处理）和 H3-Regenerate-2K（2K 超分）没有开源。<https://huggingface.co/MiniMaxAI/MiniMax-H3>，<https://github.com/MiniMax-AI/MiniMax-H3>
  - 还没有官方的未蒸馏 base：社区在讨论区追问，见 [#88](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/88)、[#97](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/97)。
- 【官方】Comfy-Org 重新打包的版本：<https://huggingface.co/Comfy-Org/MiniMax-H3>
  - DiT：`fl2va_bf16`（61.7 GB）、`fl2va_int8_convrot`（31.7 GB）、`fl2va_pruned_bf16`（约 37.5 GiB）、`fl2va_pruned_int8_convrot`（19.5 GB）、`fl2va_pruned_fp8_scaled`、`fl2va_pruned_w6a8`；`ref2va_*` 同样一套。
  - 文本编码器：`qwen3vl_32b_minimax_h3_bf16`（48.0 GB）、`int8_convrot`（25.3 GB）、`nvfp4_awq`（14.6 GB）。
  - VAE：`video_vae_fp16`（4.9 GB）、`video_vae_int8_convrot`（2.62 GB）、`audio_vae_fp32`（0.6 GB）。
  - LoRA：`fl2v_turbo_4step_v1.0_768p`、`fl2v_turbo_8step_v1.0`、`ref2v_turbo_4step_v0.1`，以及 `pika_h3_flex_*`。
  - 模型卡原话：「For diffusion models prefer `int8_convrot` if you are able to use pytorch with cu130」「`fp8_scaled` should only be used if you cannot use `int8_convrot`」。本机是 cu130，满足条件。
  - 尺寸来源：<https://comfyui-wiki.com/en/news/2026-08-03-minimax-h3-open-weights-comfyui>；pruned_bf16 的大小来自 <https://github.com/MiniMax-AI/awesome-minimax-h3-integration>。
- 【官方，Comfy 博客】剪枝的做法是把约 40% 的调制（modulation）权重换成查找表。博客称剪枝不损失输出质量。<https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui>
- 【社区】还有很多第三方量化版：GGUF Q3–Q8、NVFP4、INT4/W4A8 ConvRot、NF4、Turbo 合并版、FastH3、PDD 8 步等。清单见 <https://github.com/MiniMax-AI/awesome-minimax-h3-integration>。这个列表在 MiniMax-AI 组织下，但大部分条目是社区转换的，页面自己也让用户先核对兼容性。

### 1.2 剪枝和 int8 的质量损失（没有人专门测运动、闪烁、口型）

- 【社区，剪枝作者实测】<https://huggingface.co/multimodalart/MiniMax-H3-Pruned>
  - 剪枝把 AdaLN 投影折叠到 rank-8 子空间，相对 RMS 误差 1.45e-5。
  - 剪枝版和原版的视频余弦相似度 0.99128；作为对照，同一份权重只换注意力内核是 0.99248。作者原话：「moves the trajectory about as far as changing the attention kernel does」。
  - 音频：剪枝版 0.99911，对照 0.99964。
  - 8 bit 对比（t2va，960×544，124 帧，20 步，以 bf16 为基准）：

    | 变体 | 视频余弦 | 视频 PSNR | 音频余弦 |
    |---|---|---|---|
    | bf16 对照（编译后） | 0.9940 | 23.17 dB | 0.9968 |
    | int8 仅权重 | 0.9773 | 17.36 dB | 0.9852 |
    | fp8 dynamic | 0.9583 | 14.81 dB | 0.8775 |
    | **int8 dynamic + ConvRot** | **0.9893** | **20.65 dB** | **0.9943** |

  - 结论：我们用的 int8+ConvRot 是 8 bit 里最接近 bf16 的；fp8 的音频损失明显，0.88。
  - 这里只量了余弦和 PSNR，**没有时间维度、闪烁或口型的指标**。
- 【社区】WAS 的剪枝 r2 版：124 帧对比 bf16 是 26.1 dB。<https://huggingface.co/WAS/Minimax-h3_Singularity_v2_pruned>
- **【社区 + 本机代码】未剪枝的完整 checkpoint 在 ComfyUI 里每 17 帧闪暗、卡顿一次，剪枝版没有这个问题。**
  - 问题：[MiniMax-H3 issue #85](https://github.com/MiniMax-AI/MiniMax-H3/issues/85)、[ComfyUI issue #15426](https://github.com/Comfy-Org/ComfyUI/issues/15426)。
  - 原因：`comfy/ldm/minimax/model.py` 里 `t_emb = self.time_embedder(t_vals).to(dtype)` 把时间嵌入降到了 bf16；diffusers 保持 FP32。报告者删掉 `.to(dtype)` 后问题消失。两个 issue 都还开着，没有维护者回复。
  - 本机代码核对：0.41.2 第 749 行还是这样写。但剪枝版走的是另一个分支（`use_adaln_curves`），从 FP32 查找表插值，不经过这次降精度。**所以我们现在的剪枝版不受影响；换成完整的 bf16 / int8 反而会出问题。**

### 1.3 nvfp4 文本编码器的质量损失

- 【社区】<https://huggingface.co/rzgar/qwen3-vl-32b-minimax-h3-fp8-comfyui>：用「技术性长提示词」比较 4 bit（nvfp4_awq）和 FP8 编码器。每 100 词里读乱的词数：

  | 语言 | 4 bit | FP8 |
  |---|---|---|
  | 英文 | 1.8 | 1.4 |
  | 中文 | 3.1 | 1.6 |

  - 整体漂移：英文 9.4% 对 7.2%，中文 10.0% 对 5.5%。短提示词时 4 bit 在 13 种语言里都没有读乱。
  - 作者描述的后果：「wrong pronunciation」「broken sound on a word」「the character does the wrong thing」。
  - 我们的提示词是 350–500 英文词，再加上中文 `<d>` 台词，正好落在「长提示词」这一档。
  - 测试集具体多长没写【未核实】，也没有和 bf16 / int8 编码器直接对比。
- 【社区】<https://smeltcore.com/recipes/minimax-h3-on-rtx-5090-32-gb-video-audio-and-what-nvfp4-does-not-buy-you/>：
  - nvfp4 文件设了 `full_precision_matrix_mult`，推理时先反量化再做矩阵乘法，在 5090 上也不更快，只省了体积。
  - 引用讨论区一位用户的话：nvfp4「compromises the coherence of tricky setups」。
  - int8_convrot 编码器在 32 GB 卡上放得下：文本编码阶段约 26.5 GiB，DiT 换出显存后再加载。
- 【社区】视频 VAE 的 int8 版：Comfy 官方博客说 int8 解码器和标准解码器之间是 **67.7 dB PSNR**；对比之下，VAE 重建真实素材本身只有约 38 dB。所以 int8 VAE 的损失可以忽略。<https://blog.comfy.org/p/making-the-minimax-h3-video-vae-2x>（这是 Comfy 官方博客，归【官方】。）
- 【社区】音频 VAE 必须用 fp32，fp16 会导致音画不同步。<https://github.com/wildminder/awesome-minimax-H3/blob/main/guides/minimax-h3-performance.md>。我们已经用 fp32。

### 1.4 全精度要多少显存，32 GB 能不能跑

- 【官方】diffusers PR：单张 80 GB 卡跑 768p 需要开 `enable_auto_cpu_offload`，光 bf16 transformer 就有 61.7 GB。<https://github.com/huggingface/diffusers/pull/14355>。官方 SGLang 示例用 4 卡（`--num-gpus 4 --ulysses-degree 4`）。
- 【社区】剪枝作者在 H100 80 GB 上开 CPU 卸载：剪枝版峰值 52.7 GB，原版 65.2 GB。
- 【社区】pruned_bf16 约 37.5 GiB，超过 32 GB，只能靠 ComfyUI 的动态显存卸载；社区建议内存 64–128 GB。完整 bf16 的 61.7 GB 更要大量卸载，而且有上面那个 17 帧 bug。来源：smeltcore 和 awesome 列表。
- **判断**：在 32 GB 卡上，DiT 维持 `pruned_int8_convrot` 是对的。如果要 A/B 上限，可以用 `pruned_bf16` 走卸载跑一两个镜头（慢，要大内存），但不建议作为默认。**最便宜的一项是把文本编码器换成 `int8_convrot`。**

---

## 2. 采样设置

| 项 | 官方取值 | 来源 |
|---|---|---|
| CFG | 1（BasicGuider，没有负向分支）。权重已做 CFG 蒸馏，所以负面提示词不起作用，要正面描述想要的东西 | 【官方】模型卡；ComfyUI 提示词页原话「`BasicGuider` runs at `cfg` 1 with no negative branch」「Ban lists add unwanted concepts. State what should appear.」<https://docs.comfy.org/tutorials/video/minimax/minimax-h3-prompt-guide.md>；diffusers PR：「no classifier-free guidance, no negative_prompt」 |
| shift | 视频 12，音频 3 | 【官方】HF `scheduler/scheduler_config.json`、`audio_scheduler/...`、`FL2VA/model_index.json` 的 `sigma_shift_scales`；【本机代码】`supported_models.py` 的 `MiniMaxH3.sampling_settings` 也是 12 / 3，不加 `MiniMaxH3SigmaShift` 节点时就用这个默认值 |
| 步数 | ComfyUI 模板 20；**diffusers 官方示例 30，默认 50**（diffusers 的步数把最后的 0 也算一个网格点，30 步 = 29 次前向） | 【官方】ComfyUI 模板；diffusers PR #14355 |
| 采样器 / 调度 | `res_multistep` + `simple`（ComfyUI 模板） | 【官方】模板 JSON |
| 分辨率 | 短边 768，面积上限 768×1344，边长取 32 的倍数；2K 要靠没开源的 Regenerate-2K | 【本机代码】`nodes_minimax_h3.py`（`BASE_SHORT_EDGE=768`、`MAX_PIXELS=768*1344`）；模板注释「capped at 768x1344」 |
| 帧率 | 24 | 【官方】 |
| 帧数 | 17k+5；**训练范围约 124–362 帧（5.2–15 s），更长没测过** | 【本机代码】节点提示「trained range is ~124-362, longer is untested」 |
| 首帧 / 尾帧 | `first_frame` 直接拉伸到画布、不保持比例；`last_frame` 居中裁切；AddGuide 也是居中裁切 | 【本机代码】`_resize(..., "disabled")` 对比 `"center"`；文档也写了 off-aspect 会被拉伸 |

- 【社区】20 步是 ComfyUI 为了速度的折中，30 步通常能改善细节，音频在 20 步以下明显变差。来源：<https://www.seedance.tv/blog/minimax-h3-30-vs-50-steps>，没有同种子对比；<https://github.com/wildminder/awesome-minimax-H3/blob/main/guides/minimax-h3-performance.md> 说「20→32 步改善音频和运动，多花 15–20% 时间」【未核实】。
- 【社区】有人跑了 715 种采样器 × 调度组合的基准（20 步，不开 Turbo），帖子本身没给结论，结论在 civitai.red 文章里，我没能打开【未核实】。<https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/122>
- 【社区】音频 shift 改成 6 声音更响，但耳语会过载约 9 dB。来源同 wildminder。

### Turbo / 蒸馏 LoRA 的取舍

- 【官方，ComfyUI】
  - 模板默认关。开了以后 8 步，强度 1.0。
  - R2V 的 4 步 LoRA「faster but weaker on reference and audio fidelity. Use 20–25 steps when references must hold」。
  - 多帧参考页：「slightly lower audio and motion quality」。
  - 来源：<https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native>，<https://docs.comfy.org/tutorials/video/minimax/minimax-h3-multiframe.md>
- 【官方，LoRA 作者 ModelTC】768p 的 Turbo 是用视频 shift 6、音频 shift 3 训练的（544p 版是 12 / 3）；Studio 用 8 NFE、shift 6 / 3。所以**开 Turbo 时应该接 `MiniMaxH3SigmaShift` 把 shift 设成 6 / 3**，不要沿用默认的 12。<https://github.com/ModelTC/Minimax-H3-Turbo>
- 【社区】
  - 4 步时音频会跟着快速运动一起变差，6–8 步好一些。
  - 蒸馏后「hard cuts can smear into dissolves」，快速运动会糊。
  - Turbo、Spectrum、TeaCache 都会损失音频。
  - 来源：awesome 列表、wildminder、[Kijai 讨论 #5](https://huggingface.co/Kijai/MiniMax-H3_comfy/discussions/5)。早期 LoRA 的音频失真问题已经在核心代码里修好。
- 判断：我们不开 Turbo，这和对口型、流畅度的目标一致。

---

## 3. 口型

### 3.1 官方说法

- H3 是音画联合生成，对白写在提示词里：`<d>[Language] ...</d>`。
  - 说话人 ID `(S1)`、`(S2)` 跨镜头保持不变。
  - 画外音写成 `says in an off-screen voiceover`，并且在 `</d>` 后面写明画面里这个角色嘴是闭着的。
  - 台词跨切点时两边都加 `<scenetrans>`；视频结尾说话被截断时用 `<cutoff>`。
  - 来源：<https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/base-en.txt>
- ComfyUI 提示词页：
  - 「**Wrong-speaker assignment can happen. Tie lines to visible events, not timecodes.**」
  - 「Ellipses often hurt intelligibility」，听不清的部分写 `[unclear]`。
  - 「If unwanted speech appears, fill both fields explicitly」：`overall_soundscape` 和 `non_diegetic_music` 都要写，不要留空。
- R2V 参考音频（ComfyUI 文档）：「Audio carries timbre, not words. Specify delivery, and use one audio reference per speaker when assignment must be exact.」Ref2VA 指南也说，只参考音色时不要把参考音频里的台词带进目标视频。
- **`MiniMaxH3AddGuide` 的音频**【官方 + 本机代码】
  - 把音频编码成潜变量，作为条件 token 放在对应的时间位置（`keyframe["audio_latent"]`），每一步都重新注入，本身不被去噪。
  - 它不替换目标音轨，目标音轨仍然从噪声开始生成。文档原话：「`MiniMaxH3AddGuide` conditions generation. It is not video-to-video. Sampling still starts from the workflow's empty latent」「`denoise` does not scale guide strength」，**没有强度参数**。
  - 来源：<https://github.com/Comfy-Org/ComfyUI/pull/15439>，本机 `nodes_minimax_h3.py`。
  - 我们第十二轮实测「尾段第 0 帧贴得紧，第 21 帧只剩约 20 dB」，就是这种「引导会漂」的表现；音频引导同理。
- 官方没有「给一段音频、只生成对口型画面」的模式。模型卡只把音频当作 Ref2VA 的参考（用于音色）。

### 3.2 社区做法：音频锁定（真正的音频驱动）

- 原理：用 H3 的音频 VAE 把台词编码，**替换** AV 潜变量里那条空白的音频流，再把音频的 noise_mask 设成 0、视频设成 1。这样采样时音频始终保持原样，模型只生成配合它的画面。成片混音时用**原始**音频，不用经过 VAE 编解码的那条。
  - [VRGDG MiniMaxH3AudioDrive](https://comfy.icu/node/VRGDG_MiniMaxH3AudioDrive)：「replaces H3's blank audio latent with your encoded source track, locks it」。
  - [TJ H3 Audio Lock](https://comfy.icu/node/TJ_H3_AudioLock)：`lock` 模式整段冻结；`remix` 模式按 `strength`（默认 0.5）部分保留；`fit` 选 `pad_silence`、`loop` 或 `stretch_none`，超长直接截掉。
  - T8 节点包：`lock_source`、`remix_source`、`reference_only` 三种模式。<https://github.com/T8mars/comfyui-minimax-h3-audio-T8>，模式名来自 CSDN 教程转述。
  - 有人在 B 站专门强调「真音频驱动，绝非音频参考」：<https://www.bilibili.com/video/BV1hQuw6UEeQ/>。页面只能看到标题【未核实】。
- 要点：
  - 同一段音频最好同时接到 R2V 的 `ref_audio_0`，提示词里写 `<Audio 1>`。否则可能「lip-sync to nothing or follow the wrong track」（VRGDG）。
  - 用频谱图检查锁定是否成功，不要看波形；音频 VAE 不保留相位，波形看起来不相关是正常的（TJ）。
- **本机 0.41.2 用核心节点就能实现**【本机代码】：
  - `LTXVConcatAVLatent` 的说明写着「Merge a video latent and an audio latent into a joint AV latent (any AV model, e.g. LTXV or MiniMax H3)」。如果输入已经是 AV 潜变量，它会保留视频流、换掉音频流，并把各自的 `noise_mask` 合成一对嵌套掩码；音频比画面短时，补出来的尾巴不加掩码，由模型自己生成。
  - 每 token 的掩码由 [PR #15375](https://github.com/Comfy-Org/ComfyUI/pull/15375) 加入。v0.34 时坏过，见 [#15978](https://github.com/Comfy-Org/ComfyUI/issues/15978)，由 PR #15988 修复。本机 `model.py` 第 636–639 行有「速度乘以 denoise_mask」，就是这个修复。
  - 预计的节点链：`MiniMaxH3ImageToVideo`（AV 潜变量）→ `LTXVConcatAVLatent(video_latent=它, audio_latent=SetLatentNoiseMask(VAEEncodeAudio(台词, H3 音频 VAE), 全 0 掩码))` → 采样。
  - **我没在本机跑过**。有两点要先验证：`VAEEncodeAudio` 用 H3 音频 VAE 编出来的形状是否是 `[1,32,2,T]`；全 0 掩码怎么构造（`SolidMask` 值 0，尺寸让 `reshape_mask` 自己去对齐）。不行的话直接用上面的社区节点。
- 社区经验：
  - 「the mouth in the generated video reacts to the timing of the input audio」。生成后别把片段挪到别的时间点；用纯人声分轨，不要用混好的整轨；提示词里描述嘴型规则，比如没声音时闭嘴、长元音保持口型。<https://note.com/joh_luck/n/n6c4679754d8f>
  - T8 教程：联合生成的嘴型不会逐音素精确，要精确口型得在成片后加专门的唇形步骤。<https://blog.csdn.net/gitblog_00369/article/details/167783627>（转述）。
  - 和 H3 搭配的后期对口型工具，我**没找到具体的实测报道**。通用选项有 MuseTalk、LatentSync、wav2lip 一类【未核实】。

### 3.3 已知的口型 / 台词问题和解法（都是【社区】，官方没回复）

- 视频开头约 0.5 s 出现乱语或被截断的声音，和种子有关。[#76](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/76)。用户给的解法：
  - 写 `overall_soundscape`（没写的话，不说话的时段会「mumble」）；
  - 台词用句号结尾；
  - **音色参考只用约 4 s**，更长会出现 mumble；
  - 加说话人和语气的引导语。
- 人物胡言乱语、读出提示词、画面出现字幕。[#106](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/106)：别给模型留空闲说话的时间；也有人说部分情况是 ComfyUI 搭建问题。我们第七轮也见过「H3 把台词当字幕画进画面」。
- 同一语言口音不一致（[#84](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/84)）；Ref2VA 加音频后人物身份被改写（[#91](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/91)）。只看了标题。
- 时间点不准：有测试让台词在 3.5 s 出现，实际在 5.8–6.4 s；要 6 s 的视频返回 6.58 s。<https://fuser.studio/articles/minimax-h3-prompt-guide>（H3 API 测的）。所以**靠提示词里的时间码对齐台词不可靠**，这和官方「tie lines to visible events」一致。
- 连续镜头：每段开头约 1 s 是重放（会被裁掉），每个接续镜头开头大约有 2 s 安静；「台词加上约 4 s 安静要放得进一个镜头」，124 帧放不下一整句长台词。<https://huggingface.co/joeygambino/MiniMax-H3-Multishot-Workflow>
- 第 1.3 节提到的 nvfp4 编码器读乱中文词的问题，也会直接表现为发音错、口型错。

---

## 4. 不流畅、抖动、突然跳切

| 原因 | 证据 | 和我们的关系 |
|---|---|---|
| **提示词让模型在镜头内硬切** | 【官方】「FL2VA generally favors a single shot」「Use multiple shots only when they are explicitly specified」「If only the distance or a slight angle needs to change, prefer camera motion」「A cut should introduce new information」（base-en.txt）。【社区】3 个用「then」串起来的运镜，ffmpeg 检测到 2 次硬切（1.58 s、3.67 s）；同一首帧只写一个动作，再加「one continuous shot, no cuts」，就是 0 次切（fuser.studio，H3 Max）。joeygambino：结尾那一拍要落在说话人身上，不要落在旁边的物件上，否则会触发意外切镜头 | **高**。逐拍、350–500 词的写法容易被模型读成多个镜头 |
| 动作太少或太集中，接着「定格」 | 【社区】模型约 1.2 s 做完一个小动作然后站着不动；建议每段 2–4 个动作、至少 3 s（[#124](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/124)）。没有动作的固定构图会渲染成「a literal freeze」（Motion Context README）。「slow dolly-in」几乎不动，要写明起止景别和幅度（fuser）。第七轮我们也看到「两条动作都很少」 | 高 |
| 有效帧率只有一半（隔帧重复） | 【社区】[#74](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/74)：动漫风格常常有效帧率只有 12 fps，写实视频偶尔也有，推测和训练数据重采样有关。没有官方修复；变通办法是只对重复帧做插帧（GIMM-VFI、RIFE） | 中：要拿成片测一下才知道 |
| 每 17 帧闪暗或卡顿 | 【社区】完整 checkpoint 的时间嵌入降精度（见 1.2）。【本机代码】剪枝版不经过这条路径 | 低：别换回完整版就行 |
| 平移时每 24 帧跳一帧 | 【社区】[WanGP #2279](https://github.com/deepbeepmeep/WanGP/issues/2279)：主要出现在 Wan2GP，ComfyUI 里有人报告没有，也有人报告有；有一个「宽高是不是 64 的倍数」的假设，没证实 | 低：768×1344 两边都是 64 的倍数 |
| VAE 分块解码的接缝 | 【本机代码】H3 视频 VAE **内部固定分块**：时间上 17 帧一块（5 个 token、重叠 2 个 token，在 5 帧内线性混合），空间上 256 px 一块、至少 64 px 重叠。这是参考实现规定的块大小（代码注释「reference's semantic tile sizes」）；`decode_tiled` 直接等于 `decode`，所以 ComfyUI 的 VAEDecodeTiled 或 OOM 回退**不会再引入额外接缝**。int8 解码器对比 fp16 是 67.7 dB。社区里有人怀疑「编码时 17 帧分块之间没有上下文」（#15426），只做了单元测试，没有端到端证据 | 低。但我们的尾段要**编码** mp4，正好在这条路径上（见第 5 节） |
| 参考图或参考视频把引导拉偏 | 【官方 PR 评审】视频参考会把第 0 帧的引导拉偏，测到 -90 帧；作者提交了「Anchor guides to the target timeline when references are present」修复（[PR #15439](https://github.com/Comfy-Org/ComfyUI/pull/15439)，8 月合并，0.41.2 应该已包含）。另有一个评论说 AddGuide 会导致偏色，没证实（[#78](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/78)） | 低到中：连续镜头不带参考图 |
| CFG 太高 | 【官方】蒸馏模型只能用 cfg 1，我们已经是 | 无 |
| 量化 | 见 1.2。int8+ConvRot 接近 bf16，没有人量过时间一致性 | 低 |
| 采样器 | 没有官方证据说明 res_multistep 不好；715 种组合的基准结论我没读到 | 低 |
| 加速手段 | 【社区】Spectrum、TeaCache、EasyCache 会让人物变形，而且损失音频；SageAttention 在 sm_120 上超过约 15 万 token 时有噪声报告（bf16）。我们 768×1344×175 帧约 5.2 万视频 token，加上引导，离阈值还远 | 低。本机开着 SageAttention，必要时可以用 PyTorch 注意力做一次 A/B |
| 人物在远处时脸会崩 | 【社区】模型本身的问题（[#87](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/87)、smeltcore）。joeygambino：低于约 1 MP 时脸会变形 | 中：我们已经是 1 MP |

---

## 5. 长视频和续接

### 5.1 官方

- **用片段引导续接**【官方，ComfyUI 文档 + PR #15439】：「feed the first 22 frames of an existing video plus its audio into one AddGuide at frame_idx 0 and the model generates the continuation of both streams」。
  - 片段长度只能是 5、22、39……（17k+5）帧，多出来的会向下截。
  - 文档的例子还把一张静帧放在第 60 帧，强迫镜头经过那个姿势。
  - **官方没有给推荐的重叠帧数、强度（也没有强度参数），也没有要不要在末帧再钉一次。** 我们「尾段 22 帧 + 第 21 帧再钉末帧」的做法，在官方文档之外。第十二轮实测切点从 20 dB 提升到 36 dB，是我们自己的经验。
- **本机的 `video_minimax_h3_i2v_continuation` 模板**【本机文件核对】：`comfyui_workflow_templates_json/templates/` 里这个文件只有 `MiniMaxH3ImageToVideo`（首帧 / 尾帧），**没有** LoadVideo 和 AddGuide，等于「用上一段的最后一帧当首帧做图生视频」。GitHub 上 main 分支的版本也一样。
- **多帧参考模板** `video_minimax_h3_multiframe_reference`【官方】：Ref2VA 加串联的 AddGuide。`<Picture 1>` 同时是身份参考和第一个镜头的首帧，其他图按 `round(秒×24)` 钉到对应帧。
  - 「Pictures connected only to Add Guide nodes pin frames but aren't visible to the text encoder」：如果提示词里要提到某张图，就得把它也接到 `ref_images`。
  - 来源：<https://docs.comfy.org/tutorials/video/minimax/minimax-h3-multiframe.md>
  - **对我们的启示**：连续镜头去掉了 I2V 的 `first_frame` 之后，文本编码器就看不到首帧了。如果改写后的提示词还写着「`<Picture 1>` is fully referenced」，就成了指向一张不存在的图。这一点要核对。
- **Ref2VA 的 `video continuation` 任务**【官方提示词指南】：`<Video N>` 可以作为「continuation starting point」，任务类型写 `video continuation`；如果同时还要用一张图当尾帧，写 `[video continuation + keyframe completion]`。延续原音轨但不直接复制时，用 `audio reference`。参考视频会被 Qwen 按 2 fps 抽帧看，同时走 VAE 潜变量。<https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md>
- 第三方 API 有「H3 Max Extend」：从输入视频的最后一帧往后生成、再拼接，可以选目标尾帧。（fal、wavespeed，第三方）

### 5.2 社区里做一分钟以上一致长片的做法

- **ComfyUI-H3-Motion-Context**（awesome 列表收录）<https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context>
  - `context_length` 可选 5、22、39、56，**推荐 22**（5「just barely fluid」，22「nearly seamless」）。
  - `audio_context_length` **推荐 18**：音频上下文太长，每接一次声音就闷一点、小一点。
  - 重叠部分**直接裁掉，不做交叉淡化**；Trim 节点的 `match_tail` 要开着（H3 的音频网格取整，每段会多或少约 8 ms）。
  - **传潜变量（`context_latent`，用 Save/Load Latent），不经过像素来回编码**：作者把色偏和接缝归因于像素往返，原话「Nothing shifts the color or the contrast」。
  - 可选的 `H3 Join Match`（实验性）在接缝处匹配亮度和对比度。
  - 已知问题：一条链越往后质量越差，主要是音频（「photocopying a photocopy」）；没有动作的固定构图会定格；Turbo 和 Spectrum 会损失音频。
- **joeygambino 多镜头工作流** <https://huggingface.co/joeygambino/MiniMax-H3-Multishot-Workflow>
  - 默认模式把上一镜最后 22 帧的**原始潜变量**传进来，重新生成后裁掉。
  - 音频接缝用 40 ms 等功率焊接，放在新镜头前 0.75 s 里最安静的地方。
  - `seed_per_shot` 要开：共用一个种子时脸和声音都会漂。
  - 防漂设置：`chain_gain_control=flatten`、`master_normalize=luma+contrast`、`pin_noise≤0.10`。
  - 纹理每接一次增强约 1.3 倍（开 flatten 后约 1.02–1.05 倍），一条链建议不超过约 4 个窗口（30–40 s）。**场景切换时重新起一条链**。
  - 人物一致性：不用参考图也行，但每个镜头里外貌和房间的描述要逐字相同。
- **ComfyUI_MiniMax_H3_Extender** <https://github.com/tritant/ComfyUI_MiniMax_H3_Extender>：一段一段确认后再往下接；每段提示词开头放 `subject_definitions`；每段可以单独调色来抵消色偏；音频在最后统一从 PCM 编码，带增益匹配和去爆音。
- **[HF #124](https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/124)**：12 GB 卡拼出 39–53 s 的一个连续长镜头，10 段没有累积身份漂移。做法：第一段之后每段都用 Ref2VA，带脸部参考和场景定场图；每段重复完整的服装描述；按动作数决定每段长度。另外，反复出现的物件每段都要写明状态，否则会多出一个（例子是多出第二个杯子）。
- 台湾博客也建议长片改用 Ref2VA，每段重新带同一份参考，不要只靠尾帧逐段传递。<https://skypray.synology.me/blog/computer/comfyui-minimax-h3-workflow/>（搜索摘要转述）。
- 掩码续接【社区】：PR #15375 附带了「BasicMaskedExtension」示例工作流。思路是把上一段编码后放在新潜变量开头，`noise_mask=0` **硬保留**（不是引导），只生成后面的部分。理论上能解决「引导会漂、切点跳」，但我没看到成片对比【未核实】。
  - 本机代码核对：22 帧单独编码得到 7 个 token，正好对齐新片段前 7 个 token（`video_latent_t(22)=7`，`FRAME_PER_TOKEN=(1,4,4,4,4)`）。

---

## 6. 官方提示词指南：节奏、运镜、对白时间

来源：【官方】`base-en.txt`、`ref-en.txt`、`SKILL.md`（GitHub `skills/h3-prompt-writing/`），以及 ComfyUI 提示词页。

- **节奏**：
  - **没有「每秒多少动作」的官方规则。**
  - I2VA 的推荐结构：「first-frame anchor → action onset → continuous development → result or reaction」。
  - FL2VA：正文写两帧之间的运动路径，不要把两张关键帧各描述一遍。
  - 运动幅度和速度「only when they are meaningful; medium amplitude and normal speed are usually omitted」。
  - Ref2VA：按信息量把细节分配到各个镜头；「A single shot does not automatically justify a shorter description」；对白多的内容「prioritizes fitting the complete spoken timeline rather than mechanically reaching a word count」。
- **长度**：
  - 「350–500 英文词」**只出现在 Ref2VA 指南里**（`detailed_description` 部分）。base 指南（T2VA/I2VA/FL2VA）没有字数要求。
  - SKILL.md：「Always match the total duration of the description to the requested video length」，避免「timing that does not match the requested duration」。
- **镜头和切点**：
  - 第一个镜头不写时间戳；后面的镜头写 `[Shot N] At MM:SS.mmm, ...`，时间严格递增，用单个时间点，不写区间（ComfyUI 原话「not a range like `[5s-8s]`」）。
  - 切镜头必须带来新信息；小幅调整景别用运镜。
  - FL2VA 默认一个镜头，只有明确要求时才写多个镜头。
- **运镜**：写成镜头里的自然英语动作，不要在句尾堆运镜标签。官方没有限制每个镜头只能有一个运镜，但社区测试表明多个运镜串起来容易触发切镜头（见第 4 节）。
- **对白时间**：
  - 官方**没有语速或每秒字数规则**。
  - 只有：`<d>` 里原样保留用户台词和标点；画外音要写明嘴闭着；跨切点用 `<scenetrans>`；被结尾截断用 `<cutoff>`。
  - ComfyUI：「Tie lines to visible events, not timecodes」。
  - 说话人首次出场可以描述音高、音色、**语速**、口音。
- **负面描述**：不要写禁止清单，因为 cfg 1 没有负向分支，「no cars」反而会生成车（HF #124 的实测）。

---

## 对我们最可能有用的改动（按预期效果排序）

1. **【口型】`先配音` 改成音频锁定，混音时用原始配音。** 台词音频编码后替换 AV 潜变量的音频流，`noise_mask=0`；同一段音频接到 R2V 的 `<Audio 1>`。先用核心节点（`VAEEncodeAudio` + `SetLatentNoiseMask` + `LTXVConcatAVLatent`）在 scratchpad 里做个 A/B，不行再试 TJ 或 VRGDG 节点。台词音频按镜头内的确切时间点放，生成后不要再挪动。`原生同步` 那条路：音色参考剪到约 4 s，台词用句号结尾，`overall_soundscape` 一定要写。
2. **【乱跳】改写规则改成「一个镜头到底」。**
   - 不写 `[Shot 2+]` 时间戳（除非分镜就是要切）；只写一个主运镜，写明起止景别和幅度。
   - 2–4 个动作，按「起始 → 展开 → 结果」写，不用「then」串；加一句「one continuous shot, no cuts」。
   - 台词绑在可见的动作上，不靠时间码；结尾那一拍落在说话人身上。
   - 字数按时长写，不硬凑 350–500 词（那是 Ref2VA 指南的规则）。
   - 写完用 ffmpeg 的场景检测给每条成片数一下切点，作为回归指标。
3. **【衔接】尾段不再经过 mp4。** 每个 take 存最后一段潜变量（或至少存无损 PNG 序列加 WAV），避免 H.264 有损压缩加 VAE 再编码造成的色偏和接缝；音频上下文改成约 18 帧。可以评估 ComfyUI-H3-Motion-Context 的 `context_latent` 方案，或者掩码续接（硬保留前 7 个潜变量 token），和现在的「22 帧引导 + 第 21 帧钉末帧」用同一种子对比切点 PSNR。
4. **【一致性】连续镜头和同角色镜头都带同一组角色参考（Ref2VA），每段换种子，每段逐字重复人物外貌和服装描述，场景切换时重开一条链，一条链不超过约 4 段。** 另外核对：连续镜头去掉 `first_frame` 后，提示词是否还在引用 `<Picture 1>`。
5. **【文本编码器】`nvfp4_awq` 换成 `int8_convrot`（25.3 GB，32 GB 卡放得下）。** 同种子比较中文台词的发音和读错率。成本只是多下载一个文件、文本编码阶段多用一点显存。
6. **【步数】终版用 30 步**（diffusers 官方示例的取值），草稿保持 20 步。用同种子 A/B 看音频和细小动作。
7. **【诊断，便宜】给每条成片算逐帧平均绝对差。** 看有没有 17 帧或 24 帧周期的尖峰，以及隔帧重复（有效 12 fps）。如果有重复帧，只对重复帧插帧。
8. **保持 `pruned_int8_convrot` DiT 和 int8 VAE**，不换完整 bf16：32 GB 放不下，而且 0.41.2 里完整版有 17 帧 bug。
9. 最后手段：对口型要求高的近景镜头，成片后加一步唇形同步（MuseTalk、LatentSync 一类，和 H3 搭配的效果【未核实】）。

## 没查到或没打开的

- 715 种组合的采样器基准结论（civitai.red）、H3 Continuum（Civitai，403）、TheLocalLab 的音频对口型教程（Patreon，403）、InstaSD 文本编码器指南（403）、B 站视频的具体内容（只看到标题）。
- 官方关于每秒动作量和语速的规则：确认**没有**。
- 有没有人量过量化对时间一致性、口型的影响：**没有找到**。

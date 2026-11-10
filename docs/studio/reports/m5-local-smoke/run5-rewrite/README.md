# 第五轮（第 14c 步）：DeepSeek 按官方写法改写 + 本机 H3（2026-10-27）

工作台自己走一遍：本地 H3 的 take 先过新的「视频提示词改写」（`vprompt`，真的调 DeepSeek V4.1 Flash，Kelvin 定用它，不用本地 Qwen），改写结果按官方格式校验通过后才出片。只有 DeepSeek 和本机 ComfyUI 是真的（`DRAMA_LIVE=1` + `DRAMA_REAL_MODELS=deepseek/v4.1-flash`），其余都是 Mock；这一轮关了兜底，本地失败就在本地重试，不会落到 API。

- 命令：`DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/local_video.py --only rewrite --home <第 14a 步留下的数据目录> --cap 0.10`
- 输入和第三、四轮一样（同一个首帧、参考图、音色样本），种子：1-01 用 325085565 和 22，1-04 用 191503631 和 22。
- **工作流是工作台现在的**：`h3-i2v`（Turbo 8 步）、`h3-r2v`（Turbo 4 步）；第四轮手写版用的是关 Turbo 的 20 步。
- **花费**：DeepSeek 两次改写共 $0.0038（每个镜头一次，同一个镜头的两个种子共用一段提示词）；视频本地，不花钱。
- 改写出来的提示词：`prompt-1-01.txt`（I2VA，384 词）、`prompt-1-04.txt`（Ref2VA，322 词），都过了 `prompts/h3_format.py` 的校验，第一次就合格，没重问。
- 拼图（每秒两帧）：`rewrite-<镜头>-s<种子>.jpg`；片子和原图在本机 `C:\dev\drama-studio\docs\studio\reports\m5-local-smoke\originals\run5-rewrite\`。

## 结果

| 镜头 | 种子 | 结果 |
|---|---|---|
| 1-04 | 191503631 | **一镜到底**：楼道里缓推，她看纸条、愣住、开口说台词，脸没变。这个种子在第一轮（Turbo、原提示词）后半段跑到门口，第四轮（20 步、原提示词）第 2 秒转到空楼梯 |
| 1-04 | 22 | **一镜到底**，和上面几乎一样的节奏 |
| 1-01 | 325085565 | 一个地方：她站在楼梯口，灯闪，抱着画板袋走向家门，机位缓推 |
| 1-01 | 22 | 同上 |

**结论**：只改提示词（Turbo 不变）就不切走、不漂到别处了，两个镜头、两个种子都是。画质是 Turbo 的画质（8 步 / 4 步），和第三轮关 Turbo 的 20 步比，要不要换成 20 步等 Kelvin 看片子定。声音（台词有没有乱码、音色像不像）要 Kelvin 听。

## 过程里踩到的

- **ComfyUI 加载 H3 偶发 `hostbuf_file_reader_read failed`**（内存紧的时候从文件读权重失败，本机这一晚出现 5 次）：脚本每条 take 前先 `POST /free`（让 ComfyUI 放掉模型和缓存，不跑任务），失败就在本地再出一次；1-01 种子 22 第一次就是这样失败、重试成功。
- 第一次跑时兜底还开着，本地失败落到了 Mock 的 H3 API（没花钱）；之后关掉兜底再跑。

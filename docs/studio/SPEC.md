# 工程规格（SPEC）

> 读者：Claude Code。产品要做什么看 [PLAN.md](PLAN.md)，界面长什么样看 [prototype/](prototype/README.md)，先做什么看 [ROADMAP.md](ROADMAP.md)。本文件回答“怎么实现”。
> 本文件里的决定可以改，但改之前在 `docs/studio/DECISIONS.md` 记一条（日期、改了什么、为什么）。

## 0. 范围

- 单用户、本机运行的桌面级 Web 应用：后端跑在 `127.0.0.1`，前端是浏览器里的 SPA。不做多用户、登录、云部署。
- 平台：Windows 11（原生）、Linux、macOS（Apple 芯片）。主力机器是 Windows + RTX 5090 32 GB。
- v1 覆盖方案里的 P1、P2（成片规格 → 小说 → 剧本 → 素材 → 分镜 → 视频 → 质检 → 后期 → 看板），外加素材整理与外部同步（ComfyUI、文件夹、Eagle、达芬奇）。P3（Marble 场景世界、Blender 运镜、动作捕捉、LoRA 训练、对话式 Agent）不在 v1，但数据模型要给它们留位置。
- P0（手工做 30 秒样片、实测三个假设）由 Kelvin 手工完成，不写代码；它的结论回填到 `config/components.yaml` 的默认路由。

## 1. 底座：基于 drama-series-agent

上游：<https://github.com/binwu1/drama-series-agent>（Apache 2.0）。已知：Python 3.10+ 后端（带 `/docs` 的 HTTP API 和 `drama-series-render` CLI）、`web/` 下的 React + Vite 工作台、`workflows/selfhost/` 下的 ComfyUI MiniMax H3 工作流、OpenAI 兼容的 LLM 预设、状态存在文件里（`projects/{series}/`、`dramas/{series}/`、`memory/*.jsonl`、`series_runtime.json`）、失效传播和断点续跑。

做法：

1. 仓库以上游代码为初始提交（fork，或 clone 后推到新的私有仓库），保留 `LICENSE`，新增 `NOTICE` 写明“基于 drama-series-agent 修改”。改过的上游文件在文件头加一行修改说明。
2. M0 第一件事：通读上游，写 `docs/studio/UPSTREAM_NOTES.md`——模块地图、数据文件格式、H3 runner 的调用方式、失效传播和续跑怎么实现、哪些能直接复用。
3. 包名沿用 `drama_series_agent`，新代码作为它的子包加进去（见第 3 节），不另起一个包。上游模块能复用就包一层适配，不推倒重写；要重写的部分（镜头契约、调度器、Context-IR）按 PLAN 的“基于 drama-series-agent 的改造”一节执行。
4. **状态存储的工程决定**：方案里写“文件系统为唯一真相 + SQLite 索引”。实现上改为——**结构化状态以 SQLite 为准**（版本、任务、调用记录、配置都需要事务和聚合查询，双写容易不一致）；图片、音频、视频和大段文本存磁盘，按内容哈希引用；上游依赖的 `dramas/{series}/` 文件改为从数据库导出，保持上游技能和 CLI 能用。

## 2. 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 后端 | Python 3.12、FastAPI、Pydantic v2、SQLModel + SQLite（WAL）、Alembic、httpx、uvicorn | 全异步；上游若已用 FastAPI 则直接沿用 |
| 包管理 | uv（`pyproject.toml` + `uv.lock`） | 本地模型的运行环境也用 uv 建，独立于项目环境 |
| 任务 | 自研 asyncio 任务队列，任务持久化在 SQLite | 不引入 Celery / Redis；单机够用 |
| 推送 | SSE（`/api/v1/events`） | 前端用 EventSource；断线自动重连并按 `last_event_id` 补发 |
| 本地生成 | ComfyUI（HTTP + WebSocket API） | 工作流模板放 `workflows/`，见 6.4 |
| 本地 LLM | Ollama 或 llama.cpp server 的 OpenAI 兼容接口 | 和云端 LLM 共用一个适配器 |
| 媒体 | FFmpeg / ffprobe（子进程）、pyloudnorm、OpenTimelineIO | 时间线导出 FCPXML 和 OTIO |
| GPU 采样 | pynvml（NVIDIA），macOS 跳过 | 记录本地任务显存峰值 |
| 密钥 | keyring（系统钥匙串），`.env` 兜底 | 见第 15 节 |
| 前端 | React 19、Vite、TypeScript（strict）、TanStack Query、Zustand、react-router、i18next | 沿用上游 `web/`，按需升级 |
| 前端组件 | React Flow（关系图）、TipTap（带修订的剧本编辑）、TanStack Table（表格）、wavesurfer.js（波形） | PLAN 里已选定 |
| 图表 | 手写 SVG + d3-scale / d3-shape | 看板的图形规则见 11.3，现成图表库很难满足 |
| 测试 | pytest、pytest-asyncio、respx、Playwright（前端冒烟）、Vitest | 测试里一律用 Mock 适配器 |
| 质量 | ruff、mypy、eslint、prettier | CI 跑 lint + 单测 + mock 端到端 |

## 3. 目录结构（目标形态）

```
src/drama_series_agent/
  (上游已有模块……)
  core/        config.py  db.py  models_db.py  events.py  jobs.py  storage.py  i18n_codes.py
  modelhub/    registry.py  router.py  pricing.py  budget.py  calllog.py
               adapters/  base.py  mock.py  openai_compat.py  comfyui.py
                          minimax.py  google.py  openai_images.py  volcengine.py
                          elevenlabs.py  sync_so.py  topaz.py  local_tools.py
  prompts/     compiler.py  templates/<component>/<model_family>.j2  blacklist.py
  pipeline/    components/  enrich.py extract.py split.py script.py assets.py voice.py dub.py
                            plan.py keyframe.py video.py upscale.py lipsync.py qa.py music.py subs.py post.py
               products.py  invalidation.py  gates.py  timing.py  continuity.py
  qa/          face.py  syncnet.py  asr.py  speaker.py  ocr.py  vlm.py
  post/        trim.py  lut.py  mix.py  subtitles.py  export_otio.py  checks.py
  setup/       manifest.py  detectors.py  installer.py  mirrors.py  profile.py
  metrics/     queries.py  projection.py  export_csv.py
  spec/        presets.py  dims.py  compat.py                       (成片规格，第 13 节)
  sync/        board.py  comfy_board.py  ingest.py  folder.py  eagle.py  resolve.py   (外部同步，第 14 节)
  api/         app.py  routes/<resource>.py  sse.py
config/        providers.yaml  components.yaml  setup-manifest.yaml  qa.yaml
workflows/     <name>.json  <name>.bindings.yaml        (含上游 selfhost/)
integrations/comfyui-dramastudio/   ComfyUI 自定义节点包（第 14.2 节），单独安装到 ComfyUI/custom_nodes
web/src/
  app/         routes.tsx  AppShell.tsx
  pages/       Setup  Spec  Novel  Script  Assets  Storyboard  Generate  Post  Models  Sync  Dashboard
  components/  RunBar  Inspector  ModelPicker  PromptEditor  VersionHistory  ImpactDialog
               CostBadge  GateButton  Toast  charts/
  api/         client.ts  hooks/
  locales/     zh-CN/*.json  en/*.json
tests/         unit/  api/  e2e/  fixtures/demo/   (示例项目《雨停之前》)
```

`config/*.yaml` 的初始内容见 `docs/studio/seed/`，M0 时拷过去。用户在界面里改的配置写进数据库，YAML 只是出厂默认。

## 4. 数据模型

层级：剧集（series）→ 分集（episode）→ 场景（scene）→ 镜头（shot）→ take。资产挂在剧集下，镜头只引用资产 ID。

### 4.1 故事与剧本

| 表 | 关键字段 |
| --- | --- |
| `series` | id, slug, title, ui_lang, created_at, settings_json |
| `output_spec` | series_id, platform（cn / intl / wide / custom）, aspect（9:16 / 16:9 / 3:4 / 1:1 / 21:9）, delivery（1080p / 2k）, fps（24 / 25 / 30）, episode_len（short / mid / long / xl）, subtitles（burn / srt / both）, audio_json（采样率、目标响度、峰值）, codec, ai_mark, derive（另出一版的画幅或空）, locked_at |
| `novel_source` | id, series_id, filename, text_path, sha256, rights_confirmed_at |
| `chapter` | id, source_id, idx, title, start, end（原文字符偏移） |
| `bible_entity` | id, series_id, kind（character / location / prop / event / relation）, name, aliases[], data_json, source_spans[], frozen（用户标为不许改） |
| `suggestion` | id, series_id, kind（motive / timeline / consistency / gap）, anchor_span, text, status（pending / accepted / rejected / rewritten）, rewrite_instruction |
| `episode` | id, series_id, idx, title, hook, cliffhanger, target_seconds, budget_usd |
| `beat` | id, episode_id, idx, text, emotion（-1..1，用于情绪曲线）, source_spans[] |
| `scene` | id, episode_id, idx, heading, location_id, time_of_day, ambience |
| `script_line` | id, scene_id, idx, type（action / dialogue / vo / sfx）, character_id, text, tone, source_spans[], ai_added |
| `shot` | id, scene_id, idx, shot_type（continuous / same_scene_cut / scene_change）, size, camera_move, duration_s, duration_source（audio / manual）, intent, character_ids[], prop_ids[], line_ids[], blocking_json, audio_mode（A / B / C）, difficulty（1–6）, control_json |
| `continuity_state` | shot_id, json（站位、手中道具、服装、时间；结构见 PLAN “连续性账本”） |
| `asset` | id, series_id, kind（character / scene / prop / text / voice / style / world）, name, intent, data_json（如文字类的逐字内容、字体风格；音色类的情绪变体） |

`source_spans` 统一格式 `[{source_id, start, end}]`，用来实现“镜头 → 剧本行 → 小说段落”三向跳转。

### 4.2 产物与版本（所有“四个按钮”的基础）

界面上每一张可以“改提示词 / 重跑 / 不满意换一个 / 历史”的卡片都对应一个 **product**；每次生成或编辑产生一个 **version**，只追加、不覆盖。

| 表 | 关键字段 |
| --- | --- |
| `product` | id, series_id, owner_type（series / episode / scene / shot / asset / line）, owner_id, slot（bible / suggestions / episodes / script / asset_list / ref_image / text_image / voice / line_audio / shot_plan / keyframe / video / upscale / lipsync / qa / music / subtitles / cut）, component_id, current_version_id, adopted_version_id, locked_hash, status（empty / queued / running / ready / stale / adopted / locked / failed） |
| `product_version` | id, product_id, n, origin（run / rerun / switch / edit / fallback / import / auto_qa_rerun / comfy_ingest）, parent_version_id, payload_json, files[]（role, path, sha256, mime, duration_s, w, h）, content_hash, intent, compiled, compiled_overridden, model_key, where（local / api）, seed, params_json, qa_json, qa_pass, cost_usd, job_id, created_at, note |
| `dependency` | product_id, upstream_product_id, upstream_hash（构建时上游已采纳版本的 content_hash） |
| `gate_decision` | id, gate（novel / script / assets / storyboard / takes / export）, scope_id, product_hashes_json, decided_at, action（confirm / reopen） |

规则：

- **current**：界面当前显示的版本；**adopted**：下游实际使用的版本；**locked**：闸门确认后锁定，`locked_hash` 记录内容哈希。
- 视频的多个 take 就是 `slot=video` 的多个 version；“推荐”取质检总分最高且通过的那个。
- 每次构建下游 version 时写 `dependency`（上游 product + 当时的哈希）。

### 4.3 运行、配置、记账

| 表 | 关键字段 |
| --- | --- |
| `job` | id, series_id, product_id, component_id, kind, queue（gpu / api:<provider> / cpu）, state（queued / waiting_confirm / running / succeeded / failed / canceled）, priority, attempt, max_attempts, params_json, est_cost_usd, error_json, fallback_from_job_id, created_at, started_at, finished_at |
| `model_call` | 见第 10 节，看板的唯一数据源 |
| `config_override` | scope（project / component / item）, scope_id, component_id, data_json |
| `provider_account` | provider_id, has_key, key_ref（keyring 名，不存明文）, base_url_override, enabled |
| `custom_model` | 用户自己加的 OpenAI 兼容模型：provider_id, model_id, display_name, price_in, price_out, caps_json |
| `budget` | scope（call / shot / episode / series）, scope_id, limit_usd |
| `machine_profile` | id, scanned_at, json（第 12 节的检测结果） |
| `installed_item` | item_id, version, paths[], installed_at（用于卸载和重新检测） |
| `sync_target` | id, kind（comfy / folder / eagle / resolve）, enabled, config_json（路径、端口、模式）, status_json（最近一次检测结果） |
| `sync_item` | target_id, version_id, external_ref（文件路径、Eagle item id、画布节点 id）, content_hash, synced_at, status |

## 5. 流水线组件

组件 ID 和原型「模型与兜底」页一致。每个组件实现同一个接口：

```python
class Component(Protocol):
    id: str                      # "script"
    kind: ModelKind              # llm / image / video / tts / ...
    slot: str                    # 产出的 product slot
    def inputs(self, product) -> ComponentInputs: ...         # 读上游已采纳版本 + 资产 + 上下文
    def compile_prompt(self, intent, inputs, model) -> str: ...
    def output_schema(self) -> type[BaseModel] | None: ...    # LLM 类组件的结构化输出
    async def run(self, ctx: RunContext) -> VersionDraft: ... # 通过 router 调模型
    def estimate(self, product, model) -> Estimate: ...       # 预估花费和耗时
```

| ID | 名称 | 类别 | 输入 → 输出 | 闸门 |
| --- | --- | --- | --- | --- |
| extract | 设定提取 | llm | 小说分块 → bible_entity（合并别名） | — |
| enrich | 小说补全 | llm | 小说 + 设定 → suggestion 列表（带原文锚点） | 小说确认 |
| split | 分集规划 | llm | 小说 + 已采纳补写 → episode + beat | — |
| script | 剧本化 | llm | 节拍 + 原文 → scene + script_line | 剧本确认 |
| assets | 素材分析 | llm | 剧本 + 分镜 → asset 清单 + 出场矩阵 | — |
| img | 参考图生成 | image | 资产描述 → 角色多视角 / 场景 / 道具候选图 | 素材锁定 |
| text | 画面文字 | image | 逐字文本 + 字体风格 → 带字图 | 素材锁定 |
| voice | 音色 | voice_design / tts | 角色描述 → 中性锚点 + 4–5 个情绪变体 | 素材锁定 |
| dub | 台词配音 | tts | 台词 + 锁定音色 → 每行音频（决定镜头时长） | — |
| plan | 分镜规划 | llm | 剧本 + 资产 → shot 列表（类型、景别、站位、时长初值） | — |
| kf | 关键帧 | image | 镜头意图 + 锁定参考图 → 首帧（必要时尾帧） | 动态分镜确认 |
| world | 3D 场景（可选） | world | 场景描述 → Marble 世界（v1 只留接口） | — |
| vid | 视频生成 | video | 关键帧 + 台词音频 + 参考 → take | 选定 take |
| ctrl | 结构控制 | video | 控制视频 + 关键帧 → take（只本地） | — |
| up | 2K 精修 | upscale / video | 选定 take → 2K | — |
| lip | 口型修复 | lipsync | take + 台词音频 → 修复后 take | — |
| qa | 自动质检 | vlm + 本地工具 | take → 各项分数和通过与否 | — |
| music | 配乐 | music | 场景情绪 → 配乐 | — |
| sub | 字幕对齐 | asr | 成片音频 + 剧本台词 → 时间轴 | — |

`assets` 和 `dub` 在原型里没有单独一行（分别在 03 素材页顶部和「音色」组件里），实现时作为独立组件，界面放在同一页。

### 5.1 关键行为

- **长小说**：按章节分块（每块不超过模型上下文的 60%），逐块抽取后合并；别名合并用 LLM 判定 + 用户确认。
- **结构化输出**：LLM 组件一律要求 JSON 输出，用 Pydantic 校验；校验失败带着错误信息重试一次，仍失败则任务失败并保留原始输出供查看。
- **LLM 修改先给差异**：LLM 对已有内容的改动以 diff（修订）形式展示，用户接受后才写成新的 version。
- **音频先行定时长**：`shot.duration_s = Σ(该镜台词音频时长) + 前后留白（默认 0.3 s + 0.2 s，可配）`；超过目标模型单段上限（H3 为 2–15 s）时提示拆镜。没有台词的镜头用手填时长。
- **动态分镜**：前端把关键帧按时长排在时间线上，配台词音频播放；不需要后端渲染。可选导出幻灯片式 MP4（FFmpeg）。
- **画面文字**：分镜表里记录每个镜头的预期文字；质检用 OCR 逐字比对。
- **H3 开头乱码音**：视频组件产出后默认裁掉开头 0.3 s（后期页可关）。

## 6. 模型层

### 6.1 适配器

```python
class ModelAdapter(Protocol):
    key: str                # "deepseek/v4-pro"、"comfy/h3-local"、"mock/video"
    kind: ModelKind
    where: Literal["local", "api"]
    caps: Caps              # max_refs, durations, audio_in, control_video, resolutions, json_mode, langs, max_context
    pricing: Pricing        # unit（token_in/token_out/image/second/char/call）, price, currency, as_of, offpeak_rule
    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult: ...   # 结果含 usage
    def estimate(self, req: ModelRequest) -> Estimate: ...
    async def health(self) -> Health: ...
```

- 新增模型 = 新增适配器（或在 `providers.yaml` 填一行），不改组件和流程代码。
- **所有模型调用必须经过 `router.call()`**，由它负责选模型、预算检查、写 `model_call`、兜底。业务代码里不允许直接用厂商 SDK 或 httpx 调模型。
- 每个 kind 都有 `MockAdapter`：确定性的假输出（带文字的 PNG、FFmpeg 生成的纯色 MP4、正弦波 WAV、固定 JSON）、可配置的延迟、失败率和单价。`DRAMA_MOCK=1` 时全部模型替换成 Mock；测试默认开启。

### 6.2 写作类 LLM

- 一个 `OpenAICompatAdapter` 覆盖所有写作类模型（DeepSeek、Kimi、通义千问、豆包、GLM、MiniMax、Gemini 的 OpenAI 兼容端点、OpenAI、OpenRouter、本地 Ollama / llama.cpp、自定义）。
- 供应商表 `providers.yaml`：base_url、密钥名、模型列表（model_id、显示名、输入 / 输出单价、闲时规则、上下文长度、是否支持 JSON 模式）。初始数据见 `seed/providers.yaml`，**模型 ID 要对照官方文档核对**；「测试连接」按钮调 `GET /models` 校验密钥并列出可用模型。
- 界面上写作类组件先列 6 家常用的，其余收进「更多供应商」（原型已实现这个交互）。
- 支持流式输出，经 SSE 推到前端。

### 6.3 其他 API

图像（Nano Banana Pro、GPT Image 2、Seedream 5.0）、视频（MiniMax H3 API 含 Regenerate-2K 和 Context-IR、Seedance 2.5、Gemini Omni Flash、Wan 3.0、Kling）、配音（MiniMax Speech 2.8 HD 含音色设计、ElevenLabs）、口型（sync lipsync-2-pro）、超分（Topaz Starlight）、配乐（ElevenLabs Music）、3D（World Labs Marble，v1 只占位）。各写一个适配器；长任务用厂商的异步任务接口轮询，轮询间隔指数退避。

### 6.4 ComfyUI

- 工作流模板：`workflows/<name>.json`（ComfyUI API 格式）+ `<name>.bindings.yaml`（语义参数 → 节点 ID 和字段，例如 `prompt: {node: "12", field: "text"}`）。上游 `workflows/selfhost/` 的 H3 工作流直接纳入。
- 调用：上传输入（`/upload/image`），提交 `/prompt`，用 WebSocket 收进度，`/history/{id}` 取结果，`/view` 下载产物。
- 本地 GPU 队列并发 1；调度器按“同一模型”分组连续执行，切换大模型前调 `/free` 释放显存（PLAN：同一套模型的镜头连续跑，不再每镜卸载）。
- 本地任务超时（默认 10 分钟，可配）视为失败，进入兜底流程。

### 6.5 本地工具类模型

质检和后期用到的本地模型（人脸相似度、SyncNet、Whisper、说话人相似度、OCR、Qwen3-VL）在独立 uv 环境里以子进程或常驻小服务运行，统一包成 `local_tools` 适配器；它们也写 `model_call`（花费为 0，记时长和显存）。

## 7. 路由、兜底、预算

### 7.1 配置解析

三级：项目默认 → 组件默认 → 单个镜头 / 素材覆盖。`GET /config/resolve?component=vid&item=shot:1-05` 返回最终值和每个字段的来源层级（界面要标出“来自哪一级”）。

每个组件的配置：

```yaml
mode: local | api | hybrid        # hybrid = 本地出草稿，采纳前用 API 出终版
api_model: deepseek/v4-pro
local_model: ollama/qwen3.6-27b
fallback:
  enabled: true
  on: [error, timeout, qa_fail]   # qa_fail 需要 qa_fail_n
  qa_fail_n: 2
  to: kimi/k2.6                    # 兜底目标；为空则按 alt_order 下一个
  notify: after | ask              # 直接兜底事后通知 / 兜底前先问
alt_order: [kimi/k2.6, qwen/3.8-max, ...]   # 「不满意换一个」的顺序
per_call_cap_usd: 0.50
```

### 7.2 预设

「模型与兜底」页的四个预设，逻辑照搬原型 `Models.dc.html` 的 `presetCfg()`：

- 质量优先：能用 API 就用排第一的 API，本地只做兜底。
- 均衡（默认）：用 `balMode`（每个组件单独给，见 `seed/components.yaml`），否则有本地也有 API 的用混合。
- 省钱：能本地就本地，API 选 `cheap` 指定的那个。
- 全本地：完全不调 API；没有本地版本的组件（3D 场景）跳过。

切换预设不覆盖用户手动改过的组件（`config_override` 优先）。

### 7.3 能力过滤

模型选择器只列出满足当前镜头需求和成片规格的模型（参考图数量、时长、是否音频驱动、是否需要控制视频、画幅、分辨率）。需要 ControlNet 的镜头只显示本地模型。机器档案（第 12 节）里跑不了的本地模型隐藏。

### 7.4 按钮语义

| 按钮 | 行为 |
| --- | --- |
| 改提示词 | 打开 PromptEditor：改意图层 → 重新编译；或直接改编译层 → 标 `compiled_overridden`。「保存并重跑」或「只保存」 |
| 重跑 | 同一模型、新随机种子、同样的提示词 → 新 version（origin=rerun） |
| 不满意换一个 | 按 `alt_order` 取下一个（跳过当前），或用户手选；输入不变，按目标模型重新编译 → 新 version（origin=switch） |
| 历史 | 列出所有 version：设为当前、采纳这一版、对比 |
| 再出一条（视频） | 同配置再生成 N 条候选 take |

### 7.5 兜底

触发条件：调用失败（含 429 重试耗尽、5xx）、超时、质检连续 N 次不过。按配置切到下一个模型，新 version 的 origin=fallback，`model_call.fallback_reason` 记原因。`notify: ask` 时任务进入 `waiting_confirm`。

### 7.6 预算

- 任何 API 任务入队前先 `estimate()`。超过单次上限、单镜头上限或本集预算剩余 → 任务进 `waiting_confirm`，前端弹确认（显示预计花费）。
- 全局开关：本集预算用完后暂停所有 API 任务。
- 表头的“本集 API 花费 / 预算”实时从 `model_call` 汇总。

### 7.7 混合模式

本地出草稿（免费抽卡），用户点「采纳」时才用 API 出终版：视频走 H3 Regenerate-2K（输入为本地 768p take），LLM 走 API 模型重写定稿。终版作为同一 product 的新 version，origin=run，`parent_version_id` 指向草稿。

## 8. 提示词

- **两层**：意图层（用户的语言，和模型无关，存 `intent`）和编译层（按目标模型格式生成，存 `compiled`）。
- 编译器：`prompts/templates/<component>/<model_family>.j2`（Jinja2），上下文包括设定卡、锁定资产、连续性账本、上游内容。H3 用官方六段式。需要时可再让 LLM 润色编译结果（可配）。
- 手改过编译层的，上游变化时询问“保留手改 / 重新编译”。
- 保留上游的提示词黑名单校验（`prompts/blacklist.py`）。
- 提示词模板是文件，进 git；每个 version 存下实际发送的完整提示词。

## 9. 任务与事件

- **编排**：PLAN 架构图里的“编排 Agent”在 v1 实现为确定性的流水线调度器（代码按依赖图派任务），LLM 只在各组件里干活；用自然语言指挥整条流水线的对话式 Agent 放到 P3。
- `job` 表持久化。服务启动时把 `running` 的任务重置为 `queued`（断点续跑）。
- 队列：`gpu`（并发 1，按模型分组）、`api:<provider>`（每家并发和速率限制可配，429 指数退避）、`cpu`（FFmpeg 等，并发 = CPU 核数 / 2）。
- 依赖：任务可以声明依赖其他任务；调度器按依赖图执行（替换上游的串行 runner）。
- 取消：前端可取消排队或运行中的任务；ComfyUI 任务调用 `/interrupt`。
- SSE 事件类型：`job.updated`、`product.updated`、`version.created`、`cost.updated`、`gate.updated`、`sync.updated`、`setup.progress`、`setup.log`、`toast`。事件带递增 ID，支持 `Last-Event-ID` 补发。

### 9.1 HTTP 接口概览（`/api/v1`）

| 资源 | 接口 |
| --- | --- |
| 剧集 | `GET/POST /series`，`GET/PATCH /series/{id}`，`GET/PUT /series/{id}/spec`（成片规格，改画幅时返回影响范围） |
| 小说与设定 | `POST /series/{id}/novel`（上传），`GET /series/{id}/bible`，`PATCH /bible/{entity_id}`，`POST /suggestions/{id}/accept\|reject\|rewrite` |
| 分集、场、剧本、镜头 | `GET/PATCH /episodes/{id}`，`PATCH /beats/{id}`（含拖动换集），`PATCH /lines/{id}`（返回影响范围），`POST /shots/{id}/split\|merge` |
| 资产 | `GET/POST /series/{id}/assets`，`PATCH /assets/{id}` |
| 产物与版本 | `GET /products/{id}`（含版本列表），`POST /products/{id}/run` `{mode: rerun\|switch\|run, model?, intent?, compiled?, count?}` → job，`POST /versions/{id}/set-current\|adopt`，`POST /products/{id}/lock` |
| 影响范围 | `POST /impact/preview`（给一个待改动，返回受影响的产物和预计花费），`POST /impact/apply` `{action: mark\|rerun\|undo}` |
| 闸门 | `POST /gates/{gate}/confirm\|reopen` |
| 任务 | `GET /jobs`，`POST /jobs/{id}/cancel\|confirm` |
| 配置与模型 | `GET /config/resolve`，`PUT /config/override`，`POST /config/preset`，`GET /providers`，`POST /providers/{id}/key`，`POST /providers/{id}/test`，`POST /custom-models` |
| 看板 | `GET /metrics/*`（第 11 节） |
| 同步 | `GET/PUT /sync/targets`，`POST /sync/run`，`GET /sync/log`，`POST /ingest`（ComfyUI 节点存回，第 14.2 节） |
| 首次启动 | `POST /setup/scan`，`GET /setup/profile`，`POST /setup/install` `{items, mirror}`，`POST /setup/items/{id}/retry\|skip` |
| 事件 | `GET /events`（SSE） |


## 10. 调用记录（埋点）

每次模型调用（本地和 API 一样）写一行 `model_call`：

| 分组 | 字段 |
| --- | --- |
| 归属 | series_id, episode_id, scene_id, shot_id, component_id, product_id, version_id, job_id |
| 模型 | provider_id, model_key, where, is_fallback, fallback_reason, is_switch（不满意换一个）, attempt |
| 时间 | queued_at, started_at, finished_at（UTC，毫秒） |
| 用量 | tokens_in, tokens_out, images, output_seconds, chars, input_seconds |
| 花费 | unit_prices_json（当时的单价快照）, cost_usd, billed（失败是否计费） |
| 本地资源 | vram_peak_mb, gpu_util_avg（pynvml 每秒采样） |
| 结果 | status（success / error / timeout / canceled）, error_code（如 429）, qa_scores_json, qa_pass |

- 花费按当时单价现算并存快照；以后改价，历史花费不变。
- 预算检查、看板、CSV 导出都只读这张表。
- 不记录提示词全文和密钥（提示词在 version 里）。

## 11. 数据看板

原型：`prototype/Dashboard.dc.html`。范围切换：本集 / 全剧 / 今天。

### 11.1 接口和口径

| 接口 | 内容 | 口径 |
| --- | --- | --- |
| `/metrics/summary` | 已花、预算、预计、值得注意的几条 | 已花 = Σcost_usd（billed）；预计 = 已花 + Σ剩余未完成产物 × 当前路由的 estimate |
| `/metrics/kpis` | 已采纳成片秒数、每秒成片成本、本地 GPU 时长、API 成功率、质检通过率、镜头从开始到采纳的中位时长 | 成功率 = success / (总数 − canceled) |
| `/metrics/spend-series` | 累计花费曲线（15 分钟一桶）+ 预测虚线 | 预测线从“现在”画到预计值 |
| `/metrics/calls-series` | 每 15 分钟调用次数，按文本 / 图像 / 音视频分组，失败单列 | 类别由 model kind 映射 |
| `/metrics/shots` | 每个镜头在关键帧、视频生成、质检精修上的计算时长、候选数、花费、状态，按场分组 | 计算时长 = Σ(finished − started) |
| `/metrics/components` | 各组件累计时长，本地 vs 等 API | |
| `/metrics/speed` | 每个视频模型“出 1 秒成片要算多少秒”的中位、最快、最慢、样本数 | (finished − started) / output_seconds |
| `/metrics/apis` | 每个 API：类别、调用、成功率、中位耗时、用量 · 单价、花费和占比 | 按花费降序 |
| `/metrics/local-models` | 每个本地模型：用在哪、次数、累计时长、显存峰值 | 显存条满格 = 机器显存 |
| `/metrics/qa` | 通过 / 未过数、未过原因分布、自动重跑 / 自动兜底 / 手动换模型次数 | |
| `/metrics/episodes` | 每集成片进度、已花、预计总花费、累计计算时长 | 未开始的集按时长 × 当前路由估算 |
| `/metrics/export.csv` | `model_call` 原始行 | |

### 11.2 示例数据

原型里的数字（本集已花 $8.94、预计 $13.35、预算 $15、42 次调用 1 次失败等）在各页之间是对得上的。`tests/fixtures/demo/` 里的示例项目应生成同样的 `model_call` 行，让看板在 mock 模式下和原型一致，方便对照。

### 11.3 图形规则

- 分类色固定顺序：蓝 `#2a78d6`、橙 `#eb6834`、绿松 `#1baf7a`；不循环取色，第 4 类以上并入“其他”或拆小图。
- 顺序色（同一色相由浅到深）：`#86b6ef`、`#2a78d6`、`#104281`。
- 状态色只表示状态：通过 `#0ca30c`、失败 `#d03b3b`，必须配图标和文字。
- 只用一根 y 轴，不做双轴图。条形宽 ≤ 24 px，数据端 4 px 圆角，相邻填充之间 2 px 间隙；线宽 2 px；点 ≥ 8 px。
- 两个以上系列必须有图例；文字一律用正文颜色，不用系列色。
- 每张图都有「图 / 表」切换，表格视图是同一份数据；线图有十字准线 + 提示框，条和点有悬停提示；累计花费线和调用次数柱悬停联动。
- 暗色模式是单独选的颜色，不是自动反色。

## 12. 首次启动：主机检测与自动安装

原型：`prototype/Setup.dc.html`（中英切换完整实现）。

### 12.1 清单（manifest）

`config/setup-manifest.yaml`，每项：

```yaml
- id: node_seedvr2
  group: comfy                    # sys / rt / comfy / w(权重) / svc(网络与服务)
  name: {zh: "SeedVR2 节点（本地超分）", en: "SeedVR2 nodes (local upscaling)"}
  platforms: [windows, linux]     # macOS 上显示为“跳过，超分走 API”
  requires_cuda: true
  required: false                 # 可选项失败只记录，不阻塞
  depends_on: [comfy]
  detect: {type: comfy_node, dir: "ComfyUI-SeedVR2_VideoUpscaler"}
  install:
    - {type: git_clone, url: "...", ref: "<pinned commit>", dest: "{comfy}/custom_nodes/..."}
    - {type: uv_pip, env: comfy, requirements: "{dest}/requirements.txt"}
  size_gb: 0.1
```

检测器类型：`command`（跑命令 + 正则取版本）、`py_import`（在指定 uv 环境里）、`file`（存在 + 可选 sha256）、`comfy_node`（目录或 `/object_info`）、`nvml`（显卡、显存、驱动支持的 CUDA）、`http`（测速）、`service`（本地 LLM 服务端口）、`keyring`（密钥是否已填）。

安装步骤类型：`uv_venv`、`uv_pip`、`git_clone`（锁定 commit）、`download`（断点续传、sha256 校验、按镜像改写 URL）、`pkg`（winget / brew / apt，需要管理员权限时先问）、`script`。每一步都要幂等。

初始清单见 `seed/setup-manifest.yaml`（按原型的 PC / Mac 两套列出）。另外三项：`node_dramastudio`（我们自己的 ComfyUI 节点包，第 14.2 节）、`eagle`（只检测是否打开）、`resolve`（只检测版本和免费 / Studio）。

### 12.2 流程

1. **扫描只读**：不改动任何东西，结果存 `machine_profile`，路由据此隐藏跑不了的本地选项。
2. **推荐**：按硬件给预设（5090 → 均衡；Apple 芯片 → 视频、关键帧、超分走 API）。
3. **安装**：用户勾选（必需项默认勾上）→ 按依赖顺序执行，日志经 SSE 实时显示，每步可重试或跳过；装过的东西写 `installed_item`，卸载能清干净；重新检测只补差异。
4. **镜像**：自动（测速选择）/ 官方 / 国内镜像（Hugging Face、PyPI、GitHub 代理）。
5. **安全**：不动系统 Python；所有 Python 依赖装进 `~/.drama-studio/envs/<name>`（uv）；单项下载超过 10 GB 先确认。

## 13. 成片规格

原型：`prototype/Spec.dc.html`。新建剧集时必经这一页，之后从顶栏的规格标签进入。

### 13.1 预设和尺寸

| 平台预设 | 画幅 | 1080p 交付 | 2K 交付 |
| --- | --- | --- | --- |
| 国内短剧（抖音、快手、视频号、红果短剧） | 9:16 | 1080×1920 | 1440×2560 |
| 海外短剧 App（ReelShort、DramaBox、TikTok） | 9:16 | 1080×1920 | 1440×2560 |
| 横屏平台（B 站、YouTube） | 16:9 | 1920×1080 | 2560×1440 |
| 自定义 | 3:4 / 1:1 / 21:9 | 1080×1440 / 1080×1080 / 2520×1080 | 1440×1920 / 1440×1440 / 约 2976×1248（H3 上限） |

- `spec/dims.py` 是唯一算尺寸的地方：输入 (aspect, tier) → 宽高，宽高都取偶数。草稿固定 768p 档（短边 768），终版取交付档。
- 默认：国内短剧 · 9:16 · 1080p · 24 fps · 每集 30–90 秒 · 字幕两样都要 · 48 kHz / -14 LUFS / -1 dBTP · H.264 · AI 标识开。

### 13.2 谁读规格

- 关键帧组件：按画幅和尺寸出图；模型不支持该画幅时，按 `compat` 的处理方式（出最接近的画幅再外扩或裁切、出小图再超分）。
- 视频组件：画幅、分辨率、帧率作为请求参数；本地 ComfyUI 工作流通过 bindings 注入宽高。
- 提示词编译：把画幅写进编译层（如“竖屏 9:16 构图”）。
- 分镜和关键帧页：叠安全区参考线（平台按钮、标题和进度条会挡住的地方，比例按平台预设，可在设置里调）。
- 后期：超分目标、导出预设、字幕位置、帧率转换（25 fps 重采样，30 fps 用本地插帧）。
- ComfyUI 的「镜头」节点输出宽高和帧率（第 14.2 节）。

### 13.3 兼容检查和锁定

- `spec/compat.py`：对当前路由里的每个模型，用适配器 `caps`（支持的画幅、最高分辨率、帧率、时长）判定 原生支持 / 需要转换 / 不支持，返回给前端表格；“不支持”的模型在 ModelPicker 里隐藏。
- 第一张关键帧被采纳时写 `output_spec.locked_at`。锁定后改画幅：用失效传播算出受影响的关键帧和视频（以及按旧画幅出的场景参考图，标为可选），显示数量和预计花费，选项同 ImpactDialog。改分辨率或帧率只影响精修和导出，不触发重做。
- 另出一版：主画幅 9:16 时可选“导出时外扩出 16:9”（另计费，走外扩模型适配器）；主画幅 16:9 时可选“按人物位置自动裁成 9:16”（本地，不花钱）。

## 14. 素材整理与外部同步

原型：`prototype/Sync.dc.html`。工作台是唯一真相；外部软件只是看、排和接着做的地方。

### 14.1 同步引擎

- 触发：`version.adopted`、`product.locked` 事件（默认），或每次 `version.created`，或只手动；按用户勾选的类型过滤。
- 每个目标一个 `SyncTarget` 实现：`detect()`、`push(items)`、`remove(items)`；`sync_item` 记已同步的内容哈希，只推差异，可重试。同步任务走 `cpu` 队列，不阻塞生成。
- 文件夹布局（按镜头）：`<root>/<剧名>/E01/S01/1-03/E01_S01_1-03_video_v2.mp4`，按类型时为 `<root>/<剧名>/E01/视频/…`；每个文件旁放同名 `.json`（意图层提示词、模型、花费、质检分、来源 version id）。
- 出错只记录在同步记录里并提示，不影响流水线。

### 14.2 ComfyUI（双向）

- **素材板**：每集生成一个 ComfyUI 界面格式的 workflow JSON：
  - 分组（`groups`）：角色与音色、场景 · 道具 · 画面文字、每场一个组（镜头按顺序排）；
  - 节点：图片用 `LoadImage`，视频用 `LoadVideo`，音频用 `LoadAudio`；文件复制（或硬链接）到 `ComfyUI/input/drama/<剧名>/E01/…`，节点里引用相对路径；
  - 每组一个便签节点（`MarkdownNote`），写场次信息、提示词、模型、花费、质检分；
  - 通过 ComfyUI 的 userdata 接口写到 `workflows/短剧/<剧名>/第1集-素材板.json`，出现在 ComfyUI 的工作流列表里。每次同步整张重写；用户自己的工作流不碰。
- **节点包 `integrations/comfyui-dramastudio`**（Python 节点 + 少量前端扩展），首次启动的安装清单里加一项：
  - `DramaStudio ▸ 镜头`：下拉选剧 / 集 / 镜头，输出已锁定的关键帧（IMAGE）、台词音频（AUDIO）、参考图（IMAGE 批）、编译后的提示词（STRING）、宽、高、帧率、时长；
  - `DramaStudio ▸ 素材`：按资产 ID 输出锁定的参考图或音色样本；
  - `DramaStudio ▸ 存回工作台`：输入 IMAGE / VIDEO / AUDIO + 目标（镜头或资产、slot），把结果 POST 到后端 `POST /api/v1/ingest`，生成 origin=`comfy_ingest` 的新 version（只是候选），自动跑质检，写一行 `model_call`（where=local，花费 0，记耗时）；
  - 节点通过 `127.0.0.1` 访问后端，用安装时写入的本地令牌鉴权。
- 画布里挪节点、改分组、删节点都不回写。v2 再考虑把分组变化回写成标签。

### 14.3 Eagle（单向，可选）

- 检测：`http://localhost:41595` 有响应即视为已打开。
- 推送：按 剧 / 集 / 类型 建文件夹，`/api/item/addFromPaths` 批量加入，标签用 `角色:林晚`、`场景:楼道`、`状态:已采纳`、`模型:Nano Banana Pro` 这种格式，注释写意图层提示词。Eagle 的 item id 记在 `sync_item.external_ref`。

### 14.4 达芬奇 Resolve（单向）

- 检测版本和版次（免费 / Studio）。免费版从 21.1 起不再支持外部 Python 脚本。
- 免费版：同步时只更新整理好的文件夹，并导出 `E01.fcpxml`（和 `.otio`）；用户在达芬奇里把文件夹拖进媒体池、按文件夹建 Bin，再导入时间线。
- Studio：用官方 Python API 自动建 Bin（`MediaPool.AddSubFolder`）、导入素材（`ImportMedia`）、写元数据和片段颜色、按质检结果加标记、从 FCPXML 导入时间线（`ImportTimelineFromFile`）。

## 15. 安全与密钥

- 后端只监听 `127.0.0.1`；CORS 只允许本机前端源。
- 密钥存系统钥匙串（keyring），`.env` 兜底；数据库只存“是否已填”。API 永远不返回密钥明文；日志里对 `Authorization`、`api_key` 等字段打码。
- 用户导入小说时确认拥有改编权（`rights_confirmed_at`）。
- 生成的成片在导出时可选加 AI 生成标识（国内平台要求）。

## 16. 前端

### 16.1 路由和原型页面对应

| 路由 | 原型文件 | 说明 |
| --- | --- | --- |
| `/setup` | Setup.dc.html | 首次启动；未完成扫描时自动跳转到这里 |
| `/s/:series/spec` | Spec.dc.html | 00b 成片规格；新建剧集时必经，之后从顶栏规格标签进入 |
| `/s/:series/e/:ep/novel` | Main.dc.html | 01 小说 · 导入与补全 |
| `/s/:series/e/:ep/script` | Script.dc.html | 02 剧本 · 分集与剧本化（含影响范围弹窗） |
| `/s/:series/e/:ep/assets` | Assets.dc.html | 03 素材 |
| `/s/:series/e/:ep/storyboard` | Storyboard.dc.html | 04 分镜 · 关键帧与镜头设定 |
| `/s/:series/e/:ep/generate` | Generate.dc.html | 05 生成 · 候选墙与自动质检 |
| `/s/:series/e/:ep/post` | Post.dc.html | 06 后期 · 时间线与导出 |
| `/models` | Models.dc.html | 模型与兜底 · 全局默认、预设、密钥 |
| `/s/:series/sync` | Sync.dc.html | 素材整理与同步 |
| `/s/:series/dashboard` | Dashboard.dc.html | 数据看板 |

### 16.2 共用组件（每页都有）

- **AppShell**：顶栏（剧名 · 集名、成片规格标签如“9:16 · 1080×1920 · 24 fps”（点了进规格页）、本地 GPU 状态“空闲 / 运行中 n · 排队 m”、本集 API 花费 / 预算、中 / EN 切换）+ 左侧导航（6 个制作步骤、成片规格、模型与兜底、素材整理与同步、数据看板）。
- **RunBar**：改提示词 / 重跑 / 不满意换一个（带下拉选模型）/ 历史，按钮上显示预计花费和耗时。
- **Inspector**（右侧栏）：「运行设置」（ModelPicker）、「提示词」（PromptEditor）、「历史」（VersionHistory）三个标签。
- **ModelPicker**：运行位置（本地 / API / 混合，不可用的置灰并说明原因）、API 服务列表（前 6 个 + 更多供应商）、本地模型列表、自动兜底开关 + 触发条件 + 兜底目标、单次花费上限；底部链接“在模型与兜底里改全局默认”。
- **ImpactDialog**：改了已确认的上游时弹出，列出受影响的素材、分镜、关键帧、视频数量和预计花费；三个选项：只标记待更新 / 自动重跑（显示花费）/ 撤销修改。
- **GateButton**：每页右上的“确认……，进入下一步”。

### 16.3 i18n

- 所有界面文字走 i18next 词表（`zh-CN`、`en`），组件里不写死字符串；新增 key 必须两种语言同时加。CI 检查两份词表的 key 一致。
- 后端错误返回错误码 + 参数，由前端翻译。
- 提示词意图层跟随用户的语言；编译层按目标模型需要的语言生成。
- 原型只有 00 首次启动页做了完整中英文，其他页的英文要补译。

### 16.4 视觉

原型只定信息结构、交互和文案，视觉是线框级的，正式版要重做：

- 组件库用 shadcn/ui（Radix + Tailwind CSS），图标用 lucide；颜色、字号、间距、圆角写成设计 token（CSS 变量），亮色和暗色两套。
- 信息密度按“专业工具”来：表格和列表紧凑，卡片少用阴影；媒体（关键帧、视频、波形）是视觉中心。
- 竖屏素材多，候选墙和分镜板按 9:16 缩略图排版；规格改成横屏时自动换成 16:9 布局。
- 键盘操作：候选墙左右切换、空格播放、数字键打分、`A` 采纳。
- 设计 token 定好后先做 AppShell、RunBar、Inspector、ModelPicker 四个共用组件，再做页面。

## 17. 测试与示例项目

- 单元测试：路由解析、预设、预算、失效传播、时长计算、提示词编译、清单解析、看板口径。
- API 测试：每个路由至少一个正常 + 一个异常用例（FastAPI TestClient + Mock 适配器）。
- 端到端（mock）：从导入示例小说到导出成片跑通全流程，断言每步产生 version 和 `model_call`。
- 前端冒烟（Playwright）：每个页面能打开、语言能切换、四个按钮能触发任务。
- **示例项目**：`tests/fixtures/demo/` 放《雨停之前》第 1 集（人物林晚、周屿，镜头 1-01 到 1-09），内容和数字取自原型；`uv run drama-studio demo` 用 Mock 适配器生成，界面应和原型基本一致。
- 真实 API 只在手动冒烟脚本里调用（`DRAMA_LIVE=1`，每次运行设硬上限，默认 $1）。

## 18. 不确定的地方（实现时按这里的默认走，并在 DECISIONS.md 记录）

- 上游的 HTTP 框架、状态文件格式与本文冲突时，以本文为准，但保留对上游 CLI 的兼容导出。
- 各厂商 2026 年新模型的确切 model_id、请求格式：以官方文档为准，`seed/providers.yaml` 里标了 `verify: true` 的都要核对。
- H3 音频驱动（模式 A）的参数、ControlNet 与身份参考同时使用、中文文字渲染：等 P0 实测结论，之前按 PLAN 写的方式实现并保留开关。

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
| 本地生成 | ComfyUI（HTTP + WebSocket API） | 默认用用户已装的 ComfyUI；工作流库见 6.4（平台推荐的放仓库 `workflows/`，用户导入的放 `~/.drama-studio/workflows/`） |
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
  core/        config.py  db.py  models_db.py  events.py  jobs.py  storage.py  i18n_codes.py  capabilities.py
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
  setup/       manifest.py  probe.py  detectors.py  installer.py  steps.py  download.py
               comfy.py  snapshots.py  service.py  schema.py         (首次启动，第 12 节；已装的 ComfyUI，6.4.1)
  metrics/     queries.py  projection.py  export_csv.py
  spec/        dims.py  compat.py  schema.py                         (成片规格，第 13 节；预设在 config/spec.yaml)
  sync/        board.py  comfy_board.py  ingest.py  folder.py  eagle.py  resolve.py   (外部同步，第 14 节)
  api/         app.py  routes/<resource>.py  sse.py
config/        providers.yaml  components.yaml  setup-manifest.yaml  spec.yaml  qa.yaml
workflows/     <slug>/workflow.api.json  <slug>/workflow.yaml   平台推荐档的工作流（含上游 selfhost/ 的 H3），见 6.4
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

**M3 的实际做法**（细节和理由见 `plans/M3.md` 和 DECISIONS 里 M3 各步的条目）：

- `asset` 实际是 id, series_id, kind（character / scene / prop / text / voice；style、world 还没用到）, name, bible_id（从哪条设定来）, seed_json（分析给的描述、画面文字的逐字内容等，示例剧集另有 `order`）, retired。用户改的东西（描述、画面文字的设置、音色来源、选中的候选）不在这张表，在素材的产物上（4.2），所以重新分析不会覆盖。
- 新表 `asset_use`：一行一个（素材，场），记 episode_id、scene_id、line_ids（它出现在哪几行；空 = 整场）、version_id（来自哪一版素材清单）。出场矩阵和整集素材闸门都读它。
- 素材清单是每集一个 `asset_list` 产物（组件 `assets`），素材本身属于整部剧。采纳一集的清单时 upsert 素材、替换这一集的 `asset_use`，**只增不删**：不会让别的集用到的素材退场。id 按 key 沿用（`character:<设定 id>`、`voice:<设定 id>`、`scene:<地点 id>:<时段>`、`prop:<设定 id>`、`text:name:<名字>`，对不上再按「类别 + 名字」），范围包括其他集的清单，所以同一个人在不同集是同一条素材。
- 新素材顺手建好它的产物：角色、场景、道具 `ref_image`（组件 `img`），画面文字 `text_image`（`text`），音色 `voice`（`voice`）；角色锁定后另有 `ref_views`（`views`）。台词配音 `line_audio`（`dub`）的 owner 是剧本行，第一次配这一句时才建。

**M4 的实际做法**（细节和理由见 `plans/M4.md` 和 DECISIONS 里 M4 各步的条目）：

- `shot`（迁移 `0018`）是分镜规划已采纳版本的物化表，和 `script_line` 一样按 id upsert、版本里没有了的标 `retired`。实际列：id, episode_id, scene_id, idx, shot_type, framing（不叫 `size`）, camera_move, duration_s（分镜规划给的秒数）, manual_s（用户手填的）, intent（规划给的画面描述，只是关键帧提示词的种子）, summary, line_ids, asset_ids（角色、场景、道具、画面文字、音色都在一个列表里，不分 `character_ids` / `prop_ids`）, tail_from（连续动作接哪个镜头的尾帧）, blocking_json, audio_mode, difficulty, control_json（M5 用）, retired, version_id。显示的时长不存，读的时候现算（5.1），所以重配音不产生新版本；镜头号「1-04」也是现算（集序号 + 本集第几个）。
- 分镜规划是每集一个 `shot_plan` 产物（组件 `plan`），一集的剧本被采纳时建；物化时给每个非连续镜头建一个关键帧产物（owner `shot`，slot `keyframe`，组件 `kf`），镜头退场或改成连续动作时它的关键帧产物标 `retired`。重跑时按「同一场 + 拍的行有重叠」、再按顺序沿用已采纳版本的镜头 id。
- `continuity_state` 没建（连续性账本在 M6）。

### 4.2 产物与版本（所有“四个按钮”的基础）

界面上每一张可以“改提示词 / 重跑 / 不满意换一个 / 历史”的卡片都对应一个 **product**；每次生成或编辑产生一个 **version**，只追加、不覆盖。

| 表 | 关键字段 |
| --- | --- |
| `product` | id, series_id, owner_type（series / episode / scene / shot / asset / line）, owner_id, slot（bible / suggestions / episodes / script / asset_list / ref_image / ref_views / text_image / voice / line_audio / shot_plan / keyframe / video / upscale / lipsync / qa / music / subtitles / cut）, component_id, current_version_id, adopted_version_id, locked_hash, status（empty / queued / running / ready / stale / adopted / locked / failed）；M3 加 pick_json、settings_json、retired |
| `product_version` | id, product_id, n, origin（run / rerun / switch / edit / fallback / import / auto_qa_rerun / comfy_ingest；M3 加 pick / upload）, parent_version_id, payload_json, files[]（role, path, sha256, mime, duration_s, w, h）, content_hash, intent, compiled, compiled_overridden, model_key, where（local / api）, seed, params_json, qa_json, qa_pass, cost_usd, job_id, created_at, note；本地 ComfyUI 生成的另有 workflow_id, workflow_sha256, comfy_env_hash（6.4.5） |
| `dependency` | product_id, upstream_product_id, upstream_hash（构建时上游已采纳版本的 content_hash） |
| `gate_decision` | id, gate（novel / script / assets / storyboard / takes / export）, scope_id, product_hashes_json, decided_at, action（confirm / reopen） |

规则：

- **current**：界面当前显示的版本；**adopted**：下游实际使用的版本；**locked**：闸门确认后锁定，`locked_hash` 记录内容哈希。
- 视频的多个 take 就是 `slot=video` 的多个 version；“推荐”取质检总分最高且通过的那个。
- 每次构建下游 version 时写 `dependency`（上游 product + 当时的哈希）。

**M2 的实际做法**（细节和理由见 `plans/M2.md`「设计要点」和 DECISIONS 里 M2 各步的条目）：

- **版本是唯一真相**。`bible_entity`、`suggestion`、`episode`、`beat`、`scene`、`script_line` 是已采纳版本的**物化表**：采纳时按 id upsert，版本里没有了的行标 `retired`（不硬删），随时能从版本重建（有测试）。id 在出版本时定：重跑时和它出发时的已采纳版本逐项比对，对上的沿用 id（设定按类别 + 名字 / 别名，分集、场按序号，剧本行在同一场里按文字相似度）。页面读接口从**当前**版本的 payload 现算，当前 ≠ 采纳时标「未采纳」。
- 小说也是产物：slot 多一个 `novel`（组件 `import`），每次导入、逐段编辑都出一个版本。
- **采纳**：第一个成功的版本自动采纳，之后的重跑只变当前，要用户点「采纳」；手改（改设定、拖节拍、改剧本行……）从当前版本出一个 `origin=edit` 的版本并采纳。唯一的自动替换是用户在影响范围里确认的「确认并同步」（硬规则 5）。
- **`dependency` 挂在版本上**，比上表多 `version_id`、`slice` 两列：一个版本读了上游哪几片就写几行，哈希是那一片的规范化 JSON（不含序号、「已修改」这类显示字段）。切片如 `chapter:<idx>`、`chapters`（小说各章 / 设定的章节摘要）、`names`（设定的名字和冻结条目）、`entities:<id,…>`、`adopted` / `adopted:<段号,…>`（已采纳的补写）、`episode:<id>`。「待更新」不存标志，每次比对切片哈希现算，改了再撤销就自动不旧。
- 补全建议的决定单独存 `suggestion_decision`（不进版本，重跑后按 id 带过去）；补全的「有效哈希」只算已采纳的建议。
- **`gate_decision`** 多 `series_id`；同一闸门同一范围以最后一条为准。小说闸门的 `scope_id` 是剧集 id，管小说、设定、补全；剧本闸门是集 id，管那一集的剧本；分集规划不归闸门。确认 = 锁定已采纳版本（`locked_hash`）并把有效哈希写进 `product_hashes_json`，重新打开 = 解锁。被锁的产物直接改返回 409 `product_locked`，要走 `/impact/preview` → `/impact/apply`（`mark` 解锁、写入、再锁上；`rerun` 级联重跑并采纳，被锁的先重新打开闸门）。

**M3 的实际做法**（候选、`pick` 和锁定）：

- **组件的两个开关**：`auto_adopt`（默认开；候选类组件 `img`、`text`、`voice` 关掉：一次运行出一个版本，候选都在 `files[]`，`role: candidate`、带 `idx`，由用户挑）和 `adopt_every_run`（每次运行都采纳：素材清单、补视图、台词配音，它们跟着上游走，不用挑）。
- **「选这个」**记在产物上：`product.pick_json = {version_id, idx}`（`POST /products/{id}/pick`），不进物化表，重建物化表或 `demo --reset` 不会丢。素材只在 `pick` 指向屏幕上那一版时才返回它。
- **锁定 = `ProductService.lock_pick()`**，一个事务里：出一个 `origin=pick` 的版本（只含选中那张，`role: ref`，沿用来源版本的模型、提示词、依赖；payload 只有 `{candidate}`，来源版本和第几张记在 `params`、不进哈希，所以同一张图从哪一版锁定哈希都一样）→ 采纳并锁定 → 写这条素材自己的 `gate_decision`（gate `assets`，`scope_id` 是素材 id）。锁定**不改当前版本**。`idx` 为空时锁定整个版本（上传的图、API 终版、音色）。音色**只有终版能锁、整版锁定**（锁试听 409 `voice_needs_final`）；画面文字选中的候选 OCR 不一致时 409 `ocr_mismatch`，带 `force: true` 才锁。
- **上传**出一个 `origin=upload` 的版本，只有这一张候选并自动选中（参考图和画面文字；PNG / JPEG / WebP，≤ 20 MB）。
- `product.settings_json`：画面文字的逐字内容、贴字方式、字体，音色来源，台词的手动情绪。描述 = 提示词的意图层。锁定后改这些都 409 `product_locked`，改走影响范围 `asset_edit`。
- `product.retired`：所属对象已经不在了（剧本重跑后退场的台词的配音）。不算待更新，不进进度和级联；这一行回来时取消。
- **哈希含文件**：媒体槽位（`ref_image`、`ref_views`、`text_image`、`voice`、`line_audio`）用 `media_slicer`，切片 = payload + 文件 sha（不含提示词）。闸门和下游依赖记的都是图片 / 音频本身。补视图依赖锁定图的哈希、道具依赖描述里提到的已锁定角色的图、配音依赖剧本切片 `line:<id>` 和说话人音色的锁定哈希；素材清单依赖剧本切片 `assets`（场的地点时段、每行的 id / 类型 / 人物、非对白行的文字，所以改对白措辞不影响清单）。
- **整集素材闸门**（gate `assets`，`scope_id` 是集 id）管这一集用到的素材（`asset_use` 里有、没退场的）：确认要求都已锁定，否则 409 `assets_not_locked {count, names}`；确认不锁任何东西、重新打开也不解锁（素材属于整部剧，各自锁定）。解锁一条素材时，用到它、已确认的集一起重新打开。导航「素材」的计数是已锁定 / 本集用到的（示例第 1 集 7 / 10）。
- **影响范围**：新改动类型 `asset_unlock`（解锁不改内容，由 planner 直接从依赖图列行：补视图、拿它做参考的道具）和 `asset_edit`（改已锁定素材的描述、画面文字设置或音色来源；「只改这里」只存新描述、锁定的仍是原图，「确认并同步」再让这条素材重出候选，选好新的再锁定下游才更新）。影响行按槽位（和集）合并、花费相加（「配音 · 60 句」带 `count`）。
- **级联的停止集**：`auto_adopt` 关着的组件（候选类）级联永远不重跑：级联会采纳重跑的结果，等于解锁原来锁定的、采纳一版没人选过的候选。所以改剧本不会重画参考图；补视图和配音照常跟着走。按组件判断，以后加候选类组件不用改级联。

**M4 的实际做法**（镜头、确认镜头和分镜闸门）：

- **第三个开关 `cascade_rerun`**（默认开）：关掉的组件「确认并同步」不自动重跑，只标「待更新」。`plan` 关掉：重做会盖掉手改的设定和镜头确认，剧本加删行、换类型或说话人后由用户在分镜页点「重跑」再采纳。和候选类的停止集一起在 `component.reruns_in_cascade` 里判断，估价也不算这些。
- **切片**：分镜规划读剧本切片 `shots`（场的地点、时段，每行的 id、类型、说话人，不含任何文字：改对白措辞、改动作描写都不让分镜规划变旧）和素材清单切片 `ids`（id、类别、名字）。关键帧读分镜规划的 `shot:<id>`（类型、景别、运动、站位、参考素材、拍的行、接哪个镜头，不含时长和声音）、拍的动作行 `line:<id>`、传出去的每张锁定参考图（整版哈希）。`keyframe` 是媒体槽位（哈希含文件）。没有产物承载的「待更新」原因用 `Invalidation.check(slot, fn)` 登记：关键帧按别的画幅画的也算待更新。
- **改镜头**：结构和设定字段从分镜规划的当前版本出一个 `origin=edit` 的版本并采纳；画面描述写在关键帧产物的提示词上（意图层），选哪张写关键帧产物的 `pick_json`。已确认的镜头（或分镜闸门已确认时）普通接口 409 `shot_confirmed`，改走影响范围 `shot_edit`。
- **确认镜头**（`PATCH /shots/{id} {confirmed: true}`）：非连续镜头做 `lock_pick`（草稿锁选中的那张，没选默认第 1 张；终版只有一张就锁整版），同一个事务里写一条 `gate_decision`（gate `shot`，`scope_id` 是镜头 id），哈希记分镜规划的 `shot:<id>` 切片和锁定的关键帧。连续动作只记决定，要求它接的镜头还在（409 `no_tail_shot`）；没有关键帧版本 409 `nothing_to_confirm`。取消确认：解锁关键帧、记 `reopen`，这一集已确认的分镜闸门一起重开。「待更新」（`confirm_stale`）= 已确认，但规划切片的哈希和确认时记的不一样，或者关键帧待更新。
- **分镜闸门**（gate `storyboard`，`scope_id` 是集 id）：前提是本集镜头都已确认、都不是待更新，否则 409 `shots_not_confirmed {count, labels}`（`GateService.precondition` 是可插拔的前提）；确认时锁定已采纳的分镜规划，重新打开时解锁。进度：`done` = 已确认的镜头数，`total` = 镜头数，`stale` = 待更新的镜头数（分镜规划本身待更新再加 1）。
- **影响范围**：新类型 `shot_edit`（目标是镜头 id，patch 是 `PATCH /shots/{id}` 的字段，或 `{split: {after_line_id}}` / `{merge: true}`）：行有关键帧重画、哪几个镜头要重新确认、分镜闸门重开；「只改这里」= 重开闸门、取消确认再写入，「确认并同步」再给碰到的镜头重出关键帧草稿。`spec_aspect` 见 13.3。`asset_edit` / `asset_unlock` 多「镜头 1-01、1-04… 共 n 个」和其中已确认、要重新确认的；`line_edit` 改说话的行多一行「时长跟着配音变」（只提示）。

### 4.3 运行、配置、记账

| 表 | 关键字段 |
| --- | --- |
| `job` | id, series_id, product_id, component_id, kind, queue（gpu / api:<provider> / cpu）, state（queued / waiting_confirm / running / succeeded / failed / canceled）, priority, attempt, max_attempts, params_json, est_cost_usd, error_json, fallback_from_job_id, created_at, started_at, finished_at |
| `model_call` | 见第 10 节，看板的唯一数据源 |
| `config_override` | scope（project / component / item）, scope_id, component_id, data_json |
| `provider_account` | provider_id, has_key, key_ref（keyring 名，不存明文）, base_url_override, enabled |
| `custom_model` | 用户自己加的 OpenAI 兼容模型：provider_id, model_id, display_name, price_in, price_out, caps_json |
| `budget` | scope（call / shot / episode / series）, scope_id, limit_usd |
| `machine_profile` | id, machine（Mock 的示例机器 pc / mac；真实机器为空）, scanned_at, data_json（第 12 节的检测结果：阶段、各项状态、最近一次安装、推荐、`found`、`comfy`、`download_bps`、`app_dir`；结构见 `setup/schema.py:ProfileData`）, updated_at |
| `installed_item` | profile_id, item_id, version, paths[], installed_at（用于卸载和重新检测） |
| `comfy_env` | hash, comfyui_version, comfyui_commit, python, torch, node_packs_json（每个节点包：名称、来源、git commit 或 Registry 版本、提供的节点类）, captured_at（识别到变化就新存一份，6.4.1） |
| `comfy_snapshot` | id, profile_id, manager_name（ComfyUI-Manager 里的快照名）, env_hash, reason（install / manual）, changes_json（这次要做的改动清单）, created_at；最近一次回滚：restore_requested_at, restore_from_hash（请求时的环境哈希）, restore_state（pending / done / incomplete / unchecked）, restore_diff_json（还不一致的地方）, restored_at（扫描核对通过的时间，6.4.1） |
| `comfy_workflow` | id, slug, model_key, name, tier（recommended / mine / unverified）, source（repo / user）, dir, file_sha256, bindings_json, deps_json, caps_json, check_json（最近一次体检）, trial_json（最近一次试跑）, created_at, updated_at（6.4.2） |
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
| views⁺ | 补视图 | image | 锁定的角色图 → 侧面、背面、四种表情各一张（M3） | — |
| ocr⁺ | 文字核对 | ocr | 画面文字的候选图 → 读到的字、和要求是否一致（M3，只有本地 RapidOCR） | — |
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

`assets` 和 `dub` 在原型里没有单独一行（分别在 03 素材页顶部和「音色」组件里），实现时作为独立组件，界面放在同一页。标 ⁺ 的 `views`、`ocr` 是 M3 加的，原型没有；「模型与兜底」页因此多「补视图」「台词配音」「文字核对（OCR）」三行。

### 5.1 关键行为

- **长小说**：按章节分块（每块不超过模型上下文的 60%），逐块抽取后合并；别名合并用 LLM 判定 + 用户确认。
- **结构化输出**：LLM 组件一律要求 JSON 输出，用 Pydantic 校验；校验失败带着错误信息重试一次，仍失败则任务失败并保留原始输出供查看。
- **LLM 修改先给差异**：LLM 对已有内容的改动以 diff（修订）形式展示，用户接受后才写成新的 version。
- **音频先行定时长**：`shot.duration_s = Σ(该镜台词音频时长) + 前后留白（默认 0.3 s + 0.2 s，可配）`；超过目标模型单段上限（H3 为 2–15 s）时提示拆镜。没有台词的镜头用手填时长。
  - M3（`pipeline/timing.py`）算到台词和场：一句 = 配过音就是音频长度，没配用剧本的估计，再没有按每秒 4 个字；一场 = 有说话人的行相加（动作行的时长 M4 由镜头决定）。镜头的 `shot_seconds` 写好、测好，M4 接上。
  - M4（`timing.shot_duration`，Kelvin 定）：说话的行（对白 + 画外音）的音频一句接一句，前后各留 0.3 / 0.2 秒，是这个镜头最短的长度，有对白时就用它（来源「音频」）；用户手填更长的就用手填的（「手动」），短于音频 422 `duration_below_audio {min_s}`，传 `null` 恢复自动；之后重配音变长了就按音频算。没对白的镜头用手填的，再没有用分镜规划的秒数，再没有 3 秒。画外音叠在动作镜头上时取两者中长的。单段上限取 `vid` 路由上各模型 `caps.duration_s` 上限中最小的（H3 15 秒），超过给 `split_hint`。
  - 台词音频进版本前统一处理（`media/audio.py`，ffmpeg）：48 kHz 单声道，−18 LUFS、真峰值 −1.5 dBTP（`components.yaml` 的 `audio.dialogue`），增益取「到目标响度」和「真峰值不超」中小的，不压缩不削波；首尾静音按拉响度之后的音量判断，结尾留 `tail_s`（0.3 s）的一半自然收尾 + 50 ms 淡出，再补另一半静音。后端算好 64 段波形峰值给前端画。
  - 情绪：手动设的优先，否则按语气里的关键词（`config/voice.yaml` 的 `tones`），都没有就是平静。
- **动态分镜**：前端把关键帧按时长排在时间线上，配台词音频播放；不需要后端渲染。可选导出幻灯片式 MP4（FFmpeg）。
  - M4（`web/src/pages/storyboard/Animatic.tsx`）：rAF 时钟；每句台词从镜头开头 0.3 秒起一句接一句放素材页配好的配音（不做预演配音 `pv`，Kelvin 定），没配音的句子静音、只显示字幕，并给「去配音」；连续动作镜头先用它接的那个镜头的关键帧（真正的尾帧要等 M5 的视频）；安全区开关叠在预演和关键帧候选上。幻灯片式 MP4 没做。
- **分镜规划和关键帧（M4）**：
  - `plan`：模型每场拆镜，给拍哪几行、类型、景别、运动、画面描述、参考素材、站位、没对白的时长初值；规则后处理（`shots/ops.py:normalize`）把能确定修好的直接修好、不为此重试：没拍到的行补一个镜头（画外音叠到前一个镜头）、说话的行重复了只留第一次、每场第一个镜头不是连续动作、连续动作接同一场前面最近的非插入镜头（插入镜头 = 特写且没有角色）、参考素材只留本集的、没给站位按参考素材摆、机位按景别放。
  - `kf`：和 `img` 一样是候选类（一次 3 张）、混合模式（本地草稿 → 选一张 →「用 API 出终版」1 张，父版本是草稿）。编译层写画幅、景别和之后的机位运动、场景、站位（俯视图转成「林晚在画面右侧，远处；机位在正前方」，只写这个镜头参考素材里有的角色和道具）、拍的动作行、画面文字（模型出字写逐字内容，后期贴字写「留出位置」）。参考图只传已锁定的，按角色 → 场景 → 道具 → 画面文字取到模型能收的张数（`caps.max_refs`，本地工作流按 `ref_image` 槽数），出终版时草稿占第 1 张；没传的在提示词里点名。
  - **默认模型**（Kelvin 2026-10-26，对比见 `reports/m4-kf-bakeoff.txt`）：本地草稿 FLUX 3 Klein（`comfy/flux3-klein`），API 终版 Nano Banana 2.1（`google/nano-banana-2.1`）。`kf.local` 是 `[flux3-klein, flux3-klein-t2i, qwen-image-edit, qwen-image, flux2-dev]`。Klein 的权重（清单 `w_flux3`）在要登录的 HF 仓库，不是必装项；**没装的机器草稿换 `kf.local` 里下一个能跑、有工作流的本地模型**（Qwen-Image-Edit），都跑不了才改走 API（`capabilities.restrict` 的 `local_models`）。`Resolved.unavailable` 列出组件所有跑不了的本地模型，不只是路由上被拿掉的。
  - **组件可以按输入换模型**（`Component.model_for`，`RunService` 先读输入再定模型、编译和估价）：Klein 和 Qwen-Image-Edit 2511 都只能按参考图编辑，一个镜头没有锁定的参考图时本地草稿改用 `kf.local` 里排在当前模型后面、这台机器能跑的第一个文生图模型（本家的：Klein 文生图 / Qwen-Image）。
- **画面文字**：分镜表里记录每个镜头的预期文字；质检用 OCR 逐字比对。
  - M3 先在素材上做（`qa/ocr.py`）：每张候选过一次 OCR（`router.call()`、写 `model_call`，$0）。两边 NFKC、去空白后逐字比，标点也算；只有句末标点没读到算一致。不一致分 `missing` / `wrong` / `has_text`（后期贴字的底图上读出了字）。没有 OCR 时标「未检查」（`ocr_ok: null`），不拦锁定。
  - 两种做法：模型直接出字（提示词带逐字内容和字体），或后期贴字（底图不要字、留位置；真正的合成在 M7）。
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
- 供应商表 `providers.yaml`：base_url、密钥名、模型列表（model_id、显示名、输入 / 输出单价、闲时规则、上下文长度、是否支持 JSON 模式）。初始数据见 `seed/providers.yaml`，**模型 ID 要对照官方文档核对**；「测试连接」按钮调 `GET /models` 校验密钥并列出可用模型。模型还可以写 `request`：每次调用都带上的额外请求字段，不覆盖适配器自己设的字段（M2 用它默认关掉各家的「思考」：DeepSeek / Kimi `thinking: {type: disabled}`，千问 `enable_thinking: false`；DeepSeek、Kimi、千问的模型 ID 已在 M2 第 13 步按官方文档核对）。
- 界面上写作类组件先列 6 家常用的，其余收进「更多供应商」（原型已实现这个交互）。
- 支持流式输出，经 SSE 推到前端。

### 6.3 其他 API

图像（Nano Banana Pro、GPT Image 2、Seedream 5.0）、视频（MiniMax H3 API 含 Regenerate-2K 和 Context-IR、Seedance 2.5、Gemini Omni Flash、Wan 3.0、Kling）、配音（MiniMax Speech 2.8 HD 含音色设计、ElevenLabs）、口型（sync lipsync-2-pro）、超分（Topaz Starlight）、配乐（ElevenLabs Music）、3D（World Labs Marble，v1 只占位）。各写一个适配器；长任务用厂商的异步任务接口轮询，轮询间隔指数退避。

**M3 的实际做法**（图像三家和 MiniMax 配音，2026-10-21 按官方文档核对、真实冒烟跑通；`modelhub/adapters/`）：

- **加适配器 = 填配置**：媒体模型在 `providers.yaml` 写 `adapter`（`gemini_image` / `openai_images` / `seedream` / `minimax_speech`），`modelhub/media_adapters.py` 按它挑类；没写的媒体模型「暂不可用」。媒体模型用 `account` 指向 `llm_providers` 里的账号，同一家的写作、出图、配音共用一个密钥（地址可用 `base_url` 另写）。共用的 HTTP 层 `adapters/http.py`：429、5xx、超时退避重试 2 次，以错误映射的 `retryable` 为准。
- **模型**：Nano Banana Pro `gemini-3-pro-image`（原生 `:generateContent`）；GPT Image 2 `gpt-image-2`（没参考图 `/images/generations`，有参考图 `/images/edits`，`quality: high`）；Seedream 5.0 flash `doubao-seedream-5-0-flash-260915`（火山方舟，总是 `watermark: false`、`b64_json`）；MiniMax `speech-2.8-hd`（耳语换 `speech-2.6-hd`）走 `/t2a_v2`，音色设计 `/voice_design`，用国内站 `api.minimax.cn`。
- **尺寸**：宽高从成片规格算（硬规则 10），每家换成自己支持的最近尺寸（`adapters/images.py:fit_size`），返回图按实际像素记 `w` / `h`。Gemini 传画幅 + 能盖住画面的最小档（9:16 2K 是 1536×2752）；GPT Image 2 向上取 16（1080×1920 → 1088×1920）；Seedream 向上取 16 再缩进像素范围。
- **n 张**：GPT Image 2 一次请求出 n 张；Gemini、Seedream 同时发 n 个请求。部分失败照实记张数和花费，全部失败才报错。
- **记账**：`Pricing` 加 `token_rates`（每百万 token，分 `text_in` / `image_in` / `text_out` / `image_out`）、`extras`（按次的附加服务，如音色设计）、`price_by_res`、`currency`（人民币按 `currency_rates.CNY_per_USD` 折算）；`Usage` 加 `tokens`、`calls`。返回了分项用量就按 token 算，否则按每张价格（每张价格也用于估价）。MiniMax 按返回的计费字数记；**音色设计费记在第一次用这个音色合成的那次调用上**（MiniMax 在那时才收），估价按 `charge_design` 算进去。
- **错误码**（中英提示在 `common:modelError`）：内容审核拦下 `content_blocked`（不重试）、只回文字没出图 `no_image`、额度用完 / 没开通付费 / 安全体验模式上限 `quota_exceeded`（不重试，和限流 `rate_limited` 分开）、MiniMax 的 HTTP 200 + `base_resp` 错误码映射成 `auth_failed`、`insufficient_balance`、`voice_not_found` 等。路由把失败原文的前 500 字写进日志（`model_call` 只存码）。
- **测试连接**：`POST /providers/{id}/test` 再逐个检查用这个密钥的媒体模型（结果在 `media`），只发不花钱的请求：Gemini、OpenAI 查 `GET /models/{id}`；方舟发一个一定被拒的请求（回 400 说明密钥和模型 ID 都对）；MiniMax 用 `POST /v1/get_voice`。
- 自动化测试全部用 respx，不触网；真实调用只在 `scripts/smoke/live_assets.py`（`DRAMA_LIVE=1`）。

### 6.4 ComfyUI 与工作流库

Kelvin 本机已经装了 ComfyUI，以后会用官方和社区的各种工作流。平台默认用这份已有的 ComfyUI，并把每个工作流登记成一个本地模型（2026-10-18 Kelvin 定，见 DECISIONS 同日条目）。

#### 6.4.1 用哪个 ComfyUI

- **默认用用户已装的那份**。定位顺序同第 12 节：正在运行的实例 → 常见目录 → 设置里的路径；找到就用它和它自己的 Python。机器上一份都没有时，按第 12 节装到 `~/.drama-studio/ComfyUI`。
- **识别只读**（M1；环境存 `comfy_env`，模型文件清单存 `machine_profile`）：
  - 路径、端口（`/system_stats` 的 argv 里的 `--port`；没在跑时按常见端口试）、ComfyUI 版本、它用的 Python 和 PyTorch 版本；
  - 节点包：`custom_nodes/` 下每个包的来源和版本。git 装的读 `.git` 里的 HEAD commit 和远端地址（直接读文件，不跑 git 命令）；从 Registry 装的读 `pyproject.toml` 的版本号和 Manager 留下的记录。ComfyUI 在跑时再用 `/object_info` 记下每个包提供哪些节点类；
  - 模型文件：按 ComfyUI 的模型目录（含 `extra_model_paths.yaml` 里配的）列出各类文件的路径和大小，ComfyUI 在跑时用 `/models`、`/models/{folder}`。不算哈希（同 12.2）。
- **改动前先问**：对这份 ComfyUI 的任何安装或升级（升级 ComfyUI 本身、装或升级节点包、往它的 Python 里装包、往它的模型目录里放文件），都先列出改动清单：每一项做什么、从哪个版本到哪个版本、来源、大小。用户确认后才动手。这些项不随「必需项默认勾上」自动勾选。
- **快照和回滚**：动手前用 ComfyUI-Manager 存一份快照（ComfyUI 版本、每个节点包的 commit 或版本、pip 包），在 `comfy_snapshot` 记下原因和改动清单。界面上可以一键回滚到任意一份快照；回滚要重启 ComfyUI 才生效，平台不替用户重启他自己的 ComfyUI，只提示。没装 Manager 时，「安装 ComfyUI-Manager」作为清单第一项一起问（ComfyUI 也要装时排在 ComfyUI 后面）。
  - 快照接口用 Manager 4 的 `/v2/snapshot/*`（按 4.2.2 核对）。存不成快照时，这次安装里改 ComfyUI 的项都不装（`install.snapshot_error`）。触发回滚前先建好 `custom_nodes/.disabled`：Manager 4.2.2 在这个文件夹不存在时会退成「复制再删除」，Windows 上删 git 的只读文件失败，回滚半途中止（DECISIONS 第 8b 步）。
  - **回滚只是排上**：Manager 下次启动 ComfyUI 时才执行，可能半途失败。所以只记请求时间和当时的环境哈希（`pending`），下一次扫描识别完 ComfyUI 后核对：和快照时一致 → `done`，记 `restored_at`；和请求时一样 → 还没重启，仍是 `pending`；都不是 → `incomplete`，列出差异。只比 Manager 会恢复的东西：ComfyUI 的 commit（没有就比版本）和节点包（多出、少了、版本不同），不比 Python、PyTorch（Manager 不降级 pip 包）。
- **平台自管的另一份 ComfyUI**（和已有的那份并存，用 `extra_model_paths.yaml` 共享模型）留作以后的选项，现在不做。

#### 6.4.2 工作流就是本地模型

每个工作流登记为一个本地模型（key `comfy/<slug>`，`kind` 按服务的组件定），由四部分组成：

| 部分 | 内容 |
| --- | --- |
| 工作流文件 | ComfyUI 的 API 格式 JSON（`workflow.api.json`），登记时算 sha256 |
| 绑定 | 语义槽位 → 节点和字段。**按节点标题**（API 格式里的 `_meta.title`）找节点，不按节点编号，所以在 ComfyUI 里重排、增删别的节点不影响；被绑定的节点标题在工作流里必须唯一。用 DramaStudio 输入 / 输出节点的工作流不用写绑定（6.4.3） |
| 依赖 | 节点包（名称、来源、git commit 或 Registry 版本）、模型文件（目录类别、文件名，可选 sha256 和下载地址） |
| 能力 | 服务的组件（关键帧、视频、超分、口型……）、画幅、时长、参考图数、显存需求。字段和 `providers.yaml` 的 `caps` 一致，所以成片规格的兼容表（13.3）和能力过滤（7.3）照常用 |

- **文件布局**：平台推荐的放仓库 `workflows/<slug>/`（`workflow.api.json` + `workflow.yaml`，后者写绑定、依赖、能力），上游 `workflows/selfhost/` 的 H3 工作流改成这个格式纳入；用户导入的放 `~/.drama-studio/workflows/<slug>/`。`comfy_workflow` 表登记它们，记档位、体检和试跑结果、文件哈希。
- **登记后出现在对应组件的 ModelPicker 本地模型列表里**。路由、兜底、记账、质检的规则都不变：它就是一个 `where=local` 的模型，照样走 `router.call()`、GPU 队列和 `model_call`。
- `providers.yaml` 里现有的 `comfy/*` 本地模型（H3、SeedVR2、FlashVSR、Qwen-Image-Edit……）以后都由工作流库提供：有对应的推荐档工作流才算可用。

#### 6.4.3 对接方式

- **首选：DramaStudio 输入 / 输出节点**（节点包 `integrations/comfyui-dramastudio` 的一部分，M5 先做；14.2 的镜头、素材、存回节点仍在 M9）：
  - 输入：首帧（IMAGE）、输入视频（VIDEO，超分、口型这类以视频为输入的工作流用）、参考图（IMAGE，按序号 1、2、3… 各一个节点）、提示词（STRING，正向 / 反向）、台词音频（AUDIO）、尺寸（宽、高）、帧率、时长（秒）、种子；
  - 输出：视频、图片、音频；
  - 绑定里的槽位名：`first_frame`、`video_in`、`ref_image`（带序号）、`prompt`、`negative`、`dialogue_audio`、`width`、`height`、`fps`、`seconds`、`seed`、`video_out`、`image_out`、`audio_out`（前端契约 `web/src/api/schemas/workflows.ts`）；
  - 平台只认这些节点：提交时按节点类型填值，按节点类型取结果，不用写绑定。节点在画布里有默认值，用户在 ComfyUI 里能直接手动跑。
- **兼容：普通工作流**（官方和社区的，没有 DramaStudio 节点）：导入时自动猜绑定，例如 `LoadImage` → 首帧、正向 `CLIPTextEncode` → 提示词、采样器的 `seed` → 种子、`EmptyLatent*` 的宽高 → 尺寸、`SaveVideo` / `VHS_VideoCombine` → 视频输出。猜的结果在绑定页逐项给用户确认，没确认完不能登记。
- **调用流程**：上传输入（`/upload/image` 等）→ 提交 `/prompt` → 用 WebSocket 收进度 → 从 `/history/{id}` 找输出节点的产物 → `/view` 下载。宽高、帧率、时长一律从成片规格（第 13 节）和镜头读出来填进对应槽位。

#### 6.4.4 导入体检和分档

导入（拖进 JSON 文件，或从 ComfyUI 的工作流列表里选）后自动体检：

1. **查缺**：用 `/object_info` 找出工作流里不存在的节点类，查 ComfyUI-Manager / Registry 的节点映射，对应到节点包和版本；把加载器节点引用的模型文件名和 `/object_info` 给的可选文件列表比对，找出缺的模型。
2. **问了再装**：列出要装的节点包（含版本）和模型（含大小），走 6.4.1 的「改动前先问 + 快照」，确认后按版本安装。
3. **试跑**：用示例输入（示例项目里的首帧、参考图、提示词、台词音频，草稿档尺寸，最短时长）跑一次，结果给用户看。

分三档：

| 档 | 条件 | 能怎么用 |
| --- | --- | --- |
| 平台推荐 | 随仓库提供，节点包和模型锁定版本，平台测过 | 进预设、自动路由、兜底 |
| 我的工作流 | 用户导入，试跑通过 | 同上 |
| 未验证 | 导入了但还没试跑通过（或文件变了、体检坏了） | 只能在 ModelPicker 里手动选；不进预设、兜底和「不满意换一个」的自动顺序 |

#### 6.4.5 可复现

- 本地 ComfyUI 生成的每个 `product_version` 和 `model_call` 都记下 `workflow_id`、`workflow_sha256`、`comfy_env_hash`。`comfy_env` 按哈希存当时的 ComfyUI 版本和全部节点包版本，所以任何一版都查得到是用哪份工作流、哪套节点跑出来的。（M3：`product_version` 已有这三列，取第一个本地调用的；`model_call` 还没有，M5 接工作流库时加。）
- 工作流文件变了（哈希不同）就降为「未验证」，重新试跑通过后回到原来的档。
- 每次装或升级节点包后，自动把所有已登记的工作流体检一遍：先做静态检查（节点类、被绑定节点的标题和字段、模型文件都还在）；用到了变动节点包的推荐档和「我的」档工作流，再在 GPU 队列里排一次低优先级试跑。有坏的就提示，并给出「回滚到这次安装前的快照」。

#### 6.4.6 界面

「模型与兜底」页加「工作流库」区域。原型里没有这一块，按 M0.5 的界面风格设计，做完截图给 Kelvin 看。

- 列表：名称、服务的组件、档位、体检状态（缺几个节点包 / 模型）、上次试跑、文件是否变过；
- 导入：拖进 JSON，或从 ComfyUI 的工作流列表里选；
- 绑定：槽位 ↔ 节点标题和字段，自动猜的标出来等确认；
- 体检：缺的节点包和模型清单、安装（弹 6.4.1 的改动清单）、快照和回滚；
- 试跑：示例输入、结果预览，通过后改档；
- 分档：手动降为未验证，或升为「我的工作流」（要先试跑通过）。

先用示例数据做出来（M1，MSW 返回），M5 再接后端。M1 已做，Kelvin 审过（审阅图 `reports/ui/workflows/`）：放页面最下面，点一行在下面展开，三个标签「绑定 / 体检 / 试跑」，默认打开最该处理的那个；装依赖复用首次启动页的确认弹窗。改档规则和试跑进度的轮询见 DECISIONS「M1 工作流库界面」。

#### 6.4.7 运行

- 本地 GPU 队列并发 1；调度器按“同一工作流”分组连续执行，切换大模型前调 `/free` 释放显存（PLAN：同一套模型的镜头连续跑，不再每镜卸载）。
- 本地任务超时（默认 10 分钟，可配）视为失败，进入兜底流程；取消时调 `/interrupt`（第 9 节）。

**M3 的实际做法**（最小版的 ComfyUI 适配器，`modelhub/workflows.py`、`adapters/comfyui.py`；DECISIONS 2026-10-21「第 12 步（下）」「第 13 步」）：

- **工作流目录**按 6.4.2 的布局：`workflows/<slug>/workflow.api.json` + `workflow.yaml`（`bindings` 槽位 → 节点标题 + 字段，载入时检查标题唯一、字段存在；`models` 加载器要的文件；`caps.sizes` 各画幅尺寸）。参考图槽位可以 `optional: true`：参考图比节点少时删掉空着的 LoadImage 和读它的输入。`providers.yaml` 的 `workflow:` 指向目录；目录还没有的（H3、SeedVR2 等）照旧不可用，M5 纳入。还没有 `comfy_workflow` 表和导入、体检、试跑（M5）。
- **三个工作流**（按官方模板改写）：`qwen-image`（2512 fp8 文生图，Lightning 4 步，草稿、画面文字）、`qwen-image-edit`（2511 int8 按参考图编辑，4 步）、`qwen-image-edit-hq`（同一张图去掉 LoRA、40 步、cfg 4.0，补视图默认用它）。输出用 PreviewImage（不往用户的 output 里留文件）；尺寸按模型卡推荐的各画幅尺寸（9:16 → 928×1664），没有对应画幅时按 `max_pixels` 缩放到 16 的倍数，到成片尺寸靠之后的超分 / 导出。
- **调用**：参考图上传到 `input/dramastudio/<sha256>.png` → `/prompt` → 每秒查 `/history/{id}`（WebSocket 进度在 M5）→ `/view`。n 张候选 = n 个 prompt，种子 seed、seed+1…，用到的种子记在结果里。负面提示走 `negative` 槽位（补视图按视图和表情给，`views.py:negative_for`）。
- **停下**：本地超时 / 取消时 `/interrupt`（带 prompt_id，只停我们的）并从队列删掉；每 10 次轮询看一次 `/queue`，任务既不在队列也不在历史里报 `comfy_lost`。
- **出错码**：`comfy_model_missing`、`comfy_node_missing`、`workflow_invalid`（`/prompt` 400）；`comfy_failed`、`out_of_memory`、`comfy_interrupted`（运行中）；`comfy_not_running`。都兜底到 API。
- **地址**从上次扫描拿（`SetupService.comfy_target()`）。**健康检查**：`/system_stats` 通、`/models/<folder>` 里有工作流要的每个文件。
- **显存租约**（`modelhub/vram.py`）：整个进程一把锁。每个工作流一个持有者（`comfy:<slug>`），换别的持有者（TTS worker 或另一个工作流）时先让上一个放手：ComfyUI `/free`、worker 退出。不设超时，等锁的时间算在本地超时里。
- **GPU 队列先跑完已加载模型的任务**（`core/jobs.py`）：同一优先级里先跑和上一个任务同一模型（`params.model_key`）的；一个任务里换模型由显存租约管。
- **`DRAMA_REAL_LOCAL=1`**：Mock 模式下本地模型（`runtime` 是 `comfyui` / `python`）照样建真实适配器，API 和写作模型仍是 Mock。本机真跑不花钱：`scripts/smoke/local_assets.py`。

#### 6.4.8 按镜头选工作流；拼节点（beta）

2026-10-18 Kelvin 定。

- **按镜头选工作流**（M5）：同一个组件里有多个可用工作流时，按镜头特征挑，例如有台词要对口型、多人站位复杂、参考图张数、时长超过上限。
  - 规则做成可编辑的表（和兜底设置同一处）；也可以让 LLM 规划器给建议。
  - **只在「平台推荐」和「我的工作流」两档里选**：官方的，或者用户导入、确认绑定、试跑通过的。「未验证」的照旧只能手动选。
  - 选了哪个、为什么，记进 `model_call`；Inspector 里可以手动换；兜底规则不变。
- **工作流里的可开关分支**：推荐档工作流可以预留 ControlNet、LoRA、超分这类分支。平台按镜头开关分支、换 LoRA；每个分支都要单独试跑过。
- **拼节点（beta，默认关）**：按 `/object_info` 的节点类型，从已有的成熟工作流（推荐档和「我的工作流」）里取片段拼成新图，给用户参考。
  - **拼完不跑**：不进 GPU 队列，不进路由。
  - 用户可以在 ComfyUI 里打开它；要用时走正常的导入流程，从「未验证」开始：确认绑定 → 体检 → 试跑。

### 6.5 本地工具类模型

质检和后期用到的本地模型（人脸相似度、SyncNet、Whisper、说话人相似度、OCR、Qwen3-VL）在独立 uv 环境里以子进程或常驻小服务运行，统一包成 `local_tools` 适配器；它们也写 `model_call`（花费为 0，记时长和显存）。

**M3 的实际做法**（本地 Python 运行时，`adapters/local_python.py`；DECISIONS 2026-10-21「第 12 步（上）」）：适配器叫 `local_python`，本地 TTS 也用它。

- **一个模型一个常驻 worker**：`~/.drama-studio/envs/<env>/` 里的 Python 跑 `workers/worker_<name>.py`，第一次调用时启动并加载模型，之后常驻，直到显存租约让它走或应用退出。M3 有三个：`worker_qwentts`（Qwen3-TTS VoiceDesign，试听）、`worker_indextts`（IndexTTS-2.5，本地终版和配音）、`worker_rapidocr`（RapidOCR，CPU，不拿显存租约）。
- **协议**（`workers/worker_protocol.py`，只用标准库）：一行一个 JSON，请求和回复带同一个 id；文件写到适配器给的临时文件夹。worker 把 fd 1 转到 stderr，stdout 只有回复；崩溃时 stderr 最后几行进错误信息（`worker_crashed`）。超时、取消就杀掉 worker，下次重新启动。
- **环境变量**：`PYTHONUTF8=1`、`HF_HUB_OFFLINE=1`、`HF_HOME=<安装位置>/hf`（运行时不联网，权重由安装器先下好）。
- **配置**：`providers.yaml` 的本地模型写 `worker`、`env`、`args`（`{models}` 是安装位置，`{envs}` 是环境目录）、`gpu`、`needs`。没装时调用报 `not_installed`，能力过滤会先把它绕开。
- **保护**：Qwen3-TTS 按字数限长（3 s + 0.8 s / 字），两次都碰到上限报 `tts_runaway`；配音的电平检查拦近乎静音的结果（`audio_silent`）。

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

模型选择器只列出满足当前镜头需求和成片规格的模型（参考图数量、时长、是否音频驱动、是否需要控制视频、画幅、分辨率）。需要 ControlNet 的镜头只显示本地模型。机器档案（第 12 节）里跑不了的本地模型隐藏。工作流库里「未验证」档的工作流只能手动选，不进预设、兜底和「不满意换一个」的自动顺序（6.4.4）。

按机器过滤（M1，`core/capabilities.py`）：

- `providers.yaml` 的本地模型写 `needs`（清单项 id）和 `requires_cuda`。
- 「有」= 最近一次扫描里状态为通过、需更新、注意的项，加上之后装好的项（档案的 `found`）。从没扫描过不过滤。
- `restrict()` 在 `resolve()` 合并完各层覆盖之后做（用户手选的本地模型也会被绕开）：`local_model` 置空；`local` / `hybrid` 改成 `api`，没有 API 模型的改成 `off`；兜底和 `alt_order` 里去掉跑不了的本地模型。`Resolved.unavailable` 给出每个模型缺什么（`cuda` 或清单项 id），供界面说明「本机跑不了」。
- 路由器每次调用和兼容表（13.3）都按过滤后的路由算。Mock 下扫描示例机器同样生效。

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

**M3：多次调用的组件整套兜底**。补视图（6 张）、音色终版（设计 + 5 个情绪）这类一个版本要调用多次的组件，每次调用都是 `router.call(..., fallback=False)`；任何一步失败，整套换到兜底模型重做（`run_flow`），所以一套视图、一个音色不会混用两个模型。音色和配音的兜底是本地 IndexTTS（没有 ElevenLabs 密钥）；配音的请求同时带 `voice_id` 和本地要用的说话人样音、情绪参考，API 失败时直接兜底到本地。试听不兜底（IndexTTS 不能按文字设计音色）。

### 7.6 预算

- 任何 API 任务入队前先 `estimate()`。超过单次上限、单镜头上限或本集预算剩余 → 任务进 `waiting_confirm`，前端弹确认（显示预计花费）。
- 全局开关：本集预算用完后暂停所有 API 任务。
- 表头的“本集 API 花费 / 预算”实时从 `model_call` 汇总。

**M2 的实际做法**（`modelhub/budget.py`）：

- **入队前**：整个任务的估价对比组件的单次上限（`per_call_cap_usd`，组件配置，出厂默认 $0.50）和本集剩余，任一超过就进 `waiting_confirm`，`job.params.confirm = {reason: per_call | episode, estimate_usd, limit_usd}`。本集剩余 = 本集预算 − 已花 − 排队和等确认任务的估价 − Σ（运行中任务的估价 − 它已花的，不小于 0）。设定、补全、分集不属于某一集，只查单次上限。本集预算存 `episode.budget_usd`，是设置，不进版本。
- **每次模型调用前**（路由器的 `BudgetGuard`）：用户确认过的任务可以花到确认的金额（`job.confirmed_usd`，重启续跑不再问），其余每次调用都要在单次上限内；兜底换到更贵的模型超了就失败（`budget_exceeded`），不悄悄多花。兜底方式「先问」时任务进 `waiting_confirm`，确认后用兜底模型继续。
- 同步接口的改写（剧本行 / 场、补全建议按要求重写）超限返回 409 `over_budget {estimate_usd, limit_usd}`，前端确认后带 `confirm_budget: true` 再发一次。
- 估价按 `max_tokens` 算输出，是上限：真实花费通常低得多（第 13 步冒烟：剧本化估 $0.025，实花 $0.005）。各模型默认关掉「思考」，否则思考过程的 token 不在估价里（见 6.2 `providers.yaml` 的 `request`）。
- 还没做：上面的「全局开关」（单独的暂停开关；超过本集剩余的新任务已经会先问），表头花费仍是示例数据（`/metrics/summary` 在 M8）。
- **M3 加的**：确认过的任务最多花到「确认金额 + 余量」，余量取确认金额的 10% 和 $0.05 中大的（`components.yaml` 的 `confirm_margin`，Kelvin 2026-10-21 定）；没确认的任务仍按单次上限、不留余量。原因：估价稍低时（Nano Banana Pro 实测低 2.7%），多次调用的任务会停在最后一次，前面的钱白花。媒体调用的结果按请求缓存（`llm_cache`，key 前缀 `media:`，含返回的 JSON 如 `voice_id`），任务重试或重启续跑时出过的不再花钱。

### 7.7 混合模式

本地出草稿（免费抽卡），用户点「采纳」时才用 API 出终版：视频走 H3 Regenerate-2K（输入为本地 768p take），LLM 走 API 模型重写定稿。终版作为同一 product 的新 version，origin=run，`parent_version_id` 指向草稿。

**M3 的实际做法**（素材；Kelvin 2026-10-20 定的第 5 项）：

- **参考图、画面文字**：本地出 4 张草稿（`stage: draft`，草稿档尺寸），用户选一张后点「用 API 出终版 · 约 $x」：`POST /products/{id}/run` 带 `where: api` 和 `params: {source_version_id, source_idx}`，以那张草稿为参考出 **1 张**（`stage: final`，交付档尺寸），成为新的当前版本，`parent_version_id` 是草稿。看过再锁定；草稿够用也能直接锁草稿。按钮只在路由是混合、屏幕上是本地草稿、素材没锁定时出现；价格是路由里 API 模型一张图的标价。上传的图也能当来源。原型 v2 的「4 张终版 $0.56」不照做。
- **音色**：「重跑」= 免费试听（本地 Qwen3-TTS 3 个，各读这个角色的前两句台词；没有本地 TTS 时一个试听是一次 MiniMax 音色设计）；「用 MiniMax 出终版」= 用选中的试听做音色设计拿 `voice_id`，再按 5 种情绪（平静、愤怒、哭腔、耳语、喊叫）各读一遍；「本地」来源由 IndexTTS 出 5 个变体，全程免费。配置在 `config/voice.yaml`。
- 补视图默认只走本地（`qwen-image-edit-hq`），API 只做兜底。

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
- SSE 事件类型：`job.updated`、`product.updated`、`version.created`、`cost.updated`、`gate.updated`、`sync.updated`、`setup.progress`、`setup.log`、`toast`。事件带递增 ID，支持 `Last-Event-ID` 补发。`product.updated`、`version.created` 带 `slot`（M3）：前端遇到 `line_audio` 只刷新配音；「做一打」的槽位（`ProductService.quiet_slots`，现在只有配音）出新版本不发「已生成」的 toast，在产物列表里也不逐个估价。

### 9.1 HTTP 接口概览（`/api/v1`）

标 ⁺ 的是后来补的接口（M0.5 做界面、M1 做首次启动和工作流库界面、M2 接真实后端时页面需要，原表没有）。M2 已在后端实现的：剧集、小说与设定、分集 / 场 / 剧本（镜头除外）、产物与版本（`unadopt`、打分、`upscale` 除外，M5）、影响范围、闸门（novel / script）、任务、配置与模型（`/custom-models` 除外）；M3 加上资产、台词配音、取文件、`pick`、素材闸门（`assets`）；M4 加上镜头、拆分合并、分镜闸门（`storyboard`）、确认镜头、影响范围 `shot_edit` / `spec_aspect`；其余仍由 MSW 返回示例数据（生成页、后期页的示例数据读后端的镜头；`GET /episodes/{id}/shots` 只给示例第 1 集叠加 `video_product_id`，M5 删）。请求和响应的字段以 `web/src/api/schemas/`（zod）为准，各接口的细节和理由见 DECISIONS「2026-10-14 · M0.5 界面先行」里按步骤记的条目。M0.5 里这些接口先由浏览器里的 MSW 返回示例数据，哪个里程碑实现哪个接口见 `web/src/mocks/handlers/index.ts` 的表；实现一个就删掉对应的 handler。

| 资源 | 接口 |
| --- | --- |
| 剧集 | `GET/POST /series`，`GET/PATCH /series/{id}`，`GET/PUT /series/{id}/spec`（成片规格，改画幅时返回影响范围；锁定后直接改画幅返回 409 `spec_locked`），`GET /series/{id}/spec/compat`⁺（模型兼容表），`GET /spec/presets`⁺（平台预设和各画幅尺寸），`GET /series/{id}/episodes`⁺，`GET /series/{id}/progress`⁺（还没分集时的导航徽标；小说闸门的状态） |
| 小说与设定 | `POST /series/{id}/novel`（上传；`dry_run` 只识别章节、返回 `upload_id`，正式导入要 `rights_confirmed`），`GET /series/{id}/novel`⁺（段落），`PUT /series/{id}/novel/chapters/{idx}`⁺（逐段编辑后整章提交），`GET /series/{id}/bible`（对象：条目 + 合并建议），`PATCH /bible/{entity_id}`，`POST /bible/merge`⁺（合并 / 不是同一个 / 拆出别名），`GET /series/{id}/suggestions`⁺，`POST /suggestions/{id}/accept\|reject\|rewrite`，`POST /suggestions/{id}/reset`⁺，`POST /series/{id}/suggestions/accept-all`⁺ |
| 分集、场、剧本、镜头 | `GET/PATCH /episodes/{id}`，`GET /episodes/{id}/progress`⁺（导航徽标），`GET /episodes/{id}/script`⁺，`PATCH /beats/{id}`（含拖动换集，返回整个方案），`PATCH /lines/{id}`、`PATCH /scenes/{id}`⁺（只改文字 / 场标题；已确认时 409，前端改走影响范围），`POST /lines/{id}/rewrite`⁺，`POST /scenes/{id}/rewrite`⁺，`GET /episodes/{id}/shots`⁺（M4：读分镜规划的当前版本；每个镜头带 `label`、`scene_no` / `scene_place`、时长 `duration_s` / `duration_source` / `min_s` / `planned_s` / `manual_s` / `longest_s` / `split_hint`、`keyframe_product_id` / `keyframe_pick` / `keyframe_sha256`、`confirmed` / `confirm_stale`、`seed_changed`），`PATCH /shots/{id}`⁺（设定字段、`intent`、`keyframe_pick`、`confirmed`；已确认 409 `shot_confirmed`；时长短于音频 422 `duration_below_audio`），`POST /shots/{id}/split\|merge`（拆分 `{after_line_id?}`，默认从中间切、只有一行时后一半是 2 秒的反应镜头；合并只和同一场的下一个，409 `split_point_invalid` / `no_next_shot`；都返回本集的镜头列表） |
| 资产 | `GET /series/{id}/assets?episode=`（M3 多 `scenes`：出现在本集哪几场，带全剧场号和行；`note`、`seed_changed`、`pick`；M4 起 `shots` 是已采纳分镜规划里引用它的镜头号），`POST /series/{id}/assets`（手动新建，还没做），`PATCH /assets/{id}`（描述、选这个、画面文字设置、音色来源；已锁定 409，改走影响范围 `asset_edit`），`POST /assets/{id}/lock`⁺ `{version_id?, idx?, force?}`（409 `ocr_mismatch` / `voice_needs_final`；解锁走影响范围 `asset_unlock`），`POST /assets/{id}/upload`⁺（multipart，PNG / JPEG / WebP ≤ 20 MB；音色 422 `upload_not_supported`），`POST /episodes/{id}/assets/analyze`⁺ → job（M0.5 是同步返回），`GET /episodes/{id}/assets/matrix`⁺（场 × 用到的素材，格子是行 id，空 = 整场） |
| 台词配音⁺ | `GET /episodes/{id}/dub`（每句的说话人、音色、状态 done / stale / missing / running / failed / no_voice / voice_not_locked、情绪和 `tone_emotion`、音频带波形、时长；每场时长和已配句数），`POST /episodes/{id}/dub` `{dry_run?, line_ids?}`（`dry_run` 只给估价和句数；否则每句排一个 `product.run`，跳过的行写明原因；`line_ids` 不管状态都重配），`PATCH /lines/{id}/dub` `{emotion}`（null = 按语气） |
| 文件⁺ | `GET /files/{sha256}`：版本里的媒体文件，类型按文件头判断，支持 Range，`immutable` 缓存 |
| 产物与版本 | `GET /products?owner=&component=`⁺，`GET /products/{id}`（含版本列表、`prompt`、`estimate`、`running`），`POST /products/{id}/run` `{mode: rerun\|switch\|run, model?, intent?, compiled?, count?, where?, params?}` → job（M3 加 `where: api` = 混合模式出终版，`params` 是带类型的 `RunParams`：`task`、`source_version_id`、`source_idx`，未知字段 422），`POST /products/{id}/pick`⁺ `{version_id, idx}`，`POST /versions/{id}/set-current\|adopt`，`POST /products/{id}/lock`，`POST /products/{id}/unlock`⁺，`POST /products/{id}/unadopt`⁺，`PUT /products/{id}/prompt`⁺，`POST /products/{id}/compile`⁺，`PATCH /versions/{id}`⁺（打分），`POST /versions/{id}/upscale`⁺ → job |
| 生成 | `GET/PUT /series/{id}/generate-rules`⁺（每镜候选数、质检不过自动重跑、单镜上限），`GET /episodes/{id}/generate-log`⁺（运行记录） |
| 后期 | `GET /episodes/{id}/timeline`⁺，`PATCH /clips/{id}`⁺，`PATCH /subtitles/{id}`⁺，`GET /episodes/{id}/export/checks`⁺，`POST /episodes/{id}/export`⁺ `{format: mp4\|fcpxml\|otio\|srt}` → job |
| 影响范围 | `POST /impact/preview`（给一个待改动，返回受影响的产物和预计花费），`POST /impact/apply` `{action: mark\|rerun\|undo}` |
| 闸门 | `POST /gates/{gate}/confirm\|reopen`（M3 加 `assets`：`scope_id` 是集 id，没锁完 409 `assets_not_locked {count, names}`；M4 加 `storyboard`：`scope_id` 是集 id，镜头没确认完或有待更新的 409 `shots_not_confirmed {count, labels}`） |
| 任务 | `GET /jobs`，`GET /jobs/{id}`⁺，`POST /jobs/{id}/cancel\|confirm` |
| 配置与模型 | `GET /config/components`⁺（组件目录、可选模型、`local_runtime_ok`），`GET /config/resolve`，`PUT /config/override`，`DELETE /config/override`⁺（恢复成预设），`GET/PUT /config/defaults`⁺（预设、兜底方式；代替原来的 `POST /config/preset`），`GET /providers`，`POST /providers/{id}/key`，`DELETE /providers/{id}/key`⁺，`POST /providers/{id}/test`，`POST /custom-models`（以后） |
| 开发⁺ | `POST /dev/llm-test`（只在 Mock 下），`GET /dev/model-calls`（最近的 `model_call`，冒烟脚本也读它） |
| 看板 | `GET /metrics/summary`⁺（顶栏花费），`GET /metrics/kpis\|spend-series\|calls-series\|shots\|components\|speed\|apis\|local-models\|qa\|episodes`⁺，`GET /metrics/export.csv`⁺（第 11 节） |
| 同步 | `GET/PUT /sync/targets`，`POST /sync/targets/{id}/detect`⁺，`POST /sync/run`，`GET /sync/log`，`GET /sync/board?episode=`⁺（ComfyUI 素材板），`POST /ingest`（ComfyUI 节点存回，第 14.2 节） |
| 首次启动 | `GET /setup/profile`（`simulated`：Mock 的示例机器；`download_bps`、`app_dir`；每项 `size_bytes`、`work_s`、`touches_comfy`，安装中的 `install`：`pct`、`bytes_done`、`bytes_total`、`speed`、`eta_s`、`verifying`），`POST /setup/scan` → 202，`POST /setup/install` `{items, mirror, dir}` → 202（要用户点头的列在 `install.confirm`，改 ComfyUI 的改动清单 `install.changes`，装前的快照 `install.snapshot` 或 `install.snapshot_error`），`POST /setup/install/confirm\|cancel`⁺，`POST /setup/items/{id}/retry\|skip`，`POST /dev/setup/machine`⁺ `{machine: pc\|mac}`（只在 Mock 下切示例机器，清空扫描和安装；真实模式 403 `setup_not_simulated`） |
| ComfyUI 与工作流库（6.4） | M1 已实现：`GET /comfy/env`（识别结果：路径、端口、版本、节点包、模型文件），`GET/POST /comfy/snapshots`（每份带最近一次回滚 `restore: {state, requested_at, diff}`），`POST /comfy/snapshots/{id}/restore` → `{snapshot, restart_required}`；M5（M1 先由 MSW 返回示例数据）：`GET /workflows`，`GET /comfy/workflows`⁺（ComfyUI 自己的工作流列表，供导入），`POST /workflows/import`，`GET/PATCH /workflows/{id}`（含改档），`PUT /workflows/{id}/bindings`，`POST /workflows/{id}/check`，`POST /workflows/{id}/deps`⁺（缺的节点包和模型的改动清单），`POST /workflows/{id}/deps/install`⁺（确认后先存快照再装），`POST /workflows/{id}/trial` → job，`POST /workflows/check-all` |
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
| 复现 | workflow_id, workflow_sha256, comfy_env_hash（本地 ComfyUI 调用才有，6.4.5） |

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

`config/setup-manifest.yaml`（解析见 `setup/manifest.py`；文件头的注释列了全部字段）。三个例子：

```yaml
- id: node_vhs                    # 社区节点包：git clone 锁 commit
  group: comfy                    # sys / rt / comfy / w(权重) / svc(网络与服务)
  name: {zh: VideoHelperSuite, en: VideoHelperSuite}
  required: false                 # 可选项失败只记录，不阻塞
  depends_on: [comfy]
  detect: {type: comfy_node, dir: ComfyUI-VideoHelperSuite}
  install:
    - {type: git_clone, url: "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite", ref: "<pinned commit>", dest: "{comfy}/custom_nodes/ComfyUI-VideoHelperSuite"}
    - {type: uv_pip, env: comfy, requirements: "{dest}/requirements.txt"}

- id: node_seedvr2                # ComfyUI 自带的节点：不是安装项，旧版 ComfyUI 提示更新
  group: comfy
  name: {zh: "SeedVR2 节点（本地超分）", en: "SeedVR2 nodes (local upscaling)"}
  requires_cuda: true             # 没有 CUDA 时显示「跳过，超分走 API」
  required: true
  depends_on: [comfy]
  detect: {type: comfy_node, classes: [SeedVR2Preprocess, SeedVR2Conditioning, ...], native_since: "0.28.0"}
  fix: {missing: {code: update_comfy_native, params: {version: "0.28.0"}}, skip: unsupported_upscale_api}
  install: []

- id: w_sr                        # 权重：放进 ComfyUI 的模型目录
  group: w
  depends_on: [comfy]
  detect: {type: downloads}       # 下面的文件都在就算装好
  size_gb: 8.8
  install:
    - type: download
      hf_repo: Comfy-Org/SeedVR2
      revision: "<pinned revision>"
      files:
        - {path: diffusion_models/seedvr2_7b_int8_convrot.safetensors, folder: diffusion_models, sha256: "..."}
        - {path: vae/seedvr2_ema_vae_fp16.safetensors, folder: vae, sha256: "..."}
```

M1 加的字段：

- `detect.native_since`：ComfyUI 自带的节点从哪个版本开始有。ComfyUI 在跑时按 `/object_info` 里的节点类判断，没在跑时按 ComfyUI 版本判断。
- 安装步骤的 `version`：给改动清单看的版本号（tag）；没写时用 commit 的前 7 位。
- `installable: false`：有安装步骤但暂时不能装（DramaStudio 节点包、本地 LLM）。
- `download` 的 `files`：文件名，或 `{path, folder, sha256}`。写了 `folder`（ComfyUI 的模型类别）就放到 ComfyUI 放这类新文件的目录：`extra_model_paths.yaml` 里 `is_default: true` 的那个（识别结果里 `ModelDir.default`，ComfyUI Desktop 的共享模型目录），没有就 `{comfy}/models/<folder>`；没写的放 `dest` 下。检测 `downloads`：这些文件都在（ComfyUI 的文件在它任一模型目录里都算）。
- `size_gb`（超过 10 GB 先确认，也用于预计用时）；`pkg` 步骤的 `admin: [winget, apt]`（这些包管理器要管理员权限，先确认）；`uv_pip` 的 `by_torch`（按 ComfyUI 的 Python 里现在的 PyTorch 选包，键 `<major.minor>+<cuda>`，表里没有就报 `torch_unsupported`）；`snapshot_first: false`（只有 ComfyUI-Manager 本身）；`fix` / `if_missing`；按平台覆盖的 `windows` / `macos` / `linux`。
- 顶层 `mirrors`（官方 / 国内：Hugging Face、PyPI、GitHub 代理前缀）和 `recommend`（按顺序取第一条满足 `when` 的预设）。

检测器类型：`platform`（系统、内存、磁盘）、`nvml`（显卡、显存、驱动支持的 CUDA）、`command`（跑命令 + 正则取版本）、`py_import`（在指定 uv 环境或 ComfyUI 的 Python 里）、`file`（存在 + 可选 sha256）、`downloads`（见上）、`comfy`（定位 ComfyUI，6.4.1）、`comfy_manager`、`comfy_node`（目录或 `/object_info` 的节点类，`native_since`）、`http`（测速）、`service`（本地 LLM 服务端口）、`service_model`、`keyring`（密钥是否已填）、`resolve`。

安装步骤类型：`uv_venv`、`uv_pip`、`uv_sync`（M3）、`git_clone`（锁定 commit）、`download`（12.2-7）、`pkg`（winget / brew / apt，需要管理员权限时先问）、`script`、`copy`。每一步都要幂等：动手前先检测，已经装好的记成「已经装好了」。

M3 加的（DECISIONS 2026-10-21「第 12 步（下）」）：

- 安装步骤 `uv_sync`：`uv sync --locked --no-dev --project <项目> --python <版本>`，`UV_PROJECT_ENVIRONMENT={envs}/<env>` 把环境放到项目外。项目是仓库里的 `runtimes/<name>/`（我们写的 pyproject + uv.lock）或先 git clone 的上游仓库。`--locked`：锁文件对不上就报错，不悄悄重新解析。锁文件里是 wheel 的完整地址，PyPI 镜像对它不起作用。
- 检测 `py_import` 加 `gpu: true`：环境里的 PyTorch 要是 CUDA 版，并且内核覆盖这块显卡（5090 是 sm_120），否则「需更新」（`env_no_cuda` / `env_gpu_arch`）；装完的复查也用它。
- 清单四项：`rt_qwentts`（qwen-tts + PyTorch 2.11 cu130 + VoiceDesign 1.7B 权重）、`rt_indextts`（index-tts 锁 `d9e41aa`，Python 3.11、PyTorch 2.8 cu128）、`rt_ocr`（rapidocr + onnxruntime，CPU，Mac 上也必需）、`w_img_t2i`（Qwen-Image-2512 fp8 + Lightning LoRA，约 22 GB 新下载）；IndexTTS 的辅助模型并进 `w_tts`（8.3 GB）。本地模型的 `needs`：`comfy/qwen-image` → `[comfy, w_img_t2i]`，`local/qwen3-tts` → `[rt_qwentts]`，`local/indextts2` → `[w_tts, rt_indextts]`，`local/rapidocr` → `[rt_ocr]`。Setup 页因此多 4 行（原型没有）。

清单按原型的 PC / Mac 两套列出，另外三项：`node_dramastudio`（我们自己的 ComfyUI 节点包，第 14.2 节）、`eagle`（只检测是否打开）、`resolve`（只检测版本和免费 / Studio）。运行环境和节点的地址、版本锁定见 DECISIONS「M1 清单补齐」，权重版本见「第 8b 步」。

### 12.2 流程

1. **扫描只读**：不改动任何东西，结果存 `machine_profile`，路由据此隐藏跑不了的本地选项。
2. **推荐**：按硬件给预设（5090 → 均衡；Apple 芯片 → 视频、关键帧、超分走 API）。
3. **安装**：用户勾选（必需项默认勾上）→ 按依赖顺序执行，日志经 SSE 实时显示，每步可重试或跳过；装过的东西写 `installed_item`，卸载能清干净；重新检测只补差异。
   - 一次安装是一个 `setup.install` 任务（cpu 队列），后端重启后续跑。依赖的项失败或跳过时，依赖它的项跳过。
   - 要用户点头的（管理员权限、单项下载超过 10 GB、改已装 ComfyUI 的改动清单）先列在 `install.confirm`，确认（`/setup/install/confirm`）才开始，取消（`/cancel`）什么都不装。
   - 装完再问一次检测器（只对装完马上就看得到的 `py_import`、`file`、`downloads`）；还检测不到就报 `not_detected`，不算装好。
   - 安装位置（`dir`）在程序自己的文件夹（`app_dir`）里时，页面给黄色警告，日志写 `dir_in_app`；只提示，不拦。
4. **镜像**：自动（测速选择）/ 官方 / 国内镜像（Hugging Face、PyPI、GitHub 代理）。
5. **安全**：不动系统 Python；所有 Python 依赖装进 `~/.drama-studio/envs/<name>`（uv）；单项下载超过 10 GB 先确认。
6. **已装的 ComfyUI**：按 6.4.1 只读识别；对它的任何改动（ComfyUI 和节点的安装、升级，往它的 Python 和模型目录里放东西）都单独列改动清单确认，动手前用 ComfyUI-Manager 存快照，可一键回滚，回滚后由下一次扫描核对。
7. **下载**（`setup/download.py`）：
   - 文件按 64 MB 分块写进 `.part`，`<name>.part.json` 记下完成的块，续传和单块重试都靠它；不支持 Range 的服务器退回单连接从头下。一个块连续失败 3 次整项失败，完成的块留着。下完校验 sha256。
   - 多连接动态分段：每个连接从一个空闲块一直流到文件尾，下一块被别的连接占了就停；新连接从最长的空闲段开始。连接数从 1 个起自适应：每 5 秒看一次总速度，快 10 % 以上就加一个（最多 8 个），否则退回并固定。
   - Windows 上 `.part` 设成稀疏文件。
8. **进度和预计用时**：
   - 后端给：每项 `size_bytes`（清单的 `size_gb`）和 `work_s`（下载以外步骤的经验用时）；档案的 `download_bps`（这台机器的下载速度：最近一次装完的下载项的平均速度，还没有时扫描末尾只读地测第一个权重文件的前 16 MB）；下载中的项每秒最多报一次 `bytes_done`、`bytes_total`、`speed`（最近 5 秒）、`eta_s`、`verifying`。
   - 前端算：开始前的预计用时（跟着勾选变）、整体进度（按用时加权）、剩余时间。体积用十进制 GB / MB。
9. **Mock**：`DRAMA_MOCK=1` 时检测和安装都是模拟的（`FakeProbe` 读 `tests/fixtures/setup/{pc,mac}.yaml`，`FakeRunner` 按步推进，SageAttention 在 60 % 报 `no_wheel`），什么都不会装；`simulated: true`，页面显示示例机器切换（`POST /dev/setup/machine`）。设 `DRAMA_SETUP=real`（或 `DRAMA_MOCK=0`）才真的扫描、真的安装。只读核对真实扫描：`scripts/setup_scan_real.py`。

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
- 视频组件：画幅、分辨率、帧率作为请求参数；本地 ComfyUI 工作流通过「尺寸 / 帧率 / 时长」输入节点或绑定注入（6.4.3）。
- 提示词编译：把画幅写进编译层（如“竖屏 9:16 构图”）。
- 参考图组件：角色、道具、画面文字按成片画幅出；场景固定 16:9（`components.yaml` 的 `img.aspects`，Kelvin 2026-10-26：竖屏空景容易出成分格拼图）。
- 分镜和关键帧页：叠安全区参考线（平台按钮、标题和进度条会挡住的地方，比例按平台预设，可在设置里调）。
- 后期：超分目标、导出预设、字幕位置、帧率转换（25 fps 重采样，30 fps 用本地插帧）。
- ComfyUI 的「镜头」节点输出宽高和帧率（第 14.2 节）。

### 13.3 兼容检查和锁定

- `spec/compat.py`：对当前路由里的每个模型，用适配器 `caps`（支持的画幅、最高分辨率、帧率、时长）判定 原生支持 / 需要转换 / 不支持，返回给前端表格；“不支持”的模型在 ModelPicker 里隐藏。路由按这台机器能力过滤后的算（7.3）。
- 第一张关键帧被采纳时写 `output_spec.locked_at`。锁定后改画幅：用失效传播算出受影响的关键帧和视频（以及按旧画幅出的场景参考图，标为可选），显示数量和预计花费，选项同 ImpactDialog。改分辨率或帧率只影响精修和导出，不触发重做。
  - 接口：锁定后 `PUT /series/{id}/spec` 改画幅返回 409 `spec_locked`；用户在影响范围里选了处理方式后带 `?confirmed_impact=<impact id>` 再写。M1 只检查这个参数不为空，影响范围由 MSW 示例给（M4 之前）；M2 有真的影响范围后再校验 id。
  - **M4 的实际做法**：`locked_at` 在第一张关键帧被采纳（= 第一个镜头确认，锁定选中的关键帧）时写，同一个事务（`on_adopt("keyframe")`）；出草稿不锁。改画幅是影响范围 `spec_aspect`（后端 `ShotService.plan_aspect`）：`keyframes_redraw {count, shots}`，估价按路由上的 API 模型出终版（示例 7 × $0.134），视频到 M5 才列；场景参考图固定画 16:9（`components.yaml` 的 `img.aspects`，Kelvin 2026-10-26），不跟规格变，所以不再列「建议重出场景参考图」（`ref_images_suggest` 只在配置让场景图跟着规格时才有）；「只改这里」写规格、取消所有已确认的镜头（分镜闸门跟着重开），「确认并同步」再给这些关键帧重出本地草稿。应用 `spec_aspect` 本身就写规格；`PUT …/spec?confirmed_impact=` 现在真的校验 id：必须是这个剧应用过的 `spec_aspect` 预览、改的是同一个画幅（内存里记最近 100 条，重启就没了），否则 409 `spec_locked`。
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
- **节点包 `integrations/comfyui-dramastudio`**（Python 节点 + 少量前端扩展），首次启动的安装清单里加一项。工作流用的输入 / 输出节点见 6.4.3（M5 先做），下面三个节点在 M9：
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
| `/setup` | Setup.dc.html | 首次启动 / 环境与安装。只在打开 `/` 而且从没扫描过（`scanned_at` 为空）时跳到这里，直接打开的深链接不跳。左侧导航工具区第一个是常驻入口「环境与安装」（在「成片规格」上面），随时重新检测、补装；徽标「缺 N 项」数必需、缺少或需更新、还没装好的项，就绪时不显示。原型没有的「你的 ComfyUI」面板（识别结果、快照、回滚）和安装确认弹窗也在这页 |
| `/s/:series/spec` | Spec.dc.html | 00b 成片规格；新建剧集时必经，之后从顶栏规格标签进入 |
| `/s/:series/e/:ep/novel` | Main.dc.html | 01 小说 · 导入与补全 |
| `/s/:series/e/:ep/script` | Script.dc.html | 02 剧本 · 分集与剧本化（含影响范围弹窗） |
| `/s/:series/e/:ep/assets` | Assets.dc.html | 03 素材 |
| `/s/:series/e/:ep/storyboard` | Storyboard.dc.html | 04 分镜 · 关键帧与镜头设定 |
| `/s/:series/e/:ep/generate` | Generate.dc.html | 05 生成 · 候选墙与自动质检 |
| `/s/:series/e/:ep/post` | Post.dc.html | 06 后期 · 时间线与导出 |
| `/models` | Models.dc.html | 模型与兜底 · 全局默认、预设、密钥、工作流库（6.4.6，原型里没有这一块） |
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
- ComfyUI-Manager 的快照和节点映射接口（独立安装的 Manager 和 ComfyUI 内置的新版 Manager 路径不同）、Registry 装的节点包记录在哪：实现时按当时的官方文档核对。
- ComfyUI Desktop 默认端口可能是 8000，和本平台后端的默认端口相同（待核对）：识别时要试这个端口；真冲突时平台后端换端口。

# 上游代码笔记（UPSTREAM_NOTES）

对象：fork 自 drama-series-agent（Apache 2.0）的初始代码，`src/drama_series_agent/`、`web/`、`workflows/selfhost/`、`scripts/`、`docs/contracts/`。
本文只记录读代码得到的事实，行号以 M0 开始时的提交（`5e650b7`）为准。仓库里**没有任何测试文件**（`git ls-files | grep -i test` 为空）。

## 1. 概览

上游是"一会话绑定一部剧"的短剧 Agent：聊天（LLM + tool calling）驱动 S1 设定/文学/角色 → S2 生成 `episode-run.jsonl` → 本地 ComfyUI 跑 MiniMax H3 R2V 逐镜出片 → ffmpeg 拼 `master.mp4`。所有状态都放在 JSON/JSONL/Markdown 文件里，没有数据库。

入口：

| 入口 | 位置 | 说明 |
| --- | --- | --- |
| `drama-series-api` | `pyproject.toml [project.scripts]` → `cli.py:run_api_main` | argparse `--host/--port`，**在函数内部**新建 `FastAPI`、加 CORS `allow_origins=["*"]`、`include_router(series_router, prefix="/api")`，然后 `uvicorn.run`。没有 app factory、没有 lifespan。 |
| `drama-series-render` | `cli.py:run_episode_main` | `--project --episode --cast-series --from-shot --force --context-ir off\|local\|api --comfyui-url`，`asyncio.run(run_episode(...))`。 |
| `python -m drama_series_agent` | `__main__.py` | 等同 `run_api_main`。 |
| `scripts/run_api.py` | 和 `run_api_main` 完全重复的一份 app 构建代码（start.sh/start.ps1 调的是它）。 |
| `scripts/h3_r2v_episode_run.py` | 包一层 `run_episode_main`。 |
| `scripts/hermes_drama_intake.py` | S1 intake CLI（`run_intake` / `--dump-schemas` / `--call <tool>`）。 |
| `scripts/doctor.py` | 环境检查；`scripts/_port_r2v_stack.py` 是从 Pixelle-Video 搬代码的一次性脚本（硬编码 `E:\...` 路径，无用）。 |
| `start.ps1` / `start.sh` | 设 `DRAMA_SERIES_ROOT`=仓库根、默认 `COMFYUI_URL`，读 `.env`，必要时 `pip install -e ".[render,dev]"`，`-WithWeb` 时 `npm run dev`，最后跑 `scripts/run_api.py`。 |

`cli.py:_ensure_path()`、所有 scripts 都会改 `sys.path` 并 `os.environ.setdefault("DRAMA_SERIES_ROOT", 仓库根)`。依赖：fastapi、uvicorn、pydantic v2、loguru、httpx、openai、imageio-ffmpeg；可选 `comfykit`（`[render]`）。构建用 setuptools，`requires-python>=3.10`。

## 2. 模块地图

**根**
- `cli.py`：两个 console script 入口（见上）。
- `llm_presets.py`：`LLM_PRESETS` 列表（ModelScope/Qwen/OpenAI/Claude/DeepSeek/Ollama/Moonshot 的 base_url + 默认模型），`find_preset_by_base_url` 等查找函数。

**intake/**（S1 素材接入，纯文件操作，无 LLM）
- `constants.py`：阶段常量、`MOUNT_KEYS`、脚本/图片/音频扩展名、音色 2–15 s。
- `scaffold.py`：`scaffold_project()` 建 `projects/{slug}` + `dramas/{slug}` + `templates/{slug}` + `data/cast/{slug}`，写 `project.json`（含**绝对路径** `mounts`）；`load_project()`。
- `case_matrix.py`：脚本/图片/音频有无 → S/I/A 用例码与路由建议。
- `fs_util.py`：`file_sha256`、不可变拷贝、音频时长/图片尺寸探测。
- `ingest.py`：脚本/角色图/音色入库，`mark_deferred`。
- `manifest.py`：`IntakeManifest` → `intake_manifest.json`，`handoff_stage2.json`，`gap_report.md`。
- `memory_ops.py`：向 `memory/PROJECT.md` 追加事实；`ask_slots`。
- `pipeline.py`：`run_intake()` 串起以上步骤。
- `dispatch.py` / `tool_schemas.py`：S1 工具的名字分发与 OpenAI tool schema。

**drama/**（S1-B 到 S4 的业务逻辑）
- `runtime.py`：`SeriesRuntime` dataclass ↔ `series_runtime.json`，原子写 + `.bak`，进程内 `RLock`。
- `job_events.py`：`JobEvent`、`JobEventType`、`JobKind`、`append_event_jsonl`。
- `event_bus.py`：进程内 `InMemoryEventBus` 单例 `get_event_bus()`。
- `comfy_worker.py`：Comfy 渲染任务（线程 + 全局 `_JOBS`/`_CANCEL` 字典）、取消、续跑、单镜重渲、`resolve_templates_dir`。
- `build_worker.py`：**确定性**（正则）把文学剧本解析成节拍并生成 `episode-run.jsonl` + `episode-meta.json`；`run_s2_build_and_comfy`。
- `enrich.py`：文学生成（`run_literary_generate`，可走 LLM）、Accept 文学/角色、角色表抽取、角色图生成（默认只写占位 PNG）、音频暂缓、S1 闸门。
- `literary_skill.py`：用 `skills/0xsline-short-drama` 拼 system prompt，**直接调 LLM** 写每集剧本。
- `series_bible.py`：系列圣经 5 个 md 的状态/读写/校验，`run_series_develop`（**直接调 LLM**），保存时标记下游脏。
- `develop_skill.py`：`skills/drama-series-develop` 提示词包。
- `develop_intent.py` / `literary_intent.py`：正则判断用户话术意图（开发圣经 / 写集 / 出片）。
- `asset_studio.py`：文学与角色图的列表/保存/上传、用户首帧、`invalidate_accept`、`mark_episodes_downstream_dirty`、`propagate_literary_write`。
- `decisions.py`：`decisions/accept.jsonl` 追加式 Accept 记录、`hash_paths`。
- `review.py`：S4 镜头列表、改提示词、accept/lock/unlock、`rerun_shots`。
- `next_episode.py`：下一集预取、`continue_series`、系列进度、音色收集建议。
- `episode_progress.py`：按磁盘文件汇总每集/每镜完成度、`rebuild_master_from_shots`。
- `completion.py`：`on_episode_complete` 更新 runtime、尾帧登记、写记忆、发事件。
- `dispatch.py` / `tool_schemas.py`：S1-B ~ S4 共约 45 个工具的分发与 schema。
- `validate_contracts.py`：按 `docs/contracts/*.schema.json` 校验（有 jsonschema 就用，否则轻量检查）。

**adapters/**
- `__init__.py`：惰性 `__getattr__`，避免循环导入（注释说曾因此死锁）。
- `config/__init__.py`：`config_manager = _Manager()` **模块级单例**，读写 `$DRAMA_SERIES_ROOT/config.json`（缺省 `cwd`）。
- `config/schema.py`：`HostAppVideoConfig`、默认值（从 `COMFYUI_URL`、`LLM_*` 读）、`deep_merge`。
- `media_client.py`：`MediaCore` / `MediaService`，通过 **comfykit** 的 `ComfyKit.execute(workflow, params)` 执行工作流；全局 `_CORE` 单例。
- `media_ops.py`：`resolve_ffmpeg`（含 `E:\Program Files\Pixelle-Video...` 硬编码候选）、`extract_tail_frame`、`concat_videos`（默认裁每镜开头 0.3 s 后重编码）。
- `paths.py`：`workspace_root`、`get_resource_path("workflows",...)`、`get_data_path("cast",...)`。
- `progress.py`：`ProgressEvent` dataclass（宿主 UI 桥，基本没用）。
- `service.py`：遗留 shim，导入时就创建 `get_media_core()`。
- `r2v/schema.py`：`ShotRunLine`、`FirstFrameRef`、`EpisodeMeta`、加载函数。
- `r2v/validate.py`：`validate_episode_run` 结构 + 提示词规则（`<Picture N>`、`<Audio N>`、必须有 `<d>[Chinese]…</d>` 对白、禁"不说话"类词）。
- `r2v/runner.py`：`run_episode` 逐镜串行渲染（第 5 节）。
- `r2v/workflow_materialize.py`：按参考图/音频数量裁剪工作流节点。
- `r2v/cast_refs.py`：从 `data/cast/{series}/` 找角色锚点图和音色。
- `r2v/first_frame.py`：解析首帧来源到磁盘路径。
- `r2v/continuity.py`：`continuity/episode-tails.json` 读写。
- `r2v/context_ir.py`：Context-IR（off/local/api），api 模式**直接 urllib 调 MiniMax**。
- `r2v/comfy_cleanup.py`：`POST /free` 释放显存。

**agent/**
- `agent_loop.py`：`run_agent_turn` 最多 8 轮 tool-calling 循环；带"模型没调工具就强制入队写集"的兜底。
- `prompts.py`：中文 system prompt（嵌入当前状态）。
- `tools_merge.py`：合并 intake + drama 工具 schema。
- `dispatch_bridge.py`：`run_tool` 先走 drama 分发，未知再走 intake；强制把 `project_dir` 注入参数。
- `session_store.py`：`projects/_series_sessions.json` 会话索引，`create_conversation` 会 scaffold 项目。
- `chat_store.py`：`memory/chat.jsonl` 追加/读取。
- `turn_trace.py`：`memory/traces.jsonl` 每轮工具 span + 确定性轨迹评分。
- `ui_hints.py`：`build_status_payload` 给前端的状态聚合。
- `paths.py`：`default_workspace_root`、`projects_root`、`sessions_index_path`。

**api/**
- `routers/series.py`：唯一的 router（1544 行，第 4 节）。
- `schemas/hermes.py`：请求/响应 Pydantic 模型。

**utils/**
- `llm_client.py`：OpenAI 兼容客户端与多厂商适配（第 7 节）。
- `llm_util.py`：`fetch_available_models`、`test_llm_connection`（httpx 调 `/v1/models`）。
- `skills_paths.py`：定位 `skills/` 目录。

## 3. 数据文件

根目录 = `DRAMA_SERIES_ROOT`（默认仓库根）。下列目录都在 `.gitignore` 中。

```
config.json                                 # LLM/ComfyUI 设置，api_key 明文
projects/_series_sessions.json              # {conversations:[{conversation_id, series_id, project_dir(绝对), title, updated_at}]}
projects/{slug}/
  project.json                              # project_id/slug/title/aspect/production_profile + mounts{dramas_dir,templates_dir,cast_dir,input_dir,drama_series_root}（绝对路径）
  series_runtime.json (+ .bak)              # L1 状态机，见下
  intake_manifest.json  handoff_stage2.json  gap_report.md  short-drama.json  .short-drama/state.json
  输入/                                      # intake 原件
  memory/PROJECT.md  chat.jsonl  traces.jsonl
  decisions/accept.jsonl                    # Accept 记录（追加）
  jobs/events.jsonl  jobs/{job_id}.jsonl    # JobEvent 流水
dramas/{slug}/
  creative-plan.md world.md characters.md art-style.md episode-directory.md   # 系列圣经（≥80 字算"有"）
  episodes/ep001.md …                       # 文学剧本（真相源）
  literary_index.json                       # {series_id, premise, characters, episodes, status, writer, …}
templates/{slug}/                           # = run_episode 的 project_root
  run/EP001.episode-run.jsonl  EP001.episode-meta.json  EP001.status.jsonl
  剧集/EP001/screenplay.md                  # 文学镜像
  assets/open.png  assets/episode_open/EP00N.png   # 默认/用户首帧
  continuity/episode-tails.json             # {EP001:{tail_frame(绝对), tail_shot_id, master_path?, updated_at}}
  output/EP001/master.mp4  output/EP001/tmp/r2v_SHOT-001.json
  output/EP001/shots/SHOT-001/video.mp4 tail_frame.png context_ir_{mode}_{hash}.txt/.json context_ir_prompt.txt
data/cast/{slug}/
  cast_table.json  series_manifest.json  series_style.json
  {角色}.png | draft/{角色}.png | voices/{角色}.wav | unassigned/
```

`episode-run.jsonl`（每行一个 `r2v/schema.py:ShotRunLine`）：`schema_version`, `episode_id`, `shot_id`（`SHOT-001`）, `order`, `duration_seconds`（>0 且 ≤15.5）, `video_prompt`, `first_frame{source: external|prev_shot_tail|prev_episode_tail|keyframe_file, path?, prev_shot_id?, prev_episode_id?}`, `ref_characters`（≤8）, `ref_voices`（≤3）, `audio_mode: native|tts`, `link_mode: chain|independent`, `cast_series_id?`, `drama_refs?`。
`episode-meta.json`（`EpisodeMeta`）：`episode_id`, `default_audio_mode`, `default_link_mode`, `aspect`, `h3_workflow`, `cast_series_id`, `ref_image_size`, `context_ir`。
`status.jsonl`：runner 每镜一行 `{shot_id, status: done|failed, at, cast_series_id, n_images, n_audios, context_ir, prompt_chars, video | error}`。

`series_runtime.json`（`docs/contracts/series_runtime.schema.json`，`additionalProperties:false`）：`contract_version`, `series_id`, `conversation_id`, `stage`（idle/s1_intake/s1_enrich/s2_ready/s2_building/s2_rendering/s3_episode_done/s4_review/s5_maintain/s6_deliver/series_idle）, `default_workflow`, `aspect`, `context_ir`, `last_completed_episode`, `next_episode`, `active_job_ids`, `enrich_jobs[]`, `episodes{EPxxx:{status, workflow, master_path, jsonl_path, resume_from_shot, accepted_shots, locked_shots, failed_shots}}`, `s1_gate{literary_accepted, cast_leads_accepted, audio_status, ready_for_s2}`, `deliveries[]`, `updated_at`。
**代码写出的值超出 schema**：`stage="s2_interrupted"`（`comfy_worker.py:_apply_cancel_to_runtime`）、episode `status` 为 `needs_rebuild`/`interrupted`，以及 `literary_dirty/cast_dirty/bible_dirty/dirty_reason/dirty_at/tail_frame/tail_shot_id/completed_at` 等字段。

`accept_decision.schema.json`：`decision_id, decision_kind(artifact_acceptance|cast_image_acceptance|workflow_acceptance|episode_acceptance|shot_acceptance), artifact, character, episode_id, shot_id, status(accepted|rejected|superseded), target_hashes{relpath:sha256}, decided_by, decided_at, series_id, supersedes_decision_id`。
`job_events.schema.json`：必填 `event_id, event_type, job_id, job_kind, series_id, ts`；另有 `episode_id, shot_id, workflow, index, total, ratio, phase, progress, paths, error, message`（见第 8 节）。

环境变量：`DRAMA_SERIES_ROOT`；`COMFYUI_URL`（`COMFY_URL` 兜底，默认 `http://127.0.0.1:8188`）；`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`（只作 `config.json` 的默认值）；`MINIMAX_API_KEY`/`MINIMAX_GROUP_API_KEY`、`MINIMAX_API_BASE`/`MINIMAX_BASE_URL`（Context-IR api）；`FFMPEG_PATH`/`FFMPEG_BINARY`/`IMAGEIO_FFMPEG_EXE`；`start.*` 里的 `HOST`/`PORT`；前端 `VITE_HERMES_API_BASE`。

## 4. HTTP API（`api/routers/series.py`，`APIRouter(prefix="/series")`，挂在 `/api` 下）

所有会话接口先 `_require_conv(cid)` 查 `_series_sessions.json` 拿 `project_dir`；大多数写操作还会往 `chat.jsonl` 追加一条中文 assistant 消息。

| 方法 路径（省略 `/api/series`） | 用途 |
| --- | --- |
| GET `/conversations` · POST `/conversations` | 列会话；新建会话（同时 scaffold 项目） |
| GET `/conversations/{cid}` | 会话 + `build_status_payload` |
| GET `/conversations/{cid}/messages` · `/traces?limit=` | 聊天记录；turn trace |
| POST `/conversations/{cid}/messages` | 发消息：正则快路径（开发圣经 / 写集 / 出片）或进 `run_agent_turn` |
| POST `/conversations/{cid}/actions/accept_literary\|accept_cast\|defer_audio` | S1 闸门操作 |
| POST `/conversations/{cid}/s2/build\|validate\|comfy` | 生成 jsonl（同步）/ 校验 / 入队 Comfy |
| GET `/conversations/{cid}/bible` · GET/PUT `/bible/{file_name}` | 圣经列表 / 读 / 存（存时标记下游脏） |
| GET `/conversations/{cid}/literary` · GET/PUT `/literary/{episode_id}` | 文学列表 / 读 / 存（invalidate） |
| GET/POST/DELETE `/literary/{ep}/first-frame`，GET `/first-frame/image` | 每集用户首帧 |
| GET `/cast` · GET `/cast/{character}/image` | 角色列表 / 图片 |
| POST `/cast/characters` · `/cast/upload` · `/cast/generate` | 新增角色 / 上传图 / 用图像工作流生成 |
| GET `/jobs` · POST `/jobs/cancel` · `/jobs/resume` | 任务快照+每集进度+最近 60 条事件 / 软取消 / 断点续跑 |
| GET `/episodes/{ep}/master` · `/episodes/{ep}/shots/{shot}/video` | 下载成片 / 单镜预览 |
| POST `/episodes/{ep}/shots/{shot}/regenerate` · `/episodes/{ep}/rebuild-master` | 单镜重渲 / 只重拼 |
| GET `/conversations/{cid}/events` | "SSE"：每秒轮询内存 bus，约 60 s 后结束，要求客户端重连；无事件 ID |
| GET/PUT `/settings` · POST `/settings/reset` | 读/写/重置 `config.json`（**响应里含 api_key 明文**） |
| POST `/settings/test_llm` · `/settings/load_models` · `/settings/test_comfyui` | 测 LLM / 拉模型列表 / `GET {url}/system_stats` |

`api_cast_generate`（L990）`from api.dependencies import get_drama_series_agent` —— 这个模块在仓库里**不存在**，该接口必然 ImportError（Pixelle-Video 搬迁遗留）。

## 5. H3 runner（`adapters/r2v/runner.py:run_episode`）

签名：`async run_episode(*, project_root, episode_id, from_shot=None, force=False, force_shot_ids=None, core=None, width=None, height=None, cast_series=None, context_ir=None, context_ir_force=False, context_ir_api_with_media=True, free_vram_between_shots=True, unload_models_between_shots=True, progress_callback=None, cancel_check=None) -> Path(master.mp4)`。`project_root` 是 `templates/{slug}`。

流程：
1. 读 `run/{EP}.episode-meta.json`（缺省 `EpisodeMeta`）和 `run/{EP}.episode-run.jsonl`，按 `order` 排序，`validate_episode_run` 有错直接 `ValueError`。
2. `core = get_media_core()`（comfykit）；`_resolve_workflow_file(meta.h3_workflow)` → `workflows/selfhost/...`。
3. 逐镜**串行**循环：
   - `from_shot` 之前的镜头：若已有 `video.mp4` 就加入拼接列表并发 `shot_skipped(reason=before_from_shot)`。
   - `cancel_check()` 为真 → 发 `shot_cancelled`，抛 `JobCancelled(shot_id)`（只在镜头边界生效）。
   - 已有 `video.mp4` + `tail_frame.png` 且未 force → `shot_skipped(already_done)`。
   - 解析首帧（`first_frame.py`）→ `resolve_ref_image_paths`（Picture 1 = 首帧，之后是角色锚点）、`resolve_ref_audio_paths`。
   - `materialize_r2v_workflow(base, n_images, n_audios, ref_image_size)` 写到 `output/{EP}/tmp/r2v_{shot}.json`（固定文件名，便于 ComfyUI 缓存）。
   - `apply_context_ir(...)` 得到最终 prompt。
   - `build_r2v_media_params` → `core.media(prompt, workflow=tmp路径, media_type="video", duration, ref_image_i, ref_audio_i)`；结果 URL 用 `urllib.request.urlretrieve` 或拷贝到 `shots/{shot}/video.mp4`；ffmpeg 抽 `tail_frame.png`。
   - 追加 `status.jsonl`；发 `shot_done`。异常时写 failed 行、发 `shot_failed` 并**整集中止**（re-raise）。
   - `finally`：`free_comfyui_memory(unload_models=True, free_memory=True)`（`POST {url}/free`，失败再试 `/api/free`），发 `shot_phase(freeing_vram)`——**默认每镜都卸载模型**。
4. `concat_videos` → `output/{EP}/master.mp4`；把最后一镜尾帧登记到 `continuity/episode-tails.json`；发 `episode_done`。

**ComfyUI 交互**：上游没有自己实现 HTTP/WS。上传、提交 `/prompt`、等待完成、取结果全部由第三方库 `comfykit`（`ComfyKit(comfyui_url=...).execute(workflow_path, params)`）完成；参数注入依赖 comfykit 的"节点标题 DSL"：节点 `_meta.title` 写成 `Prompt, $prompt.value!`、`Duration seconds, $duration.value`、`ref_image_0, $~ref_image_0.image`、`ref_audio_0, $~ref_audio_0.audio`。只有 `/free` 是自己用 urllib 调的。没有 `/interrupt`，没有超时控制。

**materialize（≈ 我们的 bindings.yaml）**：`workflow_materialize.py` 写死节点 ID——`MINIMAX_NODE="136"`（`MiniMaxH3ReferenceToVideo`），图片 `LoadImage` 节点 `200..208`，音频 `LoadAudio` `210..212`。按实际数量把 `136.inputs["ref_images.ref_image_i"] = [nid, 0]` 连上，多余的 Load 节点直接删掉，并设 `ref_image_size`。分辨率**不注入**：`comfy_worker` 从不传 width/height，尺寸取工作流节点 `115 ResolutionSelector` 里写死的 `aspect_ratio="9:16 (Portrait Widescreen)", megapixels=0.3`；`series_runtime.aspect` 只写进 meta，不影响出图。这和硬规则 10（`output_spec` 唯一尺寸来源）冲突，bindings 需要覆盖节点 115 和 136 的这些字段。
`workflows/selfhost/` 里 `video_minimax_h3_r2v{,_fast,_turbo,_lora}.json` 是 API 格式；`Minimax_h3_r2v_lora.json` 是 UI 格式（`nodes[]`），不能直接提交。`series.py:_HERMES_VIDEO_DEFAULTS` 还列了不存在的 `video_minimax_h3_i2v.json`。

**Context-IR**（`context_ir.py:apply_context_ir`）：`off` 原样返回；`local` 用正则把镜头/节拍/SFX 段改写成更长的英文描述（确定性，无模型）；`api` 上传参考图/音到 MiniMax `/v1/files/upload` 得 `mm_file://`，`POST /v2/h3_context_ir` 建任务，轮询 `/v2/query/video_generation/{task_id}`（5 s 间隔，300 s 超时），失败回退 local。结果按 `sha256(mode, duration, prompt, 文件路径+size+mtime)[:16]` 缓存在镜头目录。注意：runner 的默认是 `context_ir or meta.context_ir or "local"`，但 `comfy_worker` 传的是 `rt.context_ir or "off"`。

**首帧/尾帧连续性**：`build_worker` 生成时 order=1 的首帧优先级：用户上传 `assets/episode_open/EP00N.*` > EP001 用 `assets/open.png`（每次从主角图刷新）> EP002+ 用 `prev_episode_tail`；order≥2 一律 `prev_shot_tail` + `link_mode=chain`（validate 强制 chain 必须用前一镜尾帧）。因此整集是一条链：任何一镜重渲都会让后续镜头的首帧失效，但上游**不会自动重渲后续镜头**（只有 `review.rerun_shots` 用 force 从最早镜头往后全重跑）。尾帧由 `media_ops.extract_tail_frame` 抽取；跨集通过 `continuity/episode-tails.json`（`save_tail` + `completion._ensure_episode_tail`）。

**进度回调**：`progress_callback(dict)`，`type ∈ {shot_skipped, shot_started, shot_phase, shot_done, shot_failed, shot_cancelled, episode_done}`，带 `shot_id, index, total, phase, video, tail, error, master, reason`；回调异常被吞掉。没有镜头内（采样步数）进度。

## 6. 失效传播和断点续跑

**失效（"脏"标记，不是哈希比对）**：
- `asset_studio._mark_episode_run_dirty`：在 `series_runtime.episodes[EP]` 上写 `literary_dirty=True`（总会写），按原因再写 `cast_dirty`/`bible_dirty`，`dirty_reason`、`dirty_at`；清空 `accepted_shots`、`failed_shots`；状态不是 building/rendering/interrupted 时改 `status="needs_rebuild"`。
- `mark_episodes_downstream_dirty` 对指定集或 `list_known_episode_ids`（runtime + `dramas/episodes/*.md` + `run/*.jsonl` 的并集）全部打标。
- 触发点：`save_literary_episode`（sha256 变化时 → `invalidate_accept(literary)` + `propagate_literary_write` 同步 `剧集/EP/screenplay.md` 并只标这一集）；`series_bible.save_series_bible_doc`（5 个圣经文件内容变化 → 所有集 `bible`）；`upload_cast_image` / `reject_cast_image` / `_cast_image_worker` / `accept_cast_images`（→ 所有集 `cast`）；上传/清除用户首帧（→ 该集）；`run_literary_generate` 写完的每个 md。
- `invalidate_accept`：清 `s1_gate.literary_accepted` / `cast_leads_accepted` / `ready_for_s2`，`decisions/accept.jsonl` 追加 `superseded`，`s2_ready` 回退到 `s1_enrich`。
- 判 stale：`build_worker.enqueue_build_episode_jsonl` 和 `run_s2_build_and_comfy` 里，只要任一 `*_dirty` 为真或 `status=="needs_rebuild"` 就 `force=True` 重建 jsonl；重建成功后 `build_episode_jsonl_scaffold` 清掉 dirty 字段并置 `status="ready"`。**已渲染的镜头视频不会被标记失效**：jsonl 重建后，runner 仍会因为 `video.mp4`+`tail_frame.png` 存在而跳过这些镜头，除非调用方传 `force`。Accept 的 `target_hashes` 只记录不校验。

**断点续跑**：
- 粒度是"镜头已完成 = `shots/{id}/video.mp4` 和 `tail_frame.png` 都存在"（`episode_progress.build_episode_progress`），没有任务表。
- 取消：`comfy_worker.cancel_job` 设 `_CANCEL[job_id]`，runner 在下一个镜头边界抛 `JobCancelled`，`_apply_cancel_to_runtime` 写 `episodes[EP].status="interrupted"`、`resume_from_shot`、`stage="s2_interrupted"`，发 `JobCancelled` + `Milestone` 事件。ComfyUI 端正在跑的那一镜不会被打断。
- 续跑：`resume_episode` 取 `from_shot` 参数 > `episodes[EP].resume_from_shot` > 第一个未完成镜头（`continue_from_shot`），再 `enqueue_comfy_episode(from_shot=...)`。runner 对 from_shot 之前的镜头只收集现有视频。
- `--force`：所有镜头重渲；`force_shot_ids`：只强制指定镜头（`regenerate_shot` 先删该镜 `video.mp4`/`tail_frame.png`，再 `from_shot=该镜, force_shot_ids=[该镜]`——之后已完成的镜头会被跳过，不会因首帧变化重渲）。
- 进程重启后 `_JOBS` 丢失；`active_job_ids` 里的残留 id 在 `/jobs` 里显示为 `unknown`，没有自动恢复。
- `review.rerun_shots` 检查 `locked_shots`，但随后以 `force=True` 调 `enqueue_comfy_episode`，runner 不认识锁，**from_shot 之后的锁定镜头也会被覆盖**（违反"锁定不被自动替换"）。

## 7. LLM 调用

配置与密钥：`utils/llm_client.py:load_llm_settings()` 读 `config_manager.get_llm_config()`（`config.json` 的 `llm.api_key/base_url/model`，默认值来自 `LLM_*` 环境变量），`normalize_base_url`，ModelScope 时 `ensure_inference_model` 会 GET `/models` 并在模型不可用时**自动改模型并写回 config.json**。密钥明文存在 `config.json`、经 `/settings` 返回前端。`prepare_request_kwargs` 对 ModelScope/Qwen3/GLM 加 `extra_body.enable_thinking=False`；`vendor_supports_tools` 决定是否带 tools；`chat_completions_create` 做"先带 tools、空 choices 再不带 tools"+ 429 重试 3 次。没有计费、没有 token 记录。

**所有直接调模型/厂商的地方（后面都要改走 `router.call()`）**：

| 位置 | 方式 | 用途 |
| --- | --- | --- |
| `utils/llm_client.py:chat_completions_create` | `AsyncOpenAI().chat.completions.create` | Agent 对话（被 `agent/agent_loop.py:_default_llm_chat` 调用） |
| `drama/literary_skill.py:_chat`（L63） | `create_sync_client` → `OpenAI().chat.completions.create`，temp 0.7，max_tokens 4000 | 每集文学剧本（`write_with_skill`，经 `enrich._literary_worker`） |
| `drama/series_bible.py:_chat_develop`（L301） | 同上，timeout 240 s，max_tokens 4500 | 系列圣经 5 文件（`_develop_worker`） |
| `utils/llm_client.py:list_inference_model_ids` | `httpx.get {base}/models` | ModelScope 模型探测 |
| `utils/llm_util.py:fetch_available_models` / `test_llm_connection` | `httpx.Client.get /v1/models` | 设置页测试、拉模型列表 |
| `adapters/r2v/context_ir.py:_upload_file/_create_ir_task/_poll_ir_prompt` | `urllib.request` → MiniMax API | Context-IR api 模式（付费） |
| `adapters/media_client.py:MediaService.__call__` | `comfykit.ComfyKit.execute` | 所有 ComfyUI 生成（runner、`api_cast_generate`） |
| `adapters/r2v/comfy_cleanup.py:free_comfyui_memory` | `urllib.request` POST `/free` | 释放显存 |
| `adapters/r2v/runner.py:_download_or_copy` | `urllib.request.urlretrieve` | 下载 Comfy 产物 |
| `api/routers/series.py:api_cast_generate`（L1040）/ `api_test_comfyui`（L1533） | `httpx.AsyncClient.get` / `httpx.get /system_stats` | 下载生成图 / 测连通 |

另外 `agent_loop.run_agent_turn` 每轮都调一次 `load_llm_settings()`（可能触发 `/models` 请求）。

## 8. 事件与任务

- **事件模型**（`job_events.py`）：`JobEvent` dataclass，`event_type` ∈ `JobQueued, BuildStarted, BuildDone, ShotStarted, ShotProgress, ShotDone, ShotFailed, EpisodeDone, JobCancelled, JobFailed, EnrichStarted, EnrichDone, Milestone`；`job_kind` ∈ `literary_generate, series_develop, cast_image_generate, intake_finalize, build_episode_jsonl, comfy_episode, export_package`；`phase` 限定在 queued/building/validating/uploading/sampling/downloading/freeing_vram/concat/done/failed/cancelled；`event_id="evt_"+uuid`，`ts` ISO。
- **总线**（`event_bus.py`）：进程内单例 `_BUS`，`publish` 存进**无上限的** `_history` 列表并同步回调订阅者；`set_jsonl_log(path)` 是**全局**的，最后一个调用 `enqueue_comfy_episode` 的项目决定所有事件写到哪个 `jobs/events.jsonl`。另外各 worker 自己也 `append_event_jsonl` 到 `jobs/{job_id}.jsonl` 和 `jobs/events.jsonl`，可能重复。
- **任务执行**：没有队列。`enqueue_comfy_episode`、`enqueue_build_episode_jsonl`、`run_literary_generate`、`run_cast_image_generate`、`run_series_develop` 都是 `threading.Thread(daemon=True)`（Comfy 线程里再 `asyncio.run`）；`run_in_background=False` 时同步执行。任务状态在 `comfy_worker._JOBS` 全局字典（`upsert_job_snapshot` 被各 worker 共用），取消标志在 `_CANCEL`。**没有 GPU 并发限制**：两次出片请求会同时向 ComfyUI 提交。
- **runtime 字段**：`active_job_ids`、`enrich_jobs[]`（`enrich._track_enrich_job`）、`episodes[EP].status`。
- **dispatch**（`drama/dispatch.py:handle_tool_call` → `_dispatch` 的 `if name == ...` 链，约 45 个工具）返回 JSON 字符串，供 Agent 调用；`agent/dispatch_bridge.run_tool` 在 drama 未知时回落 intake。

## 9. 前端 `web/`

React 19 + Vite 8 + TS 6，**无路由库、无状态库、无 i18n、无 Tailwind/shadcn、无测试**，npm（`package-lock.json`），包名 `hermes-web`。API 基址 `VITE_HERMES_API_BASE`，默认写死 `http://127.0.0.1:8000/api/series`（`src/api.ts`，跨域靠后端 `*` CORS）。文案中文硬编码。

hash 路由（`src/routing.ts:parseHash`）：`#/` 聊天主页；`#/c/:cid/literary[/:ep]` → `LiteraryPage`；`#/c/:cid/bible[/:file]` → `BiblePage`；`#/c/:cid/cast` → `CastPage`；`#/c/:cid/jobs` → `JobsPage`。主页（`App.tsx`）= `SystemConfigPanel`（设置）+ `StatusBar` + `ChatPane` + `Workbench`（S1 闸门/S2 按钮、跳转各页）+ `NewChatModal`。

调用的接口：第 4 节表中除 `/events` 外基本全部（`api.ts` 定义了 `eventsUrl` 但没人用）。实时性全靠 `setInterval` 轮询：发消息后轮询 messages+conversation（最多 60/120 次）、`JobsPage` 每 2.5 s `GET /jobs`、`LiteraryPage`/`BiblePage` 也有定时刷新。

## 10. 可复用清单与改造建议

| 上游模块 | 处理 | 对应 SPEC |
| --- | --- | --- |
| `adapters/r2v/schema.py`、`validate.py` | 直接复用（作为 H3 镜头导出格式与提示词校验），规则中"每镜必须有对白"要可配置 | 5 vid 组件 / 6.4 |
| `adapters/r2v/workflow_materialize.py` | 包一层：节点 ID 改从 `<name>.bindings.yaml` 读；补 width/height/fps 注入 | 6.4、13 |
| `adapters/r2v/runner.py` | 拆开重写：逐镜逻辑变成 `pipeline/components/video.py` 的单镜任务，串行循环交给调度器；保留首帧解析、尾帧、跳过已完成的语义 | 5、9 |
| `adapters/media_client.py`（comfykit） | 重写为 `modelhub/adapters/comfyui.py`（自己的 HTTP+WS：`/upload/image`、`/prompt`、WS、`/history`、`/view`、`/interrupt`、`/free`），经 router | 6.4、硬规则 1/8 |
| `adapters/r2v/comfy_cleanup.py` | 逻辑并入 comfyui 适配器；改为"切换模型前才 free"，不再每镜卸载 | 6.4 |
| `adapters/media_ops.py` | 包一层复用（ffmpeg 定位、尾帧、拼接+裁 0.3 s）；删 `E:\Pixelle` 硬编码候选；加 ffprobe | 5.1、post/ |
| `adapters/r2v/first_frame.py`、`continuity.py`、`cast_refs.py` | 包一层：路径改为从数据库资产/版本解析，保留来源语义 | 4.2、pipeline/continuity.py |
| `adapters/r2v/context_ir.py` | local 模式可复用；api 模式改成 minimax 适配器经 `router.call()` | PLAN 改造节、6.3 |
| `adapters/config/`、`llm_presets.py` | 重写为 `core/config.py` + `config/providers.yaml` + keyring；预设数据可搬进 YAML | 7、15 |
| `utils/llm_client.py` | 厂商适配（thinking 关闭、tools 能力、空 choices 重试）搬进 `modelhub/adapters/openai_compat.py`；去掉"自动改模型写回配置" | 6.1、6.2 |
| `utils/llm_util.py` | 并入 `POST /providers/{id}/test` | 9.1 |
| `drama/runtime.py`、`event_bus.py`、`job_events.py`、`comfy_worker.py`、`build_worker.py` 的任务部分 | 重写为 `core/jobs.py`（SQLite 持久化队列）+ `core/events.py`（带递增 ID 的 SSE） | 9 |
| `drama/asset_studio.py` 的 dirty/invalidate | 重写为 `pipeline/invalidation.py`（按版本依赖图传播，覆盖到镜头视频） | 4.2、5 |
| `drama/build_worker.py` 的剧本解析 | 参考其节拍解析和 Ref2VA 提示词拼装（`_build_video_prompt`），作为 plan/vid 组件的 H3 模板来源 | 5、8 |
| `drama/literary_skill.py`、`series_bible.py`、`develop_skill.py` + `skills/` | 提示词素材可复用到 `prompts/templates/`；调用改走 router，输出改 JSON + Pydantic | 5.1、8 |
| `drama/decisions.py`、`review.py` | 概念（accept/lock/superseded）映射到 version 的 adopt/lock；代码重写 | 4.2 |
| `intake/*` | 大部分不需要（我们从小说入口）；`fs_util.file_sha256`、音频时长探测可复用 | 4.1 |
| `agent/*`、意图正则（`*_intent.py`） | v1 不用（对话式 Agent 放 P3），保留不动 | 9 |
| `api/routers/series.py` | 暂时保留挂在 `/api/series` 以便上游 UI 可用，新接口另建 `api/app.py` + `/api/v1` | 9.1 |
| `web/` | 新前端按原型重写；`api.ts` 的接口列表可作对照 | 16 |
| `workflows/selfhost/*.json` | 直接纳入，补 bindings.yaml | 6.4 |

**已知的坑**：
- **全局状态，和 app factory 冲突**：`config_manager`（导入时就读 `config.json`，路径取导入时的 `DRAMA_SERIES_ROOT` 或 cwd）、`media_client._CORE`、`event_bus._BUS`（含全局 `_jsonl_path`）、`comfy_worker._JOBS/_CANCEL`、`runtime._RUNTIME_LOCKS`；`adapters/service.py` 导入即创建 MediaCore。测试里换 `DRAMA_SERIES_ROOT` 后这些不会跟着变。
- **app 构建重复且无 factory**：`cli.py:run_api_main` 与 `scripts/run_api.py` 各建一次 `FastAPI`，无 lifespan、无静态前端挂载；CORS 全开 `*`（应限 127.0.0.1）。
- **根目录解析不一致**：多数用 `DRAMA_SERIES_ROOT`，但 `comfy_worker.canonical_hermes_project` 和 `validate_contracts._CONTRACTS` 用 `Path(__file__).parents[3]`，`config/_config_path` 缺省用 `cwd`；`cast_refs` 用 `get_data_path` 而不是 `project.json.mounts.cast_dir`。
- **绝对路径落盘**：`project.json.mounts`、`_series_sessions.json.project_dir`、`episode-tails.json.tail_frame`、`status.jsonl.video` 都是绝对路径，Windows ↔ Mac 之间不可移植。
- **Windows**：大量中文目录名（`输入/`、`剧集/`）；`concat_videos` 用 `as_posix()` 写 concat 列表；`series.py` 下载结果用 `NamedTemporaryFile(delete=False)` 再重开（Windows 友好但需自己清理）；`open_path_external` 按平台调系统打开。
- **密钥**：`config.json` 明文 + `GET /settings` 返回 `api_key`/`comfyui_api_key`/`runninghub_api_key`，违反硬规则 3。
- **尺寸**：分辨率写死在工作流节点 115，`aspect` 不生效（见第 5 节）。
- **schema 漂移**：runtime 写出 schema 以外的 stage/status/字段（第 3 节）；`docs/contracts` 的 `$id` 还叫 `hermes/...`。
- **坏代码**：`api_cast_generate` 导入不存在的 `api.dependencies`；`_HERMES_VIDEO_DEFAULTS` 引用不存在的 i2v 工作流；`_default_cast_images` 只写占位 PNG；`_port_r2v_stack.py` 硬编码 `E:\` 路径。
- **并发**：线程 + 文件锁只在进程内有效；无 GPU 串行保证；进程重启任务丢失；`_history` 无限增长；`/events` 实际是 60 s 的轮询流。
- **没有测试**：上游没有任何测试，改造时要先给要复用的部分（schema/validate/materialize/first_frame/media_ops）补单测。

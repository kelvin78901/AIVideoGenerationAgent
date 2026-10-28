# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M5 视频生成**，计划 [`plans/M5.md`](plans/M5.md)（Kelvin 2026-10-26 批准，定的四项见 DECISIONS 2026-10-26「M5 计划」）。M4 已合并（PR #6，9667069），报告 [`reports/M4.md`](reports/M4.md)。
- 分支：`m5-video`（从 main 9667069 开出）。

## 已完成的小步

- 第 0–2 步（afb8bc4、c58354c、704434c；DECISIONS「M5 计划」「M5 第 1 步」「M5 第 2 步」）：计划和分支；迁移 `0019`、`media/video.py`、Mock 视频带音轨；工作流库 `wflib/`（登记、档位、导入、猜绑定、UI→API）和 `api/routes/workflows.py`。 第 3 步（22a0206；ruff 格式补丁 8588eb1，CI 那次因此红，DECISIONS「M5 第 3 步」）：`wflib/service.py` 体检（`/object_info` + Manager 节点表）、`deps`、`install_deps`（`SetupService.install_node_packs`：先快照、再 git clone + pip）、试跑任务 `workflow_trial`、全部体检和 `broke_after_install`；导入后自动体检；路由 5 个；示例机器加节点表、更多核心节点。`test_workflows_api.py` 共 9 个。全量 pytest 728 个、Playwright e2e 37 个过；ruff、mypy（含 linux）干净。
- 第 4 步（9ad44b7；Kelvin 选 B 的记录 a5c6848，DECISIONS「M5 第 4 步」）：`workflows/h3-i2v/`（官方 I2V 模板展开，对着本机 `/object_info` 静态核过；8 步 Turbo LoRA、768P 档、台词音频走 `MiniMaxH3AddGuide`，没音频时旁路）；`comfy/h3` 指过去；`modelhub/workflows.py` 的文件槽位通用化 + `bypass`；`ComfyUIAdapter` 上传首帧 / 视频 / 台词音频、WebSocket 进度（`CallContext.on_progress`，试跑接到 `job.updated`）、取视频 / 音频并探测校验、试跑自造输入；库里仓库工作流用 `providers.yaml` 点名它的模型键（`h3-i2v` → `comfy/h3`）；`websockets` 写进依赖（只 `uv lock`）。`test_comfyui_adapter.py` 共 21 个（新 7 个）。全量 pytest 735 个过；ruff、mypy（含 linux）干净。
- 第 5 步（a427890；Playwright 偶发修复 bf3de3f，DECISIONS「M5 第 5 步」）：`pipeline/components/vid.py`（首帧 / 尾帧、参考图、按 `audio_mode` 的声音、H3 提示词格式、裁头、海报帧和尾帧）；`templates/vid/`（`default.j2`、`h3_i2v.j2`、`h3_r2v.j2`）；`workflows/h3-r2v/` + `comfy/h3-r2v` + 新槽位 `ref_audio`；`materialize` 建视频产物、迁移 `0020` 补旧镜头、示例固定 id `demo-p-vid-*`；`video_product_id`；`takes` 闸门（members `lock=True`）、徽标「生成」；`run_count`（首次 2 条）、估价乘条数；影响范围 `stale_video` / `videos_redo`；`media/audio.py:dialogue_track`。新测试 `test_takes_api.py` 6 个、适配器 1 个、音频 1 个；Web 快照重导（`shots.json`、`config.json`）。全量 pytest 743 个过；前端 typecheck / lint / prettier / Vitest 297 个过；ruff、mypy 干净。
- 第 6 步（11a5d6c，DECISIONS「M5 第 6 步」）：`adapters/minimax_video.py`（H3 V2：生成 / Context-IR / Regenerate-2K 三种异步任务，按有没有声音输入分图生 / 参考生视频，取消时删排队任务）、`adapters/seedance.py`（Seedance 2.5，首帧、按 token 记账）、`adapters/tasks.py`（轮询、下载、探测）；`Usage.resolution`、按模型的 `caps.timeout_s`、按秒计价也能按 token 记账、529 重试；`vid` 的 H3 API 先过 Context-IR（`caps.prompt_ir`）、`tts` 经 API 走参考模式 `fully_copy`；价格改人民币；兼容表 Seedance 变原生 1080p。新测试 `test_video_api_adapters.py` 12 个（respx）、`test_takes_api` 加 1 个；Web `config.json` 快照重导、`Spec.test.tsx` 改一句。前端 Vitest 297 个、lint、typecheck、prettier 过；全量 pytest 756 个过（第一轮漏改 `test_spec_api` 的兼容表一句，改后单跑过）；ruff、mypy 干净。
- 第 7 步（198055c，DECISIONS「M5 第 7 步」）：`vid.final_api`（Regenerate-2K）出终版：本地 take 多存 `raw` 原片和 `params_json.request`，终版原样重发、裁头、`stage=final`、父版本是草稿，非本地 H3 草稿 `draft_not_regenerable`；出终版只出 1 条；本地 take 失败 / 超时用 `run_flow` 在 H3 API 上重建请求重做（Context-IR 花费进版本）。`test_takes_api` 加 4 个（终版、失败兜底、超时兜底、GPU 分组）。全量 pytest 760 个过；ruff、mypy（含 linux）干净。
- 第 7a-1 – 7a-5 步（68e8860、a9fa62f、314b524、f3c2073、3a8a232；DECISIONS「M5 第 7a 步（一）–（四）」）：厂商国内 / 国际站（迁移 `0021`、按站点存密钥）；账号叠加层、拉模型列表勾选、`model_setting`（迁移 `0022`），Kimi 默认 K3.1 Pro；未知价先确认（`unpriced`，迁移 `0023`）；密钥对话框的站点、模型列表、填价、媒体模型 ID；本机 Kimi 国内站测试连接列出 6 个模型。
- 第 8 步（204dd37，DECISIONS「M5 第 8 步」）：`pipeline/generate.py`（自动规则按剧集存 `app_setting`、默认读配置；运行记录从视频产物和任务推出，新 code `take` / `switch` / `final` / `waiting` / `failed`）、`api/routes/generate.py`、`api/routes/metrics.py`（最小 `/metrics/summary`）；`unadopt`（有物化的槽位 409 `unadopt_unsupported`）、`PATCH /versions/{id}` 打分；单镜头上限 `Budget.before_enqueue(shot=…)`、`reason: shot`（`components.yaml` 加 `shot_cap_usd: 2.0`）；`run_count` 改 async 读 `takes_per_shot`。前端只补契约：`JobConfirmSchema` 加 `shot`、确认弹窗文案、运行记录新 code 的中英文。新测试 `test_generate_api.py` 5 个、`confirmJobs.test.tsx` 1 个；相关 pytest 84 个、Vitest 301 个、lint、typecheck、prettier、ruff、mypy（含 linux）过；全量交给 CI。
- 第 9a 步（b10a029，DECISIONS「M5 第 9a 步」；Kelvin 定示例分镜改成已确认）：`studio/demo.py` 的 `CONFIRMED_GATES` 加分镜，确认前 `_confirm_shots`（1-04–1-07 锁关键帧选中的那张、1-08 / 1-09 只写决定），`_seed_takes` 照原型种 1-01–1-03（本地草稿 + Regenerate-2K 终版，已采纳）、1-04（两条草稿、超时兜底 H3 API、换 Seedance，待挑）；`vid.clip_files` 抽成模块函数；`lock_pick(pick_id, at)`。前端快照仍从分镜确认前导出（`test_web_fixtures` 的 `client` 去掉分镜闸门，快照没变）；Playwright `m4` 开头先取消确认 1-04–1-09。`test_gates_impact_api` 的示例测试加 take 断言。相关 pytest（闸门、快照、种子、takes、generate 共 45 个）、Vitest、Playwright e2e 过；ruff、mypy 干净。 第 9b 步（447b011，DECISIONS「M5 第 9b 步」）：删 MSW 的生成页规则 / 运行记录 / 取消采纳 / 打分、示例 take（`takes.ts` → `finishing.ts`）、镜头 take 叠加、生成徽标、`takes` 闸门、影响范围视频叠加（`handlers/impact.ts` 删）；`/metrics/summary` 改成「示例 + 后端已花」叠加到 M8；后期示例时间线读后端 take（`demoVideos`）。测试假后端 `test/fakes/generate.ts` + 快照 `generate.json`（`test_web_fixtures` 新测试，`_stable_takes` 抹掉平台差异）；`shots` / 影响范围假后端直接回答。`?shot=`、`item` 用镜头 id；候选卡封面帧、「未检查」；运行记录并列时间倒序。种子 1-04 草稿改走 `comfy/h3-r2v`。`Generate.test.tsx` 重写（13 个）；Vitest 302 个、lint、typecheck、prettier；pytest（快照、闸门、种子 30 个）；ruff、mypy；Playwright e2e 37 个过。
- 第 9c 步（899e910，DECISIONS「M5 第 9c 步」）：候选卡固定宽度（`TAKE_CARD_WIDTH`）、竖屏画面框 290 px；播放 / 空格在 `MediaLightbox`（新 `video`）里放后端的片子；本地 H3 草稿「用 API 出终版 · 约 $x」，价格来自新字段 `EstimateOut.final_usd`（`RunService._final_api_cost`，快照重导多了 `final_usd`）；队列卡按模型分组、兜底到 API、等确认。`Generate.test.tsx` 16 个（新 3 个）、`test_takes_api` 加一句；Vitest 305 个、lint、typecheck、prettier；pytest（takes、runs、products 28 个）；ruff、mypy；Playwright e2e 37 个过；截图（亮 / 暗 + 2000 px 和大图在 scratchpad）。
- 第 14a 步（2f90ca6；Kelvin 定提前，计划里插在第 10 步前）：`scripts/smoke/local_video.py`（临时目录、`DRAMA_REAL_LOCAL=1`，`--only ab --home` 复用数据目录做同种子 A/B）；本机 ComfyUI 真跑 1-01、1-04 都本地出片、有声音、768x1344、显存峰值 31.6 GB，5 秒片约 57 秒；记录 `reports/m5-local-smoke.txt`。
- 本机对比（2026-10-27，Kelvin 要求，没调 API）：`reports/m5-local-smoke/run3-workflows/`（关 Turbo 换三个社区工作流：官方 20 步、SEED HUNTER、SEEDVR2 超分；SEED HUNTER Kelvin 说效果不好，SeedVR2 最清楚）、`run4-1-04-cut/`（1-04 第 2 秒切走的原因：提示词没照官方写法，切到的就是参考图本身）。片子 `*.mp4` 被 `.gitignore` 挡着、拼图 `*.png` 没提交，见「等 Kelvin 的事」。临时对比脚本在 scratchpad（`wf_compare.py`），不进仓库。
- 第 14b 步（e448225；Kelvin 2026-10-27 定插一步、务必符合官方模板，DECISIONS「M5 第 14b 步」）：`prompts/h3_format.py`（按 MiniMax 官方 h3-prompt-writing 校验：段落和顺序、I2VA 第一行、标签、英文、台词原文、单镜头、字数；`mock_prompt`）；`templates/vid/h3_rewrite_system.j2`（规则 + 1-04 范例）；新路由组件 `vprompt`（视频提示词改写，默认 DeepSeek V4.1 Flash，可选本地 Qwen）；本地 H3 的 take 先改写（缓存，同一次的几条候选只改一次），不合格带着问题重问一次，还不合格 `prompt_not_conformant` 不出片；`h3_r2v.j2` 参考图改成 `<Subject N>`；参考图带 `desc`、首帧带 `first_desc`；估价含改写（本地 H3 一条约 $0.008）。新测试 `test_h3_format.py` 16 个、`test_takes_api` 加 2 个改 1 个；`Models.test.tsx` 组件 23 行；快照 `config.json`、`generate.json` 重导。相关 pytest（h3_format、takes、config、快照 70 个）、Vitest 305 个、lint、typecheck、prettier、ruff、mypy 过；全量交给 CI。 对比图压缩进 git、原图进 `originals/`（001a271）；删潜空间放大节点包、7 个工作流体检正常（6f52677，`reports/m5-local-smoke/comfyui-cleanup.md`）。
- 第 14c 步（62dc9f4；Kelvin 定用 DeepSeek）：`registry.real_models()`（`DRAMA_REAL_MODELS` + `DRAMA_LIVE=1`：只放开点名的模型，其余仍 Mock）；`local_video.py --only rewrite`（真 DeepSeek 改写 + 本机 H3，关兜底、每条前 `POST /free`、失败本地重试一次、清掉旧数据目录遗留的任务）；1-01、1-04 各 2 个种子都不切走、改写一次就合格，DeepSeek 共 $0.0038（`reports/m5-local-smoke/run5-rewrite/`）。`test_providers_api` 加 1 个；ruff、mypy 过。
- 第 14d 步（bdd8fac；Kelvin 定 M5 做后端 + 工作流、按钮 M6，DECISIONS「M5 第 14d 步」）：`workflows/seedvr2-up`、`workflows/flashvsr-up`；`providers.yaml` 指过去；清单加 `w_flashvsr`（锁版本，6.7 GB，本机已下）；`components.yaml` 的 `up` 注释；本机体检 + 试跑都过；预计耗时 SeedVR2 40 s / FlashVSR 32 s 每秒（实测）。清单数 35 → 36：`test_manifest`、`test_setup_api`、`test_capabilities`、`Setup.test.tsx` 跟着改，快照 `setup.json` 重导；`test_comfyui_adapter` 加 2 个。相关 pytest、Vitest 305 个、lint、prettier、ruff、mypy 过。

## 下一步

- **第 14e 步 本地 H3 草稿改成 20 步、不开 Turbo**（Kelvin 2026-10-27 定，计划 14e，DECISIONS 同日「本地 H3 草稿用 20 步」）：从 `workflows/h3-i2v/workflow.api.json`、`h3-r2v` 开始，照第三轮的 `official20` 改（删 `LoraLoaderModelOnly`，把引用它的 `model` 接回 `UNETLoader`；`BasicScheduler.steps` 改 20）；做完再做第 10 步。
- **第 10 步 工作流库接后端（前端）+ ModelPicker 档位**（计划第 10 条）：删 `mocks/handlers/workflows.ts`（和 `fixtures/demo/workflows.ts`、`db.ts` 的 `workflows` / `comfyWorkflowFiles`），挪成 `test/fakes/workflows.ts`（数据从后端导出，照 `generate.json` 的做法加进 `test_web_fixtures.py`）；试跑进度改走任务事件（`job.updated`，后端第 3 步的 `workflow_trial`）；ModelPicker 显示工作流档位，未验证的单独一组、只能手动选。从 `web/src/pages/models/WorkflowLibrary.tsx` 和 `mocks/handlers/workflows.ts` 开始；e2e `smoke.spec.ts` 的「workflow library」那条要跟着改。
- **`start.ps1` / `start.sh` 默认真实检测**（`-RealSetup` 默认开，Kelvin 2026-10-21 定；`-RealSetup:$false` / `--no-real-setup` 换回示例机器）。直接 `drama-studio dev` 和测试仍是 Mock 即示例机器。
- **约定**：生成页测试先 `confirmFakeStoryboard()`（其余页面测试的分镜是进行中）；改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（M2 计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。heredoc 里 Python 字符串的 `\n` 会被写成真换行：要写进代码的 `\n` 用 Edit 工具。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。`assets-views` 和 `assets` 是同一张（默认选中林晚），截完复制一份。

## 没提交的改动

- 无。Kelvin 装的技能目录（`.agents/` 已进 `.gitignore`，`.claude/skills/` 等其余的他自己处理），别提交。

## 踩过的坑 / 临时绕过

- **Mock 下 H3 API 的视频按 0 元算**（第 8 步发现）：`MockAdapter.estimate/run` 拿 `params.resolution`（API 跑时是 `delivery`，比如 `1080p`）去查 `price_by_res`（只有 `768p` / `2k`），查不到 → 0；真实适配器按宽高选 768P / 2K，没问题。Mock 里只有 Context-IR 记钱。第 13 步 Mock 端到端（表头花费要跟着变）时修，修了要重导快照的估价。
- **Kelvin 的 ComfyUI 是 Comfy Desktop**（0.41.2，127.0.0.1:8188，源码在 `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`，不在 `D:\ComfyUI`），H3 节点是自带的、权重和两个 Turbo LoRA 已经在。核对节点用只读的 `GET /object_info/<类名>`、`/models/<文件夹>`；**别往它 `/prompt` 发东西**（会真跑）。**测试里的 `ComfyUIAdapter` 一定传 `websocket=None` 或假的**，默认的会连真 8188。
- **CI**：`/continue` 时先 `gh run list -R kelvin78901/AIVideoGenerationAgent --branch m5-video` 看一眼。连着推送会取消上一轮没跑完的 CI，要等结果就别急着推。
- **偶发失败的测试**：Playwright `smoke.spec.ts`「a locked spec changes aspect…」2026-10-26 修了（开头用接口把画幅改回 9:16，弹窗关闭等 20 秒；CI 上连着两次挂在它）；pytest `test_web_script_fixture_is_current` 全量里偶尔两个产物 id 顺序对调（单独跑过），再碰到就查导出时的排序键。
- **临时脚本里 `create_app()` 一定先设 `DRAMA_HOME` 到临时目录**（`core/paths.py`；不是 `DRAMA_STUDIO_HOME`），否则开的是真实的 `~/.drama-studio`：第 3 步就这样把示例关键帧种进了 Kelvin 的库（Mock，没花钱，和重启后端的效果一样）。
- **测试别在「档案写完」后立刻断言任务状态**：任务结束比档案写入晚一点，CI 慢机器上会读到 running（`test_rescan_replaces_a_running_scan`，2026-10-21 修：等任务都结束再比）。
- **同一次物化建的行 `created_at` 可能相同**（Windows 时钟粗，Linux 细，结果相反）：别拿它排序或当次序；出场矩阵改成按分析里的顺序（`seed_json.order`）再按 id。
- 有 `upstream` remote（`binwu1/drama-series-agent`）；Kelvin 已把 `gh` 默认仓库设成 `kelvin78901/AIVideoGenerationAgent`，保险起见 `gh pr` 仍带 `-R`。
- 演示里逐步推进的流程（检测、安装、同步）用 `mocks/events.ts:repeatDemo`；测试把对应的 `demoTiming` 设成 0，所有步骤在一个任务里跑完，不要靠放宽等待时间。
- Kelvin 本机常开着 `start.ps1`（5173 前端 + 8000 后端，Mock 模式），Vite 会热更新，可以直接拿来做浏览器核对；不要往里发真实（非 Mock）调用。**后端不会自动重载**：改了后端接口要提醒 Kelvin 重启后端，否则热更新后的前端读旧后端，报「接口返回的数据和约定不符」。
- 示例里的运行延迟在 `mocks/events.ts:demoTiming.runMs`，测试里改成 20 ms（见 `components/products.test.tsx`）；测试要挂 `useEventStream()`（`FakeEventSource`）才收得到 `version.created`。
- **Chromium 新版 `scrollIntoView()` 返回 Promise**：`useEffect(() => el.scrollIntoView())` 这种箭头表达式会把 Promise 当清理函数，整页白屏（jsdom 里测不出来）。effect 一律写花括号；滚动日志用容器的 `scrollTop`。
- 页面里有演示事件驱动的长流程时，用临时的 `e2e/tmp-*-shots.spec.ts`（`--project=shots` 能匹配）在真浏览器里走一遍、截图到 scratchpad，跑完删掉。
- `test_restart_resume` 偶发失败（2026-10-18、10-20）的原因：Windows 上 `.venv/Scripts/python.exe` 是启动器，真正的解释器是它的子进程，`kill()` 后还要零点几秒才退出，期间读数据库报 disk I/O error。第 13 步起 `tests/e2e/conftest.py:Backend.kill()` 等端口关掉再返回（连跑 5 次都过）。
- **测试节奏（Kelvin 2026-10-26 定）**：每个小步只跑改动涉及的 pytest（对应的单元 / API 测试）+ ruff、mypy，然后提交推送；**全量交给 CI**（每次 push 都跑）。本机全量（约 17 分钟，要 `run_in_background`）只在开 PR 前或复现 CI 失败时跑。**跑的时候别改已有的源文件**：模型和迁移在收集时已加载、e2e 子进程启动时读当前文件，半路改会出假失败（M4 第 1 步踩过）；只加新文件没事。
- **单元测试绝不能触网**：`test_steps.py` 的 `_install` 默认离线 transport；别给 RealRunner 的测试传 `transport=None`（清单有真实下载地址，曾真的下了 30 GB 到 pytest 临时目录）。
- **示例机器切换**：点已选中的那台不会触发切换；e2e 里切 Mac 再切回 PC 要等前一次 `aria-checked` 变了再点。
- MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。
- **能力过滤在 Mock 下也生效**：扫描示例机器后路由会变（PC 示例装好之前视频、关键帧、超分走 API；没扫描过不过滤）。
- **改带平台分支的代码后加跑 `python -m mypy --platform linux`**：CI 是 Linux，Windows 上的 mypy 看不出只在 Windows 有的名字。
- **本机应用控制策略拦 `.venv/Scripts` 里 uv 生成的入口 exe**（`pytest.exe`、`mypy.exe`、`drama-studio.exe` 报 os error 4551，`ruff` 不受影响）：一律 `uv run --no-sync python -m pytest` / `python -m mypy`；后端用 `python -m drama_series_agent.studio_cli dev`（`start.ps1`、Playwright 已改）。再出现就是 Windows 智能应用控制（Kelvin 2026-10-20 已关掉）。
- **本机 PowerShell 执行策略禁止 `-File` 跑脚本**：钩子、状态栏、`start.ps1` 都要 `powershell -NoProfile -ExecutionPolicy Bypass -File …`。 `.ps1` 必须存成 UTF-8 带 BOM（Windows PowerShell 5.1），否则中文乱码。
- 写接口（非 GET）要带 `X-Drama-Studio: 1`，Host 必须是 127.0.0.1 / localhost；`TestClient` 要用 `base_url="http://127.0.0.1"`。
- **Kelvin 开着 `start.ps1` 时 `uv run` 会失败**（同步要替换正被占用的 `.venv/Scripts/drama-studio.exe`）：一律 `uv run --no-sync …`；**加依赖（jinja2、python-docx）时**要先请 Kelvin 停掉后端再 `uv sync`。
- Windows 上 `python` 不在 PATH（会跳到应用商店），一律 `uv run python`。pnpm：`corepack enable --install-directory ~/bin pnpm`；命令前加 `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` 避免首次下载提示。
- YAML 1.1 会把 `on:` / `mode: off` 解析成布尔值：`core/config.py` 用只认 true/false 的加载器。
- SQLite 读回时间会丢时区，用 `models_db.UtcDateTime`。
- **上游 `.gitignore` 有 `templates/`、`config.json`**，会挡住任何叫这个名字的目录 / 文件；`prompts/templates/`、`web/src/test/data/config.json` 已用 `!` 放行。新加文件后看 `git status --ignored`；**每次 push 后看一眼 `gh run list`**（这次红了 20 多个提交没发现）。
- **页面测试里上传文件**：`test/setup.ts` 已把 `FormData` / `File` 换成 Node 的（jsdom 的发出去是 `"[object FormData]"`），假后端里 `await request.formData()` 可以直接用。
- **Radix 下拉菜单里打开对话框要 `modal={false}`**，否则对话框关掉后 `body` 留着 `pointer-events: none`（jsdom 里表现为后面的测试点不动）。
- **ESLint `no-irregular-whitespace`**：全角空格（U+3000）在正则、注释里会报错（字符串里不报）——正则写 `\s`，注释别用；**`react-hooks/set-state-in-effect`**：不要在 effect 里同步 URL 参数到 state，在渲染时推出来（见 `Script.tsx` 的 `picked`）。
- **ComfyUI 偶发 `hostbuf_file_reader_read failed`**（KSampler，换模型时从文件往显卡读权重失败，当时后台在跑 pytest、内存紧）：我们按 `comfy_failed` 兜底，重跑就好。本机冒烟别和全量 pytest 同时跑。
- **Vitest 里 `vi.mock("sonner")` 对 `api/events.ts` 不生效**（setup 已经先加载了真的 sonner）：看 toast 用 `vi.spyOn(toast, "error")`。
- **改代码前先看 ruff 有没有已经改过行**：`ruff format` 会把长行拆开，之后用 sed 按原行号替换会留下碎片（第 4 步踩过）。

## 等 Kelvin 的事

- 无。已定（2026-10-27）：本地 H3 用 20 步不开 Turbo；原生配音的声音合格。


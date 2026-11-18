# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M6 质检与精修**，计划 [`plans/M6.md`](plans/M6.md)（Kelvin 2026-11-14 批准；DECISIONS「M6 计划」）。M5.5 已合并（PR #8，d453a70），各步记录在 [`reports/M5.5.md`](reports/M5.5.md)。
- 分支：`m6-qa`（从 main d453a70 开出）。
- Kelvin 定：局部修复做口型 + 视频局部修复两种；只差口型 → 自动口型修复；API take 不过也自动重跑（受单镜上限管）；精修采纳中的 take、新版通过就自动采纳。

## 已完成的小步

- **0**（d7b43a0）开分支 `m6-qa`、计划存 `plans/M6.md`、ROADMAP 链接计划、DECISIONS「M6 计划」。只改文档。
- **1**（efe50c5）线框草图 `prototype/m6/`：`takes.html`（G1–G3）、`storyboard.html`（S1 连续性）。只改文档。
- **2**（2feaccf）连续性账本：`shots/ledger.py`（现算、不建表，Kelvin 2026-11-15 同意）、`ShotOut.ledger`、`shots/service.py:ledger_inputs`；关键帧和视频编译加「接上一镜」并依赖来源镜头；web 测试数据 `shots.json` / `generate.json` 重新生成（只多了 `ledger`）。测试：`test_ledger.py` 10 passed、`test_shots_api.py` 14 passed、`test_keyframes_api.py` + `test_takes_api.py` 42 passed、`test_web_fixtures.py -k "shots or generate"` 2 passed；ruff、mypy 过。
- **3**（a5cab1c）质检框架（Mock）：`pipeline/qa.py`（`QaService`：take 出完 `products.on_created` 排 `qa.take` 任务（cpu）；六项先量后判，`judge` / `rejudge`；写 `qa_json` / `qa_pass` 和出片调用 `params.call_id` 的 `qa_scores_json`；`version.qa` 事件；`POST /versions/{id}/qa`）；`takecheck` 路由并进 `qa`（迁移 `0025` 搬覆盖配置），看图加账本三项；生成规则阈值可写 + `qa_on` + `reset_qa`；`providers.yaml` 三个工具 key（没 worker）；前端只加 `speaker`、`version.qa`、标签。测试：`test_qa.py` 5、`test_qa_api.py` 5、`test_generate_api.py`、`test_web_fixtures.py -k "config or generate or shots"`、`test_storyboard_to_takes.py`、`test_takes_api.py` 全过；`pnpm -C web test`、lint、typecheck、format 过；ruff、mypy 过。
- **4**（ffb6d9c）自动重跑和兜底：`pipeline/qa_policy.py`（`decide` 纯函数 + `QaPolicy.after_qa`，质检写完后调；重跑带 `fixes`、`auto_qa_rerun`；用完次数走 `vid` 兜底 `qa_fail`，`notify: ask` 等确认；兜底也没过就停）；`RunService.start` 加 `origin` / `fallback_reason` / `ask`；`vid.run` 去掉运行内看图和重画（只拼图）；运行记录 `take_fail_rerun/fallback/lip/stop` + 前端文案。测试：`test_qa_policy.py` 7、`test_qa_api.py` 8、`test_takes_api.py` 23、`test_generate_api.py`、`test_storyboard_to_takes.py`、`test_web_fixtures.py` 全过；`pnpm -C web test` 340、lint、typecheck、format 过；ruff、mypy（含 linux）过。
- **4 补**（dff14e8）CI 修：`JobQueue.stop` 先给运行中的任务 1 秒（取消等数据库的任务会留下写锁，DECISIONS）；`test_qa_api` 阈值那条先采纳（免得触发自动重跑）。5a 调研 `reports/m6-qa-tools-research.md` 进库。测试：`test_jobs.py` + `test_qa_api.py` 22、`test_takes_api.py` + e2e restart 25 passed。
- **4 补 2**（e7fefbb）Playwright `m5.spec.ts` 卡片上找「契约检查」改成找「画面检查」（第 4 步起运行内看图并进质检）。测试：`playwright test e2e/m5.spec.ts -g "takes for a shot"` 4 passed。
- **5a 代码**（5b23437）`runtimes/qa`（锁 28 个包，不含 torch：SyncNet 第 5b 步加）、`workers/worker_qa.py`（face / speaker / asr，`args.tool` 一个模型一个进程；编排只用标准库）、`worker_video.py`（抽帧、解码音频）、`worker_rapidocr` 读视频（`every_s`）；providers 三个 key 接 worker、清单 `rt_qa` / `w_qa`（3.4 GB）；`scripts/smoke/local_qa.py`（数据目录副本上直接调 `Measure`，不触发自动重跑）。DECISIONS「M6 第 5a 步」。测试：`test_worker_qa.py` 11、detectors / manifest / capabilities / setup-install / qa / local_python 109、web fixture setup / config、Vitest Setup + AppShell 48、Playwright smoke「first run」过；ruff、mypy（含 linux）过。
- **5a 本机**（407f710）Kelvin 同意后经 `/setup/install` 装了 `rt_qa`、`w_qa`（重新扫描两项都 ok）。`av` 降到 18.0.0（19 和 faster-whisper 1.2.1 不兼容，DECISIONS）；glintr100 归一化 127.5 / 127.5 核对过。第十九轮 55 条 take 全跑通（`reports/m6-qa-local/run19.{json,txt}`），CPU 耗时中位数：人脸 1.0 s（30 条）、台词 4.0 s（9 条）、说话人 0.1 s（9 条）、OCR 2.8 s（25 条）。修了 CI：`test_setup_api.py` 的条目数（5a 漏改）。测试：`test_setup_api.py` 11、`test_worker_qa.py` 11 passed。
- **5b**（f9c0c96；CI 修 2474c68：`test_detectors.py` 两行超长）qa 环境加 CPU torch 2.14.1（锁 36 个包，没有 nvidia）；`workers/syncnet.py`（网络、MFCC 照抄 MIT 原版）、`worker_qa` 的 `sync`（YuNet 跟踪 + 裁剪，conf 只算有声窗口）、`worker_video.grid`（25 fps）；`local/syncnet` 接 worker、`w_qa` 加 SyncNet 权重（HF LatentSync-1.6，和 VGG 官网同一个文件）、`rt_qa` 检测改看 torch、名字加「口型」。本机：经 `/setup/install` 补装 `w_qa`；官方示例 conf 10.05 / offset 3（官方 10.02 / 3）；run19 重跑五项全通，口型 3.6 s / 条（5 条有分，1.4–2.6）。冒烟脚本默认五项、JSON 写 LF。DECISIONS「M6 第 5b 步」。测试：`test_worker_qa.py` 15、detectors / manifest / capabilities / steps / local_python / qa / setup API / setup-install 143、web fixture setup 过；ruff 过。
- **5c**（本提交）本机校准，报告 `reports/m6-qa-calibration.md`、DECISIONS「M6 第 5c 步」。默认阈值人脸 0.18、口型 1.0（改用 `in_sync`：±2 帧内对得上的程度；`conf` 在音频错位时反而更高）、字错率 0.2、说话人 0.65。人脸只数能比的脸（嵌入长度 ≥ 16、不是侧脸，≥ 3 帧，取中位数）；Whisper 带角色名提示、丢 `no_speech_prob` > 0.5 的段；原生同步、没对白的镜头也识别（听到人声就不过：1-06 T1–T3 念了内心独白）。take 的 OCR 只比在读这段字的帧（≥ 2 个字相同，不算标点；读不出 → 不适用）。重跑 `reports/m6-qa-local/run19-cal.*`。测试：`test_worker_qa.py` 16、`test_qa.py` + `test_qa_policy.py` 12、`test_qa_api.py` + `test_generate_api.py` 14、web fixture generate、Vitest `Generate.test.tsx` 19 过；ruff、mypy（含 linux）过。

## 下一步

- **第 6 步 2K 精修接 take**（`plans/M6.md`）：`POST /versions/{id}/upscale` 分 take / 图片，`up` 组件出版本、自动采纳规则（E 开头那条）、估价和耗时；本机一条 take SeedVR2 放大核对（尺寸、帧率、音轨原样）。从 `pipeline/components/` 里的 `iup`（图片放大）和 MSW `handlers/generate.ts` 的 take upscale 开始看。
- **5c 留给 Kelvin 看片**：1-04 T9 口型分 0.53 不过（SyncNet 量到声音比嘴早约 0.4 秒），1-06 T1–T3 念了内心独白（字错率不过）。
- **M6 草图 Kelvin 2026-11-15 同意**（`prototype/m6/`，前端第 9 步照它做；S1 只列这个镜头拍到的人，见 DECISIONS「M6 第 2 步」）。M5.5 草图 Kelvin 2026-11-15 也同意，ROADMAP 已勾。
- **踩坑**：Claude Code 在会话空闲时会因内存不足回收后台任务（H3 + TTS 时内存只剩约 8 GB）：长任务一个镜头一个镜头在前台跑（`--from X --to X`，每条 ≤ 10 分钟）；超过 10 分钟的只能后台，被回收后 ComfyUI 里的任务还会跑完，可以从 `/history` 取回结果。被回收的任务下次启动应用会被「恢复」，脚本退出时会取消它。
- **约定**：生成页测试先 `confirmFakeStoryboard()`（其余页面测试的分镜是进行中）；改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（M2 计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。heredoc 里 Python 字符串的 `\n` 会被写成真换行：要写进代码的 `\n` 用 Edit 工具。正则里的 `\b` 同理会变成退格符（\x08）：带反斜杠的改动一律用 Write 写脚本文件或 Edit 工具。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。`assets-views` 和 `assets` 是同一张（默认选中林晚），截完复制一份。

## 没提交的改动

- 无。Kelvin 装的技能目录（`.agents/` 已进 `.gitignore`，`.claude/skills/` 等其余的他自己处理），别提交。

## 踩过的坑 / 临时绕过

- **测试之间借 helper 写 `from test_shot_ops import …`**（tests 不是包，pytest 把测试目录放进 sys.path）；`from tests.unit.… import` 本机能跑、CI 收集时报 `No module named 'tests'`（b1bc8f4 那两轮 CI 红在这）。
- **Kelvin 的 ComfyUI 是 Comfy Desktop**（0.41.2，127.0.0.1:8188，源码在 `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`，不在 `D:\ComfyUI`），H3 节点是自带的、权重和两个 Turbo LoRA 已经在。核对节点用只读的 `GET /object_info/<类名>`、`/models/<文件夹>`；**别往它 `/prompt` 发东西**（会真跑）。**测试里的 `ComfyUIAdapter` 一定传 `websocket=None` 或假的**，默认的会连真 8188。
- **CI**：`/continue` 时先 `gh run list -R kelvin78901/AIVideoGenerationAgent --branch m6-qa` 看一眼。清单加条目时条目数散在 detectors / manifest / capabilities / setup-install / setup API 测试、Setup / AppShell Vitest、smoke e2e 里，一起改。连着推送会取消上一轮没跑完的 CI。第 11 步起 Playwright smoke 卡住（后期页、看板加载、检测）：主因是第 12a 步起估价嵌套开会话、连接池耗尽（DECISIONS「估价不再嵌套开会话」），另有 SSE 断开时连接带锁留下（「数据库会话不让 Starlette 中途取消」）。**持有会话时别调用自己开会话的函数**。修完 379e610 那轮 CI 全绿；再红先看后端日志里的「QueuePool limit」「Exception terminating connection」。复现 CI 用 Docker（`mcr.microsoft.com/playwright:v1.63.0-noble`）会被内存不够停掉，别在本机跑整套。
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
- **示例机器切换**：点已选中的那台不会触发切换；e2e 里切 Mac 再切回 PC 要等前一次 `aria-checked` 变了再点。 MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。
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

- 已定（2026-11-15）：SyncNet 权重许可不明确，照用、记 DECISIONS，商用发行前再换。
- 以后：火山方舟开通 Seedance 2.5（要交保证金，Kelvin 先不管）后补跑 `live_video.py --only seedance`。 可选：想在本机 ComfyUI 里用 DramaStudio 节点，在 Setup 页勾「DramaStudio 节点包」安装（先存快照，没替你装），再重启 ComfyUI。已定：`w_h3` 的两个 Turbo LoRA 留着，以后可能做「快速草稿」档（2026-10-28）；本地 H3 20 步、原生配音合格（2026-10-27）。


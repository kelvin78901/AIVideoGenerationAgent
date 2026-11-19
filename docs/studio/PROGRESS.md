# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M6 质检与精修**，计划 [`plans/M6.md`](plans/M6.md)（Kelvin 2026-11-14 批准；DECISIONS「M6 计划」）。M5.5 已合并（PR #8，d453a70），各步记录在 [`reports/M5.5.md`](reports/M5.5.md)。
- 分支：`m6-qa`（从 main d453a70 开出）。
- Kelvin 定：局部修复做口型 + 视频局部修复两种；只差口型 → 自动口型修复；API take 不过也自动重跑（受单镜上限管）；精修采纳中的 take、新版通过就自动采纳。

## 已完成的小步

- **0–7a**（d7b43a0 … fcb0e62）分支和计划、草图、连续性账本、质检框架、自动重跑和兜底、本地质检工具（人脸 / 台词 / 说话人 / SyncNet）及其 CI 修、本机校准、2K 精修接 take、口型修复后端：各步记录挪到 [`reports/M6.md`](reports/M6.md)。
- **7b 代码**（819bed9）本地 LatentSync 1.6：`runtimes/latentsync`（锁 96 个包，torch 2.11 cu130、numpy 1.26.4）、清单 `rt_latentsync`（源码 a229c39 拉到 `{envs}/latentsync-src` + uv 环境）/ `w_latentsync`（5.5 GB，都可选）、`workers/worker_latentsync.py`（模型常驻、请求在临时目录跑、自带 ffmpeg 放 PATH 最前、出片转回镜头 fps）、`workers/latentsync_faces.py`（不装 insightface：onnxruntime CPU 跑 buffalo_l 两个 onnx 顶替 `FaceAnalysis`）；`local/latentsync` 接 worker、`needs`、估时 caps；`lip` 请求多带路径和 seed。Kelvin 2026-11-18 定 buffalo_l（非商用许可）照用、商用前再换。DECISIONS「M6 第 7b 步」。测试：detectors / manifest / setup API / setup install / local_python / capabilities / config / providers / steps / take lipsync 等过；Vitest Setup + AppShell 61、lint、typecheck、format 过；ruff、mypy（含 linux）过。
- **7b 本机**（163c483）经 `/setup/install` 装了 `rt_latentsync`、`w_latentsync`（重新扫描都 ok）。`scripts/smoke/local_lipsync.py`：1-04 T9 修前口型 0.53 不过 → 修后 2.60、错位 0，质检全过、自动采纳，87 秒，显存多占约 17 GB；1:1 对比脸和画面不变、嘴型跟配音（`reports/m6-lipsync-local/`）。修了 worker：24→25→24 fps 片尾丢 2 帧 → 补齐到 take 的帧数；估时改 30 秒 + 16 秒 / 秒。DECISIONS「M6 第 7b 步」补本机核对。测试：`test_local_python.py` 7、`test_take_lipsync_api.py` 5、web fixtures config 过；ruff、mypy 过。
- **8a**（6ccfaa7）视频局部修复本机验证：Kelvin 同意后按官方模板下了 Wan VACE 14B 一套（约 42 GB，sha256 核对，放 `ComfyUI-Shared/models`）。`workflows/vace-inpaint`（静态遮罩复制到每帧、遮罩里填 50% 灰、裁回原帧数、羽化贴回）；`scripts/smoke/local_vace.py` 直接调 ComfyUI。1-04 T9 去掉红伞：CausVid 4 步 215 秒、显存峰值约 26 GB，干净、无接缝、帧间连贯；换成黑伞不可靠（8 步一样；不加 LoRA 12 步 18 分钟才画出伞，也不干净）；静态遮罩配移动镜头会重画移进来的东西。**Kelvin 定：只做「去掉 / 修瑕疵」，CausVid（CC BY-NC-SA）照用、商用前再换。** DECISIONS「M6 第 8a 步」，报告 `reports/m6-vace-local/`。测试：`test_workflows_api.py`、`test_comfyui_adapter.py`、`test_workflow_branches.py` 49 过；ruff、mypy（脚本）过。
- **8b**（17577e6）视频局部修复后端：组件 `vinpaint`（`UpComponent` 子类，origin `inpaint`，finish kind `inpaint`，自动采纳同 2K）；`POST /versions/{id}/inpaint` 遇到 take 走它（遮罩 `mask_for` 到 take 尺寸，提示词原样、可空）；模型 `comfy/vace-inpaint`（只有本地，跑不了 409 `inpaint_unavailable` + 原因）；工作流槽位 `frames` / `length`（`comfyui.py:vace_length`）；声音从原 take 复制回去；清单 `w_vace`（可选 42 GB）；估价 `finishing.vinpaint`。DECISIONS「M6 第 8b 步」。测试：`test_take_inpaint_api.py` 3、`test_comfyui_adapter.py` 39、setup / manifest / detectors / install 89、capabilities / compat / config / providers / workflows / inpaint / take upscale / lipsync 69、web fixtures 12 过；Vitest Setup + AppShell 35、Models + Sync 16、Generate 19、i18n、typecheck、lint、format 过；ruff、mypy（含 linux）过。
- **9a**（0f4e671）候选卡：质检块接真实数据（`off` 写「已关」不算没过、画面检查可展开看各项和拼图、`qa.policy` 写自动做了什么）、「重新质检」（`POST /versions/{id}/qa`）、角标「未过 n 项 / 只差口型」；「局部修复 ▾」菜单：口型修复本地 / API 两行（估价 `finishing.lip.alt`，接口收 `where`）、涂一块区域重画（`InpaintDialog` 的 `take` 模式，首帧 + 拖动换帧，发 `/inpaint`）；跑不了 / 没人说话灰掉写原因；2K 精修读 `finishing.up`；`takeNote` 认 2K / 口型 / 局部修复版本（「口型修复自 T2」）。删了 `toast.fix`、`wall.checkLater`。DECISIONS「M6 第 9a 步」。测试：`test_take_lipsync_api.py` 6、take upscale / inpaint 8、web fixtures 12 过；Vitest Generate 23 + pictures + Assets 共 59、i18n、typecheck、lint、format 过；ruff、mypy（含 linux）过。
- **9b**（63e00b3）自动规则的质检阈值表（草图 G3）：每项阈值可改（字错率按 %、超出范围弹回）、开关（`qa_on`）、「恢复默认」（`reset_qa`）；「只有口型没过：自动口型修复」一行；改了就刷新产物（后端 `rejudge` 已有）。前端 schema 加 `speaker_sim`、`qa_on`、补丁的 `thresholds` / `qa_on` / `reset_qa`；面板 basis 改 30rem（窄屏排到运行记录上面）。测试：Vitest Generate 24、i18n、typecheck、lint、format 过。
- **9c**（3cf2da1）分镜页镜头详情「连续性」只读一节（`pages/storyboard/LedgerSection.tsx`，草图 S1：角色站位 / 朝向 / 手里 / 服装、道具状态和来源、时间和屏幕上的钟；`*_from` 的镜头 id 换成镜头号；「去改」滚到站位图 / 契约，服装跳素材页 `?asset=`）；素材页克隆模式运行条改文案；删 MSW `fixtures/demo/finishing.ts` 和 `what.up/lip/qa`。DECISIONS「M6 第 9c 步」。测试：Vitest Storyboard 35、Assets 27、Generate 24、products / Post / Sync / storyboard 共 128、i18n、typecheck、lint、format 过。**第 9 步做完。**
- **8a 重跑**（9862ee2）Kelvin 看对比图发现 8a 的遮罩盖住了字条第二行（字被重画乱）、不加 LoRA 那轮伞变黄。两块框只盖伞重跑（`reports/m6-vace-local/1-04-T9-s4-remove-tight-*`）：伞去掉、字条原样、无接缝，伞钩尖留一个红点。`local_vace.py` 加多框和 `--keep`。DECISIONS「M6 第 8a 步更正」。ruff、mypy（脚本）过。
- **9d**（本提交）遮罩盖到字时提醒：`worker_rapidocr` 每帧带回文字框；质检 OCR 存 `regions`（Mock 给 `qa.MOCK_TEXT_BOX`）；`InpaintDialog` take 模式虚线画框，涂抹（加 24 px 扩边羽化）碰到就提醒，可照样提交。本机 RapidOCR 核对过框的格式（N×4×2）。DECISIONS「M6 第 8a 步更正」。测试：`test_worker_qa.py`、`test_qa_api.py`、`test_qa.py` 29；Vitest Generate + pictures 34、i18n、typecheck、lint、format；ruff、mypy（含 linux）过。

## 下一步

- **第 10 步 示例剧坏 take + 端到端**（`plans/M6.md` G 节和第 10 步）：`studio/demo.py` 第 1 集放三条故意的坏 take（`params.mock_qa`：1-04 T1 人脸不对 → 自动重跑；1-07 屏幕时间读错 → 自动重跑；一个对白镜头口型错 → 自动口型修复）；`tests/e2e/test_qa_loop.py`；Playwright `m6`（候选墙看到没过的项、推荐、阈值改了重新判、2K 精修和口型修复各出一条并自动采纳）；截图 `reports/ui/generate-qa.*`（亮、暗、2000 px 宽），顺手重截 generate / storyboard。示例剧的 take 现在不质检（第 3 步定的），先看 `studio/demo.py` 的 `DEMO_TAKES` 和 `pipeline/qa.py` 怎么入队。
- **请 Kelvin 看局部修复重跑**：`docs/studio/reports/m6-vace-local/1-04-T9-s4-remove-tight-{50,90}-crop.jpg`（左原片、右修复，1:1）。口型修复 Kelvin 2026-11-18 看过：还行。
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


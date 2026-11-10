# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M5.5 镜头契约 + 图片来源与编辑**，计划 [`plans/M5.5.md`](plans/M5.5.md)（Kelvin 2026-11-10 批准；DECISIONS「M5.5 计划」）。M5 已合并（PR #7，e6044d4），M5 的各步记录在 [`reports/M5.md`](reports/M5.md)。
- 分支：`m5.5-images`（从 main e6044d4 开出）。
- Kelvin 定：契约和检查先做（第 2–9 步），图片来源与编辑后做（第 10–18 步）；检查**只提示、不挡**；声音克隆最后一步。

## 已完成的小步

- **第 0 步**（3f94986）：开分支、存计划、DECISIONS「M5.5 计划」、ROADMAP M5.5 加契约和检查几项。不改代码，没跑测试。

## 下一步

- **第 1 步草图已提交（e789654），等 Kelvin 看**：`docs/studio/prototype/m5.5/`（README 列了三页、亮 / 暗截图）。看过才做前端（第 8、16 步）；**Kelvin 2026-11-10 定后端第 2–7 步同时做**。草图里要 Kelvin 定的三件事见「等 Kelvin 的事」。
- **第 2 步做完（本提交）**：`shots/contract.py`（build / patch / effective）、迁移 `0024`（`shot.contract_json`、`asset.manual`）、规划模板和 `PlannedShot` 加契约字段、`script_text` 把 OS 写成「内心独白」、`shot:<id>` 切片带契约（老分镜不带、哈希不变）、`ShotOut.contract` / `PATCH {contract}`、前端 zod `ShotContractSchema` 和乐观更新；示例 `plan.json` 9 个镜头补契约（1-08 仍写开两次，留给第 4 步检查报出来）；web 测试数据重导。测试：shot contract / ops 单元、shots / storyboard / keyframes / takes / generate / gates / asset refs API、两个 e2e、unit 全部过（576）；前端 storyboard / generate / api vitest、tsc、eslint、prettier；ruff、mypy（含 linux）干净。SPEC 4.1 加一段。**Kelvin 开着 `start.ps1` 要重启后端**（新迁移；前端要 `contract` 字段，不重启会报数据和约定不符）。
- **CI 修复（ccc5535）**：测试借 helper 改成 `from test_shot_ops import`（见踩坑）。
- **第 3 步做完（本提交）**：关键帧（有契约的分镜）加「开始时 / 道具 / 嘴闭着」段（`kf.contract_blocks`）；`vid.gather` 读 `contracts.effective`：只有 `delivery == dialogue` 的行进 take，`kind` / `beats` / `start` / `end` / `props` 进草稿和改写 JSON（`h3_format.Facts` 加字段）；改写系统提示词按 `beats`；`h3_format.UNDONE` 拒撤销重做。DECISIONS、SPEC 5.1 同日。测试：h3_format、keyframes / takes / generate API、storyboard e2e、unit 全部、web fixtures 重导、前端 storyboard / generate vitest；ruff、mypy（含 linux）干净。**Kelvin 开着 `start.ps1` 要重启后端。**
- **第 3 步做完（1891ab0）**。
- **第 4 步做完（本提交）**：`shots/check.py` 规则（undone / insert_event / replay / inner_mouth / state_jump，读时现算）；路由组件 `plancheck`（`pipeline/components/plancheck.py`，默认 DeepSeek v4.1 Flash，每集一个 `shot_check` 产物，点「检查」才跑，依赖整个分镜规划）；`GET/POST /episodes/{id}/shot-checks`；示例剧规则报 1-08 undone、replay，Mock 模型报 1-03 insert_event；前端 `ProductSlotSchema` 加 `shot_check`、Models 页 26 行；config / script 测试数据重导。DECISIONS、SPEC（组件表、9.1）同日。测试（只跑改动相关的，Kelvin 2026-11-10 再次强调；全量留到合并前）：shot check / contract 单元、shots / config / capabilities API、web fixtures、前端 Models / Script vitest、tsc；ruff、mypy 干净。**Kelvin 开着 `start.ps1` 要重启后端。**
- **第 4 步做完（60e16f9）**。
- **第 5a 步做完（本提交，第 5 步分两个提交）**：道具 `physical`（size / material / wear：设定抽取 details → 素材清单 → `seed_json`，`settings.physical` 优先，`AssetOut.physical`、前端 zod `PhysicalSchema`）；道具图「真实尺寸和材质」段、关键帧「尺寸」段；画面文字 OCR 不一致不再挡锁定；示例设定补四个道具的尺寸。DECISIONS 同日。测试：asset text / assets / keyframes / bible API、asset ops、demo seed、web fixtures 重导、前端 Assets / Novel / Storyboard / Script vitest、tsc；ruff、mypy 干净。
- **下一步：第 5b 步**：带字的道具（素材分析的文字项带 `on: "prop:<id>"` 就并进那个道具：道具 `seed_json.text`，`prompts/templates/assets/default.j2` 和 `assets/ops.py:merge`；道具图画字 `img.py`；道具候选跑 OCR，照 `pipeline/components/text.py` 的写法；`kf._references` 把道具的字当画面文字逐字写）；`ref_scale` 比例参考（道具锁定后出一张和人物同框的，新槽位、`assets/service.py:lock` 里像 `draw_views` 那样排；关键帧取参考紧跟道具图）；示例剧 `txt1` 并进 `note`（`tests/fixtures/demo/assets.json` 的文字项加 `on`、`studio/demo.py` 的 `DEMO_ASSET_IDS`、MSW `web/src/mocks/fixtures/demo/assets.ts`、引用 `txt1` 的测试：`tests/api/test_asset_text_api.py` 改用 `txt2` 或道具）。做完勾第 5 步。
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
- **CI**：`/continue` 时先 `gh run list -R kelvin78901/AIVideoGenerationAgent --branch m5-video` 看一眼。连着推送会取消上一轮没跑完的 CI。第 11 步起 Playwright smoke 卡住（后期页、看板加载、检测）：主因是第 12a 步起估价嵌套开会话、连接池耗尽（DECISIONS「估价不再嵌套开会话」），另有 SSE 断开时连接带锁留下（「数据库会话不让 Starlette 中途取消」）。**持有会话时别调用自己开会话的函数**。修完 379e610 那轮 CI 全绿；再红先看后端日志里的「QueuePool limit」「Exception terminating connection」。复现 CI 用 Docker（`mcr.microsoft.com/playwright:v1.63.0-noble`）会被内存不够停掉，别在本机跑整套。
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

- **M5.5 草图**（`docs/studio/prototype/m5.5/`）：看布局和文案。三件事 Kelvin 2026-11-10 已定（风格板在成片规格页、画面文字 OCR 也只提示、take 卡局部修复按钮留着功能 M6），记在 DECISIONS「M5.5 计划」和计划第 5、12、16 步。

- 以后：火山方舟开通 Seedance 2.5（要交保证金，Kelvin 先不管）后补跑 `live_video.py --only seedance`。 可选：想在本机 ComfyUI 里用 DramaStudio 节点，在 Setup 页勾「DramaStudio 节点包」安装（先存快照，没替你装），再重启 ComfyUI。已定：`w_h3` 的两个 Turbo LoRA 留着，以后可能做「快速草稿」档（2026-10-28）；本地 H3 20 步、原生配音合格（2026-10-27）。


# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M3 素材与配音**，计划 [`plans/M3.md`](plans/M3.md)（2026-10-20 批准；Kelvin 定的七项见 DECISIONS 同日）。
- 分支：`m3-assets-voice`（从合并 PR #4 后的 main 3ffd6a2 开出）。M2 已合并，报告 [`reports/M2.md`](reports/M2.md)。

## 已完成的小步

（细节见 DECISIONS 各步的条目和提交说明；做完 M3 写报告时整理进 `reports/M3.md`。）

- 第 0–2 步：分支、计划、DECISIONS 七项（ff125ed、848eaa8）；框架和媒体基础（58f5260：迁移 `0016`、pick / retired、`RunParams`、`/files/{sha}`、`AudioPlayer`）；素材分析后端（d33cfec：组件 `assets`、物化只增不删、迁移 `0017`、示例 13 条）。
- 第 3–4 步：参考图、补视图、上传、锁定（f0e07e6：组件 `img` / `views`、`asset_unlock`、示例 7 / 13 锁定）；素材页接后端 + 出场矩阵（70a1200，截图 `assets-{draft,views,matrix}`）。
- 第 5 步：画面文字 + OCR（4461791，矩阵排序修在 68c9cdc）：组件 `text` / `ocr`、`ocr_mismatch`。截图 `assets-{text,text-composite,ocr-confirm}`。
- 第 6 步：音色（ea5fd19）：试听 → MiniMax 终版 + 5 个情绪 → 整版锁定、`config/voice.yaml`。截图 `assets-voice-{final,drafts}`。
- 第 7 步：台词配音 + 时长（后端 1d94c66、前端 49215a9，DECISIONS 2026-10-21「第 7 步」）：组件 `dub`、`pipeline/timing.py`、`POST /episodes/{id}/dub`；素材页「台词配音 n / m · 全部配音」、音色详情的台词配音、剧本页播放和真实时长；Playwright 项目 `seeded`。
- 第 8 步：素材闸门、影响范围、级联（后端 bb1b47d、前端 333bdc6，DECISIONS 同日「第 8 步」）：整集素材闸门 409 `assets_not_locked`、「素材」真实计数 7 / 10、级联停止集、影响行按槽位合并、`asset_edit`。 Kelvin 看过（cf66b26）：计数定 7 / 10，候选卡改定宽小卡 + 放大看。
- 第 9 步：Mock 端到端（c6c1761，时序修复 5fc2940，CI 绿）：`tests/e2e/test_script_to_dub.py` 从导入小说走到每句配音、场时长 = 音频之和。
- 第 10 步：图像 API 适配器（489516e，DECISIONS「第 10 步」）：`gemini-3-pro-image`、`gpt-image-2`、Seedream 5.0 flash；`adapters/{http,images,google,openai_images,volcengine}.py`、`modelhub/media_adapters.py`；按 token 记账；测试连接带 `media`。
- 第 11 步：MiniMax 适配器（0931412，DECISIONS「第 11 步」）：`/t2a_v2`、`/voice_design`、`base_resp` 错误码、按计费字数记账；`common:modelError` 把错误码翻成人话。之后改国内站 + 人民币价（0ee236c，DECISIONS「MiniMax 用国内站」）。
- 第 12 步（上）：本地 Python 运行时（783045c，DECISIONS「第 12 步（上）」）：`adapters/local_python.py`、`modelhub/vram.py`、三个 worker。
- 第 12 步（下）（d7cdced，DECISIONS 2026-10-21「第 12 步（下）」）：`modelhub/workflows.py`（工作流目录、按标题绑定）、`adapters/comfyui.py`（上传 → `/prompt` → 轮询 `/history` → `/view`，超时 `/interrupt` + 删排队，`comfy_lost`，租约 `/free`）、`workflows/qwen-image{,-edit}/`（官方模板改写，Lightning 4 步，9:16 → 928×1664）；版本记 `workflow_id` / `workflow_sha256` / `comfy_env_hash`；安装器 `uv_sync`（`UV_PROJECT_ENVIRONMENT`）、`runtimes/{qwentts,ocr}/`（pyproject + uv.lock）；清单 `rt_qwentts`、`rt_indextts`（index-tts `d9e41aa`、Python 3.11）、`rt_ocr`、`w_img_t2i`，IndexTTS 辅助模型并进 `w_tts`（8.3 GB）；`py_import` 的 `gpu: true` 查 CUDA 版和 sm_120；`needs`。worker 修正：IndexTTS 必填 `lang`、`use_cuda_kernel=False`；Qwen3-TTS 按本地文件夹加载。Setup 页多 4 行（原型没有）。测试：`test_comfyui_adapter.py` 12 个、`test_asset_refs_api.py` 真实 ComfyUI 适配器 + 假 ComfyUI 出草稿。pytest 645、Vitest 278、Playwright 34 全过。
- 第 13 步：本机真装真跑（工具 6812db1；结果 a6d565b–2b678e2，DECISIONS 2026-10-21「第 13 步」，`reports/m3-local-smoke.txt`）：五项经真实安装器装好（18 分钟，没动 Anaconda）；冒烟六步全部本地成功。跑时修了四处：画面文字提示词（原来画成拼图）、台词结尾留缓冲（`tail_s`，Kelvin 听出尾音被切）、Qwen3-TTS 限长（一次说了 78 s）、补视图改用真实参考图；Kelvin 定表情一张一种（补视图 6 张），GPU 队列先跑完已加载模型的任务（硬规则 8）。
- 第 13 步追加：补视图用官方 40 步（52b40cf，DECISIONS「第 13 步追加」）：Kelvin 看了 4 步 / 40 步对比后定的。`workflows/qwen-image-edit-hq/`（去掉 Lightning LoRA，steps 40、cfg 4.0）、模型 `comfy/qwen-image-edit-hq`，补视图本地模型改过去（草稿、画面文字、关键帧仍 4 步）；每张视图带负面提示（`views.py:negative_for`，愤怒 / 难过压住龇牙、哭），侧面 / 背面提示词收紧。5090 上 47–70 s / 张，一个角色约 6 分钟。冒烟脚本的补视图一步先查参考图是本地画的。pytest 650、Vitest 278、Playwright 34 全过。
- 第 14 步（大部分）：真实冒烟（脚本 ed52ea1；修复和结果本提交，DECISIONS 2026-10-21「第 14 步」，`reports/m3-live-smoke.txt`）：跑了三次共 $1.57。GPT Image 2 终版 + OCR、MiniMax 音色（设计 + 5 个情绪）、两句配音全部跑通，花费和估价对得上。Google（没开通付费，`limit: 0`）和 Seedream（方舟安全体验模式到上限）被账号挡住，花费 $0。修了：Seedream 删 `sequential_image_generation`；新错误码 `quota_exceeded`（不重试，`http.send()` 以 `retryable` 为准）；路由把失败原文写进日志。pytest 652、Vitest 278 过。

## 下一步

- **第 14 步剩下的 img**：等 Kelvin 处理完两家账号（见「等 Kelvin 的事」），跑 `DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/live_assets.py --only img`（约 $0.15，ComfyUI 和工作台要开着），把结果补进 `reports/m3-live-smoke.txt`，勾掉计划第 14 步。等的时候可以先做**第 15 步收尾**里不依赖它的部分（SPEC 补 M3 的实际做法、写 `reports/M3.md` 的草稿）。可选、没排期：画表情前把锁定图的头肩裁出来当参考（脸更大）。
- **提醒 Kelvin 重启后端**：第 3–12 步的新接口和配置（锁定、上传；画面文字、OCR、音色、配音，`config/voice.yaml`，`/episodes/{id}/dub`，事件的 `slot`；素材闸门、`asset_edit`；`providers.yaml` 的新价格、测试连接的 `media`；ComfyUI 适配器、清单四项；补视图改 40 步）。不重启的话热更新后的前端读旧后端：画面文字的候选显示「OCR 未检查」，配音那一行加载失败。已经有版本的素材重启后不动；要看第 5–7 步的示例，停掉后端后跑 `uv run --no-sync python -m drama_series_agent.studio_cli demo --reset` 再启动。
- **`start.ps1` / `start.sh` 默认真实检测**（`-RealSetup` 默认开，Kelvin 2026-10-21 定；`-RealSetup:$false` / `--no-real-setup` 换回示例机器）。直接 `drama-studio dev` 和测试仍是 Mock 即示例机器。
- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。heredoc 里 Python 字符串的 `\n` 会被写成真换行（第 5 步踩了两次）：要写进代码的 `\n` 用 Edit 工具。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

- **测试别在「档案写完」后立刻断言任务状态**：任务结束比档案写入晚一点，CI 慢机器上会读到 running（`test_rescan_replaces_a_running_scan`，2026-10-21 修：等任务都结束再比）。
- **同一次物化建的行 `created_at` 可能相同**（Windows 时钟粗，Linux 细，结果相反）：别拿它排序或当次序；出场矩阵改成按分析里的顺序（`seed_json.order`）再按 id。
- 有 `upstream` remote（`binwu1/drama-series-agent`）；Kelvin 已把 `gh` 默认仓库设成 `kelvin78901/AIVideoGenerationAgent`，保险起见 `gh pr` 仍带 `-R`。
- 演示里逐步推进的流程（检测、安装、同步）用 `mocks/events.ts:repeatDemo`；测试把对应的 `demoTiming` 设成 0，所有步骤在一个任务里跑完，不要靠放宽等待时间。
- Kelvin 本机常开着 `start.ps1`（5173 前端 + 8000 后端，Mock 模式），Vite 会热更新，可以直接拿来做浏览器核对；不要往里发真实（非 Mock）调用。**后端不会自动重载**：改了后端接口要提醒 Kelvin 重启后端，否则热更新后的前端读旧后端，报「接口返回的数据和约定不符」。
- 示例里的运行延迟在 `mocks/events.ts:demoTiming.runMs`，测试里改成 20 ms（见 `components/products.test.tsx`）；测试要挂 `useEventStream()`（`FakeEventSource`）才收得到 `version.created`。
- **Chromium 新版 `scrollIntoView()` 返回 Promise**：`useEffect(() => el.scrollIntoView())` 这种箭头表达式会把 Promise 当清理函数，整页白屏（jsdom 里测不出来）。effect 一律写花括号；滚动日志用容器的 `scrollTop`。
- 页面里有演示事件驱动的长流程时，用临时的 `e2e/tmp-*-shots.spec.ts`（`--project=shots` 能匹配）在真浏览器里走一遍、截图到 scratchpad，跑完删掉。
- `test_restart_resume` 偶发失败（2026-10-18、10-20）的原因：Windows 上 `.venv/Scripts/python.exe` 是启动器，真正的解释器是它的子进程，`kill()` 后还要零点几秒才退出，期间读数据库报 disk I/O error。第 13 步起 `tests/e2e/conftest.py:Backend.kill()` 等端口关掉再返回（连跑 5 次都过）。
- **全部 pytest 约 10 分钟**（超过 Bash 前台 10 分钟上限）：用 `run_in_background` 跑，输出写到 scratchpad。
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

- 看截图（原型没有的部分，都在 `reports/ui/`）：第 4 步 `assets-{draft,views,matrix}`；第 5 步 `assets-{text,text-composite,ocr-confirm}`（Mock 的图不真画字）；第 6 步 `assets-voice-{final,drafts}`；第 7、8 步 `assets-dub-{confirm,voice}`、`script-dub{,-table,-impact}`、`assets-{gate-refused,edit-locked}`；第 10 步 `spec`（兼容表两行变「原生支持」）。
- **定一下**：确认过的任务真实花费超过确认金额时现在直接停（`budget_exceeded`），多步流程（比如音色终版 = 设计 + 5 次合成）会停在半路、前面花的白花。要不要留余量（比如确认金额的 10% 或 $0.05，取大的）？没定之前靠估价往高估（DECISIONS「第 11 步」）。
- **两家账号**（第 14 步 img 要用；2026-10-21 17:47 第 4 次仍被挡，$0，见 `reports/m3-live-smoke.txt`）：① Gemini：工作台用的是钥匙串里那把密钥，它所在的项目还在免费层（配额 ID 是 `*-FreeTier`）——在 AI Studio 的 API 密钥页看这把密钥属于哪个项目，给**那个**项目开通付费；或者在已付费的项目里新建密钥，到「模型与兜底 → 填密钥」换掉。② 火山方舟：`doubao-seedream-5-0-flash` 仍报 `SetLimitExceeded`——「开通管理」里找**这个**模型（不是 4.5 等其他版本），关掉安全体验模式或调高上限；ARK 密钥属于哪个账号，就要在哪个账号里改。③ 听一下真实的 MiniMax 音色和配音：`C:\Users\kelvin\AppData\Local\Temp\drama-live-smoke-g41t4kie\out\`（`linwan-voice-*.wav`、`dub-*.wav`）。④ **定一下**：OCR 没读到句末「。」判成漏字，要不要放宽（DECISIONS「第 14 步」）。
- M2 留下的：看真实冒烟的剧本（`reports/m2-live-smoke-book.txt`），定要不要调提示词、开思考。

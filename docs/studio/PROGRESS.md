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
- 第 8 步：素材闸门、影响范围、级联（后端 bb1b47d、前端 333bdc6，DECISIONS 同日「第 8 步」）：整集素材闸门 409 `assets_not_locked`、「素材」真实计数 7 / 10、级联停止集、影响行按槽位合并、`asset_edit`。
- Kelvin 看过第 7、8 步（cf66b26）：计数定 7 / 10；候选卡改定宽小卡 + 放大看（`components/MediaLightbox.tsx`）。
- 第 9 步：Mock 端到端（c6c1761，时序修复 5fc2940，CI 绿）：`tests/e2e/test_script_to_dub.py` 从导入小说走到每句配音、场时长 = 音频之和。
- 第 10 步：图像 API 适配器（489516e，CI 绿，DECISIONS 2026-10-21「第 10 步」）。三家按官方文档核对：`gemini-3-pro-image`（原生 `generateContent`）、`gpt-image-2`（generations / edits）、Seedream 选 5.0 flash `doubao-seedream-5-0-flash-260915`；`adapters/{http,images,google,openai_images,volcengine}.py`、`modelhub/media_adapters.py`（按 `providers.yaml` 的 `adapter` 挑类）；`Pricing.token_rates` + `Usage.tokens`（Gemini、GPT Image 按 token 记账）；测试连接带上同账号的出图模型（`media`），密钥弹窗显示「这个密钥也用于」。价格改成 0.134 / 0.23（估）/ 0.018；兼容表两行变原生（和原型不同），`spec` 重截。`tests/unit/test_image_adapters.py` 13 个（respx，不触网）。pytest 614、Vitest 277、Playwright 34 全过。
- 第 11 步：MiniMax 适配器（0931412，CI 绿，DECISIONS 2026-10-21「第 11 步」）。`adapters/minimax.py`（`adapter: minimax_speech`）：`/t2a_v2`（hex WAV）和 `/voice_design`；`base_resp` 错误码；按 `usage_characters` 记字数，$3 按 `usage_voice_count` 记在 MiniMax 收费的那次合成上，试听 $60 / 百万字（`extras.design_preview_char`）；估价非 ASCII 按 2 字；测试连接用免费的 `/get_voice`。国内地址改成 `api.minimax.cn`。`run_failed` toast 的错误码翻成人话（`common:modelError`）。`tests/unit/test_minimax_adapter.py` 7 个 + 音色出终版走真实适配器的集成测试。pytest 622、Vitest 278、Playwright 34 全过。
- 第 12 步（上）：本地 Python 运行时（本提交，DECISIONS 2026-10-21「第 12 步（上）」）。`adapters/local_python.py`（常驻 worker、JSON 行协议、超时杀掉重启、`Registry.aclose()` 退出时关掉）、`modelhub/vram.py`（整个进程一把显存锁，换模型先让上一个放手）、`workers/worker_{protocol,qwentts,indextts,rapidocr}.py`（不进 mypy，第 13 步真跑）；`providers.yaml` 本地模型加 `worker` / `env` / `args` / `gpu`；`SetupService.runtime_paths()`。`tests/unit/test_local_python.py` 6 个（假 worker 用真协议，连跑 5 次都过）。pytest 628 全过（前端没改）。

## 下一步

- **第 12 步（下）：安装 + ComfyUI 适配器**（计划 `plans/M3.md` 第 12 步「下」、「本地 Python 运行时 · 清单新增」「图像适配器 · ComfyUI 最小适配器」两节；SPEC 6.4.2 工作流目录 `workflows/<slug>/workflow.api.json` + `workflow.yaml`）。① 安装器加 `uv_sync` 步骤（`setup/manifest.py:StepType`、`setup/steps.py:_StepRun._uv_sync`、`installer.py:STEP_SECONDS`，新错误码进 `setup.json` 词条）；清单加 `rt_qwentts`（env `qwentts`）、`rt_indextts`（env `indextts`，源码克隆到 `{envs}/indextts-src` 锁 commit，Python 3.11，torch 2.8 cu128，不装 DeepSpeed，辅助模型预下到 `{models}/hf`）、`rt_ocr`（env `ocr`，只用 CPU）、`w_img_t2i`（Qwen-Image-2512 fp8 + Lightning LoRA，约 20 GB）；本地模型写上 `needs`。② `adapters/comfyui.py`：`/upload/image` → `/prompt` → 轮询 `/history` → `/view`，超时 `/interrupt` + 删排队，按节点标题绑定，拿显存租约（让别人放手时 `/free`），版本记 `workflow_id` / `workflow_sha256` / `comfy_env_hash`；ComfyUI 地址从扫描结果拿（`setup/service.py:248` 的写法）。没有现成的 ComfyUI 运行客户端，`setup/snapshots.py:ManagerSnapshots` 是可以照抄的 httpx 写法。测试用假 ComfyUI（httpx MockTransport）。
- **提醒 Kelvin 重启后端**：第 3–11 步的新接口和配置（锁定、上传；画面文字、OCR、音色、配音，`config/voice.yaml`，`/episodes/{id}/dub`，事件的 `slot`；素材闸门、`asset_edit`；`providers.yaml` 的新价格、测试连接的 `media`）。不重启的话热更新后的前端读旧后端：画面文字的候选显示「OCR 未检查」，配音那一行加载失败。已经有版本的素材重启后不动；要看第 5–7 步的示例，停掉后端后跑 `uv run --no-sync python -m drama_series_agent.studio_cli demo --reset` 再启动。
- **`w_img` 已装好**（2026-10-21）：31 GB 用了 14 分钟（约 37 MB/s），sha256 都校验过，剩余时间预估误差在 ±20% 以内。
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
- Playwright 冒烟收尾时后端会打印 aiosqlite「Task was destroyed but it is pending」，不影响结果，还没查。
- **单元测试绝不能触网**：`test_steps.py` 的 `_install` 默认离线 transport；别给 RealRunner 的测试传 `transport=None`（清单有真实下载地址，曾真的下了 30 GB 到 pytest 临时目录）。
- **示例机器切换**：点已选中的那台不会触发切换；e2e 里切 Mac 再切回 PC 要等前一次 `aria-checked` 变了再点。
- MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。
- **能力过滤在 Mock 下也生效**：扫描示例机器后路由会变（PC 示例装好之前视频、关键帧、超分走 API；没扫描过不过滤）。
- **改带平台分支的代码后加跑 `python -m mypy --platform linux`**：CI 是 Linux，Windows 上的 mypy 看不出只在 Windows 有的名字。
- **本机应用控制策略拦 `.venv/Scripts` 里 uv 生成的入口 exe**（`pytest.exe`、`mypy.exe`、`drama-studio.exe` 报 os error 4551，`ruff` 不受影响）：一律 `uv run --no-sync python -m pytest` / `python -m mypy`；后端用 `python -m drama_series_agent.studio_cli dev`（`start.ps1`、Playwright 已改）。
- **本机 PowerShell 执行策略禁止 `-File` 跑脚本**：钩子、状态栏、`start.ps1` 都要 `powershell -NoProfile -ExecutionPolicy Bypass -File …`。
- 写接口（非 GET）要带 `X-Drama-Studio: 1`，Host 必须是 127.0.0.1 / localhost；`TestClient` 要用 `base_url="http://127.0.0.1"`。
- **Kelvin 开着 `start.ps1` 时 `uv run` 会失败**（同步要替换正被占用的 `.venv/Scripts/drama-studio.exe`）：一律 `uv run --no-sync …`；**加依赖（jinja2、python-docx）时**要先请 Kelvin 停掉后端再 `uv sync`。
- Windows 上 `python` 不在 PATH（会跳到应用商店），一律 `uv run python`。pnpm：`corepack enable --install-directory ~/bin pnpm`；命令前加 `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` 避免首次下载提示。
- Windows PowerShell 5.1：`.ps1` 必须存成 UTF-8 带 BOM，否则中文乱码。
- YAML 1.1 会把 `on:` / `mode: off` 解析成布尔值：`core/config.py` 用只认 true/false 的加载器。
- SQLite 读回时间会丢时区，用 `models_db.UtcDateTime`。
- **上游 `.gitignore` 有 `templates/`、`config.json`**，会挡住任何叫这个名字的目录 / 文件；`prompts/templates/`、`web/src/test/data/config.json` 已用 `!` 放行。新加文件后看 `git status --ignored`；**每次 push 后看一眼 `gh run list`**（这次红了 20 多个提交没发现）。
- **页面测试里上传文件**：`test/setup.ts` 已把 `FormData` / `File` 换成 Node 的（jsdom 的发出去是 `"[object FormData]"`），假后端里 `await request.formData()` 可以直接用。
- **Radix 下拉菜单里打开对话框要 `modal={false}`**，否则对话框关掉后 `body` 留着 `pointer-events: none`（jsdom 里表现为后面的测试点不动）。
- **ESLint `no-irregular-whitespace`**：全角空格（U+3000）在正则、注释里会报错（字符串里不报）——正则写 `\s`，注释别用；**`react-hooks/set-state-in-effect`**：不要在 effect 里同步 URL 参数到 state，在渲染时推出来（见 `Script.tsx` 的 `picked`）。
- 再出现 os error 4551，就是 Windows 智能应用控制（Kelvin 2026-10-20 已关掉）。
- **Vitest 里 `vi.mock("sonner")` 对 `api/events.ts` 不生效**（setup 已经先加载了真的 sonner）：看 toast 用 `vi.spyOn(toast, "error")`。
- **改代码前先看 ruff 有没有已经改过行**：`ruff format` 会把长行拆开，之后用 sed 按原行号替换会留下碎片（第 4 步踩过）。

## 等 Kelvin 的事

- 看截图（原型没有的部分，都在 `reports/ui/`）：第 4 步 `assets-{draft,views,matrix}`；第 5 步 `assets-{text,text-composite,ocr-confirm}`（Mock 的图不真画字）；第 6 步 `assets-voice-{final,drafts}`；第 7、8 步 `assets-dub-{confirm,voice}`、`script-dub{,-table,-impact}`、`assets-{gate-refused,edit-locked}`；第 10 步 `spec`（兼容表两行变「原生支持」）。
- **定一下**：确认过的任务真实花费超过确认金额时现在直接停（`budget_exceeded`），多步流程（音色终版 = 设计 + 5 次合成）会停在半路、前面的 $3 白花。要不要留余量（比如确认金额的 10% 或 $0.05，取大的）？没定之前靠估价往高估（DECISIONS「第 11 步」）。
- 第 13 步还要下约 20 GB 的 Qwen-Image-2512 和约 15 GB 的 TTS 环境（到时再问）。
- M2 留下的：看真实冒烟的剧本（`reports/m2-live-smoke-book.txt`），定要不要调提示词、开思考。

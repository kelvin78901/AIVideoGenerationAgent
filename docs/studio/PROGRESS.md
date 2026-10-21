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
- 第 7 步：台词配音 + 时长。后端（1d94c66，CI 绿）：组件 `dub`、`assets/dub.py`、`pipeline/timing.py`。前端（49215a9，CI 绿，DECISIONS 2026-10-21「第 7 步（前端）」）：事件带 `slot`、`line_audio` 只刷 `["dub"]`、配音不逐条 toast；`POST /dub` 加 `line_ids`、每句加 `tone_emotion`；`api/{schemas,hooks}/dub.ts`、`test/fakes/dub.ts` + `test/data/dub.json`；素材页进度卡「台词配音 n / m · 全部配音」（先估价确认）、音色详情「第 N 集的台词配音」（播放、情绪、配音 / 重配）、剧本页播放 + 真实时长 + 场标题下的台词总时长；`AudioPlayer` `compact`；Playwright 新项目 `seeded`（`smoke` 依赖它，最先跑）。截图 `assets-dub-{confirm,voice}`、`script-dub{,-table}`，`assets`、`script` 重截。ROADMAP 勾「台词配音」。pytest 590、Vitest 272、Playwright 33 全过。

- 第 8 步：素材闸门、影响范围、级联。后端（bb1b47d，DECISIONS 2026-10-21「第 8 步（后端）」）。整集素材闸门（`GateService.members`、`reopen_using`，409 `assets_not_locked`）、进度「素材」真实计数（`EpisodeService.counters`，示例 7 / 10）、级联停止集（候选类组件不重跑）、影响行按槽位合并（`count`、花费相加）、`line_audio` 进流水线顺序、`asset_edit`（`PlannedChange.rerun`：确认并同步 = 这条素材重出候选）、解锁音色列出配音句数。`tests/api/test_asset_sync_api.py` 8 个。前端（本提交，DECISIONS 同日「第 8 步（前端）」）：闸门和「素材」进度改走后端（MSW 不再叠加）、已锁定素材的修改走 `asset_edit` 影响范围、新影响行文案、影响行价格用 `formatCost`、示例剧集去掉重复的 `dub_lines`、假后端算素材计数和闸门；Playwright 无示例数据一轮加闸门和改已锁定素材。截图 `assets-{gate-refused,edit-locked}`、`script-dub-impact`，11 页全部重截（导航「素材」7/10）。pytest 598、Vitest 275、Playwright 34 全过。

## 下一步

- **第 9 步：Mock 端到端和截图**（M3 验收在这里，计划 `plans/M3.md` 第 9 步和「验收怎么做」）。Playwright 那几项第 7、8 步已经有了（`seeded.spec.ts` 全部配音并播放；`real.spec.ts` 锁定 / 解锁、改已锁定描述出影响范围、无示例数据一轮），核对一遍就行。主要是 pytest 端到端：示例小说 → 剧本确认 → 素材分析 → 13 条出候选并锁定（`gate_decision` 有哈希）→ 全集配音 → 每行有音频、场时长 = 音频之和（照 `tests/e2e/test_novel_to_script.py` 的写法，起真实后端进程）。然后素材页、剧本页亮 / 暗截图，勾 ROADMAP 的 M3 验收项。
- **提醒 Kelvin 重启后端**：第 3–8 步的新接口和配置（锁定、上传；画面文字、OCR、音色、配音，`config/voice.yaml`，`/episodes/{id}/dub`，事件的 `slot`；素材闸门、`asset_edit`）。不重启的话热更新后的前端读旧后端：画面文字的候选显示「OCR 未检查」，配音那一行加载失败。已经有版本的素材重启后不动；要看第 5–7 步的示例，停掉后端后跑 `uv run --no-sync python -m drama_series_agent.studio_cli demo --reset` 再启动。
- **`w_img` 已装好**（2026-10-21，Kelvin 用 `DRAMA_SETUP=real` 在 Setup 页装；本次安装记录见下面「等 Kelvin 的事」上一条）：31 GB 用了 14 分钟，平均约 37 MB/s；按文件算 36–42 MB/s，sha256 都校验过；装之前存了 ComfyUI-Manager 快照。剩余时间预估误差在 ±20% 以内：开头 822 秒，实际 807 秒；中途 598 / 685、621 / 532、173 / 213；最后一分钟准确。连接数没写进事件，记录里看不出来；速度比 2026-10-18 单连接实测的 25–30 MB/s 快，可能用了多连接。
- **`start.ps1` / `start.sh` 默认真实检测**（`-RealSetup` 默认开，Kelvin 2026-10-21 定；`-RealSetup:$false` / `--no-real-setup` 换回示例机器）。直接 `drama-studio dev` 和测试仍是 Mock 即示例机器。
- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。heredoc 里 Python 字符串的 `\n` 会被写成真换行（第 5 步踩了两次）：要写进代码的 `\n` 用 Edit 工具。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

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
- **改代码前先看 ruff 有没有已经改过行**：`ruff format` 会把长行拆开，之后用 sed 按原行号替换会留下碎片（第 4 步踩过）。

## 等 Kelvin 的事

- 定「素材」的计数：现在按本集用到的素材算（示例 7 / 10），原型 7 / 13 算的是整张清单（DECISIONS 2026-10-21「第 8 步（后端）」）。截图 `reports/ui/assets.light.jpg`。
- 看第 7、8 步的截图（配音没有原型）：`assets-dub-{confirm,voice}`、`script-dub{,-table,-impact}`、`assets-{gate-refused,edit-locked}`。
- 看第 4 步的素材页截图（原型没有的三块：出终版和上传 `reports/ui/assets-draft.light.jpg`、补视图 `assets-views`、出场矩阵 `assets-matrix`），有要改的告诉我。
- 看第 6 步的音色截图：终版（样音 + 情绪变体）`assets-voice-final`、试听 `assets-voice-drafts`（原型只有试听，没有终版和情绪变体）。
- 看第 5 步的画面文字截图：模型出字 `assets-text`、后期贴字叠字预览 `assets-text-composite`、锁定不一致的确认框 `assets-ocr-confirm`（原型只写「不能直接采纳」）。Mock 的图不会真的画字，只把字记在文件里给 Mock OCR 读。
- 第 13 步还要下约 20 GB 的 Qwen-Image-2512 和约 15 GB 的 TTS 环境（到时再问）。
- M2 留下的：看真实冒烟的剧本（`reports/m2-live-smoke-book.txt`），定要不要调提示词、开思考。

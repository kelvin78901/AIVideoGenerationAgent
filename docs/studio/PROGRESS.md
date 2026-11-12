# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M5.5 镜头契约 + 图片来源与编辑**，计划 [`plans/M5.5.md`](plans/M5.5.md)（Kelvin 2026-11-10 批准；DECISIONS「M5.5 计划」）。M5 已合并（PR #7，e6044d4），M5 的各步记录在 [`reports/M5.md`](reports/M5.md)。
- 分支：`m5.5-images`（从 main e6044d4 开出）。
- Kelvin 定：契约和检查先做（第 2–9 步），图片来源与编辑后做（第 10–18 步）；检查**只提示、不挡**；声音克隆最后一步。

## 已完成的小步

- **0**（3f94986）计划、分支。**1**（e789654）界面草图 `prototype/m5.5/`，等 Kelvin 看；Kelvin 已定的三件事（6e0a67c）。
- **2**（b1bc8f4）镜头契约数据：`shots/contract.py`、迁移 `0024`、`ShotOut.contract` / `PATCH {contract}`、示例 `plan.json`。CI 修复 ccc5535。
- **3**（1891ab0）关键帧画开始状态，视频按契约（只有 `delivery == dialogue` 进 take、动作预算、`h3_format.UNDONE`）。 **4**（60e16f9）分镜检查：规则 `shots/check.py` + 组件 `plancheck`，`GET/POST /episodes/{id}/shot-checks`。
- **5a**（4f0ff04）道具 `physical` 进道具图和关键帧、OCR 只提示；**5b**（45e867f）有字的道具（素材分析 `on`）、道具图画字 + OCR、示例剧删 txt1（素材 7/9）。
- **5c**（8b198bb）比例参考：新组件 `scale`（`pipeline/components/scale.py`，槽位 `ref_scale`，编辑模型，自动采纳）：道具锁定后和一个锁定角色同框出一张（描述里提到的角色，否则同场最多的）；关键帧在道具图后面紧跟它，视频不用；模板 `templates/scale/`；Models 页 27 行；前端 `ProductSlotSchema` 加 `ref_scale`。测试：keyframes / assets / asset refs / asset sync / config / capabilities / takes API、web fixtures 重导、前端 Models / Script vitest、tsc、eslint；ruff、mypy 干净。第 5 步勾掉。**Kelvin 开着 `start.ps1` 要重启后端。**
- **6**（29382a4）关键帧检查：`pipeline/kfcheck.py` + 路由 `kfcheck`（Gemini Flash-Lite），`kf._check` 每张候选看一次 + OCR（`ocr.contains`），写 `payload.candidates[i].check`；估价含看图；模板 `templates/kf/check.j2`；Models 页 28 行；前端 zod 候选加 `check`。测试：keyframes / config / capabilities API、ocr 单元、web fixtures 重导、前端 Models / Storyboard / Script vitest、tsc；ruff、mypy 干净。 **7**（8590129）take 检查：`media/video.py:contact_sheet`（6 帧 3 × 2）、`pipeline/takecheck.py` + 路由 `takecheck`，`vid._check_take` 草稿和终版都跑，写 `payload.check`、`sheet` 文件；加 `cut` / `hold` 两条量出来的；Models 页 29 行。测试：video 单元、takes / generate / config API、web fixtures 重导、前端 Models / Generate / Script vitest、tsc；ruff、mypy 干净。
- **8a**（de75eb6）分镜页：契约一节、分镜检查横幅 / 镜头卡徽标 / 镜头内提示、关键帧候选的检查条目；i18n 两种语言；测试假后端 shot-checks。测试：前端 Storyboard / storyboard vitest（32）、i18n 检查、tsc、eslint、prettier；web fixtures（shots）重导。 **8b 前半**（67d38d1）take 卡：有 `payload.check` 时「自动质检」那块换成「契约检查」（条目 + 有问题时显示 6 帧拼图），「局部修复」点了提示 M6 提供；测试：前端 Generate vitest（19）、tsc、eslint、i18n。
- **8b 后半**（cd922b8）素材页道具：`PATCH /assets/{id}` 加 `physical`（只道具，写 `settings.physical`，设过就以它为准）、`text.pen`（用什么写，`img.lettering()`，默认圆珠笔时提示词不变）；前端 `pages/assets/Prop.tsx`（尺寸材质新旧三栏、比例参考 + 重画这张），道具的字不显示做法、风格只手写 / 印刷；删掉「仍然锁定」对话框和假后端 409。截图 storyboard / generate / assets 重截（示例数据里没有比例参考图）。测试：assets / asset text / asset refs API、asset ops 单元、web fixtures（assets）重导、前端 Assets / Script / Storyboard vitest（73）、i18n、tsc、eslint、prettier；ruff、mypy 干净。**第 8 步勾掉。后端改了接口，Kelvin 要重启 `start.ps1` 的后端。**

## 下一步

- **9 中 / 9 中 B**（223d1b9、4025879）先按检查改分镜再出 take；用户写的画面描述取代剧本动作行（B）。详见 [`reports/M5.5.md`](reports/M5.5.md)。
- **9 后**（0d3c8ff，CI 修复 ca3ec73）第十九轮 10 个镜头各 1 条 take（本地 H3），粗剪 48.1 秒 `originals/run19-contract/ep1-cut.mp4`；`run19-contract/README.md` 六条瑕疵逐条结论：**六条都修好**。新问题：1-06 关门把自己关在门外（关键帧从楼道拍；1-08 接它的尾帧也在楼道）、1-04 两张便利贴 + 黑伞、1-09 光线像白天；take 检查 1-10 误报、1-06 漏报。跑法：`PYTHONIOENCODING=utf-8 DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/local_video.py --only episode --home %TEMP%\drama-ep19-5Oilw8\home --from 1-0X --to 1-0X --run run19-contract --takes 1`。 CI 修复：e2e `test_storyboard_to_takes` 按第 7 步的 take 检查改了两处断言（每条 take 和 API 终版各多一次 `takecheck`；8b 起 CI 红在这）。
- **9d**（0e4ceec…055c95d）流程约束第十九轮的新问题（DECISIONS「流程约束细节」），只重出 1-04、1-06、1-08、1-09。**Kelvin 2026-11-11 看 `run19-redo/ep1-cut.mp4`：不如第十七轮**（伞和人一样大、举手机对镜头、开门穿模、多一只手、室内外融在一起；那次成片另 6 镜是旧的）。 **9e 再追六条**（Kelvin 2026-11-11 批准，DECISIONS「第 9e 步」；修不好就回退到第十七轮的提示词写法）。**9e-1**（4d616a4）比例参考不再进关键帧、锁定道具不再自动画；`kf.size_words` 把尺寸写成和人比（「立着到人的胯部」）。测试：kf 单元、keyframes / assets API、web shots fixture 重导、前端 vitest。**9e-2**（9b0f187）特写自己局部（`kf.part_of`）不带她的全身参考、写「过肩或她的视角」（`PART_VIEW`）；看有字的东西写朝向（`facing`）；关键帧和 take 检查加 `hands`、`facing`，take 再加 `solid`（穿模）。测试：kf 单元、keyframes / takes API、shots / generate fixture 重导、前端 Storyboard / Generate vitest。**9e-3**（75e7a2e）场景 `adjoins`、`kf.shot_space`（机位地点 = 镜头引用的场景，门外场景的图进参考），两个检查的 place 问门外。**9e-4**（bc14cf0）规则 `crowded`（`shots/check.py:crowded`：穿过门口又做别的动作，或超过 3 个动作；契约门外→屋里也算穿过），i18n `checks.code.crowded`，plancheck 加 code；分镜模板加「进门 / 出门单独一个镜头」；`shots/service.py:plan_issues` 抽出来，`plan.gather` 重出时带「上一版的分镜检查」一块。示例 1-06 现在报 crowded。另修 CI：9e-2 起 1-05 不带林晚参考，影响范围少了 1-05（asset refs / storyboard 两条测试的期望）。测试：shot check 单元、shots / storyboard API、asset refs 那条、web fixtures（script / shots）重导、前端全量 vitest + i18n、tsc、prettier；ruff、mypy 干净。**9e-5a**（506b34d）关键帧检查没过自动重画：`kf.run` 本地出图且全部候选没过时，带「上一次没过的检查」再画，最多 `redraw: 2`（`config/components.yaml`，`ComponentConfig.redraw`），留第一次通过的、否则通过最多的；`payload.redraws`；估价含重画的看图；`kfcheck.passed / score / failed_text / LABELS`；分镜页候选下一行提示（i18n `shot.redrawn / redrawnStill`）。测试：keyframes API（含两条新测试）、config / capabilities API、kf 单元、web fixtures（shots）重导、前端 Storyboard vitest、i18n、tsc、eslint；ruff、mypy 干净。**9e-5b**（64865b4）take 检查没过自动重出：`vid.run` 循环（`_take_files` 抽出来，`_take(fixes=, attempt=)`），没过的几条进 `Facts.fixes` 给改写模型，不改写的模型接在提示词后；留通过最多的那条，`payload.redraws`；估价含重出的改写 + 看图；共用 `pipeline/redraw.py`（kf 也改用它，标题改成「上一次没过的检查（这次要改掉）」）；take 卡一行提示（i18n `wall.redrawn / redrawnStill`）。第 9e-5 步勾掉。测试：takes / generate / keyframes / config API、h3_format 单元、web fixtures（generate）重导、前端 Generate / Storyboard vitest、i18n、tsc、eslint；ruff、mypy 干净。**9e-6 进行中**（Kelvin 定：第十七轮副本整集重出，每镜 1 条 take，开重出）。`contract_prep.py:fresh` + `local_video.py --only fresh`（补出租屋 adjoins、道具重画、分镜两次 + 检查、关键帧；`_props` 不再等比例参考）。第一次（`report-fresh-1-stale-pictures.txt`，约 $0.11）发现关键帧提示词里存的旧画面被当成用户写的，重出分镜没用；8051553 修 `materialize._follow_plan`（测试：shots / storyboard / keyframes / takes API、web fixtures；ruff、mypy 干净）。第二次（`%TEMP%\drama-ep20b\home`，`run20-fresh/report-fresh.txt`，约 $0.11）：分镜真的变了，第二版带着检查把进门、关门、开门拆开，共 13 个镜头；关键帧 9 张，每张至少一张候选全过或接近全过，没触发自动重画。剩下的提示：1-10、1-11 `undone` 来自**剧本动作行**「她拉开门，又关上。停两秒，再拉开。」（画面不是用户写的，按第 9 步 B 视频也读这行，take 很可能又开两次门）；`crowded` 误报 1-06「一只手握着门把、准备迈步进门」（「握着」是状态）。**9e-6b**（ba6f1fa）`shots/check.py:lines_fault`：剧本动作行单独看有 `undone` / `crowded` 就出 `lines_dropped` 提示（i18n `checks.code.lines_dropped`），规则和 `vid.gather` 都不再读这几行、只按画面拍；「握着」「抵着」这类状态不再算动作。示例 1-06、1-08 多了 `lines_dropped`。测试：shot check 单元、shots / storyboard / takes / generate API、web fixtures（shots）重导、前端全量 vitest + i18n、tsc、eslint、prettier；ruff、mypy 干净。**9e-6c 进行中**：重查分镜后 1-10、1-11 报 `lines_dropped`（只按画面拍）。take：1-01、1-02、1-04 一次过；1-03 重出 2 次仍没过，都是 `event`「水滴移动」——take 检查和插入镜头提示词允许的微动打架，ffccb35 改了检查（1-03 最后用新标准重查）。副本里第十七轮的 `episode-takes.json` 旧记录已删到只剩新 take。13 条都出完（1-05、1-11 被内存回收过一次后重跑），c1472e0 修 take 检查 `end`（机位在屋里≠人在屋里），粗剪 60.3 秒，对比写在 `run20-fresh/README.md`：第十九轮五个问题里伞的大小、室内外、穿模没了；新问题是改写模型给 1-12 加了拿伞，1-13 接尾帧只好放下再拿。**等 Kelvin**：看 `originals/run20-fresh/ep1-cut.mp4`，定比第十七轮好不好（不好按 DECISIONS 9e 回退），以及要不要修「改写模型给道具编合同外的动作」。
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


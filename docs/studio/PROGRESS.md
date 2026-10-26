# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M4 分镜与动态分镜**，计划 [`plans/M4.md`](plans/M4.md)（Kelvin 2026-10-21 批准，定的四项见 DECISIONS 2026-10-21「M4 计划」）。M3 已合并（PR #5），报告 [`reports/M3.md`](reports/M3.md)。
- 分支：`m4-storyboard`（从 main fb08576 开出）。

## 已完成的小步

- M4 第 0–11 步全部做完，每步做了什么、提交 hash、测试结果挪进了里程碑报告 [`reports/M4.md`](reports/M4.md)（「附：各步的提交」）。
- 第 11 步（5a3a2f5）：SPEC 补 M4 的实际做法（4.1、4.2、5.1、9.1、13.3）；ROADMAP 勾 M4；写 `reports/M4.md`；开 PR。全量 pytest 704 个（7c6af1a）、vitest 297 个、Playwright e2e 37 个过；ruff、mypy（含 linux）、eslint、tsc、prettier 干净。
- 追加（4e98a6d，DECISIONS「场景参考图固定横屏」）：`components.yaml` 的 `img.aspects: {scene: "16:9"}`、`img.asset_aspect`；改画幅不再列场景参考图；本机第 3 轮楼道 2/4 单幅、关键帧 9/9 单幅。全量 pytest 705 个、vitest 297 个过；ruff、mypy、eslint、tsc 干净。
- 追加（59b7557，DECISIONS「Kelvin 看图之后」）：对照实验（`reports/m4-local-smoke.txt` 末尾）；参考图模板任务行改「一张单幅写实照片，单一视角」（楼道 8/8 单幅）；没有角色的镜头加 `kf.NO_PEOPLE`（陌生人 5/6 → 1/6）；Google 充值后补跑 Nano Banana Pro 成功（$0.1393，真实冒烟合计 $0.167）。
- 追加（6f51215，DECISIONS「关键帧模型对比」）：FLUX 3 Klein 两个工作流（`workflows/flux3-klein`、`-t2i`，官方扩写）、Nano Banana 2.1（只填配置）、`kf.model_for` 取排在后面的同家文生图、ComfyUI 租约按权重文件区分；对比 `scripts/smoke/kf_bakeoff.py` → `reports/m4-kf-bakeoff.txt`（$0.605）：本地 Klein 明显好于 Qwen-Image-Edit，API 2.1 ≈ Pro、便宜一半多。全量 pytest 707 个、vitest 297 个过。
- 追加（本提交，DECISIONS「关键帧默认模型」）：kf 默认本地 `comfy/flux3-klein` → API `google/nano-banana-2.1`；清单新项 `w_flux3`（可选）；`capabilities.restrict` 本地默认跑不了先换组件里下一个能跑、有工作流的本地模型（没装 Klein → Qwen-Image-Edit），`unavailable` 列出组件所有跑不了的本地模型；示例种子、前端快照、兼容表、安装页项数跟着改。全量 pytest 708 个里 707 个过，`test_web_script_fixture_is_current` 1 个偶发失败（两个产物 id 顺序对调，单独跑 10 个都过，上一次全量也过，疑似同一时刻建的行排序）；vitest 297 个、Playwright e2e 37 个过；ruff、mypy（含 linux）、eslint、tsc、prettier 干净。

## 下一步

- **等 Kelvin 看完 PR #6 合并**（`reports/M4.md` 已更新；PR 描述用 `gh pr edit 6 -R kelvin78901/AIVideoGenerationAgent --body-file docs/studio/reports/M4.md` 刷新）。合并后下一个里程碑用 `/milestone` 出计划。
- **提醒 Kelvin 重启后端并 `demo --reset`**（第 1 步加了迁移 `0018`，第 2、3 步加了示例分镜和关键帧；本地库里关键帧产物是第 2 步的随机 id，`--reset` 后才是 `demo-p-kf-1-0X`；第 5 步起分镜页完全读后端，MSW 不再兜底）：`uv run --no-sync python -m drama_series_agent.studio_cli demo --reset`。不重启的话热更新后的前端读旧后端，会报「接口返回的数据和约定不符」。
- **`start.ps1` / `start.sh` 默认真实检测**（`-RealSetup` 默认开，Kelvin 2026-10-21 定；`-RealSetup:$false` / `--no-real-setup` 换回示例机器）。直接 `drama-studio dev` 和测试仍是 Mock 即示例机器。
- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（M2 计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。heredoc 里 Python 字符串的 `\n` 会被写成真换行：要写进代码的 `\n` 用 Edit 工具。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。`assets-views` 和 `assets` 是同一张（默认选中林晚），截完复制一份。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

- **CI**：第 4 步（d5cccb3）的 CI 红了：`e2e/real.spec.ts` 解锁「林晚出租屋」现在会列出用到它的镜头、弹影响范围，测试还按「不弹窗」写；第 5 步改好了。第 5、6 步的 CI（9afc438 那次）是绿的。第 7、8 步的 CI（8f6d587 那次）是绿的。第 9、10 步之后的 CI 交接时还在跑：`/continue` 时先 `gh run list -R kelvin78901/AIVideoGenerationAgent --branch m4-storyboard` 看一眼。
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
- **全部 pytest 约 11 分钟**（超过 Bash 前台 10 分钟上限）：用 `run_in_background` 跑，输出写到 scratchpad。**跑的时候别改已有的源文件**：模型和迁移在收集时已加载、e2e 子进程启动时读当前文件，半路改会出假失败（M4 第 1 步踩过）；只加新文件没事。
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

- **1-01 剧本里的「米色风衣湿了半边」**：模型会画成半边风衣泼了黑色汁液（换成「被雨淋湿」就没有，换 40 步也有）。改不改示例剧本的措辞、要不要别的处理，等 Kelvin 定。


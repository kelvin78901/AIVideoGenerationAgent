# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M1 首次启动 + 成片规格**（M0.5 已合并，报告 [`reports/M0.5.md`](reports/M0.5.md)）
- 计划：[`docs/studio/plans/M1.md`](plans/M1.md)（已批准 2026-10-15；Kelvin 的四个决定见 DECISIONS「2026-10-15 · M1 计划」；2026-10-18 追加 4c、5c、7b、8b、8c；**全部做完**）
- 分支：`m1-setup-spec`（从 main 切出；不推 main）；**PR #3** https://github.com/kelvin78901/AIVideoGenerationAgent/pull/3 （描述 = `reports/M1.md` + 署名），等 Kelvin 审阅合并

## 已完成的小步

- 第 0–9 步的逐步记录在 [`reports/M1.md`](reports/M1.md)「逐步记录」。
- 9（1/3）：SPEC 补 M1 的实际做法、ROADMAP 勾完（865e810）。
- 9（2/3）：写 `reports/M1.md`；`test_download_into_comfyui_model_folders` 不再比请求顺序（CI 在 2a9dfc7 偶发失败过，大小是并发探测的）；PROGRESS 精简（29a89c1）。
- 9（3/3）：开 PR #3；PR 上 CI 全过（Linux pytest 327、Vitest 197、冒烟 17；Windows pytest 327、Vitest 197），结果补进报告和 PR 描述；勾计划第 9 步（本提交）。

## 下一步

- **等 Kelvin 审 PR #3**。要改就在 `m1-setup-spec` 上接着提交、push，改了报告就 `gh pr edit 3 -R kelvin78901/AIVideoGenerationAgent --body-file <报告 + 署名>` 同步描述。
- Kelvin 合并后：`git switch main && git pull`，用 `/milestone` 出 M2 计划（M2 小说 → 剧本；`drama-studio demo` 和 `POST /series` 随 M2 做）。

- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

- 有 `upstream` remote（`binwu1/drama-series-agent`）；Kelvin 已把 `gh` 默认仓库设成 `kelvin78901/AIVideoGenerationAgent`，保险起见 `gh pr` 仍带 `-R`。
- 演示里逐步推进的流程（检测、安装、同步）用 `mocks/events.ts:repeatDemo`；测试把对应的 `demoTiming` 设成 0，所有步骤在一个任务里跑完，不要靠放宽等待时间。
- Kelvin 本机常开着 `start.ps1`（5173 前端 + 8000 后端，Mock 模式），Vite 会热更新，可以直接拿来做浏览器核对；不要往里发真实（非 Mock）调用。**后端不会自动重载**：改了后端接口要提醒 Kelvin 重启后端，否则热更新后的前端读旧后端，报「接口返回的数据和约定不符」。
- 示例里的运行延迟在 `mocks/events.ts:demoTiming.runMs`，测试里改成 20 ms（见 `components/products.test.tsx`）；测试要挂 `useEventStream()`（`FakeEventSource`）才收得到 `version.created`。
- **Chromium 新版 `scrollIntoView()` 返回 Promise**：`useEffect(() => el.scrollIntoView())` 这种箭头表达式会把 Promise 当清理函数，整页白屏（jsdom 里测不出来）。effect 一律写花括号；滚动日志用容器的 `scrollTop`。
- 页面里有演示事件驱动的长流程时，用临时的 `e2e/tmp-*-shots.spec.ts`（`--project=shots` 能匹配）在真浏览器里走一遍、截图到 scratchpad，跑完删掉。
- e2e 偶发过一次失败（2026-10-18，两条 e2e 一起跑，按耗时推断是 M0 的 `test_restart_resume`），之后连跑 17 次没复现，CI 上留意。
- Playwright 冒烟收尾时后端会打印 aiosqlite「Task was destroyed but it is pending」，不影响结果，还没查（后端本步没改）。
- **单元测试绝不能触网**：`test_steps.py` 的 `_install` 默认离线 transport；别给 RealRunner 的测试传 `transport=None`（清单有真实下载地址，曾真的下了 30 GB 到 pytest 临时目录）。
- **示例机器切换**：点已选中的那台不会触发切换；e2e 里切 Mac 再切回 PC 要等前一次 `aria-checked` 变了再点。
- MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。
- **能力过滤在 Mock 下也生效**：扫描示例机器后路由会变（PC 示例装好之前视频、关键帧、超分走 API，兼容表没有 `video_draft` 行；没扫描过不过滤）。第 7 步 Setup 页接真实接口后，e2e 里如果先扫描再看成片规格页，兼容表的预期要跟着改。
- **改 `setup/` 这类带平台分支的代码后加跑 `python -m mypy --platform linux`**：CI 是 Linux，Windows 上的 mypy 看不出 `subprocess.CREATE_NO_WINDOW` 这类只在 Windows 有的名字。
- **本机应用控制策略拦 `.venv/Scripts` 里 uv 生成的入口 exe**（`pytest.exe`、`mypy.exe`、`drama-studio.exe` 报 os error 4551，`ruff` 不受影响）：一律 `uv run --no-sync python -m pytest` / `python -m mypy`；后端用 `python -m drama_series_agent.studio_cli dev`（`start.ps1`、Playwright 已改）。
- **本机 PowerShell 执行策略禁止 `-File` 跑脚本**：钩子、状态栏、`start.ps1` 都要 `powershell -NoProfile -ExecutionPolicy Bypass -File …`。
- 写接口（非 GET）要带 `X-Drama-Studio: 1`，Host 必须是 127.0.0.1 / localhost；`TestClient` 要用 `base_url="http://127.0.0.1"`。
- **Kelvin 开着 `start.ps1` 时 `uv run` 会失败**（同步要替换正被占用的 `.venv/Scripts/drama-studio.exe`）：一律 `uv run --no-sync …`。
- Windows 上 `python` 不在 PATH（会跳到应用商店），一律 `uv run python`。pnpm：`corepack enable --install-directory ~/bin pnpm`；命令前加 `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` 避免首次下载提示。
- Windows PowerShell 5.1：`.ps1` 必须存成 UTF-8 带 BOM，否则中文乱码。
- YAML 1.1 会把 `on:` / `mode: off` 解析成布尔值：`core/config.py` 用只认 true/false 的加载器。
- SQLite 读回时间会丢时区，用 `models_db.UtcDateTime`。

## 等 Kelvin 的事

- 重启后端（本步加了迁移 `0006`，启动时自动升级；库里那条回滚记录（两次回滚都在同一个快照上）会显示「回滚过（当时没有核对）」）。下次真装大文件（如 Qwen-Image-Edit 31 GB）时看速度、剩余时间准不准，连接数是否停在 1 个。

- （2026-10-18 已办：第 8b 步真装、回滚、SageAttention 都做完，ComfyUI 已带 `--use-sage-attention` 启动（改的是 Desktop 的 `installations.json`，原文件备份在当时会话的 scratchpad）；真实扫描输出 Kelvin 看过、和我这边一致；8b 的三个版本已选；`start.ps1` 改 `python -m` 后本机能起；第 7 步的两张新界面截图、第 7b 步设计稿 Kelvin 审核通过；按镜头选工作流 / 拼节点 beta 已定，见 DECISIONS 和 SPEC 6.4.8。）
- 按 `reports/M0.5.md`「怎么验证」在本机点一遍，切中英和亮暗；看 `reports/ui/README.md` 的「有意的差异」。

# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M1 首次启动 + 成片规格**（M0.5 已合并，报告 [`reports/M0.5.md`](reports/M0.5.md)）
- 计划：[`docs/studio/plans/M1.md`](plans/M1.md)（已批准 2026-10-15；Kelvin 的四个决定见 DECISIONS「2026-10-15 · M1 计划」）
- 分支：`m1-setup-spec`（从 main 切出；每步提交后 push；不推 main；做完开 PR）

## 已完成的小步

| 步 | 做了什么 | 提交 | 测试 |
| --- | --- | --- | --- |
| 0 | 开分支；计划存档 `plans/M1.md`；ROADMAP 加 M1 计划链接和「环境与安装」入口一项；DECISIONS 记 M1 的决定 | 3703675 | 仅文档 |
| 1 | 表 `series`、`output_spec` + 迁移 `0002`；`spec/dims.py`、`spec/schema.py`；`config/spec.yaml`（进 `StudioConfig.spec`）；`GET /series/{id}`、`GET/PUT /series/{id}/spec`（409 `spec_locked`、`confirmed_impact`）、`GET /spec/presets`（含 `safe_areas`）；`studio/demo.py:seed_demo()` Mock 启动时执行 | a4aae06 | pytest 142 通过；ruff、mypy 通过 |
| 2 | `spec/compat.py` + `GET /series/{id}/spec/compat?aspect=`；行由 `spec.yaml:compat_stages` 定、按解析后的路由取模型、按 `caps`（`aspects`、`max_short_edge`）判；`comfy/h3` 等补 caps；新文案 `compat.how.native` | 9b21f0d | pytest 151 通过（5 种画幅和 MSW 逐行一致）；ruff、mypy、web test 通过 |
| 3 | 删 MSW 的 series / spec / presets / compat handler；`/impact/apply` 的 `spec_aspect` 用 `put()` 写真实后端；同步页尺寸读真实规格；`test/backend.ts` 加 `fake.series` / `fake.spec`；Spec、AppShell、mocks 测试改走它；冒烟加「锁定后改画幅 → 刷新仍保留」；spec 两张截图重截，无变化 | 24f1a5d | web test 164、lint、typecheck、format 通过；e2e 14 通过；pytest 151 |
| 4a | `setup/manifest.py`（解析、平台覆盖、`fix` / `if_missing`、成环 / 重复 id 校验）、`setup/probe.py`（Real / Fake）、`setup/detectors.py`（12 种检测器 + `finish()`）；夹具 `tests/fixtures/setup/{pc,mac}.yaml`；新文案 found 9 个、fix 4 个；DECISIONS 记 4a | 本提交 | pytest 211（PC 9/9/2/8/1、Mac 6/3/4/7/8 逐行对照）；ruff、mypy、i18n 通过 |

## 下一步

- **第 4b 步（第 4 步的后半，做完勾第 4 步）**：表 `machine_profile`、`installed_item` + 迁移 `0003`；`setup/scan.py`：按 `for_platform()` 顺序逐项 `detect_item()`，每项发 `setup.progress`，结束写推荐（5090 → balanced / `local_video`；无 CUDA → balanced / `no_cuda`）；`setup.scan` 任务；`POST /setup/scan`、`GET /setup/profile`（加 `simulated`）、`POST /dev/setup/machine`（只在 Mock）。返回形状照 `web/src/api/schemas/setup.ts`；参考 `web/src/mocks/handlers/setup.ts` 的节奏。
  - 待定的小事：Fake 机器的 `envs` 路径（建议 `join(host.home, ".drama-studio/envs")`）；`machine.gpu.name` 去掉 `NVIDIA ` / `GeForce ` 前缀（原型顶栏显示 `RTX 5090`）；`DRAMA_SETUP=real` 或 `DRAMA_MOCK=0` 时用 `RealProbe`。

- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

- 有 `upstream` remote（`binwu1/drama-series-agent`）；Kelvin 已把 `gh` 默认仓库设成 `kelvin78901/AIVideoGenerationAgent`，保险起见 `gh pr` 仍带 `-R`。
- 演示里逐步推进的流程（检测、安装、同步）用 `mocks/events.ts:repeatDemo`；测试把对应的 `demoTiming` 设成 0，所有步骤在一个任务里跑完，不要靠放宽等待时间。
- Kelvin 本机常开着 `start.ps1`（5173 前端 + 8000 后端，Mock 模式），Vite 会热更新，可以直接拿来做浏览器核对；不要往里发真实（非 Mock）调用。
- 示例里的运行延迟在 `mocks/events.ts:demoTiming.runMs`，测试里改成 20 ms（见 `components/products.test.tsx`）；测试要挂 `useEventStream()`（`FakeEventSource`）才收得到 `version.created`。
- **Chromium 新版 `scrollIntoView()` 返回 Promise**：`useEffect(() => el.scrollIntoView())` 这种箭头表达式会把 Promise 当清理函数，整页白屏（jsdom 里测不出来）。effect 一律写花括号；滚动日志用容器的 `scrollTop`。
- 页面里有演示事件驱动的长流程时，用临时的 `e2e/tmp-*-shots.spec.ts`（`--project=shots` 能匹配）在真浏览器里走一遍、截图到 scratchpad，跑完删掉。
- Playwright 冒烟收尾时后端会打印 aiosqlite「Task was destroyed but it is pending」，不影响结果，还没查（后端本步没改）。
- MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。

- **本机应用控制策略拦 `.venv/Scripts` 里 uv 生成的入口 exe**（`pytest.exe`、`mypy.exe` 报 os error 4551，`ruff` 不受影响）：一律 `uv run --no-sync python -m pytest` / `python -m mypy`。
- **本机 PowerShell 执行策略禁止 `-File` 跑脚本**：钩子、状态栏、`start.ps1` 都要 `powershell -NoProfile -ExecutionPolicy Bypass -File …`。
- 写接口（非 GET）要带 `X-Drama-Studio: 1`，Host 必须是 127.0.0.1 / localhost；`TestClient` 要用 `base_url="http://127.0.0.1"`。
- **Kelvin 开着 `start.ps1` 时 `uv run` 会失败**（同步要替换正被占用的 `.venv/Scripts/drama-studio.exe`）：一律 `uv run --no-sync …`。
- Windows 上 `python` 不在 PATH（会跳到应用商店），一律 `uv run python`。
- pnpm：`corepack enable --install-directory ~/bin pnpm`；命令前加 `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` 避免首次下载提示。
- Windows PowerShell 5.1：`.ps1` 必须存成 UTF-8 带 BOM，否则中文乱码。
- YAML 1.1 会把 `on:` / `mode: off` 解析成布尔值：`core/config.py` 用只认 true/false 的加载器。
- SQLite 读回时间会丢时区，用 `models_db.UtcDateTime`。

## 等 Kelvin 的事

- **重启 `start.ps1`**：本机 8000 的后端是旧代码（没开 `--reload`），前端热更新后顶栏和成片规格页读不到 `/series`、`/spec`，重启后会自动迁移数据库并建示例剧集。

- 审阅并合并 PR #2。
- 按 `reports/M0.5.md`「怎么验证」在本机点一遍，切中英和亮暗；看 `reports/ui/README.md` 的「有意的差异」。
- 验证钩子（M0 遗留）：接受工作区信任后，确认状态栏和 `/clear` 后的 PROGRESS 注入。

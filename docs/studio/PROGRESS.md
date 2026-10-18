# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M1 首次启动 + 成片规格**（M0.5 已合并，报告 [`reports/M0.5.md`](reports/M0.5.md)）
- 计划：[`docs/studio/plans/M1.md`](plans/M1.md)（已批准 2026-10-15；Kelvin 的四个决定见 DECISIONS「2026-10-15 · M1 计划」；2026-10-18 按 SPEC 6.4 追加 4c、5c、7b，剩下的顺序 **6 → 4c → 5c → 7 → 7b → 8 → 9**）
- 分支：`m1-setup-spec`（从 main 切出；每步提交后 push；不推 main；做完开 PR）

## 已完成的小步

| 步 | 做了什么 | 提交 | 测试 |
| --- | --- | --- | --- |
| 0 | 开分支；计划存档 `plans/M1.md`；ROADMAP 加 M1 计划链接和「环境与安装」入口一项；DECISIONS 记 M1 的决定 | 3703675 | 仅文档 |
| 1 | 表 `series`、`output_spec` + 迁移 `0002`；`spec/dims.py`、`spec/schema.py`；`config/spec.yaml`（进 `StudioConfig.spec`）；`GET /series/{id}`、`GET/PUT /series/{id}/spec`（409 `spec_locked`、`confirmed_impact`）、`GET /spec/presets`（含 `safe_areas`）；`studio/demo.py:seed_demo()` Mock 启动时执行 | a4aae06 | pytest 142 通过；ruff、mypy 通过 |
| 2 | `spec/compat.py` + `GET /series/{id}/spec/compat?aspect=`；行由 `spec.yaml:compat_stages` 定、按解析后的路由取模型、按 `caps`（`aspects`、`max_short_edge`）判；`comfy/h3` 等补 caps；新文案 `compat.how.native` | 9b21f0d | pytest 151 通过（5 种画幅和 MSW 逐行一致）；ruff、mypy、web test 通过 |
| 3 | 删 MSW 的 series / spec / presets / compat handler；`/impact/apply` 的 `spec_aspect` 用 `put()` 写真实后端；同步页尺寸读真实规格；`test/backend.ts` 加 `fake.series` / `fake.spec`；Spec、AppShell、mocks 测试改走它；冒烟加「锁定后改画幅 → 刷新仍保留」；spec 两张截图重截，无变化 | 24f1a5d | web test 164、lint、typecheck、format 通过；e2e 14 通过；pytest 151 |
| 4a | `setup/manifest.py`（解析、平台覆盖、`fix` / `if_missing`、成环 / 重复 id 校验）、`setup/probe.py`（Real / Fake）、`setup/detectors.py`（12 种检测器 + `finish()`）；夹具 `tests/fixtures/setup/{pc,mac}.yaml`；新文案 found 9 个、fix 4 个；DECISIONS 记 4a | 9eeb480 | pytest 211（PC 9/9/2/8/1、Mac 6/3/4/7/8 逐行对照）；ruff、mypy、i18n 通过 |
| 4b | 表 `machine_profile`、`installed_item` + 迁移 `0003`；`setup/schema.py`、`setup/service.py`（`SetupService`：档案、`setup.scan` 任务、`run` 令牌、示例机器切换）；`GET /setup/profile`（`simulated`）、`POST /setup/scan`（202）、`POST /dev/setup/machine`；清单加 `recommend:`；勾 ROADMAP 第 1、4、5、6 项（第 1–3 步当时漏勾） | 46ba9fa | pytest 222（setup 接口 10 个）；ruff、mypy 通过；临时后端 8771 上 curl 走通 |
| 5a | `setup/installer.py`（`FakeRunner`、`install_order`、`confirm_reasons`、`InstallError`）；`SetupService` 加 `setup.install` 任务、依赖跳过、重试 / 跳过、确认 / 取消、重启续跑；`POST /setup/install`、`/setup/install/confirm|cancel`、`/setup/items/{id}/retry|skip`；清单加 `size_gb`、pkg 的 `admin`；新文案；e2e `Backend` 挪进 `tests/e2e/conftest.py` | e239238 | pytest 238（安装接口 11、installer 4、e2e 续跑 1）；ruff、mypy、i18n 通过 |
| 5b | `setup/steps.py`：`RealRunner`（7 种步骤、幂等、装前先检测、镜像、`.part` 续传 + sha256）替掉临时 runner；新文案 error 9 个、log 2 个；另修 CI：Linux mypy（ad8cf79）、corepack 的 pnpm 版本（0ba5732）；勾 ROADMAP 安装器一项 | 5ab627c | pytest 261（steps 22）；ruff、mypy（含 `--platform linux`）通过；CI（Linux）全绿 |

## 下一步

- **第 6 步 能力过滤和推荐（后端）**：`providers.yaml` 的本地模型加 `needs: [清单项 id…]` 和 `requires_cuda`；新文件 `core/capabilities.py`：按 `machine_profile`（`SetupService` 的 `local` / `demo` 档案）和 `installed_item` 算出哪些本地模型可用；`resolve()` 遇到本地跑不了的组件把 `local` / `hybrid` 降成 `api`。测试：Mac 扫描后视频、关键帧、超分的生效方式是 `api`（验收第 3 条）；5090 装好后保持 hybrid / local。从 `core/config.py:resolve()` 和 `config/providers.yaml` 的本地模型开始看。
  - 收尾时 SPEC 9.1 要补：`POST /dev/setup/machine`、`/setup/install/confirm|cancel`、profile 的 `simulated`、`install.confirm`。

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
- e2e 偶发过一次失败（2026-10-18，两条 e2e 一起跑，按耗时推断是 M0 的 `test_restart_resume`），之后连跑 17 次没复现，CI 上留意。
- Playwright 冒烟收尾时后端会打印 aiosqlite「Task was destroyed but it is pending」，不影响结果，还没查（后端本步没改）。
- MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。

- **改 `setup/` 这类带平台分支的代码后加跑 `python -m mypy --platform linux`**：CI 是 Linux，Windows 上的 mypy 看不出 `subprocess.CREATE_NO_WINDOW` 这类只在 Windows 有的名字。
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

- **ComfyUI 端口**：Kelvin 装的是 Desktop 版、便携版还是 git 克隆？跑在哪个端口？（Desktop 默认端口可能是 8000，和后端冲突；4c 要用到）
- **重启 `start.ps1`**：本机 8000 的后端是旧代码（没开 `--reload`），重启后自动迁移到 `0003`（剧集、规格、机器档案）并建示例剧集。首次启动页在第 7 步之前仍用 MSW 示例数据，后端的 `/setup/*` 可以用 `curl` 或 `/docs` 先看。
- 按 `reports/M0.5.md`「怎么验证」在本机点一遍，切中英和亮暗；看 `reports/ui/README.md` 的「有意的差异」。

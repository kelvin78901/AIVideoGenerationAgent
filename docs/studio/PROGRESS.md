# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M1 首次启动 + 成片规格**（M0.5 已合并，报告 [`reports/M0.5.md`](reports/M0.5.md)）
- 计划：[`docs/studio/plans/M1.md`](plans/M1.md)（已批准 2026-10-15；Kelvin 的四个决定见 DECISIONS「2026-10-15 · M1 计划」；2026-10-18 按 SPEC 6.4 追加 4c、5c、7b，剩下的顺序 **7 → 7b → 8 → 9**（6、4c、5c 已做完））
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
| 6 | `core/capabilities.py`（`Capabilities`、`restrict`）；`providers.yaml` 本地模型加 `needs` / `requires_cuda`；`resolve(caps=)` + `Resolved.unavailable`；档案存 `found`（扫描结束写、装好追加），`SetupService.capabilities()` 接进 `Router` 和兼容表；勾验收第 3 条；DECISIONS 记第 6 步 | c13867e | pytest 273（capabilities 单元 9、接口 3）；ruff、mypy（含 `--platform linux`）通过 |
| 4c | `setup/comfy.py`（Desktop 2 安装记录、argv 对安装、节点包 git / Registry / 手动、Python / PyTorch / Manager 版本、模型目录和文件、`identify()`）；`setup/pathutil.py`；探针加只读 `list_dir`，Fake 加 `sizes`；试端口 8188、8000；表 `comfy_env` + 迁移 `0004`；档案存 `comfy`；`GET /comfy/env`；PC 夹具补两个节点包、`extra_model_paths.yaml`、模型文件；勾 ROADMAP 一项；DECISIONS 记 4c | 37170f7 | pytest 285（comfy 单元 9、接口 3；RealProbe 在临时目录按 Desktop 2 布局读，前后文件快照一致）；ruff、mypy（含 `--platform linux`）通过；本机只读试跑结果和手查一致 |
| 5c | `setup/snapshots.py`（Manager 4 的 `/v2/snapshot/*`，按本机 4.2.2 源码核对；Fake）；`Item.touches_comfy` / `snapshot_first`，清单加 `comfy_manager`（检测 + 安装，缺 Manager 时自动排第一）；`install.confirm` 先列 `comfy_change` 改动清单；第一个改 ComfyUI 的项开始前存快照，存不成这些项就不装；表 `comfy_snapshot` + 迁移 `0005`；`GET/POST /comfy/snapshots`、`POST /comfy/snapshots/{id}/restore`；新文案 error 5 个、log 2 个、confirmReason 1 个；PC 示例补 Manager 4；DECISIONS 记 5c | bbf65ce | pytest 293（snapshots 单元 3、接口 5；续跑 e2e 加「快照只存一次」）；ruff、mypy（含 `--platform linux`）、web i18n、prettier 通过 |
| 7（1/3） | 后端：没找到 ComfyUI 时 Manager 排在要装的 ComfyUI 后面（修 5c）；`tests/api/test_web_fixtures.py` 导出 Mock 后端回答到 `web/src/test/data/setup.json`（`DRAMA_UPDATE_FIXTURES=1` 重新生成） | a5a5ea6 | pytest 295 |
| 7（2/3） | zod 补字段、`schemas/comfy.ts`、hooks；`test/setupBackend.ts`（假后端，读上面的 JSON）；Setup 页：确认弹窗 `setup/ConfirmInstall.tsx`、「你的 ComfyUI」`setup/ComfyPanel.tsx`（识别结果、快照、回滚）、改 ComfyUI 的项默认不勾；删 MSW setup handler；DECISIONS 记第 7 步 | cdce398 | web test 178 |
| 7（3/3） | 导航「环境与安装」+「缺 N 项」；`/` 没扫描过跳 `/setup`；弹窗 / 导航不换行；切示例机器清快照（后端）；Playwright 后端改 `python -m`；e2e 加完整流程和导航；全部页面重截（侧栏变了）+ `setup-confirm`、`setup-done` 两张；勾计划第 7 步、ROADMAP 4 项；之后 `start.ps1` 也改 `python -m`（5a86c26） | 5c6e0b9 | pytest 295；web test 183、lint、typecheck、format；e2e 16；ruff、mypy（含 linux） |
| 7b（设计稿） | 工作流库先做出来给 Kelvin 审：`schemas/workflows.ts`、`hooks/workflows.ts`、MSW `handlers/workflows.ts` + 示例 5 个（H3、SeedVR2 推荐；LatentSync 我的；Wan 绑定待确认；Flux Kontext 缺 2 节点包 1 模型）；`pages/models/{WorkflowLibrary,WorkflowDetail,ImportWorkflowDialog}.tsx`、`workflowStatus.ts`；`ConfirmInstall` 加 `snapshotNote`；词表 `workflows.json`、错误码 9 个；审阅图 `reports/ui/workflows/` | 本提交 | web test 183、lint、typecheck、format |

## 下一步

- **第 7b 步（等 Kelvin 审设计稿）**：界面已按 M0.5 风格做完（中英文），审阅图在 `docs/studio/reports/ui/workflows/`。Kelvin 同意后：Vitest（列表筛选、展开、确认绑定、装缺的依赖走确认弹窗、试跑后升档、导入）、Playwright 冒烟加一条、重截 models 两张、DECISIONS 记 SPEC 9.1 里没有的接口（`GET /comfy/workflows`、`POST /workflows/{id}/deps`、`/deps/install`）和试跑轮询（M5 换成任务事件）、勾计划 7b 和 ROADMAP。Kelvin 要改就先改界面再补测试。
  - 收尾（第 9 步）SPEC 要补：9.1 的 `POST /dev/setup/machine`、`/setup/install/confirm|cancel`、profile 的 `simulated`、`install.confirm|changes|snapshot|snapshot_error`、`GET /comfy/env`、`/comfy/snapshots*` 的返回结构；第 4 节 `comfy_env` 的 `comfyui_commit` 列；16.1 的 `/` 跳转规则和导航「环境与安装」。

- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
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
- **示例机器切换**：点已选中的那台不会触发切换；e2e 里切 Mac 再切回 PC 要等前一次 `aria-checked` 变了再点。
- MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。

- **能力过滤在 Mock 下也生效**：扫描示例机器后路由会变（PC 示例装好之前视频、关键帧、超分走 API，兼容表没有 `video_draft` 行；没扫描过不过滤）。第 7 步 Setup 页接真实接口后，e2e 里如果先扫描再看成片规格页，兼容表的预期要跟着改。
- **改 `setup/` 这类带平台分支的代码后加跑 `python -m mypy --platform linux`**：CI 是 Linux，Windows 上的 mypy 看不出 `subprocess.CREATE_NO_WINDOW` 这类只在 Windows 有的名字。
- **本机应用控制策略拦 `.venv/Scripts` 里 uv 生成的入口 exe**（`pytest.exe`、`mypy.exe`、`drama-studio.exe` 报 os error 4551，`ruff` 不受影响）：一律 `uv run --no-sync python -m pytest` / `python -m mypy`；后端用 `python -m drama_series_agent.studio_cli dev`（`start.ps1`、Playwright 已改）。
- **本机 PowerShell 执行策略禁止 `-File` 跑脚本**：钩子、状态栏、`start.ps1` 都要 `powershell -NoProfile -ExecutionPolicy Bypass -File …`。
- 写接口（非 GET）要带 `X-Drama-Studio: 1`，Host 必须是 127.0.0.1 / localhost；`TestClient` 要用 `base_url="http://127.0.0.1"`。
- **Kelvin 开着 `start.ps1` 时 `uv run` 会失败**（同步要替换正被占用的 `.venv/Scripts/drama-studio.exe`）：一律 `uv run --no-sync …`。
- Windows 上 `python` 不在 PATH（会跳到应用商店），一律 `uv run python`。
- pnpm：`corepack enable --install-directory ~/bin pnpm`；命令前加 `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` 避免首次下载提示。
- Windows PowerShell 5.1：`.ps1` 必须存成 UTF-8 带 BOM，否则中文乱码。
- YAML 1.1 会把 `on:` / `mode: off` 解析成布尔值：`core/config.py` 用只认 true/false 的加载器。
- SQLite 读回时间会丢时区，用 `models_db.UtcDateTime`。

## 等 Kelvin 的事

- **审第 7b 步设计稿**：`docs/studio/reports/ui/workflows/` 下 10 张（列表、各种状态的展开、装依赖的确认弹窗、导入）。
- （2026-10-18 已办：`start.ps1` 改 `python -m` 后本机能起；第 7 步的两张新界面截图 Kelvin 审核通过。）
- 按 `reports/M0.5.md`「怎么验证」在本机点一遍，切中英和亮暗；看 `reports/ui/README.md` 的「有意的差异」。

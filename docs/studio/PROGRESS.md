# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M1 首次启动 + 成片规格**（M0.5 已合并，报告 [`reports/M0.5.md`](reports/M0.5.md)）
- 计划：[`docs/studio/plans/M1.md`](plans/M1.md)（已批准 2026-10-15；Kelvin 的四个决定见 DECISIONS「2026-10-15 · M1 计划」；2026-10-18 按 SPEC 6.4 追加 4c、5c、7b，剩下的顺序 **7 → 7b → 8 → 9**（6、4c、5c 已做完））
- 分支：`m1-setup-spec`（从 main 切出；每步提交后 push；不推 main；做完开 PR）

## 已完成的小步

| 步 | 做了什么 | 提交 | 测试 |
| --- | --- | --- | --- |
| 0–3 | 分支和计划存档；表 `series`、`output_spec` + 迁移 `0002`，规格接口和预设；`spec/compat.py` 兼容表；前端规格页改走真实后端（删 MSW handler、`test/backend.ts` 加 `fake.series` / `fake.spec`） | 3703675、a4aae06、9b21f0d、24f1a5d | pytest 151；web test 164；e2e 14 |
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
| 7b（设计稿） | 工作流库先做出来给 Kelvin 审：`schemas/workflows.ts`、`hooks/workflows.ts`、MSW `handlers/workflows.ts` + 示例 5 个（H3、SeedVR2 推荐；LatentSync 我的；Wan 绑定待确认；Flux Kontext 缺 2 节点包 1 模型）；`pages/models/{WorkflowLibrary,WorkflowDetail,ImportWorkflowDialog}.tsx`、`workflowStatus.ts`；`ConfirmInstall` 加 `snapshotNote`；词表 `workflows.json`、错误码 9 个；审阅图 `reports/ui/workflows/` | d7a45b0 | web test 183、lint、typecheck、format |
| 7b | Kelvin 审过设计稿；Vitest `pages/models/WorkflowLibrary.test.tsx`（8 条：列表和筛选、推荐档只读、猜的绑定 → 确认 → 试跑 → 升档、装依赖走确认弹窗、从 ComfyUI 列表导入、拖入 JSON、降档、英文）；Models 测试只数组件表的行；冒烟加工作流库一条；重截 models 两张；DECISIONS 记 7b；勾计划 7b、ROADMAP 一项 | 8bd178f | web test 191、lint、typecheck、format；e2e 17 |
| 8 | 清单补齐：ComfyUI 锁 v0.42.1、最低 0.35.0；H3 / Fun ControlNet 是 ComfyUI 自带节点（`detect.native_since`，不再是安装项）；Manager 改 `manager_requirements.txt` 装法；VHS、SeedVR2、FlashVSR 锁 commit；PyTorch cu130 源；国内 GitHub 走 gh-proxy；权重 `installable: false` + `weights_pending_p0`；改动清单显示 tag / 短 commit；`scripts/setup_scan_real.py`（只读，本机跑过）；测试不再触网；前端测试数据重新导出、Setup / 冒烟数字跟着改；DECISIONS 记第 8 步 | dd2fcce | pytest 296；ruff、mypy（含 linux）；web test 191、lint、typecheck、format；e2e 17 |
| 8b（1/2） | Kelvin 选了 Qwen-Image-Edit-2511 int8、ComfyUI 自带 SeedVR2 + 7B int8、IndexTTS-2.5；五项权重锁 HF revision、填大小和 sha256（共约 110 GB，H3 补两个加速 LoRA）；`node_seedvr2` 改成 ComfyUI 自带（0.28.0 起）；DramaStudio 节点包不可装；download 文件加 `folder:`，放进 ComfyUI 的默认模型目录（`is_default`，Desktop 的共享目录）；新检测 `downloads`；日志 `download`；`setup_scan_real.py` 打印权重目标路径（本机核对过）；前端测试数据重新导出、Setup / 冒烟 / API 测试数字跟着改；DECISIONS 记 8b | e19f60f | pytest 300；ruff、mypy（含 linux）；web test 191、lint、typecheck、format；e2e 17 |
| 8b（2/2） | Kelvin 真装：VHS、FlashVSR、四项权重成功；IndexTTS 从仓库挪到默认位置；回滚第一次被 Manager 的 Windows bug 卡住，修复（回滚前建 `.disabled`）后第二次成功，再装回 VHS、FlashVSR；装完复检（`not_detected`）；SageAttention 在 Windows 上改用预编译包 + 按 torch 选的 triton-windows（`by_torch`、`torch_unsupported`）；git 关 detached HEAD 提示；DECISIONS 记真装结果 | dfe9908 | pytest 单元 218、API 84、e2e 2；ruff、mypy（含 linux）；web test 191、lint、format |
| 8b（收尾） | 用新代码重启后端后装 SageAttention：torch 2.12.1+cu130 配 triton-windows 3.7.1 + sageattention 2.2.0，在 5090 上跑通（和 SDPA 余弦 0.99927）；Kelvin 重启 ComfyUI 后 VHS、FlashVSR、SageAttention 都加载；勾计划 8b、ROADMAP 验收两条 | 2204067 | 仅文档（代码同 dfe9908） |
| 8c（1/4） | `setup/download.py`：按字节计量（每秒最多报一次，速度取最近 5 秒，校验中）；64 MB 分块多连接（动态分段，`.part.json` 记录续传，单块重试 3 次，不支持 Range 退回单连接，老 `.part` 的整块算数，Windows 稀疏文件）；连接数自适应 `Tuner`；`steps.py` 开始前探测一项所有文件的大小；`ItemInstall` 加 `bytes_done` / `bytes_total` / `speed` / `eta_s` / `verifying`；真实 HF 手动核对过；DECISIONS 记 8c（1/4） | 本提交 | pytest 317（download 13）；ruff、mypy（含 linux） |

## 下一步

- **第 8c 步 安装进度、预计用时、多连接下载**（`plans/M1.md` 8c，分四次提交，计划里有复选框）。下一个是 **2/4 后端预估**：档案存实测速度 `download_bps`（装完一项按 `Installed.bps` 记；没有就在扫描时测一小段，`download.measure_speed`，Fake 机器从夹具读）；`SetupItem` 加 `size_bytes`（清单 `size_gb`）和 `work_s`（git clone、pip 等的经验用时）；`FakeRunner` 的权重项也报字节（演示用）。从 `setup/service.py:_scan_job` 和 `setup/installer.py:FakeRunner` 开始。之后 3/4 前端、4/4 安装位置提示和回滚后核对。
- **第 9 步 收尾**：按计划第 9 步做。ROADMAP 勾选（验收「5090 真实扫描和实际一致」「ComfyUI 识别和 Kelvin 机器一致」等 Kelvin 看过 `scripts/setup_scan_real.py` 的输出再勾）；SPEC 补：9.1 的 `POST /dev/setup/machine`、`/setup/install/confirm|cancel`、profile 的 `simulated`、`install.confirm|changes|snapshot|snapshot_error`、`GET /comfy/env`、`/comfy/snapshots*`、`GET /comfy/workflows`、`/workflows/{id}/deps*`；第 4 节 `comfy_env` 的 `comfyui_commit`；12.1 清单的 `native_since`、`version`、`installable: false`、download 文件的 `folder:` 和检测 `downloads`（12.1 的 SeedVR2 示例改成 ComfyUI 自带）、`ModelDir.default`；16.1 的 `/` 跳转和导航「环境与安装」；6.4.3 的 `video_in` 槽位。写 `reports/M1.md`（中文，给 Kelvin），跑 CI（Linux；Windows 在开 PR 时跑），`gh pr create -R kelvin78901/AIVideoGenerationAgent --base main`，PR 描述用报告。

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

- （2026-10-18 已办：第 8b 步真装、回滚、SageAttention 都做完，ComfyUI 已带 `--use-sage-attention` 启动（改的是 Desktop 的 `installations.json`，原文件备份在当时会话的 scratchpad）；真实扫描输出 Kelvin 看过、和我这边一致；8b 的三个版本已选；`start.ps1` 改 `python -m` 后本机能起；第 7 步的两张新界面截图、第 7b 步设计稿 Kelvin 审核通过；按镜头选工作流 / 拼节点 beta 已定，见 DECISIONS 和 SPEC 6.4.8。）
- 按 `reports/M0.5.md`「怎么验证」在本机点一遍，切中英和亮暗；看 `reports/ui/README.md` 的「有意的差异」。

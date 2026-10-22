# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M4 分镜与动态分镜**，计划 [`plans/M4.md`](plans/M4.md)（Kelvin 2026-10-21 批准，定的四项见 DECISIONS 2026-10-21「M4 计划」）。M3 已合并（PR #5），报告 [`reports/M3.md`](reports/M3.md)。
- 分支：`m4-storyboard`（从 main fb08576 开出）。

## 已完成的小步

- M3 合并之后（5b3de78）：M2 剧本不调提示词、不开思考；SSE 测试的服务器最多等 30 秒启动。
- 第 0 步（2d9d3de）：存计划 `plans/M4.md`；DECISIONS 记 Kelvin 定的四项和不在 M4 做的；ROADMAP 两条验收注明「9 张关键帧」实际是 7 张（1-08、1-09 接尾帧）。只改文档。
- 第 1 步（052ef9b，DECISIONS「M4 第 1 步」）：迁移 `0018` 表 `shot`（`models_db.Shot`）；`Component.cascade_rerun`；流水线顺序加 `shot_plan` / `keyframe`（归「分镜」）；`timing.shot_duration`、`longest_take_s`；词条 `enums.durationSource`。前端槽位、owner `shot`、镜头枚举 M0.5 已有。`tests/unit/test_timing.py` 6 个；全量 pytest 668 个、vitest 278 个过；ruff、mypy（含 linux）干净。
- 第 2 步（本提交，DECISIONS「M4 第 2 步」）：组件 `plan`（`pipeline/components/plan.py`，`cascade_rerun = False`）、规则 `shots/ops.py`（补齐覆盖、插入镜头、接尾帧、id 沿用、拆分合并、改字段）、`shots/service.py`（读当前版本、时长现算、物化 + 关键帧产物、`ensure_plan`）、接口 `api/routes/shots.py`；剧本切片 `shots`（只有结构、不含文字，按 Kelvin 定第 3 项）、素材清单切片 `ids`；影响范围新行 `stale_shot_plan` / `then_shot_plan`，「确认并同步」估价不算级联不跑的产物（`component.reruns_in_cascade`）；`on_adopt` 可挂多个；`scene_numbers` 挪到 `episodes.service`；`shot_count`；示例种子 `plan.json`；导出 `web/src/test/data/shots.json`。前端契约 `scene_label` → `scene_no` / `scene_place`，加 `seed_changed`、`min_s`、`planned_s`、`manual_s`、`longest_s`、`split_hint`；MSW 镜头只管示例第 1 集。新测试 `tests/unit/test_shot_ops.py` 9 个、`tests/api/test_shots_api.py` 7 个；全量 pytest 676 个、Playwright e2e 34 个、vitest 278 个过；ruff、mypy 干净。

## 下一步

- **第 3 步 关键帧（后端，Mock）**（计划「小步」3）。**已起草、没提交**（见下「没提交的改动」）：`pipeline/components/kf.py`（`gather`、`pick_refs`、`ref_limit` 按工作流的 `ref_image` 槽数、`blocking_text`、`stale_aspect`、`KfComponent`）、模板 `prompts/templates/kf/default.j2`、测试 `tests/api/test_keyframes_api.py`（8 个，现在会失败）。还要做：
  1. `pipeline/components/plan.py` 加 `shot_plan_slicer`（`shot:<id>` = scene_id、shot_type、framing、camera_move、blocking、asset_ids、line_ids、tail_from），在 `api/state.py` 和 `studio/demo.py:slicers()` 登记；`state.py` 加 `KfComponent`。
  2. `Invalidation` 加按槽位的额外检查（`check(slot, fn)`，`stale_ids` 里对显示的版本调用），`keyframe` 登记 `kf.stale_aspect`。
  3. `Component._call_ctx` 带 `shot_id`（owner 是镜头时）。
  4. `shots/service.py`：确认 = `lock_pick`（当前版本 + 选中那张）+ `GateDecision(gate="shot", scope_id=镜头 id, hashes={分镜规划: shot 切片哈希, 关键帧: 锁定哈希})`，没版本 409 `nothing_to_confirm`，已锁定（待更新后再确认）只记新决定；连续动作只记决定；取消确认 = 解锁 + `reopen`；已确认的镜头改任何字段 409 `shot_confirmed`（第 4 步接影响范围）；`ShotOut` 加 `confirm_stale`（前端 zod 一起加）；`confirmed` 读最后一条决定。`on_adopt("keyframe")` 加 `lock_spec`：`locked_at` 为空就写。
  5. 示例：`_seed_plan` 前先用固定 id `demo-p-kf-1-0X` 建 7 个关键帧产物；`_seed_keyframes`：1-01–1-03 本地草稿（3 张，10:55）+ Nano Banana Pro 终版（1 张，11:02，$0.14）并确认，1-04–1-07 草稿（11:06）；用 `kf.gather` + `kf.pick_refs` 算依赖。重导 `shots.json`（含关键帧产物）。
- **提醒 Kelvin 重启后端并 `demo --reset`**（第 1 步加了迁移 `0018`，第 2 步加了示例分镜）：`uv run --no-sync python -m drama_series_agent.studio_cli demo --reset`。不重启的话热更新后的前端读旧后端，会报「接口返回的数据和约定不符」。
- **`start.ps1` / `start.sh` 默认真实检测**（`-RealSetup` 默认开，Kelvin 2026-10-21 定；`-RealSetup:$false` / `--no-real-setup` 换回示例机器）。直接 `drama-studio dev` 和测试仍是 Mock 即示例机器。
- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（M2 计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。heredoc 里 Python 字符串的 `\n` 会被写成真换行：要写进代码的 `\n` 用 Edit 工具。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
- 截图：`pnpm -C web shots -g "<page> (light|dark)"`（只写 `-g <page>` 时 `spec` 会匹配到文件名 `shots.spec.ts`，把所有页都截一遍），然后填 `reports/ui/README.md` 对照表那一行。`assets-views` 和 `assets` 是同一张（默认选中林晚），截完复制一份。

## 没提交的改动

- 第 3 步的草稿（没接线、没进 git）：`src/drama_series_agent/pipeline/components/kf.py`、`src/drama_series_agent/prompts/templates/kf/default.j2`、`tests/api/test_keyframes_api.py`。在它们接好之前，全量 pytest 里 `test_keyframes_api.py` 会失败。

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

- 看截图（原型没有的部分，都在 `reports/ui/`）：第 4 步 `assets-{draft,views,matrix}`；第 5 步 `assets-{text,text-composite,ocr-confirm}`（Mock 的图不真画字）；第 6 步 `assets-voice-{final,drafts}`；第 15 步重截的 `assets-views`（6 张视图）；第 7、8 步 `assets-dub-{confirm,voice}`、`script-dub{,-table,-impact}`、`assets-{gate-refused,edit-locked}`；第 10 步 `spec`（兼容表两行变「原生支持」）。

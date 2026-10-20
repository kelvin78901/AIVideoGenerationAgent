# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M2 小说 → 剧本**（M1 已合并，PR #3，报告 [`reports/M1.md`](reports/M1.md)）
- 计划：[`docs/studio/plans/M2.md`](plans/M2.md)（已批准 2026-10-19；Kelvin 的四个决定见 DECISIONS「2026-10-19 · M2 计划」）
- 分支：`m2-novel-script`（从 main 切出；不推 main）

## 已完成的小步

- 0–4：分支和计划（7a52479）；产物和版本、迁移 `0007`（1b44c55）；配置接口和预设、`0008`（178c58b）；组件框架、提示词、Mock 应答器、`llm_cache` `0009`（1909823、c2abc3f）；预算和确认、`0010`（dd6382b）。详情见各提交和计划。
- 5–7b：剧集和导入小说（6c130da、10da78b）；设定提取和设定卡（df453aa、9cac19d）；补全和修订视图（e5911aa）；小说逐段编辑（0d48ef9）。详情见各提交、DECISIONS 和计划。
- 8a（后端）：`episode`、`beat`（迁移 `0014`；`episode.budget_usd` 是设置，物化不动它）；`episodes/ops.py`（纯函数：重跑按集号 / 节拍文字沿用 id、改集、改 / 拖节拍、场号区间、切片 `episode:<id>`）、`episodes/service.py`（读已采纳方案、编辑出 `edit` 版本并采纳、进度、物化、本集预算接到 `Budget.episode_budget`）；`pipeline/components/split.py`（原文分块 + 章节摘要 + 设定名字 + 每集时长，跨块同 `ep` 接着写；Mock、`demo_payload`）、模板 `prompts/templates/split/`；`config/spec.yaml:episode_lengths`；接口 `GET /series/{id}/episodes`（每集带 `beats`、`scene_count`）、`PATCH /episodes/{id}`、`PATCH /beats/{id}`（返回整个方案）、`GET /episodes/{id}/progress`；示例种子 `demo-p-split-v1`（`tests/fixtures/demo/split.json`，3 集 22 个节拍，每集 $15）；`test/data/bible.json` 重导（产物列表多了分集规划）。pytest 475、Vitest 223 全过（ce3cc89）。
- 8b（前端）：zod `BeatSchema`、`EpisodeSchema` 加 `beats` / `scene_count`、`EpisodePatch` 加集名 / 钩子 / 卡点 / 时长、`BeatPatchSchema`；`usePatchBeat`（先按新位置显示，失败退回，`lib/beats.ts:patchBeat`）；剧本页「分集」区 `pages/script/Episodes.tsx`（「卡片 / 节拍看板」切换、没有分集时的空状态、只读 / 未采纳提示）、`BeatBoard.tsx`（原生拖放，落点是叠在卡片上的蓝线）、`EmotionCurve.tsx`（SPEC 11.3）、`PlanDialogs.tsx`（改节拍、改集）；RunBar 没有模型的版本写来源；MSW 分集 / 进度读后端再叠加示例数据、删 `PATCH /episodes/:id` 和 `demo-p-split`、顶栏预算读后端；假后端 `test/fakes/episodes.ts` + `test/data/episodes.json`；截图 `script.*.jpg` 重截、新增 `script-board{,-drag,-edit}`。pytest 475、Vitest 234、e2e 17 全过（625b8b8）。
- 9a（后端）：`scene`、`script_line`（迁移 `0015`）；`script/ops.py`（纯函数：第 n 场沿用 id、行按文字 / 同场相似度沿用、视图里场号全剧累加且场标题不含场号、改行 / 改场标题标 `edited`）、`script/service.py`（读当前版本、编辑出 `edit` 版本并采纳、重写只给建议、物化）；`pipeline/components/script.py`（只读本集：`episode:<id>` + 段落所在章 `chapter:<idx>` + 新切片 `adopted:<段号>`、`entities:<id>`；补写编号【补写n】→ `sug:<id>` 出处；名字对上设定 id；重写查单次上限和本集剩余；Mock 应答器 run / rewrite_line / rewrite_scene、`demo_payload`）；模板 `prompts/templates/script/`；接口 `GET /episodes/{id}/script`、`PATCH /lines/{id}`、`PATCH /scenes/{id}`（计划外，记 DECISIONS）、`POST /lines|scenes/{id}/rewrite`；分集规划采纳时 / 启动时给每集建剧本产物；分集卡片「场 x–y」有剧本后按实际场数；`ProductService.append_edit` 合并三处重复；示例种子 `demo-p-script-e1..3`、第 1 集 v1 本地 → v2 Kimi 已采纳（`tests/fixtures/demo/script.json`）；导出 `web/src/test/data/script.json`、`episodes.json` 重导。pytest 496、Vitest 234 全过（e0cccfc）。
- 9b（前端）：zod 场 / 行加 `paras`、`ScriptSchema` 加 `product_id` / `version_id` / `adopted` / `source_id`、场标题不含场号（显示拼「场 N　」）、`ShotSchema.line_ids`；`usePatchBlock`（没确认 → 直接 PATCH）、`useRewriteBlock` 带 `confirm_budget`（超预算在那一段下问「仍然重写」）；三向溯源：剧本行 →「对应镜头」/「来自原文第 N 段」、镜头设定「剧本」栏、小说页点段号「在剧本里」（`pages/novel/ScriptTrace.tsx`），URL 参数 `?line=` / `?shot=` / `?para=`；「未采纳」提示；MSW 删剧本 handler / fixture / 示例剧本产物，`/products?owner=episode:` 合并后端，分集 / 进度只叠加镜头数和演示闸门的「已确认」，影响范围 apply 转发后端 PATCH；`product.updated` 刷新 `["episodes"]`；假后端 `test/fakes/script.ts`；截图 `script.*`、`storyboard.*` 重截，新增 `script-trace`、`novel-trace`、`storyboard-lines`。pytest 496、Vitest 242、e2e 17 全过（86044f7）。
- 10a（后端）：`pipeline/gates.py`（小说闸门 = 本剧小说、设定、补全，前端传集 id 换成剧集；剧本闸门 = 一集剧本；确认锁定已采纳版本并记有效哈希，重新打开解锁，`gate.updated`）；`pipeline/impact.py`（各服务的编辑拆成 `plan_*` → `PlannedChange` + `commit`；预览在会话里试写改动再回滚，用切片哈希找直接受影响的产物，再往下的列为可选；行 `self_/stale_/then_<slot>`、`gate_<gate>`、`edited_<slot>`，带重跑估价；`mark` 解锁写入再锁上，`undo` 丢掉，`rerun` 暂时 422；预览在内存里，过期 409 `impact_outdated`）；八种改动（另加 `bible_merge`）；`dry_run` 导入返回 `upload_id` 给 `novel_replace` 用（zod 跟着加）；接口 `POST /gates/{gate}/confirm|reopen`、`POST /impact/preview|apply`；测试 `tests/api/test_gates_impact_api.py`。pytest 508、Vitest 242 全过（2db3801）。
- 10b（后端）：`pipeline/cascade.py`（确认并同步：任务参数带 `cascade: {id, origin}`，不建表；`JobQueue.on_finished` 钩子触发下一步，启动时 `cascade.resume()` 接着走；一个产物等它上游里流水线更靠前的都处理完再跑，顺序 补全 → 设定 → 分集 → 剧本，同一层并排；每个产物最多跑两次（设定改了名字补全再跑一次），失败的不重试、它下面的不跑；成功且仍是当前版本就采纳，被锁的先重新打开闸门；全部结束发 toast `cascade_done {count, failed}`）；`apply(rerun)` 写入后交给同步、返回第一层的任务；`running.cascade_id`；影响预览行改成补全在设定前；测试 `tests/api/test_cascade_api.py`。pytest 514、Vitest 242 全过（a583549）。
- 10c-1（前端 + 示例闸门）：影响范围弹窗主按钮「确认并同步 · 预计 $x」+「只改这里，下游标待更新」+「撤销」（成片规格页 `primary="mark"` 保留原型顺序）；后端影响行的文案 key（`self_/stale_/then_/edited_<slot>`、`gate_novel|script`）；RunBar「同步中」（`running.cascade_id`，zod 加）、左侧步骤「同步中」（`useJobs.ts:syncingSteps`，看任务列表里带 `params.cascade` 的）；toast `cascade_done` / `cascade_done_failed`；`gate.updated` 刷新产物、剧集、徽章；MSW：闸门 novel / script 放行，影响预览 / 应用转后端（`mocks/backend.ts:backendResponse`）+ 示例第 1 集剧本叠加下游行（`scriptDownstream`、`impactOverlays`），删 PATCH 转发和演示闸门叠加；`seed_demo` 确认小说闸门和第 1 集剧本闸门（只在从没决定过时；后端测试默认不种，`demo_gates` fixture 才种）；前端测试数据重导（锁定、已确认）；假后端 `test/fakes/impact.ts`（闸门、影响预览 / 应用、`reopenFakeNovel()`）。pytest 515、Vitest 246、e2e 17 全过（ec05163）。
- 10c-2（前端）：`components/ImpactGuard.tsx` + `impactGuardContext.ts`（页面包一层，`active` 时编辑先 `/impact/preview`、弹 modal 影响范围，没有行就直接 `mark`）；小说页（小说已确认或有已确认剧本时）：逐段编辑 `novel_edit`、重新导入 `novel_replace`（dry_run 的 `upload_id`）、设定编辑 / 合并 / 拆别名、补全采纳 / 忽略；已确认时「全部采纳」、按要求重写置灰 + 提示；剧本页：拖节拍 / 改节拍碰到已确认剧本时 `beat_move`；`useApplyImpact` 多刷新 `["series"]`；假后端补齐八种（写入走直接编辑的请求）、`openFakeGates()`；Mock 后端上真跑「改原文 → 确认并同步」：4 个产物重跑采纳、两个闸门重新打开；截图 `novel-impact`、`novel-syncing`、`novel-synced`、`script-impact`，`novel.*`、`script.*` 重截。pytest 515（后端没改）、Vitest 255、e2e 17 全过（本提交）。

## 下一步

- **11. 删掉旧界面**（下一步，计划第 11 步）：删 `web/src/legacy/`、`/legacy` 路由和相关配置、词条；后端上游 `/api/series/*` 只剩 `/legacy` 在用，一起摘掉（上游代码和 `drama-series-render` 命令行保留），`tests/unit/test_isolation.py` 跟着改。
- **Kelvin 要重启后端**（9b–10c）：重启后示例剧集会补上「小说已确认」「第 1 集剧本已确认」（只在这两个闸门从没决定过时）；之后在 5173 改原文、设定、剧本行都会弹影响范围。
- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。heredoc 里 Python 字符串的 `\n` 会被写成真换行（第 5 步踩了两次）：要写进代码的 `\n` 用 Edit 工具。Python 写文件要 `open(..., "w", newline="\n")`（`Path.write_text` 在 Windows 上会写成 CRLF）。
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
- **上游 `.gitignore` 有一行 `templates/`**，会挡住任何叫 templates 的目录；`src/drama_series_agent/prompts/templates/` 已用 `!` 放行，新加别的 templates 目录要留意 `git status`。
- **页面测试里上传文件**：`test/setup.ts` 已把 `FormData` / `File` 换成 Node 的（jsdom 的发出去是 `"[object FormData]"`），假后端里 `await request.formData()` 可以直接用。
- **Radix 下拉菜单里打开对话框要 `modal={false}`**，否则对话框关掉后 `body` 留着 `pointer-events: none`（jsdom 里表现为后面的测试点不动）。
- **ESLint `no-irregular-whitespace`**：全角空格（U+3000）在正则、注释里会报错（字符串里不报）——正则写 `\s`，注释别用；**`react-hooks/set-state-in-effect`**：不要在 effect 里同步 URL 参数到 state，在渲染时推出来（见 `Script.tsx` 的 `picked`）。
- **改代码前先看 ruff 有没有已经改过行**：`ruff format` 会把长行拆开，之后用 sed 按原行号替换会留下碎片（第 4 步踩过）。

## 等 Kelvin 的事

- **审第 8 步的节拍看板和情绪曲线**：截图 `reports/ui/script-board.light.jpg`（暗色 `.dark`）、`script-board-drag.light.jpg`（拖动中）、`script-board-edit.light.jpg`（改节拍）；重启后端后在 5173 剧本页点「节拍看板」能直接试拖动。
- **审第 9 步的三向溯源**：`reports/ui/script-trace.light.jpg`（剧本行 → 镜头 / 原文）、`novel-trace.light.jpg`（小说段落「在剧本里」）、`storyboard-lines.light.jpg`（镜头 → 剧本行）；重启后端后在 5173 能点着来回跳。
- **审第 10 步的影响范围和同步**：`reports/ui/novel-impact.light.jpg`（改已确认原文的弹窗）、`novel-syncing.light.jpg`（同步中）、`novel-synced.light.jpg`（同步完）、`script-impact.light.jpg`（剧本页的新按钮）；按钮文案、主按钮放「确认并同步」、已确认时「全部采纳」置灰这几处要你看一眼。
- 之后：第 13 步真实冒烟要 DeepSeek 密钥。
- M1 留下的：下次真装大文件（如 Qwen-Image-Edit 31 GB）时看速度、剩余时间准不准，连接数是否停在 1 个。

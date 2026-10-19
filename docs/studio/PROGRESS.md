# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M2 小说 → 剧本**（M1 已合并，PR #3，报告 [`reports/M1.md`](reports/M1.md)）
- 计划：[`docs/studio/plans/M2.md`](plans/M2.md)（已批准 2026-10-19；Kelvin 的四个决定见 DECISIONS「2026-10-19 · M2 计划」）
- 分支：`m2-novel-script`（从 main 切出；不推 main）

## 已完成的小步

- 0：开分支、存计划、DECISIONS 记 Kelvin 定的四项（7a52479）。
- 1：表 `product` / `product_version` / `dependency` / `gate_decision`（迁移 `0007`）、`pipeline/products.py`（`ProductService`：只追加、第一次才自动采纳、锁定、`on_adopt` 物化钩子）、`/products`、`/versions` 六个接口、`PipelineError`；事件改成只带 id（前端 zod、MSW 同步改）。pytest 339、Vitest 197 全过（1b44c55）。
- 2：`core/config.py:preset_settings()`（四个预设、`off`）、`app_setting`（迁移 `0008`）、`modelhub/catalog.py`、`/config/components|resolve|override|defaults`；`components.yaml` 加单次上限和 `sfx`；删 MSW config handler，剩下的示例 handler 用 `mocks/route.ts:demoRoute()`，页面测试用 `test/fakes/config.ts` + `test/data/config.json`。pytest 350、Vitest 197、e2e 17 全过（178c58b）。
- 3：`pipeline/component.py`（组件协议、`call_json` 校验 + 重试一次 + 缓存）、`pipeline/runs.py`（`product.run` 任务、run / rerun / switch、提示词两层、估价）、`pipeline/invalidation.py`（切片哈希、待更新现算）、`prompts/compiler.py`（Jinja2）、`llm_cache`（迁移 `0009`）、Mock 应答器；接口 `POST /products/{id}/run`、`PUT …/prompt`、`POST …/compile`；依赖 `jinja2`。pytest 357、Vitest 197 全过（1909823；模板被上游 `.gitignore` 的 `templates/` 挡住，c2abc3f 补上）。
- 4：`modelhub/budget.py`（入队前查单次上限和本集剩余、路由器守卫按确认金额放行）、`job.episode_id` / `confirmed_usd`（迁移 `0010`）、`JobNeedsConfirm`、兜底前先问（`NeedsConfirm`）；前端 `components/ConfirmJobs.tsx`（外壳里的确认弹窗）、RunBar「等你确认」。pytest 363、Vitest 201、e2e 17 全过（dd6382b）。
- 5a（后端）：`novel_source`、`chapter`（迁移 `0011`）；`novel/parse.py`（BOM / UTF-8 / GB18030、.docx、按标题切章、没标题按约 6000 字分）、`novel/service.py`（小说是产物 slot `novel`，每次导入一个 `import` 版本直接采纳；同文本不出新版本；锁定 409）；`GET / POST /series`、`PATCH /series/{id}`、`POST /series/{id}/novel`（multipart，`dry_run` 预览）、`GET /series/{id}/novel?chapter=`；`seed_demo()` 按块补示例小说、`drama-studio demo [--reset]`；示例小说 `tests/fixtures/demo/雨停之前.txt`（约 2400 字）；`web/src/test/data/novel.json` 由 `test_web_fixtures.py` 导出；依赖 `python-docx`。pytest 411 全过（6c130da）。
- 5b（前端）：zod `novel.ts`（来源可空、章节、导入结果）、`series.ts`（新建）、`products.ts` 加 slot `novel`；`postForm` 上传；顶栏剧名菜单 `components/SeriesMenu.tsx` + `NewSeriesDialog.tsx`、`pages/NoSeries.tsx`；`/` 进上次的剧集（`stores/ui.lastSeries`、`useSeriesId()`）；小说页导入弹窗 `pages/novel/ImportDialog.tsx`（`dry_run` 预览 → 改编权 → 导入）、空状态、按章切换、跨章定位建议；删 MSW `GET /series/:id/novel`，示例段落偏移取 `test/data/novel.json`；带剧集 id 的 MSW handler 对别的剧集放行；假后端 `test/fakes/novel.ts`、`backend.ts` 加剧集列表 / 新建；截图 `reports/ui/series-menu|novel-import|novel-empty.light.jpg`、小说页重截。Vitest 210、e2e 17 全过（10da78b）。
- 6a（后端）：`bible_entity`（迁移 `0012`）；`bible/merge.py`（纯函数：按名字 / 别名合并、和已采纳版本比对沿用 id、冻结原样留、候选对、patch / merge / distinct / split）、`bible/service.py`（读当前版本、编辑出 `edit` 版本并采纳、物化）、`pipeline/components/extract.py`（按章分块 ≤ 兜底链最小上下文 60%、判定「可能是同一个」、每章摘要、Mock 应答器、`demo_payload`）；接口 `GET /series/{id}/bible`（**改成对象**）、`PATCH /bible/{id}`、`POST /bible/merge`；导入小说 / 启动时补系列级产物；`providers.yaml` 加 `max_context`、本地 `send_num_ctx`；示例 fixture `tests/fixtures/demo/extract.json`，种子 `demo-p-extract-v1`。pytest 429 全过（df453aa）。
- 6b（前端）：zod `BibleSchema` / `MergeSuggestion`、条目加 `paras`；`useBible` 读对象，`useEditBibleEntity`、`useMergeBible`；`BiblePanel` 点卡片在原文标出段落（别的章先切章）、铅笔编辑（`EntityDialog`：名字、别名、简介、冻结、别名拆出来）、「可能是同一个」合并 / 不是同一个、「未采纳」；MSW 删设定数据和设定提取产物，示例剧集的产物列表合并后端的（`mocks/backend.ts`），未知产物 / 版本 id 放行；假后端 `test/fakes/bible.ts` + `test/data/bible.json`；截图 `novel.*.jpg` 重截、新增 `novel-bible{,-marked,-edit}.light.jpg`。Vitest 216、e2e 17 全过（本提交）。


## 下一步

- **第 7 步：小说补全（enrich）+ 修订视图**（计划第 7 步；迁移号顺延成 `0013`：`suggestion`、`suggestion_decision`）。**Kelvin 已定：设定读已采纳的补写**（DECISIONS 2026-10-19 · Kelvin 定）：设定提取的输入加已采纳补写（按段接在原文后，段号不变，意图改回原型那句）、补全对设定只依赖名字和冻结条目的切片（新切片，不循环）。补全组件读小说已采纳版本（`NovelService.book()`，段号同第 6 步）+ 设定已采纳版本（冻结的条目 = 不许改的情节），按章分块照 `extract.chunk_book`；建议带原文锚点（段号 → `Book.span`）；有效哈希只算已采纳的建议。接口 `GET /series/{id}/suggestions`、`POST /suggestions/{id}/accept|reject|reset|rewrite`、`POST /series/{id}/suggestions/accept-all`。前端只换数据源（修订视图已有）；删 MSW 补全部分（`handlers/novel.ts`、`fixtures/demo/novel.ts` 的 suggestions）和 enrich 产物，假后端照第 6 步（`test/fakes/` + 后端导出 JSON）；产物列表的合并已经通用，后端多出 enrich 产物后 MSW 那份要删。
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
- **改代码前先看 ruff 有没有已经改过行**：`ruff format` 会把长行拆开，之后用 sed 按原行号替换会留下碎片（第 4 步踩过）。

## 等 Kelvin 的事

- **重启后端**：第 1–6 步加了迁移 `0007`–`0012` 和 `/products`、`/config/*`、`/series`、`/series/{id}/novel`、`/series/{id}/bible`、`/bible/*` 接口；不重启的话小说页的设定区会报 404。
- **第 6 步可以过目**：`docs/studio/reports/ui/novel-bible.light.jpg`（设定卡 + 「可能是同一个」）、`novel-bible-marked.light.jpg`（点「旧小票」切到第三章、标出 3 段）、`novel-bible-edit.light.jpg`（编辑设定）；示例设定见 `tests/fixtures/demo/extract.json`（18 条，周屿的简介改了）。
- **M2 第 5 步要过目**：示例小说 `tests/fixtures/demo/雨停之前.txt`（3 章约 2400 字，计划写的约 3000 字，要加长就说）；截图 `docs/studio/reports/ui/series-menu.light.jpg`（剧名菜单）、`novel-import.light.jpg`（导入弹窗）、`novel-empty.light.jpg`（新剧集空状态）。之后：第 8 步审节拍看板和情绪曲线的截图；第 13 步真实冒烟要 DeepSeek 密钥。
- M1 留下的：下次真装大文件（如 Qwen-Image-Edit 31 GB）时看速度、剩余时间准不准，连接数是否停在 1 个。

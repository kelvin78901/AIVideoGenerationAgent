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
- 5a（后端）：`novel_source`、`chapter`（迁移 `0011`）；`novel/parse.py`（BOM / UTF-8 / GB18030、.docx、按标题切章、没标题按约 6000 字分）、`novel/service.py`（小说是产物 slot `novel`，每次导入一个 `import` 版本直接采纳；同文本不出新版本；锁定 409）；`GET / POST /series`、`PATCH /series/{id}`、`POST /series/{id}/novel`（multipart，`dry_run` 预览）、`GET /series/{id}/novel?chapter=`；`seed_demo()` 按块补示例小说、`drama-studio demo [--reset]`；示例小说 `tests/fixtures/demo/雨停之前.txt`（约 2400 字）；`web/src/test/data/novel.json` 由 `test_web_fixtures.py` 导出；依赖 `python-docx`。pytest 411 全过（本提交）。

## 下一步

- **第 5b 步：剧集和导入小说的前端**（计划第 5 步的前端部分，做完勾掉第 5 步）。zod：`novel.ts` 的 `NovelSchema` 改成后端的形状（`source` 可空，加 `encoding`、`split_by`、`chars`、`rights_confirmed_at`、`imported_at`；`chapters`、`chapter`）、`NovelImportSchema`；`series.ts` 加列表、新建；`products.ts` 的 `ProductSlotSchema` 加 `novel`（后端的 `/products?owner=series:demo` 现在有小说产物）。`api/client.ts` 加 multipart 上传。页面：顶栏剧名菜单（列表 +「新建剧集…」）、新建弹窗 → 规格页（新剧集显示「下一步：导入小说」）→ 小说页；导入弹窗（选文件 → `dry_run` 预览章节 → 勾改编权 → 导入；已有小说时提示会替换）；没有小说时的空状态；原文按章切换（点其他章的建议要先切章）；`/` 进上次看的剧集（`stores/ui` 记住，`useRouteEpisode` 的默认剧集也用它）。MSW：删 `GET /series/:id/novel` handler，`fixtures/demo/novel.ts` 的段落改从 `test/data/novel.json` 取（偏移从 8 开始，脚本和建议的出处跟着对上）；按「和 MSW 共存」规则，series 级 handler 对不认识的剧集放行到后端。页面测试的假后端 `test/fakes/novel.ts` 读 `novel.json`。i18n 新 key 两种语言。截图（剧名菜单、导入弹窗）给 Kelvin。
- **约定**：改已确认内容先 `useImpactPreview`、后 `useApplyImpact`；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`、PC 示例机器扫描前；`resetFakeSetup("pc", { scanned: true })` 直接到扫描后），看 toast 就挂 `<Toaster />`；演示延迟放 `mocks/events.ts:demoTiming`，测试里改短；AppShell 测试标题要改成页面 h1；i18n key 不能含冒号。
- **和 MSW 共存的规则**（计划「和 MSW 共存」）：MSW 只处理它内存库里有的 id，其他放行到后端；做完一块就从 MSW 库里删掉那块数据；删掉的 handler 挪成 `web/src/test/fakes/` 的测试假后端。
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
- **改代码前先看 ruff 有没有已经改过行**：`ruff format` 会把长行拆开，之后用 sed 按原行号替换会留下碎片（第 4 步踩过）。

## 等 Kelvin 的事

- **重启后端**：第 1–5 步加了迁移 `0007`–`0011` 和 `/products`、`/config/*`、`/series`、`/series/{id}/novel` 接口（`python-docx` 已装好，`start.ps1` 不用再停）。
- M2 第 5 步：过目示例小说（3 章）、审剧集菜单和导入弹窗的截图；第 8 步：审节拍看板和情绪曲线的截图；第 13 步：真实冒烟要 DeepSeek 密钥。
- M1 留下的：下次真装大文件（如 Qwen-Image-Edit 31 GB）时看速度、剩余时间准不准，连接数是否停在 1 个。

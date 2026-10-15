# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M0.5 界面先行**（M0 已完成，PR #1 待 Kelvin 合并；M0 的逐步记录见 [`reports/M0.md`](reports/M0.md)）
- 计划：[`docs/studio/plans/M0.5.md`](plans/M0.5.md)
- 分支：`m0.5-ui`（从 `m0-foundation` 切出；每步提交后 push；不推 main；M0 合并后 rebase 到 main 再开 PR）

## 已完成的小步

| 步 | 做了什么 | 提交 | 测试 |
| --- | --- | --- | --- |
| 0 | 开分支 `m0.5-ui`；计划存档 `plans/M0.5.md`；ROADMAP 加 M0.5（M1–M9 的界面条目注明「接真实接口、删 MSW handler」）；DECISIONS 记 M0.5 的工程决定 | 0444149 | 仅文档 |
| 1 | 依赖（msw 2.14.7、zod 4.6.4、@playwright/test 1.63.0、d3-scale/shape）；`api/schemas/`（common、jobs、series；`api/types.ts` 并入 `schemas/jobs.ts`）；`api(path, schema)` 运行时校验 → `bad_response`；`api/events.ts` 统一分发（SSE + `injectEvent`）；`web/src/mocks/`（http、db、events、browser、node、handlers 注册表 + `GET /series/{id}`、fixtures）；`app/demo.ts`（`VITE_DEMO_DATA`）；`stores/demo.ts` + 顶栏「示例数据」标记和剧名；`test/render.tsx` 带 QueryClient + Tooltip | b55ca38 | vitest 30 passed；lint、tsc、prettier、build 通过；**本机 Chromium 实测**：标记出现、worker 接管后 `/dev/jobs` 的任务仍经 SSE 实时变成「完成」 |
| 2 | `web/playwright.config.ts`（自起 Mock 后端 8765 + Vite 5183，视口 1440）、`e2e/`（pages、fixtures、smoke、shots）、`pnpm e2e` / `pnpm shots` / `pnpm shots:prototype`；`scripts/prototype-shots.ts` + 11 张原型截图（`docs/studio/reports/ui/prototype/`）；对照表骨架 `reports/ui/README.md`；后端 `DRAMA_WEB_ORIGINS`；**修 M0 的 SSE 断开弄坏连接池的 bug**（见 DECISIONS） | 0951287 | pytest 118 passed；vitest 30 passed；Playwright 冒烟 13 passed（连跑 6 轮无 500）；lint、tsc、prettier 通过 |
| 3 | tokens（`--tone-*` 五种状态色、`--highlight`、`--media*`，亮 / 暗分别调）；shadcn 补 tabs、dialog、popover、switch、checkbox、radio-group（`RadioCard`）、toggle-group、slider、progress、form（Label / Input / Textarea）、card、table、collapsible；`components/` 下 StatusBadge、PageHeader、SegmentedControl、Chip、MediaThumb、EmptyState、QueryState（`Skeleton` 带 `data-loading`）；`lib/format.ts`、`lib/tone.ts`；schemas episodes / spec / metrics / setup；fixtures + handlers（剧集、分集、进度、规格、`metrics/summary`、`setup/profile`）；hooks `useRouteEpisode` 等；**顶栏接数据**（剧名 · 集名、规格标签、GPU 名、本集花费 / 预算）、**导航徽标**；`/dev/components` 陈列页；新命名空间 `components` | 2561512 | vitest 32 passed；lint、tsc、prettier 通过；本机 Chromium 看了陈列页亮 / 暗 |
| 4 | `schemas/products.ts`（product / version / prompt / estimate / run 请求，字段照 SPEC 4.2 + 补充见 DECISIONS）、`schemas/models.ts`、`common.ts` 加 `PriceSchema`；示例库 products（enrich v1 本地 09:41 草稿、v2 DeepSeek 10:02 已采纳；extract v1 已采纳）、17 个写作模型目录、提示词编译；handler：run（1.4 秒后追加版本，发 `version.created` / `product.updated` / toast）、set-current、adopt（只能一个）、lock / unlock、prompt、compile；`api/hooks/products.ts`；组件 `CostBadge`、`ModelSwitchMenu`、`RunBar`、`VersionHistory`、`PromptEditor`（+ `useRunAction`、`lib/versions.ts`、`lib/cost.ts`）；新命名空间 `enums`；陈列页加两组产物 | aabe0ce | vitest 51 passed（新增 19）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；本机 Chromium 看了陈列页亮 / 暗、重跑中、换模型菜单 |
| 5 | schema `config`（组件目录、resolve 带逐字段来源、override）、`impact`、`gates`、`providers`；示例库：6 个写作组件的均衡预设、三级覆盖、改画幅和剧本第 1 段两个影响范围、闸门记录；handler `/config/components`、`/config/resolve`、`PUT /config/override`、`/impact/preview|apply`、`/gates/{gate}/confirm|reopen`；示例运行改为按配置的路由、估价随配置变；hooks `config` / `impact` / `gates`；`stores/inspector.ts`；组件 `Inspector`、`ModelPicker`、`ImpactDialog`（inline / modal）、`GateButton`；`enums.component.*`（19 个组件名）；陈列页改成 RunBar + Inspector 并排，加影响范围和闸门 | 本提交 | vitest 65 passed（新增 14）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；本机 Chromium 看了陈列页亮 / 暗、弹窗 |

## 下一步

- **第 6 步 01 小说页（Main）**：照计划「各页重点」表第 6 行。新 schema / fixtures / handlers：`GET /series/{id}/novel`（5 段原文 + 已采纳补写）、`GET /series/{id}/suggestions`（4 条：外貌、光线、心理外化、卡点，含 `alt` 改写）、`POST /suggestions/{id}/accept|reject|rewrite`、设定卡 `GET /series/{id}/bible`。原文 / 采纳后 / 对比三种视图、字数、全部采纳、设定卡四栏。页面布局：左边内容 + RunBar（`what` 用页面文案），右边 `<Inspector components=[enrich, extract]>`；页头 `GateButton gate="novel" label="确认原文，生成剧本"`。产物取 `useProducts({owner: "series:demo"})`，模型列表用 `useComponentModels(id)`；页面挂载时 `useInspectorStore.getState().reset()`。
- 原型数据和交互：`docs/studio/prototype/Main.dc.html` 第 388 行起的 `renderVals()`（段落 `P`、建议 `G`）；截图 `reports/ui/prototype/Main.jpg`。
- **约定**：页面数据没到时用 `QueryState` / `Skeleton`（带 `data-loading`）；状态色用 `StatusBadge` 或 `lib/tone.ts`；钱用 `formatUsd` / `CostBadge`；版本状态、来源用 `lib/versions.ts`；四个按钮的运行一律走 `useRunAction`（出错 toast）。
- 截图：`pnpm -C web shots -g <page>`。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

- Kelvin 本机常开着 `start.ps1`（5173 前端 + 8000 后端，Mock 模式），Vite 会热更新，可以直接拿来做浏览器核对；不要往里发真实（非 Mock）调用。
- 示例里的运行延迟在 `mocks/events.ts:demoTiming.runMs`，测试里改成 20 ms（见 `components/products.test.tsx`）；测试要挂 `useEventStream()`（`FakeEventSource`）才收得到 `version.created`。
- Playwright 冒烟收尾时后端会打印 aiosqlite「Task was destroyed but it is pending」，不影响结果，还没查（后端本步没改）。
- MSW 在 jsdom 里能拦相对路径的 fetch；handler 路径写 `*/api/v1/...`（`mocks/http.ts:v1()`）。

- **本机 PowerShell 执行策略禁止 `-File` 跑脚本**：钩子、状态栏、`start.ps1` 都要 `powershell -NoProfile -ExecutionPolicy Bypass -File …`。
- 写接口（非 GET）要带 `X-Drama-Studio: 1`，Host 必须是 127.0.0.1 / localhost；`TestClient` 要用 `base_url="http://127.0.0.1"`。
- Windows 上 `python` 不在 PATH（会跳到应用商店），一律 `uv run python`。
- pnpm：`corepack enable --install-directory ~/bin pnpm`；命令前加 `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` 避免首次下载提示。
- Windows PowerShell 5.1：`.ps1` 必须存成 UTF-8 带 BOM，否则中文乱码。
- YAML 1.1 会把 `on:` / `mode: off` 解析成布尔值：`core/config.py` 用只认 true/false 的加载器。
- SQLite 读回时间会丢时区，用 `models_db.UtcDateTime`。

## 等 Kelvin 的事

- 合并 M0 的 PR #1（合并后本分支 rebase 到 main）。
- 验证钩子（M0 遗留）：接受工作区信任后，确认状态栏和 `/clear` 后的 PROGRESS 注入。

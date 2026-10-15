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
| 3 | tokens（`--tone-*` 五种状态色、`--highlight`、`--media*`，亮 / 暗分别调）；shadcn 补 tabs、dialog、popover、switch、checkbox、radio-group（`RadioCard`）、toggle-group、slider、progress、form（Label / Input / Textarea）、card、table、collapsible；`components/` 下 StatusBadge、PageHeader、SegmentedControl、Chip、MediaThumb、EmptyState、QueryState（`Skeleton` 带 `data-loading`）；`lib/format.ts`、`lib/tone.ts`；schemas episodes / spec / metrics / setup；fixtures + handlers（剧集、分集、进度、规格、`metrics/summary`、`setup/profile`）；hooks `useRouteEpisode` 等；**顶栏接数据**（剧名 · 集名、规格标签、GPU 名、本集花费 / 预算）、**导航徽标**；`/dev/components` 陈列页；新命名空间 `components` | 本提交 | vitest 32 passed；lint、tsc、prettier 通过；本机 Chromium 看了陈列页亮 / 暗 |

## 下一步

- **第 4 步 产物与版本**：`api/schemas/products.ts`（product、version、run 请求；字段照 SPEC 4.2）；示例库加 products / versions（先放小说页的 enrich、extract 两个产物，数据见 `prototype/Main.dc.html` 底部：enrich v1 Qwen3.6-27B 本地 09:41 草稿、v2 DeepSeek V4 Pro API 10:02 已采纳；extract v1 本地 10:05 已采纳）；`POST /products/{id}/run` 约 1.4 秒后追加版本并经 `emitDemoEvent` 发 `version.created`（`api/events.ts` 的 `invalidates` 表加 products 键）；`components/` 下 CostBadge、RunBar、ModelSwitchMenu、VersionHistory、PromptEditor，放进 `/dev/components`。
- 组件用的模型列表（15 个 LLM + 本地）要从 `/config/components`（MSW，第 5 步）来；第 4 步的 ModelSwitchMenu 先吃 props（`options: {key, display, where, price_label}`），第 5 步接 hook。
- **约定**：页面数据没到时用 `QueryState` / `Skeleton`（带 `data-loading`）；状态色用 `StatusBadge` 或 `lib/tone.ts`；钱用 `formatUsd`。
- 截图：`pnpm -C web shots -g <page>`；原型截图已全部生成。原型摘要：读 `docs/studio/prototype/<Page>.dc.html` 底部的 `class Component`，或看 `reports/ui/prototype/<Page>.jpg`。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

- Kelvin 本机常开着 `start.ps1`（5173 前端 + 8000 后端，Mock 模式），Vite 会热更新，可以直接拿来做浏览器核对；不要往里发真实（非 Mock）调用。
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

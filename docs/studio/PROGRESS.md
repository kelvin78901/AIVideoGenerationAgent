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
| 5 | schema `config`（组件目录、resolve 带逐字段来源、override）、`impact`、`gates`、`providers`；示例库：6 个写作组件的均衡预设、三级覆盖、改画幅和剧本第 1 段两个影响范围、闸门记录；handler `/config/components`、`/config/resolve`、`PUT /config/override`、`/impact/preview|apply`、`/gates/{gate}/confirm|reopen`；示例运行改为按配置的路由、估价随配置变；hooks `config` / `impact` / `gates`；`stores/inspector.ts`；组件 `Inspector`、`ModelPicker`、`ImpactDialog`（inline / modal）、`GateButton`；`enums.component.*`（19 个组件名）；陈列页改成 RunBar + Inspector 并排，加影响范围和闸门 | ac2fadc | vitest 65 passed（新增 14）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；本机 Chromium 看了陈列页亮 / 暗、弹窗 |
| 6 | 小说页：schema `novel`（段落、建议、设定卡）；示例库 5 段原文、4 条建议（含重写稿）、11 个设定；handler novel / suggestions（accept、reject、reset、rewrite、accept-all）/ bible；hooks `api/hooks/novel.ts`；`components/StepLayout.tsx`（工作区 + 整列 Inspector）；`pages/Novel.tsx` + `pages/novel/`（SourceText 三种视图、SuggestionList、BiblePanel）；RunBar 跟着 Inspector 选中的组件走；命名空间 `novel`、`enums.suggestionKind`；`test/backend.ts`（假的 `/health`、`/providers`）；截图 `reports/ui/novel.*.jpg`，对照表填了第一行 | 6e8c36e | vitest 74 passed（新增 9）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；看了亮 / 暗 / 英文 |
| 7 | 剧本页：schema `script`（场、剧本行、重写建议），分集加场次范围 / 镜头数 / 剧本状态；示例库 2 场 10 行、12 段重写稿、12 个影响范围（原型 `imp`）、分集规划和每集剧本产物；handler 剧本、`/lines|scenes/{id}/rewrite`，`/impact/apply` 落盘改动；第 2 集生成后变「剧本草稿」；`pages/Script.tsx` + `pages/script/`（分集卡、剧本格式 / 结构化表格、来源高亮、编辑 / 重写 / 换模型重写 → 影响范围）；`ImpactDialog` 加 `detail`；RunBar / Inspector 对空产物用 `mode: run`；`product.updated` 顺带刷新 `["series"]` | 3d076e8 | vitest 83 passed（新增 9）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；本机看了改一段 → 弹窗 → 只标记 → 导航「待更新 2 / 1 / 1」 |
| 8 | 素材页：schema `assets`（素材、补丁、候选 payload、分析结果），价格单位 `mchar`；示例库 13 项素材及其产物（7 锁定、3 待选、3 待生成），图像和配音模型目录、img / text / voice 组件；handler 素材列表 / PATCH / lock / analyze，解锁走 `asset_unlock` 影响范围，素材产物重跑出候选，进度 7/13 按锁定数算；`pages/Assets.tsx` + `pages/assets/`（清单与筛选、详情、图像 / 画面文字 / 音色候选）；Inspector 选组件时跳到该类第一项 | 7533d0f | vitest 93 passed（新增 10）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；看了亮 / 暗 |
| 9 | 分镜页：schema `shots`（类型、景别、运动、声音做法、站位、尾帧来源），示例库 9 个镜头（34 秒、3 个已确认）、关键帧产物（3 候选）和分镜规划产物，kf 组件；handler 镜头列表 / PATCH（确认时采纳当前关键帧），分镜进度按确认数算，关键帧重跑出候选；`pages/Storyboard.tsx` + `pages/storyboard/`（预演条、镜头卡、镜头设定、可拖动的站位图）；Inspector 带 `item=shot:1-04` | 2e41148 | vitest 102 passed（新增 9）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；看了亮色 |
| 10 | 生成页：版本加 `qa`（5 项检查 + score）、`fallback_reason`、`stage`、`rating`，镜头加 `video_product_id`；视频 / 精修 / 口型 / 质检模型和 vid、up、lip、qa 组件；示例库 9 个视频产物（3 采纳、1-04 四条候选、1-05 生成中、1-06/07 排队、1-08/09 等尾帧），质检 6 过 4 不过；handler：unadopt、`PATCH /versions/{id}`、generate-rules、generate-log、upscale，新候选自动质检并写运行记录，等尾帧时 run 返回 409，进度「生成 3/9」按采纳数；`pages/Generate.tsx` + `pages/generate/`（状态卡、镜头 pills、候选墙 + 键盘、自动规则、运行记录）；`lib/takes.ts`、`lib/config.ts`；RunBar 排队状态 | 4bec5ba | vitest 113 passed（新增 11）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；看了亮 / 暗截图 |
| 11 | 后期页：schema `timeline`（片段、音频段、字幕、导出检查、导出格式），产物 slot 加 `sfx`；music / sfx / sub 组件和模型、三个后期产物；示例库音频和字幕挂在镜头上（跟着镜头时长动）；handler `GET /episodes/{id}/timeline`、`PATCH /clips/{id}`、`PATCH /subtitles/{id}`、`/export/checks`、`POST /export`；`pages/Post.tsx` + `pages/post/`（预览 + 播放头、片段设置、5 轨时间线、字幕、导出）；生成页支持 `?shot=`；补了第 10 步漏的组件说明（vid / up / lip / qa）；`Slider` 加 `thumbLabel`，测试 setup 补 `ResizeObserver` | 本提交 | vitest 121 passed（新增 8）；lint、tsc、prettier、i18n 通过；Playwright 冒烟 13 passed；看了亮 / 暗截图 |

## 下一步

- **第 12 步 成片规格页（Spec）**：照计划「各页重点」表第 12 行。4 个平台、5 种画幅、分辨率、帧率、时长、字幕、另出一版；安全区预览随画幅变；兼容表（21:9 时 Nano Banana Pro 不支持）；改画幅显示 inline ImpactDialog（$1.26 + $2.76 = $4.02，影响范围示例库里已有「改画幅」那一份）；保存时拦截。接口 `GET/PUT /series/{id}/spec`（GET 已有 handler，PUT 改画幅时先走 `/impact/preview`）。`dims` 由后端算（`spec/dims.py` 是唯一算尺寸的地方），示例 handler 里照它的规则算。
- 原型：`docs/studio/prototype/Spec.dc.html`（32 KB，`class Component` 在第 245 行，`renderVals()` 在第 269 行），截图 `reports/ui/prototype/Spec.jpg`。路由 `/s/:series/spec` 不是步骤页：用不用 `StepLayout` / Inspector 看原型（原型若没有 Inspector 就不要加）。
- **约定**：页面骨架参考 `pages/Post.tsx` / `pages/Generate.tsx`；改已确认内容先 `useImpactPreview`、后 `useApplyImpact`（剧本页是 inline ImpactDialog 的例子）；页面测试用 `test/backend.ts` 的 `backend()`（已含空的 `/jobs`），要看 toast 就在测试页面里挂 `<Toaster />`；AppShell 测试标题要改成页面 h1；Radix Slider 在 jsdom 里需要的 `ResizeObserver` 已在 `test/setup.ts` 补上。
- **Bash 工具的坑**：heredoc 里同时有中文引号、反引号和单引号时，Bash 工具会报「unexpected EOF」而整条命令不执行——改用 Write 写脚本文件再 `uv run python <文件>`。Python 写文件要 `open(..., "w", newline="
")`，`Path.write_text` 在 Windows 上会写成 CRLF（`prettier --write` 能修回）。
- 截图：`pnpm -C web shots -g <page>`，然后填 `reports/ui/README.md` 对照表那一行。

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

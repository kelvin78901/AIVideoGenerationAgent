# 工程决定记录

新的决定加在最上面：日期、决定、原因、影响。

## 2026-10-14 · M0.5 界面先行

- **新增里程碑 M0.5**（Kelvin 要求）：在 M1 之前把 11 个页面按原型做完，用示例数据跑。之后各里程碑只接后端、删掉对应的 MSW handler，界面不重写。分支 `m0.5-ui` 从 `m0-foundation` 切出（M0 的 PR 还没合并），M0 合并后 rebase 到 main 再开 PR。
- **接口契约用 zod**：`web/src/api/schemas/` 里每个接口一个 schema，TS 类型从 schema 推出；`api()` 在运行时校验响应，不符合时抛 `ApiError(code="bad_response")`。字段用 snake_case，和后端一致。原因：MSW 示例数据和以后的真实后端必须遵守同一份契约，字段对不上要马上暴露，而不是页面悄悄显示空白。
- **MSW 默认开启**（dev 和 build 都开），`VITE_DEMO_DATA=0` 关闭；`onUnhandledRequest: "bypass"`，没有 handler 的请求照常走 Vite 代理到后端。MSW 的每个响应带 `x-drama-demo: 1`，用过示例数据的路由在顶栏显示「示例数据」。示例库只在内存里，刷新页面就复原。全部 handler 删完后删掉 `web/src/mocks/`。
- **演示事件和真实 SSE 走同一个分发器**（`api/events.ts:dispatchEvent`）：MSW 模拟的运行、安装进度通过它推 `product.updated`、`version.created`、`setup.progress` 等事件，接真实后端时页面代码不改。
- **界面文字和内容分开**：状态、类别、原因等枚举由接口返回 code，前端翻译；日志和提示句子返回 `code + params`；小说、剧本、提示词、人名等用户内容原样显示，不翻译。
- **SPEC 9.1 增补的读接口**（9.1 只列了写接口和部分读接口，页面需要）：`GET /series/{id}/episodes`、`GET /episodes/{id}/progress`（导航徽标）、`GET /series/{id}/novel`、`GET /series/{id}/suggestions`、`GET /episodes/{id}/script`、`GET /episodes/{id}/shots` + `PATCH /shots/{id}`、`GET /products?owner=&component=`、`GET /config/components`、`GET /episodes/{id}/timeline` + 片段 / 字幕的 `PATCH`、`GET /episodes/{id}/export/checks` + `POST /episodes/{id}/export`、`GET /sync/board?episode=`。字段以 `web/src/api/schemas/` 为准，M0.5 收尾时同步写进 SPEC 9.1。
- **依赖版本**：MSW 用 2.14.7 而不是刚发布两周的 3.x；zod 4.6.4、Playwright 1.63.0、d3-scale 4.0.2、d3-shape 3.2.0，全部精确锁定。`msw` 的安装脚本（只是复制 worker 文件）在 `pnpm-workspace.yaml` 里显式禁用，`public/mockServiceWorker.js` 由 `msw init` 生成后进 git，lint 和 prettier 都忽略它。
- **「示例数据」标记按路由记**：`api()` 收到带 demo 头的响应时，记在当前路由上（壳层用 `useLayoutEffect` 先登记路由，子组件后发请求）。顶栏本身（剧名、规格、花费）也用示例数据，所以 M1 / M8 接上真实接口之前，每个页面都会显示这个标记。
- **Playwright 自带服务**：`pnpm e2e` / `pnpm shots` 用 webServer 自己起 Mock 后端（端口 8765，临时 `DRAMA_HOME`，空 `.env`）和 Vite（5183），不碰开发者正在跑的 5173 / 8000。为此后端新增 `DRAMA_WEB_ORIGINS`（逗号分隔，只接受 `http://127.0.0.1:<端口>` / `http://localhost:<端口>`，否则启动报错），追加到 CORS 和 `LocalOnlyGuard` 的允许来源。
- **修了一个 M0 的 SSE bug**：浏览器每次切页面都会断开 SSE，Starlette 用 anyio cancel scope 取消流，如果正好在 `EventBus.replay` / `last_id` 读库，aiosqlite 连接会被弄坏（之后请求 500「no active connection」，或者卡死）。两个读操作改为 `anyio.CancelScope(shield=True)` 读完再响应取消；引擎再加 `pool_pre_ping=True` 兜底。`tests/unit/test_events.py` 有回归测试（修复前会卡死，现在加了 30 秒超时）。Playwright 冒烟最先暴露这个问题（7 轮里出现 2 次 500）。
- **Toast 用 sonner**，不照抄原型的行内提示条（SPEC 16.2 只要求「Toast 反馈每个操作的结果」）。
- **原型截图**：原型依赖画布运行时，仓库里没有。截图时从 Kelvin 的 artifact「短剧工作台原型」取 `dc-runtime.js` 放在临时目录当 `support.js`，本机渲染后用 Playwright 截；运行时不进仓库，只提交截图。
- **截图格式**：JPEG、宽 1440 整页，中文亮色 + 中文暗色进 git（`docs/studio/reports/ui/`）；英文截图按需生成，不进 git。原因：控制仓库体积，PNG 整页图太大。

## 2026-10-14 · M0 合并前补充（Kelvin 审阅后）

- **本机接口防护**（`api/security.py:LocalOnlyGuard`，对上游 `/api` 和新 `/api/v1` 都生效）：Host 头只接受 `127.0.0.1` / `localhost` / `[::1]`（否则 421 `host_not_allowed`，防 DNS 重绑定）；所有非 GET 请求必须带 `X-Drama-Studio: 1`（否则 403 `missing_client_header`），带了 `Origin` 的必须是本机前端（否则 403 `origin_not_allowed`）。不带 Origin 的非浏览器客户端（脚本、将来的 ComfyUI 节点包）加上这个头即可。CORS 只放行 `content-type`、`x-drama-studio`、`last-event-id` 三个请求头。
- **上游设置接口不再返回密钥**：`GET/PUT /api/series/settings` 和 `/settings/reset` 的密钥字段一律清空，改给 `api_key_set` / `comfyui_api_key_set` / `runninghub_api_key_set`；保存时密钥字段为空表示「保留原值」。选择改返回值而不是摘掉路由，是为了 `/legacy` 的设置面板还能用。
- **上游直接调模型的 5 处只能经 `/legacy` 触发**：都只被上游 `/api/series/*` 路由（`/legacy` 界面在用）或上游 `drama-series-render` 命令行调用；`tests/unit/test_isolation.py` 用 AST 检查新代码不导入这些模块（例外：纯函数 `normalize_base_url`、挂载上游路由的 `router`）。`/legacy` 顶部常驻警示条。
- **Mock 模式标记**：`GET /api/v1/health` 返回 `mock`，顶栏在 Mock 时显示琥珀色「Mock 模式」。
- **PowerShell 一律加 `-ExecutionPolicy Bypass`**：这台机器的执行策略禁止 `powershell -File` 运行脚本，状态栏、两个钩子和 `start.ps1` 原来的写法都会直接失败。`Bypass` 只对那一个进程生效，不改系统设置。
- **启动脚本**：`start.ps1` / `start.sh` 改为 `uv sync` + `corepack pnpm -C web install --frozen-lockfile`，再启动 `uv run drama-studio dev` 和 `pnpm -C web dev`；后端固定监听 127.0.0.1（去掉了 `--host`），`--port` 通过 `DRAMA_BACKEND_URL` 同步给 Vite 代理；`.env` 逐行解析而不是 `source`。

## 2026-10-14 · M0 前端工具链

- **pnpm 替换 npm、ESLint 替换 oxlint**：CLAUDE.md 约定的命令是 pnpm；ESLint 能写「JSX 里禁止中文字面量」这条规则（`no-restricted-syntax`），落实硬规则 4。pnpm 12 默认拦截依赖的安装脚本，`web/pnpm-workspace.yaml` 只放行 esbuild。
- **TypeScript**：`strict` + `noUncheckedIndexedAccess`。上游界面过不了，**挪到 `web/src/legacy/` 并整文件 `// @ts-nocheck`**，ESLint 也忽略它；M2 新页面做完后整个目录删除。
- **shadcn/ui 组件手写进 `src/components/ui/`**（按 new-york 风格，`components.json` 留着以后用 CLI 加组件），颜色全部来自 `styles/tokens.css` 的 CSS 变量；暗色是单独挑的一套。
- **JSON 文件没法写注释**：改过的上游 `web/package.json`、`tsconfig*.json` 不加文件头说明，在 NOTICE 的总说明里覆盖。

## 2026-10-14 · M0 模型层

- **Mock 是默认模式**：没设 `DRAMA_MOCK` 也走 Mock，只有 `DRAMA_MOCK=0` 才调真实模型。原因：硬规则 2「开发默认用 Mock」，防止误花钱。Mock 保留真实模型的 key 和单价，Mock 模式下的花费数字和真实调用一致。
- **兜底只跳一次**：失败后换到 `fallback.to`（为空取 `alt_order` 第一个没试过的），再失败就报错。原因：沿着整个备选列表一路试下去，坏天气里花费会成倍增加；要再试由用户点「不满意换一个」。未知模型、预算超限不触发兜底。
- **每次尝试一行 `model_call`**：失败、超时、取消也记（`billed=false`、`cost_usd=0`，厂商明确计费的错误除外）。
- **`api:<provider>` 队列名取模型的 `provider_id`**：LLM 用 providers.yaml 里的供应商 id（如 `deepseek`），媒体和本地模型取 key 的前缀（如 `minimax`、`comfy`）。
- **OpenAICompatAdapter 用 httpx 直连**，不用 openai SDK：重试、错误码、流式都要自己控制，且便于 respx 测试；URL 规范化复用上游 `utils/llm_client.normalize_base_url`。
- **密钥查找顺序**：系统钥匙串（服务名 `drama-studio`，条目名 = `key_name`）→ 环境变量 → `.env`。`GET /providers` 返回 `has_key` 和 `key_source`（keyring / env / none），不返回密钥。所有 loguru 日志经过打码（Authorization、api_key、`sk-…`，以及本进程读到过的密钥原文）。测试里 `DRAMA_ENV_FILE` 指向空文件，不会读到开发机上的真实 `.env`。
- **开发接口 `/api/v1/dev/*`**：`llm-test` 只在 Mock 模式可用（否则 403 `mock_only`），给前端 `/dev/jobs` 面板和 M0 验收用。

## 2026-10-14 · M0 任务队列

- **只有处理器明确抛 `JobError(retryable=True)` 才自动重试**（到 `max_attempts` 为止）；其他异常直接失败，错误写 `error_json = {code, params}`。原因：模型调用的重试、兜底在 `router.call()` 里做，队列再盲目重试会重复花钱。
- **崩溃后续跑也算一次尝试**：启动时 running → queued；已经用完 `max_attempts` 的判 `failed`（`interrupted`），避免一个会搞崩进程的任务无限循环。**正常关闭**时运行中的任务也放回 queued，下次启动接着跑。
- **API 错误统一为** `{"detail": {"code", "params"}}`（`api/errors.py:ApiError`），前端按 code 翻译。

## 2026-10-14 · M0 数据库与配置

- **数据目录** `DRAMA_HOME`，默认 `~/.drama-studio/`：`studio.db`、`blobs/`，和 `envs/` 放在一起。测试里每个用例一个临时目录。
- **M0 只建本期用到的表**（`job`、`model_call`、`config_override`、`provider_account`、`custom_model`、`event`）；`series`、`product` 等由各自里程碑的迁移加。迁移在后端启动时程序内执行（`core/db.py:migrate`），迁移脚本放在包里（`core/migrations/`），只用 `sa.*` 类型，不依赖业务代码。
- **`job` 表比 SPEC 多两列**：`result_json`（任务输出，例如 LLM 结果）和 `depends_on_json`（SPEC 9 的任务依赖）。**新增 `event` 表**：持久化 SSE 事件，支持 `Last-Event-ID` 补发，保留最近 N 条。
- **配置的四级来源**：`factory`（components.yaml，按「均衡」预设推出默认值）→ `project` → `component` → `item`；`config_override` 的 `scope` 取后三个值，`component_id` 为空的 project 行对所有组件生效。嵌套字段按点路径逐项合并并记录来源（例如 `fallback.to`）。
- **SSE**：事件名用 `event:` 字段（前端按类型 `addEventListener`），数据是 JSON；除 `Last-Event-ID` 头外也接受 `?after=<id>`（浏览器 EventSource 首次连接带不了这个头）。不带 id 时只推新事件。
- **YAML 只把 true/false 当布尔**：YAML 1.1 的 `on/off/yes/no` 会把 `fallback.on`、`mode: off` 读坏。

## 2026-10-14 · M0 工具链

- **ruff / mypy 先只覆盖新代码**（core、modelhub、api/app.py、studio_cli 等）；上游模块在 `pyproject.toml` 里排除，改到哪个上游文件就把它纳入检查。原因：上游没有类型标注，一次性修完会大面积改上游文件，偏离「包一层适配，不推倒重写」。
- **`requires-python >=3.12`**，用 uv 管理（`.python-version` = 3.12）；保留 setuptools 构建和上游两个命令行入口，新增 `drama-studio`。
- **新 app factory `api/app.py:create_app()`**：上游路由原样挂在 `/api`，新接口在 `/api/v1`；CORS 只允许 `127.0.0.1:5173` / `localhost:5173`（上游是 `*`）。

## 2026-10-14 · 进度交接机制

- **PROGRESS.md 里的提交 hash**：每个小步只做一次提交（代码 + PROGRESS + 计划勾选）。本步那一行写「本提交」，下一步更新 PROGRESS 时把它替换成真实 hash。原因：提交前拿不到自己的 hash；不为了填 hash 额外做空提交或 amend。
- **钩子命令用 `$CLAUDE_PROJECT_DIR`**：`.claude/settings.json` 进 git，写死 `C:/dev/...` 换台机器就失效；状态栏在 `settings.local.json` 里，按要求用绝对路径。macOS 上没有 Windows PowerShell，钩子会静默失败（脚本本身也兼容 `pwsh`，需要时再加 Mac 版配置）。
- **`.ps1` 存成 UTF-8 带 BOM**：Windows PowerShell 5.1 不带 BOM 时按 ANSI 读，中文提示会乱码。
- **钩子的“已提醒”记录用纯文本**（`.claude/state/guard-<session>.txt`，一行一个阈值）：PS 5.1 的 `ConvertFrom-Json` 读数组时会套一层，导致重复提醒。

## 2026-10-14 · 方案阶段已定

- **基于 drama-series-agent**：fork 上游（或 clone 后推到私有仓库），包名沿用 `drama_series_agent`，新代码作为子包加入。原因：上游已有 Python 后端、React 工作台、ComfyUI H3 工作流和 OpenAI 兼容 LLM 预设，栈和本项目一致。
- **结构化状态以 SQLite 为准**（偏离 PLAN 里“文件系统为唯一真相”）：版本、任务、调用记录、配置都需要事务和聚合查询；大文件存磁盘按哈希引用；上游依赖的 `dramas/{series}/` 文件改为从数据库导出。
- **编排用确定性调度器**：PLAN 架构图里的“编排 Agent”在 v1 是按依赖图派任务的代码；对话式 Agent 放到 P3。原因：可测试、可续跑、花费可控。
- **写作类 LLM 统一走 OpenAI 兼容协议** + 供应商表；默认 DeepSeek V4 Pro（抽取类 Qwen3.8-flash），不默认使用 Claude。原因：Kelvin 要求便宜好用、多家可选。
- **默认成片规格**：国内短剧 · 9:16 · 1080×1920 · 24 fps。原因：短剧平台以竖屏为主；H3 原生 24 fps。
- **达芬奇同步**：免费版走“文件夹 + FCPXML”，Studio 版才用 Python API 自动建 Bin。原因：Resolve 免费版从 21.1 起不再支持外部 Python 脚本。
- **ComfyUI 是主要的外部画布**：每集生成素材板工作流 + 自带节点包实现存回；云端节点画布（Flora、Figma Weave、Krea）暂不接。
- **视觉重做**：原型只定结构和交互；正式版用 shadcn/ui + Tailwind + 设计 token。原因：Kelvin 认为原型界面粗糙。

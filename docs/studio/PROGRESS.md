# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M0 地基**（代码完成，PR 待合并）
- 报告：[`docs/studio/reports/M0.md`](reports/M0.md)
- 计划：[`docs/studio/plans/M0.md`](plans/M0.md)
- 分支：`m0-foundation`（每步提交后 push；不推 main）

## 已完成的小步

| 步 | 做了什么 | 提交 | 测试 |
| --- | --- | --- | --- |
| 0 | 计划存档、PROGRESS / 报告规则、状态栏 + 上下文提醒钩子 + SessionStart 钩子、/handoff 和 /continue、CLAUDE.md 新增一节 | 5e650b7 | 钩子脚本用模拟输入自测通过（65% 提醒一次、重复不提醒、session 不符不提醒、80% 提醒一次、直接跳到 80% 只提醒一次、无 rate_limits 显示「—」）；项目还没有自动化测试 |
| 1 | `NOTICE`；`docs/studio/UPSTREAM_NOTES.md`（上游模块地图、数据文件、H3 runner、失效传播、续跑、直接调 LLM 的位置、全局状态） | 934c772 | 仅文档 |
| 2 | Python 3.12 + uv（`uv.lock`、`.python-version`）、新依赖、ruff / mypy（strict，只覆盖新代码）/ pytest 配置；`config/*.yaml` 从 seed 拷入；`drama-studio dev` CLI；`api/app.py` 最小 app factory（上游 `/api` + `/api/v1/health`，CORS 只放行 5173）；`tests/conftest.py` | 4b4fe2b | pytest 9 passed；ruff、mypy 通过 |
| 3 | `core/paths.py`（`DRAMA_HOME` 默认 `~/.drama-studio/`）、`core/config.py`（YAML → Pydantic、四级解析 factory→project→component→item 并标来源）、`core/overrides.py`、`core/db.py`（SQLite WAL、async 会话、程序内跑迁移）、`core/models_db.py` 六张表 + Alembic `0001` | d9356ef | pytest 19 passed（含迁移升降级、模型与迁移一致、WAL、时区往返）；ruff、mypy 通过 |
| 4 | `core/storage.py`：按 sha256 存文件（`blobs/sha256/ab/<hash>`），临时文件 + `os.replace` 原子写、重复内容只存一份、大文件流式复制 | 9f60836 | pytest 25 passed；ruff、mypy 通过 |
| 5 | `core/events.py`：事件先写 `event` 表再广播，支持补发、慢订阅者从库里追、保留最近 5000 条；`api/sse.py` 的 `GET /api/v1/events`（`Last-Event-ID` 或 `?after=`，15 s 心跳）；`api/state.py` + lifespan（启动时迁移数据库） | 499003d | pytest 34 passed（含真实 uvicorn 上的 SSE 补发测试，连跑 3 次稳定）；ruff、mypy 通过 |
| 6 | `core/jobs.py` 持久化队列：gpu 并发 1、cpu 核数/2、`api:<x>` 默认 2；优先级 + 先进先出；依赖；取消（排队 / 运行中）、确认（`waiting_confirm`）；启动时把 running 放回队列（超过 max_attempts 判 `interrupted`），正常关闭也放回队列；每次状态变化发 `job.updated`；`api/routes/jobs.py`、`api/errors.py`（错误码 + 参数） | dfbd698 | pytest 49 passed（连跑 5 次稳定）；ruff、mypy 通过 |
| 7 | modelhub：`adapters/base.py`（协议、请求 / 结果类型、`ModelError`）、`adapters/mock.py`（LLM 文本 / JSON、PNG、WAV、FFmpeg MP4，可配延迟 / 失败 / 卡死）、`registry.py`（providers.yaml 三段 → spec；Mock 默认开启，`DRAMA_MOCK=0` 才走真实）、`pricing.py`、`calllog.py`、`router.py`（解析配置选模型 → 估价 → 预算钩子 → 超时 → 存文件 → 每次尝试一行 `model_call` → `cost.updated`；error/timeout 兜底一跳）；`api/handlers.py` + `POST /api/v1/dev/llm-test`、`GET /api/v1/dev/model-calls` | 3aa82a4 | pytest 69 passed；ruff、mypy 通过 |
| 8 | `modelhub/adapters/openai_compat.py`（httpx 直连 `/chat/completions`：JSON 模式、流式 + `CallContext.on_delta`、429/5xx 指数退避并尊重 Retry-After、错误码映射；`health()` = `GET /models`），非 Mock 时注册给所有带 base_url 的 llm；`core/secrets.py`（keyring → 环境变量 → `.env`，loguru 打码）；`api/routes/providers.py`（列表只给 `has_key` / `key_source`，存 / 删密钥，测试连接） | 26d8970 | pytest 89 passed（respx 模拟厂商；断言响应和日志里没有密钥）；ruff、mypy 通过 |
| 9 | 上游 `cli.py:run_api_main` 和 `scripts/run_api.py` 改为启动 `create_app()`（文件头加了修改说明）；应用装配测试（lifespan 迁移 + 队列启停、上游 `/api` 仍可用、OpenAPI 列出全部 `/api/v1` 路由） | 1ee8cf9 | pytest 92 passed；手动 `uv run drama-studio dev` + curl 走通 Mock LLM：SSE 依次收到 queued → running → cost.updated → succeeded，`model_call` 1 行 |
| 10 | 前端工具链：npm → pnpm 12（corepack；`package-lock.json` 删掉，`pnpm-workspace.yaml` 只放行 esbuild 的安装脚本）、oxlint → ESLint（typescript-eslint strict + react-hooks；**禁止 JSX 里写死中文**）+ Prettier、Vitest + Testing Library、TS strict + `noUncheckedIndexedAccess`、`@/` 别名、Vite 代理 `/api`；Tailwind v4 + `styles/tokens.css`（亮 / 暗两套，图表色按 SPEC 11.3）+ shadcn 基础组件（button / badge / dropdown-menu / tooltip / separator / scroll-area / sonner）；`stores/ui.ts`；`scripts/check-i18n.ts`。**提前做了 11b 的搬家**：上游界面挪到 `src/legacy/` 并加 `// @ts-nocheck`（上游代码过不了 strict） | 83b71c9 | vitest 4 passed、i18n 检查、eslint、tsc、vite build、prettier 全过；pytest 92 passed |
| 11 | `web/src/app/`（`App.tsx`、`routes.tsx` 11 个 SPEC 路由 + `/` 跳到示例剧集第 1 集小说页 + 404、`AppShell.tsx` 照原型的深色顶栏和左侧导航、`paths.ts`）、11 个空壳页（`pages/*.tsx`，标明哪个里程碑实现、对照哪个原型）、i18next（`src/i18n.ts`，`common` / `nav` 两个命名空间，带 key 类型检查；语言和亮暗主题存 Zustand + localStorage）；11b 收尾：`/legacy/*` 懒加载上游界面，上游 CSS 包进 `.legacy-root`；`.gitattributes` 统一 LF | 44f9db9 | vitest 9 passed（路由、导航链接、中英切换、GPU / 花费显示）、eslint（验证了写死中文会报错）、tsc、build、prettier 通过 |
| 12 | `web/src/api/`：`client.ts`（`/api/v1` 前缀；错误 → `ApiError(code, params)`，`errorMessage()` 按 `error.<code>` 翻译）、`hooks/useJobs.ts`、`useEventStream.ts`（全局一个 EventSource：`job.updated` 写进 Query 缓存，`cost.updated` 刷新调用记录，`toast` → sonner，重连后整体刷新）、`queryClient.ts`；顶栏 GPU 状态和 API 花费接真实数据；开发面板 `/dev/jobs`（只在 dev 构建注册） | 6913efe | vitest 20 passed（client 错误翻译、SSE hook、面板交互）；**在本机 Chrome 里实测**：点按钮后任务 排队中 → 完成 实时变化、调用记录增加、中英切换、`/legacy` 正常；Vite 代理下 SSE 实时推送无缓冲 |
| 13 | `.github/workflows/ci.yml`：push 只跑 Linux，PR 到 main / 手动触发时 Linux + Windows；后端 ruff（check + format）/ mypy / pytest，前端 eslint / prettier / tsc / vitest（含 i18n 检查）/ build；ruff 排除 `docs/`（ruff 0.17 会改 Markdown 里的 Python 代码块） | 934dd35 | 本地全部通过；CI 结果见下一步 |
| 14 | `tests/e2e/test_restart_resume.py`（子进程起后端 → gpu 队列 3 个任务 → 第一个运行中时硬杀进程 → 重启 → 3 个都完成，被打断的那个 attempt=2）；`/dev/llm-test` 加 `where`；CI action 升到 checkout@v7 / setup-node@v7 / setup-uv@v10；CLAUDE.md 常用命令；ROADMAP 勾选 M0；里程碑报告 `docs/studio/reports/M0.md` | 019b971 | pytest 93 passed（e2e 连跑 2 次稳定）；vitest 20 passed；lint / 类型 / 格式全过 |

## 下一步

- M0 代码全部完成，PR 已开（链接见报告 / PR 列表：`gh pr list -R kelvin78901/AIVideoGenerationAgent`）。
- PR #1 上 Linux、Windows CI 都已通过，ROADMAP M0 全部勾选。Kelvin 合并后，下一个里程碑是 **M1 首次启动 + 成片规格**，用 `/milestone` 出计划。

## 没提交的改动

- 无。`.claude/settings.local.json`（状态栏配置）在本机，按规则不进 git。

## 踩过的坑 / 临时绕过

- Windows PowerShell 5.1：`.ps1` 必须存成 UTF-8 带 BOM，否则中文乱码；`ConvertFrom-Json` 读数组会多套一层，所以“已提醒”记录改用纯文本。
- 钩子和状态栏在会话启动时加载：本会话里新建的 `settings.json` / `settings.local.json` 当场不生效，实时自测要等新会话。
- YAML 1.1 会把 `on:` / `mode: off` 解析成布尔值：`core/config.py` 用只认 true/false 的加载器。
- SQLAlchemy async 需要 `greenlet`（已加依赖）；SQLite 读回时间会丢时区，用 `models_db.UtcDateTime`。
- 新迁移：`uv run alembic revision --autogenerate -m ...`（`env.py` 的 `render_item` 会把 SQLModel / 自定义类型写成纯 `sa.*`）。
- pnpm：`corepack enable --install-directory ~/bin pnpm`（`~/bin` 在 PATH 里，不需要管理员）；命令前加 `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` 避免首次下载提示。
- 上游 `start.ps1` / `start.sh` 还在用 `npm install`、`npm run dev`，会重新生成 `package-lock.json`；新的启动方式是 `uv run drama-studio dev` + `pnpm -C web dev`（M0 收尾时在报告里说明，暂不改上游脚本）。

## 等 Kelvin 的事

- **验证钩子**：下次打开 Claude Code 时接受工作区信任（项目钩子需要），然后确认：① 状态栏显示「模型 · 上下文 N% · 5 小时额度 N%」；② 输入 `/clear` 后新会话开头能看到这份 PROGRESS.md。60% / 75% 提醒的实测：手动把 `.claude/state/context.json` 里的 `used_percentage` 改成 65 和 80，再让我跑任意一个工具。

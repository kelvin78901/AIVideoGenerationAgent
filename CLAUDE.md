# CLAUDE.md — AI 短剧工作台

本仓库基于开源项目 drama-series-agent（Apache 2.0）改造成一个一体化的 AI 短剧制作平台：用户写小说 → LLM 补全 → 结构化剧本 → 素材分析 → 分镜和关键帧 → 视频 → 后期，每一步都可视化、可改、可重跑。单用户，本机运行；主力机器是 Windows + RTX 5090 32 GB，开发也会在 Mac 上进行。

产品负责人是 Kelvin。**和 Kelvin 交流用中文**；代码、注释、提交信息、接口和变量名用英文。

## 先读什么（按顺序）

1. `docs/studio/ROADMAP.md` —— 现在做到哪个里程碑，验收标准是什么。从第一个没勾完的里程碑开始。
2. `docs/studio/SPEC.md` —— 工程规格：架构、数据模型、接口、各模块怎么实现。
3. `docs/studio/prototype/README.md` 和对应页面的 `.dc.html` —— 界面布局、文案和交互以原型为准。
4. `docs/studio/PLAN.md` —— 产品方案全文（为什么这么做、选了哪些模型、成本）。需要背景时再读。
5. `docs/studio/DECISIONS.md` —— 已经做过的工程决定。
6. `docs/studio/UPSTREAM_NOTES.md` —— 上游代码的模块地图（M0 时由你写）。

冲突时：行为以 SPEC 为准，布局和文案以原型为准，产品意图以 PLAN 为准；拿不准就问 Kelvin。

## 硬规则

1. **所有模型调用都经过 `router.call()`**：选模型、预算检查、兜底、写 `model_call` 记录都在这里。业务代码里不直接调厂商 SDK 或 httpx。
2. **测试和开发默认用 Mock 适配器**（`DRAMA_MOCK=1`）。自动化测试里绝不调用付费 API。真实调用只在手动冒烟脚本里，需要 `DRAMA_LIVE=1` 并设花费上限（默认 $1）。
3. **密钥**只存系统钥匙串（keyring），`.env` 兜底；不进数据库明文、不进日志、不经 API 返回、不进前端。`.env` 在 `.gitignore` 里。
4. **界面文字全部走 i18n 词表**（`zh-CN`、`en`），不写死在组件里；新增 key 两种语言同时加。
5. **版本只追加不覆盖**：每个产物都支持改提示词、重跑、不满意换一个、历史；已采纳或锁定的版本不会被自动替换，上游变化走失效传播。
6. **花钱前先估价**：API 任务入队前 `estimate()`，超过单次 / 单镜头 / 本集预算就进 `waiting_confirm`，等用户确认。
7. **加模型 = 加适配器或填配置**，不改流程代码。模型名、价格、默认路由放 `config/*.yaml`，不写死在代码里。
8. **本地 GPU 队列并发 1**，同一模型的任务连续跑，切换大模型前释放显存。
9. **首次启动的扫描是只读的**；安装器不动系统 Python，依赖装进 `~/.drama-studio/envs/` 下的 uv 环境；可选项失败只记录，不阻塞。
10. **成片规格是唯一的尺寸来源**：关键帧、视频、超分、导出、ComfyUI 节点的宽高和帧率都从 `output_spec` 读。
11. **工作台是唯一真相**：同步到 ComfyUI、Eagle、达芬奇、文件夹都是单向推送；只有「存回工作台」节点能产生新版本，而且只是候选。
12. 保留上游 `LICENSE`，改过的上游文件在文件头加一行修改说明。

## 技术栈

后端 Python 3.12 + FastAPI + Pydantic v2 + SQLModel / SQLite（WAL）+ Alembic + httpx，uv 管理依赖；自研 asyncio 任务队列（持久化在 SQLite）；SSE 推送。本地生成走 ComfyUI 的 HTTP / WebSocket 接口，本地 LLM 走 Ollama 或 llama.cpp 的 OpenAI 兼容接口。前端 React + Vite + TypeScript（strict）+ TanStack Query + Zustand + react-router + i18next，组件用 shadcn/ui（Radix + Tailwind）。详见 SPEC 第 2 节。

常用命令（M0 建好后以实际为准，并更新这里）：

```bash
uv sync                       # 安装后端依赖
uv run pytest                 # 后端测试（默认 Mock）
uv run ruff check . && uv run mypy src
uv run drama-studio dev       # 启动后端（127.0.0.1）
uv run drama-studio demo      # 用 Mock 生成示例项目《雨停之前》
pnpm -C web install && pnpm -C web dev
pnpm -C web test
```

## 工作方式

- **一次一个里程碑**。开始前进 plan mode，把计划（要改哪些文件、数据表、接口、测试）给 Kelvin 看，同意后再写。
- 小步提交，每次提交都能跑通测试。完成一项就在 ROADMAP 里勾掉。
- 做了 SPEC 没写或和 SPEC 不同的工程决定，在 `docs/studio/DECISIONS.md` 加一条（日期、决定、原因）。
- 产品层面的问题（交互、默认值、要不要做某个功能）问 Kelvin；纯工程问题自己决定并记下来。
- 不确定的厂商接口（模型 ID、参数）以官方文档为准，`config/providers.yaml` 里标 `verify: true` 的都要核对。
- **分支和推送**：每个里程碑开一个分支（如 `m0-foundation`），每完成一个小步提交后马上 push 到这个分支；**不直接推 main**。里程碑做完用 `gh pr create --base main` 开 PR，描述用里程碑报告，Kelvin 看完再合并。
- CI：Linux 每次 push 都跑；Windows 只在往 main 提 PR 时跑，也可以手动触发（workflow_dispatch）。

## 进度报告与上下文交接

每个里程碑都照做，保证 `/clear` 之后能无缝接着做。

- **计划文件** `docs/studio/plans/Mx.md`：计划批准后原样存进仓库，每个小步一个复选框，做完一步勾一步。
- **交接文件** `docs/studio/PROGRESS.md`（≤ 80 行，旧内容挪进里程碑报告）：当前里程碑和计划文件路径；已完成的小步（每步一行：做了什么、提交 hash、测试结果）；下一步做什么、从哪个文件开始；没提交的改动；踩过的坑和临时绕过的办法；等 Kelvin 决定的问题。每完成一个小步就更新，和代码放在同一个提交里（hash 写法见 DECISIONS 2026-10-14）。
- **里程碑报告** `docs/studio/reports/Mx.md`：里程碑做完时写，中文，写给 Kelvin：做了什么、怎么验证（能直接复制的命令）、测试和 CI 结果、和计划不一样的地方及原因、新加的 DECISIONS、遗留问题、需要 Kelvin 动手的事。PR 描述直接用这份报告。
- **节奏**：一个会话做 3–4 个小步。上下文到 60% 时（`context-guard` 钩子会提醒）做完当前小步就收尾；到 75% 时不再开始新的小步，马上整理到能提交的状态并交接。不要硬撑到自动压缩。
- **收尾**：跑测试 → 提交 → push → 更新 PROGRESS.md → 停下，告诉 Kelvin 输入 `/clear` 再输入 `/continue`。`/handoff` 立即执行这套收尾；`/continue` 读 PROGRESS、计划和 git log，核对一致后接着做下一个小步，不重新出计划，计划要改先问 Kelvin。
- **机制**（Windows，PowerShell 脚本一律 `powershell -NoProfile -File` 调用）：
  - `.claude/statusline.ps1`：状态栏显示「模型 · 上下文 N% · 5 小时额度 N%」，并把 session_id 和上下文用量写进 `.claude/state/context.json`。`statusLine` 配在 `.claude/settings.local.json`（不进 git）。
  - `.claude/hooks/context-guard.ps1`（PostToolUse）：60% 和 75% 各提醒一次（每会话），记录在 `.claude/state/`。
  - `.claude/hooks/session-start.ps1`（SessionStart）：把 PROGRESS.md、`git status --short`、最近 5 条提交打印进新会话。
  - 钩子配在 `.claude/settings.json`（进 git）；`.claude/state/` 不进 git。

## 一个功能怎样算完成

- [ ] 单元测试和 API 测试通过（Mock 适配器）
- [ ] Mock 模式下端到端能走通，示例项目里能看到效果
- [ ] 每次模型调用都写了 `model_call`
- [ ] 界面和原型对应页面一致（布局、文案、交互），中英文 key 都有
- [ ] 相关的 ROADMAP 项已勾选，必要时更新了 DECISIONS.md

# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M0.5 界面先行**（M0 已完成，PR #1 待 Kelvin 合并；M0 的逐步记录见 [`reports/M0.md`](reports/M0.md)）
- 计划：[`docs/studio/plans/M0.5.md`](plans/M0.5.md)
- 分支：`m0.5-ui`（从 `m0-foundation` 切出；每步提交后 push；不推 main；M0 合并后 rebase 到 main 再开 PR）

## 已完成的小步

| 步 | 做了什么 | 提交 | 测试 |
| --- | --- | --- | --- |
| 0 | 开分支 `m0.5-ui`；计划存档 `plans/M0.5.md`；ROADMAP 加 M0.5（M1–M9 的界面条目注明「接真实接口、删 MSW handler」）；DECISIONS 记 M0.5 的工程决定 | 本提交 | 仅文档 |

## 下一步

- **第 1 步 数据层**：装 `msw`、`zod`、`@playwright/test`、`d3-scale`、`d3-shape`（精确版本）；`web/src/api/client.ts` 加 schema 校验；抽出 `api/events.ts:dispatchEvent`（从 `api/useEventStream.ts`）；建 `web/src/mocks/`（browser / node / db / events / handlers）；`stores/demo.ts` + 顶栏「示例数据」标记。
- 原型截图（第 2 步）：运行时从 artifact「短剧工作台原型」（claude.ai/artifact/WL4RfL4RmT73kSrNWEPCrr）的 `artifact-type/dc-runtime.js` 取，放 scratchpad 当 `support.js`，不进仓库。
- 原型逐页摘要（布局、交互、示例数字）在本会话的子代理报告里，`/clear` 后需要时直接读 `docs/studio/prototype/<Page>.dc.html` 底部的 `class Component`。

## 没提交的改动

- 无。

## 踩过的坑 / 临时绕过

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

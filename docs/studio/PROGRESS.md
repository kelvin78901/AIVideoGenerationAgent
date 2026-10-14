# 进度交接（PROGRESS）

> 规则见 `CLAUDE.md`「进度报告与上下文交接」。≤ 80 行；旧内容挪进里程碑报告。

## 当前

- 里程碑：**M0 地基**
- 计划：[`docs/studio/plans/M0.md`](plans/M0.md)
- 分支：`m0-foundation`（每步提交后 push；不推 main）

## 已完成的小步

| 步 | 做了什么 | 提交 | 测试 |
| --- | --- | --- | --- |
| 0 | 计划存档、PROGRESS / 报告规则、状态栏 + 上下文提醒钩子 + SessionStart 钩子、/handoff 和 /continue、CLAUDE.md 新增一节 | 5e650b7 | 钩子脚本用模拟输入自测通过（65% 提醒一次、重复不提醒、session 不符不提醒、80% 提醒一次、直接跳到 80% 只提醒一次、无 rate_limits 显示「—」）；项目还没有自动化测试 |
| 1 | `NOTICE`；`docs/studio/UPSTREAM_NOTES.md`（上游模块地图、数据文件、H3 runner、失效传播、续跑、直接调 LLM 的位置、全局状态） | 本提交 | 仅文档 |

## 下一步

- 第 2 步：Python 工具链（pyproject、uv.lock、ruff/mypy/pytest、`config/`、`tests/conftest.py`）。

## 没提交的改动

- 无。`.claude/settings.local.json`（状态栏配置）在本机，按规则不进 git。

## 踩过的坑 / 临时绕过

- Windows PowerShell 5.1：`.ps1` 必须存成 UTF-8 带 BOM，否则中文乱码；`ConvertFrom-Json` 读数组会多套一层，所以“已提醒”记录改用纯文本。
- 钩子和状态栏在会话启动时加载：本会话里新建的 `settings.json` / `settings.local.json` 当场不生效，实时自测要等新会话。
- 本机没有 pnpm（第 10 步用 corepack 启用）；Python 3.12 要用 uv 下载（第 2 步）。

## 等 Kelvin 的事

- **验证钩子**：下次打开 Claude Code 时接受工作区信任（项目钩子需要），然后确认：① 状态栏显示「模型 · 上下文 N% · 5 小时额度 N%」；② 输入 `/clear` 后新会话开头能看到这份 PROGRESS.md。60% / 75% 提醒的实测：手动把 `.claude/state/context.json` 里的 `used_percentage` 改成 65 和 80，再让我跑任意一个工具。

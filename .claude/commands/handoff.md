---
description: 马上收尾：测试、提交、更新 PROGRESS.md 并推送，然后告诉 Kelvin 可以 /clear
---

按 `CLAUDE.md`「进度报告与上下文交接」一节的规则立刻收尾，不要再开始新的小步：

1. 把手上的改动整理到能提交的状态。做不完的部分要么回退，要么保证测试仍然通过并在 PROGRESS 里写清楚做到哪。
2. 跑测试（`uv run pytest`；动过前端再跑 `pnpm -C web test`）。失败就如实记进 PROGRESS，不要假装通过。
3. 更新 `docs/studio/PROGRESS.md`（≤ 80 行）：已完成小步（补上上一步的提交 hash）、下一步做什么和从哪个文件开始、没提交的改动、踩过的坑、等 Kelvin 决定的问题。计划文件里勾掉已完成的小步。
4. 提交（代码和 PROGRESS 一起），推到当前里程碑分支（不推 main）。
5. 用一两句话告诉 Kelvin：现在停在哪里、下一步是什么，可以输入 /clear，然后输入 /continue 接着做。

$ARGUMENTS

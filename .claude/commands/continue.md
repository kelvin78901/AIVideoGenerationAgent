---
description: 按 PROGRESS.md 接着做下一个小步（不重新出计划）
---

1. 读 `docs/studio/PROGRESS.md`、其中写的当前计划文件（`docs/studio/plans/Mx.md`），以及 `git log --oneline -10`、`git status --short`、当前分支。
2. 核对代码状态和 PROGRESS 对得上：提交 hash、未提交改动、当前分支是否是里程碑分支。对不上就先告诉 Kelvin 差在哪，不要自己猜着继续。
3. 接着做 PROGRESS 里写的「下一步」，按计划里的那个小步执行，**不重新出计划**。如果发现计划需要改（范围、接口、数据表、顺序），先停下来问 Kelvin。
4. 每完成一个小步：测试通过 → 提交 → 推到里程碑分支 → 更新 PROGRESS.md 并勾掉计划里的复选框（和代码同一个提交）。
5. 一个会话做 3–4 个小步；收到上下文提醒就按 `/handoff` 的规则收尾。

$ARGUMENTS

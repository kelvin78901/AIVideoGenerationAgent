---
description: 找到下一个没完成的里程碑，出实施计划
---

读 `docs/studio/ROADMAP.md`，找到第一个还有没勾选项的里程碑（跳过“P0 手工验证”）。

然后：
1. 读 `docs/studio/SPEC.md` 里和这个里程碑相关的章节，以及 `docs/studio/prototype/` 里对应的页面。
2. 看一下当前代码的状态，确认哪些已经做了。
3. 进入 plan mode，用中文给出实施计划：要新增或修改的文件、数据表和迁移、接口、前端页面和组件、测试，以及怎么验收。拆成能单独提交的小步。
4. 列出需要 Kelvin 决定的问题（如果有）。

计划被同意之前不要写代码。

计划批准后：开里程碑分支 `mx-<name>`；把计划原样存成 `docs/studio/plans/Mx.md`（每个小步一个复选框）；按 `CLAUDE.md`「进度报告与上下文交接」更新 `docs/studio/PROGRESS.md`。$ARGUMENTS

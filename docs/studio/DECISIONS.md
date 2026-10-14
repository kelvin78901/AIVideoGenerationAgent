# 工程决定记录

新的决定加在最上面：日期、决定、原因、影响。

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

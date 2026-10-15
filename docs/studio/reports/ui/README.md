# 界面对照：原型 vs 实现（M0.5）

每页三张图：原型（`prototype/`）、实现亮色、实现暗色。全部是宽 1440 的整页截图，中文界面，《雨停之前》第 1 集示例数据。

怎么重新生成：

```bash
pnpm -C web shots                    # 实现：全部页面的亮色 + 暗色（自动起 Mock 后端和前端）
pnpm -C web shots -g novel           # 只截一页
SHOTS_LANG=en pnpm -C web shots      # 英文版，存到 web/node_modules/.playwright/shots-en（不进 git）
# 原型：需要画布运行时 dc-runtime.js（从 Kelvin 的 artifact「短剧工作台原型」下载，不进仓库）
pnpm -C web shots:prototype --runtime <path/to/dc-runtime.js> [--only Main,Spec]
```

视觉按 SPEC 16.4 重做，不照抄原型的线框样式；布局、文案和交互以原型为准。「有意的差异」一栏写和原型不一样、而且是故意的地方。

| 页面 | 原型 | 实现 · 亮色 | 实现 · 暗色 | 有意的差异 |
| --- | --- | --- | --- | --- |
| 00 首次启动 `/setup` | [Setup](prototype/Setup.jpg) | 待做 | 待做 | |
| 00b 成片规格 `/s/demo/spec` | [Spec](prototype/Spec.jpg) | 待做 | 待做 | |
| 01 小说 `/s/demo/e/1/novel` | [Main](prototype/Main.jpg) | [亮色](novel.light.jpg) | [暗色](novel.dark.jpg) | 「导入 .txt / .docx」置灰（导入在 M2 接后端，原型里这个按钮也没有行为）；闸门按钮放在页头右侧，确认后旁边显示「已确认 · 重新打开」；模型名不带「（本地）」后缀（运行位置有单独的标记）；API 单价统一写「每百万 token」，原型里的「闲时半价」等备注没放（要等 providers.yaml 的 note 进接口） |
| 02 剧本 `/s/demo/e/1/script` | [Script](prototype/Script.jpg) | 待做 | 待做 | |
| 03 素材 `/s/demo/e/1/assets` | [Assets](prototype/Assets.jpg) | 待做 | 待做 | |
| 04 分镜 `/s/demo/e/1/storyboard` | [Storyboard](prototype/Storyboard.jpg) | 待做 | 待做 | |
| 05 生成 `/s/demo/e/1/generate` | [Generate](prototype/Generate.jpg) | 待做 | 待做 | |
| 06 后期 `/s/demo/e/1/post` | [Post](prototype/Post.jpg) | 待做 | 待做 | |
| 模型与兜底 `/models` | [Models](prototype/Models.jpg) | 待做 | 待做 | |
| 素材整理与同步 `/s/demo/sync` | [Sync](prototype/Sync.jpg) | 待做 | 待做 | |
| 数据看板 `/s/demo/dashboard` | [Dashboard](prototype/Dashboard.jpg) | 待做 | 待做 | |

## 全局差异（所有页面）

- **顶栏 GPU 状态**取真实的 `/api/v1/jobs`，没有任务时显示「空闲」；原型里有的页面写「运行中 1 · 排队 2」。
- **Toast** 用右下角弹出的提示（sonner），不是原型里页面内的蓝色提示条。
- **顶栏多两个标记**：「Mock 模式」（后端用 Mock 适配器）和「示例数据」（页面数据来自浏览器里的 MSW）。

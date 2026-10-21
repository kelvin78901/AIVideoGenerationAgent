# 开发路线（ROADMAP）

> 一次只做一个里程碑。开始前进 plan mode 出计划给 Kelvin 看；做完逐条勾选，验收项全部通过再进下一个。
> 时长是一个人业余开发的估算，只作参考。PLAN 里的阶段对应：P1 = M0–M5，P2 = M6–M9，P3 在最后。

## 并行：P0 手工验证（Kelvin 做，不写代码）

M0–M4 不依赖这些结论，可以同时进行；M5 开始前要有结论。

- [ ] 手工做一个 30 秒样片：2 个角色、5–6 个镜头，按 A 路线（本地 H3 草稿 → H3 2K 重生成）跑通
- [ ] 实测音频驱动口型（模式 A）的贴合度
- [ ] 实测 ControlNet 和身份参考同时使用的效果
- [ ] 实测中文文字渲染：20 张自己的中文招牌和界面样例，对比 GPT Image 2、Nano Banana Pro、Seedream 5.0
- [ ] 实测 9:16 竖版下 H3 本地草稿和 2K 重生成的构图、清晰度
- [ ] 把结论写进 `config/components.yaml` 的默认路由，并在 `docs/studio/DECISIONS.md` 记一条

---

## M0 地基（约 1 周）

- [x] 以 drama-series-agent 为初始代码；保留 `LICENSE`，新增 `NOTICE`
- [x] 通读上游，写 `docs/studio/UPSTREAM_NOTES.md`（模块地图、数据文件、H3 runner、失效传播、续跑）
- [x] uv 项目结构、ruff、mypy、pytest；前端 pnpm、eslint、Vitest
- [x] GitHub Actions：lint + 单测，Windows 和 Linux 各跑一遍
- [x] `core`：配置加载（`config/*.yaml` + 数据库覆盖）、SQLite + Alembic、按内容哈希的文件存储、SSE 事件总线、持久化任务队列（重启后续跑）
- [x] `modelhub`：适配器协议、注册表（读 `providers.yaml`）、`router.call()`、`model_call` 记账、各类 Mock 适配器
- [x] `OpenAICompatAdapter` + 「测试连接」（`GET /models`）
- [x] 密钥存 keyring，API 只返回“是否已填”
- [x] 前端：设计 token + shadcn/ui 基础组件、AppShell（顶栏、导航、中英切换、规格标签占位）、i18n 词表和 key 一致性检查、TanStack Query + SSE hook

**验收**
- [x] `uv run pytest` 和前端测试全绿，CI 通过
- [x] 打开前端能切中英文，导航能到各页（页面可以是空壳）
- [x] Mock 模式下发起一次 LLM 调用：前端实时看到任务状态变化，`model_call` 多一行
- [x] 任务排队时杀掉后端再启动，任务继续执行

## M0.5 界面先行（约 2 周）

> 11 个页面按原型做成可点击的 React 页面，用《雨停之前》第 1 集示例数据跑起来。还没实现的 `/api/v1` 接口由 MSW 在浏览器里返回示例数据，已实现的（jobs、providers 等）直接走后端。**M1 起各里程碑的界面条目改为「接真实接口、删掉对应的 MSW handler」，界面不重写。** 计划：[`plans/M0.5.md`](plans/M0.5.md)。

- [x] 接口契约：SPEC 9.1 的接口写成 zod schema + TS 类型，响应在运行时校验；补齐 9.1 缺的读接口（记进 SPEC 和 DECISIONS）
- [x] MSW：未实现的接口返回示例数据，带 `x-drama-demo` 头；顶栏「示例数据」标记；演示事件和真实 SSE 走同一个分发器
- [x] 共用组件正式版：RunBar、Inspector、ModelPicker、PromptEditor、VersionHistory、ImpactDialog、GateButton、CostBadge（`/dev/components` 陈列）
- [x] 制作步骤 6 页：小说、剧本、素材、分镜、生成、后期
- [x] 全局页 5 页：成片规格、首次启动、模型与兜底、素材整理与同步、数据看板
- [x] Playwright：冒烟测试进 CI；每页亮 / 暗截图，和原型并排对照（`docs/studio/reports/ui/`）

**验收**
- [x] 11 页都能打开、能点，原型里的交互都能用；数字和原型一致（本集 $8.94 / 预计 $13.35 / 预算 $15、42 次调用 1 次失败、9 个镜头 34 秒、素材 7/13、分镜 3/9、采纳 3/9、质检 6/10）
- [x] 中英切换后所有界面文字都变（示例内容除外）；亮色、暗色都检查过
- [x] 页面不写死数据：`VITE_DEMO_DATA=0` 时显示加载失败或空状态，不出现假数据
- [x] 8 个共用组件都是正式版：有 Vitest 测试，在 `/dev/components` 能看到各种状态
- [x] `pnpm test`、lint、typecheck、`uv run pytest` 全绿；Playwright 冒烟进 CI，CI 通过
- [x] 截图和原型的对照表写进里程碑报告

## M1 首次启动 + 成片规格（约 1 周）

计划：[`plans/M1.md`](plans/M1.md)。

- [x] `setup-manifest.yaml` 解析、各类检测器、只读扫描 → `machine_profile`
- [x] 安装器：按依赖顺序执行、SSE 实时日志、每步重试 / 跳过、`installed_item` 记录、镜像（自动 / 官方 / 国内）
- [x] Setup 页（对照 `prototype/Setup.dc.html`，中英文完整）（界面 M0.5 已做；这里接真实接口、删掉对应 MSW handler）
- [x] `output_spec` 表、`spec/dims.py`、`spec/compat.py`、平台预设
- [x] Spec 页（对照 `prototype/Spec.dc.html`）：平台、画幅、分辨率、帧率、每集时长、字幕、安全区预览、模型兼容表（界面 M0.5 已做；这里接真实接口、删掉对应 MSW handler）
- [x] 顶栏规格标签接真实数据
- [x] 左侧导航常驻「环境与安装」入口（Kelvin 2026-10-15 要求）：随时重新检测、补装，徽标显示缺几项
- [x] 识别已装的 ComfyUI（只读）：路径、端口、版本、节点包（git commit 或 Registry 版本）、模型文件（Kelvin 2026-10-18 要求，SPEC 6.4.1）
- [x] 改已装的 ComfyUI 前列改动清单确认；动手前用 ComfyUI-Manager 存快照，可一键回滚（SPEC 6.4.1）
- [x] 「模型与兜底」页的「工作流库」区域：导入、绑定、体检、试跑、分档，先用示例数据（SPEC 6.4.6；M5 接后端）
- [x] 安装进度和预计用时（Kelvin 2026-10-18 真装时提出）：下载按字节动态显示进度、速度、剩余时间；整体进度按体积算；开始前写出预计用时；多连接分块下载（连接数按实测速度自适应）

**验收**
- [x] 在 Kelvin 的 Windows + RTX 5090 上真实扫描，结果和实际一致
- [x] Mock 安装流程能跑完；失败项可重试、可跳过；重新扫描只补差异
- [x] macOS 上扫描后，视频、关键帧、超分自动标为走 API
- [x] 改画幅时尺寸、兼容表、安全区一起变；锁定后改画幅返回影响范围（M4 之前用示例数据）
- [x] 识别出的 ComfyUI 端口、版本、节点包版本、模型文件和 Kelvin 机器上的一致；装或升级前弹改动清单，回滚能回到改动前的快照

## M2 小说 → 剧本（约 2 周）

- [x] 导入 .txt / .docx，确认改编权，按章节分块（M2 第 5 步）
- [x] 设定提取（extract）+ 别名合并 + 设定卡；点卡片高亮原文（第 6 步）
- [x] 补全建议（enrich）：原文锚点、接受 / 拒绝 / 按要求重写、修订视图（第 7 步；另加第 7b 步小说逐段编辑）
- [x] 分集规划（split）：节拍看板（可拖动换集）+ 情绪曲线（第 8 步）
- [x] 剧本化（script）：原文和剧本左右对照，三向溯源跳转（第 9 步；镜头那一向的数据要到 M4）
- [x] 产物与版本：`product` / `product_version` / `dependency`（第 1 步）
- [x] 共用组件：RunBar、Inspector、ModelPicker（前 6 家 + 更多供应商）、PromptEditor（意图层 / 编译层）、VersionHistory（界面 M0.5 已做；这里接真实接口、删掉对应 MSW handler）（第 2、3 步）
- [x] 闸门：小说确认、剧本确认；失效传播 + ImpactDialog（第 10 步，含「确认并同步」级联重跑；第 12d 步没分集也能确认小说）
- [x] 模型与兜底页：四个预设、全局默认、密钥、兜底方式、备选顺序（界面 M0.5 已做；这里接真实接口、删掉对应 MSW handler）（第 2 步）
- [x] 预算：单次上限、超限进 `waiting_confirm`（第 4 步）
- [x] 新页面做完后删除 `web/src/legacy/`（上游 Hermes 界面）和 `/legacy` 路由（M2 第 11 步；上游 `/api/series` 一起摘掉）

**验收**
- [x] 用示例小说《雨停之前》跑到第 1 集剧本确认（M2 第 12 步：`tests/e2e/test_novel_to_script.py`、`web/e2e/m2.spec.ts`）
- [x] 任一产物都能改提示词、重跑、不满意换一个、回到历史版本、采纳（`tests/api/test_runs_api.py`、`test_products_api.py`、`web/src/components/products.test.tsx`）
- [x] 改一行已确认的剧本，弹出影响范围，三个选项都能用（M2 第 12 步：`web/e2e/m2.spec.ts`）
- [x] 手动冒烟：真实 DeepSeek 跑一遍剧本化（`DRAMA_LIVE=1`，上限 $1；M2 第 13 步：`scripts/smoke/live_script.py`，2026-10-20 花 $0.0078）

## M3 素材与配音（约 1.5 周）

- [x] 素材分析（assets）：素材清单 + 场景 × 角色出场矩阵
- [ ] 图像适配器：Nano Banana Pro、GPT Image 2、Seedream 5.0；ComfyUI 适配器的最小版本（Qwen-Image 出图、Qwen-Image-Edit 补视图）
- [ ] 参考图（img）：候选、混合模式出终版、上传、锁定、锁定后补齐侧面和背面
- [x] 画面文字（text）：逐字内容、字体风格、OCR 核对（Mock；真装 RapidOCR 归下面的「本地运行时」）
- [ ] 音色（voice）：本地试听 → MiniMax 音色设计 → 情绪变体 → 统一响度 → 锁定
- [ ] 台词配音（dub）+ 音频先行定时长（M3 算到台词和场，镜头 M4 接上）
- [ ] 本地运行时：Qwen3-TTS、IndexTTS-2.5、RapidOCR，和 ComfyUI 一起在本机真装真跑

**验收**
- [ ] 示例项目的 13 项素材（角色 2、场景 3、道具 4、画面文字 2、音色 2）都能出候选并锁定，锁定内容的哈希写进 `gate_decision`
- [ ] 每行台词都有音频，台词和场的时长由音频算出（镜头那一半挪到 M4，Kelvin 2026-10-20 定）
- [ ] 锁定的素材改描述后，提示哪些场和台词配音受影响（镜头那一半挪到 M4）
- [ ] 本机真跑：ComfyUI 出图和补视图、Qwen3-TTS 试听、IndexTTS 配音、RapidOCR 各跑一次
- [ ] 手动冒烟：真实 Google、OpenAI、火山、MiniMax 各跑一遍（`DRAMA_LIVE=1`，上限 $5）

## M4 分镜与动态分镜（约 1.5 周）

- [ ] 分镜规划（plan）：镜头类型、景别、机位、站位、时长初值
- [ ] 分镜板和表格两个视图同步；拆分、合并镜头
- [ ] 关键帧（kf）：按成片规格出图、安全区参考线、参考素材只用已锁定的、尾帧衔接
- [ ] 站位俯视图（简化版，可拖动人物和机位）
- [ ] 动态分镜播放器：关键帧按时长排开，配台词音频整集播放
- [ ] 动态分镜确认闸门；规格锁定（第一张关键帧采纳时）

**验收**
- [ ] 第 1 集 9 个镜头都有关键帧，能整集预演播放
- [ ] 把画幅从 9:16 改成 16:9，影响范围列出 9 张关键帧，并给出预计花费
- [ ] 镜头时长由台词音频算出（`pipeline/timing.py:shot_seconds`，M3 写好；从 M3 验收挪来）
- [ ] 锁定的素材改描述后，提示哪些镜头受影响（从 M3 验收挪来）

## M5 视频生成（约 2 周）

- [ ] ComfyUI 适配器完整版：按节点标题绑定、进度、取消、`/free`；上游 H3 工作流改成新格式，登记为平台推荐档（SPEC 6.4）
- [ ] 工作流库：工作流登记为本地模型（文件、绑定、依赖、能力），出现在对应组件的 ModelPicker；路由、兜底、记账、质检规则不变（SPEC 6.4.2）
- [ ] DramaStudio 节点包的输入 / 输出节点（首帧、参考图、提示词、台词音频、尺寸、帧率、时长、种子；视频、图片、音频）；普通工作流导入时自动猜绑定，在绑定页确认（SPEC 6.4.3）
- [ ] 导入体检：`/object_info` 查缺节点和模型 → 确认后按版本安装（先存快照）→ 示例输入试跑 → 分三档，未验证的不进自动路由（SPEC 6.4.4）
- [ ] 可复现：version 和 `model_call` 记工作流哈希和节点包版本；文件变了重新试跑；装节点后自动体检全部工作流，坏了提示回滚（SPEC 6.4.5）
- [ ] 工作流库界面接真实接口，删掉对应 MSW handler
- [ ] 按镜头选工作流：规则表 + 可选的 LLM 建议，只在平台推荐和「我的工作流」里选，选择理由记进 `model_call`（SPEC 6.4.8）
- [ ] 推荐档工作流的可开关分支（ControlNet、LoRA、超分），按镜头开关（SPEC 6.4.8）
- [ ] 拼节点（beta，默认关）：从成熟工作流里取片段拼成新图给用户参考，拼完不跑；要用就走导入流程（SPEC 6.4.8）
- [ ] GPU 队列按模型分组；本地超时兜底
- [ ] H3 API（含 Regenerate-2K、Context-IR）、Seedance 2.5 适配器
- [ ] 混合模式：本地草稿 → 采纳时 API 出终版
- [ ] 音频驱动（模式 A / B / C，按 P0 结论定默认）
- [ ] 候选墙：并排对比、推荐、采纳、再出一条、局部修复入口
- [ ] 本地队列 / API 队列状态条

**验收（P1 闸门）**
- [ ] 一集 3 分钟的戏全程走平台，人只在闸门处介入
- [ ] 每次调用都在 `model_call` 里，表头花费实时更新
- [ ] 本地任务超时后按兜底规则自动换到 API，并在历史里记一笔
- [ ] 导入一个不带 DramaStudio 节点的社区工作流：缺的节点和模型列清单确认后装好，确认绑定、试跑通过后出现在 ModelPicker；生成的 version 和 `model_call` 记了工作流哈希和节点包版本
- [ ] 装一个会弄坏已登记工作流的节点包后，体检报坏，并能一键回滚

## M6 质检与精修（约 1.5 周）

- [ ] 质检：人脸相似度、SyncNet、Whisper 字错率、说话人相似度、OCR、视觉 LLM（对连续性账本）
- [ ] 连续性账本（每场每镜的站位、道具、服装、时间）
- [ ] 不达标自动重跑，连续 N 次不过按兜底换模型；阈值可调
- [ ] 2K 精修（SeedVR2 / FlashVSR / H3 2K 重生成）、口型修复

**验收**
- [ ] 示例项目里故意放的坏 take（人脸不对、错字、口型错）被自动拦下
- [ ] 质检分写进 take 和 `model_call`

## M7 后期与导出（约 1.5 周）

- [ ] 裁掉开头 0.3 秒、每场一个 LUT、混音（台词 + 环境声 + 配乐，-14 LUFS）、J-cut / L-cut
- [ ] 字幕：文字取自剧本，ASR 只对齐时间；烧录 / SRT
- [ ] 导出 MP4（按成片规格）、SRT、FCPXML、OTIO；另出一版（外扩成横屏 / 裁成竖屏）
- [ ] 导出前检查：响度、黑帧、跳帧、未采纳镜头用关键帧占位

**验收（P2 闸门的一部分）**
- [ ] 导出的 FCPXML 在达芬奇免费版能导入，片段和字幕位置正确
- [ ] 10 分钟一集能出片；返工率能从 `model_call` 算出来

## M8 数据看板（约 1 周）

- [ ] `/metrics/*` 接口，口径按 SPEC 第 11 节
- [ ] 看板页全部模块：预算条、值得注意、关键指标、累计花费、调用次数、每镜时间和钱、组件时长、生成速度、API 明细、本地模型和显存、质检、按集汇总（界面 M0.5 已做；这里接真实接口、删掉对应 MSW handler）
- [ ] 每张图的「图 / 表」切换、悬停提示和联动、CSV 导出、本集 / 全剧切换（界面 M0.5 已做；这里接真实接口、删掉对应 MSW handler）

**验收**
- [ ] Mock 示例项目的数字和原型一致：已花 $8.94、预计 $13.35、预算 $15、42 次调用 1 次失败
- [ ] 图形规则全部满足（SPEC 11.3）

## M9 素材整理与外部同步（约 1.5 周，M5 之后任何时候都可以做）

- [ ] 同步引擎：触发规则、类型过滤、`sync_item` 差异推送、同步记录
- [ ] 本地文件夹同步（第 14.1 节的文件夹目标；2026-10-20 从 M3 挪来）
- [ ] ComfyUI 素材板：生成界面格式的 workflow（分组、Load 节点、便签），写进 ComfyUI 工作流列表
- [ ] 节点包 `integrations/comfyui-dramastudio`：镜头、素材、存回工作台；`POST /api/v1/ingest`（输入 / 输出节点 M5 已做）
- [ ] Eagle（检测 + 文件夹 + 标签 + 注释）
- [ ] 达芬奇：免费版文件夹 + FCPXML；Studio 版自动建 Bin、写元数据和标记
- [ ] Sync 页（对照 `prototype/Sync.dc.html`）（界面 M0.5 已做；这里接真实接口、删掉对应 MSW handler）

**验收**
- [ ] 采纳一个 take 后，几秒内出现在 ComfyUI 素材板对应的组里
- [ ] 在 ComfyUI 里用「存回工作台」节点出的结果，出现在该镜头的历史里，并且跑了质检、记了调用
- [ ] 在画布里挪节点、删节点，工作台的数据不变

---

## 之后（P3）

- 分镜画布进阶、take 对比墙进阶
- World Labs Marble 场景世界、Blender 运镜和物理模拟、手机动作捕捉
- 按场景加载 LoRA、LoRA 训练（版本锁定）
- 用自然语言指挥整条流水线的对话式 Agent
- ComfyUI 画布里的分组变化回写成标签

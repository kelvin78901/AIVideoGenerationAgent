# 工程决定记录

新的决定加在最上面：日期、决定、原因、影响。

## 2026-10-18 · 现在就在 5090 上真装节点包和权重（Kelvin 定）

- 用来测安装功能，计划加第 8b 步。改了 2026-10-15「模型权重只检测，等 P0 实测」的决定：
  - H3 全套和 Qwen3-VL-32B NVFP4 文本编码器现在就装，用官方文件；
  - Qwen-Image-Edit、SeedVR2 权重、IndexTTS2 先列出官方和社区版本让 Kelvin 挑；
  - 本地 LLM 不装。
- 权重放 ComfyUI Desktop 的共享模型目录（`ComfyUI-Shared\models`），Desktop 升级或重装都不丢。

## 2026-10-18 · M1 清单补齐（第 8 步）

逐条按官方仓库 / 文档核对（commit 用 `git ls-remote` 取，版本按各 tag 的源码核对）：

- **ComfyUI**：锁 v0.42.1（`63be2f9`），最低版本 `>=0.35.0`。
  - H3 原生节点（`MiniMaxH3ImageToVideo`、`MiniMaxH3ReferenceToVideo`，`comfy_extras/nodes_minimax_h3.py`）从 v0.30.0 开始有。
  - H3 的 Fun ControlNet（`MiniMaxH3FunControlNetApply`）从 v0.35.0 开始有。这两个起始版本是在各 tag 的源码上二分查出来的；后者和 docs.comfy.org 的教程「requires ComfyUI 0.35.0 or later」一致。
- **H3 节点、Fun ControlNet**：都是 ComfyUI 自带的，没有单独的节点包，所以不再算安装项（`install: []`，提示「ComfyUI 自带：更新到 x 或更新」）。
  - 检测：ComfyUI 在跑时按 `/object_info` 里的节点类；没在跑时按 ComfyUI 版本（`detect.native_since`，新字段）。
- **ComfyUI-Manager**：ComfyUI 0.4x 的官方装法是 `pip install -r manager_requirements.txt`（锁 `comfyui_manager==4.2.2`），启动时加 `--enable-manager`。不再 git clone 到 custom_nodes。第 5c 步核对快照接口用的正好是 4.2.2。上游已有 4.3 tag，但 ComfyUI 还没跟进，先不升。`snapshot_no_manager` 的文案改成提示 `--enable-manager`。
- **节点包**：
  - VideoHelperSuite 没有发布 tag，锁 2026-10-18 的 main `4d907be`。
  - SeedVR2 锁 v2.5.23（`5a4bf42`）。
  - FlashVSR 没有官方节点包，选 1038lab/ComfyUI-FlashVSR（`8877fdd`）：清单原来的 docs 链接指的就是它，作者在 Hugging Face 上的 1038lab/FlashVSR 模型也按它说明。
- **PyTorch**：源 `https://download.pytorch.org/whl/cu130`。2026-10-18 最新 2.14.1+cu130，有 Python 3.12 的 Windows 包。不锁版本号，和 ComfyUI 自己的 requirements.txt 一样。
- **uv**：winget `astral-sh.uv` / brew `uv`；官方安装脚本只写在注释里（没有包管理器时手动用）。
- **国内镜像的 GitHub**：用 `https://gh-proxy.com/https://github.com` 代理前缀（本机测 348 ms，返回的 commit 和官方一致）。kkgithub 连不上，ghfast 能用但慢。它是第三方服务，不能用时选「官方源」。
- **模型权重**：全部 `installable: false`，提示「等 P0 实测确定版本后再装」。
  - H3 和它的文本编码器按官方教程写了文件名（Hugging Face 的 Comfy-Org/MiniMax-H3），扫描能认出来。
  - 其他权重的文件名等 P0。
  - 影响：Mock 下 PC 示例能装的从 16 项变成 8 项，默认只勾 FFmpeg；导航徽标在全部装完后仍是「缺 6 项」（H3 节点要新版 ComfyUI，权重等 P0）。
- **`verify: true` 的核对**：在 Kelvin 的 5090 上跑 `scripts/setup_scan_real.py`（只读）：
  - PyTorch 2.12.1+cu130 判通过；
  - ComfyUI Desktop 0.41.2（没在跑）的位置、版本、commit、Python 3.13、Manager 4.2.2（pip，已启用）都认对了；
  - H3 节点和 Fun ControlNet 按版本判已有；
  - 网络测速通过。

  这三项（PyTorch、ComfyUI、网络）去掉 `verify`；Eagle、Resolve 本机没装，留着等装了的机器实测。
- **改动清单显示可读的版本**：安装步骤里写了 `version`（tag）就用它；没有就用 commit 的前 7 位。
- **测试绝不触网**：`tests/unit/test_steps.py` 的 `_install` 默认用离线 transport，碰网络就报错；遍历清单的测试只跑 `can_install` 的项。

  原因：权重有了真实地址后，那条测试真的开始下 H3 权重。本次开发中跑了 4 次，在 pytest 临时目录留下约 30 GB 的 `.part` 文件，已经删掉。

## 2026-10-18 · 按镜头选工作流；拼节点做 beta（Kelvin 定）

- **自动选工作流只用成熟的**：官方（平台推荐档）或用户导入、确认绑定、试跑通过的（「我的工作流」）。未验证的不参与自动选择。
- **拼节点做成 beta 功能**：从成熟工作流里取片段拼成新图，**拼完不跑**，只给用户参考；用户要用就按普通导入走（未验证 → 确认绑定 → 体检 → 试跑）。
- 写进 SPEC 6.4.8，ROADMAP 的 M5 加三项。原因：拼出来的图质量不可预知、没测过，不能进自动路由；但作为参考能省用户自己搭的时间。

## 2026-10-18 · M1 工作流库界面，示例数据（第 7b 步）

- **设计稿 Kelvin 审过**（审阅图 `reports/ui/workflows/`）：放「模型与兜底」页最下面，和组件表一样点一行在下面展开；展开后三个标签「绑定 / 体检 / 试跑」，默认打开最该处理的那个（有猜的绑定 → 绑定；缺依赖 → 体检；否则试跑）。
- **改档规则**（SPEC 6.4.4）：平台推荐的不能改档；升为「我的工作流」要绑定全部确认、试跑通过、文件没变过；「我的工作流」随时能降为未验证；改了绑定的「我的工作流」自动降为未验证（试跑结果不再算数）。
- **SPEC 9.1 没写、这次补的接口**（M5 接后端时再定）：`GET /comfy/workflows`（读 ComfyUI 自己的工作流列表，供导入；工作台的素材板列出但不能登记）、`POST /workflows/{id}/deps`（缺的节点包和模型的改动清单，`comfy_change` 同第 7 步）、`POST /workflows/{id}/deps/install`（确认后：先存快照再装）。装依赖复用第 7 步的确认弹窗，回滚提示指向「环境与安装」（`ConfirmInstall` 加 `snapshotNote`）。
- **试跑进度先轮询**：列表里有试跑中的工作流时每秒刷新一次；M5 有真任务后改成 `job.updated` 事件。
- **绑定的槽位**：照 SPEC 6.4.3 的输入输出，另加 `video_in`（超分、口型这类以视频为输入的工作流要用）。SPEC 收尾时补上。

## 2026-10-18 · M1 首次启动页接真实接口（第 7 步）

- **前端测试的假后端用真实后端导出的数据**：`tests/api/test_web_fixtures.py` 在 Mock 下扫描 PC / Mac 示例，把 profile（扫描前、扫描后）、全选安装时的顺序和 `install.confirm`、`/comfy/env` 写进 `web/src/test/data/setup.json`；`web/src/test/setupBackend.ts` 读它，按真实后端的节奏（202 后在下一个任务里推 `setup.progress` / `setup.log`，经测试的 `FakeEventSource` 走 SSE 那条路）模拟扫描、确认、快照、安装、重试、跳过、回滚。后端回答一变，这个 pytest 就失败，`DRAMA_UPDATE_FIXTURES=1` 重新生成。原因：MSW 示例和后端的数字已经分叉（MSW 25 项，后端 30 项），手抄一份迟早再分叉。文件由脚本生成，prettier 忽略它。
- **MSW 的 setup handler、示例数据和 `demoTiming.setup*` 删掉**：首次启动页只走真实后端（Mock 下后端自己有示例机器）。顶栏和「模型与兜底」页读 GPU 名也改走后端。
- **「只选必需的」和默认勾选一样，不含会改用户 ComfyUI 的项**；「全选」才包括它们。原因：SPEC 6.4.1 要求这些项不随必需项自动勾上，「只选必需的」就是回到默认。
- **确认弹窗关掉等于取消**（Esc、右上角都算）：取消什么都不装，回到检测结果，勾选保留。
- **「你的 ComfyUI」区域**：计划只写了快照列表和回滚；顺带把第 4c 步识别出的位置、地址、版本、Manager、节点包和模型文件（可展开）显示出来，方便核对验收第 6 条。放在页面最下面，扫描找到 ComfyUI 后才显示。
- **前一步的 bug**：没找到 ComfyUI 时（Mac 示例），勾了 Manager 也被排到最前面，排在要装的 ComfyUI 前面；改成只有装进用户自己的 ComfyUI 时才排第一。
- **导航徽标「缺 N 项」**：必需项里检测结果是「缺少」或「需更新」、而且还没装好的（PC 示例 11、Mac 4）。扫描前、扫描中、全部就绪时都不显示。会改用户 ComfyUI 的必需项也算（缺就是缺，只是不自动勾）。
- **`/` 的跳转**：profile 的 `scanned_at` 为空（从没扫描完过）才跳 `/setup`；profile 还没读到时先不渲染，读失败就照常进工作台，不把人卡在首次启动页。
- **切换示例机器也清掉示例档案的快照**：和清掉已装记录一样，「重新开始」要干净；只影响 Mock 的示例档案。
- **Playwright 和 `start.ps1` 起后端改用 `uv run python -m drama_series_agent.studio_cli dev`**：Kelvin 本机的应用控制策略拦 `.venv/Scripts/drama-studio.exe`（os error 4551），用模块方式效果一样，CI 也能跑。`start.sh`（Mac / Linux）不受影响，没改。

## 2026-10-18 · M1 改已装 ComfyUI 前先确认，快照和回滚（第 5c 步）

- **Manager 的接口按本机装的 comfyui_manager 4.2.2 源码核对**（`glob/manager_server.py`；官方文档只讲界面和 cm-cli，没写 HTTP 接口）：`GET /v2/snapshot/getlist` → `{"items": [...]}`；`POST /v2/snapshot/save` 不带请求体（表单类 Content-Type 会被拒，防 CSRF），返回 200 但不给名字，所以名字取存之前和之后 `getlist` 多出来的那个；`POST /v2/snapshot/restore?target=<名字>` 只是安排好，下次 ComfyUI 启动时才恢复；恢复要 Manager 的安全级别是 normal 或更低（本机监听时，默认 normal 可以），否则 403。Manager 4 以前的版本（custom node，`/snapshot/*`）不支持，报 `snapshot_no_manager`。
- **用 Manager 的快照，不用 Desktop 自己的**：SPEC 定的是 Manager；它对便携版、git 版、Desktop 都一样能用；Desktop 2 的快照（`.launcher/snapshots`）只有 Desktop 自己的界面能用，没有给我们调的接口。
- **哪些项算改用户的 ComfyUI**（`Item.touches_comfy`）：comfy 组里有安装步骤的项，或者安装步骤写进 `{comfy}`、`env: comfy` 的项（PyTorch 装进它的 Python、权重放进它的模型目录）。只有扫描找到的 ComfyUI 不是我们装的那份（`~/.drama-studio/ComfyUI`）时才算。每一项的 `touches_comfy` 随档案返回，第 7 步前端用它把这些项默认不勾。
- **改动清单**：`install.confirm` 里先列 `comfy_change`（item、`action` 为 install 或 update、`from`、`to`、`source`、`gb`），后面才是提权和大下载。不知道的字段直接不写，因为前端的 Message 参数不能为 null。清单另存一份在 `install.changes`，存快照时记进 `comfy_snapshot`。
- **快照什么时候存**：在第一个会改 ComfyUI 的项开始执行之前（它的 `start` 日志之后、第一步之前），不是整次安装开始前，所以排在前面、不碰 ComfyUI 的项照常先装。一次安装只存一份，重启续跑时沿用这一份。存不成时，会改 ComfyUI 的项都失败（`snapshot_not_running` / `no_manager` / `forbidden` / `restart` / `failed`），其他项照常装；失败原因在这次安装里沿用，重试时清掉再存一次。存快照要 ComfyUI 开着（Manager 的接口在 ComfyUI 里面）。
- **没装 Manager 时**：清单加了一项 `comfy_manager`（检测 pip 包或 custom node；安装从官方仓库 git clone，ref 第 8 步锁定）。勾了会改 ComfyUI 的项时自动带上它并排在最前面；它自己不用先存快照（`snapshot_first: false`）。刚装好的 Manager 要等 ComfyUI 重启后才加载，所以这一次后面的项都报 `snapshot_restart`，重启 ComfyUI 后重试就行。PC 示例机器补了 Manager 4（pip 包），这样 Mock 下能走完整个流程。清单行数变成 PC 30 行（通过 10），Mac 29 行（可选 8）。
- **`comfy_snapshot`**（迁移 `0005`）比 SPEC 多一列 `profile_id`，把示例机器和本机分开；`reason` 是 install 或 manual。
- **接口**：`GET /comfy/snapshots`；`POST /comfy/snapshots`（手动存一份，201）；`POST /comfy/snapshots/{id}/restore` → `{snapshot, restart_required: true}`。出错时：404 `comfy_snapshot_not_found`；409 `comfy_not_found`、`comfy_snapshot_failed {reason}`；安装进行中不能回滚，409 `setup_busy`。平台不替用户重启他的 ComfyUI，只提示。

## 2026-10-18 · M1 识别已装的 ComfyUI（第 4c 步）

- **Comfy Desktop 2**（Kelvin 本机，只读看过目录和日志）：安装记录在 `%APPDATA%\Comfy Desktop\installations.json`（每项有 `installPath`、ComfyUI 版本和 commit、Python、PyTorch、`launchArgs`）。程序、`.venv`、`custom_nodes` 都在 `<installPath>\ComfyUI` 里，模型放在共享目录，由 Desktop 生成的 `instance-model-paths\<id>.yaml` 指过去。它启动 ComfyUI 时 `main.py` 是相对路径，所以运行中的实例靠 argv 里的 `--extra-model-paths-config` 对上是哪一份安装。定位顺序：运行中的实例 → Desktop 的安装记录 → 常见目录 → 设置里的路径。macOS / Linux 上 Desktop 设置目录的位置是按 Electron 惯例推的，没核对。第一代 Desktop（程序和数据分两个目录、默认端口 8000）没有专门处理，只靠常见目录找。
- **端口**：先试清单里的地址（8188），再试 8000。只有 `/system_stats` 返回了 ComfyUI 的 `system`（含版本或 argv）才算找到，所以本机 8000 上的后端不会被误认成 ComfyUI。Kelvin 的 ComfyUI 在 8188，不冲突；真冲突时用 `start.ps1 -Port` 换后端端口，默认值不改。端口取 argv 的 `--port`，没有就取应答的那个地址。
- **节点包来源**：有 `.git` 是 git（HEAD、loose ref、`packed-refs`、`gitdir:` 指针都直接读文件；远端地址去掉用户名和令牌）；有 ComfyUI-Manager 留下的 `.tracking` 文件是 Registry（这一点没核对 Manager 文档）；都没有是手动放进来的，单个 `.py` 也算；只在 `/object_info` 里出现、目录里没有的记为 unknown。跳过 `.disabled` 目录和 `*.disabled`。版本取 `pyproject.toml` 的 `project.version`。
- **Python / PyTorch 版本不靠运行解释器**：在跑时取 `/system_stats`；没在跑时读 `pyvenv.cfg` 和 site-packages 里 `*.dist-info` 的目录名；最后才用 Desktop 安装记录里的值。（扫描里的 PyTorch 检测项本来就会单独跑一次 import。）
- **ComfyUI-Manager**：新版是 pip 包 `comfyui_manager`，`--enable-manager` 启用，Desktop 2 用的就是这种（本机 4.2.2）；旧版是 `custom_nodes/ComfyUI-Manager`。两种都认。**这影响第 5c 步**：Desktop 2 自己会存快照（`<installPath>\.launcher\snapshots\*.json`，开机和更新后各存一份），Manager 4 的快照接口要按官方文档重新核对。
- **模型文件**：目录是 `models/` 下的各子目录，加上每个用到的 `extra_model_paths.yaml`（argv 指定的、ComfyUI 根目录下的、Desktop 生成的）。在磁盘上最多往下走 4 层、最多记 5000 个文件，只认模型扩展名，超出的标 `models_truncated`。在跑时以 `/models/{folder}` 的清单为准，再到磁盘上对出路径和大小，对不上的路径和大小留空。
- **`comfy_env`**：哈希只覆盖 ComfyUI 版本、commit、Python、PyTorch 和节点包（含节点类），不含模型文件和路径；同样的环境不重复存。比 SPEC 多一列 `comfyui_commit`。模型清单和位置存在 `machine_profile`（`data_json.comfy`），重新扫描期间保留上一次的结果。
- **迁移**：`0004` 只建 `comfy_env`，`comfy_snapshot` 放到第 5c 步的 `0005`（计划写的是两张表都在 `0004`）。原因：Kelvin 在两步之间重启 `start.ps1` 时本机库会升到 `0004`，再回头改已经执行过的迁移，他的库里就会少这张表。
- 路径小工具（`join`、`dirname` 等）挪到 `setup/pathutil.py`，`comfy.py` 和 `detectors.py` 共用，避免循环导入。

## 2026-10-18 · M1 能力过滤（第 6 步）

- **本地模型写明自己要什么**：`providers.yaml` 的本地模型（含本地 LLM 服务的两个）加 `needs`（清单项 id）和 `requires_cuda`。H3 要 ComfyUI + H3 节点 + 两份权重 + CUDA，ControlNet 再加 Fun ControlNet 节点；SeedVR2 / FlashVSR 要各自的节点（SeedVR2 还要权重）+ CUDA；Qwen-Image-Edit 要 ComfyUI + 权重，不要求 CUDA（Mac 上 ComfyUI 能出图，只是慢）；本地 LLM 和 Qwen3-VL 要本地 LLM 服务（Qwen3.6-27B 还要 `w_llm`）。清单里还没有对应项的（CosyVoice、Whisper 等）不写 `needs`，视为能跑，跑时失败照常兜底；LatentSync、InfiniteTalk 只标 CUDA。测试检查每个 `needs` 都是清单里的 id。
- **「有」怎么算**：最近一次扫描里状态为通过、需更新、注意的项，加上之后装好的项（和安装器判断依赖的规则一致：ComfyUI 版本旧也算有，H3 节点有单独的检测项）。存在档案的 `found` 里：扫描结束时写，每装好一项追加一项，重新扫描期间沿用上一次的结果，切换示例机器时清空。**从没扫描过时不过滤**：不知道机器情况，就按配置走。
- **怎么绕开**（`core/capabilities.py:restrict`，在 `resolve()` 合并完各层覆盖之后做，所以用户手选的本地模型也会被绕开）：`local_model` 置空；`local` / `hybrid` 改成 `api`，没有 API 模型的（结构控制）改成 `off`；`fallback.to` 是跑不了的本地模型时置空（路由器接着按 `alt_order` 找）；`alt_order` 里也去掉。不自动换另一个本地模型顶上，免得悄悄换了模型。
- **来源不变**：`sources` 仍标原来那一级；另给 `Resolved.unavailable`（模型 → 缺什么：`cuda` 或清单项 id），M2 的「模型与兜底」页用它说明「本机跑不了」（前端契约里已有 `ComponentDef.unavailable`）。
- **用在哪**：`router.settings()`（每次模型调用）和兼容表（`/series/{id}/spec/compat` 按这台机器实际会走的路由判断）。Mock 模式下扫描示例机器同样生效：扫描 PC 示例后、装好之前，视频、关键帧、超分都走 API。
- **原因**：SPEC 7.3、12.2-1「跑不了的本地选项隐藏」。验收第 3 条（Mac 上视频、关键帧、超分走 API）由能力过滤直接得出，推荐预设里不用另写规则。

## 2026-10-18 · ComfyUI 与工作流库（Kelvin 定）

- **背景**：Kelvin 本机已经装了 ComfyUI，以后会用官方和社区的各种工作流。设计写进 SPEC 6.4（原「ComfyUI」扩成「ComfyUI 与工作流库」），ROADMAP 的 M1、M5 加了对应条目。
- **默认用已装的 ComfyUI**：M1 只读识别路径、端口、版本、节点包（git commit 或 Registry 版本）、模型文件。任何安装或升级都先列清单问，动手前用 ComfyUI-Manager 存快照，可一键回滚。平台自管的另一份 ComfyUI（`extra_model_paths.yaml` 共享模型）以后再说。
- **工作流库（M5）**：每个工作流登记为一个本地模型：API 格式文件、绑定（语义槽位 → 节点标题和字段）、依赖（节点包和版本、模型文件）、能力（组件、画幅、时长、参考图数、显存）。登记后进对应组件的 ModelPicker，路由、兜底、记账、质检规则不变。
- **对接**：首选 DramaStudio 节点包的输入 / 输出节点，平台只认这些；普通工作流导入时自动猜绑定，在绑定页确认。
- **导入体检和分档**：`/object_info` 查缺节点和模型 → 问了再按版本装 → 示例输入试跑。平台推荐 / 我的工作流 / 未验证，未验证的只能手动选，不进自动路由。
- **可复现**：version 和 `model_call` 记工作流文件哈希和节点包版本；工作流文件变了要重新试跑；每次装节点后自动体检全部已登记的工作流，坏了提示回滚。
- **界面**：「模型与兜底」页加「工作流库」区域（导入、绑定、体检、试跑、分档），先用示例数据做，M5 接后端。
- **随之改的旧写法和补的默认值**（Kelvin 可改）：
  - 绑定按节点标题（`_meta.title`），不再按节点编号（原 6.4 的 `{node: "12", field: "text"}`）；工作流文件从 `workflows/<name>.json` + `<name>.bindings.yaml` 改成 `workflows/<slug>/workflow.api.json` + `workflow.yaml`。
  - 「工作流库」示例数据界面放在 M1（Kelvin 说先用示例数据做、M5 再接后端；M0.5 已经结束，M1 是现在的里程碑）。
  - 机器上一份 ComfyUI 都没有时，仍按 2026-10-15 的决定装到 `~/.drama-studio/ComfyUI`；「另起一份平台自管的」理解为已经有一份时再并行装一份，这个以后做。
  - 改已装的 ComfyUI 的项（升级它、装节点、往它的 Python 装包、往它的模型目录放文件）不随「必需项默认勾上」，单独列清单确认。第 5 步的安装器要补这一层：现在只对提权和大下载确认，也还没有快照。
  - 装节点后的自动体检：所有工作流做静态检查；用到变动节点包的推荐档和「我的」档再排一次低优先级试跑（全部都试跑太占 GPU）。
  - DramaStudio 节点包分两批：输入 / 输出节点在 M5，镜头、素材、存回节点仍在 M9。
  - `providers.yaml` 里的 `comfy/*` 本地模型以后由工作流库提供，有推荐档工作流才算可用。
- **M1 计划追加**（Kelvin 2026-10-18 批准）：4c 只读识别已装的 ComfyUI、5c 改动清单确认 + 快照回滚、7b 工作流库示例数据界面；第 7、8 步跟着补；剩下的顺序 6 → 4c → 5c → 7 → 7b → 8 → 9。上面按理解补的几处，Kelvin 批准时没有提出修改，照此执行。
- **原因**：那份 ComfyUI 是 Kelvin 自己的工作环境，平台不能悄悄改坏它；社区工作流和节点更新很快，只有按节点标题绑定、记下文件哈希和节点版本、分档管理，才能放心地把它们当模型用，出了问题查得到、回得去。

## 2026-10-18 · M1 真实安装步骤（第 5b 步）

- **每一步都幂等，装之前先再检测一次**：`RealRunner` 先重跑这一项的检测器，已经「通过」就直接算装好（日志 `already`，比如扫描后用户自己装了）；各步骤再各自跳过已经做完的部分，所以重试和重启续跑只补缺的。
- **Python 包只进两个地方**：`~/.drama-studio/envs/<name>`，或者找到的 ComfyUI 自己的解释器（`env: comfy` 时优先用它，Kelvin 2026-10-15 定）。没有 venv 先 `uv venv --python 3.12`。测试把清单里三个平台的每一项都跑一遍（命令只记录不执行），断言 uv 命令全都指向 `envs`，也没有直接调 `pip` / `python`。
- **git_clone**：`--filter=blob:none` 克隆后 checkout 锁定的 ref；已经在这个 ref 就跳过，不在就 `fetch --depth 1` + checkout；目标文件夹已有别的文件、又不是仓库时报 `dest_not_empty`，不覆盖用户的东西。后面步骤的 `{dest}` 指上一步克隆 / 下载 / 复制的位置。
- **download**：写到 `.part`，再次下载用 `Range` 接着下，服务器不支持就从头下；sha256 不对就删掉 `.part` 报 `sha256_mismatch`；`hf_repo` + `files` 拼成 `<hf>/<repo>/resolve/<revision>/<file>`。
- **镜像**：「自动」按扫描时测的各站点延迟，每个站点单独判，超过 1500 ms 或不通就用国内；国内 PyPI 用清华源；步骤自带 `index_url`（PyTorch 的 CUDA 源）时不改；清单里国内 GitHub 镜像还是 TODO，暂时一律走官方。
- **pkg**：winget `--exact --silent --accept-*`，「已经装了」的退出码算成功；brew 直接装；apt 用 `sudo -n`（不弹密码，提权已在安装前确认过；Linux 上要先在终端 `sudo -v`，Linux 不是主力平台，先这样）。`script` 不经 shell，按空格拆开，命令必须在 PATH 里。
- **清单里还是 TODO 的值**让这一项以 `manifest_todo` 失败（第 8 步补齐之前，PyTorch、ComfyUI、各节点和权重都会停在这里）；子进程输出逐行发 `setup.log`（`output`，单行截到 500 字）。
- **CI 两个修复**：Linux 的 mypy 不认识 `subprocess.CREATE_NO_WINDOW`（只在 Windows 存在；第 4a 步起 CI 一直卡在 mypy，后面的 pytest 没跑），本地改动 `setup/` 后加跑 `mypy --platform linux`；runner 上 corepack 默认的 pnpm 升到 12.14.0，在仓库根目录调 `pnpm -C web` 时和 `web/package.json` 锁的 12.11.2 不符，CI 先 `corepack install -g` 锁定的版本。

## 2026-10-18 · M1 安装流程（第 5a 步）

- **一次安装 = 一个 `setup.install` 任务**（cpu 队列）：按依赖拓扑排好的顺序（存进 `install.items`）一项一项装，装好写 `installed_item`。重试时如果任务还在跑，只把这一项排回队列，由它接着装；任务已经结束就新开一个。重试不再问一遍确认。
- **依赖怎么算满足**：扫描时就在的（包括「需更新」「注意」）算满足，所以 ComfyUI 更新失败不挡 H3 节点；依赖这次装失败或被跳过 → 跳过，原因 `dependency_failed`；没勾选、机器上也没有 → 跳过，原因 `dependency_missing`。日志 `skip_dep`。
- **安装前确认**（SPEC 12.2-5）：任务队列只能在入队时进 `waiting_confirm`，所以是整次安装等确认；`install.confirm` 列出原因（`setup:confirmReason.admin` / `large_download`）。新增 `POST /setup/install/confirm` 和 `POST /setup/install/cancel`（SPEC 9.1 没有）：不直接让前端调 `/jobs/{id}/confirm|cancel`，因为档案要跟着改、要发事件。取消 = 回到检测结果，什么都没装。
- **哪些要管理员权限**：清单 `pkg` 步骤的 `admin: [winget, apt]` 写哪些包管理器装它要提权，默认只有 apt（走 sudo）；Git for Windows 装到 Program Files，标了 winget。单项 `size_gb` 超过 10 GB 的下载也要确认（权重的体积等 P0 实测后填）。
- **重启续跑**：进程被杀后任务照常恢复，正在装的那一项从 0 重来，已经装好的不重装（`tests/e2e/test_setup_resume.py` 用 `installed_at` 验证）。任务彻底失败时，排队中和正在装的项标「失败 · 安装中断了」（`interrupted`），可以重试。
- **示例机器的节奏**：每步 120 ms（`DRAMA_SETUP_FAKE_TICK_MS`，测试设 0），下载类每步 +10 %、其他 +34 %，SageAttention 到 60 % 报 `no_wheel`，和 MSW 版一致。PC 上全选是 16 项（原型 15 项，多了 DramaStudio 节点包）：15 项成功、1 项失败。
- **e2e 的 `Backend` 挪进 `tests/e2e/conftest.py`**，`start()` 可以带额外环境变量；两个 e2e 测试共用。
- 真实机器的安装步骤在第 5b 步接上；在那之前 `local` 档案的安装项都会以 `internal` 失败。

## 2026-10-18 · M1 机器档案和检测任务（第 4b 步）

- **一台机器一行 `machine_profile`**：`local` 是这台电脑（`RealProbe`），`demo` 是 Mock 的示例机器（`FakeProbe`，`machine` 列记 PC / Mac）。`installed_item` 的主键是 (profile_id, item_id)，所以 Mock 下模拟装过的东西不会混进真实档案。`DRAMA_SETUP=real|fake` 显式指定；不设时 Mock 模式就是 fake。`data_json` 存阶段、各项结果、安装请求、推荐，以及检测器看到的细节（`facts`：路径、版本、延迟），细节不经接口返回，留给安装器和能力过滤用。
- **扫描是 cpu 队列上的 `setup.scan` 任务**：`POST /setup/scan` 先把所有项设成「检测中」并返回 202，任务逐项写库、每项发一条 `setup.progress`（开始和结束各一条 `item: null`）。重新检测会取消正在跑的那次；每次扫描或重置换一个 `run` 令牌，令牌过期的任务不再写库，所以两次扫描不会混在一起。进程重启后任务照常续跑（同一个令牌，从头再扫一遍）。任务彻底失败、档案停在「检测中」时，下次读档案改回「还没检测」或「检测完成」（没出结果的项标「检测出错」）。
- **示例机器上以 `installed_item` 为准**：示例机器的探针结果是固定的，装过的项重新检测时直接算「已安装」；真实机器以检测结果为准。
- **示例机器每项间隔 110 ms**（和原型演示一致，`DRAMA_SETUP_FAKE_DELAY_MS` 可改，测试设 0）；真实扫描不加延迟。示例机器的 `envs` 在它自己的主目录下（`C:/Users/kelvin/.drama-studio/envs`、`/Users/demo/.drama-studio/envs`）。
- **推荐规则放在清单的 `recommend:` 里**（硬规则 7：默认路由不写死在代码里），按顺序取第一条满足的：有 CUDA → 均衡 / `local_video`，否则 → 均衡 / `no_cuda`。
- **扫描前的档案**：第一次读档案时做一次快速的只读硬件读取（系统、显卡、默认目录）存起来，顶栏和「会检测这些」用它。显卡名去掉 `NVIDIA ` / `GeForce ` 前缀（`RTX 5090`），显存取整。
- **切换示例机器**（`POST /dev/setup/machine`，只在 fake 模式，否则 403 `setup_not_simulated`）：取消正在跑的扫描、清空示例机器的 `installed_item`、回到「还没检测」，和 MSW 版一致。

## 2026-10-18 · M1 清单和检测器（第 4a 步）

- **扫描按清单全列**（Kelvin 2026-10-15 选定）：每台机器显示清单里这个平台的全部项，PC 29 行（通过 9 / 缺少 9 / 需更新 2 / 可选 8 / 注意 1），Mac 28 行（没有驱动；通过 6 / 注意 3 / 缺少 4 / 可选 7 / 跳过 8）。原型的 PC 25 行、Mac 17 行少了 uv、DramaStudio 节点包、Eagle、达芬奇，Mac 上把 SeedVR2 / FlashVSR 并成一行、不列需要 CUDA 的权重；两边共有的项 status 和 found / fix code 一致。需要 CUDA 的项在没有 CUDA 的机器上显示「跳过」，不隐藏。
- **清单加三个字段**（SPEC 12.1 没有）：`fix`（状态 → 建议 code，可带 params；不写时按类型给默认：节点「安装节点」、权重「下载」、其他「安装 X」、旧版「更新到最新版」）；`if_missing`（没找到时的状态，默认必需 → 缺少、否则可选）；平台覆盖 `macos:` / `windows:` / `linux:`（覆盖 required、name、variant、fix、if_missing、installable，`optional` 是 `{required: false}` 的简写）。依赖的项在这个平台不是必需的，依赖它的项也不是必需的（Mac 上 ComfyUI 可选，节点也跟着可选）。依赖成环、id 重复、依赖不存在都在加载时报错。
- **新检测类型 `comfy`**：先问正在运行的 `127.0.0.1:8188/system_stats`（argv 里有 `main.py` 的绝对路径就用它；ComfyUI 自己也是这样报的，相对路径就继续往下找），再找常见目录（主目录、文档、各盘根目录和便携版目录、`~/.drama-studio/ComfyUI`），最后用设置里的路径。用它自己的 Python（便携版 `python_embeded`、`venv`、`.venv`），都没有才用我们的 `envs/comfy`；PyTorch 检测用同一个解释器。还没找到 ComfyUI 时，PyTorch 检测我们自己的 `envs/comfy`（PyTorch 比 ComfyUI 先装）。
- **扫描不算 sha256**：`file` 检测只看文件在不在。几十 GB 的权重算一遍哈希要好几分钟，违背「大约 10 秒」；sha256 在安装器下载完时校验（第 5 步）。
- **检测器出错不阻塞**：单个检测器抛异常时这一项显示「注意 · 检测出错」，其他项照常检测。API 密钥只数 `providers.yaml` 里 LLM 供应商的 `key_name`（媒体模型和它们共用账号）。网络测速把官方的 HF / PyPI / GitHub 各访问一次，超过 `max_latency_ms` 或不通算慢；HF 慢用原来的「直连 Hugging Face 较慢」，其他站点用新的 `site_slow`。
- **探针分 `RealProbe` / `FakeProbe`**：检测器只通过 `Probe` 访问机器（跑命令、HTTP、文件、NVML、导入模块、钥匙串、达芬奇版本），`RealProbe` 只读；`FakeProbe` 读 `tests/fixtures/setup/{pc,mac}.yaml`（原型的两台示例机器），Mock 模式和测试都用它。显卡先用 NVML（`nvidia-ml-py`），没有再用 `nvidia-smi`；访问本机服务时不走系统代理。

## 2026-10-15 · M1 成片规格页接真实接口（第 3 步）

- **MSW 的 `/impact/apply` 用普通 `put()` 写规格，不用 `bypass()`**：`PUT /series/{id}/spec` 的 handler 已经删了，请求在浏览器里自然落到真实后端；测试里则落到 `test/backend.ts` 的假后端。`bypass()` 会连测试的假后端一起跳过，单测里就没法走。后端返回的错误原样转成 demo 错误。
- **同步页「镜头」节点的尺寸读真实规格**：`/sync/board` 的 demo handler 先 `GET /series/demo/spec`，后端不通时用示例数据。MSW 的内存库不再存规格（删了 `specs`）。
- **`test/backend.ts` 加剧集和规格的假后端**：`fake.series` / `fake.spec` 每次 `backend()` 重置，测试直接读写；尺寸和兼容表是 `spec/dims.py`、`spec/compat.py` 的测试副本。AppShell 测试也挂上 `backend()`（顶栏读剧集和规格）。
- **冒烟加一条**：真实浏览器里锁定规格改 16:9 →「改，并标记待更新」→ 刷新后顶栏仍是 16:9，再改回 9:16。

## 2026-10-15 · M1 兼容表（第 2 步）

- **兼容表的行由 `config/spec.yaml` 的 `compat_stages` 定**：每行 = 一个组件的某个角色（`api_model` / `local_model` / `fallback` / `alt` = 备选里第一个不是主用的），按解析后的路由取模型，所以 Inspector 改了模型表格跟着变；组件 `mode: off` 或角色为空就不出这一行。原型的 7 行照这个规则得出，5 种画幅下和 MSW 版逐行一致。
- **判定只看画幅和短边**：`caps.aspects` 不含 → 不支持，处理方式 `outpaint_from_<最接近的画幅>`；`caps.max_short_edge` 小于该行的档（草稿行用 768p，其他用交付档）→ 需要转换，`upscale_from_<1k / 720p>`；否则原生，说明用该行的 `native` code。帧率不判（SPEC 13.2 在后期转换）。没有 `caps` 的模型当原生。多个模型一行时取最差的。
- **caps 补充**：`openai/gpt-image-2` 加 `max_short_edge: 1024`、`volc/seedance-2.5` 加 `720`（都按 note 里「部分渠道」的下限，带 `verify: true`）；本地模型可以写 `caps`，`comfy/h3` 照 H3 API 填了画幅、24 fps、5–15 秒、短边 1440。新增通用文案 `spec:compat.how.native`。

## 2026-10-15 · M1 剧集和成片规格（第 1 步）

- **`config/spec.yaml` 进 `StudioConfig.spec`**：平台预设、新剧集默认规格、平台遮挡区比例都在这里；尺寸不进配置，只由 `spec/dims.py` 算（短边 1080 / 1440 / 768，21:9 2K 封顶 2976×1248）。取偶数用「四舍五入」而不是 Python 的银行家舍入，和前端 `Math.round` 一致（9:16 草稿 768×1366）。
- **`GET /spec/presets` 多返回 `safe_areas`**：前端 schema 不认识的字段会被 zod 去掉，现在不影响页面；成片规格页的预览仍用前端那份同样的数字，分镜 / 关键帧叠参考线时改读接口。
- **表名 `output_spec`，模型类叫 `OutputSpecRow`**：和 API 形状 `spec/schema.py:OutputSpec`（带 `audio`、`dims`）区分。`series_id` 外键到 `series`，级联删除。
- **示例剧集只在 Mock 下、库里一个剧集都没有时建**（`StudioState.start()` 调 `seed_demo()`），所以测试里每个 `TestClient` 都有 `demo`。时间存 UTC，接口返回 `…Z`。

## 2026-10-15 · M1 计划（Kelvin 已定）

- **ComfyUI 先用已有的**：扫描时先找正在运行的 127.0.0.1:8188 和常见目录，找到就用它（节点、权重装进它里面，用它自己的 Python）；找不到才装到 `~/.drama-studio/ComfyUI`。安装设置里能手动改路径。
- **清单只补运行环境和节点**：Python、uv、PyTorch、FFmpeg、Git、ComfyUI 和各节点在 M1 补齐真实地址、锁定版本；模型权重只检测，安装显示「等 P0 实测确定版本」，到对应里程碑再补。
- **导航加「环境与安装 / Environment」**：放工具区第一个（「成片规格」上面），徽标显示「缺 N 项」，就绪时不显示。原型里没有这个入口。
- **Mock 下检测和安装都是模拟的**：`DRAMA_MOCK=1` 时用原型里的示例机器（PC / Mac 可切），什么都不装；`DRAMA_SETUP=real`（或 `DRAMA_MOCK=0`）才真实扫描、真实安装。
- **示例剧集进真实数据库**：Mock 启动时库里没有剧集就建 `demo`（《雨停之前》，规格已锁定），这样删掉 `/series`、`/spec` 的 MSW handler 后其他页面照常能用；M2 的 `drama-studio demo` 在它上面扩展。
- **锁定后改画幅**：后端 `PUT /series/{id}/spec` 遇到已锁定又改画幅返回 409 `spec_locked`；影响范围在 M4 之前仍由 MSW 给，MSW 的 `/impact/apply` 收到 `spec_aspect` 时调真实的 `PUT …/spec?confirmed_impact=<id>` 写入（M1 只检查不为空，M2 有真的影响范围后校验 id）。
- **首次启动跳转**：只有打开 `/` 而且从没扫描过时跳到 `/setup`，直接打开的页面不跳。

## 2026-10-15 · M0.5 收尾

- **依赖的数据没加载到时不再永远转圈**：很多查询的 key 要用上游结果（例如分集 id 来自 `/series`），上游失败时它们一直是 disabled，`QueryState` 原来会一直显示骨架。现在「没有请求在跑、而且有查询失败」时，disabled 的查询显示中性提示「没有可显示的内容：它依赖的数据没加载到」，「重试」重跑所有失败的查询（`components/QueryState.tsx:useUpstreamFailed`）。正常加载时没有失败的查询，所以不会闪一下。
- **缺数据时不显示看起来像真的默认值**：顶栏本集花费没拿到时写「—」而不是 $0；模型页拿不到主机信息和组件目录时写「未知」，不再写「没有可用的显卡」「ComfyUI 已连接」；素材页清单没加载到时不显示「已锁定 0 / 0」那一行；同步页没有分集时素材板标题不带集号。`http_404` 有了中文说明「后端没有这个接口或数据（404）」。这些都是 `VITE_DEMO_DATA=0` 逐页核对时发现的。
- **演示步骤的延迟在测试里设成 0，而不是放宽等待**：检测、安装、同步这类逐步推进的演示流程统一走 `mocks/events.ts:repeatDemo(ms, step, alive)`。`ms > 0` 时每隔 ms 走一步（浏览器里的演示）；`ms = 0` 时在下一个任务里把所有步骤连着跑完（不是同步执行，HTTP 响应先发出去），事件顺序不变，React 只渲染一次。原因：慢的不是等待（测试里本来只等 2 ms），而是每步一次整页渲染，CI 上一次完整安装要 10 秒。
- **Playwright 冒烟只在 Linux CI 跑**：`--with-deps` 装 Chromium 依赖 apt；Windows 的 PR 检查不跑 e2e。失败时上传 `web/node_modules/.playwright/results`（保留 7 天）。

## 2026-10-14 · M0.5 界面先行

- **新增里程碑 M0.5**（Kelvin 要求）：在 M1 之前把 11 个页面按原型做完，用示例数据跑。之后各里程碑只接后端、删掉对应的 MSW handler，界面不重写。分支 `m0.5-ui` 从 `m0-foundation` 切出（M0 的 PR 还没合并），M0 合并后 rebase 到 main 再开 PR。
- **接口契约用 zod**：`web/src/api/schemas/` 里每个接口一个 schema，TS 类型从 schema 推出；`api()` 在运行时校验响应，不符合时抛 `ApiError(code="bad_response")`。字段用 snake_case，和后端一致。原因：MSW 示例数据和以后的真实后端必须遵守同一份契约，字段对不上要马上暴露，而不是页面悄悄显示空白。
- **MSW 默认开启**（dev 和 build 都开），`VITE_DEMO_DATA=0` 关闭；`onUnhandledRequest: "bypass"`，没有 handler 的请求照常走 Vite 代理到后端。MSW 的每个响应带 `x-drama-demo: 1`，用过示例数据的路由在顶栏显示「示例数据」。示例库只在内存里，刷新页面就复原。全部 handler 删完后删掉 `web/src/mocks/`。
- **演示事件和真实 SSE 走同一个分发器**（`api/events.ts:dispatchEvent`）：MSW 模拟的运行、安装进度通过它推 `product.updated`、`version.created`、`setup.progress` 等事件，接真实后端时页面代码不改。
- **界面文字和内容分开**：状态、类别、原因等枚举由接口返回 code，前端翻译；日志和提示句子返回 `code + params`；小说、剧本、提示词、人名等用户内容原样显示，不翻译。
- **SPEC 9.1 增补的读接口**（9.1 只列了写接口和部分读接口，页面需要）：`GET /series/{id}/episodes`、`GET /episodes/{id}/progress`（导航徽标）、`GET /series/{id}/novel`、`GET /series/{id}/suggestions`、`GET /episodes/{id}/script`、`GET /episodes/{id}/shots` + `PATCH /shots/{id}`、`GET /products?owner=&component=`、`GET /config/components`、`GET /episodes/{id}/timeline` + 片段 / 字幕的 `PATCH`、`GET /episodes/{id}/export/checks` + `POST /episodes/{id}/export`、`GET /sync/board?episode=`。字段以 `web/src/api/schemas/` 为准，M0.5 收尾时同步写进 SPEC 9.1。
- **依赖版本**：MSW 用 2.14.7 而不是刚发布两周的 3.x；zod 4.6.4、Playwright 1.63.0、d3-scale 4.0.2、d3-shape 3.2.0，全部精确锁定。`msw` 的安装脚本（只是复制 worker 文件）在 `pnpm-workspace.yaml` 里显式禁用，`public/mockServiceWorker.js` 由 `msw init` 生成后进 git，lint 和 prettier 都忽略它。
- **「示例数据」标记按路由记**：`api()` 收到带 demo 头的响应时，记在当前路由上（壳层用 `useLayoutEffect` 先登记路由，子组件后发请求）。顶栏本身（剧名、规格、花费）也用示例数据，所以 M1 / M8 接上真实接口之前，每个页面都会显示这个标记。
- **Playwright 自带服务**：`pnpm e2e` / `pnpm shots` 用 webServer 自己起 Mock 后端（端口 8765，临时 `DRAMA_HOME`，空 `.env`）和 Vite（5183），不碰开发者正在跑的 5173 / 8000。为此后端新增 `DRAMA_WEB_ORIGINS`（逗号分隔，只接受 `http://127.0.0.1:<端口>` / `http://localhost:<端口>`，否则启动报错），追加到 CORS 和 `LocalOnlyGuard` 的允许来源。
- **修了一个 M0 的 SSE bug**：浏览器每次切页面都会断开 SSE，Starlette 用 anyio cancel scope 取消流，如果正好在 `EventBus.replay` / `last_id` 读库，aiosqlite 连接会被弄坏（之后请求 500「no active connection」，或者卡死）。两个读操作改为 `anyio.CancelScope(shield=True)` 读完再响应取消；引擎再加 `pool_pre_ping=True` 兜底。`tests/unit/test_events.py` 有回归测试（修复前会卡死，现在加了 30 秒超时）。Playwright 冒烟最先暴露这个问题（7 轮里出现 2 次 500）。
- **Toast 用 sonner**，不照抄原型的行内提示条（SPEC 16.2 只要求「Toast 反馈每个操作的结果」）。
- **原型截图**：原型依赖画布运行时，仓库里没有。截图时从 Kelvin 的 artifact「短剧工作台原型」取 `dc-runtime.js` 放在临时目录当 `support.js`，本机渲染后用 Playwright 截；运行时不进仓库，只提交截图。
- **截图格式**：JPEG、宽 1440 整页，中文亮色 + 中文暗色进 git（`docs/studio/reports/ui/`）；英文截图按需生成，不进 git。原因：控制仓库体积，PNG 整页图太大。
- **产物接口补充（M0.5 第 4 步，SPEC 4.2 / 9.1 没写的部分）**：`GET /products/{id}` 除版本列表外还返回 `prompt`（下次运行用的意图层 / 编译层 / 是否手改 / 编译时的目标模型）、`estimate`（按当前路由重跑一次的预计花费和耗时，按钮上显示）、`running`（正在跑的任务 id 和模型，刷新后也能显示「正在用 X 生成…」）。新增 `PUT /products/{id}/prompt`（「只保存」，`compiled: null` 表示自动编译）、`POST /products/{id}/compile`（意图层改动时预览编译层，前端 300 ms 防抖）、`POST /products/{id}/unlock`（素材页的解锁；锁定仍是 `/lock`）。版本的 `note` 只放用户写的备注，「初版 / 重跑 / 改提示词后重跑 / 不满意换一个」由前端按 `origin`、`n` 和父版本的提示词推出来（`lib/versions.ts:originLabel`）。
- **手改过的编译层什么时候保留**：普通「重跑」沿用已保存的手改编译层；「不满意换一个」总是按目标模型重新编译（SPEC 7.4「按目标模型重新编译」），手改不跟过去。
- **示例里的运行不发 `job.updated`**：MSW 的 `POST /products/{id}/run` 返回一个 Job，但不推到任务列表——`/jobs` 是真实后端的，混进假任务会让顶栏 GPU 状态和开发面板失真。
- **示例时间按本机时区的钟点生成**（`fixtures/demo/products.ts:demoAt`）：界面按看的人所在时区显示时间，示例数据要在任何时区都显示原型里的 09:41 / 10:02 / 10:05。
- **运行设置、影响范围、闸门的接口细节（M0.5 第 5 步）**：`GET /config/components` 返回 `{components, models, local_runtime_ok}`，组件带 `api_models`、`local_models` 和 `unavailable`（运行位置 → 原因 `code + params`，前端翻译；没有本地 / API 模型的原因前端也能自己推）。`GET /config/resolve` 的 `sources` 逐字段给出 `preset / project / component / item`；兜底配置多一个 `timeout_s`（「超过 N 分钟没结果」用它）。`PUT /config/override` 在 Inspector 里按「有 item 写 item，否则写 component」，返回重新解析后的结果。组件名和说明是固定 id，前端用 `enums:component.<id>` / `componentDesc.<id>` 翻译，不从接口取文案。
- **重跑用配置的路由，换一个从屏幕上的版本往后数**：「重跑」按组件当前配置的主用模型（本地 / 混合用本地模型，API 用 API 模型），所以在 Inspector 改了模型再点重跑就生效；产物的 `estimate` 每次读取时按配置重算。「不满意换一个」没指定模型时取当前版本之后的下一个。
- **影响范围**：`POST /impact/preview` 返回 `lines`（每行 `code + params + cost_usd + optional`，前端用 `components:impact.line.<code>` 翻译）、`unaffected`、`rerun_cost_usd`、`stale`（每一步会标几个「待更新」）。`POST /impact/apply {impact_id, action}`；`undo` 只是丢掉这次预览，页面在回调里自己恢复编辑前的内容。
- **闸门**：`POST /gates/{gate}/confirm|reopen` 的请求体是 `{scope_id: <episode id>}`，确认状态不单独提供读接口，用 `GET /episodes/{id}/progress` 里对应步骤的 `state`（`takes` → 生成、`export` → 后期）。确认后的按钮仍然能直接去下一步，旁边有「重新打开」。
- **密钥提示只在真实模式显示**：模型选择器里「未填密钥」取真实后端 `/providers` 的 `has_key`，但 `/health` 说是 Mock 模式时不显示——Mock 不需要密钥，满屏提示只会干扰。
- **小说页的接口（M0.5 第 6 步）**：`GET /series/{id}/novel`（段落带字符偏移）、`GET /series/{id}/suggestions`、`GET /series/{id}/bible`；建议的决定是 `POST /suggestions/{id}/accept|reject|reset|rewrite`（SPEC 只列了 accept / reject / rewrite；「撤销采纳」和「恢复」都回到未决定，所以加了 `reset`），外加 `POST /series/{id}/suggestions/accept-all`（「全部采纳」，跳过已忽略的）。建议的 `kind` 在 SPEC 的 motive / timeline / consistency / gap 之外加上补全组件的四类（appearance / lighting / inner_to_action / cliffhanger，原型的外貌 / 光线 / 心理外化 / 卡点）。重写后 `status=rewritten`，`rewrite_instruction` 和 `rewritten_by` 保留（采纳后也显示「已按要求重写」）；已采纳的建议重写后仍是已采纳。字数 = 原文 + 已采纳补写，前端算。
- **步骤页布局 `StepLayout`**：工作区 + 右侧整列 Inspector（宽 360 / 400），窄屏时 Inspector 排到下面。没用 sticky：Inspector 本身比视口高，sticky 会把下半截藏起来。
- **「导入 .txt / .docx」在 M0.5 置灰并说明原因**：原型里这个按钮没有行为，导入要后端（`POST /series/{id}/novel`，M2）。做一个假的导入只会让示例数据前后不一致。
- **剧本页的接口（M0.5 第 7 步）**：`GET /episodes/{id}/script` 返回 `scenes` + `lines`（SPEC 4.1 的字段，另加 `duration_s`、`overlay_shot`「叠在 1-06」、`mood`、`cliffhanger`、`edited`；场景头文本放 `scene.heading`）。分集多了 `scene_from` / `scene_to`、`shot_count`、`script_status`（none / draft / confirmed）。「重写这一段 / 换模型重写」是 `POST /lines|scenes/{id}/rewrite {model?}`，只返回建议文本 `{text, model_key}`，不落盘。
- **改已确认内容一律「先预览、后落盘」**：保存或重写后先 `POST /impact/preview {kind: line_edit | scene_edit, target_id, patch: {text}}`，弹窗打开期间页面只在本地显示新文字（标「已修改」）；选「只标记 / 自动重跑」时由 `/impact/apply` 写入改动并标记下游，选「撤销」什么都不写。预览没有任何影响行时直接按「只标记」写入。这样 SPEC 9.1 的 `PATCH /lines/{id}` 不再需要单独的「返回影响范围」语义——M2 实现时可以保留 PATCH 给未确认的剧本用。
- **分镜页的接口（M0.5 第 9 步）**：`GET /episodes/{id}/shots`、`PATCH /shots/{id}`（类型、景别、机位运动、时长、画面描述、声音做法、参考素材、站位、选中的关键帧、确认）。枚举用英文 code：`shot_type` continuous / same_scene_cut / scene_change（SPEC 原有），`framing` wide / medium / close / closeup，`camera_move` static / push / follow / pan，`audio_mode` native / tts / none（对应 SPEC 的 A / B / C）。站位 `blocking` 是 `[{id, kind, label, x, y}]`，坐标 0–1，机位也是其中一项。每个非连续镜头一个关键帧产物（3 张候选放在 `payload.candidates`）；连续动作用 `tail_from` 指定接哪个镜头的尾帧。确认镜头时，如果关键帧还没采纳，就采纳屏幕上的那一版。分镜完成数（3/9）按实际确认数算。图像候选的花费按候选张数算（关键帧 3 张、参考图 4 张）。
- **成片规格页的接口（M0.5 第 12 步）**：`PUT /series/{id}/spec` 收部分字段（平台、画幅、交付档、帧率、每集时长、字幕、另出一版），返回带 `dims` 的完整规格；规格已锁定（`locked_at`）时直接改画幅返回 409 `spec_locked`，必须走 `/impact/preview {kind: spec_aspect, target_id: <series>, patch: {aspect, platform}}` + `/impact/apply`，「标记 / 自动重做」时由 apply 写入画幅。新增 `GET /spec/presets`（平台预设 + 每种画幅的 1080p / 2K / 768p 草稿尺寸，页面在保存前就能显示尺寸，尺寸仍只由后端 `spec/dims.py` 算）和 `GET /series/{id}/spec/compat?aspect=`（SPEC 13.3 兼容表：`{stage, model_keys, status: native|convert|unsupported, how: code+params}`）。页面上的改动先放在本地草稿，点「保存规格」才写；画幅的影响范围没处理完时保存被拦下。平台遮挡区的比例先写在前端（`pages/spec/SafeAreaPreview.tsx`），SPEC 13.2 说以后可在设置里调，到时改成接口给。
- **首次启动页的接口（M0.5 第 13 步）**：`GET /setup/profile` 除 `machine` 外返回 `phase`（idle / scanning / scanned / installing / done）、`items`（清单每项：`group`、`name: {zh, en}` 直接取 setup-manifest.yaml 的双语名、检测状态 `status`、`found` / `fix` 用 `code + params`（前端 `setup:found.<code>` / `setup:fix.<code>` 翻译）、`required`、`installable`、`install: {state: queued|running|done|failed|skipped, pct, error}`）、上次安装请求 `install: {mirror, dir, items}`、`default_dir` 和推荐预设 `recommendation: {preset, reason: local_video|no_cuda}`。`POST /setup/scan`、`POST /setup/install {items, mirror, dir}`（SPEC 只写了 `{items, mirror}`，页面上有「安装位置」，所以加 `dir`）、`POST /setup/items/{id}/retry|skip` 都返回 202 / 200 + 整个 profile；扫描或安装进行中再请求返回 409 `setup_busy`。进度走 `setup.progress {phase, item}`（前端直接写进 profile 缓存，阶段结束时再拉一次），日志走 `setup.log {level, code, params}`（`params.item` 是项 id，前端换成名字），日志只在页面里累积、不提供读接口。失败项不自动跳过：行内给「重试 / 跳过」（原型是失败后自动跳过）；示例里 SageAttention 每次都在 60 % 失败。重新检测时已装好的项报「已安装 · 通过」（SPEC 12.2「只补差异」）。「示例机器」切换是演示专用的 `POST /demo/setup/machine`，只在 `VITE_DEMO_DATA` 开着时显示，后端不实现。示例数据从「还没检测」开始（`scanned_at: null`，和原型首屏一致）；SPEC 16.1「未完成扫描时自动跳转到 /setup」留到 M1 接真实后端时做，否则示例项目每次打开都会被跳走。
- **模型与兜底页的接口（M0.5 第 14 步）**：SPEC 9.1 的 `POST /config/preset` 改成 `GET / PUT /config/defaults {preset, fallback_notify}`：「兜底时怎么做」也是全局默认，和预设放一起。预设不存成一份份配置，而是解析时按 `presetConfig()` 现算（照原型 `presetCfg()`：质量优先 = 第一个 API、本地兜底；均衡 = components.yaml 的 balanced；省钱 = 本地优先、兜底到 `cheap_api`；全本地 = 只用本地，没有本地版本的组件 `mode: off`）。`mode` 因此多一个 `off`（`ConfigModeSchema`；运行位置仍是 local / api / hybrid 三个）。「已手动改过，不跟随预设」= 这个组件有组件级覆盖（`sources` 里有 `component`），和各步骤 Inspector 写的是同一层；新增 `DELETE /config/override?scope=&component_id=&scope_id=`（「恢复成预设」）。表格每行用 `GET /config/resolve?component=` 各取一次（19 个组件，不加批量接口）。「本集 API 预算」用 SPEC 已有的 `PATCH /episodes/{id} {budget_usd}`，顶栏跟着变。密钥 chips 只列真实 `/providers` 里需要密钥的写作类服务（M0 只有这些），点开是密钥弹窗：保存 / 删除（只有钥匙串里的能删，环境变量的提示去改 .env）/ 测试连接，都走 M0 已有的接口；图像、视频、配音服务的密钥等接入对应模型时再加。示例组件目录按 components.yaml 的顺序，补了 `world`（3D 场景，只有 API，均衡下 `off`）和 `ctrl`（结构控制，只有本地），表格共 19 行（原型 17 行，没有素材分析和音效）。
- **同步页的接口（M0.5 第 15 步）**：`GET /sync/targets` 返回 `{targets, rules, preview}`：目标带开关、方向（ComfyUI 双向，其余单向）、检测结果 `state: ok|warn|missing` + `status`（code+params）、达芬奇的 `mode: fcpxml|api` 和 `unavailable_modes`（免费版不能用 `api`，原因 code+params）；规则是 `when`（adopt / every / manual，对应 SPEC 14.1 的三种触发）、`kinds`（9 类）、`org`（shot / type）、`extras`（提示词、模型和花费、质检分）；`preview` 是按当前布局算出的示例路径，由后端的布局代码给，前端不拼路径。`PUT /sync/targets` 收部分字段（`targets: [{id, enabled?, mode?}]`、`rules`），每次改动立即保存（原型没有保存按钮）；没检测到的目标开不了（409 `sync_target_missing`），不可用的模式 409 `sync_mode_unavailable`。新增 `POST /sync/targets/{id}/detect`（「重新检测」，返回这个目标）。`POST /sync/run {episode_id}` 返回 `{run_id, state, done, total}`，进度走 `sync.updated`（同样的字段），完成后同步记录多一行、发 toast。`GET /sync/log` 每行 `{at, what: code+params, to: [code+params]}`。`GET /sync/board?episode=` 给出素材板的分组、节点、连线和坐标（就是后端要写进 ComfyUI 工作流的那份布局），节点标题、便签和事实的值是内容原样显示，分组名、缩略图下的状态、事实的键是 code；「尺寸」那一行由成片规格算出（硬规则 10）。画布照 ComfyUI 的样子在两种主题下都是深色，连线颜色按数据类型写在 `pages/sync/Board.tsx`。
- **数据看板的接口（M0.5 第 16 步）**：`/metrics/kpis|spend-series|calls-series` 和 `/metrics/summary` 一样带 `?scope=episode&episode=<id>` 或 `?scope=series&series=<id>`。`kpis` 返回原始量（秒数、次数、成功 / 取消、限流重试、质检通过 / 总数、自动重跑 / 兜底 / 手动换模型、中位采纳时长、最慢未采纳镜头），文字和成功率由前端算和翻译。`spend-series` 每桶带 `start / end / add_usd / cum_usd / items`，`items` 是「花在哪」的 `code + params`（`component*` 参数是组件 id，前端走 `enums:component`；`cost` 等参数是美元数）；整体带 `start / now / end`（预测虚线从 now 画到 end）、`projected_usd`、`budget_usd`。`calls-series` 每桶 `counts{text,image,av}`、`failed`、`cost_usd`，另给 `totals` 和总调用 / 成功数。「今天」范围（SPEC 11 开头）原型里没有，M0.5 不做。
- **数据看板下半部分的接口（M0.5 第 17 步）**：`/metrics/shots` 返回 `scenes` + `shots`（每镜 `stage_seconds{kf,vid,post}`、花费、候选数、`status` adopted / picking / generating / queued / waiting、`waiting_for`、`notes` 和 `take_chain` 都是 code+params，`issues` 参数是逗号分隔的质检问题 code，前端走 `enums:qaIssue`）；`/metrics/components` 每组件 `local_seconds` / `api_seconds`；`/metrics/speed` 带 `example_output_s`（「4 秒约 7.5 分钟」）、每行 `where` + `price`；`/metrics/apis` 每行 `usage` 是 code+params、`prices` 是 `Price[]`、`note` 可空，另给 `total_cost_usd`；`/metrics/local-models` 带 `vram_total_gb`（满格），每行 `components` 是组件 id；`/metrics/qa` 的原因直接用 `QaIssue`（五项分开，原型把颜色和灯光合成「与描述不符 2」）；`/metrics/episodes` 总是全剧，合计行由前端加；`/metrics/export.csv` 是 `text/csv`，前端 `apiBlob()` 取回后用 object URL 触发下载。这些明细接口在示例里两个范围返回同一份（只有第 1 集有数据，范围说明里写了）。
- **暗色图表色换成 dataviz 校验过的一组**：原来的暗色分类色（`#5b9ae6` 等）亮度超出暗色带（OKLCH L 0.48–0.67），换成 `#3987e5 / #d95926 / #199e70`（在暗色卡片 `#1b1c20` 上分类色五项检查全过）；暗色顺序色改为 `#1c5cab / #3987e5 / #9ec5f4`（越多越亮）。亮色不变（SPEC 11.3 的值）。另加 `--chart-grid`、`--chart-crosshair`、`--chart-track`。
- **Vitest 固定时区 `Asia/Shanghai`**（`vitest.config.ts` 的 `test.env.TZ`），和 Playwright 一致：示例时间是 +08:00，测试里断言的时刻和原型一样。
- **i18n key 里不能有冒号**：i18next 把 `:` 当命名空间分隔符，`aspect.name.9:16` 会查错地方。画幅在词表里写成 `9x16`（`pages/Spec.tsx:ak`）。
- **后期页的接口（M0.5 第 11 步）**：`GET /episodes/{id}/timeline` 返回 `{duration_s, clips, audio, subtitles}`。画面轨的片段由镜头时长首尾相接算出（分镜里改时长，时间线跟着变），`version_id` 是采纳的候选，null 就用关键帧占位；片段设置 `trim_head`（SPEC 5.1 裁开头 0.3 秒，默认开）、`transition`（cut / dissolve / dip_black）、`dialogue_volume` / `ambience_volume`（0–100，按片段存）用 `PATCH /clips/{id}` 改，返回整条时间线。音频段 `{track: dialogue|ambience|music, label, source: native|dub|sfx|music, shot_id, component_id}`，标签是内容原样显示；字幕 `{text, line_id, edited}`，`PATCH /subtitles/{id} {text}`，和剧本原文不同时 `edited=true`（输入时预览和时间线先跟着变，失焦才保存）。`GET /episodes/{id}/export/checks` 返回 `[{status: pass|warn|fail, message: code+params}]`；`POST /episodes/{id}/export {format: mp4|fcpxml|otio|srt}` 返回 Job（示例里不进任务列表）。示例库里音频和字幕挂在镜头上（镜头 + 偏移 + 时长），所以和镜头时长一起动。
- **新增「音效」组件 `sfx` 和产物 slot `sfx`**：原型后期页有「音效」组件（MMAudio 本地 / ElevenLabs 音效），SPEC 第 5 节的组件表和 4.2 的 slot 列表里没有，M7 实现时补进 components.yaml 和 SPEC。
- **后期页没有闸门按钮**：原型的后期页头部没有「确认……」按钮，导出就是这一步的结束；`export` 闸门留给 M7 决定是在导出成片时自动确认还是另加按钮。
- **生成页支持 `?shot=1-04`**：后期页「换一条候选」带着镜头号跳过去，直接打开那个镜头的候选墙。
- **生成页的接口（M0.5 第 10 步）**：每个镜头一个视频产物（`slot=video`，`shot.video_product_id`），一个版本就是一条候选（SPEC 4.2）。版本加四个字段：`qa`（`{checks: [{metric: face|lipsync|asr|ocr|vlm, value, text, issue, ok}], score}`，`ok: null` 表示这项不适用；OCR 读出的字和视觉模型的发现是模型原话，放 `text` 原样显示，`issue` 是分类 code）、`fallback_reason`（error / timeout / qa_fail，对应 `model_call.fallback_reason`）、`stage`（混合模式的 draft / final）、`rating`（数字键打分 1–5）。新增 `POST /products/{id}/unadopt`（「取消采纳」，锁定时 409）、`PATCH /versions/{id} {rating}`、`GET/PUT /series/{id}/generate-rules`（每镜候选数、质检不过自动重跑次数、单镜上限、只读的质检阈值；M5 实现时分别对应 components.yaml 的 `candidates`、视频组件的 `fallback.qa_fail_n`、`budget(scope=shot)` 和质检组件的 `thresholds`）、`GET /episodes/{id}/generate-log`（运行记录，`code + params`，`params.model` 是模型 key，`params.cost_usd` 是数字，前端格式化）、`POST /versions/{id}/upscale`（2K 精修，返回 Job；示例里只弹提示，不进任务列表）。「推荐」= 质检通过且 `score` 最高的一条（同分取后出的），已采纳后不再显示。连续镜头的首帧镜头没采纳时，`POST /products/{id}/run` 返回 409 `upstream_not_adopted`。候选卡上的说明（自动重跑、兜底原因、不满意换一个、混合出终版）由前端按 `origin` / `fallback_reason` / `stage` 推出（`lib/takes.ts:takeNote`）。生成完成数（导航 3/9）按有采纳候选的镜头数算。
- **生成页的队列卡**：数字（运行中 / 排队）取真实 `/jobs`，所以示例里显示「空闲」；下面一行「正在跑 1-05 T1」取视频产物的 `running`。原型写的是「运行中 1 · 排队 2」，这是计划里已知的差异。排队中的产物 RunBar 显示「排队中 · 模型」，按钮不可用。
- **素材页的接口（M0.5 第 8 步）**：`GET /series/{id}/assets`（`status` 由素材的产物推出：锁定 / 有候选 / 没生成）、`PATCH /assets/{id}`（描述 = 产物提示词的意图层，改了下次重跑生效；`pick`；画面文字的 `exact / method / style`；音色来源）、`POST /assets/{id}/lock`（采纳屏幕上的那一版并锁定）、`POST /episodes/{id}/assets/analyze`。解锁不单独开接口：走 `/impact/preview {kind: asset_unlock}` + `/impact/apply`，和剧本改动同一条路。候选放在版本的 `payload.candidates` （画面文字带 OCR，音色带说明和波形）；`files[]` 等 M3 有真文件再用。素材的完成数（导航 7/13）按实际锁定数算。价格多一种单位 `mchar`（每百万字符，TTS）。
- **分集卡用路由切换**：点一集跳到 `/s/:series/e/:n/script`，顶栏的集名、导航徽标都跟着这一集走；原型是页内切换。每集的剧本是一个 `owner_type=episode` 的产物，「生成这一集的剧本」就是对它 `run`。

## 2026-10-14 · M0 合并前补充（Kelvin 审阅后）

- **本机接口防护**（`api/security.py:LocalOnlyGuard`，对上游 `/api` 和新 `/api/v1` 都生效）：Host 头只接受 `127.0.0.1` / `localhost` / `[::1]`（否则 421 `host_not_allowed`，防 DNS 重绑定）；所有非 GET 请求必须带 `X-Drama-Studio: 1`（否则 403 `missing_client_header`），带了 `Origin` 的必须是本机前端（否则 403 `origin_not_allowed`）。不带 Origin 的非浏览器客户端（脚本、将来的 ComfyUI 节点包）加上这个头即可。CORS 只放行 `content-type`、`x-drama-studio`、`last-event-id` 三个请求头。
- **上游设置接口不再返回密钥**：`GET/PUT /api/series/settings` 和 `/settings/reset` 的密钥字段一律清空，改给 `api_key_set` / `comfyui_api_key_set` / `runninghub_api_key_set`；保存时密钥字段为空表示「保留原值」。选择改返回值而不是摘掉路由，是为了 `/legacy` 的设置面板还能用。
- **上游直接调模型的 5 处只能经 `/legacy` 触发**：都只被上游 `/api/series/*` 路由（`/legacy` 界面在用）或上游 `drama-series-render` 命令行调用；`tests/unit/test_isolation.py` 用 AST 检查新代码不导入这些模块（例外：纯函数 `normalize_base_url`、挂载上游路由的 `router`）。`/legacy` 顶部常驻警示条。
- **Mock 模式标记**：`GET /api/v1/health` 返回 `mock`，顶栏在 Mock 时显示琥珀色「Mock 模式」。
- **PowerShell 一律加 `-ExecutionPolicy Bypass`**：这台机器的执行策略禁止 `powershell -File` 运行脚本，状态栏、两个钩子和 `start.ps1` 原来的写法都会直接失败。`Bypass` 只对那一个进程生效，不改系统设置。
- **启动脚本**：`start.ps1` / `start.sh` 改为 `uv sync` + `corepack pnpm -C web install --frozen-lockfile`，再启动 `uv run drama-studio dev` 和 `pnpm -C web dev`；后端固定监听 127.0.0.1（去掉了 `--host`），`--port` 通过 `DRAMA_BACKEND_URL` 同步给 Vite 代理；`.env` 逐行解析而不是 `source`。

## 2026-10-14 · M0 前端工具链

- **pnpm 替换 npm、ESLint 替换 oxlint**：CLAUDE.md 约定的命令是 pnpm；ESLint 能写「JSX 里禁止中文字面量」这条规则（`no-restricted-syntax`），落实硬规则 4。pnpm 12 默认拦截依赖的安装脚本，`web/pnpm-workspace.yaml` 只放行 esbuild。
- **TypeScript**：`strict` + `noUncheckedIndexedAccess`。上游界面过不了，**挪到 `web/src/legacy/` 并整文件 `// @ts-nocheck`**，ESLint 也忽略它；M2 新页面做完后整个目录删除。
- **shadcn/ui 组件手写进 `src/components/ui/`**（按 new-york 风格，`components.json` 留着以后用 CLI 加组件），颜色全部来自 `styles/tokens.css` 的 CSS 变量；暗色是单独挑的一套。
- **JSON 文件没法写注释**：改过的上游 `web/package.json`、`tsconfig*.json` 不加文件头说明，在 NOTICE 的总说明里覆盖。

## 2026-10-14 · M0 模型层

- **Mock 是默认模式**：没设 `DRAMA_MOCK` 也走 Mock，只有 `DRAMA_MOCK=0` 才调真实模型。原因：硬规则 2「开发默认用 Mock」，防止误花钱。Mock 保留真实模型的 key 和单价，Mock 模式下的花费数字和真实调用一致。
- **兜底只跳一次**：失败后换到 `fallback.to`（为空取 `alt_order` 第一个没试过的），再失败就报错。原因：沿着整个备选列表一路试下去，坏天气里花费会成倍增加；要再试由用户点「不满意换一个」。未知模型、预算超限不触发兜底。
- **每次尝试一行 `model_call`**：失败、超时、取消也记（`billed=false`、`cost_usd=0`，厂商明确计费的错误除外）。
- **`api:<provider>` 队列名取模型的 `provider_id`**：LLM 用 providers.yaml 里的供应商 id（如 `deepseek`），媒体和本地模型取 key 的前缀（如 `minimax`、`comfy`）。
- **OpenAICompatAdapter 用 httpx 直连**，不用 openai SDK：重试、错误码、流式都要自己控制，且便于 respx 测试；URL 规范化复用上游 `utils/llm_client.normalize_base_url`。
- **密钥查找顺序**：系统钥匙串（服务名 `drama-studio`，条目名 = `key_name`）→ 环境变量 → `.env`。`GET /providers` 返回 `has_key` 和 `key_source`（keyring / env / none），不返回密钥。所有 loguru 日志经过打码（Authorization、api_key、`sk-…`，以及本进程读到过的密钥原文）。测试里 `DRAMA_ENV_FILE` 指向空文件，不会读到开发机上的真实 `.env`。
- **开发接口 `/api/v1/dev/*`**：`llm-test` 只在 Mock 模式可用（否则 403 `mock_only`），给前端 `/dev/jobs` 面板和 M0 验收用。

## 2026-10-14 · M0 任务队列

- **只有处理器明确抛 `JobError(retryable=True)` 才自动重试**（到 `max_attempts` 为止）；其他异常直接失败，错误写 `error_json = {code, params}`。原因：模型调用的重试、兜底在 `router.call()` 里做，队列再盲目重试会重复花钱。
- **崩溃后续跑也算一次尝试**：启动时 running → queued；已经用完 `max_attempts` 的判 `failed`（`interrupted`），避免一个会搞崩进程的任务无限循环。**正常关闭**时运行中的任务也放回 queued，下次启动接着跑。
- **API 错误统一为** `{"detail": {"code", "params"}}`（`api/errors.py:ApiError`），前端按 code 翻译。

## 2026-10-14 · M0 数据库与配置

- **数据目录** `DRAMA_HOME`，默认 `~/.drama-studio/`：`studio.db`、`blobs/`，和 `envs/` 放在一起。测试里每个用例一个临时目录。
- **M0 只建本期用到的表**（`job`、`model_call`、`config_override`、`provider_account`、`custom_model`、`event`）；`series`、`product` 等由各自里程碑的迁移加。迁移在后端启动时程序内执行（`core/db.py:migrate`），迁移脚本放在包里（`core/migrations/`），只用 `sa.*` 类型，不依赖业务代码。
- **`job` 表比 SPEC 多两列**：`result_json`（任务输出，例如 LLM 结果）和 `depends_on_json`（SPEC 9 的任务依赖）。**新增 `event` 表**：持久化 SSE 事件，支持 `Last-Event-ID` 补发，保留最近 N 条。
- **配置的四级来源**：`factory`（components.yaml，按「均衡」预设推出默认值）→ `project` → `component` → `item`；`config_override` 的 `scope` 取后三个值，`component_id` 为空的 project 行对所有组件生效。嵌套字段按点路径逐项合并并记录来源（例如 `fallback.to`）。
- **SSE**：事件名用 `event:` 字段（前端按类型 `addEventListener`），数据是 JSON；除 `Last-Event-ID` 头外也接受 `?after=<id>`（浏览器 EventSource 首次连接带不了这个头）。不带 id 时只推新事件。
- **YAML 只把 true/false 当布尔**：YAML 1.1 的 `on/off/yes/no` 会把 `fallback.on`、`mode: off` 读坏。

## 2026-10-14 · M0 工具链

- **ruff / mypy 先只覆盖新代码**（core、modelhub、api/app.py、studio_cli 等）；上游模块在 `pyproject.toml` 里排除，改到哪个上游文件就把它纳入检查。原因：上游没有类型标注，一次性修完会大面积改上游文件，偏离「包一层适配，不推倒重写」。
- **`requires-python >=3.12`**，用 uv 管理（`.python-version` = 3.12）；保留 setuptools 构建和上游两个命令行入口，新增 `drama-studio`。
- **新 app factory `api/app.py:create_app()`**：上游路由原样挂在 `/api`，新接口在 `/api/v1`；CORS 只允许 `127.0.0.1:5173` / `localhost:5173`（上游是 `*`）。

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

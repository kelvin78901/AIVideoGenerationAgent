# 工程决定记录

新的决定加在最上面：日期、决定、原因、影响。

## 2026-10-28 · M5 第 13b 步：示例 ComfyUI 能装坏、能回滚；工作流库的端到端测试

- **示例机器多两个「社区」工作流**（`wflib/demo/workflows/社区/`，在 ComfyUI 列表最上面）：`图生视频-wan22.json`（Wan 2.2 图生视频的写法，缺 ComfyUI-VideoHelperSuite，装上就能体检通过、试跑、升「我的工作流」）；`胶片颗粒-filmgrain.json`（缺示例坏包 ComfyUI-FilmGrainFX，地址用 `example.com`，一看就是假的）。示例 `object_info` 补核心节点 `WanImageToVideo`。
- **坏包怎么坏**：`node_map.json` 里那个包的元数据带 `demo_breaks: ["KSampler"]`；`DemoComfy.install(snapshot, packs)` 加上包的节点类、拿掉它弄坏的类，并记下装之前的样子；`DemoComfy.restore(snapshot)` 退回去。示例坏包是我们自己的约定，真实 Manager 的节点表没有这个键。
- **回滚后重新体检**：`POST /comfy/snapshots/{id}/restore` 排上回滚后调 `WorkflowLibrary.restored(manager_name)`：示例机器立刻复原并全部体检；真实 ComfyUI 要重启才生效，仍由下一次扫描核对（SPEC 6.4.1），这里什么都不做。
- **「装后变坏」的提示带快照 id、会一直挂着**：`broke_after_install` 的参数加 `snapshot_id`（界面的「回滚到这次安装前的快照」要用）；之前只在「上次正常、这次坏了」那一次体检里出现，再点一次体检就没了。现在上次已经带着它、这次还没好，就继续带着，回滚或修好为止。
- **界面**（第 13c 步）：之前模型页工作流详情只列缺的节点包和模型，`problems` 一条都不显示。现在「体检」页签多一节「问题」（`workflows:problem.<code>`：`binding_broken`、`unknown_node`、`broke_after_install`），`broke_after_install` 下面有「回滚到这次安装前的快照」：先在原地说明（Manager 下次启动 ComfyUI 时执行、不替你重启），确认后调回滚接口，刷新工作流库和快照列表。没用弹窗：只有一个按钮、一段说明，和「环境与安装」里的快照回滚同一个接口。第 13d 步做 Playwright `m5` 和截图。

## 2026-10-28 · M5 第 13a 步：Mock 照真实适配器记钱、记工作流；生成的端到端测试

- **Mock 按真实适配器的价档记钱**：视频按秒计价的模型（`price_by_res`）由真实适配器按画面挑价档（H3：短边超过 768 用 2K；Seedance：短边够得着的最高档）。Mock 以前拿 `params.resolution` 查表，API 出片时那是交付档（如 `1080p`），表里没有 → 0 元。现在两家适配器把挑档抽成模块函数 `resolution_tier(spec, params)`，Mock 按 `spec.adapter` 调同一个（`mock.billed_tier`），用量里带上 `resolution`，估价和记账都按它。示例种子的花费是写死的，快照没变。
- **Mock 也记工作流和哈希**：本地 ComfyUI 模型（`runtime: comfyui` 且有 `workflow`）的 Mock 结果带 `raw["comfy"]`（工作流 id、`workflow_sha256`，`comfy_env_hash` 为空），和 `ComfyUIAdapter` 一样，`model_call` 和版本就都有了。验收要求「本地的带工作流哈希」，Mock 下以前是空的。
- **端到端测试从示例剧开始**（`tests/e2e/test_storyboard_to_takes.py`）：后端在 Mock 下启动时自己种示例剧（分镜已确认、1-01–1-03 已采纳、1-04 四条待挑），所以 M5 的验收不再从导入小说走起（M4 那条已覆盖）。`model_call.version_id` 对视频仍是空的（调用时版本还没建，M4 起就这样），测试按 `job_id` 对上。
- 第 13 步拆成三小步：13a 这一步、13b 导入社区工作流和装坏节点包回滚的端到端、13c Playwright `m5` 和截图。

## 2026-10-28 · 估价不再嵌套开会话（CI 的 e2e 卡住的主因）

- **原因**：第 12a 步起，`RunService.describe`（每个产品的 GET 都要算估价）在自己的会话里调 `choose_model`，选工作流又开一个会话读规则表：一个请求同时要两个连接。后期页、看板一次拉几十个产品，连接池（SQLAlchemy 默认 5 + 10）被每个请求的第一个连接占满，大家都在等第二个，等满 30 秒超时。本机并发 36 个视频产品的 GET：修之前 30.5 秒后 `QueuePool limit … reached`，修之后 1.0 秒全 200（`test_workflow_select_api` 新测试）。
- **做法**：`describe` 先在会话里读输入和默认意图，关掉会话再选工作流、编译提示词（入队那条路径本来就是这样）。约定：**持有会话时不要调用会自己开会话的函数**（`choose_model`、`vselect.*`、组件里查缓存的那些）。
- 下面那条「会话屏蔽 anyio 取消」照样保留：它管的是「写到一半被取消、连接带着写锁留下」，CI 日志里那条报错还会不会出现，看这一轮。

## 2026-10-28 · 数据库会话不让 Starlette 中途取消（修 CI 的 e2e 卡住）

- **现象**：第 11 步起 CI 的 Playwright smoke 一轮比一轮红（后期页一直「正在加载」、检测一直「正在检测…」、SSE 没有任务更新），本机全过。e49a128 那轮后端日志在 smoke 页面测试期间报了 6 次「Exception terminating connection … CancelledError: Cancelled via cancel scope … by RequestResponseCycle.run_asgi」，之后读照常、写全卡住。
- **原因**：浏览器关页面时 Starlette 用 anyio 取消作用域取消流式响应（SSE），anyio 的取消是电平触发的；数据库语句执行到一半被取消，SQLAlchemy 当场终止连接，终止这一步又被取消，连接带着写事务和 SQLite 的写锁留下，后面的写全在等。本机用「写到一半时 `move_on_after`」复现出同一条日志并卡死（`tests/unit/test_db.py`）。
- **做法**：`Database.session()` 整段放在 `anyio.CancelScope(shield=True)` 里：会话里的工作做完、照常回滚 / 还连接，取消落到会话外的下一个 await。我们自己的代码不用 anyio 取消；任务队列的取消、`asyncio.timeout` 是原生 `task.cancel()`，屏蔽挡不住它们（验证过），所以只影响「客户端走了」这一种。只在关闭时屏蔽 `close()` 不够（试过：取消发生在语句执行中，轮不到 `close()`）。`core/events.py` 原来给两个 SSE 读单独加的屏蔽现在多余，留着不碍事。

## 2026-10-28 · M5 第 12c 步：按镜头选工作流的界面

- **规则表放「模型与兜底」**（组件表和工作流库之间，`pages/models/WorkflowRules.tsx`）：一行一条规则，六个条件各一个下拉（「不限」= 不写这个条件），右边选工作流（只列接口给的 `models`，存过但现在不能选的也留在下拉里）、上移 / 下移 / 删除；每改一处整表 `PUT`；改过的剧显示「本剧已改」和「恢复默认」（`DELETE`）。LLM 建议开关在表下面，默认关。模型页没有剧集路由，按「最近打开的剧，否则示例剧」（`useSeriesId`），说明里写明只对哪部剧生效。没有原型，按 M0.5 风格；1440 和 2000 px 都是一行。
- **「选了哪个、为什么」从视频版本读**：视频 take 的版本 `params.select` 存一份和 `model_call.select_json` 一样的内容（不另开接口，`GET /products/{id}` 本来就带 `params`）；命中规则时 `select` 多存规则本身 `when`（规则表之后可能被改，序号对不上）。示例种子的本地 take 也带上（1-04 的草稿是规则 1，1-01–1-03 是默认），前端快照 `generate.json` 重导，另加 `workflow_rules`。
- **Inspector**（`components/ShotWorkflow.tsx`，只在视频生成且有镜头时）：显示「最近一条本地候选」的选择——当前版本是本地的就用它，是 API 终版就看它的父版本（本地草稿），否则看最新一条本地 take；没有就说还没在本机出过片。下一条用哪个工作流读产品估价的 `model_key`（后端估价已经过规则表和手动选择），分支按这个工作流列；手动换仍然是上面 ModelPicker 的「本地模型」（item 覆盖），这里只给说明和「改规则表」链接（`/models#workflow-rules`，页面会滚过去）。
- **分支开关**：`CONFIG_FIELDS` 两边都加 `branches`，`/config/resolve` 的 `sources.branches` 是整张表最具体的那一层；开关写 item 覆盖 `{branches: {id: bool}}`，拨回默认值时写 `null`（回到默认），有手动值时显示「恢复默认」；没试跑过的分支带「没试跑过」标记但仍可开（禁用留到有带分支的仓库工作流时再定，见第 12b 步）。仓库工作流现在都没有分支，界面显示「没有可开关的分支」；页面测试用假工作流验证开关。
- 新错误码词条：`workflow_rule_model`、`workflow_unknown_branch`。

## 2026-10-28 · M5 第 12b 步：工作流里的可开关分支

- **`workflow.yaml` 的 `branches`**（`modelhub/workflows.py:Branch`）：`id`（开关用的名字）、`kind`（`controlnet` / `lora` / `upscale`）、`name`、`nodes`（关掉时拿掉的节点标题）、`bypass`、`default`（没人选时开不开）。关掉的分支在填图时和可选槽位一样拿掉：先把被旁路节点的读者接到它某个输入的来源上，再删节点和读它的输入。分支里不能有被绑定的节点（装载时报 `WorkflowError`）。
- **旁路按输出接**（`Bypass.output`）：LoRA 加载器两个输出（0 模型、1 CLIP），各自接回 `model` / `clip` 的来源；不写 `output` 时和以前一样所有读者都接过去（H3 的音频引导）。旁路的实现从「接完就删」改成先接线、最后统一删，同一个节点可以有多条旁路。
- **按镜头开关存成配置覆盖**（`ConfigPatch.branches: {id: bool | null}`，`null` 回到默认），不存 `shot.control_json`（计划原写法）：Inspector 本来就按镜头写 item 覆盖（换模型也是），还白得组件级默认开关；`control_json` 留给控制视频的设置。开关按分支 `id` 认，不分工作流（「这个镜头用 ControlNet」对哪个工作流都是一个意思）。`/config/resolve` 的 `sources` 里加 `branches` 要改前端契约的 `CONFIG_FIELDS`，和界面一起在 12c 做；现在 `values.branches` 已经有。
- **视频 take 的请求带 `params.branches`**（只有本地工作流有分支时）：按 `branch_states(镜头 / 组件的选择)` 算出每个分支开关，ComfyUI 适配器填图时用；它在请求参数里，所以也进媒体缓存键（换开关不会拿回旧片）。
- **每个分支单独试跑**：`POST /workflows/{id}/trial {branch}` 在示例输入上只开这个分支跑一次，结果存在 `trial_json.branches.<id>`，和工作流自己的试跑互不覆盖；工作流的试跑通过才更新文件哈希，分支试跑不动。`WorkflowOut.branches`（`id / kind / name / default / trial`），前端契约 `WorkflowBranchSchema`（默认空列表）。不认识的分支 422 `workflow_unknown_branch`。
- **没做的**：仓库里的推荐工作流现在都没有分支（H3 的 Turbo LoRA 要同时改步数，不是单纯开关，Kelvin 定留着以后做「快速草稿」档），所以开关暂时没有实际可开的对象；换 LoRA（选别的 LoRA 文件）、分支没试跑过时禁止打开，等真有带分支的工作流再做。导入的工作流不能自己定义分支（没有界面），只有仓库工作流在 `workflow.yaml` 里写。

## 2026-10-28 · M5 第 12a 步：按镜头选工作流（后端：规则表、LLM 建议、记进 model_call）

第 12 步分三小步：12a 规则表和 LLM 建议的后端，12b 可开关分支，12c 界面（规则表放「模型与兜底」、Inspector 显示选了哪个和理由、按镜头开关分支）和截图。
- **Kelvin 定（2026-10-28）**：LLM 建议在镜头第一次出片前自动问，开关默认关；默认规则表放一条「原生同步 + 有锁定音色样本 → `comfy/h3-r2v`」。原来写死在 `vid.model_for` 里的这条挪进表里（删掉表里这条，原生同步的镜头就走组件默认的 `h3-i2v`）。
- **先后顺序**（`pipeline/vselect.py`）：调用方点名的模型（「不满意换一个」、指定模型）和这个镜头在 Inspector 里手动选的（`local_model` 的 item 覆盖）→ 剧集规则表第一条命中的 → LLM 建议（开着、规则都没命中、能选的不止一个时）→ 路由的本地模型。规则在 LLM 前面：表是用户明说的，LLM 只补没写到的。路由是 API 模型时不选（只在本地工作流之间挑）。
- **能选的**（`pickable`）：视频组件 `local` 里有工作流的、不是「未验证」、这台机器跑得了的；规则指向的模型选不了就跳过这条。存规则时只查前三项（换机器不该让表存不进去）。
- **规则表按剧存** `app_setting` 的 `vid.select.<series id>`（和生成规则一样）；没存过读 `components.yaml` 的 `vid.select_rules` / `select_suggest`。条件：`shot_type`、`framing`（景别）、`dialogue`、`audio_mode`、`refs`（有锁定参考图）、`voices`（有锁定音色样本），不写的不限；多的字段 422。接口 `GET / PUT / DELETE /series/{id}/workflow-rules`（`DELETE` 回到配置的表；返回带 `saved` 和能选的 `models`）；规则的模型不能选时 422 `workflow_rule_model`。
- **LLM 建议**：新路由组件 `vselect`（视频工作流建议，默认 DeepSeek V4.1 Flash，单次上限 $0.05），在**入队时**问（不在任务里问：模型定了才能估价、排 GPU 队列、按模型分组）；估价只读缓存不问。告诉它镜头（景别、类型、时长、声音、台词条数、参考图张数、音色样本张数、画面描述）和候选工作流（名字、档位、是不是默认、最长秒数、参考图槽位数、收不收音色样本 / 台词音频），要 JSON `{model, reason}`，理由用剧的语言。答案按「模型 + 发出去的内容」缓存在 `llm_cache`：镜头或候选变了才再问。失败、超预算、答了不在候选里的 → 用默认，只记日志。Mock 下选收音色样本的（原生同步 + 有音色时），否则默认。
- **记进 `model_call.select_json`**：`CallContext.select`（`RunContext.select` ← 任务参数 `params.select`）；视频那次调用写 `{by: manual | rule | suggest | default, rule?, reason?, suggested_by?}`，提示词改写、Context-IR 这些不写；LLM 建议本身另有一行 `component_id = vselect` 的调用记录。
- **组件钩子** `Component.choose_model(...)`（异步，默认就是 `model_for`）：`runs.py` 的估价和入队都改走它。

## 2026-10-28 · M5 第 11 步：DramaStudio 节点包（工作流的输入 / 输出节点）

- **节点包 `integrations/comfyui-dramastudio`**（`nodes.py`，13 个节点，版本 0.1.0）：输入 首帧、参考图（带 `index`）、输入视频、台词音频、音色样本（带 `index`，对应 `ref_audio`）、提示词、反向提示词、尺寸（宽、高）、帧率和时长（一个节点：`fps`、`seconds`，另出 `fps_int` 和 `frames` = 帧率 × 秒数取整；要 4n + 1 帧的模型自己接数学节点）、种子；输出 视频（MP4）、图片（PNG）、音频（FLAC），存进 `output/dramastudio/`，列文件的格式和 ComfyUI 自带的 SaveVideo / SaveImage / SaveAudio 一样，适配器取结果不用改。文件输入像 `LoadImage`：下拉列 `input` 文件夹（含子文件夹，平台上传在 `dramastudio/`）、能上传，`VALIDATE_INPUTS` 只查文件在不在（平台刚上传的文件不在 ComfyUI 启动时的列表里），`IS_CHANGED` 按文件哈希。每个输入都有默认值，在 ComfyUI 里能直接手动跑。
- **用经典写法（`INPUT_TYPES`），ComfyUI 的模块在用到时才 import**：不用 V3 的 `io.ComfyNode`，这样节点定义在没有 ComfyUI、没有 torch 的测试环境里也能加载。存图片和音频借 `comfy_api.latest.ui` 的 `ImageSaveHelper` / `AudioSaveHelper`，读视频用 `InputImpl.VideoFromFile`，读音频用 `comfy_extras.nodes_audio.load`（和 `LoadAudio` 一样），存视频用 `VIDEO.save_to`。在本机 ComfyUI 0.41.2 自己的 Python 里逐个跑过（读图、参考图、存图、带声音的视频存出再读回、音频存出再读回；临时目录，没装进 ComfyUI、没发 `/prompt`）。
- **「不用写绑定」= 导入时按节点类自动生成绑定**（`wflib/dramastudio.py:NODES`，状态 `dramastudio`），照样写进 `workflow.yaml`，填值、取结果、可选槽位走同一套代码，没另开一条「按节点类型提交」的路。用了 DramaStudio 节点的工作流只认这些节点，不再猜别的（`LoadImage` 之类不绑定）；同一个槽位有两个节点取第一个；参考图 / 音色样本按节点的 `index` 编号，没有就接着往后排，并且是可选的（镜头的参考图比节点少，多的节点连同读它的输入一起拿掉）；其余文件槽位必需。重名的节点照猜绑定的规则改成唯一标题。认不出的 `DramaStudio*` 节点（M9 的镜头、素材、存回）不绑定。
- **体检认得我们自己的包**：缺 `DramaStudio*` 节点类时列成缺节点包「DramaStudio」（`source: studio`、版本取包里 `pyproject.toml`，前端契约 `MissingPack.source` 加 `studio`），不是 `unknown_node`。「安装缺的节点包」时它走安装清单的 `node_dramastudio`（`NodePackSource.item`，和其他节点包一起先存快照）。
- **安装清单 `node_dramastudio` 可装了**：去掉 `installable: false` 和 `dramastudio_pending`（中英文词条删掉），缺少时提示「安装节点」；步骤只剩复制（`copy`，版本 0.1.0，复制时跳过 `__pycache__`）；「写入本地令牌和后端地址」的 `script` 步骤等 M9 的存回节点再加。名字改成「DramaStudio 节点包」。它会改用户的 ComfyUI，所以和其他节点包一样列进改动清单、默认不勾、先存快照。PC 示例机器全选从 17 项变 18 项、改动 ComfyUI 的从 11 项变 12 项，装完后缺的只剩 H3、SeedVR2 两项（要升级 ComfyUI）。
- **没做的**：包的版本更新检测（检测只看目录在不在；重装会覆盖）留到 M9 加存回节点时一起做；节点的前端扩展（下拉选镜头等）M9。

## 2026-10-28 · M5 第 10b 步：工作流库前端接后端；试跑走任务事件

- **删 MSW 的工作流库**（`mocks/handlers/workflows.ts`、`fixtures/demo/workflows.ts`、`db.ts` 两项、`demoTiming.workflowTrialMs`）：示例模式下模型页的工作流库直接读 Mock 后端。页面测试改用 `test/fakes/workflows.ts`，数据是 `test_web_fixtures.py` 新导出的 `workflows.json`（仓库的 9 个工作流全部体检后 + 示例 ComfyUI 列表里的两个导入后的样子；体检、试跑的时间 `at` 也固定）。原来 MSW 里的「Wan 2.2（社区）」「Flux Kontext（社区）」「LatentSync（我的）」后端没有，测试改成用雨夜氛围-ltx2（缺节点包和模型）、sdxl_basic（绑定待确认、体检正常）和 FlashVSR（缺节点包）。
- **示例 ComfyUI 补节点类**（`wflib/demo/object_info.json` 加 38 个，只有名字、没有输入；`node_map.json` 加 1038lab 的 ComfyUI-FlashVSR）：以前仓库工作流在 Mock 下全是「坏了」（`unknown_node`：UNETLoader、CLIPLoader 都没有），接上后端后模型页会一片红。现在除 FlashVSR（缺节点包、可装）外都正常；H3 和 SeedVR2 节点按 ComfyUI 0.41 自带算。
- **试跑进度走 `job.updated`**：`useWorkflows` 不再每秒轮询；`api/events.ts` 收到 `workflow_trial` 的状态变化（不带 `progress` 的那种）就刷新工作流库；试跑中显示采样步数（`JobSchema.progress`，ComfyUI 的 `step` / `steps`，从任务列表缓存里读）。
- **装依赖只算节点包**：后端 `install_deps` 本来就只装节点包、模型文件留给用户放（第 3 步）。按钮改成「安装缺的 N 个节点包」，改动清单只列节点包，缺模型时提示自己放进 models 目录后重新体检；提示里带 `restart_required`（真 ComfyUI 要重启）和 `failed`。
- **仓库工作流的绑定只看不改**（写在 `workflow.yaml`，后端本来就 409 `workflow_tier_repo`），说明一句。
- ModelPicker 的档位徽标改用工作流库的颜色和词（`workflows:tier.*`），不另起一套。

## 2026-10-28 · M5 第 10a 步：ModelPicker 显示工作流档位，未验证的单独一组

- **`GET /config/components` 的 `models[].tier`**（`modelhub/catalog.py:_tier`）：只有 `runtime: comfyui` 且有 `workflow` 的本地模型有值；在库的「未验证」集合里 → `unverified`（文件变了的仓库工作流也算），库里升过「我的」→ `mine`，其余（`providers.yaml` 带的）→ `recommended`；LLM、API、Python worker 模型是 `null`。没另开接口，选择器本来就读这份目录。
- **选择器**：本地模型照旧一个单选组，未验证的放在组末一个带标题的小组里（「未验证的工作流 · 只能手动选」+ 一句说明），每个工作流带档位徽标（颜色和词跟工作流库一样，第 10b 步）；「兜底到」不列未验证的（后端 `_manual_only` 本来就会去掉）。手动选成本地模型照常写覆盖。
- 原因：SPEC 6.4.4 / 7「未验证只能手动选」；后端第 2 步已经把它挡在自动路由外，界面要让人看出来为什么它不会被自动用到。

## 2026-10-28 · M5 第 14e 步：本地 H3 草稿 20 步；媒体缓存认工作流文件；库同步跟着仓库文件走

- **`workflows/h3-i2v`、`h3-r2v`**：删 `LoraLoaderModelOnly`（Turbo LoRA），`BasicGuider` 和 `BasicScheduler` 直接接 `UNETLoader`，`steps` 8 / 4 → 20（res_multistep + simple，官方关 Turbo 的默认）；`models` 去掉两个 LoRA，名字去掉「Turbo」；`est_seconds_per_s` 25 → 30 / 36（第六轮本机实测 158 / 188 秒一条 5.17 秒的片子，`reports/m5-local-smoke/run6-20steps/`）。
- **媒体调用的结果缓存键加上工作流文件哈希**（`media._media_key` + `modelhub/workflows.py:workflow_sha256`，每次读文件，不走 `shipped_workflow` 的进程内缓存）。原因：这个缓存是为了重试 / 续跑不重复花钱，键只有「模型键 + 提示词 + 参数 + 种子」；工作流改成 20 步后，同种子的 take 1 秒内拿回 Turbo 的旧片子、不写 `model_call`。没有工作流的模型键不变，旧缓存照常命中。
- **工作流库同步仓库工作流时，文件哈希变了就刷新 `deps_json.models`、清掉旧体检**（`wflib/service.py:sync`）：以前只更新哈希、名字、能力，旧的模型清单（含 LoRA）和旧图的体检结果一直留着。仍是推荐档；体检要再跑一次（工作流库「全部体检」或导入时）。
- **安装清单的 `w_h3` 仍下载两个 Turbo LoRA（3.9 GB）**：Kelvin 2026-10-28 定留着，以后可能做「快速草稿」档。
- 顺带修 CI（379c314，第 14c / 14d 步之后红了三次）：安装 / 扫描测试补 `w_flashvsr`，运行记录测试改成本地 take 只有改写的花费。

## 2026-10-27 · Kelvin 定：本地 H3 草稿用 20 步、不开 Turbo；原生配音的声音合格

- **本地 H3 草稿（`comfy/h3`、`comfy/h3-r2v`）改成 20 步、不开 Turbo LoRA**（res_multistep + simple，官方关 Turbo 的默认）。原因：Kelvin 看了第三轮（`reports/m5-local-smoke/run3-workflows/`）和第五轮（`run5-rewrite/`），Turbo（8 / 4 步）画质不够；20 步一条 5 秒片约 2.5–6 分钟，换来画质。提示词改写（第 14b 步）解决切走 / 漂移，步数解决画质，两者独立。做法见计划第 14e 步。
- **原生配音（`native`，H3 参考生视频 + 锁定音色样本）的声音 Kelvin 听过，合格**：第五轮 1-04 的台词没有乱码、音色像林晚。第二轮 ab-22-B 的乱码音频是 Turbo 4 步时声音没收敛（官方说说话和音色要 12 步以上），换 20 步后不再是问题。

## 2026-10-27 · M5 第 14d 步：2K 精修的本地档（SeedVR2 默认、FlashVSR 兜底）

- **Kelvin 定**：「2K 精修」（`up`）本地默认 SeedVR2，兜底 FlashVSR，按钮上显示预计耗时。范围：M5 做后端和工作流，按钮和 `POST /versions/{id}/upscale` 仍是 M6（计划原样）。`components.yaml` 的 `up` 本来就是 `local: comfy/seedvr2`、`fallback_to: comfy/flashvsr`，只补了注释。
- **`workflows/seedvr2-up`**：第三轮本机对比验证过的图（ComfyUI 自带 SeedVR2 节点 + 7B int8，官方模板 `utility_seedvr2_3b_int8_upscale_video` 换 7B），直接缩放到成片尺寸（居中裁），时间方向按显存自动分块，lab 调色，原片的声音和帧率原样带过去。
- **`workflows/flashvsr-up`**：1038lab 的 `AILab_FlashVSR`（Balanced 预设）只能 ×2 / ×4，所以 ×2 再缩到成片尺寸。
- **FlashVSR 权重进安装清单 `w_flashvsr`**（锁 1038lab/FlashVSR f1bc6756，五个文件 6.7 GB、带 sha256，下到 `ComfyUI/models/FlashVSR`）：节点缺文件时会自己整仓下载 13 GB（含用不上的两个），而且绕过我们的快照和进度。`comfy/flashvsr` 的 `needs` 加上它；本机已经下好。
- **预计耗时 = 估价的 `seconds`**：ComfyUI 适配器本来就按 `caps.est_seconds_per_s × 片长` 算，按钮（M6）直接用。本机实测：5.17 秒的 768×1344 片子放大到 1080×1920，SeedVR2 194 / 211 s（→ 40 s 每秒），FlashVSR 164 s（→ 32 s 每秒），都含加载模型。FlashVSR 并没有快很多，当兜底（SeedVR2 失败、超时）而不是「快速档」。
- **本机体检 + 试跑都过**（工作流库的 `check` / `trial`）：SeedVR2 15 / 15 个节点、FlashVSR 6 / 6，试跑 27 s / 69 s。1:1 裁脸：两者都没改脸，FlashVSR 皮肤纹理多一点、略显锐化，SeedVR2 更顺（`reports/m5-local-smoke/run3-workflows/1-04-face-seedvr2-vs-flashvsr.jpg`）。

## 2026-10-27 · M5 第 14b 步：本地 H3 的提示词按官方写法改写

- **原因**（本机对比 `reports/m5-local-smoke/run4-1-04-cut/`，同首帧、同种子、官方 20 步）：1-04 第 2 秒切走、画面漂到别处，换采样器、关 Turbo、换社区工作流、关 SageAttention 都没用；切过去的画面就是参考图本身（场景图、人物全身像）。按 MiniMax 官方 `h3-prompt-writing`（GitHub `MiniMax-AI/MiniMax-H3`，b731d8846cf7 的 `base-en.txt` / `ref-en.txt`）手写的提示词两个种子都一镜到底。我们原来的模板违反了三条：要英文（只有台词保留原文）、主体描述 350–500 词逐拍写、只定长相 / 场景的参考图不能单独写成 `<Picture N>` 一行（那是给首帧 / 关键帧的），要写进 `<Subject N>`。
- **改写走新路由组件 `vprompt`**（视频提示词改写，`kind: llm`，写作模型可选、可本地）：经 `router.call()`，`model_call` 记在 `vprompt` 名下；模型页多一行。默认 DeepSeek V4.1 Flash（便宜、英文够用），兜底 Qwen3.7 Plus，「全本地」时用 Qwen3.6-27B。只给本地 H3：API 的 H3 已经有官方的 Context-IR（多模态，能看图），不重复改写。
- **务必符合官方模板 = 代码校验**（`prompts/h3_format.py:check`）：段落名和顺序、I2VA 第一行逐字、标签只用发了的且都要引用、参考图只能出现在 `<Subject N>` 行里、英文（`<d>` 和引号里的画面文字除外）、台词原文逐字按顺序、旁白格式、只有 `[Shot 1]`（我们每个镜头就是一条，换景别用运镜）、`non_diegetic_music` 必须 N/A（配乐后期加）、字数（Ref2VA 300–650、I2VA 120–650，比官方的 350–500 宽一点）。不合格把问题列给模型重问一次（`REWRITE_TRIES = 2`），还不合格报 `prompt_not_conformant`、不出片、原始回答存成文件：宁可不出也不送不合格的提示词。
- **规则用我们自己的话转述**（`templates/vid/h3_rewrite_system.j2`），只照抄格式字符串（I2VA 第一行、段落名、标记词），范例用第四轮验证过的 1-04 那段：官方仓库没有单独的许可证（模型是 MiniMax H3 Community License），不把原文整份放进仓库。
- **改写模型看不到图**：参考图带上分析里的长相描述（`refs[].desc`：用户给那张图写的描述，否则分析的 `description`），首帧带关键帧的描述（`first_desc`）；原来的模板输出（中文描述）作为 `draft` 一起给。
- **缓存**：按（模型、消息）缓存改写结果，一次出两条候选（种子不同）共用一段提示词，「再出一条」输入没变也不重问；候选之间只差种子，好比较。
- **估价**：本地 H3 的 take 加上改写的上限（按问两次、6000 输出 token 算，DeepSeek V4.1 Flash 约 $0.008）；按条数乘，实际只问一次，偏高。
- **模板**：`h3_r2v.j2`（API 的 Context-IR 和本地改写的起点）的参考图改成 `<Subject N> is …, whose look comes from <Picture N>`。`h3_i2v.j2` 不变（它就是改写的起点）。

## 2026-10-27 · M5 第 9c 步：候选卡、视频播放、出终版按钮、队列卡

- **候选卡固定宽度**（`lib/cards.ts:TAKE_CARD_WIDTH`，竖屏 236 px、横屏 320 px，换行排列），竖屏的画面框按原型固定 290 px 高、封面帧按真实比例居中；原来按面板宽度伸缩的网格在约 2000 px 的屏上会把画面拉大、`max-h` 截高后比例也不对。
- **播放走大图**：`MediaLightbox` 的条目可以带 `video`，在对话框里放后端的片子（封面帧当 poster、自带控件、自动播放，← → 换条）；卡片上的播放按钮和空格都打开它。原来的「示例数据里没有视频文件」提示删掉。
- **「用 API 出终版 · 约 $x」只给本地 H3 草稿**（`stage=draft`、本地、H3 系；Regenerate-2K 只收 H3 自己的草稿，后端对别的返回 `draft_not_regenerable`）。价格是后端的：`EstimateOut` 新加 `final_usd`，组件配了 `final_api`（目前只有 `vid`）时由 `RunService.describe` 按镜头时长估 Regenerate-2K；前端不自己算（按秒计价还带输入视频，只有后端知道）。其他快照里的估价多了 `"final_usd": null`，重导。
- **队列卡**：本地、API 两张卡各列活动任务按模型分组的「运行 n · 排队 n」（按出现顺序，GPU 同模型连着跑），API 卡另列「n 个本地任务已兜底到 API」（`fallback_from_job_id`）和「n 个任务等你确认花费」（`waiting_confirm`）。质检卡里「自动兜底 n 次」仍按版本数。

## 2026-10-27 · M5 第 9b 步：生成页接后端（数据）

- **删掉的 MSW**：生成页的规则、运行记录、取消采纳、打分（`handlers/generate.ts` 只剩 M6 的 2K 精修）；示例 take 和它们的质检（`fixtures/demo/takes.ts` 改名 `finishing.ts`，只剩 2K 精修 / 口型 / 质检三个本集产物）；镜头上的 `video_product_id` 叠加（`handlers/shots.ts` 只剩给后期示例读镜头和 take 的 `demoShots` / `demoVideos`）；生成徽标叠加（`series.ts`）、`takes` 闸门（`gates.ts`）；影响范围的视频叠加（`handlers/impact.ts`、`fixtures/demo/impacts.ts` 整个删掉：后端的预览从第 5 步起自己列视频行）。MSW 的产品列表：没有 owner、示例里也没有的（`?component=vid`）放行给后端；镜头的产品全是后端的。
- **`/metrics/summary` 留一层叠加到 M8**：数据看板整页还是示例（各张表对着 $8.94），所以 MSW 的 summary 是「示例的已花 / 预计 + 后端已花」、预算用后端的、洞察用示例的。表头和生成页的花费因此会跟着真实（Mock）花费实时涨。计划说删掉这个 handler，改成叠加，M8 再删。
- **后期示例的时间线读后端的 take**：`buildTimeline` 用 `demoVideos()`（`GET /products?component=vid`）找每个镜头采纳的版本。
- **测试假后端** `test/fakes/generate.ts`（数据 `generate.json`，`test_web_fixtures.py` 从「应用启动时那样」的示例导出：分镜已确认、有 take）：视频产物、跑 take（先出 `takes_per_shot` 条、再出一条 1 条、出终版 1 条 2K；没确认分镜 409、上一镜没采纳 409）、采纳 / 取消采纳 / 打分、规则、运行记录、生成闸门和徽标。别的页面测试仍是「分镜进行中」，生成页测试先 `confirmFakeStoryboard()`。FFmpeg 各平台出的字节不同，导出时 take 文件的 sha256 按版本 id 重算、时长取到 0.1 秒、版本哈希按 id 写（`_stable_takes`）。`shots` 和影响范围的假后端改成直接回答（以前经 MSW 转发）。
- **`?shot=` 和 Inspector 的 `item` 都用镜头 id**（生成页、后期页「换一条候选」，和分镜页一致）。
- **M5 的 take 没有质检**：候选卡的质检框显示「未检查」，状态卡「10 条候选还没质检」；没有质检分数就没有「推荐」，默认选中最新一条。
- **运行记录同一分钟的两行**：后端按时间正序（兜底那行在它出的 take 前），页面倒序时并列的也倒过来。
- **示例种子补一处**：1-04 原生同步、有林晚的锁定音色，本地草稿改走 `comfy/h3-r2v` 并带音色样本（依赖也记上），和真跑一致。

## 2026-10-27 · M5 第 9a 步：示例的分镜确认、视频 take 种子

- **示例第 1 集的分镜改成已确认**（Kelvin 2026-10-27 定）：原型里分镜页（3/7 确认）和生成页（3/9 采纳）是各自的假数据；后端规定分镜确认后才能出视频，接了后端只能二选一。`CONFIRMED_GATES` 加 `("storyboard", "demo-e1")`；确认它之前，种子把没决定过的镜头确认掉（1-04–1-07 锁定关键帧当前版本上选中的那张，默认 A；1-08、1-09 只写决定；时间 11:24）。用户重开过的闸门照旧不再确认。
- **视频 take 照原型种**（`DEMO_TAKES`）：1-01–1-03 本地 H3 草稿 + 「用 API 出终版」（Regenerate-2K，父版本是草稿，已采纳）；1-04 首跑两条草稿、一条本地超时后在 H3 API 上出的（`origin=fallback`、`fallback_reason=timeout`）、一条「不满意换一个」的 Seedance 2.5，待挑；1-05–1-07 没跑过；1-08、1-09 等上一镜。每条和 Mock 跑出来的存法一样：输入来自 `vid.gather`（依赖照记，不会一种下去就待更新），片子是 Mock 纯色 mp4（有声音），裁头、封面帧、尾帧走 `vid.clip_files`（从 `VidComponent._clip_files` 抽出的模块函数），本地草稿留 `raw` 和 `params.request`，所以示例草稿也能真的「用 API 出终版」。花费按国内价算进版本的 `cost_usd`，**不写 `model_call`**（和关键帧种子一样），所以表头「本集已花」不含种子的钱。运行中 / 排队的卡片不预置：Mock 任务一启动就会跑完，点「生成」就能看到。
- **`lock_pick` 加 `pick_id` / `at`**（只有种子用）：锁定候选时新建的 pick 版本用固定 id（`demo-p-kf-1-04-v2`）和示例时间，快照和 MSW 示例对得上。
- **前端快照仍从「分镜确认之前」导出**：`test_web_fixtures.py` 的 `client` 去掉分镜闸门，`shots.json` 等不变——分镜页测试测的正是「进行中 → 确认镜头」，这个场景照样成立；生成页要的带 take 的数据第 9b 步另导一份。Playwright `m4` 开头先用接口把 1-04–1-09 取消确认（顺带重开分镜），再在界面上走原来的确认流程；1-04 的终版因此是 v3（v2 是种子的 pick）。
- **原因**：测试默认不种闸门（`conftest._demo_gates_open`），所以视频种子（要跑 ffmpeg）只在应用启动、`demo_gates` 的测试里发生，不拖慢几百个 API 测试。

## 2026-10-27 · M5 第 8 步：生成页接口（后端）

- **自动规则按剧集存在 `app_setting`**（key `generate.rules.<剧集 id>`，只存改过的字段），没改过的读配置：`takes_per_shot` ← `vid.candidates`（2），`qa_retry_max` ← `fallback_defaults.qa_fail_n`（2），`shot_cap_usd` ← `components.yaml` 新加的顶层 `shot_cap_usd`（$2，原型的值），`thresholds` ← `qa` 组件的阈值（只读，PUT 里带它 422）。没有新表、没有迁移。原因：这三项是「这部剧怎么出片」的设置，不是某个组件的路由；放进组件覆盖层会和模型页的「恢复成预设」搅在一起。`qa_retry_max` 现在只存不用，M6 的质检重跑读它（模型页的 `fallback.qa_fail_n` 仍是兜底配置的默认）。
- **`takes_per_shot` 生效**：`Component.run_count` 改成 `async (session, product)`，视频组件首跑读剧集的规则；再出一条仍是 1 条。
- **单镜头上限**（硬规则 6 原来缺的一档）：`Budget.before_enqueue(shot=(镜头 id, 上限))`，镜头上的工作（关键帧、视频，`owner_type=shot` 的产物）入队前检查「镜头已花（`model_call.shot_id`）+ 这个镜头的产物还在排队 / 运行的预留 + 这次估价」；超了进 `waiting_confirm`，`reason: shot`，`limit_usd` 是镜头剩下的。顺序：未知价 → 单次 → 单镜 → 本集。路由守卫（每次调用前）不查单镜：入队时已经问过，确认的任务按确认金额走。前端 `JobConfirmSchema` 加 `shot`，确认弹窗一句新文案。
- **运行记录不建表**，读时从本集镜头的视频产物推出：每个 take（`origin` 是 run / rerun / switch / fallback 的版本）一行，code `take` / `switch` / `final`（M5 没质检；有 `qa` 后是 `take_pass|fail`、`switch_pass|fail`）；兜底出的 take 前面加一行 `fallback_timeout`（分钟数取视频组件的 `fallback.timeout_s`）/ `fallback_error`；还在运行、等确认、失败的任务各一行（`started`、`waiting`、`failed`，后两个标黄）。按时间排，id 带前缀（`v-` / `fb-` / `job-`）。新加的 code 中英文都加了。
- **取消采纳**只给没有物化的槽位（视频、关键帧候选这类）：设定、剧本、分镜规划这些采纳后写进业务表的，`unadopt` 返回 409 `unadopt_unsupported`（业务表不知道怎么「退回」）；锁定时 409 `product_locked`。**打分**（`PATCH /versions/{id} {rating}`，1–5 或 null）和 `note` 一样是版本上唯一可改的字段，不算内容、不改哈希。
- **最小 `/metrics/summary`**：已花 = 范围内 billed 的 `model_call.cost_usd`；预算 = 本集的，全剧是各集已设的之和（都没设就 null）；预计 = 已花 + 活动任务还要花的（和本集剩余同一算法，`Budget.reserved`）+ 视频从没跑过的镜头 × 下一次估价 × `takes_per_shot`。上游没好（没有估价）的镜头先不算，其他组件的「剩余」M8 再加；`insights` 先返回空。

## 2026-10-26 · M5 第 7a 步（四）：服务页的站点、模型列表和价格（前端）

- **密钥对话框**（`KeyDialog.tsx` + 新的 `ProviderModels.tsx`；原型里没有，按现有对话框的样式做）：两个站点的厂商顶部有「国内站 / 国际站」切换（有密钥的站点标「已有密钥」），切换就是 `PATCH /providers/{id}`，提示「两个站点是两个账号」；测试连接后出**模型列表**（勾选、参考价 / 你填的价 / 「价格未知」徽标、「填价格 / 改 / 清除」行内小表单：输入、输出每百万 token，¥ / $），超过 12 个模型出筛选框（OpenRouter）；没拉过列表时一句提示「用内置的参考表」。原来那句「这个密钥也用于：…」换成**媒体模型 ID** 小节：每个媒体模型一个输入框（有列表的厂商用 `datalist` 给建议），「保存」「已改」「恢复默认」。
- **后端补两个字段**：`/config/components` 的每个模型加 `priced`（API 写作模型有没有单价；媒体模型按 `pricing_for_media(...).known`，所以订阅制、没价的也算未知）；`GET /providers` 的 `media` 每项加 `model_id`（当前生效的）和 `custom_model_id`。
- **选择器**：API 模型没单价时，价格那行换成徽标「价格未知 · 运行前会先问你」；路由里的 API 模型不在这个组件的可选列表里（没勾选 / 换站点后没有）时，「API 服务」下面红字提示去换。模型页的组件表里，主用模型那格同样标红「没启用，点开换一个」。
- **改了站点、勾选、价格、媒体 ID、测试连接之后**一起刷新 `providers`、`config`（选择器目录、路由）和 `products`（估价）三组查询。
- **和计划不同**：计划说删掉 `mocks/fixtures/demo/models.ts` 里写死的模型表；它现在只给 MSW 示例版本起模型名，选择器早就读真实的 `/config/components`，所以留着不删。

## 2026-10-26 · M5 第 7a 步（三）：价格未知的模型先确认

- **补硬规则 6 的漏洞**：以前没单价的模型按 $0 估价，从不进 `waiting_confirm`。现在 `Budget.before_enqueue(…, priced=False)` 一律返回 `Verdict(False, reason="unpriced")`（不看上限和本集预算），任务进 `waiting_confirm`，`params.confirm = {reason: "unpriced", estimate_usd: 0, limit_usd: null}`。填了单价（`model_setting`）就回到正常的上限检查。
- **路由守卫用 `BudgetExceeded(scope="unpriced")`，不用计划里写的 `NeedsConfirm`**：`NeedsConfirm` 是「兜底要先问」专用（带失败的模型和兜底目标），挪作他用会让任务走 `_ask_fallback`；而同步调用的地方（重写、补全的「按要求重写」）本来就把 `BudgetExceeded` 转成 409 `over_budget`。规则：没确认过（`confirmed_usd` 为空、任务也没确认）的调用遇到未知价就停；确认过的任务照旧按「确认额 + 余量」判断（未知价的花费记 0，所以一定放行）。后果：一个没确认过的任务兜底到未知价的模型会以 `budget_exceeded` 失败，而不是悄悄花钱——和「兜底更贵就失败」一致。
- **同步重写**：剧本化的重写（`_check_budget`）和补全的「按要求重写」遇到未知价返回 409 `over_budget`，`reason: "unpriced"`；带 `confirm_budget` 重发就跑。
- **兜底要先问的确认**里加 `priced`（兜底目标没单价时为 false），前端把预计花费显示成「价格未知」。
- **记账**：迁移 `0023` 给 `model_call` 加 `unpriced`（路由按 `spec.pricing.known` 写，`cost_usd` 仍是 0）；`calllog.unpriced_calls(series_id / episode_id)` 数「价格未知的已计费调用」，给第 9 步表头用。`EstimateOut` 加 `priced`（前端 schema 可选字段）。
- **前端只做了最小的**：`JobConfirmSchema.reason` 加 `unpriced`（不加的话确认弹窗解析失败）、确认弹窗文案「{{model}} 没有单价，这次花多少不知道。可以在模型页给它填上单价。」、按钮「确认，开始运行（价格未知）」。选择器徽标等在 7a-4。

## 2026-10-26 · M5 第 7a 步（二）：写作模型按厂商列表选

- **「账号叠加层」代替第 7a-1 步注册表里的站点参数**：仿照工作流库的 `set_library` / `with_library`，`core/config.py` 加 `set_accounts` / `with_accounts`，`get_config()` = 出厂配置 + 工作流库 + 账号。叠加后：每个厂商的 `base_url` / `key_name` / `docs` 是当前站点的；写作模型行是**勾选的模型**（参考表里有的用表里那行，表外的 `<厂商>/<model_id>`、参数用厂商新字段 `model_defaults`、价格未知）；表里各行的价格换成当前站点的；用户的单价、媒体模型 ID 叠上去；`components.yaml` 里写 `api: [llm]` 的组件展开成所有已启用的写作模型（按 `llm_ui_order`，再按厂商顺序）。好处：目录、估价、选择器、路由都直接读 `get_config()`，选择器里的价格也跟着站点走。`specs_from_config` 退回只读配置，`Registry.set_account` 换成 `Registry.reload(cfg)`（重建 API 模型、删掉不再勾选的写作模型）；`StudioState.refresh_accounts()` 在账号或设置变了之后调用。
- **数据**（迁移 `0022`）：`provider_account.models_json`（`{site, ids, fetched_at}`）、`enabled_json`（勾选的 id；空 = 没拉过列表，参考表照旧生效）；新表 `model_setting`（`model_key`、`model_id`、`price_json`）。`custom_model` 表照旧没用上。
- **列表怎么来、怎么勾**：「测试连接」成功就把 `GET /models` 的结果存下来；第一次拉到时自动勾上参考表认识的 id，之后保留用户的勾选、去掉厂商不再列出的 id（退役的模型自然消失，路由用到它时照常 `unknown_model`）。`PUT /providers/{id}/models {enabled}` 勾选（只能勾列表里有的，422 `unknown_model_id`；没拉过列表 409 `models_not_listed`）。**换站点会清掉列表和勾选**：另一站是另一个账号，列表要在那边重新拉，拉之前用参考表。
- **单价和模型 ID**：`PUT /providers/settings/{model_key}` `{price: {in, out, currency}, model_id}`、`DELETE` 同路径。只认注册表里的模型、厂商列表里出现过的模型或参考表里的模型（404 `unknown_model`）。`GET /providers` 每个厂商加 `listed`：拉到的每个 id、是否勾选、是否在参考表、价格和来源（`user` / `table` / 未知）。
- **参考表的变化**：Kimi 加 **K3.1 Pro**（`kimi-k3.1-pro`，¥13/68、$2/10 每百万 token，上下文 1,048,576）。思考关不掉，流水线默认 `reasoning_effort: low`（**Kelvin 2026-10-26 定**：思考按输出计费、占 `max_tokens`，估价也没算）。默认路由里的 `moonshot/kimi-k2.6`（剧本化、大纲的兜底，剧本化的「不满意换一个」第一个）换成 K3.1 Pro；K2.6 留在表里（示例数据、历史版本在用，2026 年底退役）。写作模型从 14 个变成 16 个（加了 K3.1 Pro；K2.6 也还在），选择器的「更多供应商」跟着变。各厂商的 `model_defaults`：DeepSeek 关思考、百炼 `enable_thinking: false`、MiniMax 关思考且不开 JSON 模式，其余开 JSON 模式。
- **媒体模型的列表下拉**（OpenAI、Gemini 拉列表给媒体模型改 ID 当建议）留到前端那步（7a-4）一起做；后端现在能存媒体模型的 ID 覆盖。

## 2026-10-26 · M5 第 7a 步（一）：厂商的国内站 / 国际站

起因：Kelvin 的 Kimi 密钥是国内站的，配置写死国际站，测试连接 401（国内站 200）。Kelvin 定：每个厂商能切站点、默认国内站；模型改成按厂商返回的列表选（第 7a-2 步）。计划见 `plans/M5-7a.md`。

- **配置**：厂商行可以写 `sites`（`cn` / `intl`，各自的 `base_url`、`key_name`、`docs`）和 `default_site`；只写 `base_url` / `key_name` 的旧写法照读（当成一个叫 `main` 的站点）。有两站的：Kimi、百炼（Qwen）、智谱、MiniMax，四家都默认国内站。价格按默认站写，另一站的写在模型行的 `by_site`（写作模型和媒体模型都能用，媒体模型跟着它 `account` 的站点走：MiniMax 换国际站时配音、H3、Regenerate、Context-IR 都换成美元价）。
- **密钥按站点分开存**：国内用原来的名字（`MOONSHOT_API_KEY`、`MINIMAX_API_KEY` …），国际加 `_INTL`（`MOONSHOT_INTL_API_KEY` …）。两站是独立账号，换站不丢另一站的密钥。百炼的 `DASHSCOPE_API_KEY` 以前指国际站，现在指国内站（这台机器没存过百炼密钥）。
- **账号的站点存 `provider_account.site`**（迁移 `0021`），空 = `default_site`。注册表启动时按账号建 spec（`specs_from_config(cfg, accounts)`）；`PATCH /providers/{id} {site}` 换站后 `Registry.set_account` 重建这个厂商的写作模型和用它密钥的媒体模型（地址、密钥、价格）。`base_url_override`（以前只有测试连接读）现在实际调用也认，优先于站点地址。
- **接口**：`GET /providers` 每个厂商加 `site`、`sites`（各站地址、有没有密钥），原来的 `base_url` / `has_key` / `docs` 是当前站点的；`POST …/key {site?}`、`DELETE …/key?site=` 按站点存删（不写是当前站点）；测试连接用当前站点，结果带 `site`。不认识的站点 422 `unknown_site`。
- **2026-10-26 按两站官方价格页核对的价**（每百万 token，国内人民币 / 国际美元）：Kimi K2.6 ¥6.5/27、$0.95/4.00（K2 系列 2026 年底退役）；Qwen3.8-max ¥12/36、$2/6，3.7-plus ¥2/8、$0.40/1.60（256K 以内，两站都有限时 8 折，写原价），3.8-flash ¥0.8/2.7、$0.15/0.47；GLM-5.3 ¥8/28、$1.40/4.40，5.3-Flash ¥0.8/2.8、$0.15/0.50（国内不免费）；MiniMax-M3 ¥2.10/8.40、$0.30/1.20（两站都是「永久五折」后的价）。MiniMax 国际站媒体价：配音 $100 / 百万字符、音色设计 $3、快速复刻 $1.5、设计试听 $60 / 百万字符；H3 768P $0.08/s、2K $0.13/s、超 5 张的图 $0.04；Regenerate $0.05/s（输入同价、图 $0.025）；Context-IR $0.90/3.60。
- **顺带改正的模型参数**：智谱 `model_id` 填上 `glm-5.3` / `glm-5.3-flash`（以前是 null，调不了）；GLM-5.3 关不掉思考（发 `thinking: disabled` 会报错），不加 `request`；MiniMax-M3 的 `model_id` 填 `MiniMax-M3`、加 `thinking: disabled`、`json_mode` 改 false（文档的 Chat Completions 没有 `response_format`）；上下文：K2.6 262,144，GLM-5.3、M3 1M。
- **`docs/studio/seed/providers.yaml` 不跟着改**（计划写了「同步」）：它是 M0 拷进 `config/` 的初始数据，之后从没同步过，`config/` 才是现行配置。
- 测试里「兜底模型比原模型贵」那条（`test_a_pricier_fallback_after_a_yes_fails`）的前提变了：Qwen3.7-plus 国内价比 DeepSeek Flash 便宜，测试改成先把百炼切到国际站。

## 2026-10-26 · M5 第 7 步：视频出终版、本地失败 / 超时兜底

- **「用 API 出终版」走组件的 `final_api`**（`components.yaml` 的 `vid.final_api: minimax/h3-regenerate-2k`，新配置项），不是路由的 API 模型（H3 API 是重新出一条，不是把草稿出成 2K）。前端照关键帧的写法：`POST /products/{id}/run {where: api, params: {source_version_id}}`；`model_for` 换到 `final_api`，估价（含影响范围的 `final_cost`）也按它算。**出终版只出一个版本**（`RunService.start` 有 `source_version_id` 时条数是 1，以前按 `run_count`，视频第一次会是 2）。
- **草稿多存两样，供 Regenerate-2K 原样重发**：本地 take 的文件加 `raw`（没裁头的原片，帧数和官方要求的 17k+5 对得上；裁头后的不行），版本 `params_json.request` 记实际发出的请求（首帧、参考图、音色 / 台词音轨的 sha256、画幅、时长、`with_audio`），`prompt` 文件本来就是实际发出的提示词。终版用这些 + `video_in: raw`，出来的 2K 视频同样裁头 0.3 秒、取封面和尾帧，`stage=final`、父版本是草稿，payload 沿用草稿的、`resolution: 2k`。不是本地 H3 出的草稿（API take、旧的没有 `raw` 的）→ 任务失败 `draft_not_regenerable`。终版失败不兜底，草稿不动。
- **不预先检查 Regenerate-2K 的输入规格**（24 fps、带音轨、宽高 32 的倍数、面积 ≤ 768×1344）：不合格时 MiniMax 拒绝任务（失败不收费）。已知风险：本地工作流 1:1（1024×1024）、21:9（1568×672）面积超了；`none` 镜头的草稿可能没有音轨。第 14 / 15 步实测后再定是改工作流尺寸还是在 UI 上禁用。
- **本地 take 失败或超时，整条 take 在兜底模型上重做**（`run_flow`，和配音终版一样）：请求按兜底模型重建（H3 API 的模式、提示词格式、Context-IR），不是把本地请求原样转发；每次调用 `fallback=False`。版本 `origin=fallback`、`fallback_reason` 是 `error` / `timeout`，本地那次的 `model_call` 记失败或超时（`notify: ask` 时先问，沿用 `run_flow`）。Context-IR 的花费算进版本的 `cost_usd`。
- **GPU 分组**：视频 take 走 `gpu` 队列、按 `model_key` 分组（M1 的 `grouped`），新测试在 `vid` 这一层验证：H3 在跑时，后排的 H3 take 先于先排的 H3 参考生视频。

## 2026-10-26 · M5 第 6 步：视频 API 适配器（MiniMax H3、Seedance 2.5）

按官方文档核对（MiniMax 国内文档在 platform.minimaxi.com，`platform.minimax.cn` 只有控制台；火山方舟 docs.volcengine.com 82379/1520757、1521309、1521720、1330310、1544106、1299023）。没真调过，真调在第 15 步。

- **H3 走 V2 接口，不是旧的海螺接口**：`POST /v2/video_generation`、`/v2/h3_context_ir`、`/v2/video_regeneration` 三种异步任务，共用 `GET /v2/query/video_generation/{task_id}` 轮询（指数退避，5 秒起、×1.5、封顶 30 秒），视频在 `content.url`，下载后探测（读不了 `invalid_response`、短了 `video_too_short`，都算已花钱）。地址是账号的 `…/v1` 去掉版本号。一个适配器 `adapters/minimax_video.py` 按 `kind` 分三种（`video` / `llm_aux` / `upscale`），`model_id` 都是 `MiniMax-H3`。调用被取消或超时时 `DELETE` 掉还在排队的任务（运行中的停不了）。
- **H3 API 的两种模式**：首帧和参考素材不能混用。有声音输入（`tts` 的台词音轨、`native` 的音色样本）→ 参考生视频，首帧当 `<Picture 1>`、再加锁定参考图（共 9 张）、音频最多 3 条；没有声音输入 → 图生视频，首帧是硬锚定，不带参考图。`tts` 镜头经 API 时台词音轨是 `<Audio 1>`、`fully_copy`（`h3_r2v.j2` 加了 `dub` 分支），对应 PLAN 的模式 A；本地 `h3-i2v` 照旧用 AddGuide。H3 总会出声，`with_audio` 关不掉；没有种子。
- **Context-IR 是官方的多模态提示词改写（异步任务，只出提示词）**，不是聊天接口。`vid` 对 `caps.prompt_ir` 有值的 API 模型（H3 API）先调一次（经 `router.call()`，单独一条 `model_call`，同一次运行的几条 take 共用缓存），把我们的 H3 格式（中文描述 + 英文字段）连同同样的图片、音频交给它，拿回英文提示词再出视频；版本的 `prompt` 文件存的就是实际发出的提示词（Regenerate-2K 要原样重发）。改写失败不挡出视频，用我们自己的提示词，payload `prompt_ir: false`。估价把它加进去。
- **分辨率由适配器按画面短边选**：H3 短边超过 768 → `2K`，否则 `768P`（API 跑交付档，所以 1080p 交付也出 2K，和 PLAN 的方案 B 一致）；Seedance 取短边够得着的最高档（1080p / 720p / 480p）。实际出的档位写进新字段 `Usage.resolution`，路由按它记账（以前只认请求里的 `resolution`，视频组件没传，H3 估价会是 0）。
- **价格用人民币存配置**（计划写的是「换算成美元存配置」）：和配音、Seedream 一样存 CNY，按 `currency_rates` 折算，汇率变了不用改单价。H3 768P 0.50 元 / 秒、2K 0.80 元 / 秒，每个任务前 5 张图免费、之后 0.20 元 / 张（`extras.extra_image`）；Regenerate-2K 输出 0.30 元 / 秒 + 输入视频 0.30 元 / 秒（官方示例里 `base_video` 记 0 秒，估价按收算，记账按返回的 `usage`）；Context-IR 5.80 / 23.00 元每百万 token。
- **Seedance 2.5**（`doubao-seedance-2-5-260628`，`adapters/seedance.py`）：参数用 JSON 字段（强校验），不用 `--rs` 文本指令；只发首帧（`ratio: adaptive`，2.5 首帧模式只能这样，画幅跟着关键帧），不发参考图（`max_refs: 0`）和音频；`tts` 镜头 `generate_audio: false`（台词后期铺）。**按 token 计费**（宽 × 高 × 24 × 秒 / 1024；480p / 720p 70 元、1080p 77 元每百万 token）：`price_by_res` 存 9:16 每秒的估价，记账用返回的 `completion_tokens` × `token_rates`（`cost_usd` 的 token 计费从图片扩到按秒的单位）。**1080p 原生支持**，规格兼容表里 Seedance 从「部分渠道只到 720p，需要再超分」变成原生（2K 交付时仍要超分）。
- **API 视频的超时按模型配**：`caps.timeout_s`（H3、Regenerate、Seedance 1800 秒），没有就用路由默认的 600 秒。HTTP 529（过载）加进重试。
- **之后的事**：本地 → API 兜底时请求是按本地模型做的（I2V 格式、不过 Context-IR），第 7 步做兜底时再按 API 模型重建请求。Regenerate-2K 要未裁头的 768P 原片（帧数 17k+5、带音轨、宽高是 32 的倍数、面积 ≤ 768 × 1344）：现在 take 只存裁头后的视频，第 7 步要另存原片；本地工作流 1:1（1024 × 1024）和 21:9（1568 × 672）的面积超过这个上限，到时要核对。

## 2026-10-26 · M5 第 5 步：视频组件 `vid`（后端，Mock）

- **视频产物在物化时就建，不等分镜确认**（和计划写的「分镜闸门确认后」不同）：`shots/service.py:materialize` 给每个镜头（连续镜头也有）建 owner `shot`、slot `video` 的产物，跟着镜头退役、回来，和关键帧一个写法；**出视频要分镜已确认**（409 `storyboard_not_confirmed`）。这样产物 id 稳定（示例固定成 `demo-p-vid-<镜头号>`，和 MSW 的一致），影响范围和失效也有地方挂。已有的镜头由迁移 `0020`（只改数据）补上。
- **一条 take = 一个版本**（前端契约：评分、质检、采纳都按版本）。第一次出 `candidates` 条（2），之后「再出一条」1 条：组件新钩子 `run_count`，`POST /products/{id}/run` 的 `count` 默认改成「由组件定」。**估价乘上条数**：以前 `count` > 1 时只按一条估价和查预算（硬规则 6 的漏洞），现在 `start` 按 `count` 倍。
- **首帧**：普通镜头用锁定的关键帧（没锁 409 `keyframe_not_locked`）；连续镜头用它接的那个镜头**已采纳 take 的尾帧**（没采纳 409 `upstream_not_adopted {id: 镜头号}`）。依赖记关键帧产物或上一镜的视频产物，上游换了就「待更新」。
- **声音按 `audio_mode`**：`tts` 把这个镜头说话的行的已采纳配音从 0.3 秒起一句接一句拼成一条 48 kHz 单声道（`media/audio.py:dialogue_track`，补静音到镜头时长），当 `dialogue_audio` 传；有一句没配音就 409 `line_audio_missing`。`native` 把说话人锁定音色的 `anchor` 样本按说话顺序（S1、S2 …）当 `ref_audio` 传，`model_for` 换到工作流收 `ref_audio` 的本地模型（`comfy/h3-r2v`）；没锁音色的说话人只写在提示词里。`none` 不要声音（`with_audio: false`，`overall_soundscape: N/A`）。
- **新槽位 `ref_audio`**（带序号的音色样本，`h3-r2v` 用）：后端 `Slot`、库的 `SlotName`、前端 `SlotSchema` 和两种语言的词表都加了。`workflows/h3-r2v/` 照官方 R2V 模板（ref2va 权重、4 步 Turbo LoRA、首帧当 `<Picture 1>`、参考图最多 4 张、音色最多 3 个），同样对本机 `/object_info` 静态核过；`providers.yaml` 加 `comfy/h3-r2v`，视频组件的本地列表加上它。
- **提示词两层不变**：编译层是 `templates/vid/default.j2`（中文，用户能改）；发给 H3 时套 H3 自己的格式（`h3_i2v.j2`：首帧那一行 + 三个字段；`h3_r2v.j2`：参考模式的六段 `subject_definitions` … `non_diegetic_music`），台词写成 `(S1) says: <d>[Chinese] …</d>`、画外音照官方写法、配乐一律 `N/A`。格式照 MiniMax 官方的两份提示词指南（HF `MiniMaxAI/MiniMax-H3` 的 docs）。官方要英文正文：现在是中文描述放进英文字段，第 6 步的 Context-IR 再按官方指南写英文。「六段式」指的就是参考模式的六段。
- **每条 take 裁掉开头 0.3 秒**，文件 `video`（带时长、宽高）、`poster`（第一帧）、`last_frame`（最后一帧）、`prompt`；payload 记 `duration_s`、`asked_s`、`resolution`、`aspect`、`audio_mode`、`refs`、`voices`。本地出的 `stage=draft`（终版第 7 步）。质检是 M6，`qa` 为空。
- **生成确认 `takes`**：GateService 的 members 闸门加 `lock=True`：确认时每个镜头都要有采纳的 take（409 `takes_not_adopted {count, labels}`），然后锁定；重新打开时解锁。导航徽标「生成 n/m」：分镜确认前「未开始」，之后是有采纳 take 的镜头数，待更新数按失效算。
- **影响范围**：`video` 进影响范围的排序和步骤表（步骤 `generate`），镜头设定、台词、关键帧变了走通用的 `stale_video` / `then_video` 行；改画幅另加 `videos_redo`（已有几条 take、几条已采纳、已采纳的出 API 终版要多少钱）。「确认并同步」不自动重出视频（和关键帧一样只标待更新）。
- **本地运行的进度**：组件的 `CallContext` 带上 `on_progress = RunContext.progress`，ComfyUI 的采样步数直接走 `job.updated`。

## 2026-10-26 · M5 第 4 步：ComfyUI 适配器完整版、H3 本地工作流

- **H3 本地工作流 `workflows/h3-i2v/` 照官方 I2V 模板**（`video_minimax_h3_i2v.json`，子图展开成 API 格式），节点名、输入名、可选值对着 Kelvin 本机 ComfyUI 0.41.2 的 `/object_info` 静态核过（没真跑，真跑在第 14 步）。用 `MiniMaxH3ImageToVideo`（fl2va 权重）而不是上游 `selfhost/` 的 `MiniMaxH3ReferenceToVideo`：首帧是硬锚定，不是提示词里的「<Picture 1> 是首帧」。草稿固定开 8 步 Turbo LoRA（官方开关默认关，参数照官方 Turbo 默认）。尺寸按画幅取 768P 档（短边 768，和 H3 API 768P、Regenerate-2K 的输入对上），帧率固定 24，时长落到 5–15 秒，帧数照官方表达式落到 17k+5。每秒成片的估时 `est_seconds_per_s: 25` 是估的，第 14 步实测后改。
- **配音方式 `tts` 的台词音频用 `MiniMaxH3AddGuide` 挂在第 0 帧**：I2V 节点本身不收音频，官方的 AddGuide 把音频按原样锚进去（相当于 PLAN 模式 A 的 fully_copy）。**`native` 模式的锁定音色样本这个工作流收不了**（音色参考只有 Reference to Video 节点的 `ref_audios`，配 ref2va 权重）：**Kelvin 2026-10-26 定（选 B）**：第 5 步加 `workflows/h3-r2v/`（`MiniMaxH3ReferenceToVideo` + ref2va 权重 + 它自己的 4 步 Turbo LoRA），`native` 镜头走它，锁定音色样本当 `<Audio N>` 传进去、首帧当 `<Picture 1>`（软约束，提示词里写明它是起始帧）；`tts` 和 `none` 镜头走 `h3-i2v`。
- **绑定加 `bypass`**：可选的文件槽位（`first_frame`、`video_in`、`ref_image`、`dialogue_audio`）没给文件时，绑定的节点删掉；`bypass` 列的节点也去掉，但把它某个输入的连线交给读它的节点（没有台词音频时 AddGuide 的 `positive` 直接进引导器）。不能像参考图那样直接删：引导器的 `conditioning` 是必填的。第 12 步的可开关分支（LoRA、ControlNet）也用这个。必填的文件槽位没给文件 → `ref_missing`。
- **适配器**：输入文件按 sha256 从 blob 库取，和参考图一样传 `/upload/image`（ComfyUI 收任何文件）；参数名 `first_frame` / `video_in` / `dialogue_audio`（sha256）、`duration_s`、`fps`，和 Mock 视频一致。WebSocket（`/ws?clientId=`，`websockets` 库，原来是 uvicorn 带进来的，现在写进依赖）收 `progress` → `CallContext.on_progress`（新字段，试跑任务接到 `job.updated`）；收到「跑完」就马上读 `/history`，有 socket 时历史每 5 秒兜底读一次，连不上或断了回到每秒轮询。取输出按槽位：`image_out` / `video_out` / `audio_out`，SaveVideo 的文件在 `images` 下、VideoHelperSuite 在 `gifs` 下都认。视频取回后探测：读不了 `invalid_response`、比要的短 0.5 秒以上 `video_too_short`、画幅差 2% 以上 `video_wrong_size`；`usage.output_seconds` 记实际秒数。试跑（`params.trial`）缺必填的输入文件时自己造一张图 / 一段音 / 一段视频。
- **仓库工作流被 `providers.yaml` 的模型点名时，库里就是那个模型**（`h3-i2v` → `comfy/h3`），不再另登记一个 `comfy/h3-i2v`；否则视频组件会多出一个只要 ComfyUI 就能跑的本地模型，绕过 `comfy/h3` 的 `needs`（节点、权重、CUDA）。

## 2026-10-26 · M5 第 3 步：体检、装依赖、试跑

- **体检只靠 `/object_info`**：图里的节点类 ComfyUI 不认识的算缺；**模型文件对照加载器那一项的可选列表**（ComfyUI 把模型文件夹里的文件列成下拉选项），不在里面的算缺，不另调 `/models/<folder>`。缺的节点类按 ComfyUI-Manager 的节点表（`/v2/customnode/getmappings?mode=cache`，旧版 Manager 不带 `/v2`）归到节点包；节点表里也没有的记成问题 `unknown_node`，状态「坏了」。绑定对不上图（标题没了、字段改名）记 `binding_broken`。导入后马上体检一次（ComfyUI 没开就先不体检）。
- **装节点包复用安装器**：`SetupService.install_node_packs` 先存 ComfyUI-Manager 快照（原因记 `install`，改动清单写节点包；快照列表的契约只有 install / manual 两种），再给每个包拼一个临时安装项（`git_clone` 到 `custom_nodes/<仓库名>` + `uv_pip` 装它的 requirements，和清单里的节点包一样），交给同一个 runner；示例机器走 FakeRunner。还没跑过我们安装器的机器也能装（镜像用 auto，没有权重文件夹）。**真实 ComfyUI 要重启才加载新节点包**：接口返回 `restart_required: true`，重启后再「全部体检」；示例机器装完立刻生效并自动全部体检。没有下载地址的模型文件不装，继续列着，让用户自己放。
- **装完节点包后坏了的工作流指回快照**：库记住最近一次装节点包前的快照；之前体检是「正常」、现在不是的工作流，加问题 `broke_after_install`（带快照名），状态记「坏了」，界面据此提示回滚（回滚走已有的 `/comfy/snapshots/{id}/restore`）。
- **试跑是 GPU 队列的任务**（`workflow_trial`，只跑一次不重试），通过 `router.call()` 用工作流对应的第一个组件、指定这个模型、不兜底，所以有 `model_call`。示例输入：固定一句提示词，尺寸是它支持的第一个画幅的草稿档（`spec/dims.py`，没写就 9:16 → 768×1366），视频取最短时长（没写 3 秒），图片时长记 0。通过后把「这次通过的文件哈希」记成登记哈希。试跑不属于某部剧，所以不读某集的成片规格，这是硬规则 10 的一个明确例外。

## 2026-10-26 · M5 第 2 步：工作流库（登记、档位、导入、绑定）

- **库进配置，而不是另开一套**：`core.config` 加 `Library` 覆盖层（`set_library`）。`get_config()` = 工厂 YAML + 库：`providers.yaml` 里没有的工作流变成本地模型 `comfy/<slug>`，按 kind 放进组件的 `local`（video → 视频生成；image → 关键帧、参考图；upscale → 超分；lipsync → 口型）。这样 ModelPicker、路由、能力过滤、注册表都不用改就认得导入的工作流。启动、导入、改档位、改绑定时重新发布；应用停止和每个测试开始时清空（否则上一个应用的库会漏进后面的测试）。
- **未验证的只能手动选**：`StudioConfig.unverified`，`resolve` 在覆盖之后把它们从 `alt_order`（「不满意换一个」）和 `fallback.to` 里拿掉；用户自己选的 `local_model` 保留。「我的工作流」加进组件的 `alt_order`。
- **仓库的 `workflows/<slug>/` 是推荐档，文件即真相**：每次启动按文件刷新绑定、能力、名字；`selfhost/`（上游旧格式）跳过。用户导入的放 `~/.drama-studio/workflows/<slug>/`（`workflow.api.json` + `workflow.yaml`，yaml 里 `pending` 记还没确认的猜测，`origin` 记来源），模型的 `workflow_root` 指过去，`ComfyUIAdapter` / `kf.local_workflow` 按它找文件。文件哈希变了：显示 `file_changed`，「我的工作流」降为未验证。
- **导入**：拖进来的 JSON 或 ComfyUI 列表里的路径；**UI 格式按 `/object_info` 转成 API 格式**（`wflib/convert.py`：静音的节点去掉、旁路的节点按同类型输入直通、`Reroute` 直通、`PrimitiveNode` 的值填进去、种子后面的「生成后控制」不算输入、备注去掉；不认识的节点类 409 `workflow_unknown_nodes` 列出来，子图 409 `workflow_subgraph`）。ComfyUI 存的、它自己列表里的都是 UI 格式，不转的话列表导入没法用。
- **猜绑定**（`wflib/guess.py`）：沿条件链往上找接到采样器 `positive` / `negative` 的 `CLIPTextEncode`（经过 `LTXVConditioning` 这种两路都进的节点时只走同名那一路）；第二个 `LoadImage` 起是参考图 1、2…；被猜中的节点标题不唯一时改成「原标题 #节点 id」，绑定按标题找。只把图里真能接上的绑定写进 yaml。
- **ComfyUI 的工作流列表走它的 user data 接口**（`/api/userdata?dir=workflows`、`/api/userdata/workflows%2F<path>`）：文件夹版、便携版、Desktop 都一样；Mock 的示例机器用 `wflib/demo/`（LTX-2 的 API 格式、SDXL 的 UI 格式、素材板）。素材板按文件名前缀「DramaStudio 素材板」或 JSON 里的 `extra.dramastudio.board` 认出来，不能导入。
- **接口返回的 `name` 是中文名**（契约是单个字符串；导入的工作流中英文同名）。

## 2026-10-26 · M5 第 1 步：工作流表、model_call 的工作流列、视频小工具

- **表 `comfy_workflow`**（迁移 `0019`）按 SPEC 4 的列，另加两列：`name_json`（`{zh, en}`，SPEC 写的 `name` 是单语言）和 `kind`（image / video / upscale…，ModelPicker 按组件的 kind 分组要用）。`slug` 唯一。文件还在 `workflows/<slug>/`，表里存档位、确认过的绑定、体检和试跑结果、做这些时的文件哈希。
- **`model_call` 加 `workflow_id / workflow_sha256 / comfy_env_hash / select_json`**：路由在开始调用时就写 `workflow_id`（本地模型的 `spec.workflow`，失败的调用也有），成功后从适配器的 `raw["comfy"]` 补哈希和环境；`select_json` 留给第 12 步按镜头选工作流的理由。节点包版本不另存：`comfy_env_hash` → `comfy_env.node_packs_json`。
- **`media/video.py`**：`probe`（解析 FFmpeg 对输入的输出：尺寸、时长、帧率、有没有声音；`imageio-ffmpeg` 不带 ffprobe）、`trim_head`（默认 0.3 秒，**重新编码** H.264 CRF 16 + AAC，保证按帧切而不是落到最近的关键帧）、`frame`（第一帧当封面、最后一帧给连续镜头当首帧，PNG）。都在线程里跑 FFmpeg。
- **Mock 视频可以带声音**（`with_audio` 参数 → 正弦波 AAC 音轨）：H3 原生音频、按台词对口型时视频本身有声音，后面的组件和后期要能区分。

## 2026-10-26 · M5 计划（Kelvin 定的四项）

计划见 `plans/M5.md`。
- **视频出终版按按钮**：本地草稿采纳后不自动出 2K，和关键帧一样在候选卡上点「用 API 出终版 · 约 $x」才花钱（H3 Regenerate-2K）。SPEC 7.7 写的「采纳时自动出」按这条改。原因：每次采纳草稿都花钱，用户控制不了。
- **按镜头选工作流做规则表 + LLM 建议，建议走 API 模型**（默认 DeepSeek，不占本机显卡、不跑本地 LLM）；**拼节点（beta）挪到之后（P3）**，ROADMAP 跟着改。
- **本机真跑 + 真实冒烟上限 $3**：本机下 H3 权重（约 65 GB，先存快照）跑草稿；API 冒烟 H3 API、Regenerate-2K、Seedance 2.5 各 1 条（视频比图片贵，默认的 $1 不够）。
- **配音方式两种都保留，每个镜头自己选**：分镜规划按镜头建议、用户在分镜页改，不设全局默认。对照 PLAN 的音频驱动模式：`tts`（先配音再对口型）= 模式 A（台词音频喂给 H3，`fully_copy`）；`native`（原生同步）= 模式 B（H3 自己出声，给锁定音色样本，说话人编号 S1/S2）；`none` = 不出声。模式 C（后期对口型）是 M6 的口型修复。`models_db.py` 注释里的「SPEC A / B / C」按这个对照改。
- **不在 M5 做**：自动质检和不达标重跑（M6，M5 的 take 显示「未检查」）、2K 精修接口和口型修复（M6）、后期页裁头开关和混音（M7）、看板其他指标（M8，M5 只做表头要的 `/metrics/summary`）、素材板和存回工作台节点（M9）。

## 2026-10-26 · 关键帧默认模型：本地 FLUX 3 Klein、API Nano Banana 2.1（Kelvin 定）

- **默认路由**：`components.yaml` 的 `kf` 预设 `balanced` 改成 `local: comfy/flux3-klein`、`api: google/nano-banana-2.1`；`kf.local` 改成 Klein 在前（`[flux3-klein, flux3-klein-t2i, qwen-image-edit, qwen-image, flux2-dev]`）。参考图 `img` 不换（仍是 Qwen-Image 草稿 → Nano Banana Pro）。
- **Klein 进安装清单但不是必装项**（`setup-manifest.yaml` 的 `w_flux3`，20.8 GB，固定 HF 修订和 sha256）：仓库要登录 HF 并同意许可，安装器还不会带 HF token，勾上会下载失败（可选项失败只记录）。两个 Klein 模型的 `needs` 写上 `[comfy, w_flux3]`，能力过滤因此认得它。以后安装器支持 HF token（存钥匙串，硬规则 3）时再考虑改成必装。
- **本地默认模型跑不了时先换同组件的下一个本地模型**（`capabilities.restrict` 新参数 `local_models`，`config.resolve` 传 `comp.local`）：按 `kf.local` 的顺序从当前模型往后找（到末尾从头找）这台机器能跑的，都不行才像原来一样改走 API / 关掉。不这样的话，没装 Klein 的 5090 草稿会走收费 API。替补只取有办法跑的：ComfyUI 模型要有工作流（FLUX.2 dev 只写了 `needs: [comfy]`、还没有工作流，不能当替补，否则只装了 ComfyUI 的机器会把草稿派给它）。
- **`Resolved.unavailable` 列出组件所有跑不了的本地模型**（原来只有路由上被拿掉的）：`kf.model_for` 靠它跳过跑不了的文生图模型，原来漏了不在路由上的（例如没装 `w_img_t2i` 时会选 Qwen-Image）。
- **示例种子**：关键帧草稿记成 `comfy/flux3-klein`，终版 `google/nano-banana-2.1`、$0.06（对比里的实际花费）；前端快照重导。

## 2026-10-26 · 关键帧模型对比：FLUX 3 Klein、Nano Banana 2.1

Kelvin 要求在 M4 分支上做（「湿了半边」保留不改，用来考新模型）。结果见 `reports/m4-kf-bakeoff.txt`。

- **FLUX 3 Image Klein 两个工作流** `workflows/flux3-klein`（按 1–4 张参考图编辑）、`workflows/flux3-klein-t2i`（文生图）：照 BFL 官方的 `flux3_klein_int8_mi2i.json` / `_t2i.json` 把子图展开成 API 格式。保留官方的 Qwen3.5 9B 提示词扩写（官方明说不要不带它用；系统提示词和贪心解码照抄），去掉框选那条路，输出尺寸按成片画幅；扩写的种子固定，同一提示词的几张候选共用一次扩写。全是 ComfyUI 0.41.2 的原生节点，不用装自定义节点包。权重 int8（主模型 5.8 GB + 文本编码器 4.9 GB + 扩写 9.8 GB + VAE 0.3 GB）这次手动用 `hf download` 放进 ComfyUI-Shared 的模型目录：HF 仓库要登录同意许可，安装器还不支持，`providers.yaml` 里因此没写 `needs`。以后进安装清单时，HF token 按硬规则 3 存钥匙串。
- **`kf.model_for` 改成取「排在当前模型后面」的第一个文生图模型**（到末尾再从头找）：每个编辑模型后面跟它本家的文生图（Qwen-Image-Edit → Qwen-Image，FLUX 3 Klein → FLUX 3 Klein 文生图）。`kf.local` 现在是 `[qwen-image-edit, qwen-image, flux3-klein, flux3-klein-t2i, flux2-dev]`，默认路由没改。
- **ComfyUI 的显存租约按权重文件区分占用者**（`ComfyUIAdapter._owner`，原来按工作流）：Klein 的编辑和文生图用同一套权重，原来两者之间也会 `/free`，把 20 GB 重新读一遍，读的时候 ComfyUI 报 `hostbuf_file_reader_read failed`（这台机器内存 32 GB）。用不同权重的工作流之间照旧释放（硬规则 8）。
- **Nano Banana 2.1**（`google/nano-banana-2.1`，`gemini-nano-banana-2.1`，按官方模型页和价格页核对）：和 Pro 同一个适配器，只填配置；2K 每张 $0.0504（我们 1080p 交付走 2K），最多 14 张参考图；进了 `img_api`（参考图、补视图、关键帧的可选 API 模型），默认路由没改。实测比估价贵 15–35%（默认中等思考），确认余量 max(10%, $0.05) 兜得住。
- **默认模型换不换等 Kelvin 定**（产品决定；已定，见上一条）：对比的结论是本地草稿 Klein 明显好于 Qwen-Image-Edit，API 终版 Nano Banana 2.1 和 Pro 差不多、便宜一半多。

## 2026-10-26 · Kelvin 看图之后：拼图、陌生人、风衣污渍

对照实验见 `reports/m4-local-smoke.txt` 末尾（同样的种子直接对本机 ComfyUI）。

- **参考图模板的任务行改成「一张单幅写实照片，单一视角」**，场景的类别说明改成「一个视角、一张完整的照片，看得清空间、光线和天气」。原来的「素材参考图：后面每个镜头都拿它当参考」会让 Qwen-Image 排成设定参考表那样的多格图（只去掉「素材参考图」、留着「后面每个镜头都照着它画」仍有 2/4）；改后楼道 8/8 单幅，角色、道具不受影响。不换成官方 50 步：同样没有拼图，但每张 65 秒，草稿要快。横屏（上一条）照留。
- **参考素材里没有角色的镜头，关键帧提示词加「[人物] 这个镜头里没有人物，不要画人。」**（`kf.NO_PEOPLE`）：不说的话 6 张里 5 张会冒出一个陌生人，加了是 1/6。
- **风衣污渍**是 1-01 剧本动作行里的「湿了半边」：换成「被雨淋湿」就没有了，换 40 步也还有。这是剧本内容，不自动改写。Kelvin 2026-10-26 定：示例剧本也不改，留着考新模型（默认换成的 FLUX 3 Klein 画这一镜没有污渍）。

## 2026-10-26 · 场景参考图固定横屏（Kelvin 定）

- **场景参考图一律画 16:9**，不跟成片规格（Kelvin 2026-10-26，M4 第 9 步本机真跑之后）。原因：Qwen-Image-2512 在 9:16 下画空景几乎总是分格拼图（楼道 4/4，提示词里说不要也没用），关键帧里的空间结构跟着不稳。角色、道具、画面文字仍跟成片规格。
- **写在配置里**：`components.yaml` 的 `img` 加 `aspects: { scene: "16:9" }`（`ComponentDefault.aspects`：素材类别 → 画幅，没写的跟规格），`img.asset_aspect(kind, spec_aspect)` 是唯一读它的地方；参考图组件和示例种子都用它。硬规则 10 管的是关键帧、视频、超分、导出、ComfyUI 节点，参考图不在其中。
- **改画幅不再建议重出场景参考图**：`spec_aspect` 的 `ref_images_suggest` 只在场景图的画幅会跟着规格变时才列（新旧规格下 `asset_aspect("scene", …)` 不一样），现在的配置下不会出现。前端测试假后端跟着删掉这一行。
- **已经锁定的竖版场景图不动**：示例 `demo --reset` 之后是横版；用户自己项目里已锁定的竖版场景图仍是有效参考，不标待更新，想换就解锁重画。

## 2026-10-26 · M4 第 10 步：真实冒烟

- **HTTP 402 归 `quota_exceeded`**（不重试，`modelhub/adapters/http.py:error_for`）：真实冒烟时 Gemini 的预付项目额度用完，返回 402 RESOURCE_EXHAUSTED，原来落到兜底的 `bad_request`。和 M3 的「429 + limit: 0」一样是钱的问题，界面已有「额度用完」的词条。
- **Nano Banana Pro 那张终版没有补跑**（Kelvin 定）：兜底到 Seedream 5.0 出的终版构图跟草稿、人物一致，算这一步通过；Google 充值之后用 `live_storyboard.py --only kf` 可以补（约 $0.14）。
- **冒烟脚本** `scripts/smoke/live_storyboard.py`：继承 `live_assets.LiveSmoke`（连接测试、每个组件的单次上限、总上限、超了取消）；分镜规划重跑一次、不采纳（第 3 项：不自动重做）；关键帧先在本地把 1-04 的两张参考图（林晚、楼道）重画锁定，再出本地草稿和 API 终版。

## 2026-10-26 · M4 第 9 步：本机真跑

- **没有锁定参考图的关键帧草稿改走 Qwen-Image**（第 3 步挪来的）：组件加钩子 `Component.model_for(inputs, model, settings)`（默认原样返回），`RunService.start` / `describe` 先读输入再定模型、再编译提示词和估价，所以提示词里的目标模型、任务的队列、显示的估价都是换过之后的。`kf.model_for`：本地模型的工作流 `needs_refs()`（有不可选的 `ref_image` 槽，Qwen-Image-Edit 2511）、这个镜头又没有锁定的参考图、也不是出终版时，取 `components.yaml` 里 `kf.local` 列表中第一个工作流不需要参考图、这台机器能跑（不在 `settings.unavailable`）的模型；都没有就不换，跑的时候按 `ref_missing` 照常兜底。`kf.local` 改成 `[qwen-image-edit, qwen-image, flux2-dev]`（原来的锚点 `img_local` 没别人用，删了）。原因：换哪个模型写在配置里，不在代码里写死模型名（硬规则 7）。
- **站位只写镜头用到的角色和道具**（`kf.blocking_text(items, in_shot)`，按参考素材的 id 或名字匹配，地标和机位照写）：分镜规划的站位是整场的俯视图，本机真跑时 1-02（门口的伞）、1-07（手机）的提示词写了「林晚在画面中间」，模型就画了一个不像林晚的陌生人。
- **关键帧模板 [约束] 加「一张完整的单幅画面，不要分格或拼图」**：Qwen-Image-2512 在 9:16 下画的场景参考图几乎都是分格拼图，Qwen-Image-Edit 会照着画成 2–3 格；加了这句之后 10 张关键帧都是单幅。参考图模板加同样一句没用（楼道仍是 4/4 拼图），没加。场景参考图怎么办留给 Kelvin 定（见 `reports/m4-local-smoke.txt`）。
- **本机冒烟脚本** `scripts/smoke/local_storyboard.py`：复用 `local_assets.py` 的计时、显存和报告；在临时数据目录里先把林晚、楼道、红伞用 Qwen-Image 重画并锁第 1 张（示例锁定的是 Mock 色块，拿它当参考没意义），便利贴、手机、锁屏时间只解锁不画（不传色块），再出 1-01、1-02、1-04 的草稿和没有参考图的 1-07。

## 2026-10-24 · M4 第 8 步：Mock 端到端

- **后端验收测试** `tests/e2e/test_script_to_storyboard.py`（真的起后端进程，Mock）：新建剧集走到素材全部锁定（M3 的路，`_confirmed_script` 多了剧名参数），然后分镜规划（原型的 9 个镜头，Mock 对示例第 1 集按 `plan.json` 回答）→ 7 个关键帧各出 3 张本地草稿（`model_call` 记在关键帧产物上）→ 1-04 选 B、用 API 出终版 → 9 个镜头都确认 → 分镜闸门；`gate_decision` 里每个镜头记了分镜规划和关键帧的哈希（接尾帧的只有分镜规划）；全集配音后 1-04 = 0.3 + 音频 + 0.2 秒、1-06（画外音）= max(5, 同样算法)，确认过的镜头不变「待更新」；改画幅列出 7 张关键帧、约 $0.94；改已锁定的林晚列出 6 个镜头、其中 4 个有自己关键帧的会重画。
- **规格什么时候锁**：出草稿不锁（候选等人选，没有采纳），第一个镜头确认（锁定选中的关键帧 = 采纳）时锁，和 SPEC 13.3「第一张关键帧采纳时」一致；测试按这个写。
- **Playwright 新项目 `m4`**（`e2e/m4.spec.ts`，不用示例数据）：预演按时长播放、1-04 的台词配音真的被播放（记录 `HTMLMediaElement.play` 的文件）、空格暂停；1-04 选 B → 出终版（SSE 收到 v2）→ 确认，其余镜头逐个确认，「去生成视频」确认分镜闸门。依赖 `seeded`（它给第 1 集配好了音）。
- **Playwright 项目顺序固定成 `seeded` → `m4` → `real` → `smoke`**：`m4` 要在 `real` 解锁「林晚出租屋」之前（否则 1-06 的关键帧待更新，闸门过不了）；`smoke` 里的 M2 流程会重新剧本化示例第 1 集（素材的出场场次跟着没了），原来 `real` 没有依赖、实际排在它前面，现在明确写成 `smoke` 依赖 `real`。`pnpm e2e` 仍是 `--project=smoke --project=real`，依赖的项目自动跑。

## 2026-10-24 · M4 第 7 步：动态分镜和安全区（前端）

- **`ShotOut.keyframe_sha256`**：选中那张关键帧候选的文件（关键帧产物当前版本里 `role: candidate`、`idx` = `keyframe_pick` 的那个；终版只有一张）。确认后锁定的是另建的 `pick` 版本，但当前版本不变，所以确认前后是同一张图。接尾帧的镜头是 null。镜头卡片、预演画面都用它（`fileUrl`），不再是占位色块。
- **预演（`storyboard/Animatic.tsx`，替换 `PreviewStrip`）**：rAF 时钟按镜头时长走（`timeline.ts:timeline`）。「播放预演」从头放；「暂停」停在原处并选中那个镜头（下面的设定跟着换，方便边看边改）；再播从停的地方接着放；停着时去点别的镜头，再播从那个镜头开头放；放完回到开头。点时间条上的镜头块跳到点的位置（键盘按回车跳到镜头开头）并选中它；当前镜头块里有进度。空格键播放 / 暂停，焦点在输入框、按钮、对话框等控件上时不抢空格。时间显示「00:10 / 00:34」是「播放」会从哪里放。
- **画面**：选中的关键帧；连续动作镜头用它接的那个镜头的（1-09 接 1-08、1-08 接 1-06，一直追到有关键帧的镜头），右上角标「接 1-06 尾帧」。真正的尾帧要等 M5 有视频。镜头卡片同样处理。画面固定大小（竖版高 224，横版宽 300），原型是 96×170 的文字块，放字幕和安全区太小。
- **声音和字幕**：每句台词（`GET /episodes/{id}/dub` 里这个镜头拍的说话行，按 `line_ids` 的顺序）从镜头开头 0.3 秒（`timing.PRE_ROLL_S`，前端抄了一份）起一句接一句放，超出镜头结尾的截掉；字幕是这句的文字，位置按成片规格的字幕位置（安全区配置里的 `subtitle`）。没配音的句子只有字幕，下面写「n 句还没配音 · 去配音」（链到素材页的「全部配音」）。旧的配音（`stale`）照样放。
- **「共 x 秒」那句**改成「用当前关键帧 + 台词配音 + 字幕，不花钱」（原型写「本地临时配音」，Kelvin 定了不做预演配音 `pv`）。
- **安全区**：一个「安全区」开关放在预演栏右边，同时管预演画面和镜头设定里的关键帧候选（默认关；不保存）。比例从 `GET /spec/presets` 的 `safe_areas` 读，选哪一组由 `lib/safeArea.ts:safeAreaKind` 按画幅和平台定（从 `SafeAreaPreview` 抽出来的算法）；成片规格页的预览也改读接口，前端不再有一份数字（`config/spec.yaml` 注释已改）。画在关键帧上的框不写名字，规格页的写。
- 前端契约：`SpecPresetsSchema.safe_areas`（区域 `key` 是五个已知名字的枚举，对应 `spec:preview.zone.*` 词条）、`ShotSchema.keyframe_sha256`。测试假后端：选候选、重跑时 `keyframe_sha256` 跟着变；`test/backend.ts` 的规格预设补 `safe_areas`。
- 页面测试用假的 `requestAnimationFrame` 和 `performance`（`vi.useFakeTimers({ toFake: [...] })`），其他计时器照常，查询和 MSW 不受影响。

## 2026-10-23 · M4 第 6 步：表格视图、拆分合并、时长（前端）

- **选中的镜头写进 URL**（`?shot=`，`replace`），视图是 `?view=table`（默认分镜板，不写参数）。原来点镜头只改页面内状态、剧本页的链接优先；现在两种视图和刷新都保持同一个镜头。
- **表格视图在镜头列表的位置**：预演条和运行条不变，「分镜板 / 表格」切换放在新的一行「镜头 · 9 个 · 34.5 秒」右边；表格下面仍是选中镜头的完整设定（站位、参考、首帧在表格里放不下）。类型、景别、运动用原生下拉，时长是数字框（离开时保存），台词、参考素材、关键帧（「已选 A」/「接 1-06 尾帧」/「还没有」）、状态只读。窄屏（1440）表格横向滚动。
- **一条改动路径**：表格的单元格、镜头设定、拆分、合并都走 `Storyboard.tsx:edit`：已确认的镜头（或分镜闸门已确认；合并时下一个镜头已确认也算）一律先 `shot_edit` 预览（拆分是 `{split: {after_line_id}}`，合并是 `{merge: true}`），否则直接调 PATCH / split / merge。改动被拒（比如短于音频）时表单复原。
- **拆分**：只拍一行的镜头直接拆（后端按动作 / 对白决定后一半拍不拍这行）；拍多行的弹出「在「…」之后切」让用户选切点（不提供「从中间切」，选第一个切点就是最常见的情况）。**合并**只和同一场的下一个镜头，没有就灰掉并提示。
- **时长**：输入框 `step=0.5`、最小值是音频长度（没有台词时 0.5），最大 60（后端上限）。下面一行写来源：「按台词音频算（含前后留白），最短 x 秒」/「手动设定 · 不能短于台词音频 x 秒」/「手动设定」/「按分镜规划」；手动设过就有「恢复按音频」或「恢复规划的 x 秒」（PATCH `duration_s: null`，前端 `ShotPatchSchema` 放开了 null）；超过视频单段上限写「超过 15 秒（视频单段上限），建议拆镜」。来源判断：`manual_s` 有值就是手动，否则看 `duration_source`（`audio` / 其余算规划）。
- **改动后刷新**：PATCH、拆分、合并成功后都刷新产物（分镜规划多了 `edit` 版本）和分镜进度，原来只有确认 / 取消确认才刷。
- 测试假后端补了拆分、合并（`ops.split` / `ops.merge` 的简化版：切行、重排镜头号、新的后一半有空的关键帧产物、合并掉的那个的关键帧产物删掉、接尾帧的改接后一半）和时长规则（`timing.shot_duration`）。
- 新词条：`storyboard.list.*`、`storyboard.table.*`、`storyboard.shot.durationSource.*` 等，错误码 `split_point_invalid`、`no_next_shot`、`no_shot_to_continue`。

## 2026-10-23 · M4 第 5 步：分镜页接后端（前端）

- **删掉的 MSW**：镜头的 PATCH、示例分镜规划和关键帧产物（`fixtures/demo/shots.ts` 整个删掉，`shotId` / `videoProductId` 挪进 `takes.ts`）、分镜闸门（放行到后端）、`spec_aspect`（MSW 自己的影响范围那条路整个删了，`impacts` 库也删了）、素材列表的镜头叠加和解锁叠加（`handlers/assets.ts` 删掉）、剧集列表的镜头数叠加。
- **还留着的**：`GET /episodes/{id}/shots` 只给第 1 集叠 `video_product_id`（按视频产物的 `owner_id` 找，不按镜头号，拆分后也对得上；M5 删）。生成页、后期页的 MSW 读镜头前先取后端的（`handlers/shots.ts:demoShots`，存进 `getDb().shots` 给同步代码用），所以分镜里改时长，后期时间线跟着变：示例整集现在是后端算的 34.5 秒（1-04 没配音，按剧本估计 4 秒加留白），后期页测试的位置跟着改了。示例进度只留生成、后期两步（`DemoSteps`）。
- **剧本块下游的示例叠加只留视频行**（M5）：原来还有原型写死的素材行（「素材 · 道具『红色长柄伞、黄色便利贴』」）和镜头、关键帧行，现在这些都由后端给（素材行 M3 起就有，镜头和关键帧行第 2–4 步），留着会重复。
- **素材的「出现在」**（`AssetOut.shots`）改由后端算：已采纳分镜规划的镜头（`shot` 表，未退场）里引用了它的，写成「1-04」，按 `?episode=` 过滤，按镜头号排。
- **`PUT …/spec?confirmed_impact=` 真校验**（第 4 步挪过来的）：`ImpactService` 记下应用过的预览（`applied(id)`，只记「只改这里」「确认并同步」，内存里最多 100 条，重启就没了）。规格已锁定又要改画幅时，id 必须是这个剧的 `spec_aspect` 预览、而且改的是同一个画幅，否则 409 `spec_locked`，和没给 id 一样，不加新错误码。应用 `spec_aspect` 本身就会写规格，所以前端改画幅不再调这个 PUT；它留给「应用之后再存一次规格」的客户端。
- **通用候选网格** `components/CandidateGrid.tsx`：固定尺寸的卡片 + 放大看（M3 定的宽屏做法），素材页的 `ImageCandidates` 和分镜页的首帧都用它。卡片尺寸挪到 `lib/cards.ts`（组件文件只导出组件，ESLint fast-refresh 规则）。`FinalButton` 挪到 `components/`，词条从 `assets.final.*` 挪到 `components.final.*`。
- **关键帧卡片下面写「本地草稿」或「API 终版」**：后端的候选没有原型里那句构图说明（「构图偏左，留门的位置」）；以后模型给了 `label` 就显示 `label`。
- **改已确认的镜头**（或分镜闸门确认之后）：改设定、画面描述都先做 `shot_edit` 预览，弹影响范围对话框，确认前什么都不写；「撤销」把表单复原（`ShotSettings` 重新挂载）。确认、取消确认直接走 PATCH（后端规则）。
- **Inspector 的单镜头覆盖** item 改成 `shot:<镜头 id>`，和后端 `runs.item_of()` 读的一致（原来是镜头号）。
- **测试假后端** `test/fakes/shots.ts`（数据是第 2、3 步导出的 `test/data/shots.json`）：改设定、选这个、确认（草稿锁成 `pick` 版本、终版整版锁）、取消确认、出草稿 / 出终版、分镜闸门、`shot_edit`、`spec_aspect`、素材改动和解锁里的镜头行。剧集列表、素材列表的假后端现在直接应答（不再经过 MSW 叠加）。
- 新词条：`storyboard.shot.kfDraft` / `kfFinal` / `editTitle`、`storyboard.status.stale`，错误码 `nothing_to_pick`、`duration_below_audio`，中英文都加了。

## 2026-10-23 · M4 第 4 步：分镜闸门、进度、影响范围（后端）

- **分镜确认**（gate `storyboard`，scope 集）：`GATES` 加一项，锁本集的分镜规划；`GateService.precondition(gate, fn)` 是新的可插拔前提，`ShotService` 登记：有镜头没确认或「待更新」就 409 `shots_not_confirmed {count, labels}`。取消确认一个镜头时，这一集已确认的分镜闸门一起重开（解锁分镜规划）。原来测「未知闸门」用的是 `storyboard`，改成 `takes`（M5）。
- **分镜进度**：`done` = 已确认的镜头数（含「待更新」的），`total` = 镜头数，`stale` = 「待更新」或关键帧待更新的镜头数，加上分镜规划本身待更新的 1。闸门确认了才是「已确认」。
- **`shot_edit`**（新的影响范围类型，目标是镜头 id）：patch 是 `ShotPatch` 的字段，或者 `{split: {...}}` / `{merge: true}`。拆分、合并已确认的镜头，普通接口也 409 `shot_confirmed`，要走这里。行：
  - 规划切片变了的关键帧由通用的依赖图列出（`stale_keyframe`）；分镜闸门确认时还有 `self_shot_plan`；
  - 自己出的行：`shot_reconfirm`（取消哪几个镜头的确认，合并时含下一个）、`shot_redraw`（只改了画面描述：没有切片变化，通用行列不出来，照 M3 改素材描述的 `asset_redraw`）、`gate_storyboard`。
  - 「只改这里」：先重开闸门、取消确认，再写入（`relock = False`：闸门重开了，不再锁回去）。「确认并同步」再给碰到的镜头（拆分时含新的后一半）重出关键帧草稿。
- **`spec_aspect`** 挪到后端（`ShotService.plan_aspect`）：
  - 行：`keyframes_redraw {count: 有版本的关键帧数, shots: 镜头数}`，估价 = 每张按路由上的 API 模型出终版的价钱（`RunService.final_cost`，示例 7 × $0.134）；`ref_images_suggest {count, aspect}`：按旧画幅出的已锁定场景参考图（可选，只提示）。视频到 M5 才有，不列。
  - `stale` 由规划器给（`PlannedChange.stale`）：规格不是产物，通用的依赖图算不出来。
  - 「只改这里」写规格、取消所有已确认镜头（闸门跟着重开）；「确认并同步」再给这些关键帧重出本地草稿。
- **`PUT …/spec?confirmed_impact=` 校验 id 挪到第 5 步**：现在前端的改画幅还走 MSW，MSW 的 apply 拿自己的 impact id 调 PUT（`e2e/smoke.spec.ts` 就走这条）。这一步校验的话，到第 5 步删 MSW 之前这条 e2e 会断。第 5 步前端改走后端的 `spec_aspect` 时一起做。
- **别的类型补镜头行**：`ImpactService.extra(kind, fn)` 让别的服务给一个类型加行。`asset_edit` / `asset_unlock`：`shot_refs`（用到这个素材的镜头，含连续动作，只算角色、场景、道具、画面文字）、`shots_confirmed_redraw`（其中已确认、有关键帧的，换图后要重新确认）。`line_edit` 改说话的行：`shot_duration_follows`（时长跟着重配的音频变，只提示）。动作行和加删行的镜头行由通用依赖图给（第 2、3 步）。
- 新词条：上面这些行和错误码 `shots_not_confirmed`，中英文都加了。

## 2026-10-22 · M4 第 3 步：关键帧（后端，Mock）

- **关键帧读已采纳的分镜规划和剧本的 payload**，不读 `shot` / `script_line` 物化表（组件的规矩）。依赖：分镜规划的新切片 `shot:<id>`（类型、景别、运动、站位、参考素材、拍的行、接哪个镜头，不含时长和声音，`plan.shot_plan_slicer`）、拍的动作行 `line:<id>`、传出去的每张锁定参考图（整版哈希）。
- **`keyframe` 进 `MEDIA_SLOTS`**：哈希含文件内容。否则 `pick` 版本的 payload 都是 `{"candidate": {}}`，不同的图锁出来哈希一样，确认记的哈希没意义。
- **`Invalidation.check(slot, fn)`**：没有产物承载的「待更新」原因。关键帧登记 `kf.stale_aspect`：显示的版本按别的画幅画的（`pick` 版本看它来源的草稿）。改画幅的影响范围是第 4 步。
- **参考图张数**：模型的 `caps.max_refs`；本地工作流按它的 `ref_image` 槽数（qwen-image-edit 3 张）；都没有就 3。出终版时草稿占第 1 张。没传的（未锁定，或超过张数）在提示词里点名。
- **确认这个镜头**（`PATCH {confirmed: true}`）：在 `lock_pick` 的同一个事务里写一条 `gate_decision`（gate `shot`，scope 镜头 id），哈希记分镜规划的 `shot:<id>` 切片和锁定的关键帧。终版只有一张图就锁整版，草稿锁选中的那张（没选默认第 1 张）。连续动作只记决定，要求它接的镜头还在（409 `no_tail_shot`）。关键帧已锁定（「待更新」后再确认）只记新决定。没有关键帧版本 409 `nothing_to_confirm`。
- **取消确认**：解锁关键帧，记 `reopen`。重开分镜闸门在第 4 步（闸门那时才有）。
- **`confirm_stale`**（「待更新」）= 已确认，并且分镜规划的切片哈希和确认时记的不一样，或者关键帧待更新（参考图换了、动作行改了、画幅改了）。
- **已确认的镜头改任何字段都 409 `shot_confirmed`**（含画面描述、选哪张）；第 4 步接影响范围 `shot_edit`。
- **规格锁定**：`on_adopt("keyframe")` 挂 `shots.service.lock_spec`，第一张关键帧采纳时（确认镜头时）`locked_at` 为空就写上，同一个事务。
- **`model_call.shot_id`**：产物的 owner 是镜头时 `Component._call_ctx` 带上。
- **没有锁定参考图时本地换 Qwen-Image**（2511 只能按参考图编辑）挪到第 9 步本机真跑时做：示例 7 个镜头都至少有一张锁定的参考图，Mock 下看不出区别。
- **示例**：关键帧产物 id 固定 `demo-p-kf-1-0X`（和 MSW 一样），在分镜规划物化之前建好。1-01–1-03：v1 本地草稿 3 张（10:55）+ v2 Nano Banana Pro 终版 1 张（11:02，$0.14，父版本 v1），锁整版、11:02 确认；1-04–1-07：v1 草稿（11:06）。依赖和提示词都用 `kf.gather` / `kf.pick_refs` 算，和真跑一样。`shots.json` 导出加上 7 个关键帧产物，不再替换随机 id。
- **影响范围里的关键帧**：示例关键帧有了真实依赖，通用的依赖图就会列出它们（`stale_keyframe` / `then_keyframe` / 解锁素材时的 `uses_keyframe`），这一步先让它们说清楚是哪些镜头：图节点加 `label`（镜头号「1-04」，`n` 是镜头所在的集），镜头的产物分组时总带 `count` 和 `shots`；`uses_keyframe` 的名字用镜头号。中英文词条一起加。连续动作镜头（没有关键帧）、改画幅、`shot_edit` 这些专门的行仍在第 4 步。
- 新错误码的中英文词条：`shot_confirmed`、`nothing_to_confirm`、`no_tail_shot`、`no_keyframe`。
- 第 2 步的 `test_shots_api` 里改镜头的两个测试从 1-02 换成 1-05：1-02 现在是已确认的示例镜头，不能直接改。

## 2026-10-21 · M4 第 2 步：分镜规划（后端）

- **模型的回答用规则补齐，不为覆盖问题重试**（计划写的是「不过就带着错误重试一次」）：没拍到的行补一个镜头（画外音叠到它前面那个镜头上），说话的行重复了只留第一次，每场第一个镜头不是连续动作，连续动作接哪个镜头按规则定，参考素材只留本集的、没给就按素材分析的出场位置补，没给站位就按参考素材摆、机位按景别放（`shots/ops.py:normalize`）。原因：这些都能确定地修好，重试多花一次 LLM 的钱还不一定改对。JSON 本身不合格时仍按原来的结构化输出重试一次。
- **插入镜头** = 特写、参考素材里没有角色（便利贴、手机）。连续动作默认接同一场里它前面最近的非插入镜头；模型给的 `continues`（第几个镜头）在同一场、在它前面时照用。
- **镜头列表读分镜规划的当前版本**（和剧本页一样），`shot` 表是已采纳版本的物化；改镜头从当前版本出 `edit` 版本并采纳。重跑出的新版本不自动采纳（`plan` 是普通 LLM 组件：第一次自动采纳，之后要用户点）。
- **场号和地点由接口分开给**：`scene_no`（全剧场号）、`scene_place`（场标题去掉日 / 夜、内 / 外），前端拼「场 n · 地点」。M0.5 契约的 `scene_label` 是写死的中文，删了。`dialogue` 按剧本原样拼（「林晚（OS）：……」），是内容不是界面文字。
- **分镜规划产物什么时候有**：一集的剧本被采纳时建（`ProductService.on_adopt` 改成一个槽位能挂多个物化函数，剧本槽位多挂一个 `shots.service.ensure_plan`）；启动时的 `ensure_series_products` 也会补。关键帧产物在分镜规划物化时给每个非连续镜头建好（组件 `kf` 第 3 步才有），镜头退场或改成连续动作时标 `retired`。
- **切片**：分镜规划依赖剧本切片 `shots` 和素材清单的新切片 `ids`（每条素材的 id、类别、名字，不含描述：重新描述素材不会让分镜变旧）。`shots` 是场的地点、时段和每行的 id、类型、说话人，**不含任何台词或动作的文字**：计划「设计要点」写的是「非对白行的文字」也算，和 Kelvin 定的第 3 项（改一行动作描写只让拍它的镜头的关键帧待更新）对不上，按 Kelvin 定的改。加删行、换类型或说话人才让分镜规划待更新。
- **影响范围里的分镜规划**：新行 `stale_shot_plan` / `then_shot_plan`，写明「不自动重做」。「确认并同步」的预计花费不再算级联不会重跑的产物（候选类和 `cascade_rerun` 关掉的，判断条件抽成 `component.reruns_in_cascade`，级联和估价共用）：原来分镜规划的估价会被算进「确认并同步 · 预计 $x」，但级联并不跑它。
- **拆分、合并**：拆分默认从中间切；只有一行时动作行两边都拍、对白留在前面、后面是 2 秒的反应镜头；原来接它尾帧的连续镜头改接后一半。合并只和同一场的下一个镜头合，行按剧本顺序排，规划秒数相加，手填的时长清掉。
- **示例种子**：第 1 集分镜规划 v1（DeepSeek V4 Pro，10:48，已采纳），9 个镜头 id 沿用 `demo-shot-1-01`…，内容是 `tests/fixtures/demo/plan.json`（照原型）。没配音时 1-04 按剧本估计 4 秒、加留白 4.5 秒，整集 34.5 秒（原型 34 秒）。
- **MSW**：`GET /episodes/{id}/shots` 只回示例第 1 集（MSW 库里有镜头的），别的集放行到后端；`PATCH /shots/{id}` 不认识的 id 放行。`mocks.test.tsx`「不认识的 id 返回翻译好的错误」改用后期时间线（还在 MSW 的接口）。
- `assets.service._scene_numbers` 挪成 `episodes.service.scene_numbers`（公开）：镜头服务也要用，第 4 步素材的影响范围又要列镜头，放在素材服务里会循环导入。

## 2026-10-21 · M4 第 1 步：镜头表、时长规则

- **表 `shot`**（迁移 `0018`）：分镜规划已采纳版本的物化表，和 `script_line` 一样按 id upsert、退场标 `retired`。列名用前端契约（M0.5 `schemas/shots.ts`）已有的 `framing`、`asset_ids_json`，不用 SPEC 4.1 的 `size`、`character_ids` / `prop_ids`：参考素材本来就是素材 id，角色、场景、道具、画面文字一个列表就够。时长分两列：`duration_s` 是分镜规划给的秒数，`manual_s` 是用户手填的；显示的时长读的时候现算（下一条），所以重配音不产生新版本。关键帧提示词的意图层在关键帧产物上，`intent` 只是规划给的种子（M3「描述 = 意图层」）。
- **`timing.shot_duration`**（Kelvin 定第 1 项）：说话的行（对白 + 画外音）的音频一句接一句，前后各留 0.3 / 0.2 秒，是这个镜头最短的长度；有对白时就用它（来源「音频」），用户手填的更长就用手填的（「手动」）；没对白时用手填的，再没有用规划的秒数，再没有 3 秒。手填的比音频短（比如重配音后音频变长了）时按音频算、来源变「音频」。`longest_take_s` 取视频路由上各模型 `caps.duration_s` 上限中最小的（H3 15 秒），超过就建议拆镜。
- **`Component.cascade_rerun`**（默认开）：关掉的组件「确认并同步」不自动重跑，只标待更新（Kelvin 定第 3 项，`plan` 第 2 步关掉）。和 M3 的停止集（候选类组件）合在 `cascade._cascades` 里判断。
- **流水线顺序**：`shot_plan` 9、`keyframe` 10，排在台词配音后面，待更新数算进「分镜」一步；没登记的槽位排到最后（99，原来是 9）。

## 2026-10-21 · M4 计划（Kelvin 已定）

计划见 `plans/M4.md`（2026-10-21 批准）。Kelvin 定的四项：

1. **镜头时长**：有对白的镜头 = 台词音频 + 前 0.3 秒 + 后 0.2 秒（来源「音频」），可以手动加长、不能短于音频；没对白的镜头用分镜规划给的初值（来源「手动」）；画外音叠在动作镜头上时，取动作镜头的时长和「画外音 + 留白」中长的。SPEC 5.1 原文是「有台词就按音频算」，画外音那一条按这里改：画外音不对口型，镜头长短由动作决定（示例 1-06 关门 + 画外音仍是 5 秒）。
2. **不做预演配音 `pv`**（原型「分镜」页 Inspector 的第三个组件）：动态分镜直接放 M3 的台词配音（锁定音色，每句不到 $0.01，本地 IndexTTS 免费）；还没配音的句子静音、只显示字幕，旁边给「去配音」。原因：再出一份临时配音，时长会和正式配音对不上，而镜头时长按正式配音算。
3. **分镜规划不跟着「确认并同步」自动重做**：剧本加删行、改结构后分镜规划标「待更新」，由用户在分镜页重跑再采纳；只改某一行动作描写时，只有拍这一行的镜头的关键帧待更新；改对白措辞不影响分镜（重配音，时长跟着变）。原因：重做会盖掉手改的景别、站位和已确认的镜头。实现上是组件开关 `cascade_rerun`，`plan` 关掉。
4. **本机真跑 + 真实冒烟**：本机用 ComfyUI 的 Qwen-Image-Edit 拿多张锁定参考图出关键帧草稿；冒烟跑 DeepSeek 分镜规划第 1 集 + Nano Banana Pro 关键帧终版 1 张，上限 $1。

计划里定的其他几项：

- **验收里的「9 张关键帧」实际是 7 张**：1-08、1-09 是连续动作，接上一镜的尾帧，没有自己的关键帧（PLAN「连续动作镜头用上一段末尾片段续写，其余镜头都从关键帧起步」，原型也是这样）。改画幅时 9 个镜头都要重新确认，重画的是 7 张。动态分镜里连续动作镜头先显示来源镜头的关键帧，真正的尾帧要有视频，在 M5。ROADMAP 的两条验收加了说明。
- **关键帧和参考图一样走混合出终版**：本地出 3 张草稿，选一张后用 API 出 1 张终版（M3 第 5 项）。原型确认过的镜头「v2 · 3 张终版」不照做。
- **不在 M4 做**：连续性账本 `continuity_state`（M6）；真正的尾帧和首帧之外的尾帧关键帧（M5）；带字镜头默认走 GPT Image 2（等 P0 中文文字实测，现在可以在这个镜头的运行设置里手动换）；动态分镜导出幻灯片式 MP4（SPEC 5.1 写的是可选，之后）；H3 价格换成国内站价格（M5，和 H3 适配器一起；本文件「MiniMax 用国内站，Seedream 按火山方舟人民币价」那条写成了「H3 适配器 M4 才做」，H3 适配器在 ROADMAP 的 M5）；生成页 `?shot=` 用镜头号、分镜页用镜头 id 的不一致（M5 改生成页时统一）。

## 2026-10-21 · M3 合并之后

- **M2 的剧本不调提示词、不开思考**（Kelvin 定）：看了 M2 整本真实冒烟写出来的剧本（`reports/m2-live-smoke-book.txt`）之后定的。写作组件的提示词不改，各模型照旧关掉「思考」（`providers.yaml` 的 `request`）。M2 报告「遗留问题」里剧本质量那一条到此结束。
- **SSE 测试的服务器最多等 30 秒启动**（`tests/api/test_events_sse.py`）：原来只等 5 秒。应用启动时会建 Mock 示例剧集，M3 之后多了示例图和音频，本机启动约 1.7 秒。PR #5 的 Windows CI 比平时慢约 3 倍（整套 pytest 37 分钟），两个 SSE 测试在准备阶段超时（651 过、2 个 error）。现在服务器任务提前退出时直接抛出它的错误，不用等满 30 秒。同一次的 Linux CI 是另一个原因：下载 pnpm 时 registry.npmjs.org 超时，和代码无关。
- M4 分支 `m4-storyboard` 从合并 PR #5 后的 main（fb08576）先开出来，放这两项（main 不直接推）。M4 计划批准后接着用这个分支。

## 2026-10-21 · M3 第 14 步追加：OCR 句末标点、确认金额留余量

Kelvin 看了真实冒烟的结果后定的两项。

- **OCR 没读到句末标点不算漏字**（`qa/ocr.py:_matches`）：GPT Image 2 那张便利贴上写了句号，RapidOCR 没读到，原来判「漏字」、锁定要强制。现在文字末尾的标点（NFKC 之后 Unicode 类别 P*，比如「。」「！」「。」」）没读到也算一致。读成别的标点、中间的标点漏掉、整段只有标点，这几种仍按原规则判。代价：模型真漏画了句末标点时查不出来。
- **Mock 和示例的「OCR 不一致」改成漏掉「点」字**：原来去掉的是最后一个字，正好是句号，在新规则下算一致。现在去掉倒数第二个字：示例便利贴 D 读成「楼下便利店，等你到十二。」，`ocr_mismatch` 也一样。原型的 D 去掉的是句号，和新规则冲突，按新规则改。
- **确认金额留余量**（`components.yaml` 的 `confirm_margin`、`ConfirmMargin.allowance`、`BudgetGuardImpl`）：确认过的任务最多花到「确认金额 + 余量」，余量取确认金额的 10% 和 $0.05 中大的那个。原来花到确认金额就停（`budget_exceeded`）：估价稍微偏低时，多次调用的任务会停在最后一次，前面花的钱白花。例子：Nano Banana Pro 实际比估价多 2.7%，确认 4 张会在第 4 张之前停下。没确认的任务仍按单次上限，不留余量。`budget_exceeded` 的提示改成「单次上限，或确认的金额加余量」。
- **真实音色**：Kelvin 听了 MiniMax 的音色和两句配音，和之前生成的差距不大，有的能用、有的不能用。代码不改，靠多出几个候选来挑。

## 2026-10-21 · M3 第 14 步：真实冒烟

结果见 `reports/m3-live-smoke.txt`。跑了五次，合计 $1.72（Kelvin 批准的清单约 $1.78，脚本上限 $3），清单上的四步全部跑通。

- **冒烟脚本**（`scripts/smoke/live_assets.py`）：在进程内起应用（临时数据目录，先按 Mock 建示例剧集，再把所有模型切成真实的；`DRAMA_MOCK=0` 启动不建示例）。本地模型的安装位置和 ComfyUI 取正开着的工作台的（同 `local_assets.py`）。每个 API 步骤都是「本地免费草稿 → 用 API 出 1 个终版」，所以只付 1 张图或 1 个音色。花钱的保护：先跑连接测试（免费）；每个组件的单次上限临时设成该步额度（`LIMITS`），估价超了任务就等确认，脚本取消；每步开始前查「已花 + 额度 ≤ 上限」，运行中每半秒查一次，超了就取消；本地草稿兜底到了 API 就停。`--mock` 全程走 Mock、不花钱。
- **音色和配音用林晚，不用周屿**：示例第 1 集只有两句台词，都是林晚的（一句耳语、一句平静）。所以先解锁她的 Mock 音色，再试听、出终版、锁定，配这两句；耳语那句正好走 speech-2.6-hd。
- **Seedream 不带 `sequential_image_generation`**：5.0 flash 收到就报 400 `InvalidParameter`（组图只有 lite 有），参数删掉了。
- **额度用完不当限流**：新错误码 `quota_exceeded`，不重试，中英文提示「这家账户的额度用完了，或者在控制台设了用量上限……去厂商控制台处理」。认定的情况有三种：429 正文里有 `limit: 0`（Gemini 项目没开通付费，免费层没有出图模型的额度）、`insufficient_quota`（OpenAI 没余额）、方舟的 `SetLimitExceeded`（安全体验模式的用量上限）。`http.send()` 改成以错误映射的 `retryable` 为准（原来只看状态码，429 一律重试）。原来这几种都是 `rate_limited`：请求重试 3 次、任务再重试 3 遍，提示还写「调用太频繁」。
- **路由把失败原文写进日志**（`router.py`，warning，前 500 字）：`model_call` 只存错误码，兜底之后任务的报错又是兜底模型的，第一次冒烟时 Gemini 为什么失败查不到。厂商的错误正文里没有密钥。
- **核对的数**：GPT Image 2 一张 1088×1920 实际 $0.1721（估价 $0.2262，按 token 估偏高约 30%，往高估、不改）；MiniMax 音色设计费 $1.3947（¥9.90），5 个变体和两句配音按计费字数，合计和估价相差不到 $0.001；耳语走 2.6 HD。GPT Image 2 单张约 64 s。
- **图像终版**（第 5 次，Kelvin 给 Gemini 的项目开通付费、关掉方舟安全体验模式之后；第 4 次两家还没生效，照样 `quota_exceeded`、不重试、$0）：Nano Banana Pro 1536×2752、21 s、$0.1376；Seedream 5.0 flash 1088×1920、15 s、$0.0169。两张都按本地草稿的构图出。**Nano Banana Pro 估价偏低约 2.7%**：估价按每张 $0.134（1120 个输出 token），实际还有输入（提示词 + 参考图）和思考 token，约 $0.004。单张任务不受影响；但确认过的多张任务会在最后一张前停下（确认 4 张 $0.536，花了 3 张 $0.4128 后第 4 张查 $0.4128 + $0.134 > $0.536 → `budget_exceeded`）。价格是界面上展示的官方单价，没改；留给「确认金额要不要留余量」一起定。
- **等 Kelvin 定**：GPT Image 2 那张图上句号写着，但 OCR 没读到句末的「。」，判成「漏字」（`ocr_ok: false`，锁定要强制）。现在的规则是逐字比、标点也算（第 5 步）。要不要放宽成「句末标点没读到不算错」？

## 2026-10-21 · M3 第 13 步追加：补视图用官方 40 步

Kelvin 看了同一张锁定参考图上 4 步和 40 步的对比后定的。

- **对比**（周屿，5090，同一张本地出的参考图）：4 步 Lightning（cfg 1.0）每张 4–8 s，皮肤磨皮感重、放大有细网格纹，头发和耳朵边缘发软。官方 40 步（不接 LoRA、cfg 4.0、负面提示）每张 47–103 s，一个角色约 6 分钟（4 步约 1 分钟），皮肤、发丝、耳朵都自然。问题是 cfg 4.0 时提示词才真正起作用：「生气」画成龇牙皱鼻、「难过」快哭出来，侧面变成仰头的 3/4 侧脸。
- **新工作流 `workflows/qwen-image-edit-hq/`**、模型 `comfy/qwen-image-edit-hq`（「Qwen-Image-Edit 40 步（本地）」，`needs` 同 `w_img`，不用下新文件）。和 `qwen-image-edit` 是同一张图，只是去掉 LoRA 节点、steps 40、cfg 4.0，和官方模板关掉 LoRA 时一样。`est_seconds` 80。
- **补视图的本地模型改成它**（`components.yaml`；`local` 列表里 4 步的仍可在「模型与兜底」里选）。草稿、画面文字、关键帧仍是 4 步。示例剧集里林晚的视图版本也记成这个模型。
- **负面提示**（`views.py:negative_for`，适配器原来就支持 `negative` 槽位）：通用的「低画质，模糊，畸形，五官变形，拼图，分格，水印，文字」，侧面加「正脸，3/4 侧脸，两只眼睛，仰头」，背面加「侧脸，回头，转身」，愤怒加「龇牙，露齿，张嘴，皱鼻子，狰狞，夸张表情」，难过加「哭泣，眼泪，张嘴，五官扭曲，夸张表情」。负面提示写在组件里，工作流的节点默认是空的（同模板）。API 模型和 4 步工作流（cfg 1.0）不吃负面提示，照样传、不起作用。版本的 `payload.negative` 记每张用的负面提示。
- **正面提示收紧**：侧面「标准正侧面，脸和身体都转向画面左侧 90°，只看得到一只眼睛，平视前方」；背面「完全背对镜头，头和身体都不转」；愤怒「压着火的怒意：眉头紧锁、嘴唇紧闭、眼神发冷」；难过「眼神低垂、嘴角微微下沉、神情落寞」。
- **ComfyUI 偶发 `hostbuf_file_reader_read failed`**：重跑冒烟时 2512 草稿在 KSampler 里报这个错（ComfyUI 0.41.2 的 `comfy_aimdo` 从文件往显卡读权重失败；当时刚从 Edit 换到 2512，后台还在跑 pytest，内存紧）。我们按 `comfy_failed` 兜底到 API、记了 `model_call`，行为是对的；冒烟脚本原来不查参考图是谁画的，拿 Mock 占位图补了视图。现在参考图不是本地画的，这一步就报失败。

## 2026-10-21 · M3 第 13 步：本机真装真跑

结果和耗时见 `reports/m3-local-smoke.txt`。

- **`DRAMA_REAL_LOCAL=1`**（`modelhub/registry.py`）：Mock 模式下，`runtime` 是 `comfyui` / `python` 的本地模型照样建真实适配器，API 和写作模型（包括本地 LLM 服务）仍是 Mock。用来在本机真跑本地模型而不花钱；也可以给 `start.ps1` 的后端设上，在界面里看本地模型的真实结果。默认关。
- **本地冒烟**（`scripts/smoke/local_assets.py`）：进程内起一份应用（临时数据目录、Mock 示例剧集），把安装位置和 ComfyUI 地址换成正在开着的工作台扫描到的（读它的 `/setup/profile`、`/comfy/env`，不改它），按组件真实走一遍：草稿、画面文字 + OCR、补视图、音色重新试听、IndexTTS 本地终版 + 锁定、全部配音。每步核对 `model_call` 都是 `local` 成功（兜底到 Mock API 也算失败），记耗时和 `nvidia-smi` 的显存峰值。只跑部分步骤时报告写在临时目录，不覆盖正式报告。
- **配音用真实流程**：示例里林晚的音色是 Mock 的正弦波，拿它当 IndexTTS 的说话人样本会克隆出近乎静音（电平检查报 `audio_silent`）。冒烟先解锁她的音色（影响范围「标记待更新」）、Qwen3-TTS 重新试听、IndexTTS 出本地终版并锁定，再「全部配音」；本地音色没有 MiniMax 的 `voice_id`，台词自动走 `local_final`（IndexTTS）。
- **画面文字的提示词改了**（`prompts/templates/text/default.j2`）：第一行原来是「4 张候选：手写纸条、手机屏幕、招牌这类…」，还有一行给人看的「[核对] 每张出图后 OCR…」。Qwen-Image 照字面画成 3–4 格拼图（还画了一格手机），OCR 读到同一句话几遍、逐字比对全不一致。改成「一张画面，里面只有下面这一处字，一字不差」，约束加「单幅画面，不拼图、不分格；这处字只出现一次」，4 张都是单张、OCR 全部一致。和原型 `Assets.dc.html` 的编译层文案不同（原型写「4 张候选」）：发给模型的是一张图的请求，候选张数是我们发几次。参考图的模板本来就没写张数。
- **台词结尾留缓冲**（Kelvin 听出来的：「音没有完全吐完整就结束了」，`media/audio.py`）：原来在拉响度**之前**按固定的 −45 dB 裁首尾静音、结尾只留 50 ms，耳语和句尾的轻音被当成静音切掉（「……周屿？」原始 1.28 s 存成 0.80 s）。现在静音按拉响度之后的音量算（门限 = `trim_db` − 要提高的增益，最低 −90 dB），结尾留 `tail_s` 的一半（0.15 s）自然收尾、最后 50 ms 淡出，再补一半（0.15 s）静音。`tail_s` 在 `components.yaml` 的 `audio.dialogue`，默认 0.3。每句台词因此长约 0.3 s，场时长照旧等于音频之和。
- **Qwen3-TTS 限长**（`workers/worker_qwentts.py`）：试听时有一句 9 个字的台词生成了 78 s（模型没给结束，一直说到 qwen-tts 默认的 2048 步），这段还被带进了本地终版当锚点。现在按字数给 `max_new_tokens`（3 s + 0.8 s / 字，12 步 / 秒，远超正常语速），碰到上限重来一次，两次都碰到报 `tts_runaway`。
- **补视图用真实参考图**：示例里锁定的参考图是 Mock 占位图（色块 + 名字），补视图拿它当参考只能乱编：四格是四个不同的人，占位图上的字被画成标签（Kelvin 看到的 `linwan-views-view-2-expressions.png`）。冒烟改成先用 2512 本地给周屿出图、选第一张锁定（锁定会自动开始补视图），再看三张视图：侧面、背面和参考图是同一个人同一身衣服，表情图是同一张脸、没有乱字。表情图要的「2×2 四种表情」一次出成一大两小三种，另一次出成 6 格且扭曲（手伸进嘴里、拼接断开）。
- **表情一张一种**（Kelvin 2026-10-21 定，`pipeline/components/views.py`）：补视图从 3 张（侧面、背面、表情拼图）改成 6 张：侧面、背面、平静、微笑、愤怒、难过，表情都是正面头肩特写、「只画这一个人、这一张脸，单幅画面不拼图」，愤怒和难过加「克制不夸张，五官不变形」。一张脸占满 928×1664，4 步模型也不变形；每个角色多 3 次调用（约 6 s 一张）。界面按版本自己的 `payload.views` 列视图，2026-10-21 之前的版本还是一张「表情」。Qwen-Image 偶尔在角落加一小块像水印的模糊字，之后看要不要在负面提示里压。
- **GPU 队列先跑完已加载模型的任务**（硬规则 8，`core/jobs.py`，Kelvin 问到）：原来只按优先级和先来后到，补视图（ComfyUI）和配音（IndexTTS）交替排队时每个任务都换一次模型（每次 15–30 s）。现在 `gpu` 队列在同一优先级里，先跑和上一个任务同一模型（`params.model_key`）的；优先级照旧最先。只看任务的主模型：一个任务里换模型（画面文字里的 OCR、配音兜底到 IndexTTS）由显存租约管。
- **结论**：两个工作流、三个 worker 在 5090 上都能用，显存租约换手正常（ComfyUI 跑完占着约 28–31 GB，TTS 拿租约时 `/free`）。首次加载：Qwen-Image 约 20 s、Edit 约 25 s、Qwen3-TTS 约 17–29 s、IndexTTS 约 32–38 s；之后 2512 草稿 4 张约 13 s，补视图 6–9 s / 张，试听 3–9 s / 句，IndexTTS 约 4 s / 句。
- **没覆盖**：声音好不好听、图好不好看由 Kelvin 判断（冒烟只核对跑通、尺寸、时长、OCR）。

## 2026-10-21 · M3 第 12 步（下）：ComfyUI 适配器、两个工作流、`uv_sync`、清单四项

版本、文件、哈希都按官方仓库 / Hugging Face 接口核对（2026-10-21）；第 13 步在本机第一次真跑。

**ComfyUI**
- **工作流目录**（SPEC 6.4.2，`modelhub/workflows.py`）：`workflows/<slug>/workflow.api.json`（API 格式）+ `workflow.yaml`（`bindings`：槽位 → 节点标题 + 字段，标题必须唯一、字段必须存在，载入时就检查；`models`：加载器用到的文件；`caps.sizes`：各画幅的尺寸）。参考图槽位可以写 `optional: true`：参考图比节点少时，删掉空着的 LoadImage 和所有读它的输入。`providers.yaml` 的 `workflow:` 指向目录；目录还没有的（H3、SeedVR2 等）照旧不可用，M5 再改格式纳入。
- **两个工作流**按官方模板（Comfy-Org/workflow_templates d0e41fe）改写：`qwen-image`（2512 fp8 文生图）、`qwen-image-edit`（2511 int8 按参考图编辑，最多 3 张参考图）。和模板不同：① 默认打开 Lightning 4 步 LoRA（steps 4、cfg 1.0；模板默认关，50 / 40 步）——草稿要快；② 输出用 PreviewImage（临时文件夹），不往用户的 ComfyUI output 里留文件；③ 编辑工作流的采样起点改成 `EmptySD3LatentImage`，输出按成片画幅（9:16 → 928×1664），模板是 VAEEncode 参考图 1，9:16 会变成 752×1392（denoise 1.0 时起点只决定尺寸）。int8 convrot 用自带的 UNETLoader（ComfyUI 0.27.0 起支持）。
- **尺寸**：按模型卡推荐的各画幅尺寸（9:16 → 928×1664），不是成片的 1080×1920（不是 16 的倍数）；到成片尺寸靠之后的超分 / 导出。没有对应画幅时按 `max_pixels` 缩放到 16 的倍数。
- **调用**（`adapters/comfyui.py`）：参考图上传到 `input/dramastudio/<sha256>.png` → `/prompt` → 每秒查 `/history/{id}`（不做 WebSocket，M5）→ `/view`。n 张候选 = n 个 prompt，种子 seed、seed+1…；没给种子就随机一个，用到的种子记在结果里。
- **停下**：路由的本地超时 / 取消时调 `/interrupt`（带 prompt_id，只停我们的，用户在 ComfyUI 里手动跑的不受影响）并把它从队列删掉。每 10 次轮询看一次 `/queue`，任务既不在队列也不在历史里（用户清了队列）就报 `comfy_lost`，不用等 10 分钟超时。
- **出错码**：`/prompt` 400 时缺模型文件（`value_not_in_list`）→ `comfy_model_missing`，缺节点类 → `comfy_node_missing`，其余 → `workflow_invalid`；运行出错 → `comfy_failed`，显存不够 → `out_of_memory`，被中断 → `comfy_interrupted`；连不上 → `comfy_not_running`。都会兜底到 API，提示文字在 `common:modelError`。
- **显存租约**：每个工作流一个持有者（`comfy:<slug>`），换别的模型（TTS worker 或另一个工作流）时先让 ComfyUI `/free`（卸载模型、释放显存），对应 SPEC 6.4.7「切换大模型前 /free」。
- **ComfyUI 地址**从上次扫描拿（`SetupService.comfy_target()`：扫描到的 URL，没有就按端口，扫描前 127.0.0.1:8188）。**可复现**：结果的 `raw["comfy"]` 带 `workflow_id`（目录名）、`workflow_sha256`（API JSON 的哈希）、`comfy_env_hash`（上次扫描的环境），写进 `product_version` 的同名三列（`media_draft` 取第一个本地调用的）；媒体缓存里也存一份，重试命中缓存时照样有。`model_call` 没有这三列，M5 接工作流库时再加（SPEC 9.x 的复现字段）。
- **健康检查**：`/system_stats` 通、`/models/<folder>` 里有工作流要的每个文件。
- **清单 `w_img_t2i`**（约 31.8 GB，已装 `w_img` 时文本编码器和 VAE 校验后跳过，实际新下约 22 GB）：Qwen-Image-2512 fp8（Comfy-Org 没有 2512 的 int8 版；lightx2v 的 int8 不是 ComfyUI 的量化格式）、Lightning 4 步 LoRA 用模板的 fp32 版。PC 必需、Mac 可选（同 `w_img`）。`comfy/qwen-image` 的 `needs` 改成 `[comfy, w_img_t2i]`。

**本地 Python 运行时的安装**
- **`uv_sync` 步骤**：`uv sync --locked --no-dev --project <项目> --python <版本>`，`UV_PROJECT_ENVIRONMENT={envs}/<env>`（环境变量是唯一能把环境放到项目外的办法，所以 `Exec` 加了 `env` 参数）。项目是仓库里的 `runtimes/<name>/`（我们写的 pyproject + uv.lock）或模板路径（`{envs}/indextts-src`，先 git clone）。`--locked`：锁文件和 pyproject 对不上就报错，不悄悄重新解析。**锁文件里写的是 wheel 的完整地址，PyPI 镜像对它不起作用**；国内装得慢的话，以后另出一份指向镜像的锁。改了 pyproject 要 `uv lock --project runtimes/<name>`。
- **`rt_qwentts`**：qwen-tts 0.1.1、PyTorch / torchaudio 2.11.0 cu130（torchaudio 最高 2.11，配套用 2.11；cu130 的构建列表有 sm_120）、`librosa<1`；`exclude-dependencies = ["gradio"]`（只有它的演示命令用）。模型 VoiceDesign 1.7B（自带 12Hz 分词器）下到 `{models}/Qwen3-TTS-12Hz-1.7B-VoiceDesign`，worker 按文件夹加载：qwen-tts 锁死的 transformers 4.57.3 离线时按仓库名加载会去调 `model_info`（4.57.4 才修）。12Hz 用不到 SoX。只装 Windows、Linux x86_64，`requires_cuda`。
- **`rt_indextts`**：index-tts 锁 main 的 `d9e41aa`（2026-09-29，v2.5.0 之后的修正），按它自带的 `uv.lock` 装：Python 3.11（它要求 <3.12）、PyTorch 2.8 cu128；不装 extras（DeepSpeed、flash-attn 要编译）。worker 改了两处：`infer()` 的 `lang` 是必填（默认 `zh`）；`use_cuda_kernel=False`（默认会在启动时编译 BigVGAN 的 CUDA 内核，要装 CUDA 工具链和 MSVC）。`requires_cuda`。
- **IndexTTS 的辅助模型并进 `w_tts`**（5.5 → 8.3 GB）：w2v-bert-2.0（只要 config、preprocessor_config、model.safetensors，不要 2.3 GB 的 conformer_shaw.pt）、CAMPPlus、BigVGAN，放 `IndexTTS-2.5/hf_cache/`——index-tts 先找这里，找到就不联网（找不到时会先测 HF / ModelScope 再下）。放 `w_tts` 而不是 `rt_indextts`，是因为 `w_tts` 的检测会核对每个文件。
- **`rt_ocr`**：rapidocr 3.10.0 + onnxruntime 1.31.0（RapidOCR 不带推理引擎），只用 CPU；默认模型（PP-OCRv6）在 wheel 里，不用下。OCR 没有 API 兜底，所以 Mac 上也必需。Windows、Linux x86_64、Mac arm64（onnxruntime 没有 Intel Mac 的包）。
- **装完检查显卡**：`py_import` 检测加 `gpu: true`：除了能导入，还要环境里的 PyTorch 是 CUDA 版，并且它的内核覆盖这块显卡（`torch.cuda.get_device_capability()` 对应的 `sm_XY` 在 `get_arch_list()` 里，5090 是 sm_120）。不满足就是「需更新」（`env_no_cuda` / `env_gpu_arch`），提示重装没用、先走 API；安装后的复查也用它，所以装出一个用不了显卡的环境会显示安装失败（`not_detected`）。
- **测速用权重**：扫描测速取第一个下载文件的前 16 MB，现在先找权重组（`rt_qwentts` 的模型文件夹以小配置文件开头，测不出速度）。
- **`needs`**：`local/qwen3-tts` → `[rt_qwentts]`、`local/indextts2` → `[w_tts, rt_indextts]`（都加 `requires_cuda`）、`local/rapidocr` → `[rt_ocr]`。没装时能力过滤把试听切到 MiniMax、配音兜底去掉 IndexTTS、OCR 关掉。
- **IndexTTS 的协议**：代码和模型都是「bilibili 模型使用协议」（不是 Apache）：可以商用，免费、全球；上个月月活超过 1 亿或上一年收入超过 10 亿元要先拿书面授权；要保留版权声明、不能用它或它的输出去改进别的 AI 模型；适用中国法律、上海仲裁。我们只在本机调用、不分发它的代码和权重，满足条件。Qwen3-TTS、w2v-bert、BigVGAN、CAMPPlus 是 Apache-2.0 / MIT。

**界面**：Setup 页多了 4 行（运行环境 3 行、权重 1 行），原型里没有；PC 示例扫描「缺少」9 → 13，Mac「缺少」4 → 5、「可选」8 → 9、「跳过」8 → 10，默认勾选 2 → 5 项。没加新组件，没截新图。

## 2026-10-21 · MiniMax 用国内站，Seedream 按火山方舟人民币价

- **MiniMax 改用国内站**（Kelvin 定）：`minimax_llm` 的地址换成 `https://api.minimax.cn/v1`。国内站配音 3.50 元 / 万字符（约 $49 / 百万字符，国际站 $100），音色设计 9.90 元（约 $1.39，国际站 $3），设计试听 2.00 元 / 万字符。国内文档写明「1 个汉字算 2 个字符」，和估价的算法一致。国内、国际是两个账号，密钥不通用；换站时地址和人民币单价一起改。
- **价格直接写人民币**：两个配音模型 `currency: CNY`、`price_per_million: 350`，`extras` 写 9.90 元和 0.0002 元 / 字；记账时按 `currency_rates.CNY_per_USD`（7.1）折成美元。
- **音色终版不再需要确认**：设计 + 5 个变体约 $1.40，低于音色组件的单次上限 $3，直接跑（原来约 $3.0x，每次都要确认）。上限没改。
- **H3 视频的价格先不动**：国内站 768P 0.50 元 / 秒、2K 0.80 元 / 秒、再生成到 2K 0.30 元 / 秒（国内文档没写输入另收），比现在配置里的国际价便宜约 13%。H3 适配器 M4 才做，到时一起换，现在的国际价只会估高。`minimax/m3`（写作模型）的价格同样到用时再改。
- **Seedream 已经是国内的火山引擎**（`ark.cn-beijing.volces.com`；国际版是 BytePlus，另一个平台）。价格换成火山方舟官方价目表的 0.12 元 / 张（约 $0.017），输入图免费，审核没过没出图的不收；原来写的 $0.018 是 BytePlus 的美元价。
- 「台词配音」一句的估价从约 $0.0007 降到约 $0.0003；素材页「全部配音」的确认框截图 `assets-dub-confirm` 里的金额是旧的（约 $0.0014，现在约 $0.0006），下次重截时更新。

## 2026-10-21 · M3 第 12 步（上）：本地 Python 运行时、显存租约

第 12 步分两次提交：这次是本地 Python 运行时；安装（`uv_sync`、清单四项、`needs`）和 ComfyUI 适配器下次做。

- **一个模型一个常驻 worker**（`modelhub/adapters/local_python.py`）：`~/.drama-studio/envs/<env>/` 里的 Python 跑 `workers/<worker>.py`，第一次调用时启动、先发 `init` 加载模型，之后一直留着（模型常驻显存），直到显存租约让它走或者应用退出（`Registry.aclose()` 关掉 stdin，worker 自己退出）。
- **协议**（`workers/worker_protocol.py`，只用标准库）：一行一个 JSON，每个请求带 id，回复带同一个 id；文件写到适配器给的临时文件夹，读回内存后马上删掉。worker 启动时把 fd 1 转到 stderr，库（包括 C 代码）打印的东西都进 stderr，stdout 只有回复；stderr 最后几行在 worker 崩溃时进错误信息（`worker_crashed`）。
- **超时、取消就杀掉 worker**：路由的本地超时会取消这次调用，适配器随即杀掉 worker，下次调用重新启动，所以绝不会把上一个请求迟到的回复当成这次的。
- **环境变量**：`PYTHONUTF8=1`、`HF_HUB_OFFLINE=1`、`HF_HOME=<安装位置>/hf`（安装器先把要用的模型下好，运行时不联网），`PYTHONPATH` 指向应用的 `workers/`（worker 要导入协议文件）。
- **配置**：`providers.yaml` 的本地模型写 `worker`、`env`、`args`（`{models}` 是 Setup 页选的安装位置，`{envs}` 是环境目录）、`gpu`。`local/qwen3-tts`、`local/indextts2`、`local/rapidocr` 已经写上；环境由下一次提交的安装项建，没装时调用报 `not_installed`、照常兜底。
- **worker 文件名都带 `worker_` 前缀**：脚本所在目录在 `sys.path` 最前面，叫 `rapidocr.py` 的话 `import rapidocr` 会导入它自己。
- **三个 worker 按官方 README 写，第 13 步在本机第一次真跑**：Qwen3-TTS `Qwen3TTSModel.generate_voice_design(text, language, instruct)`；IndexTTS-2.5 `indextts.infer_v2_5.IndexTTS2(..., use_bf16=True, use_qwen_emo=True)`（用文字描述情绪必须开 `use_qwen_emo`），说话人用锚点、情绪优先用变体音频、没有就用文字；RapidOCR 3.x `RapidOCR()(path).txts`。不进 mypy（依赖只在各自环境里）。
- **显存租约**（`modelhub/vram.py`）：整个进程一把锁，不看任务在哪个队列。拿锁时如果上一个占显存的是别人，先让它放手（worker 退出；ComfyUI 下次提交接 `/free`），放手失败只记日志、继续。租约本身不设超时：等锁的时间算在路由的本地超时里，超时就兜底。RapidOCR（`gpu: false`）不拿锁。
- **测试**：`tests/fixtures/workers/worker_fake.py` 用真的协议文件，按台词模拟卡住、崩溃、出错；测试用基础解释器（`sys._base_executable`）起 worker，因为 Windows 上 venv 的 `python.exe` 是启动器，杀掉它后真正的解释器还会多活一会儿。

## 2026-10-21 · M3 第 11 步：MiniMax 适配器

按 platform.minimax.io（国际）和 platform.minimax.cn（国内）的文档核对（2026-10-21），`providers.yaml` 去掉 `verify`，测试全用 respx。

- **一个适配器两种调用**（`adapters/minimax.py`，`adapter: minimax_speech`）：`kind="tts"` 走 `POST /v1/t2a_v2`，`kind="voice_design"` 走 `POST /v1/voice_design`。模型 ID `speech-2.8-hd`、`speech-2.6-hd`（耳语只有 2.6 有，2.8 明确不支持 whisper；`fluent` 也只有 2.6）。
- **地址**：跟 `minimax_llm` 账号走。国际 `https://api.minimax.io/v1`，国内现在是 `https://api.minimax.cn/v1`（原来的 `minimaxi.com` 文档站已跳到 `minimax.cn`），国内国际是两个账号，密钥不通用；切国内改 `providers.yaml` 里账号的 `base_url`。两边接口一样，不用 GroupId。
- **请求**：不流式，`output_format: hex`，WAV 44.1 kHz 单声道（之后统一处理成 48 kHz、−18 LUFS）；`voice_setting` 只带 `voice_id`、`emotion`、`vol`（以及 `speed`、`pitch` 的默认值），组件给本地兜底准备的 `speaker`、`emotion_text` 这些不发；`language_boost: auto` 写在 `caps.request`。音色设计：描述做 `prompt`，台词做 `preview_text`（最多 500 字，多了截掉）。
- **出错**：MiniMax 出错也回 HTTP 200，看 `base_resp.status_code`。1000 / 1001 / 1002 / 1013 / 1039 / 1041 / 2045 重试；1004、2049 → `auth_failed`；1008 → `insufficient_balance`；1026、1027 → `content_blocked`；2042、2054 → `voice_not_found`；2056（5 小时额度用完）不重试。没有 `voice_id` 的音色（本地音色）调 API 直接 `voice_id_missing`。
- **计费**
  - 合成按返回的 `extra_info.usage_characters`（MiniMax 的计费字数）。估价时非 ASCII 字符（汉字、全角标点）都按 2 个算，宁可估高：确认过的任务每次调用前都检查「已花 + 这次估价 ≤ 确认金额」，真实字数比估价多一点，6 步的音色流程会在最后一步被拦下（见下面「等 Kelvin 定」）。
  - 音色设计 $3：官方写明「设计出的音色第一次合成时收，不是设计时」，合成的返回里有 `usage_voice_count`。所以实际花费按 `usage_voice_count` 记在那次合成上；估价仍按组件的 `charge_design`（第一个情绪变体）算进 $3。
  - 设计时的试听另收字数费：价格页写 $60 / 百万字，接口文档写 $30，按高的记（`extras.design_preview_char: 0.00006`，`Usage.calls` 计字数）。
- **测试连接**：MiniMax 没有免费检查模型 ID 的接口，用 `POST /v1/get_voice`（列出自己设计过的音色，不收费）确认密钥能用。
- **整套流程测试**：`test_asset_voice_api.py` 加了一条，Mock 试听之后切到真实适配器 + respx 假 MiniMax，出终版走 1 次设计 + 5 次合成（耳语在 2.6、喊叫 `vol: 2.0`），$3 记在 MiniMax 收费的那次合成上，总花费等于估价。
- **失败提示翻成人话**：`run_failed` 的 toast 原来直接显示错误码（「生成失败（auth_failed）」），现在按 `common:modelError.<code>` 翻译（「密钥不对或没有权限，去「模型与兜底」检查密钥」），没翻译的码照旧显示原文。
- **等 Kelvin 定**：确认过的任务真实花费超过确认金额时现在直接停（`budget_exceeded`），多步流程会停在半路、已经花的钱白花。要不要给确认金额留一点余量（比如 10% 或 $0.05，取大的）？没定之前不改，靠估价往高估。

## 2026-10-21 · M3 第 10 步：图像 API 适配器（三家）

三家都按官方文档核对过（2026-10-21），`providers.yaml` 去掉 `verify`，自动化测试全部用 respx，不触网、不花钱。真调用在第 14 步冒烟。

- **模型和接口**
  - Nano Banana Pro：`gemini-3-pro-image`（稳定版，不再是 `-preview`），走原生 `POST /v1beta/models/{id}:generateContent`，头 `x-goog-api-key`。账号还是 `google_llm`、同一个密钥，但地址另写（账号的是 OpenAI 兼容地址，出不了图）。官方文档现在的示例都换成了新的 Interactions API；`generateContent` 仍列在核心接口里，计划定的就是它，没换。
  - GPT Image 2：`gpt-image-2`（快照 `gpt-image-2-2026-04-21`）。没参考图走 `/images/generations`（JSON），有参考图走 `/images/edits`（multipart，每张一个 `image[]`）。不能传 `input_fidelity`（它总是高保真读参考图），`quality: high` 写在 `caps.request`。
  - Seedream 5.0：选 **5.0 flash**（`doubao-seedream-5-0-flash-260915`）。三档里最便宜（约 $0.018 / 张，pro 约 ¥0.3、lite 约 ¥0.22），1K–2K（92 万–462 万像素）正好覆盖草稿档和交付档；lite 最少 369 万像素，出草稿浪费。总是带 `watermark: false`（接口参考写默认 true，教程写默认 false，两处矛盾）和 `response_format: b64_json`（URL 要二次下载、24 小时过期）。
- **尺寸**：宽高还是从成片规格算（硬规则 10），每家换成自己支持的最近尺寸（`adapters/images.py:fit_size`），返回图按实际像素记 `w` / `h`。
  - Gemini：画幅原样传（成片规格的 5 种画幅它都支持），`imageSize` 取能盖住画面的最小档（草稿 1K，1080p / 2K 交付都是 2K）。模型按档出自己的像素，9:16 2K 是 1536×2752。
  - GPT Image 2：官方允许任意 `宽x高`（两边 16 的倍数、最长边 ≤ 3840、长短边比 ≤ 3:1、65.5 万–829 万像素），所以直接按画面尺寸向上取 16：1080×1920 → 1088×1920。**和计划不同**：计划写「9:16 用 1152x2048」，那是按第三方渠道的固定尺寸写的。
  - Seedream：`宽x高` 向上取 16，再缩放进像素范围（1:1 草稿 768×768 → 960×960）。
- **n 张**：GPT Image 2 一次请求出 n 张；Gemini 和 Seedream 一次只出一张，n 张就同时发 n 个请求（`one_per_request`），Gemini 的种子用 `seed + i`。部分失败时，出来的几张照实记张数和花费，`raw.failed` 记失败的错误码；全部失败才报错。
- **按 token 计费的照 token 记账**：Gemini 和 GPT Image 2 都按 token 收费（Gemini 的思考按文本输出另算，GPT Image 2 的价格随尺寸、质量、参考图变）。`Pricing` 加 `token_rates`（每百万 token，按 `text_in` / `image_in` / `text_out` / `image_out`），`Usage` 加 `tokens`；返回了分项用量就按 token 算实际花费，没返回（或出现没有单价的种类）就按每张价格算。每张价格只用来估价：
  - Gemini $0.134 / 张（1K、2K 都是 1120 个输出 token；4K $0.24，我们最高用 2K）。
  - GPT Image 2 按尺寸估：每百万像素约 3600 个输出 token（high；1024×1536 high 约 $0.165，来自第三方实测，官方只有交互式计算器），每张参考图估 2000 个输入 token。1080p 竖屏约 $0.23 / 张，2K 约 $0.40。
  - Seedream $0.018 / 张，按 `usage.generated_images` 计数。这是 BytePlus 的美元价；火山引擎的人民币价页面是脚本渲染的，没读到，第 14 步冒烟时看账单核对。
- **兼容表跟着变（和原型不同）**：
  - 「带字关键帧 · GPT Image 2」从「转换：部分接入渠道只到 1K，本地超分」变成「原生」（`max_short_edge: 1024` 删掉）。我们直连 OpenAI，官方能直接出交付尺寸。
  - 21:9 下「关键帧 · Nano Banana Pro」从「不支持：先出 16:9 再外扩」变成「原生」，官方画幅列表里有 21:9。
  - 原型里这两行是按第三方渠道的限制画的；规格页布局和文案不变，只是这两行的状态按真实能力显示。
- **出错**：内容审核拦下统一成 `content_blocked`（OpenAI `moderation_blocked`，Gemini `blockReason` / `finishReason` 是安全类，方舟 `*SensitiveContentDetected`），不重试；只回了文字没出图是 `no_image`。429、5xx、超时按退避重试 2 次（`adapters/http.py`，`openai_compat.py` 也改用它）。
- **测试连接**：`POST /providers/{id}/test` 除了 `GET /models`，再逐个检查用这个账号密钥的出图模型（结果在 `media` 里），只发不花钱的请求：Gemini、OpenAI 查 `GET /models/{id}`；方舟没有文档写明的免费列表接口，发一个它一定拒绝的请求（空提示词、1×1），回 400 就说明密钥和模型 ID 都对。`GET /providers` 每家带 `media`，密钥弹窗写「这个密钥也用于：Nano Banana Pro」。
- **加适配器 = 填配置**：媒体模型在 `providers.yaml` 写 `adapter`（`gemini_image` / `openai_images` / `seedream`），`modelhub/media_adapters.py` 按它挑类；没写 `adapter` 的媒体模型还是「暂不可用」。

## 2026-10-21 · Kelvin 看过第 7、8 步：素材计数、候选卡太大

- **「素材」按本集用到的素材算（7 / 10）**：Kelvin 定，不改回原型按整张清单算的 7 / 13。第 8 步（后端）那条的「等 Kelvin 定」到此结束。
- **候选卡、补视图卡改成定宽的小卡**：Kelvin 在宽屏（约 2000 px）上看，原来 4 列网格按详情栏宽度等分，一张 9:16 的图被拉到约 290 × 515 px，比例不协调。
  - 现在卡片宽度固定，按画幅定（`pages/assets/status.ts:CARD_WIDTH`：9:16 是 148 px，16:9 是 252 px），放不下就换行，不随屏幕变大。
  - 看细节用放大：候选图右下角「放大」按钮，补视图整张卡可点，打开 `components/MediaLightbox.tsx`。图按屏幕大小完整显示（最高 80% 视口高），← → 或按钮切换同一组的其他张。
  - 放大不等于选中，选中还是点卡片。「放大」按钮放在卡片旁边、叠在图上，不放进卡片里：候选卡是单选按钮，单选按钮里的控件读屏读不到。
- **配音听起来是噪音**：Mock 适配器只生成一段合成测试音，用来走通流程、算时长和波形，不调用真实 TTS。真声音要等第 11 步（MiniMax 适配器）和第 13 步（本机真装真跑 IndexTTS / Qwen3-TTS）。

## 2026-10-21 · M3 第 8 步（前端）：素材闸门、改已锁定素材

- **素材闸门和「素材」进度改走后端**：MSW 不再叠加第 1 集「素材」这一步的计数，也不再接管 `gates/assets`。素材页、左侧导航都显示「已锁定 7 / 10」，原型是 7 / 13，见第 8 步（后端）那条，等 Kelvin 定。
  - 没锁完时点「去做分镜」，toast「还有 3 条素材没锁定：林晚出租屋 · 夜、旧黑发圈、便利贴手写」，不跳页。
- **改已锁定的素材**：描述、画面文字的字 / 做法 / 字体、音色来源，先预览 `asset_edit`，弹影响范围（`ImpactDialog` 弹窗）。
  - 「撤销」或关掉弹窗：输入框恢复原值。
  - 没锁定的照旧直接保存。
  - 弹窗标题「「林晚」已锁定，改动会影响下游」，下面一行「新描述：……」。
- **影响行的价格用 `formatCost`**：几分钱以下保留有效数字，一句配音写「约 $0.0005」，不是「$0.00」。免费的（本地草稿重出候选）不写价格，和其他免费行一样。
- **示例剧集的影响预览**：「三年了。他凭什么。」那一行叠加的 `dub_lines`（「配音 · 1 条」）删掉。配过音时后端自己给「台词配音 · 1 句按新台词重配」，没配过就没有这一行。
- `useApplyImpact` 之后也刷新配音（`["dub"]`）：改台词、换音色后，配音状态马上变「待更新」。
- 测试假后端：第 1 集的「素材」进度按假素材的锁定现算；`gates/assets` 要求用到的素材都锁定；`asset_edit` 的预览和应用。

## 2026-10-21 · M3 第 8 步（后端）：素材闸门、影响范围、级联

第 8 步也分两次提交：这次是后端，前端（「去做分镜」接后端、改已锁定素材的描述走影响范围、新的影响行文案、进度换成后端的）下次做。

**整集素材闸门**（`gate: assets`，`scope_id` 是集 id；每条素材自己的闸门 `scope_id` 是素材 id，第 3 步就有）
- 管的是这一集用到的素材（`asset_use` 里有、没退场的），由 `AssetService.episode_assets` 列出：`GateService.members(gate, fn)` 让闸门的「哪些产物」可插拔。
- 确认要求它们都已锁定，否则 409 `assets_not_locked`（`count`、`names`），确认时记下各自的哈希。确认不锁任何东西，重新打开也不解锁：素材是整部剧的，各自单独锁定。
- 解锁一条素材时，用到它、已确认的集一起重新打开（`GateService.reopen_using`）。

**进度里的「素材」**（`EpisodeService.counters`，由 `AssetService.badge` 算）
- 已锁定数 / 本集用到的素材数。示例第 1 集是 **7 / 10**：清单里 13 条，有 3 条本集没出场（周屿、周屿的音色、楼下便利店）。原型写「7 / 13」，算的是整张清单；这里按闸门要锁的算，等 Kelvin 看要不要改回整张清单。
- 「待更新」= 用到的素材里过期的 + 本集台词配音里过期的。
- 状态：闸门确认了是「已确认」；有素材是「进行中」；还没分析是「未开始」。

**级联的停止集**
- 候选类组件（`auto_adopt` 关着的：参考图、画面文字、音色）的产物，级联永远不重跑。原因：级联会采纳重跑的结果，会解锁原来锁定的、采纳一版没人选过的候选。所以改剧本不会重画、也不会解锁参考图；补视图和配音照常跟着走。
- 按组件判断，没有按槽位列名单：以后再加候选类组件不用改级联。

**影响范围**
- 影响行按槽位（和集）合并成一行，花费相加：60 句配音是一行「配音 · 60 句」。合并了的行和「做一打」的槽位（配音）的行带 `count`。
- `line_audio` 进流水线顺序（排在补视图后面），「待更新」算在「素材」那一步。
- `line_edit` 带配音：改的这一句如果配过音，图上直接有「`stale_line_audio`，`count: 1`」，「确认并同步」只重配这一句。
- 新的改动类型 `asset_edit`：改**已锁定**素材的描述、画面文字设置或音色来源（`pick` 不行，422；没锁定的直接 `PATCH`，这里 409 `not_locked`）。
  - 影响行：`asset_redraw`（这条素材按新描述重新出候选，带这次重跑的估价）；`uses_*`（锁定新的之后跟着变的：补视图、拿它做参考的素材、用这个音色的配音）；`asset_in_scenes`（出现在哪几场，只提示）。`unaffected` 是 `edit_keeps_ref`。
  - 「只改这里」：只存新描述。锁定的仍是原来那张，哈希不变，下游都不过期。
  - 「确认并同步」：存新描述，再让这条素材自己重跑，出新候选给你选（`PlannedChange.rerun`）。锁定不动，选好新的再锁定，下游才更新。预计花费把规划器给的行算进去了。
- 解锁音色的影响行，配音那一行改成 `uses_line_audio {name, count}`：之前 `names` 填的是台词 id。

**查过的现象**：Playwright 全量跑时，M2 的「改已确认的小说 → 确认并同步」之后第 1 集有一句台词的音色没锁定。原因是 Mock 把改过的小说重新剧本化时，说话人切成了「了一」，于是新建了这个角色和它的音色。不是音色匹配的问题，原有素材的锁定都还在（`test_a_script_sync_never_redraws_nor_unlocks_an_asset`）。

## 2026-10-21 · M3 第 7 步（前端）：台词配音的界面

**事件收窄**
- `product.updated` 和 `version.created` 都带上 `slot`。前端 `api/events.ts` 遇到 `slot: line_audio` 只让配音的查询（`["dub"]`，`api/hooks/dub.ts`）失效，不刷全部产物、分集和剧本。
- 配音的 key 不放在 `["episodes", …]` 下面：否则别的产物一变，配音也跟着重拉。
- 「做一打」的槽位（`ProductService.quiet_slots`，现在只有配音）出新版本时不发「已生成 vN」的 toast。原因：一次「全部配音」几十句会弹几十个；改成点「开始配音」时一个 toast「已开始配 n 句」。

**接口补充**
- `POST /episodes/{id}/dub` 加 `line_ids`：给的这几句不管状态都重配（「配音 / 重配」用）。音色没锁定的照样跳过；不认识的行 404 `line_not_found`。
- 正在配的行现在也写进 `skipped`（`product_busy`），和第 7 步后端那条「跳过的行写明原因（正在配）」一致；之前只有排任务时撞上的才写。
- 每句多一个 `tone_emotion`：按语气算出的情绪，手动改过也给。情绪下拉框第一项「按语气（耳语）」要用它。

**界面**（配音没有原型，照现有样式加）
- 素材页进度卡多一行「台词配音 n / m」+ 进度条 +「全部配音」。两行共用一个网格，列对齐、不换行。
  - 点「全部配音」先 `dry_run`，弹窗写句数、估价、跳过的句数和音色名，确认后才排任务。
  - 没有能配的句子时按钮灰掉；都配好了时提示「这一集的台词都配好了」；有句子在等音色时，同一行写「林晚 的音色还没锁定，2 句先等着」。
- 音色详情最下面「第 N 集的台词配音」：这个音色在本集的每句台词，各有状态、情绪下拉框（按语气 + 五种情绪）、播放（带波形和时长）、「配音 / 重配」。
  - 音色没锁定时写「先锁定「林晚」的音色」，按钮灰掉。
  - 改情绪不会让已有的配音变「待更新」（第 7 步后端：情绪从下一条起用），提示「改完点「重配」才用上」。
- 剧本页：配过音的台词行右边有播放按钮和真实时长，表格的「时长」列也是。没配的仍显示剧本的估计。
  - 场标题下面多一行「台词 x 秒 · 已配音 n / m」：只算有说话人的行（`timing.py`），动作行的时长 M4 由镜头决定，所以不叫「本场时长」。
- `AudioPlayer` 加 `compact`：只有按钮和时长，给剧本行用。

**测试**
- `web/src/test/data/dub.json`（`tests/api/test_web_fixtures.py` 导出）：全部配音前、估价、配完后。配音产物在第一次配时才建，id 是随机的，导出时换成 `dub-<行 id>`；Mock 音频随种子变，文件哈希按行固定。
- 假后端 `test/fakes/dub.ts`：音色锁没锁读 `test/fakes/assets.ts` 的产物，所以解锁音色后台词跟着变「音色未锁定」。
- Playwright 新加 `seeded` 项目，`smoke` 依赖它，所以它最先跑：要用示例原样的测试放这里（`e2e/seeded.spec.ts`，配音这条）。原因：M2 的流程测试会用 Mock 输出重新剧本化第 1 集，之后台词和素材都变了。
  - 副作用：`real` 项目现在也排在 `smoke` 前面。M2 的一条测试按 `/周屿？/` 找剧本行，配过音后会同时匹配到播放按钮「播放：……周屿？」，改成按说话人后面的 `）：……周屿？` 找。

## 2026-10-21 · M3 第 7 步（后端）：台词配音和时长

第 7 步分两次提交：这次是后端，前端（素材页、剧本页）下次做。

**产物**
- 每句有说话人的对白 / 旁白一个产物：slot `line_audio`，owner `line:<行 id>`，组件 `dub`。
- 产物在第一次配这一句时才建（`assets/dub.py`），不在剧本物化时建。原因：没配过音的行没有版本，建了也不会过期，只会让产物列表多出几十行。
- 剧本重跑后退场的行，它的配音产物标 `retired`；这一行回来时取消。`retired` 的产物永远不算待更新（`Invalidation.stale_ids` 跳过它们）。
- **每次运行都采纳**（`adopt_every_run`）：配音跟着台词和音色走，用户点「重配」就是要新的这一条；旧的留在历史里。

**依赖**
- 剧本的新切片 `line:<id>`：这一行的类型、说话人、语气、文字。改这一句，只有这一句的配音变「待更新」。
- 说话人音色的锁定哈希。换锁定的音色，这个角色的配音全部变「待更新」。
- 说话人的音色要先锁定，否则 409 `voice_not_locked`（带音色名）；找不到音色是 409 `no_voice`。
- 「这一句是谁的音色」：音色素材的出场里有这一行的那条；没有就按设定 id 找这个角色的音色。

**情绪**
- 手动设的（产物设置 `emotion`，`PATCH /lines/{id}/dub`，设成 null 就回到按语气）优先。
- 否则按语气里的关键词（`config/voice.yaml` 的 `tones`，从上往下第一个对上的）：例如「低声，愣住」是耳语。
- 都没有就是平静。

**调用**
- API 音色（有 `voice_id`）走 T2A，带情绪参数；耳语换 2.6 HD，和出音色变体用同一份 `emotion.minimax` 配置。
- 本地音色（没有 `voice_id`）走 `local_final`（IndexTTS）。
- 一次请求里同时带上 `voice_id` 和本地要用的说话人样音、情绪参考（文件路径），所以 API 失败时路由器能直接兜底到本地 IndexTTS（`components.yaml` 里配音的兜底从 ElevenLabs 改成 `local/indextts2`）。
- 每段配音都过统一响度。

**接口**
- `GET /episodes/{id}/dub`：本集每句台词（按场、行排序）的说话人、音色、状态（done / stale / missing / running / failed / no_voice / voice_not_locked）、情绪、音频（采纳版本的文件，带波形）、时长；每场的时长和已配句数。
- `POST /episodes/{id}/dub`：`dry_run: true` 只给总估价和句数；否则给每句还没有最新音频、音色已锁定的台词各排一个 `product.run`。跳过的行写明原因（音色没锁定、找不到音色、正在配）。
- `PATCH /lines/{id}/dub`：手动设情绪。
- 配音产物在产物列表里不算下一次运行的估价（`ProductService.quiet_slots`），几十句一起列出时不会每句都估一次。
- `dub` 组件加了一份最短的提示词模板：没有模板时 `describe` 不给估价，「全部配音」的总估价会是 0。

**时长**（`pipeline/timing.py`）
- 一句：配过音就是音频长度；没配就用剧本的估计；剧本也没估就按每秒 4 个字。
- 一场：它的台词一句接一句相加。只算有说话人的行；动作行的时长 M4 由镜头决定。
- 一个镜头（M4 用）：几句音频相加，前面加 0.3 秒、后面加 0.2 秒；超过单段上限时建议拆。

## 2026-10-21 · M3 第 6 步：音色

**流程**（组件 `voice`，`config/voice.yaml`，改配置不用改代码）
- 「重跑」= 免费试听（`stage: draft`）：3 个，描述后面分别加「偏低沉 / 更清亮 / 带一点沙哑」。
  - 本地（Qwen3-TTS）每个试听逐句读这个角色的前两句台词，一句一个文件（`role: candidate`，`idx` 是第几个试听，`line` 是第几句）。
  - 角色在剧本里还没有台词（周屿）时读 `sample_text`。
  - 路由是 API 时（这台电脑没有本地 TTS），一个试听是一次 MiniMax 音色设计：一段试听读完几句，`voice_id` 记在候选上。
- 「用 MiniMax 出终版」（`where: api` + 选中的试听，`stage: final`）：音色设计拿到 `voice_id`（试听本来就是 API 设计的就直接用），再用 T2A 让这个角色的第一句台词按 5 种情绪各读一遍：平静、愤怒、哭腔、耳语、喊叫。
  - 耳语用 `minimax/speech-2.6-hd`（`providers.yaml` 新加，只用于耳语，`verify: true`）；喊叫是 angry + 音量 2.0。这些参数第 11 步按官方文档核对。
- 「本地」来源：选中的试听就是锚点，5 个变体由 `local/indextts2` 按情绪文字出，全程免费。
- 终版的文件：锚点（`role: anchor`）+ 每种情绪一个（`role: variant`，带 `emotion`）；payload `{provider, voice_id, emotions, label}`。
- **只有终版能锁定，而且整版锁定**（没有 pick 版本）。锁定试听返回 409 `voice_needs_final`，界面上锁定按钮灰掉，提示「先出终版」。
- 声音克隆这一项灰掉，写「之后支持」；真去跑会失败（`voice_clone_not_supported`）。

**花费**
- **音色设计的 $3 记在第一次用这个音色合成的那次调用上**（请求带 `charge_design`，按 `extras.voice_design` 计），不记在设计那一次上。和计划写的不同，原因：MiniMax 在第一次合成时才收这 $3；没有本地 TTS 时 3 个试听都是 API 设计，如果设计时就记，会算成 $9，而实际只收选中的那一个。出终版时设计和第一次合成在同一个版本里，版本花费不受影响。
- 估价 = 设计 + 5 个变体的字数费 + $3，超过音色的单次上限 $3，所以「出终版」一定先进「等你确认」。
- 示例里林晚的终版记 $3.004（$3 + 40 个字）。

**兜底和缓存**
- 终版里的每次调用都是 `fallback=False`；任何一步失败，整套改用本地 IndexTTS 重做（`run_flow`），所以一个音色不会混用两家。`components.yaml` 里音色的兜底从 ElevenLabs（没有密钥）改成 `local/indextts2`。
- 试听的调用也不兜底：IndexTTS 不能按文字描述设计音色，失败就让这次运行失败，用户可以换一个模型。
- 媒体调用缓存现在也存调用返回的 JSON（音色设计的 `voice_id`），任务重试或重启续跑时不会重新设计、也不会再收钱。

**响度**
- 每段音频进版本前都过 `media/audio.py` 统一响度（−18 LUFS）。
- 测试默认设 `DRAMA_FAST_AUDIO=1` 跳过 FFmpeg，只量时长和波形；有一个测试关掉它，确认响度在 ±0.5 LU 以内。

**接口和前端**
- 版本文件多三个字段：`line`（读的是第几句）、`emotion`、`waveform`（64 段，后端算好）。
- 素材页的音色改用真音频（`AudioPlayer`）：
  - 试听一行一个，可以播放、选中；
  - 终版显示「终版 · 偏低沉 · API 音色设计」、样音和「情绪变体」五个；
  - 「用剧本里的台词试读」播放选中试听读这一句的那段，终版播放样音。
- 「出终版」按钮在试听的说明右边：本地来源写「用本地出终版（免费）」，否则写「用 {模型名} 出终版」。不在按钮上写价格：前端拿不到 $3 这笔附加费，点了以后「等你确认」会显示准确的估价。
- 示例种子：林晚的音色改成 v1 本地试听（3 个 × 2 句）、v2 MiniMax 终版（从 A 出），整版锁定。
- 出场矩阵的列顺序改成按分析里的顺序（第 5 步后的 CI 修复，68c9cdc）：同一次物化建的行 `created_at` 可能相同，Windows 和 Linux 排出来不一样。

## 2026-10-21 · M3 第 5 步：画面文字和 OCR

**OCR（新组件 `ocr`，`qa/ocr.py`）**
- 只有本地模型 `local/rapidocr`（`providers.yaml` 新加，kind `ocr`，免费），不做 API 兜底。「模型与兜底」页因此多一行「文字核对（OCR）」，原型没有这一行（和补视图一样）。
- 走 `router.call()`：每张候选一次调用，写 `model_call`（$0），记在画面文字的产物和任务下，`component_id` 是 `ocr`。
- 请求带图片的 sha 和本地路径（`params.path`），第 12 步的 RapidOCR worker 也按路径读图。
- `local/rapidocr` 先不写 `needs`：清单里还没有 `rt_ocr`（第 12 步加），而没写 `needs` 的模型视为能跑。
- 没有 OCR 时（组件不跑、模型报错），候选标「未检查」（`ocr_ok: null`）：不拦锁定，也不让这次出图失败。
- **比对**：两边都做 NFKC、去掉所有空白，再逐字比，标点也算。NFKC 会把全角数字、冒号、逗号换成半角，所以「２３：５２」和「23:52」算一致。
- 不一致的原因有三种：
  - `missing`：只是少了字或标点；
  - `wrong`：有字读成了别的，或者多出了字；
  - `has_text`：后期贴字的底图上读出了字。
- 前端只显示后端给的结果，不再自己比。
- Mock：Mock 出图把要画的字写进 PNG 的 `iTXt`（第 1 步），Mock OCR 读回来。`MockSettings.ocr_mismatch` 让 OCR 少读最后一个字，用来测不一致。

**画面文字（组件 `text`）**
- 继承参考图的 `img`：4 张候选、混合模式（本地草稿 + API 终版）、不自动采纳。`components.yaml` 补了 `candidates: 4`，之前漏了，只会出 1 张。
- 两种做法：
  - 模型直接出字：提示词里有「[文字，必须逐字一致]」和字体说明，请求带 `params.text`（Mock 照着画；真实模型从提示词读，第 10 步的适配器不发这个参数）。
  - 后期贴字：提示词要求画面里没有任何字，并留出放字的位置；OCR 确认底图上没字。
- 版本 payload 多两样：每张候选的 `ocr`、`ocr_ok`、`ocr_issue`，以及出图时用的设置 `text {exact, method, style}`。锁定出的 pick 版本带着这张的 OCR 结果，所以锁定哈希里也有它。
- 改了字或做法之后，屏幕上这一版仍按出图时的设置显示 OCR，并提示「这一版是按「模型直接出字」出的……点「重跑」按现在的设置出」。
- 提示词模板 `text/default.j2` 写全（照原型的 compile）。

**锁定**
- 选中的候选 OCR 不一致（`ocr_ok: false`）时，`POST /assets/{id}/lock` 返回 409 `ocr_mismatch`，参数是读到的字、要求的字和原因；body 带 `force: true` 才锁定。未检查的照常锁定。
- 前端收到 `ocr_mismatch` 弹确认框（「候选 B 的字和要求不一致」，写出读到的和要求的）：「仍然锁定」带 `force` 重发，「取消」不锁。

**上传**：给画面文字上传的图也过 OCR，按上传时的设置比对。第 3 步上传的图没有过 OCR。

**前端**
- 画面文字的候选改成显示真图。以前是按字体风格画的色块，现在只在版本没有图片文件时才用。
- 后期贴字的底图上，按当前的字和字体风格叠一层字，预览贴字后的样子；真正的合成在 M7。
- OCR 那一行有六种：一致、底图没有字、有错字、缺字或缺标点、底图上读到了字、未检查。

**示例**
- 便利贴手写（txt1，模型出字）照原型：B 把「点」读成「占」，D 少了句号。
- 手机锁屏时间（txt2，后期贴字）的四张改成空白底图，OCR 一致。以前示例里贴字的四张也画了字。

## 2026-10-21 · M3 第 4 步：素材页接后端、出场矩阵

原型里没有出场矩阵、「用 API 出终版」和上传，下面是照现有页面的样式定的，截图给 Kelvin 看（`reports/ui/`）。

- **候选显示真图**：版本 `files[]` 里 `idx` 对得上的那张（`/api/v1/files/{sha}`），角上仍标 A–D。
- **「用 API 出终版 · 约 $0.14」**（候选标题右边）：
  - 只在三个条件同时满足时出现：路由是混合模式、屏幕上是本地草稿（`stage: draft`）、素材没锁定；
  - 价格是路由里 API 模型一张图的标价；
  - 点了以后用选中的那张当参考出 1 张，成为新的当前版本。终版不是草稿，所以不会再出现这个按钮；想从别的草稿出终版，先在历史里把那一版设为当前。
- **上传参考图**：详情标题行、锁定按钮左边，接受 PNG / JPEG / WebP。锁定时不能用；音色没有这个按钮。
- **「出现在」改成场**：
  - 按全剧场号显示「场 1 场 2」，链到剧本页这一场里它的第一行（`?line=`）；
  - 示例剧集后面仍跟着 MSW 叠加的镜头（M4 换成真的）；
  - 清单第二行写「2 场 · 6 个镜头」「出现在 N 场」或「本集未出现」。
- **补视图**：角色详情最下面，三张（侧面、背面、表情）。正在补时写「正在按锁定的图补齐……」，锁定的图换了写「正在等重画」。
- **「清单 / 出场矩阵」切换**：在素材网格上方。
  - 矩阵占满宽度，详情在下面。
  - 一行一场；一列一样素材，照清单的顺序：角色、场景、道具、画面文字、音色。计划写的是「列是角色和场景」，但道具、画面文字和音色也按行出现，一起列出来更有用。
  - 格子里的数字是这一场里有它的行数，整场出现的写「整场」，点击跳到剧本那一行。
  - 点列头选中这样素材。
  - 同名的角色和音色（林晚）靠格子的读屏名区分：「角色「林晚」在场 1：2 行」。
- **「重新分析剧本」改成任务**：提示「已开始」，版本出来后 `product.updated` 刷新清单。MSW 的 analyze 删掉了，示例剧集也走后端的 Mock 分析。
- `useAssets(series, episode)`：每集一个缓存，`scenes` 和来源是这一集的；改动返回的素材写回所有集的缓存，只保留各自的 `scenes`。
- **历史里的 pick 版本照常列出**（「锁定的候选」）。它的来源版本也显示「已锁定」（第 3 步的 `versionStatus`），因为屏幕上是来源那一版。
- Playwright 的无示例数据一轮加上素材页：真图确实加载出来（`naturalWidth > 0`）、矩阵、锁定再解锁。

## 2026-10-21 · M3 第 3 步：参考图、补视图、上传、锁定

**参考图（组件 `img`）**
- 一次运行出 4 张候选，不自动采纳。
- 尺寸只从成片规格来：本地草稿用草稿档（9:16 是 768×1366），API 用交付档（1080×1920）。
- 「用 API 出终版」= `where: api` + `params.source_version_id / source_idx`：
  - 以那张草稿为参考出 **1 张**（Kelvin 定的第 5 项，约 $0.14），`stage: final`，父版本是草稿；
  - 上传的图也能当来源。
- 本地默认模型改成 `comfy/qwen-image`（2512，文生图）；2511（`qwen-image-edit`）只能编辑，留给补视图。
- **「参考素材只用已锁定的」的具体做法**：
  - 道具的描述里提到的角色，如果已锁定，就拿它的锁定图做参考，并依赖它。所以给角色锁定另一张图，这个道具会变「待更新」。例：旧黑发圈「戴在林晚左手腕上」。
  - 场景画空景，不带人；角色本身不带参考。
- 素材产物第一次运行的意图就是素材的描述：新增 `Component.default_intent`，以前是空的。

**补视图（新组件 `views`）**
- 角色锁定后自动跑：以锁定图为参考，出侧面、背面、表情各一张。
- **每次都采纳**（`adopt_every_run`）：视图跟着锁定图走，不用挑。
- 依赖锁定图的哈希。重新锁定同一张图时，视图不过期，就不重跑。
- 三张都用 `fallback=False`；任一张失败，就整套换到兜底模型重出，所以一套视图不会混用两个模型。
- `components.yaml` 加一行：本地默认 `comfy/qwen-image-edit`，API 兜底 Nano Banana Pro，单次上限 $1。「模型与兜底」页因此多一行「补视图」，和「台词配音」一样，原型里没有这一行。

**媒体调用缓存**
- 每次出图（以后还有配音）的结果文件，按请求记在 `llm_cache` 里（key 前缀 `media:`）。任务重试或重启续跑时，已经出过的不再花钱。

**锁定 `POST /assets/{id}/lock`**
- 默认锁定屏幕上那一版里选中的候选；body 可以指定 `version_id`、`idx`。
- 走 `lock_pick`，在同一个事务里写这条素材自己的 `gate_decision`：gate `assets`，scope 是素材 id，哈希是 pick 版本的媒体切片，也就是这张图本身。
- 素材的 `pick` 只在它指向屏幕上那一版时才返回，换了一版就从 0 算。
- 解锁写 `reopen`。整集的素材闸门（scope 是集 id）在第 8 步做。

**上传 `POST /assets/{id}/upload`**
- 接受 PNG、JPEG、WebP，不超过 20 MB。宽高从文件头读（`media/image.py`），不引入 Pillow。
- 上传后出一个 `origin: upload` 的版本，里面只有这一张候选，并且自动选中。
- 只有参考图和画面文字能上传；音色返回 422 `upload_not_supported`。

**解锁 = 影响范围 `asset_unlock`**
- 解锁不改内容，比哈希找不出受影响的东西，所以由 planner 直接从依赖图列行。为此 `PlannedChange` 加了三个字段：`lines`、`unaffected`、`relock=False`（应用后不再锁回去）。
- 列出的行：
  - `uses_ref_views`：这个角色的补视图；
  - `uses_ref_image`：用它做参考的道具。
- `unaffected` 是 `unlock_keeps_ref`：解锁后原图照常在用，锁定新的一张后，用到它的才更新。
- 示例剧集的镜头行仍由 MSW 叠加，M4 删。
- `PIPELINE_ORDER` 加上 `ref_image` / `text_image` / `voice`（6）和 `ref_views`（7），都算在导航的「素材」那一步。

**接口和示例**
- 版本文件加 `idx`、`view` 两个字段（前端契约同步）。
- 示例种子：照原型补上候选版本，文件用 Mock 现生成，7 / 13 已锁定，每条都有闸门记录；林晚补好了视图。
  - 林晚 v1 是本地草稿（Qwen-Image），v2 是 API 终版，只有 1 张：原型写的 4 张 $0.56 是 Kelvin 定第 5 项之前的。
  - 锁定出的 pick 版本是 v3。
- 顺手修了第 2 步的漏洞：`drama-studio demo` 没注册素材清单的物化，命令行建的示例没有素材行。
- 前端：版本状态把「pick 的来源版本」也算作已采纳 / 已锁定（`lib/versions.ts:versionStatus`）。否则锁定后，运行条上的当前版本会显示「草稿」。

**MSW**
- 素材列表、改动、锁定、产物都改走后端，删掉 MSW 里素材的产物、锁定和解锁。
- 示例剧集只叠加「出现在」的镜头，以及解锁预览里的镜头和关键帧行（`mocks/handlers/assets.ts`）。
- 进度里「素材 7/13」改读后端列表。
- 「重新分析剧本」对示例剧集仍由 MSW 回答：前端第 4 步才改成跟任务。
- 页面测试用新的假后端 `test/fakes/assets.ts`，数据由 `tests/api/test_web_fixtures.py` 导出到 `test/data/assets.json`。

## 2026-10-21 · 启动脚本默认真实检测（Kelvin 定）

- `start.ps1` 加 `-RealSetup` 开关，**默认开**：`DRAMA_SETUP=real`，Setup 页扫描、安装这台电脑，模型调用仍走 Mock、不花钱。`-RealSetup:$false` 换回原型的示例机器。没传开关、但已经设了 `$env:DRAMA_SETUP` 时，以环境变量为准。`start.sh` 同样默认真实，`--no-real-setup` 换回示例机器。启动横幅多一行「Setup: this computer / sample machines」。
- 原因：Kelvin 用 `start.ps1` 起的工作台在 Mock 下一直显示示例机器，去 Setup 页装 Qwen-Image-Edit 时才发现不是本机。M3 第 13 步还要真装 TTS、OCR。
- 只改启动脚本：直接 `drama-studio dev`、测试和 Playwright 仍按原规则（Mock 模式即示例机器）。

## 2026-10-20 · M3 第 2 步：素材分析（后端）

**清单从哪来**
- 每集一个 `asset_list` 产物（组件 `assets`），素材本身属于整部剧。
- 剧本和设定按规则给出大部分素材（`assets/ops.py:collect`）：
  - 每行台词上的人物；
  - 说话人（对白、旁白）各一条音色；
  - 每个「地点 + 时段」一个场景；
  - 台词文字里提到的设定道具，按在行内出现的先后排。
- 出场矩阵也由这些规则算出，不依赖模型。
- 模型只做三件事：
  - 给已知素材写描述，可以改个更好认的名字；
  - 找设定里没有的道具和画面文字（逐字内容、字体风格、贴字方式）；
  - 列出马上要出场的角色、场景或音色，`lines` 留空，写一句 `note`。
- 示例里的 周屿、他的音色、楼下便利店 就是这样来的，和原型的 13 条对上。

**id 沿用**
- 按 key 沿用：`character:<设定 id>`、`voice:<设定 id>`、`scene:<地点 id>:<时段>`、`prop:<设定 id>`、`text:name:<名字>`。key 对不上时，按「类别 + 名字」沿用。
- 沿用范围包括本集已采纳的清单和其他集的清单，所以同一个人在不同集是同一条素材。
- 示例种子用原型的 id（`linwan`、`hall` …，`studio/demo.py:DEMO_ASSET_IDS`）。素材产物的 id 是 `demo-p-asset-<id>`，和 MSW 一致。

**物化只增不删**
- 采纳一集的清单时：upsert 素材，替换这一集的 `asset_use`，不会让别的集用到的素材退场。
- 新素材顺手建好它的产物：角色、场景、道具是 `ref_image` / `img`，画面文字是 `text_image` / `text`，音色是 `voice` / `voice`。

**用户改的东西都在素材的产物上**
- 描述 = 提示词的意图层（`PATCH /assets/{id}` 的 `intent` 走 `save_prompt`）。
- 画面文字的逐字内容、贴字方式、字体，以及音色来源，放在新列 `product.settings_json`（迁移 `0017`，`ProductService.update_settings`）。
- 「选这个」放在 `product.pick_json`。
- 锁定后改这些都返回 409 `product_locked`，第 8 步改走影响范围。
- 重新分析不会覆盖这些设置。如果产物已经出过候选、而分析给出的描述变了，素材标 `seed_changed`；用户改了描述就清掉这个标记。

**「重新分析剧本」每次都采纳**
- 新增 `Component.adopt_every_run`。理由：用户明确点了重新分析，清单只增不删，而用户设的东西不在清单里，所以采纳不会覆盖任何人的工作。
- 依赖剧本新切片 `assets`（`script/service.py:script_slicer`）：场景的地点、时段，每行的 id、类型、人物，以及非对白行的文字。所以改一句对白的措辞，清单不会变旧。
- 另外依赖用到的设定条目（`entities:<id,…>`）。
- **素材清单接进影响范围和级联**：`PIPELINE_ORDER` 里排在剧本后面，左侧导航算在「素材」那一步。
  - 改动作行：影响范围多一行「第 n 集素材清单 · 会重新分析」，「确认并同步」最后会重跑它（便宜，而且只增不删）。
  - 改对白措辞：不影响素材清单。
  - 影响行的文案加了 `*_asset_list` 四个，中英都有。
  - M2 的几个测试跟着改：级联序列最后多了素材清单；「下游没东西」的例子改成改对白。

**接口**
- `GET /series/{id}/assets?episode=`：比 M0.5 的契约多 `scenes`（出现在本集哪几场，带全剧场号和行）、`note`、`seed_changed`。`shots` 到 M4 前是空的，示例剧集的镜头由 MSW 叠加。
- 排序：按类别，同类里按首次出现（集、场、行），没出现的排在最后、按清单顺序。
- 来源 `source` 多一个代码 `note`：没在任何一集出现时显示 note。
- `PATCH /assets/{id}`。
- `POST /episodes/{id}/assets/analyze` 改成返回任务（M0.5 的 MSW 同步返回 `{added, changed}`），前端在第 4 步跟着改。
- `GET /episodes/{id}/assets/matrix`：本集的场 × 用到的素材，格子里是行 id，空表示整场。
- `img` / `text` / `voice` 先放一份最简单的提示词模板，第 3、5、6 步写全。

## 2026-10-20 · M3 第 1 步：框架和媒体基础

**候选与锁定**
- **候选类组件不自动采纳**（`Component.auto_adopt = False`）：一次运行出一个版本，4 张候选都在 `files[]`（`role: candidate`，带 `idx`），由用户挑一张锁定。
- 「选这个」记在产物上（`product.pick_json = {version_id, idx}`，新接口 `POST /products/{id}/pick`）。不放物化表，重建物化表或 `demo --reset` 都不会丢。
- **锁定 = `ProductService.lock_pick()`**，在同一个事务里做三件事：
  - 出一个新来源类型 `pick` 的版本：只含选中那张（`role: ref`），沿用来源版本的模型、提示词、依赖；
  - 采纳并锁定；
  - 调用 `record` 钩子，写闸门记录（第 3 步的素材闸门）。
- 锁定**不改当前版本**，候选网格仍显示它来自哪一版。
- pick 版本的 payload 只有 `{candidate: 候选的说明}`，来源版本和第几张记在 `params`（不进哈希）。所以同一张图不管从哪一版锁定，哈希都一样。
- `idx` 为空时直接锁定整个版本：上传的图、API 终版、音色。
- 新来源类型 `upload`（上传的文件）。
- `product.retired`：所属对象已经不在了（剧本重跑后被删掉的台词）。这类产物不算待更新，也不进进度和级联（第 7 步用）。
- 这两列和 `asset`、`asset_use` 两张表都在迁移 `0016` 里一次建好。

**哈希含文件**
- 媒体槽位（`ref_image`、`ref_views`、`text_image`、`voice`、`line_audio`）默认用 `media_slicer`：切片 = payload + 文件 sha（不含提示词）。
- 这样闸门记的、下游依赖的都是图片或音频本身，换了图就变。

**运行参数**
- `POST /products/{id}/run` 加两个参数：
  - `where`：`api` 就是混合模式的「用 API 出终版」，走路由里的 API 模型；
  - `params`：带类型的 `RunParams`，包括 `task`、`source_version_id`、`source_idx`，未知字段 422。
- `params` 进任务参数和 `Inputs.params`，组件的 `run` 和 `estimate` 都读得到。
- 终版的 `parent_version_id` 是它出发的草稿。

**多次调用的组件**
- `router.call(..., fallback=False)`：作为流程一步的调用不自己兜底，由组件为整个流程统一兜底。
- 价格加 `Pricing.extras`（按次的附加服务，如音色设计 $3），按 `Usage.calls` 计费。
- 图片也支持 `price_by_res`（Gemini 4K 更贵）。

**账号**
- 媒体模型用 `account` 指向 `llm_providers` 里的账号，沿用它的密钥和地址（可用 `base_url` 另写）。
- 同一家的写作、出图、配音共用一个密钥。
- 本地模型注册时带上 `caps` 和 `workflow`。

**取文件**
- `GET /api/v1/files/{sha256}`：只接受 64 位十六进制。
- 类型按文件头判断（BlobStore 不存元数据）。
- 支持 Range（音频拖进度），缓存头 `immutable`。
- 版本里的 `files[].path` 改成实际的相对位置 `blobs/sha256/<ab>/<sha>`。原来写的 `blobs/<sha>` 不对；旧记录不改，界面只用 sha。

**台词音频**（`media/audio.py`）
- 解码成 48 kHz 单声道，裁首尾静音（低于 −45 dB）。每头留 50 ms，避免切掉第一个辅音。
- 响度目标 −18 LUFS、真峰值 −1.5 dBTP，配置在 `components.yaml` 的 `audio.dialogue`。对白比成片的 −14 LUFS 低，给 M7 的音乐、音效留余量。
- 增益取两者中较小的：拉到目标响度要的增益，和让真峰值不超的增益。不压缩、不削波：尖峰很大的片段（喊叫）宁可比目标轻一点，也不失真。
- 短于 0.4 秒（BS.1770 门限块）的片段按 RMS 估响度。
- 后端算好 64 段波形峰值，前端直接画，不引入 wavesurfer.js。
- 用 ffmpeg 处理（`imageio-ffmpeg` 自带），在线程里跑；没有用 SPEC 写的 pyloudnorm，因为它会把 numpy、scipy 带进主环境。

**Mock**
- Mock 图片改成柔和的双色渐变。
- 要求画字的图（`params.text`），把字写进 PNG 的 `iTXt` 块（`drama:text`），第 5 步的 Mock OCR 从这里读回。

**前端**
- 新增共用组件 `AudioPlayer`：播放 / 暂停、后端给的波形随播放点亮、时长；整页同时只放一个。
- 新增 `fileUrl(sha)`。
- 契约加上：槽位 `ref_views`、来源类型 `pick` / `upload`、产物的 `pick` / `retired`、运行的 `where` / `params`。

## 2026-10-20 · M3 第 0 步：整本组件的分块也看输出上限

- **一块原文还要小到让回答装得进 `max_tokens`**：`chunk_limit = min(60% × 最小上下文, 0.8 × max_tokens ÷ output_ratio)`。`output_ratio` 是「回答 token ÷ 原文 token（按 `estimate_tokens` 估）」，取 M2 第 13 步真实冒烟的实测值再留余量：设定提取 1.4（实测 2999 / 2741）、分集规划 0.9（1854 / 2741）、补全 0.3（429 / 2741）。原因：DeepSeek 的上下文是 1M，原来只按上下文切，长小说会整本塞进一次调用，而设定提取的回答和原文差不多长，JSON 会在 `max_tokens` 处被截断（M2 报告「遗留问题」）。
- `max_tokens`：设定提取 4000 → 8000，分集规划 4000 → 6000（都不超过常见模型的 8192 输出上限）。示例小说在三个组件里仍是一块，示例数据不变；估价按 `max_tokens` 算上限，设定提取的估价从 $0.0059 变成 $0.0083。

## 2026-10-20 · M3 计划：Kelvin 定的七项和范围

计划见 `plans/M3.md`（2026-10-20 批准）。

1. **镜头留给 M4**：M3 只把配音时长算到台词和场；镜头时长的计算函数（`pipeline/timing.py:shot_seconds`）在 M3 写好、测好，M4 出镜头时直接用。改素材时影响范围列出用到它的场和台词配音，示例剧集的镜头行仍由 MSW 叠加。ROADMAP M3 验收里的「镜头」那一半挪到 M4。原因：镜头表是 M4 分镜规划的产物，M3 先建会让分镜页（仍读示例数据）和后端各有一份镜头。
2. **本地部分在 M3 真装真跑**：ComfyUI（Qwen-Image-2512 出图、Qwen-Image-Edit-2511 补视图）、Qwen3-TTS（本地试听）、IndexTTS-2.5（本地配音）、RapidOCR，都在 Kelvin 的 PC 上装好、各真跑一次。Qwen-Image-Edit-2511 只能编辑，文生图另下 Qwen-Image-2512（约 20 GB，文本编码器和 VAE 共用）。
3. **本地文件夹同步挪到 M9**：M3 范围已经很大；同步页在 M9 之前仍是示例数据。
4. **真实冒烟用四家**：Google、OpenAI、火山引擎、MiniMax（Kelvin 都有密钥）。
5. **混合模式出终版**：本地出 4 张草稿，选一张后 API 以它为参考出 1 张终版（约 $0.14 / 素材），看过再锁定；草稿够用也可以直接锁定草稿。原型里 v2 的 $0.56（4 张终版）不照做。
6. **上传参考图**：要做，上传的图出一个 `origin: upload` 的版本，当一个候选。
7. **声音克隆先不做**：界面上「声音克隆」灰掉，写「之后支持」。

**不在 M3 做**：文件夹同步（M9）、镜头表和镜头时长落库（M4）、声音克隆（之后）、ElevenLabs 适配器（没有密钥；音色和配音的兜底改成本地 IndexTTS，和原型一致）、OCR 的 API 兜底（只用本地 RapidOCR，没装时标「未检查」）、后期贴字的真正合成（M7）、预演配音 `pv`（M4）、ComfyUI 的 WebSocket 进度（M5；M3 轮询 `/history`）、没有说话人的旁白配音（之后）。

## 2026-10-20 · M2 第 13 步：真实冒烟

- **按官方文档核对了 DeepSeek、Kimi、通义千问的模型 ID**（M2 四个组件的主模型、兜底和备选都在这三家）：`deepseek-v4-pro`、`deepseek-flash`（V4.1 Flash；旧名 `deepseek-v4-flash` 已退役）、`kimi-k2.6`、`qwen3.8-max` / `qwen3.7-plus` / `qwen3.8-flash`。价格和 `providers.yaml` 一致（Kimi 的价格页没读到表格，价格没核对）；DeepSeek 的「测试连接」（`GET /models`）也返回了这两个 ID。这三家改成 `verify: false`；火山、智谱、MiniMax、Google、OpenAI、OpenRouter 等后面的里程碑用到时再核对。
- **默认关掉「思考」**：这些模型默认都开思考模式。思考过程按输出 token 计费，也占 `max_tokens`（结构化 JSON 可能被截断）；而估价按 `max_tokens` 算答案，不算思考，「花钱前先估价」会算少。`providers.yaml` 的模型加了 `request` 字段：每次调用都带上的额外请求字段，不覆盖适配器自己设的（model、messages ……），请求自己的参数优先。DeepSeek / Kimi 写 `thinking: {type: disabled}`，千问写 `enable_thinking: false`。以后要开思考，改这里就行，不用改代码（硬规则 7）。Kimi K2.6 的 temperature 是固定值，传别的值会报错；我们的组件都不传。
- **冒烟脚本** `scripts/smoke/live_script.py`：自己起一个 `DRAMA_MOCK=0` 的后端（随机端口、临时数据目录），只走 HTTP，和 Kelvin 开着的工作台互不影响，其他地方仍默认 Mock。四个组件都指到 DeepSeek（设定提取默认用本地模型）。单次上限设成 `--ask-above`（默认 $0.20），估价超过就不跑、停下来问；累计花费加估价超过 `--cap`（默认 $1）也不跑；跑的过程中累计花费超过上限就取消。`--mock` 用 Mock 后端走同一条流程，不花钱，用来先检查脚本本身。
- 结果（2026-10-20，Kelvin 同意后我跑的）：示例小说第一章（160 字）→ 补全 4 条，全部采纳 → 设定 8 条 → 1 集 8 个节拍 → 第 1 集剧本 2 场。4 次调用，合计 $0.0078（按高峰价记账；跑的时候是闲时，实际扣费大约一半），没有兜底、没有失败，每次调用 2.2–4.6 秒。后端日志和临时数据库里都搜不到密钥。完整输出见 `reports/m2-live-smoke.txt`。

## 2026-10-20 · M2 第 12d 步：没分集时也能确认小说（Kelvin 定）

- **新剧集在分集规划前就能「确认原文，生成剧本」**：小说闸门本来就按剧集记（`gate_decision.scope_id` 是剧集 id，后端也收剧集 id），前端改成用剧集 id 确认；确认后进剧本页，那里就是「开始分集规划」。原因：12a 端到端发现，没分集时这个按钮是灰的（`GateButton` 要一个集 id），用户得先去剧本页做分集规划再回来确认，按钮上也没有提示。Kelvin 2026-10-20 同意这样改。
- **新接口 `GET /series/{id}/progress`**（`SeriesProgressOut`）：小说这一步按剧集算，其余都是「未开始」。SPEC 9.1 里没有这个接口，第 14 步补进去。左侧导航在路由里的那一集不存在时（还没分集）读它显示徽章；`GateButton` 的属性 `episodeId` 改名 `scopeId`，小说闸门传剧集 id，其他闸门传集 id。确认或重新打开小说闸门后，刷新剧集的进度和每一集的进度。
- 分集规划不归小说闸门管（第 10 步定的），所以小说先确认、后跑分集规划没有冲突。pytest 和 Playwright 的新剧集流程都改成先确认小说、再做分集规划。

## 2026-10-20 · M2 第 12 步：端到端

- **pytest 端到端起真实后端进程**（`tests/e2e/test_novel_to_script.py`，沿用 M0 的 `Backend` fixture），只走 HTTP；`model_call` 从 `/dev/model-calls` 读。原因：和 `tests/api` 的 TestClient 测试互补，覆盖启动时建产物、重启后闸门仍在。
- **Playwright 加 `real` 项目**：第三个 webServer 是 `VITE_DEMO_DATA=0` 的 Vite（5184），和 smoke 共用 Mock 后端 8765（后端 `DRAMA_WEB_ORIGINS` 两个都放行）；`pnpm e2e` = smoke + real。real 只收 zod 不一致（`does not match its schema`、`[events]`）、页面异常和 5xx；404 记成测试注释不算失败（现在只有 M4 的 `/episodes/{id}/shots`、M8 的 `/metrics/summary`、工作流库 `/workflows`）。原因：MSW 示例数据会盖住后端的真实返回，契约不一致只有关掉它才看得见。
- **M2 流程用例（`m2.spec.ts`）进 smoke 项目、串行**：会改示例剧集（剧本行、小说第 2 段），文件名排在 `smoke.spec.ts` 前面先跑；smoke 里的页面用例只看标题和报错，不受影响；任务页用例改成按新任务 id 找那一行。新剧集流程里 M3 / M4 才有的 `/series/{id}/assets`、`/episodes/{id}/shots` 的 404 列为允许。

## 2026-10-20 · M2 第 11 步：删掉旧界面

- 删 `web/src/legacy/`（上游 Hermes 界面）、`pages/Legacy.tsx`、`/legacy` 路由、`common.legacy` 词条和 ESLint / Prettier 里对它的忽略。
- **后端不再挂上游的 `/api/series/*`**：这些接口直接调模型、不经过 `router.call()`（不记账、不查预算），唯一的用户 `/legacy` 已经删了。上游代码（`api/routers/series.py`、`api/schemas/`、`agent/`、`drama/` …）留在仓库里，只是不挂载；`drama-series-render` 命令行不变；`drama-series-api` 仍起 `create_app`，现在只有 `/api/v1`。
- `tests/api/test_upstream_settings.py`（上游 settings 接口不回传密钥）删掉：接口不再对外；`test_app` 改成断言 `/api/series/...` 是 404，`test_isolation` 的白名单去掉上游 router 那一项。

## 2026-10-19 · M2 第 10 步：闸门、影响范围

### 10c 前端（2026-10-20）

- **影响范围弹窗的按钮**：主按钮（实心、排第一）「确认并同步 · 预计 $x」（估价是 0 时只写「确认并同步」），然后「只改这里，下游标待更新」「撤销」。会重跑的产物就是弹窗里的各行（后端按流水线顺序列，各带估价）。原型里的「只标记待更新 / 自动重跑受影响的部分 / 撤销修改」按 Kelvin 2026-10-19 第 6 条改了（原型没跟着改）。成片规格页（M4 前仍是 MSW）保留原型的顺序（`primary="mark"`，「改，并标记待更新」在前）：改画幅要重画关键帧、重做视频，自动重做是例外。
- **「同步中」从哪来**：RunBar 看产物的 `running.cascade_id`；左侧步骤看全局任务列表（`/jobs`，SSE 实时更新）里没结束、带 `params.cascade` 的任务：补全、设定 → 小说，分集 → 剧本，剧本只算本集的（`useJobs.ts:syncingSteps`）。不加接口：任务列表本来就常驻在 App 里。
- **完成提示**：toast `cascade_done` 有失败时前端换成 `cascade_done_failed` 的文案（`api/events.ts`）。`gate.updated` 刷新产物、剧集列表（剧本状态）和进度徽章。
- **MSW**：`/gates/novel|script` 放行到后端。`/impact/preview` 除了 `spec_aspect`、`asset_unlock`（M4）都转给后端；示例剧集第 1 集剧本的块，在后端结果后面再叠加镜头、关键帧这些下游行（`fixtures/demo/impacts.ts:scriptDownstream`），叠加的「待更新」记在 `impactOverlays`，`/impact/apply` 转给后端成功后再加到示例进度上。转发用 `mocks/backend.ts:backendResponse`（错误原样返回），不用 `passthrough()`：页面测试里要落到假后端（`test/fakes/impact.ts`）。删掉 apply 里转发 PATCH 的那段和 `series.ts` 里演示闸门的叠加。
- **示例种子的闸门**：`seed_demo` 最后确认小说闸门和第 1 集剧本闸门，只在这个闸门从来没有过决定时做：用户重新打开的，重启后保持打开。后端测试默认把 `demo.CONFIRMED_GATES` 换成空的（`tests/conftest.py`；大多数测试直接改示例剧集），要种子闸门的测试用 `demo_gates` fixture（导出前端测试数据的 `test_web_fixtures.py` 用它，所以前端假后端里小说和第 1 集剧本是已确认的）。
- **什么时候先预览**（10c-2）：小说页的改动（逐段编辑 `novel_edit`、重新导入 `novel_replace`、设定编辑 / 合并 / 拆别名 `bible_edit` / `bible_merge`、补全的采纳 / 忽略 / 恢复 `suggestion_decision`）在小说已确认**或**有任何一集剧本已确认时先预览；节拍的拖动和改动（`beat_move`）只在它离开或进入的那一集剧本已确认时预览，别的集照旧直接写、立即显示新位置。预览没有任何行就直接「只改这里」（toast「已保存。」）。共用组件 `ImpactGuard`（页面包一层，`active` 决定要不要预览）+ `useImpactGuard()`（各编辑处拿到就走预览，拿不到就照旧直接写），弹窗是 `ImpactDialog variant="modal"`，「撤销」后编辑框保持原样（用户可以接着改或取消），写入后编辑框 / 弹窗才关。原因：编辑分散在五个组件里，一个页面只要一个弹窗。
- **后端没有影响种类的操作**：已确认时「全部采纳」和按要求重写补全（要调模型）按钮置灰，补全区写一句「要先重新打开」——后端对锁定的补全返回 409，与其报错不如先说清楚。改集（集名、钩子、卡点、预计时长）不预览：分集规划不归任何闸门，直接改，受影响的剧本照常显示「待更新」。
- **假后端的影响预览**（`test/fakes/impact.ts`）：「只改这里 / 确认并同步」时，用直接编辑的那个请求（`PATCH /lines`、`PUT …/chapters/{idx}`、`POST /suggestions/{id}/accept` …）写入，落到各自的假后端 handler，不另写一套写入逻辑；`novel_replace` 只记录（上传的文件在后端）。`openFakeGates()` 把两个闸门都打开，测「没确认时直接写」的老测试用它。

### 10b 后端（确认并同步）

- **同步不建表**：一次「确认并同步」= 一组重跑任务，任务参数里带 `cascade: {id, origin}`（`origin` 是改动的那个产物）。每一步都从数据库现算（`pipeline/cascade.py:advance`）：这组任务到目前的状态 + 从 `origin` 往下、现在「待更新」的产物。任务结束（成功、失败、取消）时队列的新钩子 `JobQueue.on_finished` 触发下一步；启动时 `StudioState.run()` 调 `cascade.resume()`，把停机正好停在两步之间的同步接着走（不弹完成提示）。原因：同步的状态本来就在任务和版本里，另存一份只会对不上。
- **顺序**：一个产物要等它上游里「流水线更靠前」的产物都处理完（还要重跑的、在跑的、等确认的、失败或取消的都算没完）；同一层（几集的剧本）并排跑。流水线顺序是 小说 → **补全 → 设定** → 分集 → 剧本：设定按「原文 + 已采纳补写」提取，补写的锚点带着新原文的 id，所以补全要先跑；补全只读设定的名字，设定重跑后名字变了，补全再跑一次（它采纳过的建议原样保留，设定不会再变旧）。影响预览里各行也按这个顺序列。**每个产物一次同步里最多跑两次**，失败 / 取消的不重试，它下面的也不跑（停在「待更新」），别的分支继续。原因：不这样排，分集和剧本会先按旧设定跑一遍、设定出来后再跑一遍，花两份钱；最多两次防止设定 ↔ 补全来回跑。
- **自动采纳**：同步里的重跑成功后，如果它还是界面上的当前版本（用户没在中途换别的），就采纳；被锁的先重新打开它所在的闸门（没有闸门却被锁的直接解锁）。改的那个产物本身照 `mark` 写入、重新锁上；它所在的闸门只有在同一闸门下别的产物被重跑采纳时才重新打开（改小说 → 设定、补全重跑 → 小说闸门打开；只改剧本一行、下游没东西 → 剧本闸门保持确认）。
- **预算**：每个重跑照常走 `RunService.start` 的估价和单次上限 / 本集剩余检查，超了进「等你确认」，确认后接着往下。
- **完成提示**：这组任务都结束、也没有能再排的时候，发一次 toast `cascade_done {count, failed}`（`count` = 更新了几个产物，按产物去重；有失败时 `level: warning`），文案 key 在 10c 加。`GET /products` 的 `running` 多一个 `cascade_id`，前端 10c 用它显示「同步中」。

### 10a 后端（闸门、影响预览、`mark` / `undo`）

- **第 10 步拆成三块**：10a 后端闸门 + 影响预览 + `mark` / `undo`；10b「确认并同步」级联重跑（后端）；10c 前端（弹窗主按钮、同步中状态、MSW 放行、示例种子的闸门）。10a 期间 `rerun` 返回 422 `action_not_supported`，前端的 `/impact/*`、`/gates/*` 仍由 MSW 处理，所以页面行为不变。
- **两个闸门各管什么**（SPEC 5 组件表）：小说闸门 = 本剧的小说、设定、补全（按剧集，前端传集 id，后端换成剧集，`gate_decision.scope_id` 存剧集 id）；剧本闸门 = 一集的剧本。分集规划不归任何闸门（SPEC 表里 split 的闸门是「—」），所以拖节拍不会 409；它让已确认的剧本变旧，前端在 10c 里遇到这种情况先弹影响范围。确认时锁定已采纳的版本（`locked_hash`），`product_hashes_json` 记有效哈希（补全取 `adopted` 切片，其他取整个 payload）；第一个产物（小说 / 剧本）没有采纳过返回 409 `nothing_adopted`，有任务在跑返回 409 `product_busy`；重复确认返回原来那条决定，只补锁。重新打开解锁。时间相同的两条决定会把后一条往后挪 1 微秒，保证「最后一条」唯一。
- **影响预览 = 在事务里试写再回滚**：各领域服务把编辑拆成「算出来」（`plan_*`，返回 `PlannedChange`：新的 payload，或补全决定的 `stage`）和「写进去」（`commit`）；预览把改动写进一个会话（新版本设为采纳、或写决定行）、用和「待更新」同一套切片哈希算出哪些依赖切片变了，然后回滚。原因：不另写一套「假设」逻辑，补全决定这种不进版本的改动也能算。SQLite 的写事务在第一次写入时才开始，之前的读不占锁，回滚后什么都不留（测试：预览 + 撤销后决定仍是待定）。
- **预览列什么**：直接依赖变了的切片的产物 = 「待更新」（`stale_<slot>`，带当前路由的重跑估价，本地或估不出为 null）；再往下的（依赖这些产物的）= 可选（`then_<slot>`，上游重跑后有变化才会跟着变）；改的产物本身被锁定时第一行 `self_<slot>`「已确认的 X 会改成新内容」（改动等于没改时不出这行、也不出别的行，前端照旧直接 `mark`）；受影响的产物被闸门锁着时 `gate_<gate>`（同步后闸门会重新打开）；受影响产物的已采纳版本是手改的（origin `edit`）时 `edited_<slot>`。`<slot>` 用产物的 slot（`novel`、`bible`、`suggestions`、`episodes`、`script`），剧本行带 `{n: 集号}`。`stale` 计数：小说步 = 设定、补全，剧本步 = 分集规划、剧本。`rerun_cost_usd` = 直接 + 可选各行估价之和（同步最多会跑这么多）。文案 key 在 10c 加。
- **改动种类**：计划里的七种，另加 `bible_merge`（合并 / 不是同一个 / 拆出别名，`patch` = `POST /bible/merge` 的请求体，`target_id` 是第一个 id），否则小说确认后设定面板的合并建议只能先重新打开闸门。`scene_edit` 的 `patch` 接受 `text`（剧本页发的）或 `heading`。`suggestion_decision` 的 `patch` = `{action: accept|reject|reset}`（按要求重写要调模型，确认后的小说里先不支持，409 `product_locked`）。`novel_edit` 的 `target_id` 是剧集 id，`patch` = `{chapter, title, paragraphs}`。
- **重新导入已确认的小说**：`POST /series/{id}/novel` 的 `dry_run` 现在把上传的文件存进 blob 库，返回 `upload_id`（文件的 sha256）；影响预览 `novel_replace` 的 `patch` = `{upload_id, filename}`，确认后按这个文件导入。原因：影响范围的请求是 JSON，不能再传一次文件；文件按内容寻址，导入时本来也要存。zod `NovelImportSchema` 加 `upload_id`。
- **`mark` 写已锁定的产物**：先解锁、写入（各服务原来的编辑路径，物化、事件照旧）、再按新采纳的版本锁上；闸门仍是「已确认」，不另记一条决定（用户在弹窗里确认的就是这次改动）。下游被锁着又变旧的（比如改了原文后的设定、已确认的剧本），`mark` 不动它们的锁：状态显示「待更新」，要重跑采纳得先重新打开闸门，或者用「确认并同步」（10b）。
- **预览存在内存里**（最多 100 条），应用时按同样的改动重新算一遍：改动所基于的版本或内容变了返回 409 `impact_outdated`；后端重启后旧预览 404 `impact_not_found`，重新预览即可。不建表：预览是几秒钟内的事，没有要持久化的东西（同步任务的 id 在 10b 存在任务参数里）。

## 2026-10-19 · M2 第 9 步：剧本化

### 9b 前端

- **改一段怎么存**：剧本没确认（`script_status` 不是 `confirmed`）→ 直接 `PATCH /lines|scenes/{id}`，toast「已保存」，不弹影响范围；已确认 → 照旧先影响预览。第 10 步之前影响范围还是 MSW 的，选「只标记 / 自动重跑」时 MSW 把改动转发给后端的 PATCH（和改画幅 `spec_aspect` 一样），所以剧本内容始终在后端。
- **重写超预算**：409 `over_budget` 时在那一段下面显示「预计 $x，超过上限 $y，确认后才会发出」+「仍然重写」（带 `confirm_budget` 再发），和补全的重写一样。
- **三向溯源走 URL 参数**：剧本页 `?line=<id>`、分镜页 `?shot=<id>`、小说页 `?para=<段号，0 起>`。剧本行选中后显示「对应镜头 1-06」（链到分镜页）和「来自原文第 N 段」（链到小说页）；分镜的镜头设定最上面一栏「剧本」列出它拍的行（链到剧本页）和原文段号（链到小说页）；小说页点段号打开「在剧本里」（按分集规划的节拍段号找到是哪一集，再读那一集的剧本，列出引用这一段的行，链到剧本页）。链接带来的选中和用户自己点的：用户点的优先，链接一变就以链接为准（在渲染时推出来，不用 effect 同步状态——react-hooks 的 `set-state-in-effect` 规则会报）。
- **镜头 → 剧本行用 `ShotSchema.line_ids`**（SPEC 4.1 `shot.line_ids`）：示例分镜 9 个镜头补上行 id（1-06 拍 `demo-b8` 并叠着旁白 `demo-b10`），M4 换成真实分镜。
- **MSW**：删剧本 handler、`fixtures/demo/script.ts`、示例剧本产物和「第一次出剧本 → 草稿」的逻辑。`GET /products?owner=episode:<示例集>` 合并后端的产物（剧本化），空 id（集还没加载）不去问后端，其他剧集的集直接放行。分集列表的叠加只剩镜头数，以及演示闸门确认时把后端的「草稿」显示成「剧本已确认」；`stage` 用后端的。进度徽章的剧本步同理：后端的，演示闸门确认时显示「已确认」。这些在第 10 步闸门接后端时删掉。
- **`product.updated` 事件也刷新 `["episodes", …]`**（剧本、进度徽章）：跑完一集剧本页面自己换成剧本。没有剧本时才显示「生成这一集的剧本」；原来「剧本草稿已生成（示例只展开第 1 集）/ 重新生成这一集」那段删掉了（现在任何一集都能真的生成，重跑在运行条上）。
- **运行条加载中占位**：剧本化产物要从后端拿，比 MSW 慢，运行条没出来前先显示骨架（和小说页一样），截图不会漏掉它。

### 9a 后端

- **第 9 步拆成 9a 后端、9b 前端**（和第 8 步一样），计划里记了。
- **剧本化读什么**：只读这一集——分集规划的 `episode:<id>`（集名、钩子、卡点、预计时长 / 场数、节拍）、节拍引用的段落（按章分组，带段号）、这些段落上的已采纳补写、本集用到的设定条目（段落里出现过的条目，或名字 / 别名出现在本集文字里的人物、地点、道具）。依赖四种切片：分集 `episode:<id>`；小说 `chapter:<idx>`（段落所在的章；小说版本只存每章的哈希，做不到段级，改了同一章的别的段也会让它变旧）；补全 `adopted:<段号,…>`（只看这些段上的已采纳补写，新加的切片）；设定 `entities:<id,…>`（这些条目的类别、名字、别名、简介，不含段号；条目被删掉哈希也会变，新加的切片）。所以拖一个节拍只让两集的剧本变旧，采纳第 3 章的补写不影响第 1 集。按集记花费（`episode_id`），入队查本集剩余预算。
- **补写编号**：提示词里补写写成「【补写1】」，模型在行的 `adds` 里引用编号；后端换成 `{source_id: "sug:<建议 id>", start: 0, end: 字数}` 的出处，并把补写所在的段号并进这一行的 `paras`（小说上标亮那一段）。
- **payload 里不存序号**：场的顺序 = 列表顺序；`GET` 时场号按全剧累加（前面各集有已采纳剧本的数剧本里的场，没有的用预计场数），行的 `idx` 是本集阅读顺序、场标题也占一个号（第一个场标题是 0，和 MSW 示例一致）。**场标题不含场号**（「夜　内　林晚出租屋」），前端显示时拼「场 N　」；模型或用户写在前面的「场 N」会被去掉。这样改第 1 集的场数不会改第 2 集的任何内容和哈希。分集卡片的「场 x–y」在有剧本以后按实际场数算。
- **接口多返回 `paras`**：场和行都带段号（0 起），前端直接用，不再拿字符区间去匹配段落（来自补写的出处 `sug:` 起点是 0，会被误配到第 1 段）。`GET /episodes/{id}/script` 像设定一样显示当前版本，带 `product_id`、`version_id`、`adopted`、`source_id`。
- **新增 `PATCH /scenes/{id}`**（计划只写了 `PATCH /lines/{id}`）：「重写这一段」对场标题也能用，保存建议需要它。两个 PATCH 都只收文字（`text` / `heading`），从当前版本出 `edit` 版本并采纳，改过的标 `edited`（「已修改」）；内容没变不出版本。被锁定 409 `product_locked`（第 10 步接影响范围），在跑 409 `product_busy`。返回整个剧本。
- **重写**：`POST /lines|scenes/{id}/rewrite` 带可选 `model`（「换模型重写」）、`instruction`、`confirm_budget`，返回 `{text, model_key}`，什么都不存；按估价先查单次上限和本集剩余预算，超了 409 `over_budget {reason, estimate_usd, limit_usd}`。锁定的剧本也能要建议（保存时走影响范围）。
- **id**：重跑时第 n 场沿用已采纳版本第 n 场的 id；行先找本集里文字完全相同的，再找同号那一场里相似度 ≥ 0.6 的，都没有出新 id（`sc-` / `ln-` + 12 位）。示例第 1 集的 id 和 MSW 一致（场 `demo-b1`、`demo-b7`，行 `demo-b2..b12`）。
- **人物 / 地点 id**：模型写的名字按设定的名字 / 别名对上（规范化后完全相同，否则取包含在里面的最长名字，所以「林晚（OS）」是林晚、「夜　外　便利店门口」是楼下便利店）。
- **每集的剧本产物在分集规划采纳时建**（物化里补上没有的），启动时也给已有的分集补上（Kelvin 现有的库）。示例三集的剧本产物 id 固定（`demo-p-script-e1..3`），第 1 集种子 v1 本地 10:12 → v2 Kimi 10:20（不满意换一个）已采纳，和 MSW 一致；`demo-b10` 的「叠在 1-06」是示例数据，模型不输出。
- **`ProductService.append_edit`**：设定、分集、剧本三处「用户手改出 edit 版本」的重复代码合成一个。

## 2026-10-19 · M2 第 8 步：分集规划

### 8b 前端

- **看板放在「分集」区，和卡片二选一**（`pages/script/Episodes.tsx`）：切到看板时 Inspector 和运行条换成分集规划，切回卡片换回剧本化。还没有分集时是空状态（「开始分集规划」）。分集规划正在跑或被锁定时看板只读；当前版本没采纳时提示「在历史里采纳后才会换」（列表读已采纳的方案，见 8a）。
- **拖动用浏览器原生拖放**（不加依赖）：卡片上半截放在它前面、下半截放在后面，列的空白处 / 「拖到这里放在最后」放在最后；被拖的卡片留在原处变淡（Chrome 里拖动的源元素离开页面会结束拖动），落点用一条叠在卡片上的蓝线标出（不占位置：占位的标记会把卡片挤开，指针下的目标来回跳）。界面先按新位置显示、请求失败就退回，完成后重读列表（示例剧集要叠加 MSW 的数据）。键盘和不方便拖的时候用节拍弹窗里的「所在的集」。
- **情绪曲线**（`EmotionCurve.tsx`）：按 SPEC 11.3，一根 y 轴（-1 / 0 / +1）、2px 线（单调三次插值）、每个节拍一个 10px 点、各集之间虚线分隔、悬停十字准线 + 读数、「图 / 表」切换；只有一个系列，不放图例。情绪写成「+0.4」「−0.25」「0」。
- **RunBar 的版本行**：没有模型的版本（手动修改、导入）写来源（「v2 · 手动修改 · 01:12 · 已采纳」），不再留空。
- **MSW**：`GET /series/:id/episodes` 和 `GET /episodes/:id/progress` 读后端，示例剧集叠加镜头数、剧本状态、阶段（剧本和闸门还在 MSW，第 9、10 步删），进度里小说步取第 1 集的闸门状态（小说闸门是整部剧的）、待更新数用后端的；`PATCH /episodes/:id` 删掉（预算走后端，顶栏的预算由 `/metrics/summary` 从后端的分集读，全剧预算 = 各集之和）；`demo-p-split` 删掉。页面测试的假后端 `test/fakes/episodes.ts`（数据 `test/data/episodes.json` 由 `test_web_fixtures.py` 导出），`fakeBackendFetch` 挪到 `test/backend.ts` 统一分发。

### 8a 后端

- **分集规划读什么**：原文（和设定提取、补全一样按块发，段落后带已采纳补写）+ 每章摘要（设定提取写的）+ 设定里的名字 + 成片规格的每集时长。计划里写的是「摘要 + 设定 + 已采纳补写」，我加上了原文本身：节拍要标出处（段号），只有摘要标不出来；3000 字的示例一块就够，长小说分块。依赖四个切片：小说 `chapters`、设定 `chapters`（摘要）和 `names`、补全 `adopted`。分集规划属于整部剧，只查单次上限。
- **长小说跨块**：第 2 块起带 `[上一块]`（切到第几集、最后一段），模型这一集没讲完就用同一个 `ep` 号接着写，后端把它接回上一集（节拍拼上，卡点用后面的，时长 / 场数取大）。
- **每集时长档位进配置**：`config/spec.yaml` 的 `episode_lengths`（short 30–90 秒、mid 90–180、long 180–300、xl 540–660），提示词里写「每集时长：30–90 秒」。改成片规格不会让分集变旧（规格不是产物），要换就重跑。
- **id**：重跑时第 n 集沿用已采纳版本第 n 集的 id；节拍先找全剧里文字完全相同的，再找同号那一集里相似度 ≥ 0.6 的，都没有就新 id。示例剧集的 id 和 MSW 一致（`demo-e1..3`），节拍 `demo-bt1..22`（`demo-b*` 已经是剧本行）。
- **`GET /series/{id}/episodes` 读已采纳的方案**（镜像表 `episode` / `beat`，迁移 `0014`），不像设定和补全那样读当前版本：集是剧本、预算、花费挂靠的地方，导航、顶栏都用它，不能显示一个还没采纳的方案。重跑出的新方案在历史里，点「采纳」后列表才换。手改（集名、钩子、卡点、预计时长；节拍文字、情绪、拖动）从已采纳版本出 `edit` 版本并采纳。每集带 `beats`、`scene_count`（预计场数）。
- **本集预算是设置，不进版本**：存在 `episode.budget_usd`，物化只更新内容字段、从不动它；`PATCH /episodes/{id}` 只改预算时不出版本、闸门锁定时也能改。`modelhub/budget.py` 的「本集剩余」从这里读（第 4 步留的钩子）。示例三集各 $15。
- **`PATCH /beats/{id}` 返回整个方案**（拖一个节拍会改两集）；`position` 是在目标集其余节拍里的位置（0 起，省略 = 放最后）。集的切片 `episode:<id>` 是剧本要读的内容（集名、钩子、卡点、时长、场数、节拍的 id / 文字 / 情绪 / 段号），不含字符区间（同一文本重新导入会变）也不含序号，所以拖一个节拍只让两集变旧，换集号不让任何一集变旧。
- **派生字段**：`script_status` 看这一集的剧本产物（没采纳 = `none`，剧本闸门最后一次是确认 = `confirmed`，否则 `draft`）；`stage` 有剧本版本 = `in_progress`，否则 `script_pending`（`not_started` 暂时不用）；`scene_from / scene_to` 在有剧本之前按预计场数全剧累加；`shot_count` 到 M4 才有。`GET /episodes/{id}/progress`：小说步看小说闸门，待更新数 = 设定、补全里变旧的；剧本步看本集剧本和闸门，待更新数 = 分集规划和本集剧本里变旧的；后四步先是「未开始」（示例剧集由 MSW 叠加）。

## 2026-10-19 · M2 第 7b 步：小说逐段编辑

- **一章一次提交**：`PUT /series/{id}/novel/chapters/{idx}` 带 `{title, paragraphs}`（这一章改完后的样子），返回这一章（和 `GET …/novel?chapter=` 一样）。段落里的换行当作分段，前后空白去掉，空段丢掉；整章删空 422 `chapter_empty`；标题空 = 没有标题。内容和现在一样时什么都不出。没有小说 404 `novel_not_found`，被闸门锁定 409 `product_locked`（第 10 步接影响范围）。
- **新文本按固定格式拼**（`novel/parse.py:compose`）：每章「标题行、空行、一段一行」，章与章之间空一行；章节和段落按给的来，不再解析一遍，所以不像标题的标题也留着。存成新的 `novel_source`（`encoding: edited`，文件名和改编权确认时间沿用），小说产物出一个 `edit` 版本并采纳（父版本是原来采纳的那个）。章节哈希只看标题和各段文字，没改的章哈希不变：只依赖那几章的产物不变旧；设定、补全读整本书，变待更新。有测试：拼出的文本再导入一次，章节和段落完全一样。
- **补全建议跟着文字走**：`reanchor` 先找文字完全相同、离原段号最近的段；找不到就在原段号前后 20 段里找最像的（`SequenceMatcher` ≥ 0.6，改了几个字的那段）；都没有才丢掉。`GET /suggestions` 也按这个把当前版本的建议挪到现在的文本上显示（段号跟着插入 / 删除变），设定提取读的补写也一样，不用等补全重跑。
- **设定的段号不跟**：设定条目的 `paras` 还是旧文本的段号，在它前面插段以后，点设定卡标出的段会错位，直到设定重跑（它本来就变待更新了）。没做实时换算，等第 10 步的同步自动重跑。
- **前端**：只在「原文」视图里能改（另外两个视图里有补写，不是作者的原文），提示「要改原文，切到「原文」」；每段悬停或键盘聚焦时浮出「改 / 在后面插入 / 删除」三个按钮（浮在段落上，不占正文宽度）；删除要在那一段下面再确认一次；章节选择旁边「改标题」。下游有采纳的结果时编辑框下面写「保存后小说补全、设定提取会变成待更新」（第 10 步换成影响范围弹窗）。小说被锁定时不显示这些按钮。截图 `reports/ui/novel-edit.light.jpg`。

## 2026-10-19 · M2 第 7 步：小说补全

- **Kelvin 回复「continue」**：按「计划变更」做（第 7、7b、10 步）；同步后被确认过的闸门重新打开（我的提议）没有反对，第 10 步照这个做。
- **决定不进版本**：`suggestion_decision`（迁移 `0013`，和镜像表 `suggestion` 一起）按建议 id 存状态、重写后的文字、要求、重写用的模型；采纳 / 忽略 / 撤销 / 重写都不出版本。没有行 = 待定。撤销一条重写过的回到「已重写」（和原型一致）。
- **重跑怎么带过去**（`suggestions/ops.py:reconcile`）：已采纳版本里**已采纳的建议原样保留**（用户同意的是那段文字），重跑在同一段同一类又给的当重复丢掉；其他建议同段、同类、同文字（忽略空白）的沿用 id，所以「忽略」还是忽略；剩下的出新 id（`sug-` + 12 位）。理由也换成新的。
- **小说换了文本**（重新导入；以后 7b 的逐段编辑每次也是新 source）：补全把旧建议按段落文字挪到新文本里最近的同文字段落，找不到的丢掉（`reanchor`）。设定提取只用锚在当前文本上的补写，其余的等补全在新文本上重跑。
- **有效哈希**：补全产物的 `adopted` 切片 = 已采纳建议的 id、段号、出处和最终文字（有重写用重写）；设定提取依赖它。待定、忽略的改动不让设定变旧。
- **补全读设定的 `names` 切片**：每条的类别、名字、别名，加冻结条目的全部字段（键名用 `fixed`：`frozen` 是显示字段，切片哈希会跳过）。示例剧集的补全是在设定之前做的，没有这条依赖；重跑后才有。
- **补写在提示词里**：`[P3] 原文【补写】补写文字`，跟在那一段后面，段号不变；设定提取的模板加了一句说明，默认意图改回原型的「只用原文和已采纳的补写，不要编」。分块代码挪到 `pipeline/components/chunks.py`，两个组件共用（块大小按带补写的文字算）。
- **按要求重写**：同步调用，用组件路由的主用模型（`enrich/rewrite.j2`，任务 `rewrite`，`max_tokens` 400），先估价，超单次上限返回 409 `over_budget {estimate_usd, limit_usd}`；前端在那张卡里显示「预计 $X，超过上限 $Y…」和「确认花费，重写」，确认后带 `confirm_budget: true` 再发，这次调用最多花到估价（兜底更贵就 409）。`model_call` 记在补全产物上。
- **`GET /series/{id}/suggestions` 改成对象**（和设定一样）：`{product_id, version_id, adopted, source_id, suggestions}`；当前版本没采纳时标题旁标「未采纳」并说明设定和分集仍用采纳的那一版。`accept-all` 也返回这个对象。决定后后端发 `product.updated`，前端刷新产物列表（设定可能变待更新）。RunBar 还不显示「待更新」，第 10 步做。
- **补全和设定可能来回触发**：采纳补写 → 设定待更新 → 设定重跑出新名字 → 补全待更新 → 补全重跑……每一步都要用户点（或第 10 步的同步）。第 10 步的级联同步要保证同一次同步里每个产物只跑一次。
- **示例剧集**：补全 v1 本地 09:41 → v2 DeepSeek V4 Pro 10:02（不满意换一个）采纳，s1 已采纳，内容来自 `tests/fixtures/demo/enrich.json`（原型 4 条，也存了原型的重写文字）；设定 v1 依赖补全的 `adopted` 切片。有测试：新剧集真跑一遍补全，结果除 id 外和种子一样。MSW 删掉补全数据、handler 和补全产物；`products.test.tsx` 这类通用组件测试自己往 MSW 库里放一个同样历史的 `test-p-enrich`；页面测试的假后端 `test/fakes/suggestions.ts` 用后端导出的 `test/data/suggestions.json`。假后端的产物估价跟着路由变（换成本地模型就是 0），和后端读时现算一致。
- **测试不再借用示例剧集的 `suggestions` 槽**：`test_novel_api`、`test_products_api` 改用测试专用的槽。
- **迁移号顺延**：第 7 步用了 `0013`，计划里第 8、9 步的迁移改成 `0014`、`0015`。

## 2026-10-19 · Kelvin 定：手动编辑和自动同步

- **小说、剧本都能手动编辑，编辑确认后自动同步**：影响范围弹窗的「确认并同步」写入改动后，直接受影响的下游按估价自动重跑，并一层层往下（级联到剧本），**新版本自动采纳**；每一步照常过预算检查。硬规则 5 改成：只有用户确认过的改动能触发自动替换，旧版本都在历史里（CLAUDE.md 已改）。被闸门确认过的下游同步后闸门重新打开，等用户再确认（我的提议，写在计划第 10 步里给 Kelvin 过目）。
- **小说逐段编辑**：改字、插入 / 删除段落、改章节标题；保存出新的小说版本和新的 `novel_source`，段号重排（计划新增第 7b 步）。
- **都在 M2 做**；计划 `plans/M2.md` 加了「计划变更」一节，改了第 7、10、12 步和验收。
- **示例小说加长到 3006 字、71 段**：第 1 章不动（原型那 5 段），第 2 章加 3 段（拐角撞上外卖员、那年夏天在便利店画她、玻璃上的画法），第 3 章加 4 段（三年没联系的句号、伞柄发烫、旧白衬衫、站台灯箱）。`extract.json` 的段号按原文匹配重排。已有的库要 `drama-studio demo --reset` 才会换成新文本。

## 2026-10-19 · Kelvin 定：设定读已采纳的补写

- **设定提取读原文 + 已采纳的补写**（和原型一致）：采纳 / 撤销一条补写，设定变「待更新」。**补全只用设定里的名字和冻结的条目**（原型的补全提示词里只有「设定卡：林晚、周屿」），依赖设定的切片只含这些，所以重跑设定不会让补全变旧，不会互相循环。补全里加的外貌、穿着经设定流到 M3 的角色参考图。第 7 步实现：设定提取的输入加上已采纳补写（按段插在原文后面，段号不变），默认意图改回原型的「只用原文和已采纳的补写，不要编」；6a 的第一条作废。

## 2026-10-19 · M2 第 6 步：设定提取

### 6b 前端

- **设定卡的交互**（原型里只有四列文字，没有这些）：点一条在原文里标出它出现的段落（暖色底，和补全建议定位用的蓝色区分），出处在别的章先切章再滚过去，四列下面一行说「出现 N 段，已在左边标出」；再点一次取消。铅笔按钮打开「编辑设定」（名字、别名、简介、冻结；每个别名可以「拆出来」），只发改了的字段。「可能是同一个」放在四列上面：「合并」留下原文提到更多的那条，另一条变成它的别名；「不是同一个」直接消失。当前版本没采纳时标题旁标「未采纳」，并说明剧本和素材仍用之前采纳的那一版。关系类条目不显示（原型只有四列；人物关系图不在 M2）。
- **MSW 合并后端的产物列表**：示例剧集的 `GET /products?owner=series:demo` 先取后端的（小说、设定提取），再接 MSW 的（补全、分集、剧本……），经 `mocks/backend.ts:backendJson()`（`bypass` 发给后端，后端不在或出错当空）；不在 MSW 库里的产物 / 版本 id 一律放行到后端。页面测试里 `backend()` 把它换成假后端（`test/fakes/bible.ts`，数据是后端导出的 `test/data/bible.json`）。删掉 MSW 的设定数据、设定 handler 和设定提取产物，`PRODUCT_EXTRACT` 留作后端产物的 id。
- **设定区的说明文字仍是原型的「来自原文和已采纳的补写」**，虽然现在只读原文：第 7 步定了补写进不进设定再一起改。

### 6a 后端

- **设定提取只读原文，不读已采纳的补写**：原型的意图写「只用原文和已采纳的补写」，但 SPEC 里补全要读设定（小说 + 设定 → 建议），两边互读会循环（采纳补写 → 设定待更新 → 重跑 → 补全待更新 → …）。默认意图改成「只用原文，不要编」。补写里新出现的外貌、穿着怎么进设定，第 7 步做补全时再定（问 Kelvin）。
- **依赖切片 `chapters`**：设定读整本书，按切片 `chapters`（各章哈希的列表，不含文件名和 source id）依赖小说产物；加章、删章、改任何一章都变待更新。
- **分块**：按章凑块，原文块 ≤ 路由上主用模型和兜底模型里较小上下文的 60%；一章超了按段拆，后面几块的章标题带「（续）」；一段超长也不拆。`providers.yaml` 的 LLM 加 `max_context`：只给本地两个填了 32768，API 的没核对过不填（按 32k 算，宁可多分几块）。本地服务的 provider 加 `send_num_ctx: true`，请求体带 `options.num_ctx`（Ollama 默认上下文只有 2–4k，会悄悄截断）。Ollama 的 OpenAI 兼容接口认不认这个字段，网上说法不一，没核对：第 13 步或本地真跑时看 `model_call` 的输入 token，不认就改成在 Ollama 那边设 `OLLAMA_CONTEXT_LENGTH`。
- **段号**：提示词里 `[P1]` 起算（和界面上的 01 一致）；payload 里 `paras` 是 0 起算的全书段号，模型给的段号不在本块里的丢掉。同时存 `source_spans`（SPEC 的出处格式），接口两个都给，前端高亮用 `paras`。
- **合并**（`bible/merge.py`，纯函数）：同类、名字或别名规范化后相同（NFKC、去空格和标点、小写）的合并：名字取先出现的，别名取并集，简介取第一个非空的，details 按键先到先得，段号取并集。再和**已采纳版本**逐条比对：名字（其次别名）对上的沿用 id 和原来的主名；几组落到同一个 id 视为用户合并过，再合并一次；冻结的条目原样拷贝，对上它的丢掉；对不上的出新 id（`c-` / `l-` / `p-` / `e-` / `r-` + 12 位）。排序：类别 → 第一次出现的段 → 名字。
- **「可能是同一个」**：同类（人物、地点、道具、事件；关系不比）、名字共享汉字的成对（最多 40 对，共享多的在前），一次 LLM 调用判定（`extract/judge.j2`，任务 `judge`，`max_tokens` 1500），判为同一个的进 `merge_suggestions`。用户点「不是同一个」的对存进 `distinct`，重跑不再问。估价 = 每块一次 + 一次判定（上限，没有相似名字时不判定）。
- **每章摘要**：同一次调用顺带出（≤ 80 字），存在 payload 的 `chapters` 里给分集规划用，接口不返回。
- **编辑**：`PATCH /bible/{id}`（name / aliases / data / frozen，只改带了的字段）；`POST /bible/merge`：`merge`（第一个留下，其余的名字变别名）、`distinct`、`split`（别名独立成条目，带走提到它的段落；原条目留下也提到自己名字的段；两者记为 distinct）。都从**屏幕上的版本**（当前版本）出一个 `edit` 版本并采纳；内容没变不出版本；沿用来源版本的依赖行，所以小说改了以后再编辑仍是待更新。改名不带 aliases 时旧名自动变别名，下次提取还认得出。产物在跑 409 `product_busy`，被锁 409 `product_locked`。
- **`GET /series/{id}/bible` 改成对象**（原契约是数组）：`{product_id, version_id, adopted, source_id, entities, merge_suggestions}`。总是从当前版本的 payload 现算（同一个纯函数），`adopted: false` 时页面标「未采纳」；不读物化表。`bible_entity`（迁移 `0012`）只在采纳时物化：按 id upsert，版本里没了的标 `retired`；有测试：删光后从已采纳版本重建，行完全一样。`frozen` 加进 `DISPLAY_KEYS`（冻结不让下游变旧）。
- **系列级产物自动建**：导入小说后（`NovelService.after_import`）和启动时，给有小说的剧集补上系列级组件的产物（现在只有设定提取）。示例剧集先建 `demo-p-extract` 再导入小说，不然钩子会建一个随机 id 的。
- **Mock**：示例小说按 `tests/fixtures/demo/extract.json` 回答（按块里有的段号裁剪，章节摘要只在一章的第一块出）；其他小说按「出现在两段以上、最常见的三个两字词当人物」。判定按 fixture 写好的对，否则共享两个汉字或互相包含算同一个。示例剧集的设定 v1 用同一套代码从这份 fixture 拼出来（`extract.demo_payload`）；有测试：新剧集导入示例小说真跑一遍（也试了小上下文分成多块），结果和种子除 id 外一样。示例设定比 MSW 原来的多几条（店员、公交站台、旧小票、黑色发圈……），和三章小说对上；周屿的简介从「本集只出现字迹」改成「林晚的旧恋人 · 三年前去了深圳」；示例里有一条合并建议（旧发圈 / 黑色发圈）。
- **测试不再借用示例剧集的 `bible` 槽**：示例剧集有了真实的设定产物，`test_runs_api` 的上游改用 `test_upstream` 槽，`test_products_api`、`test_novel_api` 改用 `episodes`、`suggestions` 槽。

## 2026-10-19 · M2 第 5 步：剧集和导入小说

- **小说也是一个产物**（slot `novel`，组件 `import`）：每次导入追加一个 `origin=import` 的版本并直接采纳。原因：重新导入 = 替换、旧文本留在历史里、下游变「待更新」、闸门锁定，全都复用第 1–3 步的机制，不另造一套。下游按切片 `chapter:<idx>` 依赖它，切片哈希 = 标题 + 各段文字（空行、缩进变了不算改动）。同一份文本再导入不出新版本（返回 `unchanged: true`）；被闸门锁定时 409 `product_locked`（影响范围 `novel_replace` 第 10 步做）。
- **原文放 blob**：`novel_source.sha256` 是规范化后的文本（去 BOM、换行统一成 `\n`，别的不动），所有字符偏移都指向它；`original_sha256` 是上传的原文件。SPEC 4.1 的 `text_path` 不要了。另加 `encoding`、`split_by`、`chars`。
- **章节表存段落偏移**（`para_start`、`paras_json`），比 SPEC 多两列：段号全书连续，存下来以后改了切分规则，旧导入的段号（剧本行、`[P12]` 引用）也不变。
- **切分规则**（`novel/parse.py`）：段落 = 去掉首尾空白（含全角空格）的非空行；标题行 = 不超过 40 字、开头像「第 X 章 / 回 / 节」「Chapter N」「楔子 / 序章 / 尾声 / 番外……」、不以句末标点结尾（「第三节课下课后，他来了。」是正文），.docx 里用了标题样式的段落也算。第一个标题前的文字单独成一章（没有标题）；标题下面没有正文的丢掉（卷名）；整本没有标题时按段落凑成约 6000 字一部分。
- **编码**：有 BOM 按 BOM，否则先试 UTF-8 再试 GB18030；解出来含 NUL（没 BOM 的 UTF-16）算读不了。.docx 用 `python-docx`。上传上限 30 MB。错误码：`unsupported_file` 415、`file_too_large` 413、`novel_unreadable {reason: encoding|docx}`、`novel_empty`、`rights_not_confirmed` 422。
- **接口**：`POST /series/{id}/novel` 是 multipart（`file`、`rights_confirmed`、`dry_run`）。`dry_run` 只返回识别结果（编码、章节），不存、不要求确认改编权，导入弹窗的章节预览用它。`GET /series/{id}/novel?chapter=` 默认第一章，只带这一章的段落；没导入过时返回 200 和 `source: null`（页面显示空状态，不当成错误）。
- **剧集**：`GET /series` 按新建时间倒序；`POST /series {title, ui_lang}` 同时建默认成片规格；slug 取标题里的英文和数字，没有就 `series`，重名加 `-2`；改名不改 slug。
- **前端**：顶栏剧名是菜单（剧集列表 +「新建剧集…」），新建后到成片规格页，规格页已有的「下一步：导入小说」接着走。`/` 进上次看的剧集（记在浏览器里 `stores/ui` 的 `lastSeries`，不在列表里了就进最新的；一个剧集都没有时显示「开始一部剧」）；不在剧集里的页面（环境与安装、模型）的链接也指向它。导入弹窗选好文件就先发一次 `dry_run` 显示识别结果，确认改编权后再发一次真正导入（文件传两次，小说不大，换来不用在前端重写切章规则）。原文按章取，点另一章的补全建议先切章再定位。产物的 slot 契约加 `novel`。
- **剧名菜单不是 modal**（`DropdownMenu modal={false}`）：Radix 的 modal 菜单里打开对话框，关掉后 `body` 会留下 `pointer-events: none`，整页点不动。
- **和 MSW 共存从这一步开始执行**：带剧集 id 的示例 handler（分集列表、补全建议、设定、产物列表）只认示例剧集，别的剧集放行到后端；所以新剧集导入小说后，补全建议和设定两块显示「后端没有这个接口」，到第 6、7 步接上。删了 MSW 的 `GET /series/{id}/novel`；示例数据的段落偏移改从 `test/data/novel.json`（后端导出）取，第 1 段从偏移 8 开始（前面是「第一章　红伞」），补全建议的锚点和剧本行的出处跟着对上。
- **页面测试用 Node 的 FormData / File**（`test/setup.ts`）：jsdom 的和 Node 的 fetch（undici）互不认识，上传会被发成字符串 `"[object FormData]"`。
- **示例剧集**：启动时（Mock）只在库里一个剧集都没有时建示例剧集；示例剧集在的话补上它缺的块（现在是小说：`demo-novel`、`demo-src`、`demo-src-ch1..3`）。`drama-studio demo` 不管有没有别的剧集都建；`--reset` 先删掉示例剧集（规格、产物、版本、小说级联删除；`job`、`model_call` 里的记录留着）。示例小说约 2400 字（计划写的约 3000 字），Kelvin 过目后加长到 3006 字（见「Kelvin 定：手动编辑和自动同步」）。

## 2026-10-19 · M2 第 4 步：预算和确认

- **入队前查一次，调用前再查一次**（`modelhub/budget.py`）：入队时用整个任务的预估比单次上限（解析结果的 `per_call_cap_usd`）和本集剩余，超了任务直接进 `waiting_confirm`，原因写在任务参数 `confirm: {reason: per_call|episode|fallback, estimate_usd, limit_usd}`。每次模型调用前路由器的守卫再查：确认过的任务最多花到确认的金额（已花 + 这次预估），没确认的单次调用不能超过单次上限；超了抛 `budget_exceeded`，不兜底，一分钱不花。所以确认之后主用模型出错、兜底模型更贵时任务失败，而不是悄悄多花。
- **本集剩余** = 预算 − 已花 − 排队 / 等确认任务的预估 − 运行中任务还没花完的预估（预估 − 已花，不小于 0），不重复算。设定提取、补全、分集规划不属于某一集，只查单次上限。分集表在第 8 步才有，所以本集预算的读取是注入的（`Budget.episode_budget`），现在为空。
- **任务表加两列**（迁移 `0010`）：`episode_id`（花费算在哪一集）、`confirmed_usd`（确认时记下当时的预估，重启续跑不再问）。
- **兜底前先问**（`notify: ask`）：路由器在要兜底时抛 `NeedsConfirm`（只对有任务的调用），处理器抛 `JobNeedsConfirm`，队列把任务放回 `waiting_confirm`、合并新参数（兜底模型、原因、预估）、这次不算尝试次数；确认后按兜底模型重跑，记为兜底（`model_call.is_fallback`、版本 `origin=fallback`），并且不再往下兜底（仍是一跳）。
- **前端**：外壳里常驻 `ConfirmJobs`，读真实 `/jobs` 里第一个等确认的 `product.run`，弹窗说明原因、预计花费和上限，「确认，开始运行」走已有的 `POST /jobs/{id}/confirm`、「取消这次运行」走 `cancel`；弹窗不能点外面关掉。产物的 `running` 多一个 `state`，RunBar 显示「等你确认 · 模型」。小于 $0.01 的预估显示四位小数（`lib/format.ts:formatCost`）。安装任务也会进 `waiting_confirm`，但它们有自己的确认界面，这个弹窗不管。
- **同步的改写建议**（剧本行 / 场、补全建议的重写，第 7、9 步）还没有接口；到时超过单次上限返回 409 `over_budget {estimate_usd, limit_usd}`，前端确认后带 `confirm_budget: true` 再发，调用时把预估放进 `CallContext.confirmed_usd`（守卫已支持）。文案已加。

## 2026-10-19 · M2 第 3 步：组件框架、提示词、Mock 应答器

- **迁移编号顺延**：`0009` 是新表 `llm_cache`（计划里 `0009` 写的是第 4 步的 `job.confirmed_usd`），之后各步的迁移号都加一。
- **组件**（`pipeline/component.py`）：`inputs()` 返回标题数据块 + 读了哪些上游切片；默认 `run()` 一次调用：编译层作 system、数据块作 user，`json_mode`，Pydantic 校验；不过就把模型的回答和错误（`prompts/templates/_shared/fix_json.j2`）追加进对话再问一次，换模型兜底后重试留在答出来的那个模型上；第二次还不过任务失败 `invalid_output`，原始回答存 blob，`error.params.raw` 是它的哈希。多次调用的组件（长小说分块）自己覆盖 `run()`，用 `call_json()`。
- **校验通过的回答按请求缓存**（`llm_cache`，键 = 模型 + 消息 + 种子 + max_tokens + 输出结构）：任务重试或重启续跑不重复花钱；重跑换了种子，不会命中。命中不写 `model_call`（没有调用）。
- **提示词**：`prompts/compiler.py` 用 Jinja2（`StrictUndefined`），`templates/<component>/<family>.j2`，`family` = 模型 key 的前缀，找不到用 `default.j2`；默认意图层在 `intent.<lang>.txt`，按剧集的 `ui_lang`。实际发出的全文存 blob，作为版本的 `files[]`（role `prompt`），不算进 `content_hash`。模板随包发布（`pyproject.toml` 的 package-data）。
- **一次运行的提示词**：开始运行时写回产物（PromptEditor 下次显示的就是它），并复制进任务参数，排队期间改提示词不影响这一次。「重跑」沿用手改的编译层；带新意图或「不满意换一个」都按目标模型重新编译（和 M0.5 的约定一致）。「换一个」取 `alt_order` 里屏幕上那一版所用模型的下一个（到头绕回）。
- **队列**：本地模型进 `gpu`，API 进 `api:<provider_id>`；路由器报的可重试错误（429、5xx）交给队列按 `max_attempts` 重试，其余直接失败。
- **产物状态读时算**：有排队 / 等确认 / 运行中的任务 → queued / running（从 `job` 表读，取消了的排队任务不会卡住）；上次失败 → failed；然后 stale（`pipeline/invalidation.py` 现算）、locked、adopted、ready、empty。`running` 里的模型取任务参数。
- **Mock**：`ModelRequest.meta = {component, task}` 不发给厂商；组件的应答器经 `Registry.add_mock_responder()` 登记（`modelhub` 不依赖 `pipeline`）；`MockSettings.bad_json = N` 让接下来 N 次 JSON 回答坏掉，测重试。
- **流式**：写作类调用带 `stream: true`，增量按字数每秒最多一次推 `job.updated` 的 `progress: {chars}`；RunBar 显示「已生成 N 字」等第 6 步有真组件时再接。
- **提示**：成功推 `toast` `version_created {n, model}`（model 是显示名），失败推 `run_failed {error}`；新错误码 `component_not_ready`、`component_off`、`no_alternative`、`invalid_output` 等两种语言都有文案。

## 2026-10-19 · M2 第 2 步：配置接口

- **预设在后端现算**：`core/config.py:preset_settings()` 照搬原型 `presetCfg()`（质量 / 均衡 / 省钱 / 全本地，全本地下没有本地版本的组件 `mode: off`，路由器调用它报 `component_off`）。当前预设和兜底方式存新表 `app_setting`（键 `config.defaults`，迁移 `0008`），`resolve()` 多一个 `defaults` 参数。来源层 `factory` 改名 `preset`，和前端契约一致；解析结果里 `fallback.local_timeout_s` 改名 `timeout_s`（YAML 的键不变）。
- **「不满意换一个」的默认顺序**：YAML 没写 `alt_order` 的组件按原型规则排：兜底目标第一，然后本地、API（去掉主用的）。M0 的规则是「API 里除了主用的」。所以 Mac 上能力过滤会从顺序里拿掉本地模型（`test_capabilities` 跟着改）。
- **单次花费上限进 `components.yaml`**：顶层默认 `per_call_cap_usd: 0.50`，各组件的值取自原型各页 Inspector（设定提取 $0.2、剧本化 $0.8、视频 $2……）；没有 API 模型的组件为 null。写作类组件的默认兜底条件不含 `qa_fail`（文本没有自动质检），界面上仍可以勾。
- **「音效」组件 `sfx` 现在就进 `components.yaml`**（M0.5 说 M7 再加）：组件目录改由后端给，后期页的 Inspector 要用它；`providers.yaml` 补 `elevenlabs/sfx`、`local/mmaudio`（`verify: true`，没有价格）。模型页的表格因此是 20 行（多了 `dub` 和 `sfx`，原来示例里没有 `dub`）。
- **媒体组件的路由以 YAML 为准**：原来 MSW 照原型页面写的几条（配音 API + IndexTTS2、配乐 API、口型 API、精修兜底到 H3 2K）和 YAML 不一样，现在素材、生成、后期页的 Inspector 显示 YAML 的值；到 M3 / M5 / M7 做这些组件时再定。
- **组件目录**：`custom`（自定义 OpenAI 兼容模型）先不列，等自定义模型接口；媒体价格换成界面的单位（按分钟的换成每秒，按分辨率的取草稿档，订阅制和按 token 的辅助模型不显示）；本地模型没有价格。`unavailable` 只给机器原因（`machine_cuda`、`machine_missing {count}`，新文案两种语言），「没有本地 / API 版本」前端自己推。`local_runtime_ok` = 没扫描过或扫描找到了 ComfyUI。
- **`/config/resolve` 按本机能力过滤**（和路由器、兼容表一样），界面看到的就是真会跑的路由。`PUT /config/override` 按顶层字段合并进已有的覆盖；`project` 层存成不带组件（对所有组件生效）；模型 key 不认识返回 422 `unknown_model`。
- **MSW**：删 `handlers/config.ts` 和 `fixtures/demo/config.ts`；剩下的示例 handler 用 `mocks/route.ts:demoRoute()` 读真实的 `/config/resolve`。页面测试的假后端 `test/fakes/config.ts` 读 `test/data/config.json`（目录 + 四个预设下每个组件的预设层，由 `tests/api/test_web_fixtures.py` 生成，`DRAMA_UPDATE_FIXTURES=1` 更新）。

## 2026-10-19 · M2 第 1 步：产物和版本

- **`dependency` 挂在版本上**：比 SPEC 4.2 多 `version_id` 和 `slice` 两列，一个版本读了上游哪几片就写几行（SPEC 只写了 `product_id`，但同一产物的不同版本依赖的上游不同）。`product_version` 现在就带上 6.4.5 的 `workflow_id`、`workflow_sha256`、`comfy_env_hash`（可空），M5 不用再迁移。
- **产物的 `status` 只存运行状态**（empty / queued / running / ready / failed），locked / adopted 读的时候按 `locked_hash`、`adopted_version_id` 推出（`pipeline/products.py:status_of`）；stale 第 3 步现算。原因：同一事实不存两份。
- **自动采纳只在第一次**：`append(adopt=None)` 只有还没采纳过时才采纳；用户手改出的版本 `adopt=True`。被闸门锁定的产物照样能出新版本，但不能采纳（409 `product_locked`）。
- **事件只带 id**：`version.created` = `{product_id, version_id, n, origin}`，`product.updated` = `{product_id, series_id, status}`。原来的契约要带整个版本，剧本、设定的 payload 很大，每条都要存进 `event` 表；前端本来就只用这两个事件来刷新缓存，没有读内容。前端 zod 和 MSW 一起改。
- **流水线的错误用 `PipelineError(status, code, **params)`**，app 里统一转成和 `ApiError` 一样的 `{detail: {code, params}}`；服务层不依赖 FastAPI，任务处理器里也能用。

## 2026-10-19 · M2 计划（Kelvin 已定）

- **示例小说补写到 3 章**（约 3000 字）：第 1 章开头就是原型里的 5 段，第 2、3 章对应《十二点》《旧发圈》；另出一份 .docx 测导入。原因：原来只有 180 字，分不出 3 集，也演示不了拖节拍换集。Kelvin 过目后定稿。
- **节拍看板放剧本页「分集」区**：加「卡片 / 节拍看板」切换；看板一列一集，节拍卡可拖到别的集，上面一条全剧情绪曲线。原型里没有这一块，做完截图给 Kelvin 审。
- **新建剧集的入口是顶栏剧名菜单**：剧集列表 +「新建剧集…」；新建后先到成片规格页（SPEC 16.1「新建剧集时必经」），再到小说页导入；打开 `/` 时进上次看的剧集。
- **重新导入小说 = 替换**：旧文本留在历史里；设定、补全、分集、剧本都变「待更新」；已确认过的先弹影响范围，三个选项照常。
- 工程上的设计（版本是唯一真相、物化表、id 在出版本时定、只有第一次成功才自动采纳、建议的决定单独一张表、按切片算依赖哈希且「待更新」现算、Mock 应答器、预算算法、和 MSW 共存的规则）见 `plans/M2.md`「设计要点」，各步做完时再按实际情况补记。

## 2026-10-19 · M1 第 8c 步（4/4 后半）：回滚后核对

- **回滚只是排上**：ComfyUI-Manager 下次启动 ComfyUI 时才执行，而且会半途失败（2026-10-18 第一次就是）。所以「回滚」按钮不再马上记 `restored_at`，而是记请求时间和当时的环境哈希，状态 `pending`。
- **下一次扫描核对**（识别完 ComfyUI 之后），按顺序判断：
  1. 现在的 ComfyUI 和快照时的一致 → `done`，记 `restored_at`。快照后什么都没改过时，回滚本来就是空操作，也算这一种；示例机器的环境不会变，所以示例里重新检测就会显示「已回滚」。
  2. 和请求时的环境哈希相同 → 还没重启 ComfyUI，继续 `pending`。
  3. 都不是 → `incomplete`，列出差异：ComfyUI 的 commit（没有就比版本），多出的、少了的、版本不同的节点包。
- **只比 Manager 会恢复的东西**：ComfyUI 和节点包。不比 Python、PyTorch，因为 Manager 不降级 pip 包，比了会永远「没完成」。节点包按名字比 commit（没有就比版本），不比加载出的节点类：ComfyUI 没在跑时读不到节点类。
- **迁移 `0006`**：`comfy_snapshot` 加 `restore_requested_at`、`restore_from_hash`、`restore_state`、`restore_diff_json`。之前的回滚记录标成 `unchecked`（界面写「回滚过（当时没有核对）」），`restored_at` 清空。
  - 原因：Kelvin 回滚之后又装回了 VHS、FlashVSR，现在的环境和快照本来就不一样，拿来比会误报「没完成」。
- **接口**：`ComfySnapshot` 加 `restore: {state, requested_at, diff}`；`restored_at` 的意思改成「核对通过的时间」。核对结果写日志 `restore_done` / `restore_incomplete`。

## 2026-10-19 · M1 第 8c 步（4/4 前半）：安装位置在程序目录里时提示

- 档案加 `app_dir`（程序所在的文件夹：真实机器是仓库根目录 `REPO_ROOT`，示例机器读夹具），扫描时和 `default_dir` 一起写。
- 「安装位置」等于它或在它下面时，输入框下面的说明换成黄色警告，提示会让程序文件夹变大、更新或重装时可能被一起删掉。比较时统一斜杠，Windows 盘符路径不分大小写（和 `pathutil.norm` 一致）。
- 只提示，不拦：确实想放那里也能装。开始安装时日志多一行 `dir_in_app` 警告。
- 原因：2026-10-18 真装时安装位置填成了仓库目录，IndexTTS 下进了仓库。

## 2026-10-19 · M1 第 8c 步（3/4）：安装页显示进度和预计用时

- **放在哪**（原型里没有，截图见 `reports/ui/setup-installing.light.jpg`、`setup-confirm.light.jpg`）：
  - 安装按钮那一排写「约 N GB，预计 M 分钟」，跟着勾选实时变；鼠标悬停显示「按这台机器测到的下载速度 X MB/s 估算」。
  - 确认弹窗底部写这次安装的合计。
  - 下载中的项：进度条下面两行小字，「已下 / 总大小」和「速度 · 剩 M 分钟」；算 sha256 时第二行换成「校验中…」。行内百分比取整（后端给一位小数）。
  - 汇总条在「正在安装…」后面写「剩余约 M 分钟」。
- **没测过速度**：只写体积，加一句「还没测过下载速度，算不出用时」；安装中算不出剩余时间就不显示。
- **整体进度按用时加权**：每项的权重 = 下载量 ÷ 测到的速度 + `work_s`（从没测过就按 20 MB/s 算权重）。剩余时间：正在下的项用它自己的 `eta_s`，排队的下载项按正在下的那项的实时速度，没有就按 `download_bps`。
- **大小用十进制 GB / MB**（`useUnits`）：和清单的 `size_gb`、Hugging Face 页面、改动清单里的「约 49.3 GB」一致。`lib/format.ts:formatBytes` 是二进制单位，素材页继续用它。

## 2026-10-19 · M1 第 8c 步（2/4）：预估用的数

- **档案存 `download_bps`**（这台机器的下载速度，字节/秒），`GET /setup/profile` 返回。
  - 装完一项、而且它有下载时，记这一项的平均速度：只算收数据的时间，不算校验。
  - 还没有时，扫描最后测一小段：清单里第一个权重文件的前 16 MB，从「自动」镜像会选的站点下，只放在内存里，所以扫描仍然只读。
  - 测不到就留空，前端只写体积。已经有了就不再测，重新扫描也不测。
- **每项给两个数**：`size_bytes`（清单的 `size_gb`）和 `work_s`。`work_s` 是下载以外步骤的经验用时（`installer.STEP_SECONDS`）：clone 20 s、pip 60 s、包管理器 60 s、建 venv 10 s、脚本 30 s、复制 5 s。
- **整体进度、剩余时间和开始前的预估都由前端算**，后端只给上面这些数和每项的实时字节。
  - 原因：勾选哪些项是在页面上改的，预估得跟着勾选实时变；整体进度条本来就在前端算（`overallPct`）。放在一处，两边不会算得不一样。
- **示例机器**：扫描测速读夹具（PC 22 MB/s、Mac 12 MB/s）；示例安装的权重项按 25 MB/s 报字节，最后报一下「校验中」。

## 2026-10-19 · M1 第 8c 步（1/4）：下载按字节报进度、分块多连接

- **新模块 `setup/download.py`**，`steps.py` 的下载改用它。
- **分块**：文件按 64 MB 分块写进 `.part`。每个连接从一个空闲块开头一直流到文件尾，到下一块时认领，下一块已被别的连接占了就停。新连接从最长的空闲段开始；这段前面紧挨着一个正在下的块时，从段的中间开始（IDM 式动态分段）。
  - 原因：每块单独请求，49 GB 要多出约 770 次 Hugging Face 跳转；单连接时也没必要断开重连。
- **续传**：`<name>.part.json` 记下完成的块，续传和单块重试都靠它；记录里的大小或块大小对不上就从头下。老的单连接 `.part`（没有记录）开头的整块算下完。
- **不支持 Range**：探测请求 `Range: bytes=0-0` 回 200，就单连接从头下。
- **重试**：一个块连续失败 3 次（之间等 1 s、2 s）整项失败；完成的块留着，重试从断点接着下。
- **连接数自适应（`Tuner`）**：从 1 个开始，每 5 秒看一次总速度；比之前最好的快 10 % 以上就再加一个（最多 8 个），否则退回一个并固定。一次安装里共用，后面的文件直接用找到的连接数。
- **Windows 上 `.part` 设成稀疏文件**（`FSCTL_SET_SPARSE`）：不然在文件中间写，NTFS 会先把前面全部补零。设置失败不影响下载。
- **按字节计量（`Meter`）**：一项所有文件合计的已下载 / 总大小；速度取最近 5 秒；每秒最多报一次；算 sha256 时报「校验中」。
  - 第一步开始前先探测这一项所有文件的大小，总数从一开始就准。
  - `ItemInstall` 加 `bytes_done`、`bytes_total`、`speed`（字节/秒）、`eta_s`、`verifying`。
  - `pct` 保留一位小数；有下载的项按字节算，封顶 99，装完才是 100。
- **真实网络手动核对**（Hugging Face，Xet 存储的跳转）：探测拿到了大小和 Range 支持；用 4 个连接下 gpt2 的 `tokenizer.json`，sha256 一致；H3 音频 VAE 的前 16 MB 测出 41 MB/s。

## 2026-10-18 · M1 第 8b 步：Kelvin 5090 上真装的结果和修复

- **装了什么**（`DRAMA_SETUP=real`，ComfyUI Desktop 0.41.2 开着）：
  - VHS、FlashVSR：在锁定的 commit 上（`4d907be`、`8877fdd`）。
  - 四项权重：H3 49.3 GB、Qwen3-VL-32B 文本编码器 15.7 GB、SeedVR2 7B 8.8 GB、IndexTTS-2.5 5.5 GB，全部下完、sha256 都对。
  - 装前自动存了快照，改动清单 6 项。下载单连接实测 18–30 MB/s，共约 79 GB，一小时左右。
  - 重新检测：通过 21、可选 6、缺少 3（DramaStudio 节点包没发布；Qwen-Image-Edit 这次不装；SageAttention 见下）。
- **SageAttention 报「完成」却检测不到**：PyPI 的 `sageattention` 1.0.6 装上了，但它要 `triton`，Windows 上没有，一导入就报错；安装器只看 `uv pip` 的返回码。
  - 改 1：装完再问一次检测器，只对 `py_import`、`file`、`downloads` 三类（装完马上就能看到）；还检测不到就报 `not_detected`。ComfyUI 在跑时看到的节点和版本要重启后才变；包管理器改的 PATH 只对新进程生效，所以这两类不复检。
  - 改 2：Windows 上改装 woct0rdho 的预编译包 `sageattention 2.2.0+cu130torch2.10.0andhigher.post6`（abi3，Python ≥ 3.10），加上 `triton-windows`。
    - triton-windows 的版本要和 PyTorch 自己锁的 triton 一致（`pytorch/.ci/docker/triton_version.txt`：2.12、2.13 → 3.7.1，2.14 → 3.8.0）。
    - 清单新字段 `by_torch`：键是 `<major.minor>+<cuda>`，装的时候问 ComfyUI 的 Python 现在是哪个 PyTorch（同一次安装里可能刚升级过），表里没有就报 `torch_unsupported`。
  - 新装法在 Kelvin 机器上装好：torch 2.12.1+cu130、triton-windows 3.7.1、sageattention 2.2.0；装完复检通过。
    在 5090（sm_120）上跑了一次 1×8×1024×64 的注意力，和 PyTorch SDPA 的余弦相似度 0.99927（量化注意力，正常）。
    FlashVSR 启动时认到了它。ComfyUI 自己的模型要用它，得加启动参数 `--use-sage-attention`：Kelvin 同意开，改在 Desktop 的 `installations.json`（`launchArgs`），Desktop 完全退出后再改，不然会被它写回。2026-10-19 已开：argv 带上了参数，日志「Using sage attention」。
- **安装位置填成了仓库目录**（`C:\dev\drama-studio`，页面默认是 `C:\Users\kelvin\DramaStudio`），IndexTTS 下进了仓库。
  - 已挪到默认位置；用默认位置重新装时，安装器检测到文件已在，记成「已经装好了」，没有重下。
  - 安装位置在程序目录里时要提示，加进第 8c 步。
- **回滚：ComfyUI-Manager 4.2.2 在 Windows 上会半途失败**。
  - 原因：Manager 回滚时用 `shutil.move` 把快照里没有的节点包挪进 `custom_nodes\.disabled`。这个文件夹不存在时改名失败，Python 改成先复制再删除；git 的 pack 文件是只读的，删除报「拒绝访问」，回滚中止，留下一份复制品，其余节点包都没处理。
  - 修复：触发回滚前先建好 `.disabled`（`snapshots.prepare_restore`），这样就是同盘改名。
  - 第二次回滚成功：VHS、FlashVSR 停用，节点不再加载。删掉了第一次留下的复制品；之后用安装器装回去了（全新 clone，装前又存了快照）。
  - 已知限制：
    - 回滚不卸载快照之后多出来的 pip 包（Manager 只补齐快照里有的）。
    - 停用的节点包留在 `.disabled` 里。
    - 平台在「排上回滚」时就记 `restored_at`，没核对是否真的生效（第一次失败了也显示「已安排回滚」）。ComfyUI 重启后要核对环境和快照是否一致，加进第 8c 步。
- **git checkout 加 `-c advice.detachedHead=false`**：锁定 commit 就是 detached HEAD，git 那十几行提示只会占满安装日志。

## 2026-10-18 · M1 第 8b 步：权重版本、SeedVR2 改用 ComfyUI 自带节点、权重放哪

- **Kelvin 选定的版本**（候选、大小、来源在 8b 列给他挑）：
  - 图像编辑：Qwen-Image-Edit-2511 int8_convrot（Comfy-Org 重打包），按官方模板 `image_qwen_image_edit_2511_int8` 配齐：Qwen2.5-VL-7B fp8 文本编码器、VAE、Lightning 4 步 LoRA，共 31.0 GB。
    - 没选 2026-10-13 新出的 Qwen-Image 2.1（7B，生成和编辑一体，最多 10 张参考图）：太新，P0 时可以再比。
  - SeedVR2：用 ComfyUI 自带节点（`comfy_extras/nodes_seedvr.py`，v0.28.0 起，在各 tag 源码上二分查的），权重用 Comfy-Org/SeedVR2 的 7B int8_convrot 和 VAE，共 8.8 GB。
    - 改了第 8 步：不再装社区节点包 numz。`node_seedvr2` 和 H3 一样算「ComfyUI 自带」，不再是安装项。
  - 配音：IndexTTS-2.5（IndexTeam 2026-08 发布，比 2 快，多了语速控制），5.5 GB。
    - 运行环境等配音那个里程碑再装：index-tts 源码、Python 3.10–3.11 的 uv 环境、运行时自动下载的辅助模型。
- **这次真装不装 Qwen-Image-Edit**（Kelvin 2026-10-18：不是必要的，用到再装）。清单里保留这一项和锁定的版本，以后在「环境与安装」勾上就能装；没装时关键帧按能力过滤走 API。
- **H3 全套按官方模板补了两个加速 LoRA**：`video_minimax_h3_i2v` / `r2v` 默认引用，各 1.96 GB；Comfy-Org 仓库里的和 lightx2v 原仓库的 sha256 一致。
  - H3 合计 49.3 GB，文本编码器 15.7 GB，五项权重共约 110 GB。
- **权重锁 revision**：每个 Hugging Face 仓库锁 commit，改动清单显示前 7 位。
  - 文件大小和 sha256 取自 HF 接口 `/api/models/<repo>/tree/<rev>`。
  - 不走 LFS 的小文件（IndexTTS 的配置、分词表）HF 不给 sha256，靠锁定的 revision。
- **ComfyUI 用的权重放哪**：照 ComfyUI 自己的规则。
  - `extra_model_paths` 里写了 `is_default: true` 的那组目录排在最前，新文件放那里。ComfyUI Desktop 给每个安装写的 `instance-model-paths/<id>.yaml` 就是这样指向共享目录 `ComfyUI-Shared\models` 的；没有这样的目录就放 `{comfy}/models/<类别>`。
  - 清单里 download 的文件写 `folder:`（diffusion_models、vae、loras、text_encoders），表示放进 ComfyUI 的这一类目录；`ModelDir` 加 `default`；安装时用扫描时存下的模型目录。
  - 不写死 Desktop 的路径：用户自己配了别的默认目录也一样对。本机只读扫描核对过：13 个文件都落在 `C:\Users\kelvin\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\<类别>`（`scripts/setup_scan_real.py` 新加了「weights would go to」一段）。
- **新检测类型 `downloads`**：这一项下载步骤里的文件都在才算装好，和安装用同一份文件清单。
  - ComfyUI 的文件在它任一模型目录里（含 extra_model_paths）都算。
  - 原来的 `file` 只看一个文件、只看 `{comfy}/models`，认不出 Desktop 共享目录里的。
- **往 ComfyUI 模型目录放文件算改动 ComfyUI**（SPEC 12.2-6）：这类权重进改动清单、默认不勾、动手前先存快照。
  - Manager 的快照不含模型文件，回滚也不会删已下载的权重；为了规则统一，照样先存。
  - IndexTTS 不进 ComfyUI，默认勾上。
- **不走 ComfyUI 的权重放「安装位置」**（Setup 页的 `dir`，即 `{models}`）：IndexTTS 在 `{models}/IndexTTS-2.5`。
- **DramaStudio 节点包** `installable: false`，提示「还没发布：随 ComfyUI 对接一起提供」（源码 M5 才有）。
- **下载日志**每个文件多一行 `download`（文件 → 目标路径），真装时能看到每个文件落在哪。
- **影响（Mock 的示例 PC）**：能装的变成 11 项，默认勾 FFmpeg 和 IndexTTS-2.5；全部装完后导航徽标是「缺 3 项」（H3、SeedVR2 节点要新版 ComfyUI，我们自己的节点包还没发布）。

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

# 删掉潜空间放大节点包之后的体检（2026-10-27）

第三轮对比（`run3-workflows/`）为 SEED HUNTER 的完整版在本机 ComfyUI 装过一个第三方节点包；SEED HUNTER Kelvin 认为效果不好，不用了，所以删掉（Kelvin 2026-10-27 定）。

## 做了什么

1. **先存快照**：ComfyUI-Manager `POST /v2/snapshot/save` → `2026-10-27_22-26-40_snapshot`（含删之前的全部节点包和 pip 包，要恢复就在 Manager 里选它）。当时队列是空的。
2. **删掉**：
   - 节点包 `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\Comfyui_Minimax_h3_latent_Upscaler`（LBH-123-AI，40316cf0，2026-10-27 装的）；
   - 模型 `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models\latent_upscale_models\minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors`（690 MB）。
   `custom_nodes` 里剩 `ComfyUI-FlashVSR`、`ComfyUI-VideoHelperSuite`，和装之前一样。
3. **重启 ComfyUI**（Manager `POST /v2/manager/reboot`，15 秒回来，启动参数没变）；`GET /object_info/MinimaxH3LatentUpscaler3D` 返回空，节点已经没了。
4. **体检全部已登记的工作流**：Kelvin 的工作台库里登记了 7 个（都是仓库自带的，没有导入的社区工作流）。用工作流库自己的「全部体检」（`POST /api/v1/workflows/check-all`，真实机器、临时数据目录，不动 Kelvin 的库；只读 `/object_info` 和 Manager 的节点表，不跑任务）。

## 体检结果：7 个都正常

| 工作流 | 模型 | 结果 | 节点 | 缺的节点包 | 缺的模型 |
|---|---|---|---|---|---|
| `flux3-klein` | `comfy/flux3-klein` | 正常 | 16 / 16 | 无 | 无 |
| `flux3-klein-t2i` | `comfy/flux3-klein-t2i` | 正常 | 12 / 12 | 无 | 无 |
| `h3-i2v` | `comfy/h3` | 正常 | 19 / 19 | 无 | 无 |
| `h3-r2v` | `comfy/h3-r2v` | 正常 | 18 / 18 | 无 | 无 |
| `qwen-image` | `comfy/qwen-image` | 正常 | 10 / 10 | 无 | 无 |
| `qwen-image-edit` | `comfy/qwen-image-edit` | 正常 | 14 / 14 | 无 | 无 |
| `qwen-image-edit-hq` | `comfy/qwen-image-edit-hq` | 正常 | 13 / 13 | 无 | 无 |

没有一个用到被删的节点，删之前也没有（这个包只在第三轮的临时对比脚本里用过，没登记进工作台）。

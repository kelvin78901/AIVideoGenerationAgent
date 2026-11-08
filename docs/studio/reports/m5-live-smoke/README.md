# M5 真实冒烟（第 15 步，2026-11-08）

命令（用 `local_video.py --keep` 留下的数据目录；Kelvin 同意，上限 $3，Seedance 按 720p）：

```
DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/live_video.py --home <数据目录>\home --cap 3 --only h3,regen,seedance
```

第一轮（上午）：select 过（$0.0048）；h3 因上行慢、建任务重发、音色样本太短失败（没扣钱）→ 第 15a、15b 步。

第二轮（本报告 `report-run2.txt`），共花 **$1.16**：

| 步骤 | 结果 | 耗时 | 花费 |
|---|---|---|---|
| h3：1-04 原生同步 → `minimax/h3-api` | 成功，1440×2560，4.18 s，有声音；林晚音色样本由 0.87 s 的锚点和同一音色的下一段拼成 4.0 s 送出（15b） | 292 s | $0.48（含 Context-IR） |
| regen：1-04 本机草稿 `faae4efb` → Regenerate-2K | 成功，1440×2560，4.88 s，和草稿逐帧对得上（`1-04-local-draft-vs-regen-2k.jpg`：上排本机 768P 草稿，下排 2K） | 141 s | $0.21 |
| seedance：1-01 → `volc/seedance-2.5` 720p | **没跑成**：火山方舟账号没开通 `doubao-seedance-2-5-260628`（ModelNotOpen）；路由兜底到 `minimax/h3-api` 出了一条（`1-01-h3-api-fallback.jpg`），脚本按「没走到 Seedance」判停 | 201 s | $0.46（兜底那条） |

- 1-04 镜头只要 1.66 s，H3 API 最短 4 s，按 4 s 计费。
- 建任务没有重发：MiniMax 这轮每步只建了一个任务。
- 片子在临时目录（没进仓库）：`C:\Users\kelvin\AppData\Local\Temp\drama-local-video-z2icdq70\live-out\`。

Seedance：开通要交保证金，Kelvin 2026-11-08 定先不管；以后开通了再跑 `--only seedance`。

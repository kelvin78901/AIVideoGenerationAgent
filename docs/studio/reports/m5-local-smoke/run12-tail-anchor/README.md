# 第十二轮：尾段引导加末帧锚点（第 15h 步，2026-11-09，Kelvin 定试这个）

第十一轮发现连续镜头的切点跳（尾段引导往后会漂）。这里在尾段引导后面再串一个官方 `MiniMaxH3AddGuide`，把上一镜的最后一帧钉在第 21 帧（尾段的最后一帧），裁掉 22 帧后这条片子就从上一镜真正的结尾接着演。

```
DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/tail_anchor.py --home <第十一轮的数据目录> [--label 1-08]
```

在第十一轮数据的副本上出 1-08 一条，种子、输入和第十一轮第 1 条一样，图在本进程里改（产品没动）；259 秒。

| | 引导段第 0 / 5 / 10 / 15 / 21 帧 和上一镜尾段比 | 切点（1-06 末帧 → 1-08 首帧） |
|---|---|---|
| 第十一轮（只有尾段） | 35.0 / 29.8 / 23.6 / 21.2 / 20.4 dB | **20.3 dB** |
| 加末帧锚点 | 35.2 / 33.1 / 31.5 / 33.2 / 36.8 dB | **36.5 dB** |

- `cut-1-08.jpg`：左 1-06 最后一帧、中 第十一轮 1-08 第一帧（头转了、姿势变了）、右 加锚点后的第一帧（接上了）。
- `sheet-anchored-1-08.jpg`：动作没被锚点卡住：转身拉开门、关上、扶着门把停住、再拉开；开头约半秒先站着不动。`sheet-run11-1-08.jpg` 是对照。
- 片子（不进 git）：`../originals/run12-tail-anchor/anchored-1-08.mp4`、`run11-1-08.mp4`，图 `graph.json`。

## 做进产品（第 15h 步）

两个 H3 工作流（`h3-i2v`、`h3-r2v`）在 `Tail guide` 后面加 `Tail end`（`MiniMaxH3AddGuide`，`frame_idx` 21 = `TAIL_FRAMES - 1`），图读首帧那个 LoadImage（连续镜头的首帧就是上一镜最后一帧），不加新槽位；没给尾段时和尾段一起旁路。`h3-i2v` 给了尾段时去掉 I2V 的首帧锚，首帧的 LoadImage 留着给 `Tail end` 读。

## 产品原样核对（同一天，改完工作流之后）

```
DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/local_video.py --only episode --home <第十一轮的数据目录> --from 1-08 --to 1-08 --run run12-tail-anchor
```

不打补丁，用仓库里的 `h3-i2v`（带 `Tail end`）出 1-08 两条（改写、看图走缓存）：切点 **37.1 / 37.1 dB**，开头两帧 45.7 / 50.7 dB（裁头不再复制第一帧）。每条 293–298 秒，比第十一轮的 250 秒长；补丁版那条是 259 秒，所以多出来的不全是锚点造成的，没细查。拼图 `sheet-1-08-*.jpg`，报告 `report-from-1-08.txt`。

# P3 替换图与成片重排联动检查点

日期：2026-08-12

## 本次完成

- 图片工作台在有已完成替换图时，新增“用新图重排成片”入口。
- 该入口复用现有 `rerun_stage(image)` 机制，只重排 image 下游阶段，不重跑采集、逐字稿和改写。
- render 阶段读取 `image_index` 后，会优先应用最新完成的镜头替换图，再生成时间轴与成片。
- 替换图版本与旧图并存，历史成片不被直接覆盖，只有显式重排后才采用新图。

## 自动回归

- `npm.cmd run build`（`web/`）：通过。
- `python -m compileall -q .`（`worker/`）：通过。
- `python -m unittest tests.test_p0_reliability tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal -v`：11 项通过。
- `git diff --check`：通过。
- 未执行真实替换图 -> render 远程链路冒烟；当前为本地代码契约验证。
- 本机 Node 为 v22.19.0，项目期望 Node 20.x。

## 剩余边界

- 目前仍是整段下游重排，不是只局部替换单镜头视频片段。
- 替换图完成后的自动提醒和批量重排策略仍可继续优化。

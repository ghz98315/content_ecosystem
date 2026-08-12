# Edge 默认音色明确化 checkpoint

更新时间：2026-08-12

## 已完成

- 采集工作台默认音色从模糊的“系统默认 Edge 音色”改为“Edge · 晓晓（系统默认）”。
- 同时显示实际 Voice ID：`zh-CN-XiaoxiaoNeural`。
- 任务详情的配音快照在未选择自定义档案时也显示同一 Voice ID。
- Worker 默认配置与 `worker/tts_voices.json` 已确认均指向晓晓，无需数据库迁移。

## 验证

- `npm.cmd run build`（`web`）：通过。
- `git diff --check`：通过，仅有既有换行格式提示。

## 线上操作

Vercel 部署完成后刷新 `/video-collection`，默认项应显示为 Edge · 晓晓；无需重新创建已有音色档案。

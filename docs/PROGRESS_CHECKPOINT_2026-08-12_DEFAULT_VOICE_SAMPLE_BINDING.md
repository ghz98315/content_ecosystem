# 默认音色样本关联 checkpoint

更新时间：2026-08-12

## 已完成

- 默认项统一显示为“晓晓 · edge-tts（系统默认）”。
- 默认选择会查找已启用的 `zh-CN-XiaoxiaoNeural` 音色档案，并自动加载其已上传样本试听。
- 晓晓档案不会再在普通可选列表中重复显示。
- 其他音色选项统一显示“名称 · 模型”，Provider 仅在模型缺失时作为回退显示。
- 默认 Edge 任务现在也明确快照 `edge / edge-tts / zh-CN-XiaoxiaoNeural`，不会受 Worker 的全局 CosyVoice 默认值影响。

## 验证

- `npm.cmd run build`（`web`）：通过。
- `git diff --check`：通过，仅有既有换行格式提示。

## 线上检查

部署后刷新 `/video-collection`：默认晓晓应显示样本播放器；如未显示，确认晓晓档案已启用、Voice ID 精确为 `zh-CN-XiaoxiaoNeural`，且已有样本路径。

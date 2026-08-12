# TTS 参数统一 checkpoint

更新时间：2026-08-12

## 已完成

- 新增任务级 `tts_model` 快照字段，并写入 TTS 阶段参数。
- 网页音色档案表单保存 `provider`、`model`、`voice_id` 三元组。
- 新任务创建时同时快照 Provider、模型、Voice ID 和音色档案 ID。
- Worker 合成时优先使用任务快照的 Voice ID 和模型；`.env` 中的 `DASHSCOPE_VOICE_PROFILE`、`DASHSCOPE_VOICE` 仅作为无快照旧任务的默认值。
- 保留现有环境变量兼容，不要求立刻删除 `DASHSCOPE_VOICE_PROFILE`。

## 验证

- `python -m unittest tests.test_video_quality.TtsInputTests tests.test_video_quality.NetworkRetryTests -v`：33/33 通过。
- `python -m compileall -q .`：通过。
- `npm.cmd run build`（`web`）：通过。
- `git diff --check`：通过，仅有既有换行格式提示。

## 需要手工操作

1. 在 Supabase 执行 `supabase/migrations/0017_task_tts_model_snapshot.sql`。
2. 部署并重启 Worker。
3. 在 `/voice-cloning` 保存一个 CosyVoice2 音色档案，填写模型和完整 Voice ID。
4. 创建新任务，确认任务详情显示 Provider / 模型 / Voice 快照。

## 当前判断

参数来源已统一为音色档案和任务快照，避免网页选择值被 Worker 环境默认值静默覆盖。

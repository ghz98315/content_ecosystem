# P4 任务级 TTS 快照

日期：2026-08-12

## 本次完成

- 新增 `supabase/migrations/0016_task_tts_profile_snapshot.sql`。
- 在 `tasks` 增加任务级 TTS 快照字段：`tts_voice_profile_id`、`tts_provider`、`tts_voice`、`tts_voice_label`。
- 扩展 `seed_stages()`，创建任务时把 TTS 快照固化进 `tts` stage 的 `params`。
- Worker TTS 阶段支持优先读取 `stage.params.provider` 和 `stage.params.voice`，不再只依赖全局环境变量。
- 新增 provider override 单元测试，保证显式快照优先生效。
- `video-collection` 创建任务时已开始写入这些快照字段；导入页的音色下拉 UI 仍待补齐。

## 自动回归

- `python -m unittest tests.test_video_quality.TtsInputTests -v`：15 项通过。
- `python -m unittest tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal tests.test_p0_reliability -v`：11 项通过。
- `npm.cmd run build`（`web/`）：通过。
- `git diff --check`：通过。

## 当前阻断

`0016_task_tts_profile_snapshot.sql` 尚未执行。执行前，远端 `tasks` 表和 `seed_stages()` 触发器还不具备 TTS 快照字段与下游注入能力。

## 下一步

用户执行 `0016_task_tts_profile_snapshot.sql` 后，继续补齐导入页音色下拉 UI、任务详情中的快照展示，以及默认音色策略说明。

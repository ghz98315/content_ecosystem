# P4 任务配音快照可见性

## 本次完成

- 修复并重建 `web/app/task/[id]/page.tsx`，恢复任务详情页生产构建。
- 保留任务、阶段、来源音频工件加载与实时订阅。
- 保留阶段重跑、阶段确认、任务取消和预检视图入口。
- 在任务来源摘要中展示任务创建时保存的配音快照：音色名称、provider；未选择自定义音色时显示系统默认 Edge 音色。
- P4 导入页已将所选 `voice_profiles` 写入任务级 `tts_voice_profile_id`、`tts_provider`、`tts_voice`、`tts_voice_label` 字段。

## 当前判断

任务级配音配置已经从导入入口传递到 worker，并能在任务详情页回显。worker 侧仍以任务快照为优先，避免后续修改全局音色配置影响已创建任务。

## 验证

- `npm.cmd run build`（`web`）通过。
- `python -m unittest tests.test_video_quality.TtsInputTests -v`：15/15 通过。
- `python -m unittest tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal tests.test_p0_reliability -v`：11/11 通过。
- `git diff --check` 通过；仅有现有工作区换行格式提示。
- 未执行真实远程 TTS、视频生成或付费服务调用。

## 受影响文件

- `web/app/task/[id]/page.tsx`
- `web/app/video-collection/page.tsx`
- `supabase/migrations/0015_voice_profiles.sql`
- `supabase/migrations/0016_task_tts_profile_snapshot.sql`
- `worker/stages/tts.py`
- `worker/tests/test_video_quality.py`

## 下一步

继续 P4：补充音色可用性/禁用状态校验和默认策略边界，再自动执行同一组回归；不需要新增 SQL 时直接推进。

## Checkpoint

未创建本地 git checkpoint commit：当前工作区包含大量既有及并行改动，无法安全隔离提交。

# 2026-08-10 取消阶段误判修复

## 问题

任务 `4f3ebfa2-140b-4f1a-91aa-ed0e396b3be3` 的 ingest 和 transcribe 已完成，但 clean 到 render 在 `04:59:59` 被统一标记为 `cancelled`，任务随后被错误标记为 `done`。

worker 停止本身不会把 pending/processing 阶段标记为 cancelled。根因是 `maybe_finish_task()` 将“全部 done 或 cancelled”当成完成条件，导致非取消任务的下游阶段被跳过。

## 修复

- 非 explicitly cancelled 任务只允许所有阶段均为 `done` 时标记完成。
- 发现未取消任务包含 cancelled 阶段时，标记为 failed 并记录日志。
- 明确取消的任务仍保持 cancelled，不会被重新激活。

## 数据恢复

- 保留该任务已完成的 ingest/transcribe。
- clean、rewrite、image、book、tts、render 已恢复为 pending。
- 任务已恢复为 processing，等待 worker 从 clean 阶段继续。

## 验证

- `python -m unittest tests.test_video_quality.NetworkRetryTests -v`
- 17 项全部通过。

# P3 镜头级图片审核检查点

日期：2026-08-12

## 本次完成

- 新增 `supabase/migrations/0013_image_review_audit.sql`。
- 新增 owner-scoped `review_image_frame` RPC，记录镜头序号、审核决定、备注、审核人和时间。
- 图片检查抽屉新增“确认通过”和“要求替换”操作；要求替换只记录人工决定，不会自动触发生图或修改历史成片。
- 抽屉读取并显示每个镜头最近一次审核结果。

## 自动回归

- `npm.cmd run build`（`web/`）：通过。
- `python -m compileall -q .`（`worker/`）：通过。
- `python -m unittest tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal -v`：5 项通过。
- `git diff --check`：通过。
- 未执行远程镜头审核写入验证；需先执行 `0013_image_review_audit.sql`。
- 本机 Node 为 v22.19.0，项目期望 Node 20.x。

## 边界

真正的单图重生成、替换图片版本和 Provider 切换仍需 Worker 镜头级任务接口；当前不会伪造这些能力。

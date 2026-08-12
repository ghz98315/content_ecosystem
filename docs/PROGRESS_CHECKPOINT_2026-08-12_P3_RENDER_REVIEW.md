# P3 成片人工审核审计检查点

日期：2026-08-12

## 本次完成

- 新增 `render_reviews`，记录成片审核人、决定、备注和时间。
- 新增 owner-scoped `review_render_stage`，在同一事务内写入审核记录并更新阶段与任务状态。
- 成片“人工审核通过”改用原子 RPC，页面展示最近审核决定和时间。
- RLS 明确限制为任务 owner 读取与写入审核记录。

## 自动回归

- `npm.cmd run build`（`web/`）：通过。
- `python -m compileall -q .`（`worker/`）：通过。
- `python -m unittest tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal -v`：5 项通过。
- `git diff --check`：通过。
- 未执行远程 RPC 写入验证；需先执行 `0012_render_review_audit.sql`。
- 本机 Node 为 v22.19.0，项目期望 Node 20.x。

## 下一步

执行迁移后验证一次真实成片审核记录，再继续镜头级版本与替换接口。

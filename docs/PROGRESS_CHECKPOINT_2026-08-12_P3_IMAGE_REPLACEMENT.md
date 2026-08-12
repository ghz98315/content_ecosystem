# P3 镜头级图片替换版本检查点

日期：2026-08-12

## 本次完成

- 新增 `supabase/migrations/0014_image_replacement_requests.sql`，支持镜头级重生成请求入库。
- 图片检查抽屉新增“提交重生成请求”。
- Worker 新增替换请求认领、处理、完成/失败回写。
- 替换版本复用现有九宫格生图、幂等 Provider 和安全提示词规则，不新造第二条生成链路。
- 新版本图片落到 `task_id/replacements/img_xxx_vyyy.png`，前端优先显示最新替换图。

## 自动回归

- `npm.cmd run build`（`web/`）：通过。
- `python -m compileall -q .`（`worker/`）：通过。
- `python -m unittest tests.test_p0_reliability tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal -v`：10 项通过。
- `git diff --check`：通过。
- 未执行真实远程替换请求冒烟；需先执行 `0014_image_replacement_requests.sql`。
- 本机 Node 为 v22.19.0，项目期望 Node 20.x。

## 剩余边界

- 当前替换图生成后会在图片工作台优先展示，但不会自动重跑 render。
- 后续需要把“替换图已完成”与成片重排、质检再跑联动起来。

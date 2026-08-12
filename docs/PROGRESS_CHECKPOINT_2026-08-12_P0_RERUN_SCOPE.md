# P0 重跑范围确认 checkpoint

更新时间：2026-08-12

## 本次完成

- 任务详情页触发阶段重跑前，展示当前阶段及下游阶段的影响范围。
- 明确提示已完成的上游产物不会被重跑，与 `rerun_stage` 的依赖感知语义保持一致。
- 通用详情阶段壳为重跑按钮补充包含影响范围的 `aria-label`。

## 验证

- `npm.cmd run build`（`web`）：通过。
- `python -m unittest tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_p0_reliability -v`（`worker`）：8/8 通过。
- `git diff --check`：通过，仅有既有换行格式提示。

## 当前判断

P0 的阶段重跑说明已覆盖前端实际操作入口；真实线上任务和远程 Worker 仍需在具备线上网络与授权的环境中人工验收。

## 下一步

继续收敛 P1 采集工作台的运营能力，优先检查批量任务操作与 URL 查询参数同步的边界测试；线上域名待网络可达后再执行只读 HTTP 检查。

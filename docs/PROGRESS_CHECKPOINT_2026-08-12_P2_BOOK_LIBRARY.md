# P2 书籍库聚合检查点

日期：2026-08-12

## 本次完成

- 新增 `supabase/migrations/0011_book_library.sql`：owner-scoped 书籍聚合、关联任务查询、候选整组人工确认。
- 新增 `/book-library`：书名/作者搜索、已确认/待确认筛选、分页、任务/成片统计、关联任务抽屉和确认入口。
- 顶部导航与侧栏新增“书籍库”。
- 聚合逻辑以确认书名优先；未确认记录只显示为“待确认候选”，不会伪装成稳定书籍。

## 验证

- `npm.cmd run build`（`web/`）：通过。
- `git diff --check`：通过。
- 未执行 Supabase 写入或远程 RPC 验证；`0011` 需要用户在 Supabase SQL Editor 执行后，页面才会读取真实数据。
- 本机 Node 为 v22.19.0，项目期望 Node 20.x。

## 下一步

执行 `0011_book_library.sql` 后，验证书籍库聚合、候选确认和跨任务明细；随后进入 P3 媒体生产人工控制。

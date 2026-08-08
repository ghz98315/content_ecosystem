# 内容创作台数据平台迁移决策

> 状态：已确认继续使用现有 Supabase，暂停迁移  
> 日期：2026-08-04  
> 触发原因：曾误判 Supabase 项目/连接不可用；用户已确认现有 Supabase 可正常使用  
> 影响范围：短视频任务、小红书知识库、认证、数据库、文件存储、实时状态、Worker

## 1. 决策摘要

当前决策为 **A：继续使用现有 Supabase 项目**。本阶段不迁移到自建 Supabase、Neon 或 Cloudflare R2，优先恢复并验证现有连接、认证、数据库、Realtime 和 `artifacts` Storage。

后续只有在现有 Supabase 确认无法满足容量、稳定性或账号约束时，才重新打开 B/C 方案评估。

飞书多维表格可以作为运营看板、选题库或人工审核入口，但不适合作为本项目核心数据库。

推荐目标架构：

```text
浏览器
  → Next.js API（认证、权限、数据校验、签名 URL）
      → Neon PostgreSQL（任务、阶段、产物索引、小红书结构化数据）
      → Cloudflare R2（PDF、音频、图片、字幕、成片）

本地 Python Worker
  → Neon PostgreSQL（原子认领和阶段状态）
  → Cloudflare R2（读取输入、上传产物）

页面状态更新
  → 2-3 秒增量轮询
  → 后续有明确需求时再升级 SSE/WebSocket
```

选择该架构的原因：

- 继续使用标准 PostgreSQL，保留事务、索引和原子任务认领能力。
- R2 使用兼容 S3 的对象存储接口，适合 MP3、PNG、PDF、MP4。
- 浏览器不再直接访问数据库，权限、校验和供应商切换集中在 Next.js API。
- Worker 可以用成熟的 PostgreSQL 与 S3 SDK，不需要绑定特定 BaaS SDK。
- 轮询足以支撑当前单用户、长任务工作台，复杂度低于重建 Realtime。

`待验证`：Neon 和 Cloudflare R2 的免费额度、账号可用性及中国网络表现会变化，创建账号时必须以供应商当前控制台为准，不在本文档承诺固定额度。

---

## 2. 为什么不能直接迁移到飞书多维表格

### 2.1 当前系统需要的能力

| 能力 | 当前用途 |
|---|---|
| 关系数据 | tasks、stages、artifacts、xhs_books、xhs_topics、xhs_drafts |
| 数据库事务 | 原子认领阶段、状态推进、重跑下游失效 |
| 并发控制 | 防止多个 Worker 重复处理同一阶段 |
| 权限控制 | 用户只能读取自己的任务和产物 |
| 私有文件 | 原始 PDF、音频、图片、字幕和成片 |
| 临时访问地址 | 浏览器预览和下载私有产物 |
| 高频状态更新 | Worker 持续更新 processing、done、failed、needs_review |
| 查询能力 | 按任务、阶段、状态、时间和产物类型组合查询 |

### 2.2 飞书多维表格的适合边界

适合：

- 选题池和发布排期。
- 人工审核列表。
- 已完成视频的运营数据回填。
- 团队可视化进度看板。
- 从核心数据库同步出的摘要数据。

不适合：

- 作为 Worker 的高频任务队列。
- 承担数据库事务和并发锁。
- 保存大量媒体文件及其版本。
- 替代私有对象存储和 Presigned URL。
- 承担浏览器登录、会话和细粒度权限。
- 成为八阶段产物之间的稳定引用系统。

结论：飞书可作为二级运营界面，不作为主数据源。

---

## 3. 当前 Supabase 耦合清单

### 3.1 前端认证

当前：

- `web/lib/useAnonAuth.ts` 读取 Supabase session，并执行匿名登录。
- `tasks.owner` 依赖 `auth.users.id`。
- RLS 使用 `auth.uid()` 判断任务归属。

迁移后：

- 使用服务端安全会话，不再让浏览器直接获得数据库访问能力。
- 当前产品为单账号创作工具，首版采用单管理员账号或明确的受邀账号。
- Next.js API 从会话中解析用户 ID，并在 SQL 查询中强制加入 owner 条件。

### 3.2 前端数据库访问

当前直接访问位置包括：

- 首页读取和创建 tasks。
- 任务详情读取 tasks/stages 并更新阶段状态。
- rewrite/book 评审门更新 params。
- ingest 详情读取 artifact meta。
- XHS 页面读取 books/topics/drafts。

迁移后全部改为：

```text
GET    /api/tasks
POST   /api/tasks
GET    /api/tasks/:id
PATCH  /api/tasks/:id
POST   /api/tasks/:id/cancel
POST   /api/stages/:id/approve
POST   /api/stages/:id/rerun
GET    /api/tasks/:id/artifacts
POST   /api/uploads/presign
GET    /api/artifacts/:id/url
```

XHS 保留现有 API Route 结构，但底层从 Supabase Client 改为统一数据库和对象存储服务。

### 3.3 Realtime

当前：

- 首页订阅 tasks 列表变化。
- 任务详情订阅任务和阶段变化。

迁移后首版：

- 首页有 processing 任务时每 3 秒拉取增量状态。
- 任务详情有 pending/processing/needs_review 时每 2 秒拉取任务快照。
- 页面隐藏后降低频率或暂停；重新可见时立即刷新。
- done/failed/cancelled 稳定状态停止高频轮询。

选择轮询而不是立即重建 Realtime 的理由：任务处理单位是秒到分钟，2-3 秒延迟不影响创作体验，且显著降低迁移复杂度。

### 3.4 文件存储

当前：

- Worker 通过 Supabase Storage 上传和下载产物。
- Web 通过 signed URL API 预览私有文件。
- XHS PDF 在浏览器直接上传 Supabase Storage。

迁移到 R2 后：

- Worker 使用 `boto3` S3 Client。
- Next.js 使用 AWS S3 兼容 SDK生成上传和下载 Presigned URL。
- 浏览器只获得短时、限定对象 key 和操作类型的 URL。
- Bucket 保持私有，禁止公开列表。

建议对象 key：

```text
users/{owner_id}/tasks/{task_id}/source/audio.mp3
users/{owner_id}/tasks/{task_id}/transcript/v{version}.json
users/{owner_id}/tasks/{task_id}/rewrite/v{version}.json
users/{owner_id}/tasks/{task_id}/images/v{version}/{index}.png
users/{owner_id}/tasks/{task_id}/tts/v{version}.mp3
users/{owner_id}/tasks/{task_id}/render/v{version}.mp4
users/{owner_id}/xhs/books/{book_id}/source.pdf
```

### 3.5 Worker 数据访问

当前 Worker 通过 `supabase-py` 查询表和 Storage。

迁移后：

- 数据库使用 `psycopg` 连接 PostgreSQL。
- 文件使用 `boto3` 连接 R2。
- 所有 SQL 集中在 repository 层，stage handler 不直接调用供应商 SDK。
- 阶段认领使用 PostgreSQL 事务和 `FOR UPDATE SKIP LOCKED`。

原子认领目标行为：

```sql
begin;

select id
from stages
where status = 'pending'
  and not exists (
    select 1
    from stages prior
    where prior.task_id = stages.task_id
      and prior.seq < stages.seq
      and prior.status not in ('done', 'cancelled')
  )
order by seq, updated_at
for update skip locked
limit 1;

update stages
set status = 'processing', updated_at = now()
where id = :id;

commit;
```

---

## 4. 方案对比

| 方案 | 代码改造 | 运维 | 在线可用性 | 媒体存储 | 结论 |
|---|---:|---:|---:|---:|---|
| 合并到现有 Supabase 项目 | 低 | 低 | 高 | 一般 | 若仍有可用项目，最快恢复 |
| 自建 Supabase + Tunnel | 低到中 | 高 | 依赖本机 | 依赖本机磁盘 | 零供应商项目费，但维护成本高 |
| Neon + R2 | 中到高 | 低到中 | 高 | 好 | 推荐长期方案 |
| Cloudflare D1 + R2 | 高 | 中 | 高 | 好 | 需重写 PostgreSQL 事务逻辑 |
| Firebase | 高 | 中 | 高 | 好 | 数据模型和 Worker 改造过大 |
| 飞书多维表格 | 高 | 中 | 受 API 限制 | 不适合 | 仅作为运营辅助 |

---

## 5. 推荐迁移策略

采用并行适配后切换，不在一个提交中删除 Supabase。

### M0：架构选择门

- [ ] 确认限制类型：免费项目数量，还是数据库/Storage 用量。
- [ ] 确认目标：合并 Supabase / 自建 Supabase / Neon + R2。
- [ ] 确认旧数据是否必须迁移。
- [ ] 确认 Production 是否允许短暂停写切换。

### M1：服务端 API 收口

- [ ] 新增统一的 tasks/stages/artifacts API。
- [ ] 前端停止直接写数据库。
- [ ] 保持底层仍使用 Supabase，实现行为等价。
- [ ] 将 Realtime 封装为统一刷新接口。
- [ ] 完成现有 Production 回归。

价值：即使最终继续使用 Supabase，浏览器也不再与供应商 SDK 深度耦合。

### M2：Worker Repository 收口

- [ ] 定义任务、阶段、产物 repository 接口。
- [ ] 现有 Supabase 实现迁入 repository。
- [ ] stage handler 只调用领域接口。
- [ ] 增加本地单元测试覆盖状态推进和前置阶段判断。

### M3：Neon 数据库实现

- [ ] 创建 PostgreSQL 项目和连接凭据。
- [ ] 迁移 tasks/stages/artifacts/xhs 表结构。
- [ ] 增加 owner、版本、当前产物和状态索引。
- [ ] 实现原子阶段认领。
- [ ] 接入服务端 API 和 Worker repository。

### M4：R2 对象存储实现

- [ ] 创建私有 Bucket 和最小权限凭据。
- [ ] 实现上传、下载、删除和 Presigned URL。
- [ ] Web 手动上传与 XHS PDF 改用 Presigned PUT。
- [ ] Worker 产物读写切换到 R2。
- [ ] 验证大文件、中文元数据、超时和重试。

### M5：认证替换

- [ ] 建立单管理员或受邀账号登录。
- [ ] 使用 HttpOnly、Secure、SameSite Cookie。
- [ ] 所有 API 校验会话和 owner。
- [ ] Worker 使用独立服务凭据，不复用浏览器会话。
- [ ] 验证未登录、越权 ID 和过期会话。

### M6：状态刷新替换

- [ ] 实现可见性感知的任务轮询。
- [ ] processing 时高频，稳定状态时停止。
- [ ] 请求失败采用退避，不无限快速重试。
- [ ] 页面明确显示“最后更新”和“连接异常”。

### M7：数据迁移与双环境验收

- [ ] 导出旧 tasks/stages/artifacts/XHS 结构化数据。
- [ ] 复制必须保留的对象文件。
- [ ] 校验记录数、关联关系、对象存在性和哈希/大小。
- [ ] Preview 使用新平台跑完整八阶段。
- [ ] 旧 Production 保持可回退。

### M8：Production 切换

- [ ] 短暂停写。
- [ ] 执行最终增量迁移。
- [ ] 切换 Production 环境变量。
- [ ] 发布并执行线上冒烟。
- [ ] 观察至少一个完整视频任务。
- [ ] 失败则恢复旧环境变量和旧部署。

### M9：Supabase 退役

- [ ] 新平台稳定运行并完成验收后再开始。
- [ ] 先撤销写入，不立即删除旧数据。
- [ ] 保留约定时间的只读备份。
- [ ] 删除旧凭据前确认没有代码引用。

---

## 6. 回退设计

迁移过程中保留配置开关：

```text
DATA_BACKEND=supabase | postgres
OBJECT_STORAGE=supabase | r2
STATUS_TRANSPORT=realtime | polling
```

要求：

- 数据库和对象存储可以分别切换，避免同时排查两类问题。
- 旧 Supabase 实现保留到新平台完成真实样片验收。
- Production 切换通过环境变量和部署完成，不在运行时随机混用后端。
- 回退后新平台产生的数据单独保留，禁止自动覆盖旧平台数据。

---

## 7. 数据迁移验收

结构化数据：

- [ ] tasks 总数一致。
- [ ] 每个 task 的 8 个 stage 顺序和状态一致。
- [ ] artifact 与 task/stage 外键关系完整。
- [ ] XHS books/topics/drafts 关联完整。
- [ ] owner 映射明确，没有无主任务。

对象文件：

- [ ] 每条 artifact 的对象存在。
- [ ] 文件大小与源对象一致。
- [ ] JSON 可以解析。
- [ ] MP3 可以播放。
- [ ] PNG 可以解码。
- [ ] MP4 可以读取媒体信息并播放。
- [ ] Presigned URL 过期后不可继续访问。

业务闭环：

- [ ] 新建任务。
- [ ] Worker 原子认领。
- [ ] 八阶段状态推进。
- [ ] rewrite/book 人工评审。
- [ ] 手动上传。
- [ ] 产物预览与下载。
- [ ] 取消和重跑。
- [ ] XHS PDF、选题、文案和卡片导出。

---

## 8. 需要用户确认的决策

只需要确认以下一项主选择：

1. `A - 合并 Supabase`：仍有一个可用 Supabase 项目，希望最快恢复。
2. `B - 自建 Supabase`：优先零供应商费用，接受电脑关机时数据服务不可用。
3. `C - Neon + R2`：接受一次中等规模迁移，换取长期供应商解耦和在线可用性。

同时补充：

- 当前限制是“只能有两个免费项目”，还是“某个项目数据库/Storage 超额”。
- 旧 Supabase 中的历史任务和媒体文件是否必须保留。

未确认前允许继续：文档、测试基线、服务端 API 边界设计。  
未确认前暂停：新数据库依赖、数据迁移脚本、Production 环境变量变更。

---

## 9. 开发素材卡

- 阶段：规划阶段，次阶段为验收准备。
- 本轮主题：从供应商直连改为可替换的数据平台边界。
- 关键模块：认证与权限、任务数据库、对象存储、状态刷新、Worker 认领。
- 解决的问题：免费项目限制不再直接阻断产品迭代。
- 用户可感知变化：迁移后任务、素材和成片仍在同一工作台完成，底层供应商变化对创作流程透明。
- 关键设计决策：飞书作为运营辅助，不承担核心任务队列和媒体存储。
- 验证证据：当前代码中的 Supabase Auth、RLS、Realtime、Database、Storage 直接调用盘点。
- 待验证/边界：新供应商账号、当前免费额度、中国网络和旧数据规模。
- 可写角度：真正降低云服务成本，不是换一张表，而是先把产品从供应商 SDK 中解耦。

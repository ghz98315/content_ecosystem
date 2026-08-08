# 短视频创作台线上冒烟与回退清单

> 用途：每个优化批次在 Preview 和 Production 环境重复执行。  
> 首次建立：2026-08-04  
> 当前状态：B0 基线检查进行中

## 1. 环境基线

| 项目 | 当前基线 | 验证状态 |
|---|---|---|
| Git 主分支 | `master` | 已确认 |
| Production 来源 | GitHub `master` 自动部署 | 文档确认，待 Vercel 控制台复核 |
| Vercel 主域 | `content-ecosystem-neon.vercel.app` | 2026-08-04 返回 HTTP 200 |
| 自定义域 | `content-ecosystem.socra.cn` | 2026-08-04 返回 HTTP 200 |
| 自定义域代理 | Cloudflare → Vercel | 响应头确认 |
| 前端 Root Directory | `web/` | 项目文档确认，待 Vercel 控制台复核 |
| Worker | 本地 `python worker/main.py` | 配置存在，运行状态待验证 |
| 数据和文件 | Supabase + private `artifacts` bucket | 项目文档确认 |

### 1.1 2026-08-04 基线发现

- 前端生产构建通过，原 `serverExternalPackages` 无效配置警告已清除。
- Worker Python 源码编译通过。
- 两个 Production 域名均返回 HTTP 200。
- Production 桌面截图可以加载页面壳，但数据区先停留在“连接中”，随后显示“登录失败：Failed to fetch”。
- Production 移动截图显示 Sidebar 固定占用约 240px，主工作区过窄，当前移动布局不可用。
- Supabase DNS 解析和 TCP 443 连接正常，但 HTTPS 握手失败，脱敏错误为 `SSL UNEXPECTED_EOF_WHILE_READING`。
- Vercel CLI 已安装，但当前没有有效登录凭据，无法读取项目和部署列表。

基线截图位于：`docs/evidence/B0/`。

## 2. 发布标识

每次发布前填写：

```text
批次：
环境：Preview / Production
Git 分支：
Git 提交：
部署标识或 URL：
验证时间：
验证人：Codex
基准任务 ID：
```

## 3. 本地发布门

- [ ] `git status --short` 已检查，未混入不相关文件。
- [ ] 未提交 `.env`、密钥、用户数据、下载文件或日志。
- [x] `npm.cmd run build` 通过且无新的构建警告（2026-08-04）。
- [x] `python -m compileall -q worker` 通过（2026-08-04）。
- [ ] 当前批次涉及的专项测试通过。
- [ ] 数据库迁移为向后兼容变更。
- [ ] 已写明本批次回退方式。

## 4. Preview 冒烟

### 4.1 页面与导航

- [ ] 首页返回 HTTP 200。
- [ ] 首页在 `1440×900` 正常显示。
- [ ] 首页在 `1280×720` 正常显示。
- [ ] 首页在 `390×844` 正常显示。
- [ ] Sidebar 展开、收起和导航正常。
- [ ] `/xhs` 可以打开，短视频改动没有破坏图文工作台。

### 4.2 任务创建

- [ ] 匿名登录或已有会话初始化成功。
- [ ] 分享链接输入内容可以保留。
- [ ] 创建任务成功后进入任务详情。
- [ ] 非法输入显示可理解错误，不产生空任务。
- [ ] 重复提交期间按钮禁用，不重复创建。

### 4.3 任务详情

- [ ] 任务标题、整体状态和八阶段状态可见。
- [ ] 当前阻塞阶段被自动选中。
- [ ] pending / processing / needs_review / failed / done / cancelled 显示正确。
- [ ] 阶段切换不会触发页面结构跳动。
- [ ] 已完成产物可以获取 signed URL 并预览。

### 4.4 八阶段关键路径

- [ ] ingest 自动解析成功，或正确进入手动上传兜底。
- [ ] transcribe 能读取 ingest 音频。
- [ ] clean 能读取逐字稿并输出清洗稿。
- [ ] rewrite 生成候选并停在评审门。
- [ ] 选择候选后，下游读取正确最终稿。
- [ ] image 生成索引和图片产物。
- [ ] book 低置信时停在评审门。
- [ ] tts 生成音频和字幕产物。
- [ ] render 生成可播放、可下载的 9:16 MP4。

### 4.5 异常路径

- [ ] 自动采集失败后可以手动上传继续。
- [ ] API 失败显示可操作错误，不泄露密钥和内部响应。
- [ ] Worker 暂停时页面保持可理解的等待状态。
- [ ] 阶段失败后可以重试。
- [ ] 任务取消后不再继续处理。

## 5. Production 冒烟

Production 只执行已经在 Preview 通过的检查：

- [ ] 两个线上域名返回 HTTP 200。
- [ ] 首页和 `/xhs` 可访问。
- [ ] 固定基准任务可以打开。
- [ ] 本批次新增或修改的主操作成功。
- [ ] Supabase 查询、Realtime 和 signed URL 正常。
- [ ] Worker 能认领阶段并回写状态。
- [ ] 页面无新的阻断级控制台错误。
- [ ] 已记录 Production 提交和部署标识。

## 6. 视觉检查

- [ ] 最长标题不会覆盖状态或按钮。
- [ ] 长文案可滚动且不会撑破工作区。
- [ ] 图片、音频、视频加载前后布局稳定。
- [ ] 按钮文字和图标不溢出。
- [ ] 移动端主要操作无需横向拖动才能触达。
- [ ] 页面不存在无意义的嵌套卡片和装饰性大面积渐变。
- [ ] 键盘焦点清楚可见。

## 7. 回退流程

### 7.1 Git 自动部署回退

适用于当前未登录 Vercel CLI 的基线方式：

1. 确认引入问题的 Git 提交。
2. 使用新的 revert 提交撤销该批次，不重写 `master` 历史。
3. 推送 revert 提交到 `origin/master`。
4. 等待 GitHub → Vercel 自动部署完成。
5. 对两个 Production 域名执行 HTTP 和主路径复测。
6. 在执行文档记录回退提交、原因和残留数据影响。

### 7.2 Vercel 部署回退

Vercel 登录恢复后优先使用：

1. 在项目 Deployments 中定位上一条已验收 Production。
2. 执行 Promote / Rollback。
3. 检查自定义域是否指向回退部署。
4. 再通过 Git revert 使代码主分支与线上状态一致。

### 7.3 数据库回退

- 只执行预先编写且验证过的补偿迁移。
- 不删除线上表、列、枚举值或已有 artifact。
- 先恢复应用兼容性，再处理孤立的新字段或新数据。
- 涉及用户产物的数据清理必须单独确认。

## 8. 立即回退条件

- 无法创建或打开任务。
- 阶段状态被错误推进、覆盖或循环执行。
- 新旧产物混用导致错误成片。
- signed URL、认证或 Storage 全面失败。
- Production 数据写入与旧代码不兼容。
- 主要桌面或移动视口无法完成核心操作。

## 9. 批次结果模板

```md
### Bx 线上验证记录

- 状态：Preview 通过 / Production 通过 / 待验证 / 已回退
- Git 提交：
- Preview：
- Production：
- 基准任务：
- 通过路径：
- 失败路径：
- 视觉检查：
- 已知边界：
- 回退提交或部署：
- 下一动作：
```

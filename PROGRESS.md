# AI图书带货视频创作台 — 开发进度

最后更新：2026-08-05

## 最新修复检查点（待处理任务取消与删除，2026-08-05）

### 已修复

- 新建任务未启动 Worker 时，任务详情会把“全阶段 pending”识别为尚未开始，并提供“取消并删除”操作。
- 删除采用受控流程：先把任务置为 cancelled，再取消所有 pending 阶段；确认没有活动阶段后才删除任务，避免误删已经开始处理的数据。
- 已开始处理的任务只允许取消，不直接删除；取消和删除操作现在会等待 Supabase 响应并显示明确的成功或错误信息，不再静默失败。
- Worker 在阶段处理结束汇总任务状态前会复核任务是否已取消，避免把 cancelled 任务重新写回 processing。

### 本地验证

- Next.js 生产构建通过。
- Worker 单元测试 21 项通过，新增“已取消任务不会被重新激活”回归用例。
- 待推送 `master` 触发 Vercel 部署并执行线上取消/删除烟测。

## 最新恢复检查点（人工二次发布流程，2026-08-05）

### 当前本地状态

- 远端实现基线：`3745849 feat: isolate worker to a test task`，人工 V2 流程、数据库迁移兼容和 Worker 指定任务隔离均已推送。
- 本地未推送提交：`fb47fbb chore: save edge tts voice catalog`；`master` 比 `origin/master` 超前 1 个提交。
- `worker/tts_voices.json` 已保存 edge-tts 7.2.8 当前返回的 8 个 `zh-CN` 音色，默认仍为 `zh-CN-XiaoxiaoNeural`。
- 旧 Worker PID `7480` 已停止；当前没有启动全局 Worker，历史队列不会继续被消费。
- 数据库最后只读核验：13 个历史 pending，另有 4 个更新时间停留在 7 月的遗留 processing。
- 下一操作：用户在生产首页新建健康类 V1 任务并提供任务 ID；使用 `WORKER_TASK_ID=<新任务ID>` 启动新版 Worker，只处理该任务。

### 本轮已实现（已部署，待端到端验收）

- 明确两次去重语义：`promote-2` = 首次去重，生成首发 V1；`promote-3` = 首发稿验证为爆款后，人工触发的二次去重，生成独立 V2。
- 健康类提示词新增 `worker/prompts/categories/health/initial_dedup.txt` 和 `repost_dedup.txt`；旧 `rewrite.txt` 保留为首次去重兼容别名。
- V2 不读取原始清洗稿，Worker 强制读取 V1 rewrite artifact 中的 `final_text`，再运行 `repost_dedup`。
- 新增任务版本字段和父子关系：`rewrite_mode`、`source_task_id`、`version_no`；V2 自动取消 ingest/transcribe/clean，独立运行 rewrite→image→book→tts→render。
- 新增 `create_repost_task(uuid)` 安全函数，只有当前用户的 render 阶段完成后才能创建 V2；重复点击会返回现有未取消/未失败的 V2。
- V1 成片详情增加人工确认按钮“生成二次发布版本”，确认后跳转到独立 V2 任务；不会覆盖 V1 的文案或视频。

### 本轮验证

- Worker 单元测试：20 项通过（包含指定任务隔离测试）。
- Python 编译：通过。
- Next.js 生产构建：通过。
- 数据库迁移 `0003`、`0004`、`0005` 已由用户确认在 Supabase 执行成功；其中 0005 对尚未执行 0003 的环境做了 `content_category` 兼容补充。
- 当前部署：提交 `fd7572c` 已推送并完成 Vercel 部署；生产首页和既有任务页均返回 HTTP 200。
- 当前状态：`待验证`，尚未执行真实 V1→人工确认→V2 端到端流程。

### 下一步

1. 等待用户提供新建健康类 V1 的任务 ID；不要在没有任务 ID 时启动 Worker。
2. 使用新增 `WORKER_TASK_ID` 过滤器受控启动新版 Worker，不处理历史队列。
3. 完成 V1 全流程，确认 render 完成后人工点击“生成二次发布版本”。
4. 切换过滤器到 V2 任务 ID，验证前三阶段为 cancelled、rewrite 输入确实来自 V1 `final_text`，并验证 V2 生成独立图片、配音和 final.mp4。

## 上一恢复检查点（基础链路，2026-08-05）

### 当前节点

- 主阶段：人工二次发布流程开发完成，等待迁移、部署和 V1→V2 验收。
- 当前功能实现基线：`5a7bfd8 improve health rewrite compliance and tts reliability`。
- `master` 与 `origin/master` 已对齐到 `5a7bfd8fc177db8f8312f7c8e164ccaac5e64b2f`，已触发 Vercel 自动部署。
- 生产首页及既有任务页已返回 HTTP 200；用户已确认部署完成。
- 本轮重点仅为健康类图书视频；社科类、教育类只保留首页入口，暂不开发；XHS 暂不测试。

### 本轮已完成

- 健康类提示词按阶段拆分管理：清洗、轻量改写、合规检查；改写不再提供 A/B/C 三个方向。
- 改写目标调整为：尽量保留原文长度、开头钩子、中间内容和结尾，只做必要的轻量改写。
- 新增 `skills/wechat-video-book-compliance/`，在改写生成后和人工确认时执行健康内容合规检查。
- 首页增加健康类、社科类、教育类分类入口；仅健康类可用，其他分类显示“待开发”。
- 分镜目标调整为平均约 8 秒、每镜约 24-32 字；图片按 4:3 使用。
- 成片保留片头书名卡；画面使用一种 Zoom In 动效和叠化切换；画面上方固定书名/作者，下方固定简短免责声明。
- TTS 仍使用 `edge-tts 7.2.8`，默认音色为 `zh-CN-XiaoxiaoNeural`；已改为只传纯正文，过滤时间点、分隔符、Markdown、JSON、SSML、镜头和画面说明等格式内容。
- TTS 约按 90 字/26 秒拆段、3 路并发合成，并由 FFmpeg 合并音频和平移字幕时间戳。
- Supabase 网络层已增加显式证书包、关闭 HTTP/2、缩短 keepalive、有限重试和客户端重建；Storage 与 render 查询也已加入重试。
- 评论策略已明确：优先购买意向评论；没有购买意向时，补充高点赞或高回复评论。评论抓取仍取决于采集源实际返回能力。

### 已验证证据

- 既有任务 `36b9ff99-55c8-4b62-a919-8388138c4e7d` 已用新版逻辑单独重跑 TTS 和 render。
- TTS 从异常的 `4267.207` 秒降为 `434.861` 秒，共 25 个合成批次、68 个字幕片段，检查结果 `contains_ssml: false`，阶段状态为 `done`。
- render 阶段状态为 `done`，新 `final.mp4` 已覆盖：1080x1920、70 张图片、Zoom In + dissolve，任务总状态为 `done`。
- Worker 测试 19 项通过；Python 编译通过；Next.js 生产构建通过；真实 edge-tts 短句烟测通过；新版 Supabase 客户端只读查询曾通过。

### 重要边界

- Supabase 当前尚无 `tasks.content_category` 列。迁移文件已提交但未执行；前端创建任务暂不写该字段，Worker 在字段缺失时回退为健康类。
- 2026-08-05 最后确认时，全局 Worker PID 为 `7480`，启动于 `2026-08-05 07:35:22`，仍加载旧代码；数据库另有 13 个 pending 阶段。
- 不要直接重启全局 Worker，否则可能批量消费旧 pending。下次开始时必须先复核 Worker PID、pending 数量及目标测试任务 ID，再决定受控启动方案。
- Index-TTS 尚未接入。接入前需确认 API 地址、鉴权、请求/响应、参考音频上传、单次长度限制及时间戳能力；当前生产测试仍走 edge-tts。
- 本轮首次“全新任务端到端”验收尚未完成，不能据此宣称整条生产链路已经验收通过。

### 下次直接从这里继续

1. 读取本节和 `RESUME_PROMPT.md`，执行 `git status --short --branch` 与 `git log -1 --oneline`。
2. 获取用户新建的健康类测试任务 ID；不要复用旧任务判断完整新链路。
3. 只读检查全局 Worker、pending 阶段和新任务各 stage 状态，避免旧任务被意外消费。
4. 设计并执行受控的新版 Worker 测试，优先跟踪新任务的 rewrite、image、book、tts、render。
5. 按“改写完整性、8 秒分镜、4:3 图片、纯正文配音、书名/作者/免责声明、Zoom In + 叠化”逐项验收并记录证据。
6. 测试完成前不部署额外改动；出现问题先定位并修复，再决定是否重新部署。

## 部署

- 前端：`content-ecosystem-neon.vercel.app`（GitHub master → Vercel 自动部署，root = `web/`）
- Worker：本地运行 `python worker/main.py`
- DB/Storage：Supabase（私有 bucket `artifacts`）

---

## 8阶段流水线

| seq | kind       | 产物                                      | 评审门                     |
|-----|------------|-------------------------------------------|----------------------------|
| 1   | ingest     | `{taskId}/audio.mp3`                      | 失败时手动上传             |
| 2   | transcribe | `{taskId}/transcript.json`                | 无                         |
| 3   | clean      | `{taskId}/clean.json`                     | 无                         |
| 4   | rewrite    | `{taskId}/rewrite.json`                   | 必须选候选才继续           |
| 5   | image      | `{taskId}/images_index.json` + 分图       | 无                         |
| 6   | book       | `{taskId}/book.json`                      | confidence=low 时才进      |
| 7   | tts        | `{taskId}/tts.mp3` + `tts_subtitles.json` | 无                         |
| 8   | render     | `{taskId}/final.mp4`                      | 无                         |

---

## 前端组件（Notion 风格重构后）

| 文件 | 用途 |
|------|------|
| `web/app/globals.css` | CSS design tokens、keyframes、utility classes |
| `web/components/Sidebar.tsx` | 汉堡收起侧边栏，工具导航 + 任务列表 |
| `web/components/PipelineBar.tsx` | 8节点可点击流程条，状态图标 |
| `web/components/StageDetail.tsx` | 按 kind 分发到各子面板 |
| `web/components/detail/_shell.tsx` | DetailShell 公共壳 + TextBtn |
| `web/components/detail/IngestDetail.tsx` | 统计卡片 + 粉丝量 + 热门评论 |
| `web/components/detail/TranscribeDetail.tsx` | 逐字稿展示 + 字数 |
| `web/components/detail/CleanDetail.tsx` | 清洗后 / 原文切换 |
| `web/components/detail/RewriteDetail.tsx` | A/B/C 候选选择，写 chosen_index |
| `web/components/detail/BookDetail.tsx` | 书名内联编辑，确认继续 |
| `web/components/detail/TtsDetail.tsx` | 音频播放 + 合成文案 |
| `web/components/detail/ImageDetail.tsx` | 3列网格 + 灯箱，批量 signed URL |
| `web/components/detail/RenderDetail.tsx` | 9:16 视频播放 + 下载 |
| `web/app/task/[id]/page.tsx` | 2列布局，自动选中活跃节点 |
| `web/app/page.tsx` | 首页，新建任务表单 + 任务列表 |
| `web/app/api/signed-url/route.ts` | 服务端 signed URL（需 `SUPABASE_SERVICE_KEY`） |

---

## 环境变量

### Worker（`worker/.env`，已 gitignore）
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
OPENAI_API_KEY=
DEEPSEEK_API_KEY=        # 可选，book 阶段优先用
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE=int8
REWRITE_MODEL=gpt-4o-mini
CLEAN_MODEL=gpt-4o-mini
```

### Vercel
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=    # 非 NEXT_PUBLIC_，仅 API route 使用
```

---

## 已修复 Bug（全量）

| 提交 | 问题 | 修法 |
|------|------|------|
| `f5264bd` | handler 返回 `"failed"` 被 else 分支覆盖成 `"done"` | `else` → `elif status == "done"` |
| `3912f70` | `claim_next_stage` 不接受 `cancelled` 作为前置完成状态 | `== "done"` → `in ("done", "cancelled")` |
| `3912f70` | 重跑时 `chosen_index`/`manual_book_name` 残留 | `rerun()` 清除这两个 params |
| `64fb956` | `maybe_finish_task` 不接受 `cancelled` | 同上改法 |
| `2aa85b6` | 私有 bucket 签名 URL 用 anon key 失败 | `/api/signed-url` 改用 service key |
| `77e9621` | 下载按钮依赖 `task.status===done` | 改为 `renderStage?.status==="done"` |
| `044a62e` | book.py 总是选候选 A（读自身 params） | 增加 DB fallback 查 rewrite stage params |
| `044a62e` | tts 把 `<break>` 标签当文字朗读 | 构建完整 SSML，`html.escape()` + `<speak><voice>` |
| `06b4047` | rewrite short-circuit 时 `chosen` 字段不回写 JSON | 下载 → 更新 chosen → 重新上传 |
| `7e9861a` | ImageDetail 读错数据结构（`d.images` 不存在） | 改为读 `images_index.json` 数组，批量获取 signed URL |
| `de58b3d` | WinError 10054 连接重置污染日志 | 识别连接类错误静默 + 2s 退避 |
| `5ece063` | PDF 上传报 413（Vercel 4.5MB 限制） | 客户端直传 Supabase Storage，API 只接收 `file_path` |
| `d6977b7` | 中文文件名导致 Storage key 非法 | 上传时只用 `Date.now().pdf` 作为文件名 |
| `4a62a36` | 生成选题报 500（OpenAI key 欠费） | topics route 切换为 DeepSeek |
| `d9cd5f3` | "解析 LLM 返回失败" | 剥除 DeepSeek 偶发的 markdown 代码块包裹再 `JSON.parse` |
| `466875f` | 生成文案报 422（合规硬拦截） | 改为软警告：返回 `banned_word` 字段，前端标红不阻断 |
| `77c39ac` | 导出 ZIP 失败（截图被 `scale(0.6)` 缩放节点） | 添加隐藏原始尺寸节点，`html-to-image` 截图该节点 |
| `d11c0d5` | 切 tab 清空文案/卡片 state | 改用 `display:none` 隐藏 tab 而非卸载组件 |
| `d11c0d5` | 文案生成后无法直接进卡片工厂 | 正文右上角加「🎨 送入卡片工厂」按钮 |
| `5067972` | PDF 服务端解析报 500（@napi-rs/canvas 缺失） | `next.config.js` 加 `serverExternalPackages: ['pdf-parse']` |
| `39b344c` | `DOMMatrix is not defined`（pdfjs-dist 需要浏览器环境） | 将 PDF 解析完全移至客户端（pdfjs-dist 浏览器版），服务端只存数据 |

---

## 已完成功能（本轮新增）

- **Notion 风 UI 重构**：2列布局，Sidebar 汉堡收起，PipelineBar 可点击，各阶段独立详情面板，fadeSlideIn 动画
- **粉丝量**：从 f2 视频响应提取 `fans_count`，写入 `tasks.author`，采集面板展示
- **热门评论**：`fetch_hot_comments()` 抓 top-10 按点赞排序（best-effort），保存到 artifact meta
- **改写候选选择修复**：选 B/C 后 book/tts/image 均正确使用所选候选
- **小红书图文工作台**（`/xhs`）：
  - 知识库管理（文字粘贴 + PDF上传解析）
  - 书籍内容段落选取（复选框，已选字数实时显示）
  - 主题矩阵（OpenAI生成选题卡，内联编辑标题，合规检测）
  - 文案生成室（DeepSeek，三种文风，正文+评论剧本，一键复制）
  - 视觉卡片工厂（Cover/Body/Tail 三类卡片，品牌名可配置）
  - ZIP 批量导出（html-to-image × 2倍像素 + JSZip）
  - 自定义域名：`content-ecosystem.socra.cn` 绑定 Vercel
  - **测试阶段全流程修复**（2026-07-07）：413/非法key/500/解析/422/ZIP/tab-state/卡片关联，共8个bug全部修复

---

## 下一阶段计划

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P0 | **确认 `/api/xhs/cards` 使用的 LLM** | 检查是否仍用 OpenAI key（欠费），如是切换 DeepSeek |
| P0 | **XHS 端对端验收** | PDF 上传 → 选题 → 文案 → 卡片工厂 → 导出 ZIP 完整跑通 |
| P1 | **Prompt 质量优化** | 跑 3-5 条真实视频，根据输出调整 `prompts/rewrite.txt`、`prompts/clean.txt` |
| P1 | **XHS 卡片样式优化** | 根据实际导出效果调整字体大小、间距、高亮样式 |
| P2 | **渲染模板优化** | `worker/stages/render.py` 字幕样式、字体、9:16 布局深度定制 |
| P3 | **批量任务** | 一次提交多链接，自动队列 |
| P3 | **数据反馈** | 记录候选选择频率，用于 prompt A/B 测试 |

---

## 已知注意事项

- `fans_count`：取决于 f2 返回字段名（`fans_count` 或 `follower_count`），首次运行验证
- 热门评论：f2 版本若不支持 `fetch_video_comments` 会静默跳过，显示"暂无评论数据"属正常
- 图片阶段：需要 OpenAI API Key 有 `gpt-image-*` 权限
- Windows 部署：`WinError 10054` 已静默，worker 自动重连

---

## 数据库注意事项

确认已执行（Supabase SQL Editor）：

```sql
ALTER TYPE stage_status ADD VALUE IF NOT EXISTS 'cancelled';
```

---

## Render 阶段依赖

render 需要以下 artifacts 已存在：

- `type = "image_index"`（image 阶段产出）
- `stage_kind = "tts"` + `type = "audio"`（tts 阶段产出）
- `type = "book"`（book 阶段产出，可选）

任一缺失 → render 报 "缺少图片或音频产物"。

# AI图书带货视频创作台 — 开发进度

最后更新：2026-07-04

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
  - 自定义域名：`content.socra.cn` 绑定 Vercel

---

## 下一阶段计划

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P0 | **XHS 端对端测试** | 跑完整流程：新建书籍 → 选题 → 文案 → 卡片 → 导出 ZIP |
| P0 | **Prompt 质量优化** | 跑 3-5 条真实视频，根据输出调整 `prompts/rewrite.txt`、`prompts/clean.txt` |
| P1 | **XHS 卡片样式优化** | 根据实际导出效果调整字体大小、间距、高亮样式 |
| P1 | **渲染模板优化** | `worker/stages/render.py` 字幕样式、字体、9:16 布局深度定制 |
| P2 | **批量任务** | 一次提交多链接，自动队列 |
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

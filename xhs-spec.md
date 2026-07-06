# XHS Content Engine — 技术规格文档 (SPEC)

> 版本：v1.0 | 日期：2026-07-05
> 基于 PRD `xhs-prd.md` 整理，结合现有 `content-ecosystem` 项目架构确认的实施方案。

---

## 一、项目定位

**产品名称：** 小红书图文生成工作台（集成于现有内容创作台）
**核心用途：** 基于电子资料（PDF / 文字），自动化生成符合小红书合规要求的爆款图文内容矩阵。
**品牌人设：** 可配置（默认"大厂工程爸"），每本书单独设定。
**访问入口：** `content.socra.cn/xhs`（现有 Sidebar 已有占位，激活即可）

---

## 二、技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端框架 | Next.js 14 App Router | 沿用现有项目 |
| 样式 | Tailwind CSS（XHS专用）| 仅扫描 `app/xhs/**` 和 `components/xhs/**`，与现有视频模块隔离 |
| 状态管理 | React useState / useReducer | 无需 Zustand，保持轻量 |
| PDF 解析 | `pdf-parse`（服务端 API Route）| 安全，密钥不暴露 |
| 卡片截图 | `html-to-image`（客户端）| 将 DOM 渲染为 PNG |
| 批量导出 | `jszip`（客户端）| 多张 PNG 打包 ZIP |
| LLM — 选题 | OpenAI API（`gpt-4o-mini`）| 现有 `OPENAI_API_KEY` |
| LLM — 文案/卡片 | DeepSeek API | 现有 `DEEPSEEK_API_KEY` |
| 数据库/存储 | Supabase | 新增 3 张表；PDF 存 `artifacts` bucket |

---

## 三、数据库设计

### 3.1 新增表（在 Supabase SQL Editor 执行）

```sql
-- 知识库：一本书 / 一份电子资料
CREATE TABLE xhs_books (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title        TEXT NOT NULL,              -- 书名/资料名
  brand_name   TEXT DEFAULT '大厂工程爸', -- 卡片书眉品牌名（可配置）
  raw_text     TEXT,                       -- 提取后的纯文字内容
  file_url     TEXT,                       -- PDF 原件在 Supabase Storage 的路径
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- 选题矩阵：每本书可生成多组选题
CREATE TABLE xhs_topics (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      UUID REFERENCES xhs_books(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,              -- 爆款标题（≤20字）
  pain_point   TEXT,                       -- 核心痛点
  logic        TEXT,                       -- 内容逻辑
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- 文案草稿：包含正文、评论剧本、卡片数据
CREATE TABLE xhs_drafts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id     UUID REFERENCES xhs_topics(id) ON DELETE CASCADE,
  style        TEXT,                       -- 文风：engineer / emotional / practical
  body         TEXT,                       -- 正文 Markdown
  comments     JSONB,                      -- 评论区剧本 [{role, content}]
  pages        JSONB,                      -- 卡片正文分段数组
  summary      TEXT,                       -- 价值总结
  cta          TEXT,                       -- 互动提问（合规）
  created_at   TIMESTAMPTZ DEFAULT now()
);
```

---

## 四、前端路由结构

```
/xhs
├── page.tsx                  ← 知识库列表 + 新建书籍入口
└── book/
    └── [id]/
        └── page.tsx          ← 书籍详情（4 个 Tab）
            ├── Tab 1: 主题矩阵
            ├── Tab 2: 文案生成室
            ├── Tab 3: 视觉卡片工厂
            └── Tab 4: 书籍设置（品牌名等）
```

**Sidebar 改动：** 将 `active: false` 改为 `active: true`，`href: "/xhs"` 生效。

---

## 五、API Routes

```
web/app/api/xhs/
├── books/
│   └── route.ts          GET 列表 | POST 新建（含 PDF 解析）
├── books/[id]/
│   └── route.ts          GET 详情 | PATCH 更新品牌名
├── topics/
│   └── route.ts          POST 调用 OpenAI 生成选题
├── copy/
│   └── route.ts          POST 调用 DeepSeek 生成文案+评论剧本
└── cards/
    └── route.ts          POST 调用 DeepSeek 切分文本+生成 CTA
```

---

## 六、各模块详细规格

### 6.1 知识库管理（`/xhs`）

**功能：**
- 书籍列表（卡片形式，显示标题、品牌名、字数、创建日期）
- 新建书籍弹窗（Modal）：
  - 书名输入框
  - 品牌名输入框（默认"大厂工程爸"）
  - 内容输入方式二选一：
    - **Tab A：粘贴文字**（Textarea，支持大段）
    - **Tab B：上传 PDF**（`<input type="file" accept=".pdf">`，上传后服务端解析）
- 点击书籍卡片进入 `/xhs/book/[id]`

**PDF 处理流程：**
```
客户端上传 PDF → POST /api/xhs/books（multipart）
→ 服务端 pdf-parse 提取文字
→ 存 raw_text 到 xhs_books
→ 原 PDF 存 Supabase Storage artifacts bucket
→ 返回 book.id
```

---

### 6.1.1 书籍内容独立选取（新增）

进入书籍详情后，`raw_text` 按自然段切分成段落列表展示。

**交互：**
- 每段左侧有复选框，默认全选
- 可取消勾选不相关段落
- 顶部显示"已选 X 段 / 共 Y 段，约 Z 字"
- 所有后续操作（生成选题、生成卡片）只使用**已勾选的段落**

**存储：** 选中段落索引存在前端状态，不持久化（每次进入书籍页默认全选）

---

### 6.2 主题矩阵（Tab 1）

**交互流程：**
1. 顶部输入框：核心痛点（可手填，或从已选段落自动提取关键词建议）
2. 点击【AI 生成选题】→ 调用 `POST /api/xhs/topics`（只传已选段落内容）
3. 返回结果以**卡片形式**可视化展示（非纯表格）

**选题卡片 UI：**
```
┌─────────────────────────────────────┐
│  ☑  📌 标题（可内联编辑）            │
│  痛点：孩子讲题卡壳                  │
│  逻辑：从方法论角度拆解              │
│                                     │
│  [✍ 去生成文案]  [🎨 去生成卡片]    │
└─────────────────────────────────────┘
```

- 每张选题卡可单独勾选
- 顶部有【全选】/【批量操作】
- 选中后可点击【开始创作】进入文案生成室
- 多选时可批量生成文案（逐个排队处理）

**OpenAI Prompt（服务端写死）：**

**OpenAI Prompt（服务端写死）：**
```
System: 你是一个小红书爆款操盘手。
User: 核心痛点：{painPoint}
      书籍内容摘要：{rawText前500字}
      请生成3个爆款选题，标题≤20字，要有大厂降维打击感。
      返回严格JSON：[{"title":"","painPoint":"","logic":""}]
```

---

### 6.3 文案生成室（Tab 2）

**左右两栏布局：**

左侧（参数区）：
- 选题标题（从Tab1带入 或 手动输入）
- 核心知识点（Textarea，从知识库摘取片段）
- 文风选择（3选1）：
  - `engineer`：大厂降维打击风
  - `emotional`：情绪共鸣风
  - `practical`：纯干货实操风
- 【一键生成文案】按钮

右侧（结果区）：
- 正文（Markdown 渲染）
- 评论区剧本（区分小号提问 / 大号回复）
- 右上角：【复制正文】【复制评论】

**DeepSeek Prompt（服务端）：**
```
System: 你是大厂工程师爸爸，写小红书笔记，文风：{style}
        合规红线：绝对禁止"私信""留言送资料""买""链接""加群"等词
User: 标题：{title}
      知识点：{knowledge}
      要求：1.痛点引入 2.揭露假象 3.大厂解决方案 4.价值升华
      额外：生成2条评论区剧本（1条小号提问+1条大号专业回复）
      返回JSON：{"body":"正文markdown","comments":[{"role":"小号","content":""},{"role":"大号","content":""}]}
```

---

### 6.4 视觉卡片工厂（Tab 3）

**左侧输入：**
- 主标题输入框
- 原书内容 Textarea（可从知识库一键导入）
- 品牌名（从书籍设置继承，可临时修改）
- 【AI 智能切分】按钮

**右侧预览：** CSS Grid，多张卡片并排显示

**卡片规格：450px × 600px（3:4），导出时 scale×2 = 900×1200px**

**三类卡片：**

| 类型 | 内容 | 特殊样式 |
|------|------|----------|
| Card 1（封面）| 主标题 | 超大字号，橙色高亮，大留白 |
| Card 2~N-1（正文）| pages[i] 原书文字 | 左侧橙色竖线，书眉（品牌名+页码）|
| Card N（尾页）| summary + cta | 总结文字 + 灰底圆角CTA框 |

**导出流程：**
```
点击【导出整套图文 ZIP】
→ html-to-image 逐张截图（scale:2）
→ JSZip 打包：{主标题}-1.png, {主标题}-2.png ...
→ 触发浏览器下载 {主标题}.zip
```

---

## 七、合规红线（代码层面强制执行）

以下词汇在服务端 Prompt 中设为绝对禁止，同时前端展示结果时做关键词检测并高亮警告：

```
私信 | 留言 | 送资料 | 买 | 链接 | 加群 | 关注 | 点赞 | 收藏 | 求关注
```

---

## 八、UI 设计规范（XHS 模块专属）

```css
/* XHS 模块色值 */
--xhs-primary:   #0A192F;  /* 深海蓝，主背景/标题 */
--xhs-accent:    #FF6B35;  /* 大厂橙，高亮/按钮/竖线 */
--xhs-card-bg:   #F8F9FA;  /* 卡片背景，冷灰白 */
--xhs-cta-bg:    #F1F5F9;  /* CTA 框背景 */
```

字体（卡片内）：`PingFang SC, Microsoft YaHei, sans-serif`

---

## 九、开发顺序（4个 Phase）

| Phase | 内容 | 预估工时 |
|-------|------|----------|
| P1 | DB 建表 + Sidebar 激活 + `/xhs` 基础布局 + Tab骨架 | 0.5天 |
| P2 | 知识库列表 + 新建弹窗 + 文字粘贴 + PDF 上传解析 | 1天 |
| P3 | 选题矩阵（OpenAI）+ 文案生成室（DeepSeek）| 1.5天 |
| P4 | 卡片工厂 + html-to-image + JSZip 导出 | 2天 |

**总计约 5 天**

---

## 十、环境变量（新增）

已有变量复用，无需新增。Worker `.env` 已有：
```
OPENAI_API_KEY=    # 选题生成
DEEPSEEK_API_KEY=  # 文案/卡片生成
```

Vercel 需同步确认这两个变量已配置。

---

## 十一、待确认事项（开发前）

- [ ] Supabase `artifacts` bucket 是否允许存 PDF？（现在只存图片/音视频）
- [ ] DeepSeek API 的 base URL 和 model name（确认现有 config 中的值）
- [ ] OpenAI 选题是否需要流式输出（streaming），还是等待完整结果

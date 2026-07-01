# M0 联调指南

目标：验证「本地 worker ↔ Supabase ↔ Vercel 前端」实时联通。
做完你会看到：在网页粘贴一个链接建任务 → worker 自动逐个处理 8 阶段 → 网页实时显示状态推进 → 到「改写」「书籍信息」两步自动停下等你点「确认继续」→ 全部完成。

> M0 是**假处理**（每步 sleep 2 秒），不真正下载/转写/生图。目的是先打通链路，真实逻辑在 M1+ 接入。

---

## 一、建 Supabase 项目（约 5 分钟）

1. 打开 https://supabase.com → 新建 project（免费档），记住数据库密码。
2. 项目建好后，进 **Project Settings → API**，抄下三个值：
   - `Project URL`（形如 `https://xxxx.supabase.co`）
   - `anon public` key（给前端）
   - `service_role` key（给 worker，**保密，别进前端/git**）
3. 开启匿名登录：**Authentication → Sign In / Providers → Anonymous** 打开。

## 二、建表 + RLS

进 **SQL Editor**，依次粘贴执行这两个文件的内容：

1. `supabase/migrations/0001_init.sql`（建表 + 建 task 自动生成 8 stage）
2. `supabase/migrations/0002_rls.sql`（RLS + Realtime）

执行后在 **Table Editor** 应能看到 `tasks / stages / artifacts` 三张表。

## 三、启动本地 worker

```bash
cd worker
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env      # PowerShell: Copy-Item .env.example .env
# 编辑 .env，填 SUPABASE_URL 和 SUPABASE_SERVICE_KEY（service_role）

python main.py
```

看到 `worker 启动。轮询间隔 3 秒…` 即正常，保持这个窗口开着。

## 四、启动前端

```bash
cd web
npm install
copy .env.local.example .env.local   # PowerShell: Copy-Item
# 编辑 .env.local，填 NEXT_PUBLIC_SUPABASE_URL 和 NEXT_PUBLIC_SUPABASE_ANON_KEY（anon）

npm run dev
```

浏览器打开 http://localhost:3000

## 五、验证联通（关键）

1. 首页粘贴任意一段文字/链接（M0 不解析内容），点「新建任务」。
2. 点进任务详情，观察 8 阶段：
   - 「采集」应很快变「处理中」→「完成」，随后「逐字稿」「清洗」依次推进。
   - **无需刷新页面**——状态是 Realtime 实时推来的。
   - 到「改写」会停在**待确认**（橙色），点「确认继续」→ 继续往下。
   - 到「书籍信息」同样停下，点「确认继续」。
   - 最后「成片」完成，任务总状态变 `done`。
3. 试「重跑」：点任意已完成阶段的「重跑」，worker 会重新处理它。

### 通过标准
- [ ] 建任务后 worker 自动认领，无需手动干预
- [ ] 前端不刷新就能看到状态实时变化（验证 Realtime）
- [ ] 评审门（改写/书籍信息）能停下、点确认后继续
- [ ] 重跑能把某阶段拉回重新处理
- [ ] 8 阶段全绿，任务 `done`

以上全过 = M0 达成，本地↔云↔前端链路打通，可进 M1（真实抖音采集）。

---

## 需要你提供 / 准备的凭证清单

| 用途 | 变量 | 放哪 | M0 必需 |
|---|---|---|---|
| 前端连 Supabase | `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `web/.env.local` | ✅ |
| worker 连 Supabase | `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | `worker/.env` | ✅ |
| 改写/清洗/生图 | `OPENAI_API_KEY` | `worker/.env` | M4/M6 |
| 书名反推 | `DEEPSEEK_API_KEY` | `worker/.env` | M7（没配 fallback OpenAI）|
| 抖音备用解析 | `THIRDPARTY_DOUYIN_KEY` | `worker/.env` | 可选 |

## 常见问题

- **前端报「登录失败」**：Supabase 没开 Anonymous 登录（第一步第 3 点）。
- **worker 报缺环境变量**：`worker/.env` 没填或没 copy。
- **状态不实时更新**：`0002_rls.sql` 里的 Realtime publication 没执行成功，重跑那几行。
- **RLS 拦截**：前端用 anon key 只能看自己匿名账号建的任务；换浏览器/清 cookie 会换新匿名账号，看不到旧任务，属正常。

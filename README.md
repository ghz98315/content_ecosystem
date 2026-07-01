# content_ecosystem

AI 图书带货视频创作台 —— 把「抖音采集 → 逐字稿 → 清洗 → 改写 → 配音 → 生图 → 书籍信息 → 成片」整条链做成单界面 web 工具。

完整方案见 [`docs/DEV_PLAN.md`](docs/DEV_PLAN.md)。

## 架构

```
Vercel(Next.js 前端+轻API) ── Supabase(Postgres/Storage/Realtime/Auth) ── 本地 Python worker(重活)
```

- **web/** —— Next.js 前端，部署 Vercel
- **worker/** —— 本地 Python worker，跑下载/ASR/生图/ffmpeg 等重活
- **supabase/** —— 建表 SQL 与 RLS
- **docs/** —— 开发文档

## 当前进度

M0 骨架：验证「本地 worker ↔ Supabase ↔ 前端」实时联通。联调步骤见 [`docs/M0_SETUP.md`](docs/M0_SETUP.md)。

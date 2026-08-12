# 线上部署可访问 checkpoint

更新时间：2026-08-12

## 部署状态

- GitHub `master` 已推进到 `d878989`。
- 用户确认 Vercel 部署已完成，网页已可打开。
- 本执行环境对两个域名的 HTTP 请求仍受网络策略拦截，无法代替浏览器完成页面验收。

## 浏览器验收入口

- `https://content-ecosystem-neon.vercel.app`
- `https://content-ecosystem.socra.cn`
- 任务工作台：`/video-collection`
- 任务详情：`/task/<task-id>`
- 音色管理：`/voice-cloning`
- 书籍库：`/book-library`

## 当前建议

先在浏览器确认两个域名使用同一 Supabase 匿名会话，再进行脱敏任务的创建和阶段状态检查。真实 TTS、视频生成仍需明确授权后执行。

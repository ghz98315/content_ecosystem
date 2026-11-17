# 图片与成片迁移到 Cloudflare R2

沿用 [原数据平台迁移决策](DATA_PLATFORM_MIGRATION_DECISION.md) 中的私有对象存储方案。本轮保留 Supabase 的登录、任务、阶段、产物索引、文稿、字幕、音频、用户上传封面和知识库。R2 负责 Worker 生成的任务图片和成片，沿用原有对象路径。读取先核查 R2，找不到时读取 Supabase。二次发布复制的图片各自保留独立对象。

## 配置和启用

1. 创建私有 R2 桶，并为该桶生成对象读写 S3 凭据。公共访问保持关闭。仅将 `R2_ACCOUNT_ID`、`R2_BUCKET`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY` 放入 Vercel Production、`web/.env.local` 和 `worker/.env`。Worker 需要安装 `requirements.txt` 中的 boto3。暂未启用时保留 `R2_BUCKET` 为空。
2. 桶的 CORS 允许 `https://content-ecosystem.socra.cn` 的 GET 和 HEAD，允许请求头 Range，并暴露 Accept-Ranges、Content-Range、Content-Length、ETag。参考 [Cloudflare CORS](https://developers.cloudflare.com/r2/buckets/cors/) 和 [私有签名地址](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)。
3. 先部署并启用 Web 读路径，再启用并重载 Worker。测试一条新任务，核对 R2 对象存在、浏览器图片预览、视频播放与下载、二次发布图片复用。新文件开始写 R2 后，回退时仅暂停 Worker 写入，保留 Web 的 R2 读取配置。

## 存量处理

在 Worker 运行环境中执行以下命令。先运行生产的清理预览，过期图片和成片按现有 48 小时清理，源宫格按 24 小时清理。用迁移清单估算剩余源媒体，优先处理存量成片。盘点只统计数据库已登记的生成媒体，不代表项目总存储或账单。

```powershell
python migrate_r2_media.py inventory --limit 10000
python migrate_r2_media.py copy --limit 10000
# Web 和 Worker 已验收，并且迁移窗口内暂停重跑或删除历史任务后
python migrate_r2_media.py remove-verified --limit 10000
```

复制及移除均跳过仍在运行或人工确认的任务。移除前重新读取双方内容并比对大小和 SHA-256，复核任务状态和源对象元数据。源副本移除后，数据库产物路径保持原样。保留期由现有 Worker 和 Web 清理继续执行，复制不会延长有效期。确认最终存储实际下降后结束迁移。已累计的流量和账单周期须在 Supabase 控制台分开核对。

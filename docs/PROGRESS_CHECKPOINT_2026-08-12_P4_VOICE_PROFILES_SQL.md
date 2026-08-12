# P4 音色配置持久化迁移

日期：2026-08-12

## 已完成

- 新增 `supabase/migrations/0015_voice_profiles.sql`。
- 增加 owner-scoped `voice_profiles` 表，记录 Provider、Voice ID、模型、样本路径、授权确认和启用状态。
- 增加 RLS，以及启用/停用和删除 RPC。

## 当前阻断

该 migration 尚未在 Supabase 执行。执行前不继续接入页面读写，避免前端依赖尚不存在的表。

## 下一步

用户执行 `0015_voice_profiles.sql` 后，继续完成 `/voice-cloning` 音色列表、启停、删除确认和创建表单联调，并自动回归构建。

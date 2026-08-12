# P4 音色可用性校验

## 本次完成

- 在批量导入任务创建前重新查询所选 `voice_profiles`。
- 只有当前仍为 `enabled = true` 的 profile 才会写入任务级配音快照。
- profile 被禁用、删除或查询失败时，阻止创建任务并自动切回系统默认 Edge 音色。
- 系统默认 Edge 音色不依赖 profile 表，保持原有创建路径。

## 验证

- `npm.cmd run build`（`web`）通过。
- `git diff --check` 通过；仅有现有工作区换行格式提示。
- 未执行真实远程 TTS、视频生成或付费服务调用。

## 受影响文件

- `web/app/video-collection/page.tsx`

## 下一步

继续 P4 的默认音色策略与 profile 管理边界检查；若不需要新 SQL，则直接开发并在完成后重复回归。

## Checkpoint

未创建本地 git checkpoint commit：工作区存在大量并行改动，当前不具备安全隔离提交条件。

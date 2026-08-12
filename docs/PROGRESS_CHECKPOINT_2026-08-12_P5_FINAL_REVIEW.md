# P5 跨页面验收检查

## 已检查范围

- 首页项目工作台
- 视频采集工作台
- 任务详情页
- TTS 阶段详情
- 音色管理页
- 书籍库页面
- 通用 `DetailShell`

## 已覆盖能力

- 工作区连接中和页面加载骨架
- 空结果与无 artifact 状态
- 查询/签名 URL 失败提示与重试入口
- 任务详情加载失败、任务不存在和阶段为空状态
- TTS 生产音频加载失败、字幕加载失败和重试
- 键盘 `:focus-visible` 样式
- 任务工作区 tab 的 `aria-pressed`
- 任务取消、采集刷新、采集重试的 `aria-busy`
- 移动端 TTS 音频标题、下载按钮和快照提示布局

## 保留的验收边界

- 首页文件仍存在历史压缩/乱码 JSX，未做大范围格式化；其筛选 tab 已有 `role="tab"` 和 `aria-selected`。
- 未执行真实任务端到端验收、截图验收或真实远程 TTS/视频生成，因为当前环境没有执行授权且会产生外部/付费副作用。
- Node 本地为 `v22.x`，项目预期为 `20.x`；当前构建通过但发布前仍应在 Node 20 环境复核。

## 回归证据

- `npm.cmd run build`（`web`）通过。
- `python -m unittest tests.test_video_quality.TtsInputTests -v`：15/15 通过。
- `python -m unittest tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal tests.test_p0_reliability -v`：11/11 通过。
- `git diff --check` 通过；仅有既有换行格式提示。

## 下一步

进入人工验收准备：在 Node 20 环境启动 Web，使用真实或脱敏任务检查桌面/移动端截图、TTS 试听与错误重试；这一步需要用户侧实际环境验证。

## Checkpoint

未创建本地 git checkpoint commit：工作区包含大量并行改动，当前不具备安全隔离提交条件。

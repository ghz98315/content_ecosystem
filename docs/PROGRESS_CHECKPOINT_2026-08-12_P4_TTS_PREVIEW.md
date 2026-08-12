# P4 TTS 第一切片：生产音频与试听隔离

日期：2026-08-12

## 本次完成

- TTS 详情页明确区分完整生产音频与分段试听音频。
- 完整生产音频增加下载入口，并显示为任务音频快照。
- 分段音频改为按需试听并自动播放，试听不会覆盖生产音频。
- 修复 Edge TTS 单元测试的 provider 隔离：测试显式锁定 `edge`，不受本地 `TTS_PROVIDER` 环境变量影响。

## 回归结果

- `npm.cmd run build`（`web/`）：通过。
- `python -m unittest tests.test_video_quality.TtsInputTests.test_edge_tts_receives_plain_text_not_custom_ssml -v`：通过。
- `python -m unittest tests.test_rewrite_confirmation tests.test_manual_clean_revision tests.test_transcribe_book_signal tests.test_p0_reliability -v`：11 项通过。
- 真实 Edge TTS 联网合成未执行；当前环境外部网络不可用，不作为本地回归阻断。
- 本机 Node 为 `v22.19.0`，项目期望 Node 20.x。

## 当前判断

该切片已完成，可进入下一块：音色配置/voice ID 管理。CosyVoice2 仍保持实验性 provider，不切换生产默认值。


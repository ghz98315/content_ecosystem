# 2026-08-10 TTS 复刻音色与网页上传阶段节点

## 已完成

- DashScope SDK `1.26.6` 已安装，并加入 `worker/requirements.txt`。
- CosyVoice DashScope HTTP 非实时合成已接入现有 TTS provider。
- 系统音色 `longsanshu_v3` 已验证成功。
- CosyVoice v3 复刻音色已创建并验证成功。
- CosyVoice v3.5 复刻音色已创建并验证成功：
  - `cosyvoice-v3.5-flash-narrator35-9e4fe951db0d4f81bac6c0aada05738e`
- 增加 voice profile 机制，支持多个模型和 Voice ID 切换。
- 增加显式 `create_cosyvoice_voice.py`，复刻创建不会被普通 worker 自动触发。
- 增加声音样本上传页和服务端签名 URL 接口。
- 商用化网页优化规划已整理为 `docs/WEB_UI_COMMERCIAL_OPTIMIZATION_PLAN.md`。

## 当前正式配置意图

- `TTS_PROVIDER=cosyvoice2`
- `DASHSCOPE_MODEL=cosyvoice-v3.5-flash`
- `DASHSCOPE_VOICE_PROFILE=cloned_narrator35`
- Edge 保留为手动兜底，切换 `TTS_PROVIDER=edge` 后重启 worker。

## 已验证命令

- `python -m unittest tests.test_video_quality.NetworkRetryTests.test_cosyvoice2_provider_is_isolated_and_requires_configuration tests.test_video_quality.NetworkRetryTests.test_cosyvoice2_openai_compatible_audio_response -v`
- `npm.cmd run build`（web）
- v3.5 复刻音色隔离试听：`worker/tts-comparisons/narrator35-cloned-20260810/`

## 下一步

部署本节点相关文件后，创建一条新的完整任务，验证 ingest 到 render 的第一阶段生产流程。新任务验证期间不改变网页视觉规划，不开启多风格成片等未实施能力。

## 风险与边界

- `.env` 和真实 API Key 不进入 Git。
- 当前 worker 的生产切换需要重启后才读取新的环境变量。
- Edge 不做自动混合回退，避免同一任务出现两种音色；故障时手动切换并重启。

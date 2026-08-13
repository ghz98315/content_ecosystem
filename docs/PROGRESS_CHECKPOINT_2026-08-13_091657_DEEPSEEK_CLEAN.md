# DeepSeek 清洗模型拆分 Checkpoint

时间：2026-08-13 09:16（Asia/Shanghai）

## 开发素材卡

阶段：开发阶段，次阶段为回归与部署准备。

本轮主题：将逐字稿清洗从通用 OpenAI 客户端拆分到独立 DeepSeek 客户端。

关键模块：Worker 清洗阶段、模型配置、环境变量模板和质量回归。

解决的问题：清洗与改写共用模型入口，难以独立控制成本、温度和模型职责；模型配置混用也容易导致清洗请求发往错误的服务地址。

用户可感知变化：清洗阶段固定使用 `deepseek-chat`，改写、生图、TTS 等阶段保持原配置；异常扩写上限、自动严格重试和前 10 秒钩子保护继续生效。

关键设计决策：

- 新增 `config.clean_client()`，只读取 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_BASE_URL`。
- `CLEAN_MODEL` 默认改为 `deepseek-chat`，请求温度设为 `0.2`，兼顾稳定输出和必要的 ASR 纠错。
- 缺少 DeepSeek Key 时明确失败，不静默回退到其他模型，避免模型职责漂移。
- 密钥只保存在已被 Git 忽略的 `worker/.env`，不进入代码、文档或提交记录。

验证证据：

- `python -m unittest tests.test_video_quality -q`：73 项通过。
- `git diff --check`：通过。
- DeepSeek 官方兼容接口最小真实请求：`deepseek-chat` 正确完成错字修复。

待验证边界：代码尚待推送和部署；线上 Worker 重启后，需要对失败的清洗阶段执行一次重跑，确认真实长文清洗结果及长度变化。

可写角度：把内容生产流水线中的“大模型”拆成有清晰职责、可独立验收的模型工位。

可直接引用句：清洗模型可以更换，但钩子保护、长度拦截和人工确认不能跟着模型一起消失。

## 影响文件

- `worker/config.py`
- `worker/stages/clean.py`
- `worker/.env.example`
- `worker/tests/test_video_quality.py`

## 下一步

提交并推送本次改动，部署后重启 Worker；对当前失败清洗阶段执行重跑并检查清洗稿与原稿差异。

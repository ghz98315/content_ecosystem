# 运行与移交

Python 3.10+。基础安装（选择调用项目的虚拟环境）：

```text
python -m pip install -r SKILL_DIR/scripts/requirements.txt
```

媒体转写按需安装：

```text
python -m pip install faster-whisper numpy imageio-ffmpeg
```

TXT/MD 输入和单独清洗不需要 Whisper、FFmpeg、GPU 或大模型 API Key。本地音视频导入只复制文件，ASR 时才需要媒体依赖。Whisper 首次使用会下载模型，可用 --model 指向已存在的 faster-whisper / CTranslate2 模型目录；离线时先准备本地模型。

## 平台配置

视频号需要当前用户有权使用的 YUANBAO_COOKIE。指定调用项目私有 .env 的绝对路径：

```text
python SKILL_DIR/scripts/pipeline.py ingest --input "视频号分享链接" --out "输出目录" --env-file "私有配置文件路径"
```

也可在进程环境配置 YUANBAO_COOKIE。抖音公开分享页可先匿名读取；需要 Cookie 时用 DOUYIN_COOKIES 指向 Netscape cookies.txt。登录失效、验证或平台变化时停止，不循环刷新登录、不抓取其他项目凭据。仅读取固定抖音域名分享页；没有媒体时上传原文件。当前独立包未包含 f2 的匿名令牌和签名回退，不保证与映作所有旧解析分支完全相同。

## 参数

- transcribe：--model small（可传本地目录）、--device cpu/cuda、--compute-type int8/float16、--language zh、--no-vad、--force。
- ingest：单文件上限300MiB；新输出目录，不覆盖已有 manifest；只支持视频号及抖音链接、本地文件。不接受任意网站媒体直链。
- prepare-clean：--category general/guoxue/health/social_science/scene/education。
- finish-clean：读取 cleaned.txt，输出差异与统计，不自动重写；清洗后不重新对齐音频。

## 产物与状态

manifest.json 保存 schema_version、输入类型、各阶段状态/耗时、依赖下一步及安全错误提示。source.json 只保存分享链接/本地来源、标题、作者和平台可用统计，不保存 Cookie、播放 token、签名媒体链接。点赞不是播放量，未返回的统计不写成0。

transcript.json 包含 text、language、duration、segments/words、timing_available 和 asr_signature；文本导入时 duration=null、segments=[]。cleaned.json 包含 raw、cleaned、opening_hook、category、counts、quality_warnings；diff.md 是两稿逐行差异。模型结果或书名来源仍需人工抽查。

复用后续项目时保持这套文件约定，外部系统如需数据库再写适配器；本包不会连接 Supabase、启动映作任务或调用配音。

## 来源与可移植安装

来源：映作项目 worker/stages/ingest.py、transcribe.py、clean.py 及 resolvers 的2026-11-26实现。独立包保留平台解析边界、FFmpeg PCM 解码、词级时间戳、CPU回退、开头保留与清洗差异审查；移除数据库/存储绑定和收费清洗接口，使用当前 Codex 执行清洗。类别规则保留在 references/clean/，general 为通用保真规则。

把 media-transcript-clean 整个文件夹复制到 Codex 用户技能目录 ~/.codex/skills/，即可跨项目发现；也可放目标项目 .agents/skills/ 仅该项目使用。在新的聊天调用 $media-transcript-clean；当前未刷新列表时可显式要求读取完整 SKILL.md 路径后执行。WorkBuddy 可以读取相同 SKILL.md 和脚本，但它的安装位置/发现方式需按当前客户端配置，不能保证与 Codex 全局目录自动互通。

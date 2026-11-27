# 映作工作台 · 项目状态与 WorkBuddy 接管说明

## 当前交接点

- **2026-11-27 分镜标签防复发**　172581d8 已成片，Windows 守护程序 15:38:29 已启动新 Worker（PID 31044）。共用分镜报错采用阶段名称，本机源码已加载，真实任务错误分支未重跑；Web 旧前缀兼容未上线。

- **2026-11-27 女性成长任务生图重跑完成**　172581d8 生图已 done，成片运行中。11 月 21 日启动的常驻 Worker 沿用旧错误标签，数据库分类仍为 health。分镜批次校验补强已在本机验证，常驻进程待成片结束且队列空闲后重载。

- **2026-11-26 独立前置采集 Skill 已交付**　`skills/media-transcript-clean/` 脱离 Supabase，支持采集、逐字稿、清洗分别调用；已安装本机 Codex 全局技能目录，跨目录6项离线验证通过。压缩包 `worker/output/media-transcript-clean.zip`，不含凭据、缓存或原稿；本轮不涉及生产 Web/Worker 部署，详见下方记录。

- **2026-11-26 视频号图文采集误报已修复**　`289e8bcb-c292-479f-8866-52b53b11e709` 为图片配乐内容，无视频地址；已区分图文、缺少地址和不可信地址，19 项采集测试通过，真实解析已核验并更新当前任务提示。任务仍等待用户上传原始文案 TXT/MD 或含朗读的视频/音频。修复位于本机 Worker 源码，无 Web 和数据库迁移，远端状态见下方记录。

- **2026-11-24 发布包购书评论固定引导已完成**　购书评论现由“联系本篇痛点的价值共鸣段 + 系统固定购书步骤”组成；系统只使用确认稿中真实出现并能确定的书名，生成和保存时都会去重追加，无明确书名或无购书内容时不强行添加。发布包契约测试与 Web TypeScript 检查通过，本地已提交；GitHub HTTPS 连续 TLS 中断，尚未推送和触发 Vercel。

- **2026-11-23 女性成长分镜编号已恢复**　任务 `1b58f006-ea32-4d03-8ac9-66edf93a0e00` 实为 health，不是历史哲科；共享胶片写实规划器的后续批次误从 1 编号，现可安全映射回全片编号。画面已完成并进入成片。提交 `1f32501` 已重新推送，GitHub/Vercel 状态 success。

- **2026-11-23 视频号瞬时下载恢复已验证**　任务 `28f0c5c2-e7fe-4acb-a863-6f18505ca122` 已修正为用户提供的分享链接并重跑，采集成功、音频已入库，现进入逐字稿。提交 `4bbaf57` 已推送；下载器支持最多 3 次重试及断点续传，仍保留腾讯域名、容量、时长和 Cookie 隔离边界。

- **2026-11-23 中段留存抓手已发布**　女性成长健康与历史哲科新增按篇幅分布的留存抓手规划与程序审查，改写确认页可直接查看正文锚点、抓手功能和继续收听理由。提交 `44a58fb` 已推送，Vercel 状态 success；新任务或重跑改写加载 Skill 1.6.2 / history-1.3。真实长稿的模型产出与业务听感仍待新任务验收。

- **2026-11-21 二创听感优化待发布**　历史哲科与女性成长/健康规则已合并完成，本地提交 `b34154b`，74 项定向回归通过。GitHub HTTPS 推送被 TLS 中断，线上 Web 与常驻 Worker 尚未更新。女性成长测试任务 `f7e3b72f-9f01-46d0-a99d-d3d84d2d1a8c` 仍是旧版 `skill 1.5.0` 稿件待确认；页面重跑确认未落库，数据库时间未变化，未继续配音、生图或成片。

- **2026-11-21 配音时间戳与配乐音量**　ff07ea6 已推送，Vercel success、线上资源含 20% 默认值。Worker 15:18:38 重载，云心跳 online；0046 已在新项目 SQL Editor 执行并查询确认 `tasks.bgm_volume` 默认 0.20。c492 任务最新外部配音已 approved，所有阶段含成片 done。28 项 Worker 测试、Web TypeScript 与生产契约通过；历史任务的已保存音量未批量覆盖。
- **外部配音零时长词**　110be2a 与后续边界修复 ff07ea6 均已上线。c492 原音频曾过期清理；新版本音频已获批，配音与成片均 done。旧失败版本仅作历史记录。

- **R2 媒体分流**　兼容代码 f0ec8ee 已推送，R2 未启用。原规划见 DATA_PLATFORM_MIGRATION_DECISION.md，本轮切换见 R2_MEDIA_CUTOVER.md。Worker 和 Web 本地环境未找到 R2 凭据，生产未迁移或删除源对象。

- **本地素材导出与配乐默认授权**　1d4c24a 已推送，线上页面已核验。Worker 等成片空闲重载。Worker 高清成片使用北京时间 MMDD 加标题，Web 所有选用的配乐默认勾选授权。

- **队列与改写服务已恢复**　11-14 19:49:47 常驻 Worker 重启并确认心跳更新；09c90b2d 采集、逐字稿和清洗完成，两条任务此前均因 xcode.best 连接失败。代理规则更新后已确认两条均收到模型正文，09c90b2d 已保存稿件待确认。

- **历史哲科配乐**　已部署，历史哲科预设上传、列表、试听及删除已通过线上检查。生产重复曲目已清理。

- **口播出处措辞**　已部署至常驻 Worker，待真实稿件验收。

- **女性成长 AI 画风与人物封面**　已部署至生产，提交 `5b50e24`，Worker 17:56:29 重载并核实心跳在线。女性成长与健康共用模板；新建的 AI 任务采用历史社科胶片写实风与全文封面。旧模板快照仍可运行。各内容线常规分镜统一为 90–120 有效字。

- **二次发布已上线**　生产 0045 已核实，Web 已加载新版入口，Worker 13:10:44 重载并在线。首发图齐全复用、缺图重生的业务实跑待验收。

- **公众号编辑资料**　2026-11-13 封存到 `docs/wechat-handoff-2026-11-13.zip`，包括三篇细纲、三张配图、交接说明与深圳样片素材。后续补真实录屏、同稿计时对照和发布材料合图。
- **最近更新**　2026-11-13，中国标准时间。发布包与改写封面共同确认已上线，已清理用户下载完成的历史生成媒体。
- **本机仓库**　`D:\github\content_ecosystem`。当前本地与 GitHub `master` 已核实为发布提交 `ff07ea6`。仓库中保留先前的无关工作区修改与未跟踪资料。
- **媒体保留**　云端成片和生成图片保留 48 小时，源宫格 24 小时，本机高清导出 7 天。Worker 已重载在线，线上 Web 定时入口已可达，未验证带凭据的本次定时执行。
- **本地工作区**　历史社科第五版样图留在忽略目录 `worker/output/history-layout-reference-preview-v5.png`。其他历史资料和运行产物仍在本机。原有的 `0025_visual_reference_framework.sql` 修改和未跟踪的旧迁移未纳入本次发布。
- **线上状态**　生产 Web 已加载 ff07ea6 的 20% 默认配乐选项，常驻 Worker 重载并核实心跳在线，数据库默认值已确认 0.20。c492 的配音与成片阶段均 done。[生产工作台](https://content-ecosystem.socra.cn/) · [Vercel 部署列表](https://vercel.com/ghz98315s-projects/content-ecosystem/deployments)
- **数据环境**　本机 `web/.env.local` 与 `worker/.env` 已确认都指向 Supabase 项目 `kzscdqscuxildtofxzww`。Vercel 环境变量、连接权限、实际迁移和线上存储容量需要分别核实。旧项目 `fdbnjfzfdxtlqqtgbzgs` 曾因配额受限，恢复和历史数据迁移未确认。

## 项目概览

Next.js 工作台和轻量 API 在 Vercel，Supabase 管理账号、任务、阶段、产物和存储，Windows 上的 Python Worker 负责采集、转写、二创、生图或选素材、对齐和 FFmpeg 成片。Vercel 和 Worker 分别发布。

- **主流程**　采集链接或导入稿件 → 转写与清洗 → 二创审阅 → 配音或上传音频 → 对齐字幕、准备画面与书籍信息 → 成片 → 发布文案。已写好的稿件可跳过前置步骤。阶段可按任务模式调整，排查时看实际 `stages.kind`、状态、参数、错误及产物。
- **内容线**　国学 4:3 工笔淡墨四宫格；女性成长与健康生活 4:3，新 AI 模板与历史社科共用古典胶片写实画风，另可用公共或本地素材；山河人文 9:16 写实风光四宫格，支持独立封面；历史社科 4:3 古典胶片写实；经管 9:16。比例指当前模板画面，成片可以是含背景填充的竖屏。模板以 `web/lib/productionTemplateManifest.json` 和任务保存的模板设置为准。
- **二创与审稿**　各类别的单人口播共用程序化有效字数、正文完整性和本地字面复用检查。健康 100%–110%，历史社科及山河人文 90%–110%，国学与其他类自动目标至少保留 95%，执行参考 85%–110%。历史哲科只逐字锁定前 3–4 句；识别到的文末荐书段保留书名和转化意图后允许重塑听众价值。健康「只精修」模式记录复用分数；双人播客走独立对话规则。分数是与来源稿的本地比较，文皮皮结果需另行测定。
- **配音与素材**　支持外部配音和重新对齐，也支持内置配音。符合条件时可复用旧画面轨。素材来源有 AI 生图、公共素材和本地素材。素材库位于本机 `D:\Obsidian\99_剪映素材库`，公用书封目录为 `剪映公用素材库\90_书籍封面`。接管后先核对任务选中的素材来源及 Worker 是否能访问目录。
- **历史社科及新女性成长 AI 生图封面**　改写、生图和成片页可上传任务封面。生图前上传或命中本地人物封面时，九宫格全部用于正文。无匹配时按确认全文设计封面，取首批左上格，后续正文镜头从首批第二格开始。生成封面、提示词和来源可在生图页查看。
- **上传封面**　预览与成片按顶部对齐显示 4:3，宽图左右居中裁剪。成片对裁后的封面等比放大至至少 1080 像素宽，并轻度锐化。
- **产物与运营**　任务、原稿、二创稿和采集记录需要保留。媒体有独立清理流程，实际清理期限和待清理范围以当前部署及配置为准。发布包、播放数据及账号功能的当前线上表现按需单项核验。

### 排查入口

- 新建任务、模板和类别　`web/components/ProductionSetup.tsx`、`web/lib/productionTemplateManifest.json`、`worker/production_templates.py`。
- 改稿、审稿与断点恢复　`worker/stages/rewrite.py`、`worker/rewrite_review.py`、`worker/rewrite_editorial.py`、`worker/rewrite_checkpoint.py`、`skills/book-video-rewrite/`。
- 配音、字幕和修复入口　`web/app/api/narration/route.ts`、`worker/stages/external_narration.py`、`worker/external_alignment.py`、`worker/stages/tts.py`。
- 生图、选材和成片　`worker/stages/image.py`、`worker/local_materials.py`、`worker/local_material_history.py`、`worker/stages/render.py`。
- 任务领取和耗时　`worker/main.py`、`worker/db.py`、`worker/stage_timing.py`。媒体留存　`worker/media_retention.py`、`web/app/api/maintenance/media-retention/route.ts`。
- 历史资料　[架构初查](ARCHITECTURE.md)、[旧交接单](HANDOFF_TO_CODEX_2026-11-10.md)、[项目历史检查点](../PROGRESS.md)、[历史部署手册](DEPLOYMENT_RUNBOOK.md)。其中的域名、提交号、环境状态和待办要按本页的最新记录复核。

## 最近变更与接手位置

### 2026-11-27 · 分镜类别误标防复发 · 源码完成

- 共用分镜报错统一使用“画面分镜”，页面仅对 image 节点的旧类别前缀做显示兼容。常驻 Worker 在两阶段之间发现分镜模块更新后退出，由现有 Windows 守护程序重载。任务分类继续以业务字段为准。
- 涉及 worker/history_visuals.py、worker/main.py、worker/tests/test_history_workflow.py、web/components/detail/_shell.tsx。历史画面 21 项测试、Worker 语法、Web TypeScript 和 git diff --check 通过。172581d8 已成片；队列空闲时停止旧 Worker，由守护程序重启。暂存区已核实为空，自动审批拦截提交与推送 master 的组合操作，未提交、未推送及未部署 Web。

### 2026-11-27 · 女性成长任务分镜误标及首批校验 · 生图重跑完成

- 数据库类别为 health。领到失败重跑的是 11 月 21 日启动的常驻 Worker PID 30368，早于 11 月 23 日修正共用规划器错误标签的提交。仅重排失败 image，保留上游，旧进程先领单，最终 image done（15:33:34），随后进入 render。未重复提交。
- worker/history_visuals.py 增加异常批次一次重试、安全编号归位和预期/返回编号诊断。21 项历史流程测试通过。源码未提交或推送，无 Web 变更。为保护正在成片的同一任务，常驻进程暂未重载，待队列空闲后启用新版。

### 2026-11-26 · 采集逐字稿清洗跨项目 Skill · 已交付及全局安装

- 按用户要求独立封装三个前置节点到 `skills/media-transcript-clean/`，本地文件产物替代 Supabase；视频号解析和抖音公开分享页复用现有模块，ASR 使用 faster-whisper，清洗由调用 Skill 的 Codex 执行。提供 general 及5类现有清洗规则，保留开头、统计和差异报告，字数变化只提醒，不触发自动重写。
- 交付15个文件（入口、UI信息、规则、脚本及依赖），本机全局安装在 `C:/Users/ghz00/.codex/skills/media-transcript-clean`；ZIP 在 `worker/output/media-transcript-clean.zip`。归档只包含 py/md/txt/yaml，排除缓存、环境文件及真实资料。其他项目新聊天用 `$media-transcript-clean`；若列表未刷新可显式读取入口路径。
- 验证：源包和全局安装分别6项离线测试通过；Skill quick_validate 两处通过；CLI --help 和 git diff --check 通过。全局安装测试从仓库外临时目录启动，代码没有导入项目 db/storage/config。验证涵盖虚构文本全链、缓存命中/源变化失效、差异提示、重复导入保护、错误凭据脱敏、图文识别、模拟词级时间与CUDA回退。
- 限制：未在独立包调用真实平台或下载Whisper模型，未实测真实音频识别；ASR测试为模拟模型。视频号需调用者自己的登录态，抖音只含公开分享页，无 f2 签名回退；清洗使用当前Codex而不是原DeepSeek API，听感与错词仍需抽查。用户级Skill不等于WorkBuddy自动发现，WorkBuddy需显式加载或按客户端安装。未调用收费模型，未改真实任务，未部署或重启生产Worker。本轮仅本地保存和提交，远端发布不属于本次运行要求。

### 2026-11-26 · 视频号图文误报媒体地址 · 修复及真实核验完成

- 任务 `289e8bcb-c292-479f-8866-52b53b11e709` 实测响应为 `mediaType=2`，包含 `picInfo` 和 `bgmInfo`，无 `videoUrl/h264VideoInfo.videoUrl`。现有视频采集器把空地址误报为非预期域名；已补充内容类型判断和明确的上传文案兜底，保留媒体域名限制，不把背景音乐当逐字稿来源。
- 涉及 `worker/resolvers/wechat_channels.py`、`worker/tests/test_wechat_channels.py`。19 项视频号采集测试、`git diff --check` 通过；使用新版代码真实解析该链接，确认为图文分支，仅将当前 ingest 的错误提示更新为上传 TXT/MD 或含朗读的视频/音频，其他阶段和产物未修改。没有可用的视频音轨，未伪造采集成功，也未自动采用73字符的简介代替完整原稿。
- 本机按任务 Worker 下次启动加载新版代码；已运行进程未强制重启。无 Web、迁移或配置改动。提交 `51992db` 已 HTTPS 推送远端 master；同时带出此前待推送的发布包提交 `979bfaa`，其 Vercel 部署状态未验证。当前图文任务仍 needs_review，等待原始文案或含朗读的素材。

### 2026-11-24 · 发布包购书评论固定引导 · 本地已提交，推送受阻

- 已把购书评论拆成“结合本篇文案痛点的价值段 + 系统固定购书步骤”。模型只写100字以内的价值段，必须抓取本篇的具体处境、矛盾、遗憾或痛点并说明书籍能带来的实际帮助；禁止用“读经典、学智慧、值得一读”等空话代替价值。
- 系统从最终确认稿的书名号中选择真实书名：只有一本时直接采用；有多本时必须由价值段明确选中主要推荐书。生成和保存都会去除旧模板再按四行固定格式追加，防止漏行、改格式和重复。没有明确书名、购书评论为空或山河人文无商品时不强行添加。
- 涉及 `web/lib/publication.ts`、`web/app/api/publication/route.ts`、`web/components/detail/PublicationPanel.tsx`、`web/tests/publication_contracts.mjs`。验证：`node tests/publication_contracts.mjs` 通过；`node node_modules/typescript/bin/tsc --noEmit --incremental false` 通过；`git diff --check` 通过。本地提交起点为 `7e2fa58`（交接状态更新后会 amend，最终提交号以 `git log -1` 为准）。SSH 因本机无公钥被拒；HTTPS 用 Schannel 和 OpenSSL 多次重试均被远端提前断开 TLS。未推送、未触发或核验 Vercel；网络恢复后推送当前 `master` 即可。

### 2026-11-23 · 女性成长健康分镜批次编号恢复 · 已修复并实跑验收

- 任务 `1b58f006-ea32-4d03-8ac9-66edf93a0e00` 已核实为 `health` 类别，改写领域 `health`、模板 `health-v1`、4:3 及 `content_line=health` 均正确；不是误选历史哲科。女性成长健康按既定规则共用胶片写实画面规划器，旧错误文案固定写成“历史社科分镜”，导致类别观感错误。
- 实际失败为第 19–24 镜批次返回了批内编号而非全片编号。已增加确定性归一：当镜头数量、顺序完整且编号恰为本批 1–N 时，按批次位置安全映射回全片编号；其他错序、缺镜或重复仍阻断生图。健康线错误标题同步改为“女性成长健康分镜”。
- 验证：21 项历史/女性成长画面流程测试通过，覆盖后续批次从 1 重新编号的自动映射及女性成长专属错误标题；`git diff --check` 通过。提交 `1f32501` 已在网络恢复后推送到远端 `master`，GitHub/Vercel 状态 success；本机任务 Worker 已加载当前代码。
- 任务实跑：只恢复 image，复用已完成的确认稿、外部配音和字幕。画面阶段越过原第 19–24 镜错误，登记 2 个生图批次后完成为 `done`；book 随后完成，render 已进入 `processing`。未重跑改写、配音或字幕。

### 2026-11-23 · 视频号瞬时下载中断闭环 · 已修复并实跑验收

- 任务 `28f0c5c2-e7fe-4acb-a863-6f18505ca122` 两次在视频号媒体下载阶段进入人工确认。数据库保存的分享链接后缀为 `AhHMAu5RTR`，用户本次提供的是 `AaeQgmOxLM`；两条链接均已安全验证可解析，腾讯媒体 CDN 当前直连和系统代理均返回 206，文件约 31.7 MB 并支持范围请求，登录态与解析接口不是本次根因。
- 根因是现有下载器遇到一次 `httpx` 连接或读取中断就直接失败，没有重试或断点续传。已为腾讯受信媒体地址增加最多 3 次有限重试及按已下载字节续传，仍保留 300 MB、300 秒、跳转域名校验和不携带登录 Cookie 的安全边界；最终失败提示会明确说明自动重试已用完。
- 验证：视频号 16 项测试通过；模拟首段下载后读取超时，第二次请求从 `Range: bytes=4-` 续传并拼出完整文件。真实链接用新版下载器完整取得 31,697,188 字节，临时文件随即删除。扩展 `test_video_quality` 运行时间过长且无失败输出，人工停止，未作为本次通过依据。`git diff --check` 通过。
- 发布与任务：提交 `4bbaf57` 已推送到远端 `master`，无 Web 或数据库迁移。任务链接已修正为 `AaeQgmOxLM`；因后台服务凭据不能代替用户身份调用 `rerun_stage`，在确认任务无处理中阶段后仅将失败的 ingest 恢复为 pending 并启动限任务 Worker。实跑结果 ingest `done`、音频路径已登记、transcribe `processing`，其余下游按原任务继续。

### 2026-11-23 · 女性成长健康与历史哲科中段留存抓手 · 已推送部署

- 现有规则原先主要保护开头钩子、核心反差和情绪推进，缺少可量化的中段抓手分布检查。现为女性成长健康与历史哲科增加 `retention_beats`：按正文约每 450–550 个有效字规划一处、至少 2 处最多 8 处，必须引用成稿真实锚点并写明功能及继续收听理由，同时检查前中后分布；禁止以虚假悬念、恐吓、健康焦虑、连续反问或夸大事实留人。检查不通过会进入现有有限返工，最多仍为 3 次，达到上限后保留稿件供人工确认。
- 改写确认页新增「中段留存抓手」清单，展示抓手类型、正文原句和继续收听理由，便于人工判断是否真实兑现。涉及 `skills/book-video-rewrite/`、`worker/prompts/`、`worker/rewrite_skill.py`、`worker/stages/rewrite.py`、`web/components/detail/RewriteReviewPanel.tsx`。
- 验证：规则包 `quick_validate.py` 通过；二创、确认、编辑审查、口播和历史流程共 77 项 Worker 回归通过；Web TypeScript 检查通过；`git diff --check` 通过。提交 `44a58fb` 已推送到远端 `master`，GitHub/Vercel 状态 success。无数据库迁移；Worker 为按任务启动，新任务或重跑会从当前工作区加载新版。未调用真实模型，真实长稿的抓手质量、密度和业务听感待新任务验收。

### 2026-11-22 · 二创事实影响分层与三策略 · 已推送部署

- 通用、历史哲科、女性成长健康规则新增事实影响分层：人物经历、年代、精确数据、归属、医学结论和关键因果等重要事实须对应信息卡或已核验依据，偏差直接修正文稿且核对过程只留审稿区；普通起居、情绪、家庭相处及共鸣性低风险场景可自然补充或同级替换，无需逐项举证，但不得变成具名经历、精确数据、医疗效果或关键因果。
- 深度二创统一至少组合三种实质策略并记录落点；历史规则版本升至 history-1.2，通用/健康 Skill 升至 1.6.1。规则包校验和75项 Worker 回归通过，`git diff --check` 通过；提交 `91951bc` 已推送到远端 `master`，GitHub/Vercel 状态 success。Worker 为按任务启动，新改写任务会直接加载新版代码；真实稿件的三策略、事实修正和审稿信息展示仍待业务任务验收。

### 2026-11-21 · 历史哲科旧锁定稿改为人工确认 · 已发布

- 用户在历史哲科确认页遇到“锁定钩子和转化结尾须逐字保留”阻断。已兼容旧改写产物：页面不再阻止人工提交，Worker 不再把已确认的人工稿退回待确认；原钩子或原转化结尾被修改时保留醒目提示及最终复核指标。
- 涉及 `web/components/detail/RewriteDetail.tsx`、`web/components/detail/RewriteReviewPanel.tsx`、`worker/stages/rewrite.py` 和历史工作流测试。75 项 Worker 回归、Web TypeScript 和 `git diff --check` 通过；提交 `58916cb` 已连同前一批 `b34154b` 推送到 `master`。GitHub/Vercel 状态 success，生产任务页 200，线上 chunk 已检出“系统不再阻断提交”和“原转化结尾 · 可人工改写”。
- 生产队列发布时无 processing 阶段。Worker 为任务级按需进程，用户刷新历史哲科稿件并再次点击确认后，watchdog 会用当前工作区新版代码接续。最近的历史哲科待确认任务为 `b256cebe-acf1-435e-b014-9d48edb6438b`；未替用户确认稿件，也未运行下游阶段。

### 2026-11-21 · 历史哲科及女性成长二创听感优化 · 已提交，待推送和实稿验收

- 用任务 `f7e3b72f-9f01-46d0-a99d-d3d84d2d1a8c` 的《局外人》原稿与改写稿复核女性成长与健康生活规则。新规则保留人物冲突、生活场景、对话、文学意象和关键观点，移除“未必、不必、不等于”等密集防御性解释，把疑点留在审核信息，并加强书籍对45岁以上听众的具体阅读价值。医学内容仍保留诊断、用药、治疗、疗效和替代医疗边界，普通生活建议不逐条补免责句。
- 历史哲科规则同步纳入本批：只锁开头钩子，荐书结尾保留书名与意图后可重塑；保留来源场景、案例及对话，移除口播免责腔。两类规则均接入有限自动返工检查。任务 f7e3 当前 `health / health-v1`，改写 `needs_review`，下游待运行；锁定钩子中的“她说”疑似应为“他说”，未静默修改，需在人工确认时处理。
- 本地验证：规则包结构校验通过；Python 语法检查通过；改写确认、编辑审查、相似度、规则路由、口播风格和历史工作流共 74 项测试通过；`git diff --check` 通过。本地提交为 `b34154b Refine history and growth rewrite voice`。
- 发布与实稿：两次 HTTPS 推送均因 GitHub TLS/连接中断失败，本机 `127.0.0.1:17890` 未监听，远端与 Vercel 未更新，常驻 Worker 未重载。工作台点击任务 f7e3 的“重跑当前阶段及下游”并确认，但数据库复查显示 rewrite 仍为 2026-11-21 15:47:05（北京时间）旧 `needs_review`，页面操作没有落库；限任务 Worker 因无 pending rewrite 立即退出。因此当前页面仍显示旧 `skill 1.5.0`，不是本轮 1.6.0 验收结果。
- 下一步：恢复可用的 GitHub/代理连接后推送 `b34154b`，确认 Vercel 发布；在生产队列安全时重载 Worker。随后从任务 f7e3 正常重跑“改写”，仅启动该任务 `rewrite`，验收 `prompt_version/rewrite skill 1.6.0`、字数 100%–110%、防御性措辞密度、枯树/飞鸟/领带/“温柔的冷漠”及默尔索冲突是否保留，并停在人工确认。锁定钩子中的“她说”应人工改为“他说”。

### 2026-11-21 · 历史哲科二创听感优化 · 本地完成，未部署

- 按荣格原稿与现有成稿的对比结果优化历史哲科专属规则：删除口播中的免责和考证说明，保留并生活化改写来源稿已有的场景、案例与对话，增强45岁以上听众的对象感，并强化书籍价值塑造。对话可改写但保留人物关系、问答方向与观点作用；事实疑点继续留在审核元数据，不混入口播。女性成长与健康规则本轮不修改。
- 历史哲科从“钩子＋荐书尾段逐字锁定”改为只锁定开头钩子；来源荐书段留作审核对照，模型可重塑痛点、阅读价值、对自己与家庭的帮助及自然阅读引导。新增历史专属后置检查，命中免责句、连续转折开段或反复“不是……而是……”时进入既有返工循环。
- 涉及 `skills/book-video-rewrite/references/history.md`、`worker/prompts/categories/social_science/history_rewrite.txt`、`worker/rewrite_skill.py`、`worker/spoken_style.py`、`worker/stages/rewrite.py` 及定向测试。规则包结构校验通过；Python 语法检查、5 项口播检查单测、规则顺序/版本及尾段解锁的独立校验通过，`git diff --check` 通过。完整测试因当前基础运行时缺少项目依赖且临时安装下载过慢未完成；未调用真实模型、未改真实任务、未提交、未推送、未重载 Worker、未部署。

### 2026-11-21 · 外部配音时间戳闭环与配乐默认值 · 已发布并验收

- c492 的识别词「所以」被 ASR 标为 44.45–44.45；已发布的 110be2a 会用相邻有效时间修复。补充相邻词共用边界时从邻词借短时长、整段识别时间全为零时明确失败，避免假对齐。改动在 `worker/external_alignment.py` 与定向测试；实际源音频已按 48 小时清理，用户重传后才能验收此任务。
- 新任务配乐默认 20%：`web/lib/musicPresets.ts` 统一首页和采集入口，采集选择器保留 10% 作为手动项；`worker/stages/render.py` 缺省值 20%；0046 迁移修改数据库默认值。旧任务的已存音量不回写。涉及 `web/app/video-collection/page.tsx` 和 `supabase/migrations/0046_default_bgm_volume_20_percent.sql`。
- 本地验证：`python -m unittest tests.test_external_alignment tests.test_external_narration` 28 项通过；`node node_modules/typescript/bin/tsc --noEmit --incremental false` 通过；`node tests/production_contracts.mjs` 通过。提交 ff07ea6 已推送，`git ls-remote` 核对远端 master；GitHub commit status 中 Vercel success，线上 `video-collection` bundle 包含“明显 20%（默认）”。
- 数据库：新项目 Supabase SQL Editor 执行 0046，返回 Success；随后查询 `information_schema.columns`，`tasks.bgm_volume` 的 `column_default` 为 0.20。本机 `web/.env.local` 的 DATABASE_URL 未能供 psycopg 正常连接，本次通过已登录 Dashboard 执行，未修改本地密钥。
- Worker：生产 `processing` 阶段数为 0 后验证旧 Python PID 14600 身份并停止，守护进程启动新版 PID 30368，15:18:38 启动日志正常；云端 `system/worker-health.json` 的 status online、心跳约 9 秒。启动日志有一次留存清理 SQL statement timeout，未影响 Worker 运行；如持续出现再单独排查。
- c492 任务最终复核：任务 done；ingest、transcribe、clean、rewrite、image、book、tts、render 均 done。最新 `external_narrations.state=approved` 且音频/字幕路径均存在；上一版仍为 failed，不再需用户重复上传。未实看成片画面和字幕内容，视觉验收仍可按需进行。

### 2026-11-21 · c492 配音零时长词修复 · 已修复发布，待重传音频

- 缓存识别匹配率 98.6%，225 条字幕仅「所以」44.45–44.45 无有效时长。精确匹配但零时长的识别词会在相邻真实时间范围内局部定位，稿件和有效词时间保持原值。本稿定位为 44.30–44.60，225 条全部通过 validate_cues。
- external_alignment 和 external_narration 共 26 项测试通过；110be2a 已提交并推送。生产无活动阶段时重载 Worker，新 PID 14600。新进程启动日志正常，最后云心跳仍为 recovering，在线状态待再次确认。
- 原音频 11-18 上传，11-20 03:19 UTC 已按 48 小时规则清理，云端 info 返回 404。当前任务未强制完成、未伪造音频。用户重新上传原 MP3 后可沿用原确认稿继续对齐。

### 2026-11-17 · 待发布改动上线及媒体分流 · Web 已发布

- 1d4c24a 已推送并核对远端；线上任务页 200 且 JS 含配乐新增提示。生产成片执行中，检查后未中断。
- f0ec8ee 已推送，GitHub 发布状态中 Vercel success，涵盖 Worker 媒体读写、二次发布、Web 签名与清理、存量 inventory/copy/remove-verified，未改数据库结构。Worker 11 项回归与 Web 类型、生产契约通过。线上只读抽查 20 个已登记旧媒体，全部可读取元数据，合计 2,118,070 字节；不是总用量。
- 待接手动作：常驻 Worker PID 27332 仍运行旧进程。已等待 24dec7f7、9214797b 完成，持续有新成片（最近核对 95c9a8c6）。留出空闲窗口后重载 Worker 并核对心跳。待 R2 私有桶、CORS 和四项凭据到位，先验收 Web 读取，再启用 Worker 写入。验证迁移副本后分批移除 Supabase 原件。真实 R2 与存储降额未验证。生产保留清理只读预览为 0。已在运行配置增加独立 boto3 目录并验证本机 SDK 导入。

### 2026-11-16 · 本地素材成片命名与配乐默认授权 · 本地完成

- Worker 本地素材高清成片按北京时间 MMDD 加主标题（空时用任务标题、书名或成片），同名用（2）递增。保留原目录和七天清理逻辑，不追改旧文件。现有浏览器下载和公共素材保存流程未改。
- Web 两个新建入口对默认配乐勾选授权，任务配乐面板对已有曲目、内置曲目、个人预设与新上传文件默认勾选。旧任务重新保存后写入数据库。
- Worker tests.test_stock_render_integration 4 项通过，覆盖真实 FFmpeg 成片、北京时间跨日和重名保护。Web tests/production_contracts.mjs 和 TypeScript 检查通过。本地未提交、未推送，Web 和 Worker 未更新，待线上验收。

### 2026-11-14 · 改写代理恢复 · 真实任务已返回正文

- 用户加入 xcode.best 代理规则后，匿名连通探测返回 HTTP 401 JSON，TLS 恢复。09c90b2d 和 2b3d259b 已重新进入改写，前者由限任务 Worker 领取并保存改写稿后待人工确认，后者由常驻 Worker 领取，检查点确认前两次已有正文，第三次处理中。本轮无代码、推送或部署变更。

### 2026-11-14 · 采集与改写排队恢复 · 待改写网络恢复

- Supabase 在用户恢复代理后可读。09c90b2d 采集、2b3d259b 改写均 pending 且无错误，生产队列无活动阶段，Worker 心跳已过期。重载 Worker 及守护进程后，生产心跳 online，PID 27332。临时改写 Worker 已自动退出。两条任务均已领取改写，均为 APIConnectionError；对现有 xcode.best 匿名健康探测在 TLS 握手中断。无需重新采集，待服务连通后仅重跑改写；本轮无代码、推送或线上部署变更。

### 2026-11-14 · 配乐与口播规则上线 · 已部署

- 本地提交 d4e39c3，经 HTTPS 推送并核对远端 master。沿用上一轮 Web TypeScript、生产契约、65 项改写和 13 项配乐相关 Worker 回归。无需新迁移。
- Worker 在队列空闲时重载，00:36:25 PID 9476，生产心跳 online，核验时 8 秒内刷新。
- Web 用临时账号和静音文件确认历史哲科预设上传、列表、签名试听、禁止删除被引用曲目和取消引用后删除均通过，临时账号、任务及文件已清理。首次代理请求超时，直连复测通过。实际成片混音和真实稿件待验收。

### 2026-11-14 · 历史哲科配乐与个人预设 · 本地完成

- 历史哲科新增独立音乐类别，Web 列表、上传、签名试听及 Worker 成片识别支持 social_science。现有曲目留在原类别。文件上传前选择类别及是否保存预设，写入时显示进度状态，失败时展示存储错误。个人预设支持删除，API 校验所属账号及任务引用。
- 生产：已用文件哈希确认健康类两份「哲科人文-Death Pledge」完全相同，两份均无任务引用。已仅删除较新的副本，并复查原件及「哲科人文-虚空」仍在。
- 验证：Web TypeScript 与 production_contracts.mjs 通过，Worker tests.test_book_cover_inserts 通过。功能未提交、未推送，Web、Worker 尚未更新，无迁移。部署后验证历史哲科真实上传与试听、成片配乐和删除行为。

### 2026-11-13 · 口播出处审稿措辞 · 本地完成

- 历史社科与健康走共用口播措辞约束。出处待核类说明留在审核元数据，正文去除存疑引语的引号与具体归属，或省去依赖出处的说法。程序在现有返工次数内识别常见变体，跳过锁定钩子及历史锁定结尾。
- 文件：worker/prompt_profiles.py、worker/spoken_style.py、worker/stages/rewrite.py、worker/prompts/rewrite_skill_contract.txt 和历史社科规则。Worker unittest 65 项通过（tests.test_spoken_style、tests.test_rewrite_review、tests.test_rewrite_editorial、tests.test_rewrite_skill、tests.test_history_workflow）。本地未提交、未推送，Web 与 Worker 未更新，线上未验收。发布后用新稿检查口播正文和审核信息。

### 2026-11-13 · 女性成长新版上线 · 已部署

- 本地验证沿用 124 项 Worker 测试、Web 契约与 TypeScript。仅暂存本轮 27 个代码、规则与测试文件。提交 `5b50e24`，用 HTTPS 推送公开仓库，并用 `git ls-remote` 核实 `master`。
- 生产首页、新建项目入口和任务页返回 HTTP 200。使用 UTF-8 检查生产资源，确认 `health-v1` 为 4:3 古典胶片写实，并核对任务页新增 `effective_char_count` 和 `local_cover_name`。Vercel API 现有凭据返回 403，网站已发布版本由线上资源核实。
- 初次启动受旧 Worker 日志锁影响。再查生产队列无运行中阶段，停止旧进程 6832 后通过既有计划任务启动新版。17:56:29 PID 25808，启动日志正常，生产心跳 online，检查时约 23 秒内刷新。
- 无新迁移。未创建线上测试任务或调用付费生图。用户会新建项目，建议通过本地人物预设命中与未命中两种情况核验封面及分镜。

### 2026-11-13 · 女性成长 AI 画风、人物封面与通用分镜 · 本地完成

- Web 新建任务和调整类别共用模板设置。女性成长与健康的 AI 使用 health-v1 v3，4:3，复用历史社科胶片写实视觉和全文封面规划。女性日常场景沿文案年代设计。旧任务版本与健康素材模式兼容。
- 封面优先级为手动上传、本地人物预设、各内容线自动封面。素材模式保留按书名查找与素材取帧。Worker 从素材库的 `91_成片预设封面` 读取并校验图片。去除文件名尾号后与正文及标题核对，同人多图按任务 ID 稳定随机选择；不同人物难以区分时使用后续回退。生图命中本地封面时记录文件名。
- `worker/storyboard.py` 统一 AI、山河人文、二次发布与本地／公共素材分镜。汉字、字母和数字计有效字。短稿或长度无法完整分配时允许末镜不足 90 字，保留全部正文。实际素材偏短时可拆成多个片段，双人播客仍采用单张背景。新生图缓存包含分镜版本和稿件摘要。
- 本地验证：Worker unittest 共 124 项通过，覆盖历史社科、健康、国学、山河人文、素材、二次发布、人物封面与可靠性；Web 的 `node scripts/test-production-templates.cjs`、`node tests/production_contracts.mjs` 与 TypeScript 检查通过。
- 发布状态见上方部署记录。实际出图、封面优先级和成片效果待新任务验收。

### 2026-11-13 · 二次发布上线 · 已部署

- 用户确认 0045 已执行。生产调用探测命中新版首发任务校验，未创建任务。提交 `7582c5d` 已推送并用 `git ls-remote` 核对，线上任务页 HTTP 200 且前端资源含新二次发布提示。
- 队列空闲时重载常驻 Worker，PID 6832，13:10:44 启动，生产心跳 online。沿用上轮 68 项相关 Worker 回归、Web 契约、TypeScript 和迁移语法验证。未创建线上 V2 或触发付费请求。下一步可用首发图尚在、首发图已过期的任务各跑一条。

### 2026-11-13 · 二次发布改写与首发图片复用 · 本地完成

- 0045 在同一事务创建 V2、跳过前三个采集步骤、继承制作模板与领域；兼容旧的待处理 V2。单人口播加载 `skills/book-video-rewrite/references/repost.md`。AI 图片全部可用时复制进 V2 的私有目录并按新稿重建分镜索引；整套不完整时走常规生图。素材拼接按源任务设置重新选材。配音、文案和成片各按 V2 独立处理。
- Web 生产契约与 TypeScript 检查通过。Worker 68 项定向测试通过，涵盖复用、缺图、权限错误与指定重生图。0045 已通过 SQL 和 PL/pgSQL 语法解析。本地验证后的上线状态见上方部署记录。

### 2026-11-13 · 云端成片保留 48 小时与二次发布审查 · 完成

- Worker 与 Web 定时清理已统一为云端成片 48 小时，提交 `feb62cd` 已推送。生产队列空闲后重载 Worker，进程 20868 于 12:48:42 启动，心跳 online。生产清理预览符合条件 0；尚无到期对象用于新版删除验证。Web 生产定时入口匿名返回 401，带凭据的执行尚未核验。
- Web 发布包与生产契约、TypeScript 校验通过。Worker `tests.test_local_materials tests.test_rewrite_review tests.test_rewrite_skill` 共 42 项通过。
- 二次发布审查与实际规则见 `docs/REPOST_WORKFLOW_REVIEW_2026-11-13.md`。代码显示旧建任务触发器标记前置为 cancelled，与只接受 done 的领取规则冲突。生产只读查询没有二次发布任务，未创建测试任务。此次按审查范围保留二次发布代码和提示词，下一步先修建任务并统一继承模板，再加专属二次发布规则。

### 2026-11-13 · 提前清理生产媒体与封面流程部署 · 已执行

- 用户确认此前生成媒体已下载。生产 Storage API 分批清理 38 条成片、397 张图片、16 张源宫格、4 张生成封面及对应产物记录，返回删除体积 1,684,073,328 字节，失败 0，目标记录余 0。逐层复扫 45 个已完成任务目录，生成媒体已无残留，仅见一张约 195 KB 的手动上传封面，按生成媒体范围保留。未修改任务阶段、文字、音频与本地下载。Supabase 配额页面未复核。
- 用户确认 `0044_confirm_rewrite_with_cover.sql` 已执行，使用不存在的任务探测 RPC 得到预期业务拒绝，未修改任务。提交 `9d58f7a` 已推送。生产任务页 HTTP 200 且脚本含新 RPC，发布包匿名接口 HTTP 401 符合预期。空闲 Worker 重载，心跳在线。线上未用真实稿件生成付费产物；下一条健康及历史任务验证预填、确认与发布包。

### 2026-11-13 · 公众号封存与改写阶段封面确认 · 本地完成

- 公众号细纲、三图、续写说明与深圳原稿、改写稿、成片、封面和发布文案节选已封存于 `docs/wechat-handoff-2026-11-13.zip`，已核对 10 个条目。压缩包及解包目录仅在本地。
- 改写产物新增 `cover_suggestion`。健康类按书名、作者生成建议，历史社科按主要人物、人物介绍、文案重点生成建议。来源为原始标题和原稿，并参考改写稿概括重点。缺失项允许手填。审核页上传封面先作为本页待确认项，`0044_confirm_rewrite_with_cover.sql` 在一个事务里保存封面、画面文字并排队确认。历史模板副标题在审核时要求两行。旧任务已保存的画面文字优先。
- 发布包优先沿原标题扩写简介，使用确认稿核对事实。发布标题保留三个候选，16 字校验含标点。发布包读取已保存的画面文字，保留历史副标题换行。封面入口支持未上传状态，可上传、预览或沿用自动封面。普通渲染和山河人文渲染都接入上传件。
- 验证：`node tests/publication_contracts.mjs`、`node tests/production_contracts.mjs`、`node node_modules/typescript/bin/tsc --noEmit --incremental false` 通过；Next 生产构建通过；相关 Worker 64 项测试通过。用模拟模型检查两类模板及缺字段回退；pglast 解析 SQL 与 PL/pgSQL 通过。数据库事务尚未在实际数据库验证。
- 此处为上线前本地记录，提交、迁移、生产 Web 和 Worker 的最终状态见上方部署记录。旧待审稿件缺少新建议时可手填。

### 2026-11-13 · 公众号三篇细纲与配图 · 本地完成

- 扩充 `docs/WECHAT_BUILD_IN_PUBLIC_EDITORIAL_PLAN.md`，按上手、效率、发布准备三个读者收益整理文章段落、实例和素材清单。`docs/wechat-visuals/` 新增三个 900 px 宽 PNG，已逐张目视检查并核对文档引用。核对深圳样片和验收记录，尚缺面向发稿的操作录屏、同稿手工计时基线及三样成品合图。本次为本地编辑资料，无业务代码提交或部署。

### 2026-11-12 · 封面发布与线上验收 · 已上线并验收

- 本地生产构建和 54 项相关 Worker 测试通过。七个封面相关文件提交 `fcbaa31`，已推送并核对 GitHub `master`。本批无需数据库迁移。
- 测试任务 `3b757509-b671-43d7-8b16-c3bb6f2141b6` 原成片质检通过，已核对为上传封面，旧成片记录无裁剪、增强为关闭。上游画面、配音和稿件均已完成。
- 生产任务页返回 HTTP 200，已加载带顶部 4:3 预览的新资源。常驻 Worker 于 17:14:44 重载并成功领取后续任务。
- 指定任务仅重跑成片阶段，复用已有稿件、40 个画面、配音和字幕。实际成片使用的上传封面由 1100×1113 顶部裁为 1100×825，成片记录为 `cover_origin=uploaded`、`cover_crop=top_center_4x3` 和 `cover_enhanced=true`。
- 17:26:13 成片完成，任务和阶段均为 `done`，自动质检为 `passed`。新产物为 `renders/61fb1b3c-f9f3-42b2-a17f-8ceaff6b4fc9/final.mp4`。[测试任务](https://content-ecosystem.socra.cn/task/3b757509-b671-43d7-8b16-c3bb6f2141b6)
- 本次生产成片验收覆盖上传封面路径。历史社科自动生成首格封面的路径通过本地模拟测试，待使用历史社科任务验证实际生图。

### 2026-11-12 · 上传封面 4:3 裁剪 · 本地完成

- 调整上传封面共用的渲染入口和封面预览。成片先按拍摄方向纠正，再顶部对齐裁为 4:3 并高清处理。成片元数据记录裁剪方式和增强状态。
- 目标任务 `3b757509-b671-43d7-8b16-c3bb6f2141b6` 为 `health-v1` 本地素材拼接，阶段为 `done`。只读验证实际原封面从 1100×1113 顶部裁为 1100×825，保留原分辨率并轻度锐化。
- 54 项相关 Worker 测试与 Web TypeScript 检查通过，涉及 `worker/stages/render.py`、`worker/tests/test_history_workflow.py`、`web/components/detail/StockCoverSettings.tsx`。生产未部署，目标任务未重新成片。部署后只需重跑成片阶段来应用新封面。

### 2026-11-12 · 历史社科生图封面 · 本地完成

- 上传沿用任务封面存储和授权。自动模式为全文设计独立封面提示词，首批排封面加最多 8 镜，后续每批最多 9 镜。封面从首格切出并独立归档，正文镜号、文字范围和配音对齐保持一致。已有任务的成片可继续使用主题镜头。
- 人物故事优先用头肩近景。通过 Wikidata 匹配姓名和人物实体，从 Wikimedia Commons 读取肖像来源和许可标记。APIMart 首批带匹配图作参考，备用文字通道和无可靠肖像时记录示意状态。题材、年代、地域及服化道取确认稿支持的情境。图像有源图、独立封面和提示词记录，片头沿用已确认标题。
- 涉及 `worker/history_visuals.py`、`worker/stages/image.py`、`worker/stages/render.py`、`worker/tests/test_history_workflow.py`、`web/app/api/video-cover/route.ts`、`StockCoverSettings.tsx` 和 `ImageDetail.tsx`。
- 验证　53 项 Worker 测试通过，包含上传跳过设计、首格封面跨批镜号、同名人物歧义和旧任务回退。测试对在线国学参考图使用本地替身，历史肖像检索及生图请求使用模拟返回。Web TypeScript 检查通过。
- 本轮为本地变更，生产 Web、Worker、数据库和已有任务保留上次发布状态。线上验收可用新历史社科任务分别测试上传封面与自动首格，复核封面预览、肖像来源、正文时间轴和片头成片。

### 2026-11-12 · 历史社科主标题微调 · 已完成

- 用户要求主标题字号 60→65，黑色描边 6→3。仅调整历史社科模板；31 项相关测试通过，提交 `40f047d` 已推送，Worker 重载。任务 `4e7031dd-13b0-4f4b-b372-0b04da8b847a` 仅重跑成片并完成，复用画面轨，新成片路径 `renders/7a3aa4ac-0b21-4b40-901a-d68fc599a523/final.mp4`，日志记录自动质检及任务完成。未另行制作样图。

### 2026-11-12 · 历史社科参考图文字比例与字幕 · 进行中 · Codex

- 用户进一步指定主标题恢复俪金黑，字号 60；副标题 70，两行基线间距 80 px，距图片 40 px。已生成第二版本地样图 `worker/output/history-layout-reference-preview-v2.png`，使用旧第13镜与实际已保存标题、示例口播字幕。等待用户确认，未提交或部署、未重成片。当前视觉比此前样图更突出俪金黑标题。
- 最新调整　副标题和口播字幕均恢复 HarmonyOS Sans SC；副标题字号 75、两行基线间距 70 px，主标题仍是俪金黑 60，底行至图片 40 px。第三版静帧样图为 `worker/output/history-layout-reference-preview-v3.png`，仅本地生成。等待用户确认，未部署或重成片。
- 第四版　用户指定主标题改 HarmonyOS Sans SC 60，副标题改俪金黑 75，两行基线距离 75 px；口播字幕仍为 HarmonyOS Sans SC。静帧 `worker/output/history-layout-reference-preview-v4.png` 已生成并查看；俪金黑的实际字面较高，75 px 基线间距使两行视觉上贴得过近。31 项 Worker 回归通过（设置本地 `TEMP/TMP` 至 `worker/output`）；第一次未设该目录时测试因受限临时目录失败，与业务代码无关。等待用户判断是否增大两行间距，仍未部署或重新成片。
- 第五版　用户确认副标题俪金黑 70、两行基线 90 px，主标题 HarmonyOS Sans SC 60、口播字幕 HarmonyOS Sans SC、脚注白字黑描边保持。样图 `worker/output/history-layout-reference-preview-v5.png` 已目视核对，31 项测试通过。按用户确认进入提交、发布和现有目标任务仅重跑成片阶段。
- 部署验收　提交 `5b32042` 已推送；空闲 Worker 重载后，仅重排任务 `4e7031dd-13b0-4f4b-b372-0b04da8b847a` 的成片节点。新成片 `renders/bf0b7d51-2b40-4636-a455-ee018c00738f/final.mp4`，任务与阶段均 `done`，质检 `passed`。产物元数据核对主标题 HarmonyOS Sans SC、副标题俪金黑、口播字幕 HarmonyOS Sans SC，封面增强 `true`，画面轨缓存命中 `true`。图片、配音、字幕及文案没有重跑。
- 用户提供两张画面参考，要求历史社科主标题缩小 50%，副标题放大 20%，两行距离增大 30%，副标题至画面上缘间距缩小 30%；随后补充口播字幕采用白色粗宋体、黑描边、居中样式；底部脚注白字黑描边。仅调整历史社科模板。用户要求先交样图，确认后再部署和重新成片。
- 已核对当前渲染为俪金黑主标题、HarmonyOS Sans SC 副标题、楷体口播字幕；双行副标题使用 ASS 换行，无法精准控制行距。已在本地改为两行独立定位、Noto Serif SC 宋体，主标题按旧实际字号半数、副标题基准 64→77 并以 90% 横向比例控制安全宽度；两行基线间距为字号 1.3 倍，底行离画面上缘间距 56→39。历史社科口播字幕改为白色粗宋体黑描边，脚注白字黑描边；其他类别不变。
- 本地样图　`worker/output/history-layout-reference-preview.png`，1080×1920，复用目标任务第13镜现有高清封面，显示已保存的主副标题和脚注、参考口播字幕。样图用静帧，口播字幕在样图第0帧演示；实际视频字幕仍按配音时间轴出现。
- 验证　31 项 Worker 相关回归通过，`git diff --check` 通过，已用 FFmpeg 输出并人工查看样图。**尚未提交、推送、重载 Worker、重新成片**。用户要求先确认样图，再进行部署和目标视频重合成。

### 2026-11-12 · 历史社科文字与音乐栏 · 已上线并验收 · Codex

- 已核对历史社科主标题当前使用浅色描边、副标题基准 56；个人预设保存在账号私有存储的 `artifacts/user-music/{owner}/{category}/`，内置预设保存在同一 `artifacts` 存储桶的 `music-presets/`，选用后均写入任务背景音乐路径。已修正历史社科主标题白字黑描边，副标题基准 56→64；保留两行上白下黄。音乐栏内置曲目与个人预设合并成一个选曲框，单独解释人声音量和背景音乐音量。
- 文件　`worker/stages/render.py`、`worker/tests/test_history_workflow.py`、`web/components/detail/BackgroundMusicSettings.tsx`、`web/app/globals.css` 及本说明书。
- 本地验证　31 项相关 Worker 测试通过，Web 流程契约及 TypeScript 检查通过；`git diff --check` 通过。`4d8efaf` 已推送，线上任务页 JS 含新版选曲与音量说明，Worker 重载并核验心跳。
- 目标任务　`4e7031dd-13b0-4f4b-b372-0b04da8b847a` 仅重跑成片，生成 `renders/7e1af539-ac34-4afe-99fa-c88e073fdb98/final.mp4`，状态 `done`，质检 `passed`，第13镜为主题封面10帧，`cover_enhanced=true`。图片、配音、字幕均未重跑。本任务未配置背景音乐，产物 `bgm_enabled=false`，配音音量1.1。
- 后续修正　最新产物元数据记录了旧默认 `title_color=#FFF4D9`，但 ASS 实际已强制绘制白字黑描边。`6dd8ee1` 已修正未来产物记录为 `#FFFFFF`，31 项测试通过，已推送并重载空闲 Worker，心跳在线；已完成视频不需再重跑。

### 2026-11-11 · 历史哲学封面与字体 · Codex

- 状态　`e045b0e` 已推送；线上任务页与重载后的 Worker 均已核验。历史社科的画面文字采用女性成长模板的字体，主标题与双色副标题全程显示，主题封面从已有分镜图选择并持续10帧。
- 配乐　所有类别的新任务及新选曲目默认 10%。指定任务已改为 10%，其他任务已有自定义音量不批量覆盖。
- 验证　57 项 Worker 回归、Web 类型和流程契约通过。指定任务在 35 张已有分镜图中选中第13镜人物画面。
- 比例　指定任务 APIMart 请求和分镜提示词为 4:3；实际四张九宫格均为 1448×1086，35 格索引均为 4:3，抽查第1、13、35镜实际尺寸约为4:3。成片沿用9:16画布和4:3原画。
- 线上验收　任务 `4e7031dd-13b0-4f4b-b372-0b04da8b847a` 于 23:37:08 完成。仅重跑成片，复用确认稿、配音、字幕和生图。新成片确认使用第13镜、10帧、俪金黑／HarmonyOS Sans SC／KaiTi、4:3画面和10%配乐。
- 后续高清　`f9faeac` 新增本地 Lanczos 等比放大和轻度锐化。目标任务第13镜样张位于 `worker/output/history-cover-4e7031dd-shot13.png`（463×348→1080×812）。51项本地回归通过。当前成片使用原始素材，高清样张单独提供；后续成片可自动应用此处理。新 Worker 于23:39:12重载，生产心跳在线。

### 2026-11-11 · 所有内容线口播字幕放大并上移 · Codex

- 状态　已随 `e045b0e` 发布。调整通用和山河人文两套口播字幕渲染入口。通用 72→78，山河人文 64→70，以 1080×1920 ASS 坐标为基准。字幕向上移，距实际画面底边至少两行；较高的旧位置仍上移约一行。
- 文件　`worker/stages/render.py`、`worker/scene_render.py` 及国学、健康和山河人文布局测试。
- 验证　56 项 Worker 回归通过。FFmpeg 样帧验证了 4:3、1:1 和全屏画面。4:3 样帧字幕可见像素离画面底边 174 px，较高的 1:1 和全屏布局保留更大间距。
- 接手动作　发布并重载 Worker，当前渲染任务完成后再切换。已有视频需重跑成片以应用新字幕位置和字号。

### 2026-11-11 · 历史社科分镜切换 DeepSeek · Codex

- 状态　已推送 `7b790dd`。历史社科分镜和补图备注改用 `deepseek-flash`，APIMart 负责图片。清洗、二创与其他类别沿用各自配置。
- 验证　61 项本地回归通过。虚构文案两镜在官方接口约 17 秒返回；目标任务 `4e7031dd-13b0-4f4b-b372-0b04da8b847a` 的 35 镜已用正式 DeepSeek 接口生成，已通过编号及人物卡校验，并保存到原任务分镜缓存。未发 APIMart 请求。
- 同时排查　`82d9d40a-23ad-436b-a939-9a72766d35b3` 已成片，最近一次约 9 分 25 秒。任务 `cf171417-9a31-466a-b8f9-e297528b62bf` 曾在成片混音时出现连接异常，库里成片状态仍处理中但心跳过期，现场无 FFmpeg 进程。已在无其他活动阶段时触发 Worker 重载，等正常恢复逻辑处理。
- 接手动作　重载已核验。日志确认 `cf171417` 已从成片节点重新认领并开始编码，成片仍待产出。目标历史任务可从「画面」重跑，复用 35 镜分镜和已有字幕、配音、确认稿。

### 2026-11-11 · 历史社科分镜 524 · Codex

- 状态　任务 `4e7031dd-13b0-4f4b-b372-0b04da8b847a` 两次停在生图前的分镜规划，xcode.best 返回 524。确认稿、配音和字幕已完成，任务无生图产物。
- 修复　历史社科分镜每批最多 6 镜流式返回，沿用已定义人物卡与全片编号；超时提示具体镜头范围。改动在 `worker/history_visuals.py` 和 `worker/tests/test_history_workflow.py`，60 项本地回归通过。提交 `09e3197` 已推送。数据库和 Web 功能未改。
- 阻塞　生产 Worker 仍在处理其他成片，尚未重载。自动审批拦截了向现有 xcode.best 发送该任务确认稿以补齐分镜的请求。实际分镜和生图尚未验证。
- 接手动作　确认队列空闲后重载 Worker；在有明确授权时仅重跑画面节点，复用已完成的外部配音、字幕和确认稿。

### 2026-11-11 · 历史社科双色副标题 · Codex

- 发布　`60b07b3` 已推送，Vercel 生产任务页和 Worker 心跳均已核验。任务 `4e7031dd-13b0-4f4b-b372-0b04da8b847a` 的原副标题已拆为「二十世纪以来」与「唯一的哲学天才」。保留原文字、主标题和其他字段。任务仍待用户确认改写稿，成片待运行。

- 状态　本地完成。改写和成片页均可录入最多两行副标题，上白下黄，使用黑描边。单行显示白字黑描边。总长度 36 字符（含换行），沿用现有数据库字段和校验上限。
- 文件　`web/lib/videoText.ts`、`web/components/detail/VideoTextSettings.tsx`、`web/components/detail/RenderDetail.tsx`、`worker/stages/render.py` 及相应回归测试。
- 验证　43 项 Worker 回归、Web 流程契约和 TypeScript 检查通过；FFmpeg 实际渲染的样帧确认两行颜色及黑色轮廓。未测试线上任务。
- 接手动作　用户先确认上述任务的改写稿，再按正常流程制作；已有成片可在「成片画面文字」编辑副标题，选择「保存并重新成片」复用上游产物。

### 2026-11-11 · 简化文案入口与女性成长稿领域判断 · Codex

- 状态　已上线。任务 `cf171417-9a31-466a-b8f9-e297528b62bf` 已完成采集、转写和清洗；单次庄子引文使二创停在领域校验，用户确认归入女性成长与健康生活。
- 改动　提交 `c4a1918` 已推送。常规改写页不再让用户重复选择改写方式，只在实际领域冲突时显示领域选择。成稿入口继续直接制作，已完成导入时不显示改写重跑按钮。
- 验证　52 项 Worker 回归及 Web 类型、流程检查通过。用原任务已保存的清洗稿只读验证，改写规则解析为 `health`。没有调用模型。
- 接手动作　在这条任务点「重跑」。保留原分类、已保存的画面文字和采集、转写、清洗结果。本轮未启动改写。

### 2026-11-11 · 历史社科哲理分镜 · Codex

- 状态　已提交并推送 `d90054f`。历史社科 4:3 分镜增加哲理画面规则。具体史事按资料呈现，抽象哲理用生活动作、自然意象或器物表现，手机画面中突出一个关键形状、动作或落点。
- 文件　`worker/history_visuals.py`、`worker/stages/image.py`、`worker/tests/test_history_workflow.py`。分镜和图片缓存路径升为 `history_period_film_4x3_v2`，新生图时使用新版提示词。
- 验证　57 项本地回归通过，模拟树冠人头侧影和水滴正落向石面圆凹两例。未调用真实生图服务。本次只有 Worker 代码变动。
- 上线　GitHub 已确认新版，本地与远端一致。生产队列空闲时重载 Worker，核实新进程、生产心跳和数据库读取均正常。
- 接手动作　由用户创建历史社科任务测试哲理书籍，检查纯说理段是否具象、单格在手机上是否能辨认。历史成片无需重跑。

### 2026-11-11 · 生产部署 · Codex

- 状态　发布提交 `bff5839` 已推送到 GitHub `master`。99 项 Worker 回归、Web 类型检查、前端流程契约及生产构建通过。本次使用现有数据库字段，无迁移。
- 核验　生产首页 200，新封面接口匿名请求 401。无运行中任务时重载受守护的 Worker，进程于北京时间 18:08:04 启动，生产心跳在线。生产库读状态成功。Web 验证仅检查可用性和新接口存在。
- 范围　发布包含历史社科流程、单人口播审稿、女性成长与健康生活精修、本地素材选取、封面及音乐预设；视频画面文字校验兼容旧数据缺少账号名称。交接文档留在本机。
- 待查　额外运行的旧画面文字脚本未配置 `@/` 路径别名，未跑完。Worker 启动日志记录两条历史音频留存清理失败，原因待查，主进程和心跳均正常。
- 接手动作　用户自行安排业务测试。若需接续排查，从新任务的类别、字数记录和历史社科画面模板版本着手。

### 2026-11-11 · 建立持续交接

- 状态　文档已落地。新增仓库级 `AGENTS.md` 和本说明书，并更新 README 与会话恢复入口。业务代码、线上数据和部署状态保持上面的交接点。
- 接手动作　使用本文件顶部状态和下方「接管步骤」。接手任何后续修改时，复制文末模板追加到本节顶部。

### 2026-11-11 · 历史社科与单人口播审稿

- 状态　此条记录对应发布前的本地回归，后续发布见上方。各轮都以同一来源稿计算字数，局部返工先扣除锁定头尾和复用段落，给可改部分分配字数。择稿优先检查完整性和字数，再看审稿问题与重复指标。最后仍超出字数范围时保留完整稿供人工确认，页面可查看每轮实际字数和偏差。
- 画面　历史社科独立模板采用 4:3、古典胶片写实风，按文案年代安排人物、环境和服饰。继续保留与国学模板的独立设置。
- 文件　`worker/stages/rewrite.py`、`worker/rewrite_review.py`、`worker/rewrite_editorial.py`、`web/components/detail/RewriteReviewPanel.tsx`、`worker/history_visuals.py`、`worker/prompts/categories/social_science/history_rewrite.txt`、`web/lib/productionTemplateManifest.json`。
- 验证　81 项回归及 Web TypeScript 检查通过。另运行 5 个既有改稿用例并通过。扩展全量测试停在 Windows 本地异步连接初始化的双人配音用例。真实模型长稿、真实生图和线上成片本轮未验收。
- 接手动作　先对照下文的工作区边界。如获授权上线，先核对线上 Web 和 Worker 版本，分批审查提交，使用一条虚构或授权的历史社科任务验证稿长、锁定头尾、4:3 画面和人工确认；再用健康和国学样本确认类别规则。二创的独立回归可在无供应商请求的情况下先跑。

### 较早的本地改动与版本边界

- 已提交、是否已部署需逐项核对　从当前缓存远端基线之后的本地提交可见账号入口、工作台更名、类别调整、字幕与外部配音恢复、书封画中画、发布包与音乐重设等修改。可用 `git log --oneline origin/master..HEAD` 查看准确清单。
- 同批次功能文件　女性成长精修涉及 `worker/rewrite_skill.py`、`worker/prompts/categories/health/polish.txt`、`skills/book-video-rewrite/references/health.md`；本地素材、封面、音乐涉及 `worker/local_materials.py`、`worker/local_material_history.py`、`worker/music_presets.py`、`web/app/api/video-cover/`、`web/components/detail/StockCoverSettings.tsx`、`web/lib/userMusicPresets.ts`。
- 审查新增文件时特别区分源码、测试、SQL、文档与运行媒体、日志、参考资料。环境文件、Cookie、原始素材和运行产物留在本机。新克隆接手需要先同步指定的未提交源码或经过审查的提交。

## 接管步骤

1. 在同一工作目录读本页与根目录 `AGENTS.md`。用 `git status --short`、`git diff --stat`、`git log -5 --oneline` 核对接管点，检查有无其他工作正在修改同一批文件。
2. 按用户指定任务继续。排查线上任务先核对任务 ID、阶段错误、最后活动时间、有效产物和 Worker 状态。重跑前确认影响范围和可复用产物，验收优先用明确的单任务范围，避免消费历史队列。
3. 保留开发、部署和验收证据。推送之前核对目标分支和待发布改动。Vercel、Worker、数据库迁移分别核验，历史部署手册仅作流程参考。数据库迁移先核实生产记录和依赖。
4. 开始写操作时记下进行中检查点。完成、暂停、遇到阻塞或交回时及时更新本页，记录可直接执行的下一步。用户指定 WorkBuddy 接管后，按当次授权推进。

### 本机验证命令

在仓库根目录的 PowerShell 中运行。Worker 运行时描述文件和 Web 依赖在本机已存在，新环境可按 `worker/requirements.txt` 和 `web/package.json` 安装。

```powershell
Push-Location worker
$runtime = Get-Content output/worker-runtime.json -Raw | ConvertFrom-Json
$env:PYTHONPATH = (@($PWD.Path) + $runtime.dependencies) -join ';'
$env:PYTHONUTF8 = '1'
$env:TEMP = Join-Path $PWD 'output'
$env:TMP = $env:TEMP
& $runtime.python -m unittest tests.test_history_workflow tests.test_rewrite_review tests.test_rewrite_confirmation tests.test_rewrite_skill tests.test_rewrite_editorial tests.test_production_templates tests.test_image_style_profiles tests.test_stock_render_integration
Pop-Location
```

```powershell
Push-Location web
$node = 'C:\Users\ghz00\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
if (-not (Test-Path -LiteralPath $node)) { $node = 'node' }
& $node node_modules/typescript/bin/tsc --noEmit --incremental false
Pop-Location
```

### 追加交接记录模板

```markdown
### YYYY-MM-DD HH:mm（北京时间）· 事项 · 接管方

- 状态与位置：进行中 / 本地完成 / 已提交 / 已推送 / 已上线 / 已验收；分支、提交、任务或部署记录。
- 已做与文件：用户目标、已完成的动作、关键路径和仍在编辑的文件。
- 验证：命令或检查方式、结果、未通过或未验证的项目。
- 线上与数据：Web、Worker、数据库分别记录是否变更，附安全的证据位置。
- 下一步：接手后第一条具体动作，以及需要的输入、环境或权限。
```

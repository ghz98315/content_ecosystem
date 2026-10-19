# AI图书带货视频创作台 — 开发进度

最后更新：2026-10-19

## 当前检查点：外部配音413修复（2026-10-19）

- 故障任务 `fc866990-8147-4ce9-8496-9a2858b8b675` 的MP3原件已成功上传（5,686,190字节）；旧流程解码为原采样率/声道PCM后又上传WAV，超过Supabase单文件上限。TUS分片不能绕过单文件配额。
- 配音成品引用原始上传文件，不重编码、不重复上传；16k单声道PCM仅在本地分析使用。失败时保留新识别结果，避免恢复后再次识别。
- 存储层413改为明确的文件超限提示，不暴露服务响应正文。无存储限额/套餐调整。
- 217项回归通过，修复提交 `6e0bb5b` 已发布。原故障版本实际恢复approved/tts done，709.809秒音频生成288条字幕，audio_path已核对等于原始MP3路径；任务继续生图，未重跑上游。详情见 `docs/EXTERNAL_AUDIO_413_FIX_2026-10-19.md`。

## 当前检查点：标题入口合并（2026-10-19）

- 按用户截图移除改写页旧“封面标题确认”表单，仅保留统一的“成片画面文字”（主标题/副标题/脚注）。
- 确认改写稿前保存当前表单中的未保存文字，再把同一份主副标题交给旧历史封面确认契约；保留必填和24/36字限制，不修改数据库枚举或绕开原确认门。
- 兼容旧节点参数及已确认产物中的标题；显式空值保留，旧数据晚到不会覆盖正在编辑的草稿；跨节点保存冲突仍要求重新读取。
- 历史类开头封面改为与正文画面读取同一份显式设置，避免重新成片后仍在首15帧显示旧标题。仅修改设置不会重跑业务任务或更新已有视频。
- 214项Python回归、26项统一标题检查、13项页面稳定检查通过；生产构建/类型检查通过。修改详情见 `docs/TITLE_EDITOR_UNIFICATION_2026-10-19.md`。

## 当前检查点：视频号线上采集接入（2026-10-19）

- 已实现视频号链接→元宝会话解析→腾讯视频号详情→受限媒体下载→抽音频→现有逐字稿链路。
- Cookie仅发往固定腾讯元宝主机；不进入前端、数据库、日志或公开代码。逐次读取worker/.env，更换后无需重启；生产代码更新仍需要重启Worker。
- 登录态缺失/过期、内容不可读、下载异常时进入节点提示与上传兜底；不安装证书、不改变系统代理。互动数据保留平台展示值，缺失数据不伪装为0。
- 213项Python集中回归及生产构建/类型检查通过；线上真实验收结果见 `docs/WECHAT_ONLINE_TEST_2026-10-19.md`。
- 既往“视频号尚未接入”记录为历史状态；本次只验收到逐字稿，不启动二创、生图或成片。
- 线上任务 `69597e05-b00d-465b-8482-81b89d358bc9` 实测通过：12分48秒视频，采集12.547秒、逐字稿125.765秒/2932字，私有产物已读回；停在清洗前，继续需重跑清洗。原工作区归属已核对。

## 当前检查点：新一轮全流程前的未完成事项收口（2026-10-19）

- 单人口播二创已实现 book-video-rewrite 1.2 接线：独立领域选择、国学/健康/混合规则、信息卡与提纲依据展示、输入与规则指纹、初稿加3次修订的中断续计。保留人工确认；不宣称独立事实核实或文皮皮实测。
- 播放数据补齐 CSV/TSV 导入、预览、工作区归属校验、重复跳过与冲突提示，历史快照不覆盖。用户暂无明确自动接口，先支持文件导入。
- 本地真实编码的2秒虚构样例已验证首次写入画面缓存，修改标题后二次命中且新标题保留。首次约4.2秒、再次约1.3秒；质量报告使用测试替身，不作为真实画质验收，也不外推长视频提速。
- 189项集中Python回归、另1项真实编码缓存集成、22项数据导入和13项页面状态检查通过；生产构建、类型检查及skill结构校验通过。
- 下一轮业务全流程仍需验证真实模型文案质量、长视频端到端耗时、页面视觉和新版运镜主观效果。此前浏览器读取工具持续超时，页面抖动只完成机制修复，未冒称真实视觉验收。
- 视频号自动采集与播放数据自动回流保留为依赖项：下载开源工具不等于后台统计接口，涉及证书/系统代理的候选未安装。本轮不重跑真实稿件或发起额外付费生成。
- 发布与Worker更新结果见 `docs/PRE_E2E_CLOSEOUT_2026-10-19.md`。

## 当前检查点：第二轮运镜与页面稳定优化（2026-10-19）

- 最新清单见 `docs/OPTIMIZATION_ROUND2_2026-10-19.md`；此前核查和计时报告继续保留为历史证据。
- 新版为16%匀速放大/缩小交替，4倍工作图、4:4:4处理、2倍输出后缩回原尺寸；真实30秒样片已验证实际1.16倍。
- 页面已修复加载提示推挤、心跳触发自动换节点、终态持续刷新、表单重复加载与叠加入场位移等代码机制。
- 28项Python回归、13项页面状态/结构检查、正式构建和类型检查通过。真实浏览器视觉验收因工具读取连续超时尚未完成，不宣称页面抖动已完全验收。
- 当前业务任务未重跑；旧成片仍保留原效果，新版规则用于下一次成片。完整新流程和画面轨命中收益仍待实际验收。


## 当前检查点：细节收口与耗时核查（2026-10-19）

- 以 `docs/DETAIL_AUDIT_2026-10-19.md` 为最新状态；以下旧记录保留为历史，不把过期“待验证”当作当前状态。
- 已完成四宫格/国学模板、文字与配乐编辑、低分辨率容错、字幕自动纠正、发布包、页面计时与媒体保留功能。
- 当前线上已完成视频仍是6%运镜版；新版12%匀速交替运镜已通过30秒真实编码和首尾比例验证，供下一次成片使用。
- 逐字稿原CPU节点608秒；隔离补齐GPU依赖后，557.8秒源音频本机识别49.5秒，模型与解码合计约56秒；尚不代表新任务完整节点耗时。
- 新增成片版本地址/播放器刷新、文字跨节点同步、画面轨缓存、封面无重编码拼接、内部步骤计时及资源起止采样。
- 明确保留待办：二创skill分领域接线、视频号稳定自动采集、平台播放数据自动回流、新版全流程与缓存真实命中验收。
- 当前业务任务未重新排队，不在本轮自动启动完整流程。下一轮再验证整体耗时目标。


## 外部配音模式已上线并完成工程闭环（2026-10-15）

- 生产网站已部署至 `https://content-ecosystem.socra.cn/`，Vercel部署 `dpl_D8RYFiwsXQ5CH1Pj87VawkipTZto`；数据库0034迁移已生效。本轮是CLI直接发布，未推送Git。
- 191项Python回归、8项生产HTTP检查、9项生产权限与上传事务检查通过。
- 按用户授权上传93.195秒工程配音并复用已有图片，完整链路完成：真实识别→44条字幕→两条时间校准→审核→6张复用图片合成。成片93.690秒，10项技术质检通过，已抽查关键画面；未提交新生图请求，临时云端数据已清理。
- 本机Worker已后台启动并设当前用户登录后自动启动。修复旧NO_PROXY造成的连库失败及Windows识别依赖加载问题；不需要IndexTTS云端参与外部配音。电脑需保持开机才能持续处理。
- 二创确认前的处理逻辑未改。工程验收片不代表正式配音获用户确认；生产部署、运行方式与范围详见 `docs/EXTERNAL_NARRATION_RELEASE_2026-10-15.md`。

## 当前推进方向：外部配音驱动视频（2026-10-15）

- 用户决定暂停 IndexTTS 听感调试，采用文案确认后线下制作配音、上传最终人声，再进行文稿核对、字幕对齐、分镜生图和渲染的流程。
- 已核对现有上传、配音页面、词级识别、任务领取、分镜和渲染入口；详细执行计划保存在 `docs/EXTERNAL_NARRATION_PLAN_2026-10-15.md`。
- 已在本地实现外部配音来源选择、WAV/MP3签名直传、版本记录、等待状态、识别差异核对、语义字幕拆分、逐句试听及时间校准。新任务页面默认外部配音，已有任务保留原方式；二创确认前的内容处理逻辑未改动。
- 外部配音由 Worker 单独处理且不调用 TTS；字幕确认后才放行生图/渲染。配音与字幕按已确认版本读取；改词时使用新的图片缓存目录，仅节奏变化时复用图片。图片重跑不重做已确认配音。
- 新增迁移 `0034_external_narration.sql`，包含版本表/RLS、上传审核事务、媒体及图片替换事务领取与代次令牌保护；已通过SQL编辑器事务应用到生产，REST查询新表200。前端生产构建、191项完整Python回归、8项本机HTTP检查、本地PostgreSQL事务与权限验证通过。旧测试预期已同步现有规则，二创代码及提示词未改。
- 生产Auth/RLS/签名上传/RPC专项回归9项通过，临时账户、任务和静音文件均已清理；固定识别结果仅用于事务契约验证，真实ASR及完整成片尚未验收。
- 当前Supabase与Vercel后台均已登录；数据库迁移及生产专项回归已完成，生产前端 `/api/narration` 仍404。独立发布包不含.env，官方Vercel CLI首次设备授权已请求用户确认。未启动全局队列，未向生产发布依赖新表的前端。
- 真实ASR联调尚未通过：本机新安装的PyAV模块被Windows应用控制策略拦截，用户提供的云端SSH端口当前拒绝连接；正式验收前需恢复可用Worker环境，未降低系统安全策略。
- 已有《道德经》样音离线联调得到44条字幕，2条需人工校准；未用新功能执行生产上传、付费生图或成片验收。发布与验收步骤见 `docs/EXTERNAL_NARRATION_DELIVERY_2026-10-15.md`。
- 现有自动配音作为可选入口保留；最终外部配音尚待用户提供。云实例本轮未执行关机。

## 音色样本与国学调试稿已就绪（2026-10-15）

- 用户提供 `历史配音-王立群1013.wav`，已复制为 `ref-doc/cloningvoice/history-reference-1013.wav` 并核对 SHA-256：`F9B614910FDC62DDEBF7045B2749043AB09BE1F128E3DCA1AA8A090BB36CE60C`。
- 样本为 38.522 秒、44.1kHz、16-bit、双声道 PCM；左右声道相关度 0.999998，接近双单声道；峰值 -0.18dBFS，无整数满幅削波样本。IndexTTS 会使用参考音频前约 15 秒，真实试听后再决定是否另裁更合适的片段。
- 用户指定的《道德经》第01期五段调试文案已保存到 `worker/deploy/indextts25/guoxue_debug_script.txt`，部署后的试听默认使用 `history_reference_1013` 音色和该文案。
- 新恒源云 RTX 3090 实例已完成 IndexTTS 2.5 部署。源码固定为 `d9e41aac89fd00b3d71497fddb287b7f24613712`，模型固定为 `c39ce5ba981572cb187443877ff559dfb246ce63`；认证健康检查通过，GPU 推理串行保护已启用。
- 已用指定全文生成 4 种情绪配置 × 3 个固定 seed，共 12 个原始样音，保存在 `worker/output/indextts25-history-reference-1013/20261015-074915-896320/`。
- 原始输出检查发现官方 PCM 转换会把少量峰值硬限制到 0 dBFS；部署脚本现于 PCM16 转换前加入可复现的 -1 dB 余量。修复后的 seed 29 四个候选保存在 `worker/output/indextts25-history-reference-1013/20261015-080506-398758/`，全部 SHA-256 校验通过、峰值 -1.000 dBFS、满幅采样为 0。
- 最新部署包 `worker/output/indextts25-deploy.tar.gz` 为 5,151,667 bytes，SHA-256 `FFE0674217B1B6387C62A374EF35B53C3C44AEAA49B457DFA2E1447A1E9B20A2`，包内 13 个文件校验通过；恒源云模型下载默认使用可覆盖的 Hugging Face 国内镜像，避免直连超时。
- 第一轮情绪配置试听已完成，下一步在选定的 D 版基础上确认节奏参数，再进入字幕时间轴与视频拼接优化。
- 用户已选定 D 版 `reference_only` 作为情绪基准。已保持 seed 29 与其他解码参数不变，生成 6 个节奏隔离候选，目录为 `worker/output/indextts25-history-reference-1013/20261015-081428-795237/`；全部哈希通过、峰值 -1.000 dBFS、满幅采样为 0。
- 节奏候选时长：基准 83.298 秒、0.95 轻微加速 79.153 秒、1.05 轻微减速 87.431 秒、内部静音 0ms 为 82.698 秒、120ms 为 83.058 秒。180-token 长分段缩短到 69.561 秒，偏离过大，暂不作为生产候选。
- 用户反馈 D 版前后停顿太短、缺少换气，并提供官方参数截图。已确认截图与 D 版的音色情绪模式一致；服务现显式传入并记录 `do_sample=true`、`max_mel_tokens=1500`，其余截图参数原本已一致。
- 已按官方参数生成 200/400/600ms 三个内部换气间隔版本，目录为 `worker/output/indextts25-history-reference-1013/20261015-082934-077363/`；时长分别为 83.298/83.898/84.498 秒，三条哈希通过、峰值 -1.000 dBFS、满幅采样为 0。全文共有 4 个生成段、3 个可控段落连接点。
- 用户确认 600ms 大分段间隔仍缺少明显换气。已实现标点独立停顿后处理：先保留完整 D 版连贯语气，再把检测到的自然低能量间隙扩展到逗号 300ms、句号 800ms、问叹号 900ms、破折号 700ms、省略号 900ms、分号/冒号 450ms、引号 150ms。
- 标点停顿候选位于 `worker/output/indextts25-history-reference-1013/20261015-0900-punctuation-postprocess/`；48 个内部标点边界全部映射，新增静音 9.907 秒，总时长从 83.298 秒变为 93.205 秒，峰值仍为 -1.000 dBFS、满幅采样为 0。映射误差中位数 0.210 秒、最大 0.846 秒。
- 逐标点重新推理方案也已实测，但 49 个短句使总时长膨胀至 175.081 秒并会增加起音/收尾割裂风险，已排除。`worker/indextts25_longform_eval.py` 中按 profile 生成静音时误用统一 `pause_ms` 的错误已修正，并将停顿时长计入累计时间轴。
- 用户继续反馈标点后处理版语速偏快约 8%，且估算停顿位置不连贯。已用 IndexTTS 原生 `duration_factor=1.08` 重新生成连续 D 版，基础时长 89.904 秒；未使用后期拉伸。
- 已用 Whisper small 对慢速版生成中文字级时间戳，原文/识别字符匹配率 98.37%。48 个内部标点中 47 个映射到真实低能量间隙，1 个使用精确词尾时间，解决按字符比例估算造成的词中卡顿。
- 新候选位于 `worker/output/indextts25-history-reference-1013/20261015-0920-slow108-aligned/`：自然停顿版 93.375 秒（新增 3.471 秒），严格参考值版 96.055 秒（新增 6.151 秒）；两条峰值 -1.000 dBFS、无满幅采样、哈希通过。临时 Whisper 依赖已从 IndexTTS 主虚拟环境移除，并恢复锁定的 protobuf 3.19.6。

## 最新检查点（Supabase 连通确认与 IndexTTS 云端重建，2026-10-11）

- 后续调研已核对官方、BSAI ComfyUI、vLLM 与 SECourses 方案，尚未证实存在可直接替换且已针对本项目国学音色验收的版本。继续以固定官方版本为候选，加入三阶段参数试听配置及多随机种子复测。
- 修正显式 repetition_penalty 被截到 2.0 的范围错误（官方默认 10.0），补传向量模式的 emo_alpha；增加可重复试听用 seed 及解码参数入口。旧值未显式传入时不会受原截断影响。修正后 10 项 CPU 定向检查通过，部署包已重建并通过包内 9 个文件的校验；真实听感仍待 GPU 验证。

- 生产域名可访问；线上前端 Supabase 公共配置与本地一致。匿名身份查询返回 HTTP 200，数据库总计 17 条任务，新匿名身份在 owner RLS 下可见 0 条。当前用户浏览器身份尚未直接核验，旧任务列表为空更可能是匿名会话/域名变化。
- 首页本地增加加载、错误、重试与匿名会话隔离说明；Next.js 生产构建通过，尚未部署。
- 用户确认旧恒源云实例与镜像都已清除，需要新实例重新部署。旧地址不能用于恢复；新实例地址/端口及可用 SSH 登录尚待提供。
- 已准备 `worker/deploy/indextts25/` 重建工具：固定官方源码 commit、模型 revision 记录、上传安装、tmux 启动、随机密钥、健康检查、四组隔离国学试听。
- 本地保留 `旁白35.mp3` 和 `讲历史配音.mp3`；最小部署包位于 `worker/output/indextts25-deploy.tar.gz`，包含两套音色，未包含项目环境变量与数据库密钥。包内 8 个文件校验通过。
- IndexTTS 默认时长系数统一为 1.00；前端百分比语速映射到 duration_factor；国学/历史单人口播接入分段表达提示。服务显式保留音色匹配模式，开放内部静音和 tokens 分段参数；旧启动脚本移除固定测试密钥默认值。
- 4 项 CPU 服务定向检查、Python 语法检查及 PowerShell 语法检查通过。Linux 安装脚本尚未在新实例运行，真实 GPU 推理、短稿盲听、长稿字幕对齐与转场优化均待接通云端后执行。
- 云端重建步骤见 `worker/deploy/indextts25/README.md`。使用新的隔离任务开展后续配音/字幕/渲染验收。

## 追加检查点（历史口播重音与停顿，2026-08-15）

- 历史音色提示已强化事件铺垫、冲突爆发、转折、因果和结果的重音与语调起伏，保持克制的历史讲述感，避免平铺直叙或夸张表演。
- `indextts25_longform_eval.py` 已支持句间 `--pause-ms` 停顿；修复 Windows 下临时静音文件句柄未释放导致的清理失败。
- 专项测试 4/4、Worker 全量回归 142/142 通过；当前正式任务和原 CosyVoice 成片未被覆盖。
- 恒源云实例当前已关机（SSH `Connection refused`）；下一轮试听前需控制台手动开机，试听完成后继续执行安全关机。
- 本轮试听已保存：旁白35 `1.08` 为 130.879 秒，旁白35 `1.00` 为 120.255 秒；历史 `1.00 + 120ms` 句间停顿为 19.829 秒。目录为 `worker/tts-comparisons/indextts25-single-narrator35-current/preview-*` 与 `worker/tts-comparisons/indextts25-history-narrator-smoke/preview-100-pause120`。
- 用户确认旁白35 `preview-100` 更好，历史版本可使用；选定配置已更新为旁白35 `f_single_narrator35_100`，历史 `history_narrator_100_pause120`。待恒源云再次开机后重跑当前任务 `TTS + render`。
- 已按 `ref-doc/promote-TTS停顿.md` 生成 IndexTTS 隔离标点试听：旁白35、`duration_factor=1.00`，每类标点 2-3 处，文档值域中间值为 300/800/900/700/900/450/150ms。试听成片实际 49.382 秒，其中语音 39.428 秒、额外静音约 9.95 秒；云实例已关机。

## 最新进度检查点（IndexTTS2.5 生产接入待长文验收，2026-08-15）

- 单人口播的正式目标顺序已确定为 `IndexTTS2.5 -> CosyVoice2 -> Edge`；回退按整篇重做，禁止同一成片逐段混用不同音色。
- 已增加 IndexTTS2.5 HTTP Provider、恒源云常驻服务脚本、F 组 QwenEmotion 参数、鉴权、健康检查、GPU 串行推理和可选空闲关机。
- IndexTTS 长稿分段扩展到约 220 字上下文；所有 Provider 的无标点文本改用标点、空白、中文分词边界和书名/专名保护，不再直接按字符上限切词。
- 音色管理与任务快照已支持 `indextts25`，新增“新任务默认音色”；迁移 `0024_indextts25_provider.sql` 尚未部署。
- 当前真实成片已生成 `final.mp4`，时长 372.72 秒；原质检唯一失败为书名号计数误报。本地已修复计数，并将所有字幕规范问题降为提示，不再拦截成片完成。
- 本地验证：136 项 Worker 测试、Python 编译、Next.js 生产构建和 `git diff --check` 通过。
- 恒源云实例已确认关机。IndexTTS F 仍为 `provisional`，2000 字真实长文听感、字幕对齐和服务连通性仍 `待验证`，生产启用门保持关闭。

## 最新进度检查点（部署成功，进入 TTS Provider 接入，2026-08-09）

### P0 可靠性收口（已部署，待隔离任务验收）

- 阶段重跑不再使用会覆盖下游 `params` 的前端 fallback；RPC 缺失或未更新记录时明确失败，不再静默破坏改写确认状态。
- 新增 `0007_reliable_review_and_rerun.sql`：重跑和改写确认均由数据库事务原子更新阶段与任务状态，并正确失效下游人工确认参数。
- APIMart 每个九宫格批次持久化 Provider task ID、提示词摘要和幂等键；轮询超时后恢复原任务，不重新提交付费生图请求。
- Worker 不再对整个有外部副作用的 handler 做三次重试；数据库、轮询和下载重试由各处理器在可恢复边界内负责。
- 本地验证：59 项 Worker 测试、Python 编译、Next.js 生产构建和 `git diff --check` 均通过。
- 已确认：远程 Supabase 已执行 `0007`，两个 RPC 可被调用并返回预期业务错误；提交 `052647f` 已推送到 `origin/master`。
- 已确认：用户已确认 Vercel 部署完成。
- 待验证：使用全新隔离任务验证改写确认、阶段重跑和 APIMart 超时恢复；不要启动全局 Worker，历史队列仍含遗留 pending/processing 状态。

### 当前状态

- 最新线上基线 `b664417` 已完成部署，并由用户确认部署成功；本地 `master` 与 `origin/master` 已对齐到该提交。
- 已部署基线包含清洗异常扩写保护和 TTS Provider 边界；生产任务仍默认使用 Edge TTS，不会自动切换到未验收的新音色服务。
- 当前主阶段已从部署转入 TTS Provider 接入与试听验收，目标 Provider 为 CosyVoice2。
- 本地已形成 CosyVoice2 HTTP 适配器、隔离试听对比工具、配置示例和自动化测试改动；这些改动仍在工作区中，`未上线`。

### 已验证与边界

- 已确认：`b664417` 部署成功，线上发布阻塞已解除。
- 仅本地验证：Python 编译、16 项 Provider 定向测试和 57 项 Worker 全量测试通过。
- 待验证：真实 CosyVoice2 endpoint、音色 ID/授权参考音频、长句停顿、音质、时长与字幕对齐。
- 生产启用门保持关闭；在真实试听验收通过前，Edge TTS 继续作为默认生产 Provider 和回退基线。

### 下一步

1. 配置真实 CosyVoice2 接口与已授权音色，使用同一段文本生成 Edge/CosyVoice2 隔离对比音频。
2. 按音频可解码、停顿自然度、音色质量、时长合理性和字幕对齐逐项记录验收结果。
3. 验收未通过时继续使用 Edge；全部通过后再单独决定是否启用生产 Provider，不覆盖既有任务音频。

## 最新修复检查点（清洗可解释与九宫格4:3切割，2026-08-06）

### 已实现

- 清洗产物新增 `change_summary`，记录原文/清洗后字数、缩减比例，以及最多 24 条删减或替换片段；清洗页面在正文顶部展示该摘要。
- 九宫格仍按“每 9 个分镜只调用一次生图 API，再由 Pillow 本地切成 9 张”执行，不改为逐图调用，保持成本控制。
- `gpt-image-2` 九宫格源图默认请求尺寸调整为可配置的 `1536x1024`；3×3 边界采用比例取整坐标，覆盖整张源图且不累计像素误差。
- 每个源格按中心安全区精确裁成 4:3；生图提示词要求主体位于中央安全区、仅允许极细分隔线，禁止宽白边和拼贴边框。
- 每批九宫格原图以 `image_grid` artifact 单独保存，同时记录原图尺寸、每行列切割边界、目标比例和校验状态，可追溯每张小图来自哪张总图。
- 若模型返回的原图比例与请求尺寸不一致，程序直接停止切图并报错，避免错误图片进入自动剪辑。

### 验证状态

- Worker 单元测试 25 项通过，覆盖边界无缝覆盖、4:3 输出尺寸和异常方形画布拒绝切割。
- Python 编译、Next.js 生产构建通过。
- 当前任务 `c04850bd-61a5-4c3b-bd17-be407064710c` 的旧版 image 已完成，book 处于 needs_review；旧版未保存九宫格原图，无法事后还原错误切割来源。
- `待验证`：使用新版代码真实重跑一批九宫格，核对源图、9 张切图和自动剪辑预览后再进入 render。

## 最新恢复检查点（发布后等待 V1→V2 验收，2026-08-06）

### 当前状态

- 功能与发布记录已同步 `origin/master`；本检查点之前的发布记录基线为 `9563057 docs: record task cancellation deployment`。
- 功能发布基线为 `a51f5b1 fix: make pending task cancellation reliable`；两个生产域名和新版前端包已完成线上核验。
- 当前没有 Python/FFmpeg Worker 进程，不会消费历史队列。
- Supabase 最新只读核验：0 个 pending 任务；阶段表仍有 13 个历史 pending 和 4 个 7 月遗留 processing。
- 待处理任务现在可“取消并删除”；运行中任务只取消不删除，Worker 不会把 cancelled 任务重新激活。

### 下一步

1. 用户在生产首页新建健康类 V1，并提供任务 ID。
2. 仅使用 `WORKER_TASK_ID=<V1任务ID>` 启动 Worker，不启动全局消费。
3. 完成 V1 后人工点击“生成二次发布版本”创建独立 V2。
4. 将过滤器切换到 V2 ID，验收前三阶段 cancelled、rewrite 来源为 V1 `final_text`，以及 V2 独立图片、配音和成片。

### 阶段结论

- 主阶段：发布完成，进入端到端验收阶段。
- 已验证：取消/删除闭环、线上 RLS、生产前端包、Worker 取消状态保护。
- 待验证：一条真实健康类 V1→人工确认→V2 全流程。

## 最新修复检查点（待处理任务取消与删除，2026-08-05）

### 已修复

- 新建任务未启动 Worker 时，任务详情会把“全阶段 pending”识别为尚未开始，并提供“取消并删除”操作。
- 删除采用受控流程：先把任务置为 cancelled，再取消所有 pending 阶段；确认没有活动阶段后才删除任务，避免误删已经开始处理的数据。
- 已开始处理的任务只允许取消，不直接删除；取消和删除操作现在会等待 Supabase 响应并显示明确的成功或错误信息，不再静默失败。
- Worker 在阶段处理结束汇总任务状态前会复核任务是否已取消，避免把 cancelled 任务重新写回 processing。

### 验证与发布

- Next.js 生产构建通过。
- Worker 单元测试 21 项通过，新增“已取消任务不会被重新激活”回归用例。
- 修复提交 `a51f5b1` 已推送到 `origin/master` 并完成 Vercel 自动部署；生产任务页返回 HTTP 200，新前端包已包含“取消并删除”逻辑。
- 线上 RLS 烟测通过：临时匿名用户创建 8 阶段 pending 任务后，取消、阶段同步、删除和清理均成功。
- 原待处理任务 `d2ad457e-04bc-413a-a9f2-c1feacd49eb2` 已按要求取消并删除，复核任务和阶段均无残留。

## 最新恢复检查点（人工二次发布流程，2026-08-05）

### 当前本地状态

- 远端实现基线：`3745849 feat: isolate worker to a test task`，人工 V2 流程、数据库迁移兼容和 Worker 指定任务隔离均已推送。
- 本地未推送提交：`fb47fbb chore: save edge tts voice catalog`；`master` 比 `origin/master` 超前 1 个提交。
- `worker/tts_voices.json` 已保存 edge-tts 7.2.8 当前返回的 8 个 `zh-CN` 音色，默认仍为 `zh-CN-XiaoxiaoNeural`。
- 旧 Worker PID `7480` 已停止；当前没有启动全局 Worker，历史队列不会继续被消费。
- 数据库最后只读核验：13 个历史 pending，另有 4 个更新时间停留在 7 月的遗留 processing。
- 下一操作：用户在生产首页新建健康类 V1 任务并提供任务 ID；使用 `WORKER_TASK_ID=<新任务ID>` 启动新版 Worker，只处理该任务。

### 本轮已实现（已部署，待端到端验收）

- 明确两次去重语义：`promote-2` = 首次去重，生成首发 V1；`promote-3` = 首发稿验证为爆款后，人工触发的二次去重，生成独立 V2。
- 健康类提示词新增 `worker/prompts/categories/health/initial_dedup.txt` 和 `repost_dedup.txt`；旧 `rewrite.txt` 保留为首次去重兼容别名。
- V2 不读取原始清洗稿，Worker 强制读取 V1 rewrite artifact 中的 `final_text`，再运行 `repost_dedup`。
- 新增任务版本字段和父子关系：`rewrite_mode`、`source_task_id`、`version_no`；V2 自动取消 ingest/transcribe/clean，独立运行 rewrite→image→book→tts→render。
- 新增 `create_repost_task(uuid)` 安全函数，只有当前用户的 render 阶段完成后才能创建 V2；重复点击会返回现有未取消/未失败的 V2。
- V1 成片详情增加人工确认按钮“生成二次发布版本”，确认后跳转到独立 V2 任务；不会覆盖 V1 的文案或视频。

### 本轮验证

- Worker 单元测试：20 项通过（包含指定任务隔离测试）。
- Python 编译：通过。
- Next.js 生产构建：通过。
- 数据库迁移 `0003`、`0004`、`0005` 已由用户确认在 Supabase 执行成功；其中 0005 对尚未执行 0003 的环境做了 `content_category` 兼容补充。
- 当前部署：提交 `fd7572c` 已推送并完成 Vercel 部署；生产首页和既有任务页均返回 HTTP 200。
- 当前状态：`待验证`，尚未执行真实 V1→人工确认→V2 端到端流程。

### 下一步

1. 等待用户提供新建健康类 V1 的任务 ID；不要在没有任务 ID 时启动 Worker。
2. 使用新增 `WORKER_TASK_ID` 过滤器受控启动新版 Worker，不处理历史队列。
3. 完成 V1 全流程，确认 render 完成后人工点击“生成二次发布版本”。
4. 切换过滤器到 V2 任务 ID，验证前三阶段为 cancelled、rewrite 输入确实来自 V1 `final_text`，并验证 V2 生成独立图片、配音和 final.mp4。

## 上一恢复检查点（基础链路，2026-08-05）

### 当前节点

- 主阶段：人工二次发布流程开发完成，等待迁移、部署和 V1→V2 验收。
- 当前功能实现基线：`5a7bfd8 improve health rewrite compliance and tts reliability`。
- `master` 与 `origin/master` 已对齐到 `5a7bfd8fc177db8f8312f7c8e164ccaac5e64b2f`，已触发 Vercel 自动部署。
- 生产首页及既有任务页已返回 HTTP 200；用户已确认部署完成。
- 本轮重点仅为健康类图书视频；社科类、教育类只保留首页入口，暂不开发；XHS 暂不测试。

### 本轮已完成

- 健康类提示词按阶段拆分管理：清洗、轻量改写、合规检查；改写不再提供 A/B/C 三个方向。
- 改写目标调整为：尽量保留原文长度、开头钩子、中间内容和结尾，只做必要的轻量改写。
- 新增 `skills/wechat-video-book-compliance/`，在改写生成后和人工确认时执行健康内容合规检查。
- 首页增加健康类、社科类、教育类分类入口；仅健康类可用，其他分类显示“待开发”。
- 分镜目标调整为平均约 8 秒、每镜约 24-32 字；图片按 4:3 使用。
- 成片保留片头书名卡；画面使用一种 Zoom In 动效和叠化切换；画面上方固定书名/作者，下方固定简短免责声明。
- TTS 仍使用 `edge-tts 7.2.8`，默认音色为 `zh-CN-XiaoxiaoNeural`；已改为只传纯正文，过滤时间点、分隔符、Markdown、JSON、SSML、镜头和画面说明等格式内容。
- TTS 约按 90 字/26 秒拆段、3 路并发合成，并由 FFmpeg 合并音频和平移字幕时间戳。
- Supabase 网络层已增加显式证书包、关闭 HTTP/2、缩短 keepalive、有限重试和客户端重建；Storage 与 render 查询也已加入重试。
- 评论策略已明确：优先购买意向评论；没有购买意向时，补充高点赞或高回复评论。评论抓取仍取决于采集源实际返回能力。

### 已验证证据

- 既有任务 `36b9ff99-55c8-4b62-a919-8388138c4e7d` 已用新版逻辑单独重跑 TTS 和 render。
- TTS 从异常的 `4267.207` 秒降为 `434.861` 秒，共 25 个合成批次、68 个字幕片段，检查结果 `contains_ssml: false`，阶段状态为 `done`。
- render 阶段状态为 `done`，新 `final.mp4` 已覆盖：1080x1920、70 张图片、Zoom In + dissolve，任务总状态为 `done`。
- Worker 测试 19 项通过；Python 编译通过；Next.js 生产构建通过；真实 edge-tts 短句烟测通过；新版 Supabase 客户端只读查询曾通过。

### 重要边界

- Supabase 当前尚无 `tasks.content_category` 列。迁移文件已提交但未执行；前端创建任务暂不写该字段，Worker 在字段缺失时回退为健康类。
- 2026-08-05 最后确认时，全局 Worker PID 为 `7480`，启动于 `2026-08-05 07:35:22`，仍加载旧代码；数据库另有 13 个 pending 阶段。
- 不要直接重启全局 Worker，否则可能批量消费旧 pending。下次开始时必须先复核 Worker PID、pending 数量及目标测试任务 ID，再决定受控启动方案。
- Index-TTS 尚未接入。接入前需确认 API 地址、鉴权、请求/响应、参考音频上传、单次长度限制及时间戳能力；当前生产测试仍走 edge-tts。
- 本轮首次“全新任务端到端”验收尚未完成，不能据此宣称整条生产链路已经验收通过。

### 下次直接从这里继续

1. 读取本节和 `RESUME_PROMPT.md`，执行 `git status --short --branch` 与 `git log -1 --oneline`。
2. 获取用户新建的健康类测试任务 ID；不要复用旧任务判断完整新链路。
3. 只读检查全局 Worker、pending 阶段和新任务各 stage 状态，避免旧任务被意外消费。
4. 设计并执行受控的新版 Worker 测试，优先跟踪新任务的 rewrite、image、book、tts、render。
5. 按“改写完整性、8 秒分镜、4:3 图片、纯正文配音、书名/作者/免责声明、Zoom In + 叠化”逐项验收并记录证据。
6. 测试完成前不部署额外改动；出现问题先定位并修复，再决定是否重新部署。

## 部署

- 前端：`content-ecosystem-neon.vercel.app`（GitHub master → Vercel 自动部署，root = `web/`）
- Worker：本地运行 `python worker/main.py`
- DB/Storage：Supabase（私有 bucket `artifacts`）

---

## 8阶段流水线

| seq | kind       | 产物                                      | 评审门                     |
|-----|------------|-------------------------------------------|----------------------------|
| 1   | ingest     | `{taskId}/audio.mp3`                      | 失败时手动上传             |
| 2   | transcribe | `{taskId}/transcript.json`                | 无                         |
| 3   | clean      | `{taskId}/clean.json`                     | 无                         |
| 4   | rewrite    | `{taskId}/rewrite.json`                   | 必须选候选才继续           |
| 5   | image      | `{taskId}/images_index.json` + 分图       | 无                         |
| 6   | book       | `{taskId}/book.json`                      | confidence=low 时才进      |
| 7   | tts        | `{taskId}/tts.mp3` + `tts_subtitles.json` | 无                         |
| 8   | render     | `{taskId}/final.mp4`                      | 无                         |

---

## 前端组件（Notion 风格重构后）

| 文件 | 用途 |
|------|------|
| `web/app/globals.css` | CSS design tokens、keyframes、utility classes |
| `web/components/Sidebar.tsx` | 汉堡收起侧边栏，工具导航 + 任务列表 |
| `web/components/PipelineBar.tsx` | 8节点可点击流程条，状态图标 |
| `web/components/StageDetail.tsx` | 按 kind 分发到各子面板 |
| `web/components/detail/_shell.tsx` | DetailShell 公共壳 + TextBtn |
| `web/components/detail/IngestDetail.tsx` | 统计卡片 + 粉丝量 + 热门评论 |
| `web/components/detail/TranscribeDetail.tsx` | 逐字稿展示 + 字数 |
| `web/components/detail/CleanDetail.tsx` | 清洗后 / 原文切换 |
| `web/components/detail/RewriteDetail.tsx` | A/B/C 候选选择，写 chosen_index |
| `web/components/detail/BookDetail.tsx` | 书名内联编辑，确认继续 |
| `web/components/detail/TtsDetail.tsx` | 音频播放 + 合成文案 |
| `web/components/detail/ImageDetail.tsx` | 3列网格 + 灯箱，批量 signed URL |
| `web/components/detail/RenderDetail.tsx` | 9:16 视频播放 + 下载 |
| `web/app/task/[id]/page.tsx` | 2列布局，自动选中活跃节点 |
| `web/app/page.tsx` | 首页，新建任务表单 + 任务列表 |
| `web/app/api/signed-url/route.ts` | 服务端 signed URL（需 `SUPABASE_SERVICE_KEY`） |

---

## 环境变量

### Worker（`worker/.env`，已 gitignore）
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
OPENAI_API_KEY=
DEEPSEEK_API_KEY=        # 可选，book 阶段优先用
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE=int8
REWRITE_MODEL=gpt-4o-mini
CLEAN_MODEL=gpt-4o-mini
```

### Vercel
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=    # 非 NEXT_PUBLIC_，仅 API route 使用
```

---

## 已修复 Bug（全量）

| 提交 | 问题 | 修法 |
|------|------|------|
| `f5264bd` | handler 返回 `"failed"` 被 else 分支覆盖成 `"done"` | `else` → `elif status == "done"` |
| `3912f70` | `claim_next_stage` 不接受 `cancelled` 作为前置完成状态 | `== "done"` → `in ("done", "cancelled")` |
| `3912f70` | 重跑时 `chosen_index`/`manual_book_name` 残留 | `rerun()` 清除这两个 params |
| `64fb956` | `maybe_finish_task` 不接受 `cancelled` | 同上改法 |
| `2aa85b6` | 私有 bucket 签名 URL 用 anon key 失败 | `/api/signed-url` 改用 service key |
| `77e9621` | 下载按钮依赖 `task.status===done` | 改为 `renderStage?.status==="done"` |
| `044a62e` | book.py 总是选候选 A（读自身 params） | 增加 DB fallback 查 rewrite stage params |
| `044a62e` | tts 把 `<break>` 标签当文字朗读 | 构建完整 SSML，`html.escape()` + `<speak><voice>` |
| `06b4047` | rewrite short-circuit 时 `chosen` 字段不回写 JSON | 下载 → 更新 chosen → 重新上传 |
| `7e9861a` | ImageDetail 读错数据结构（`d.images` 不存在） | 改为读 `images_index.json` 数组，批量获取 signed URL |
| `de58b3d` | WinError 10054 连接重置污染日志 | 识别连接类错误静默 + 2s 退避 |
| `5ece063` | PDF 上传报 413（Vercel 4.5MB 限制） | 客户端直传 Supabase Storage，API 只接收 `file_path` |
| `d6977b7` | 中文文件名导致 Storage key 非法 | 上传时只用 `Date.now().pdf` 作为文件名 |
| `4a62a36` | 生成选题报 500（OpenAI key 欠费） | topics route 切换为 DeepSeek |
| `d9cd5f3` | "解析 LLM 返回失败" | 剥除 DeepSeek 偶发的 markdown 代码块包裹再 `JSON.parse` |
| `466875f` | 生成文案报 422（合规硬拦截） | 改为软警告：返回 `banned_word` 字段，前端标红不阻断 |
| `77c39ac` | 导出 ZIP 失败（截图被 `scale(0.6)` 缩放节点） | 添加隐藏原始尺寸节点，`html-to-image` 截图该节点 |
| `d11c0d5` | 切 tab 清空文案/卡片 state | 改用 `display:none` 隐藏 tab 而非卸载组件 |
| `d11c0d5` | 文案生成后无法直接进卡片工厂 | 正文右上角加「🎨 送入卡片工厂」按钮 |
| `5067972` | PDF 服务端解析报 500（@napi-rs/canvas 缺失） | `next.config.js` 加 `serverExternalPackages: ['pdf-parse']` |
| `39b344c` | `DOMMatrix is not defined`（pdfjs-dist 需要浏览器环境） | 将 PDF 解析完全移至客户端（pdfjs-dist 浏览器版），服务端只存数据 |

---

## 已完成功能（本轮新增）

- **Notion 风 UI 重构**：2列布局，Sidebar 汉堡收起，PipelineBar 可点击，各阶段独立详情面板，fadeSlideIn 动画
- **粉丝量**：从 f2 视频响应提取 `fans_count`，写入 `tasks.author`，采集面板展示
- **热门评论**：`fetch_hot_comments()` 抓 top-10 按点赞排序（best-effort），保存到 artifact meta
- **改写候选选择修复**：选 B/C 后 book/tts/image 均正确使用所选候选
- **小红书图文工作台**（`/xhs`）：
  - 知识库管理（文字粘贴 + PDF上传解析）
  - 书籍内容段落选取（复选框，已选字数实时显示）
  - 主题矩阵（OpenAI生成选题卡，内联编辑标题，合规检测）
  - 文案生成室（DeepSeek，三种文风，正文+评论剧本，一键复制）
  - 视觉卡片工厂（Cover/Body/Tail 三类卡片，品牌名可配置）
  - ZIP 批量导出（html-to-image × 2倍像素 + JSZip）
  - 自定义域名：`content-ecosystem.socra.cn` 绑定 Vercel
  - **测试阶段全流程修复**（2026-07-07）：413/非法key/500/解析/422/ZIP/tab-state/卡片关联，共8个bug全部修复

---

## 下一阶段计划

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P0 | **确认 `/api/xhs/cards` 使用的 LLM** | 检查是否仍用 OpenAI key（欠费），如是切换 DeepSeek |
| P0 | **XHS 端对端验收** | PDF 上传 → 选题 → 文案 → 卡片工厂 → 导出 ZIP 完整跑通 |
| P1 | **Prompt 质量优化** | 跑 3-5 条真实视频，根据输出调整 `prompts/rewrite.txt`、`prompts/clean.txt` |
| P1 | **XHS 卡片样式优化** | 根据实际导出效果调整字体大小、间距、高亮样式 |
| P2 | **渲染模板优化** | `worker/stages/render.py` 字幕样式、字体、9:16 布局深度定制 |
| P3 | **批量任务** | 一次提交多链接，自动队列 |
| P3 | **数据反馈** | 记录候选选择频率，用于 prompt A/B 测试 |

---

## 已知注意事项

- `fans_count`：取决于 f2 返回字段名（`fans_count` 或 `follower_count`），首次运行验证
- 热门评论：f2 版本若不支持 `fetch_video_comments` 会静默跳过，显示"暂无评论数据"属正常
- 图片阶段：需要 OpenAI API Key 有 `gpt-image-*` 权限
- Windows 部署：`WinError 10054` 已静默，worker 自动重连

---

## 数据库注意事项

确认已执行（Supabase SQL Editor）：

```sql
ALTER TYPE stage_status ADD VALUE IF NOT EXISTS 'cancelled';
```

---

## Render 阶段依赖

render 需要以下 artifacts 已存在：

- `type = "image_index"`（image 阶段产出）
- `stage_kind = "tts"` + `type = "audio"`（tts 阶段产出）
- `type = "book"`（book 阶段产出，可选）

任一缺失 → render 报 "缺少图片或音频产物"。

# 已确认成稿直入生产线

## 入口契约

新建项目选择 `ready_script` 后，前端把原样文案写入 `ingest.params.ready_script_text`，任务保持 `configuring`，模板参数保存成功后才排队。`source_platform=manual`、`source_url=null`，不伪造采集链接。

Worker 的 `ready_script.materialize` 是输入适配器：生成与正常二创完全相同的 `rewrite` JSON 产物（至少含 `candidates/chosen/final_text/content_category`），并同步 `rewrite.params.final_text`。现有配音、生图、公共素材、字幕、成片继续读取这个统一产物，不根据输入来源分叉。

采集、逐字稿、清洗节点标记 `done` 且附 `skipped` 原因，前端隐藏其流程导航；改写节点显示为「确认成稿」。重新运行改写节点仍由此适配器恢复产物，不调用二创模型。后续新增其他输入方式应添加新的入口适配器，保持下游产物契约不变。

## 边界

- 文案 20–30000 字符；保留分段和标点，不自动改写。
- 正常链接采集与二创流程不变。
- 未保存好成稿或模板时任务停留在 `configuring`；失败的创建会标记取消，不进入 Worker。
- 本模式没有原始对标视频及其互动数据，历史分析应以人工导入成稿标识区分。

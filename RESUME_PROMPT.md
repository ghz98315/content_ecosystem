# 重启会话提示词

每次开启新对话时，把下方内容粘贴给 Kiro，即可快速恢复上下文。

---

## 📋 模板（直接复制粘贴）

```
项目：AI图书带货视频创作台 / 小红书图文生成器
路径：D:\github\content_ecosystem
进度文件：PROGRESS.md（请先读取）

背景：
- 8阶段视频流水线已全部完工（ingest→transcribe→clean→rewrite→image→book→tts→render）
- 前端 Notion 风格重构完毕，部署在 content-ecosystem-neon.vercel.app
- Worker 本地运行：python worker/main.py
- 存储：Supabase 私有 bucket artifacts

当前任务：[在此填写你想做的事，例如：]
- 继续开发小红书图文生成流程
- 调试 XXX 阶段的问题
- 优化 XXX 功能

请先读取 PROGRESS.md 了解最新进度，然后我们继续。
```

---

## 🔖 常用场景快捷语

| 场景 | 粘贴内容 |
|------|----------|
| 继续视频号流水线 | `读取 PROGRESS.md，继续视频号带货视频流水线开发，当前需要：[描述具体需求]` |
| 继续小红书图文流程 | `读取 PROGRESS.md，继续开发小红书图文生成流程（采集→改写→配图→排版预览）` |
| 调试 Worker | `读取 PROGRESS.md，Worker 报错如下：[粘贴错误日志]` |
| 跑新视频链接 | `读取 PROGRESS.md，帮我跑这条视频：[粘贴链接]，排查流水线问题` |
| UI 调整 | `读取 PROGRESS.md，需要调整前端 [组件名] 的显示效果：[描述需求]` |
| Prompt 优化 | `读取 PROGRESS.md，根据以下输出结果优化 prompts/rewrite.txt：[粘贴输出]` |
| 自定义域名/访问问题 | `读取 PROGRESS.md，前端部署在 Vercel，需要配置自定义域名提升国内访问速度` |

---

## 💡 小贴士

- 每次 Kiro 做完一个功能模块，要求它更新 `PROGRESS.md` 的"已完成功能"和"下一阶段计划"
- 重大节点可以说："帮我保存一个 checkpoint 到 memory"
- 如果 Kiro 忘记了上下文，说："读取 PROGRESS.md 和 RESUME_PROMPT.md 恢复上下文"

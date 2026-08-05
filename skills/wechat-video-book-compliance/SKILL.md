---
name: wechat-video-book-compliance
description: Review Chinese WeChat Channels book-video scripts for health-content red lines, prohibited advertising language, medical claims, fear tactics, false authority, and medical diversion. Use when checking a health-book transcript or rewritten voiceover before TTS, storyboarding, rendering, publication, or reuse. Social-science and education profiles are reserved but not yet supported.
---

# 视频号书籍内容合规检查

对健康类书籍短视频文案执行最终风险检查。输出风险报告，不承诺平台审核结果，不把风险判断当作医疗或法律意见。

## 检查流程

1. 确认内容分类。当前仅支持 `health`；社科和教育内容应标记为“规则待开发”，不要套用健康规则得出通过结论。
2. 完整读取 [references/health-rules.md](references/health-rules.md) 和 [references/prohibited-terms.md](references/prohibited-terms.md)。
3. 先检查可明确识别的词语和话术结构，再结合上下文检查诊断、疗效、食疗、恐吓、权威背书和医疗导流。
4. 区分中性知识引用与商品功效宣传。疾病名称、医生、治疗等词语单独出现时不自动判为高风险。
5. 对每个问题引用原文中的完整片段，说明原因，并给出不增加事实的最小修改建议。
6. 存在 `high` 风险时返回 `blocked`；仅有 `medium/low` 时返回 `warning`；没有问题时返回 `pass`。

## 输出格式

返回以下结构，不直接重写整篇文案：

```json
{
  "status": "pass|warning|blocked",
  "issues": [
    {
      "level": "high|medium|low",
      "category": "风险类别",
      "text": "原文风险片段",
      "reason": "结合语境的具体原因",
      "suggestion": "最小修改建议"
    }
  ]
}
```

## 判定边界

- 不因规避关键词而改动人物、书名、数字、时间、案例或因果关系。
- 不把不确定问题写成确定违规；使用 `medium` 并要求人工复核。
- 不以“已通过本 Skill”宣称一定符合视频号最新规则。
- 规则资料可能滞后；平台政策更新时同步更新参考文件和运行时规则。

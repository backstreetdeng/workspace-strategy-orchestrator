---
name: intent-classifier
description: "汽车市场分析意图分类器：识别用户查询类型（趋势分析/竞品分析/机会识别等），提取品牌、价位等维度"
homepage: 暂无
metadata: {"clawdbot":{"emoji":"🔍"}, "openclaw": {"tools": ["classify"]}}
---

# 汽车市场分析意图分类器

## 功能说明

解析用户问题，识别分析意图类型，返回结构化的分类结果供后续工作流使用。

## 工具列表

| 工具 | 用途 | 参数 |
|------|------|------|
| `classify` | 意图分类 | `question`: 用户问题 |

## 使用示例

```prose
# 方式1：在 session 中调用
let intent = session "意图识别"
  prompt: "使用 intent-classifier.classify 工具分析用户问题：{question}"

# 方式2：直接引用工具（在支持自动调用的环境中）
# AI 会自动识别并调用 classify 工具
```

## 输出格式

```json
{
  "success": true,
  "result": {
    "intent_type": "竞品分析",
    "confidence": 0.85,
    "keywords": ["竞品", "对比", "比亚迪"],
    "dimensions": {"价格区间": "20-30万", "车型级别": "SUV", "动力类型": "纯电"},
    "need_sentiment": true,
    "brands_mentioned": ["比亚迪", "特斯拉"],
    "price_range": "20-30万",
    "vehicle_type": "纯电SUV"
  }
}
```

## 意图类型

| 意图类型 | 关键词 | 说明 |
|---------|--------|------|
| 趋势分析 | 趋势、发展、前景 | 市场走势预测 |
| 画像分析 | 用户画像、消费者 | 目标用户特征 |
| 竞品分析 | 竞品、对比、竞争 | 竞争格局分析 |
| 机会识别 | 机会、切入点 | 市场机会识别 |
| 政策解读 | 政策、补贴、退坡 | 政策影响评估 |
| 综合分析 | 分析、研究、评估 | 无明确意图 |

## 技术实现

- 主文件: `skill_main.py`
- 核心逻辑: `intent_classifier.py`
- 依赖: MiniMax/OpenAI API 或本地 Ollama

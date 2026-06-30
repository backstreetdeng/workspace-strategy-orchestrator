---
name: pg-vector-search
description: "PostgreSQL向量数据库检索：根据语义相似度检索市场数据、行业报告、政策文件"
metadata: {"clawdbot":{"emoji":"🔍"}, "openclaw": {"tools": ["search"]}}
---

# PostgreSQL 向量检索 Skill

## 功能说明

基于语义相似度从向量数据库中检索相关文档。适用于：
- 市场数据检索
- 行业报告检索
- 政策文件检索
- 知识库问答

## 工具列表

| 工具 | 用途 | 参数 |
|------|------|------|
| `search` | 向量语义检索 | `query`: 查询文本, `top_k`: 返回数量, `search_mode`: 检索模式 |

## 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| query | string | 必填 | 查询文本 |
| top_k | int | 6 | 返回结果数量 |
| search_mode | string | "hybrid" | 检索模式：hybrid/vector/keyword |

## 输出格式

```json
{
  "success": true,
  "count": 6,
  "results": [
    {
      "content": "文档内容...",
      "score": 0.85,
      "metadata": {"source": "行业报告", "date": "2024-01"}
    }
  ]
}
```

## 使用示例

```prose
session: analyst
  prompt: "使用 pg-vector-search 检索相关内容：search(query='比亚迪市场战略', top_k=6)"
```

## 技术实现

- 主文件: `vector_search.py`
- 函数: `vector_search(query, top_k, search_mode)`
- 依赖: psycopg2, PostgreSQL + pgvector 扩展

"""
pg-vector-search skill
向量检索技能 - 封装RAG引擎的混合检索（向量+关键词+RRF融合）

功能：
- 向量检索（语义相似度）
- 关键词检索（BM25/ILIKE）
- 混合检索（RRF融合）
"""

import sys
import os
import json
from typing import Dict, Any, List, Optional

# 添加RAG引擎路径
RAG_ENGINE_PATH = r"E:\AI\data\envs\car_agent_env\ai-decision\rag-engine"
if RAG_ENGINE_PATH not in sys.path:
    sys.path.insert(0, RAG_ENGINE_PATH)


def load_dotenv():
    """加载环境变量"""
    env_path = os.path.join(os.path.dirname(RAG_ENGINE_PATH), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


load_dotenv()


def vector_search(
    query: str,
    top_k: int = 6,
    brand: str = None,
    source: str = None,
    search_mode: str = "hybrid"
) -> Dict[str, Any]:
    """
    向量检索主函数

    Args:
        query: 检索查询
        top_k: 返回数量
        brand: 品牌过滤（可选）
        source: 来源过滤（可选）
        search_mode: 检索模式
            - "vector": 仅向量检索
            - "keyword": 仅关键词检索
            - "hybrid": 混合检索（默认）

    Returns:
        检索结果
    """
    try:
        from retrieval.vector_store import (
            vector_search as vs_vector_search,
            keyword_search as vs_keyword_search,
            hybrid_search as vs_hybrid_search
        )

        # 构建元数据过滤器
        metadata_filter = None
        if brand or source:
            metadata_filter = {}
            if brand:
                metadata_filter["brand"] = brand
            if source:
                metadata_filter["source"] = source

        # 根据模式选择检索方法
        if search_mode == "vector":
            results = vs_vector_search(query, top_k, metadata_filter)
        elif search_mode == "keyword":
            results = vs_keyword_search(query, top_k, metadata_filter)
        else:
            # hybrid 模式
            results = vs_hybrid_search(query, top_k, metadata_filter)

        # 格式化结果
        formatted_results = []
        for i, doc in enumerate(results, 1):
            formatted_results.append({
                "rank": i,
                "content": doc.get("document", "")[:500] + "..." if len(doc.get("document", "")) > 500 else doc.get("document", ""),
                "score": round(doc.get("score", doc.get("rrf_score", 0)), 4),
                "source": doc.get("metadata", {}).get("source", "未知"),
                "brand": doc.get("metadata", {}).get("brand", None),
                "file_name": doc.get("metadata", {}).get("file_name", None),
                "publish_date": doc.get("metadata", {}).get("publish_date", None)
            })

        return {
            "success": True,
            "query": query,
            "search_mode": search_mode,
            "count": len(formatted_results),
            "results": formatted_results
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "search_mode": search_mode,
            "results": []
        }


def search_by_intent(intent_result: Dict[str, Any], top_k: int = 6) -> Dict[str, Any]:
    """
    根据意图识别结果进行检索

    Args:
        intent_result: intent_classifier 的输出结果
        top_k: 返回数量

    Returns:
        检索结果
    """
    # 提取查询关键词
    keywords = intent_result.get("keywords", [])
    brands = intent_result.get("brands_mentioned", [])

    # 构建检索查询
    query = " ".join(keywords) if keywords else intent_result.get("question", "")

    # 获取品牌过滤
    brand = brands[0] if brands else None

    # 执行混合检索
    return vector_search(
        query=query,
        top_k=top_k,
        brand=brand,
        search_mode="hybrid"
    )


# OpenClaw skill 接口
def skill_main(action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    OpenClaw skill 主入口

    Args:
        action: 操作类型 (search/by_intent)
        params: 参数字典

    Returns:
        标准化结果
    """
    if params is None:
        params = {}

    if action == "search":
        return vector_search(
            query=params.get("query", ""),
            top_k=params.get("top_k", 6),
            brand=params.get("brand"),
            source=params.get("source"),
            search_mode=params.get("search_mode", "hybrid")
        )
    elif action == "by_intent":
        return search_by_intent(
            intent_result=params.get("intent_result", {}),
            top_k=params.get("top_k", 6)
        )
    else:
        return {"success": False, "error": f"未知操作: {action}"}


if __name__ == "__main__":
    # 命令行测试
    import argparse

    parser = argparse.ArgumentParser(description="向量检索")
    parser.add_argument("--query", default="比亚迪市场分析")
    parser.add_argument("--top_k", type=int, default=6)
    parser.add_argument("--mode", default="hybrid", choices=["vector", "keyword", "hybrid"])

    args = parser.parse_args()

    result = vector_search(
        query=args.query,
        top_k=args.top_k,
        search_mode=args.mode
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

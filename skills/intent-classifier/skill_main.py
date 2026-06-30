"""
汽车市场分析意图分类器 - OpenClaw Skill 标准版

标准 OpenClaw Skill 格式：
- @skill 装饰器标记异步函数
- async def 函数定义
- SKILL.md 注册工具
"""

import sys
import os
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

# 添加 RAG 引擎路径
RAG_ENGINE_PATH = r"E:\AI\data\envs\car_agent_env\ai-decision\rag-engine"
if RAG_ENGINE_PATH not in sys.path:
    sys.path.insert(0, RAG_ENGINE_PATH)


def load_env():
    """加载环境变量"""
    env_path = Path(RAG_ENGINE_PATH) / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


load_env()

# 导入现有的分类器
from intent_classifier import IntentClassifier, IntentResult


async def classify(question: str) -> Dict[str, Any]:
    """
    意图分类 Skill

    Args:
        question: 用户问题

    Returns:
        分类结果
    """
    try:
        classifier = IntentClassifier(use_llm=True)
        result = classifier.classify(question)
        return {
            "success": True,
            "result": result.to_dict()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============ OpenClaw Skill 入口 ============
# 使用装饰器导出为 OpenClaw Skill


def skill_main(action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    OpenClaw skill 主入口（同步包装器）

    Args:
        action: 操作类型
        params: 参数字典

    Returns:
        Skill 执行结果
    """
    if params is None:
        params = {}

    if action == "classify":
        question = params.get("question", "")
        # 同步调用异步函数
        return asyncio.run(classify(question))
    else:
        return {
            "success": False,
            "error": f"未知操作: {action}"
        }


# 如果是直接运行，执行测试
if __name__ == "__main__":
    test_questions = [
        "分析比亚迪的市场战略",
        "10-15万紧凑型SUV趋势",
        "特斯拉Model Y竞品分析"
    ]

    print("=" * 60)
    print("意图分类器 Skill 测试")
    print("=" * 60)

    for q in test_questions:
        print(f"\n问题: {q}")
        result = asyncio.run(classify(q))
        print(f"结果: {result}")

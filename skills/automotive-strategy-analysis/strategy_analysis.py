# -*- coding: utf-8 -*-
"""
automotive-strategy-analysis skill
汽车市场战略分析技能 - 封装RAG引擎中的分析模块

提供PEST、波特五力、SWOT分析和4P营销分析
"""

import sys
import os
import json
import re
import subprocess
from typing import Dict, Any, List, Optional


# callback_client.py 路径
CALLBACK_CLIENT_PATH = r"C:\Users\11489\.openclaw\workspace-market\fastapi_18003_adapter\callback_client.py"
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
def emit_callback(callback_url: str, session_id: str, phase: str, status: str, agent: str, summary: str):
    """发送 callback 到编排层"""
    if not callback_url or not session_id:
        return
    try:
        cmd = [
            sys.executable,
            CALLBACK_CLIENT_PATH,
            "--callback-url", callback_url,
            "--session-id", session_id,
            "--phase", phase,
            "--status", status,
            "--agent", agent,
            "--summary", summary
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception:
        pass




def pest_analysis(brand: str = None, segment: str = "乘用车", sql_data: Dict = None, vector_data: Dict = None) -> Dict[str, Any]:
    """
    PEST分析函数

    Args:
        brand: 品牌名称，可选
        segment: 市场细分
        sql_data: SQL查询结果数据
        vector_data: 向量检索结果数据

    Returns:
        PEST分析结果
    """
    try:
        from market_strategy.tools.analysis_frameworks.pest_analysis import PESTAnalyzer

        analyzer = PESTAnalyzer(market=segment or "乘用车")
        result = analyzer.full_analysis()

        # 如果有外部数据，尝试融合到分析中
        if sql_data or vector_data:
            result = _enrich_analysis_with_data(result, sql_data, vector_data)

        return {
            "success": True,
            "intent_type": "pest_analysis",
            "data": result,
            "summary": result.get("summary", {}),
            "data_used": {
                "sql_records": sql_data.get("record_count", 0) if sql_data else 0,
                "vector_results": len(vector_data.get("results", [])) if vector_data else 0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "intent_type": "pest_analysis"
        }


def porter_analysis(brand: str = None, segment: str = "乘用车", sql_data: Dict = None, vector_data: Dict = None) -> Dict[str, Any]:
    """
    波特五力分析

    Args:
        brand: 品牌名称，可选
        segment: 市场细分
        sql_data: SQL查询结果数据
        vector_data: 向量检索结果数据

    Returns:
        波特五力分析结果
    """
    try:
        from market_strategy.tools.analysis_frameworks.porter_analysis import PorterAnalyzer

        analyzer = PorterAnalyzer(segment=segment or "乘用车")

        # 优先使用传入的市场数据，而不是重新加载
        market_data = None
        if sql_data and sql_data.get("success") and sql_data.get("results"):
            # 使用传入的SQL数据
            market_data = _extract_market_data_from_sql(sql_data)
        else:
            # 回退到内部加载
            try:
                from market_strategy.knowledge_base import MarketKnowledgeBase
                kb = MarketKnowledgeBase()
                brands = kb.get_sales_by_brand(top_n=50)
                market_data = {"brand_ranking": brands}
                kb.close()
            except Exception:
                pass

        result = analyzer.full_analysis(market_data)

        # 如果有向量数据也加入分析
        if vector_data and vector_data.get("success") and vector_data.get("results"):
            result = _enrich_porter_with_vectors(result, vector_data)

        return {
            "success": True,
            "intent_type": "porter_analysis",
            "data": result,
            "summary": result.get("summary", {}),
            "data_used": {
                "sql_records": sql_data.get("record_count", 0) if sql_data else 0,
                "vector_results": len(vector_data.get("results", [])) if vector_data else 0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "intent_type": "porter_analysis"
        }


def swot_analysis(brand: str, segment: str = None, sql_data: Dict = None, vector_data: Dict = None) -> Dict[str, Any]:
    """
    SWOT战略分析

    Args:
        brand: 品牌名称（必需）
        segment: 市场细分，可选
        sql_data: SQL查询结果数据
        vector_data: 向量检索结果数据

    Returns:
        SWOT分析结果
    """
    try:
        from market_strategy.tools.analysis_frameworks.swot_analysis import SWOTAnalyzer

        analyzer = SWOTAnalyzer(brand=brand)

        # 优先使用传入的数据
        if sql_data and sql_data.get("success") and sql_data.get("results"):
            analyzer.market_data = _extract_market_data_from_sql(sql_data)
        else:
            try:
                from market_strategy.knowledge_base import MarketKnowledgeBase
                kb = MarketKnowledgeBase()
                brands = kb.get_sales_by_brand(top_n=50)
                analyzer.market_data = {"brand_ranking": brands}
                kb.close()
            except Exception:
                pass

        # 如果有向量数据也加入分析
        if vector_data and vector_data.get("success") and vector_data.get("results"):
            pass  # SWOT analyzer doesn't support direct vector injection

        result = analyzer.generate_full_analysis()

        return {
            "success": True,
            "intent_type": "swot_analysis",
            "data": result,
            "summary": result.get("summary", {}),
            "data_used": {
                "sql_records": sql_data.get("record_count", 0) if sql_data else 0,
                "vector_results": len(vector_data.get("results", [])) if vector_data else 0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "intent_type": "swot_analysis"
        }


def fourp_analysis(brand: str, segment: str = None, sql_data: Dict = None, vector_data: Dict = None) -> Dict[str, Any]:
    """
    4P营销组合分析

    Args:
        brand: 品牌名称（必需）
        segment: 市场细分，可选
        sql_data: SQL查询结果数据
        vector_data: 向量检索结果数据

    Returns:
        4P分析结果
    """
    try:
        from market_strategy.tools.analysis_frameworks.marketing_analysis import MarketingAnalyzer

        analyzer = MarketingAnalyzer(brand=brand, segment=segment)
        result = analyzer.full_analysis()

        # 如果有数据也加入分析
        if sql_data or vector_data:
            result = _enrich_analysis_with_data(result, sql_data, vector_data)

        return {
            "success": True,
            "intent_type": "fourp_analysis",
            "data": result,
            "summary": result.get("summary", {}),
            "data_used": {
                "sql_records": sql_data.get("record_count", 0) if sql_data else 0,
                "vector_results": len(vector_data.get("results", [])) if vector_data else 0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "intent_type": "fourp_analysis"
        }


def _extract_market_data_from_sql(sql_data: Dict) -> Dict:
    """从SQL数据中提取市场数据"""
    results = sql_data.get("results", [])
    if not results:
        return None
    
    # 提取第一条记录作为市场概况
    record = results[0]
    market_data = {
        "total_sales": record.get("total_sales", 0),
        "brand_count": record.get("brand_count", 0),
        "model_count": record.get("model_count", 0),
        "source": "sql_query"
    }
    return market_data


def _enrich_analysis_with_data(result: Dict, sql_data: Dict, vector_data: Dict) -> Dict:
    """将外部数据融入分析结果"""
    # 在summary中添加数据使用信息
    if "summary" not in result:
        result["summary"] = {}
    
    data_info = []
    if sql_data and sql_data.get("success"):
        records = sql_data.get("record_count", 0)
        if records > 0:
            data_info.append(f"SQL数据:{records}条记录")
    
    if vector_data and vector_data.get("success"):
        results = vector_data.get("results", [])
        if results:
            data_info.append(f"向量检索:{len(results)}条结果")
    
    if data_info:
        result["summary"]["data_sources"] = data_info
    
    return result


def _enrich_porter_with_vectors(result: Dict, vector_data: Dict) -> Dict:
    """将向量检索结果融入波特分析"""
    results = vector_data.get("results", [])
    if not results:
        return result
    
    # 在forces中添加竞争情报
    competitive_info = []
    for r in results[:3]:
        content = r.get("content", "")[:200]
        if content:
            competitive_info.append(content)
    
    if competitive_info and "forces" in result:
        # 添加到现有竞争者威胁分析中
        if "competitive_rivalry" in result["forces"]:
            result["forces"]["competitive_rivalry"]["competitive_intel"] = competitive_info
    
    return result


def comprehensive_analysis(
    brand: str = None,
    segment: str = "乘用车",
    question: str = None,
    sql_data: Dict = None,
    vector_data: Dict = None
) -> Dict[str, Any]:
    """
    综合战略分析 - 整合分析

    Args:
        brand: 品牌名称，可选
        segment: 市场细分
        question: 用户问题（可从中提取品牌信息）
        sql_data: SQL查询结果数据
        vector_data: 向量检索结果数据

    Returns:
        综合分析结果
    """
    try:
        # 如果用户没提供brand，则从question中提取
        if not brand and question:
            brand = extract_brand_from_question(question)

        # 执行各项分析
        pest_result = pest_analysis(brand, segment, sql_data, vector_data)
        porter_result = porter_analysis(brand, segment, sql_data, vector_data)

        swot_result = {}
        if brand:
            swot_result = swot_analysis(brand, segment, sql_data, vector_data)

        fourp_result = {}
        if brand:
            fourp_result = fourp_analysis(brand, segment, sql_data, vector_data)

        # 生成综合摘要
        summary = {
            "market_sentiment": pest_result.get("data", {}).get("summary", {}).get("overall_sentiment", "中性"),
            "industry_attractiveness": porter_result.get("data", {}).get("summary", {}).get("industry_attractiveness", "中等吸引力"),
            "strategic_posture": swot_result.get("data", {}).get("summary", {}).get("strategic_posture", "平衡型")
        }

        return {
            "success": True,
            "intent_type": "comprehensive_analysis",
            "brand": brand,
            "segment": segment,
            "pest": pest_result.get("data", {}),
            "porter": porter_result.get("data", {}),
            "swot": swot_result.get("data", {}),
            "fourp": fourp_result.get("data", {}),
            "summary": summary,
            "data_used": {
                "sql_records": sql_data.get("record_count", 0) if sql_data else 0,
                "vector_results": len(vector_data.get("results", [])) if vector_data else 0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "intent_type": "comprehensive_analysis"
        }


def extract_brand_from_question(question: str) -> Optional[str]:
    """从问题中提取品牌名称"""
    # 常见品牌
    brands = [
        "比亚迪", "特斯拉", "蔚来", "小鹏", "理想",
        "吉利", "长城", "长安", "广汽", "上汽",
        "奇瑞", "一汽", "东风", "北汽", "众泰",
        "问界", "小米", "零跑", "哪吒", "威马",
        "埃安", "极氪", "岚图", "极狐", "阿维塔"
    ]

    for brand in brands:
        if brand in question:
            return brand

    return None


def analyze(
    question: str,
    brand: str = None,
    segment: str = "乘用车",
    framework: str = "all",
    sql_data: Dict = None,
    vector_data: Dict = None
) -> Dict[str, Any]:
    """
    统一分析入口

    Args:
        question: 用户问题
        brand: 品牌名称，可选
        segment: 市场细分
        framework: 分析框架 (all/pest/porter/swot/fourp)
        sql_data: SQL数据
        vector_data: 向量数据

    Returns:
        分析结果
    """
    # 提取品牌
    if not brand:
        brand = extract_brand_from_question(question)

    if framework == "pest":
        return pest_analysis(brand, segment, sql_data, vector_data)
    elif framework == "porter":
        return porter_analysis(brand, segment, sql_data, vector_data)
    elif framework == "swot":
        if not brand:
            return {"success": False, "error": "SWOT分析需要指定品牌", "intent_type": "swot_analysis"}
        return swot_analysis(brand, segment, sql_data, vector_data)
    elif framework == "fourp":
        if not brand:
            return {"success": False, "error": "4P分析需要指定品牌", "intent_type": "fourp_analysis"}
        return fourp_analysis(brand, segment, sql_data, vector_data)
    else:
        return comprehensive_analysis(brand, segment, question, sql_data, vector_data)


# OpenClaw skill 接口
def skill_main(action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """OpenClaw skill 主入口 - 包含细粒度 callback 发射"""
    if params is None:
        params = {}

    question = params.get("question", params.get("query", ""))
    brand = params.get("brand")
    segment = params.get("segment", "乘用车")
    framework = params.get("framework", "all")
    sql_data = params.get("sql_data")
    vector_data = params.get("vector_data")
    callback_url = params.get("callback_url")
    session_id = params.get("session_id")

    # 从 params 提取 callback 参数
    if not callback_url:
        callback_url = params.get("callback", {}).get("callback_url") if isinstance(params.get("callback"), dict) else None
    if not session_id:
        session_id = params.get("callback", {}).get("session_id") if isinstance(params.get("callback"), dict) else None

    if action == "analyze":
        # 细粒度 callback：分步执行，每步完成后 emit
        if framework == "all":
            # PEST
            emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始PEST框架分析")
            pest_result = pest_analysis(brand, segment, sql_data, vector_data)
            emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "PEST分析完成，政策+技术两维度洞察已提炼")

            # 波特五力
            emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始波特五力框架分析")
            porter_result = porter_analysis(brand, segment, sql_data, vector_data)
            emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "波特五力分析完成，替代品/供应商议价能力已评估")

            # SWOT
            if brand:
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始SWOT框架分析")
                swot_result = swot_analysis(brand, segment, sql_data, vector_data)
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "SWOT分析完成，SO策略已识别")

            # 4P
            if brand:
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始4P营销框架分析")
                fourp_result = fourp_analysis(brand, segment, sql_data, vector_data)
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "4P分析完成，营销策略已提炼")

            # 综合结果
            result = comprehensive_analysis(brand, segment, question, sql_data, vector_data)
            return result
        else:
            # 单框架：直接执行
            if framework == "pest":
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始PEST框架分析")
                result = pest_analysis(brand, segment, sql_data, vector_data)
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "PEST分析完成")
                return result
            elif framework == "porter":
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始波特五力框架分析")
                result = porter_analysis(brand, segment, sql_data, vector_data)
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "波特五力分析完成")
                return result
            elif framework == "swot":
                if not brand:
                    return {"success": False, "error": "需要品牌参数"}
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始SWOT框架分析")
                result = swot_analysis(brand, segment, sql_data, vector_data)
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "SWOT分析完成")
                return result
            elif framework == "fourp":
                if not brand:
                    return {"success": False, "error": "需要品牌参数"}
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始4P框架分析")
                result = fourp_analysis(brand, segment, sql_data, vector_data)
                emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "4P分析完成")
                return result
            else:
                return {"success": False, "error": f"未知操作: {action}"}
    elif action == "pest":
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始PEST框架分析")
        result = pest_analysis(brand, segment, sql_data, vector_data)
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "PEST分析完成")
        return result
    elif action == "porter":
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始波特五力框架分析")
        result = porter_analysis(brand, segment, sql_data, vector_data)
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "波特五力分析完成")
        return result
    elif action == "swot":
        if not brand:
            return {"success": False, "error": "需要品牌参数"}
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始SWOT框架分析")
        result = swot_analysis(brand, segment, sql_data, vector_data)
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "SWOT分析完成")
        return result
    elif action == "fourp":
        if not brand:
            return {"success": False, "error": "需要品牌参数"}
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始4P框架分析")
        result = fourp_analysis(brand, segment, sql_data, vector_data)
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "4P分析完成")
        return result
    elif action == "comprehensive":
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "开始综合战略分析")
        result = comprehensive_analysis(brand, segment, question, sql_data, vector_data)
        emit_callback(callback_url, session_id, "AnalysisRunning", "running", "analysis-agent", "综合战略分析完成")
        return result
    else:
        return {"success": False, "error": f"未知操作: {action}"}


if __name__ == "__main__":
    # 测试代码
    import argparse

    parser = argparse.ArgumentParser(description="汽车市场战略分析")
    parser.add_argument("--action", default="comprehensive", choices=["pest", "porter", "swot", "fourp", "comprehensive"])
    parser.add_argument("--brand", default=None)
    parser.add_argument("--segment", default="乘用车")
    parser.add_argument("--question", default="分析比亚迪的市场竞争")

    args = parser.parse_args()

    result = skill_main(args.action, {
        "question": args.question,
        "brand": args.brand,
        "segment": args.segment
    })

    print(json.dumps(result, ensure_ascii=False, indent=2))
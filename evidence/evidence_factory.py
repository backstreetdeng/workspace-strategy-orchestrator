# evidence_factory.py
# P1: 工具结果 evidence 标准化
# 统一动态置信度计算 + 准确 data_caliber + 完整 limitations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from .evidence_ledger import Evidence


@dataclass
class EvidenceQuality:
    """evidence 质量评估结果"""
    confidence: float          # 综合置信度 0-1
    coverage_score: float      # 对问题的覆盖度 0-1
    source_credibility: float  # 来源可信度 0-1
    data_caliber: str         # 数据口径描述
    limitations: List[str]    # 局限性说明
    coverage_dimensions: List[str]  # 覆盖的分析维度


def calc_sql_evidence_quality(
    param: str,
    data: Any,
    time_range: str,
    user_intent: Any = None
) -> EvidenceQuality:
    """
    动态计算 nl2sql 工具的 evidence 质量评分。
    
    置信度由以下因素综合决定：
    - 查询特异性：越具体的查询（品牌/车型）置信度越高
    - 结果完整性：返回行数越多且非空，置信度越高
    - 时间对齐：数据时间范围与用户需求匹配度
    - 数据特异性：销量/份额类数值数据置信度 > 计数类
    """
    param_lower = param.lower()
    limitations = []
    coverage_dimensions = ["销量", "份额", "增速"]
    
    # 1. 查询特异性评分
    if any(kw in param_lower for kw in ["brand", "品牌", "比亚迪", "特斯拉", "吉利", "奇瑞"]):
        specificity_score = 0.85
        query_type_label = "品牌维度"
    elif any(kw in param_lower for kw in ["model", "车型", "细分市场", "segment"]):
        specificity_score = 0.80
        query_type_label = "车型维度"
    elif any(kw in param_lower for kw in ["trend", "趋势", "走势", "近"]):
        specificity_score = 0.75
        query_type_label = "趋势维度"
    elif any(kw in param_lower for kw in ["overview", "大盘", "整体", "总量"]):
        specificity_score = 0.70
        query_type_label = "市场概览"
    else:
        specificity_score = 0.65
        query_type_label = "通用查询"

    # 2. 结果完整性评分
    record_count = 0
    if isinstance(data, dict):
        record_count = data.get("record_count", data.get("count", 0))
        has_data = bool(data.get("results") or data.get("data"))
    elif isinstance(data, list):
        record_count = len(data)
        has_data = record_count > 0
    else:
        has_data = data is not None
    
    if not has_data or record_count == 0:
        completeness_score = 0.0
        limitations.append("数据库无返回结果")
    elif record_count <= 3:
        completeness_score = 0.50
        limitations.append(f"返回数据量较少（{record_count}条），样本有限")
    elif record_count <= 20:
        completeness_score = 0.70
    else:
        completeness_score = 0.85

    # 3. 时间范围评分
    if time_range and time_range != "unknown":
        if "近" in time_range or "最近" in time_range:
            recency_score = 0.80
        elif any(yr in time_range for yr in ["2024", "2025", "2026"]):
            recency_score = 0.90
        else:
            recency_score = 0.65
    else:
        recency_score = 0.50
        limitations.append("数据时间范围不明确")

    # 4. 数据特异性（数值统计 > 计数）
    data_type_score = 0.80  # 销量数据库默认为数值统计

    # 综合置信度 = 特异性×完整性×时效性×数据类型的加权几何平均
    raw_conf = (
        specificity_score * 0.30 +
        completeness_score * 0.30 +
        recency_score * 0.25 +
        data_type_score * 0.15
    )
    confidence = round(min(0.92, max(0.10, raw_conf)), 3)

    # 覆盖度：主要反映查询类型对用户问题的覆盖
    coverage_map = {
        "品牌维度": 0.80,
        "车型维度": 0.75,
        "趋势维度": 0.70,
        "市场概览": 0.65,
        "通用查询": 0.55,
    }
    base_coverage = coverage_map.get(query_type_label, 0.60)
    coverage_score = round(min(0.90, base_coverage + completeness_score * 0.10), 3)

    # 来源可信度（数据库来源固定高可信度）
    source_credibility = 0.85

    # data_caliber：给出具体口径描述
    caliber_map = {
        "品牌维度": f"品牌维度销量/份额；统计口径: {time_range}；数据来自 PostgreSQL vectordb.sales_import 表",
        "车型维度": f"车型维度销量/份额；统计口径: {time_range}；数据来自 PostgreSQL vectordb.sales_import 表",
        "趋势维度": f"月度/周度趋势数据；统计口径: {time_range}；数据来自 PostgreSQL vectordb.sales_import 表",
        "市场概览": f"市场整体销量/增速；统计口径: {time_range}；数据来自 PostgreSQL vectordb.sales_import 表",
        "通用查询": f"结构化数据查询；统计口径: {time_range}；数据来自 PostgreSQL vectordb.sales_import 表",
    }
    data_caliber = caliber_map.get(query_type_label, f"结构化销量/份额数据库口径；统计口径: {time_range}")

    if record_count > 0:
        data_caliber += f"；有效记录数: {record_count} 条"

    # 若时间范围模糊则追加说明
    if not time_range or time_range == "unknown":
        limitations.append("时间范围未指定，数据时效性无法评估")

    return EvidenceQuality(
        confidence=confidence,
        coverage_score=coverage_score,
        source_credibility=source_credibility,
        data_caliber=data_caliber,
        limitations=limitations,
        coverage_dimensions=coverage_dimensions
    )


def calc_rag_evidence_quality(
    results: List[Any],
    query: str,
    time_range: str,
    user_intent: Any = None
) -> EvidenceQuality:
    """
    动态计算 RAG 检索的 evidence 质量评分。
    
    置信度由以下因素综合决定：
    - 检索相关度：返回文档数越多越可能覆盖
    - 来源多样性：多个来源 > 单来源
    - 时间覆盖：文档时间与问题时间范围匹配度
    - 查询特异性：具体问题 > 宽泛问题
    """
    if not results:
        return EvidenceQuality(
            confidence=0.05,
            coverage_score=0.05,
            source_credibility=0.50,
            data_caliber="向量检索无结果，非结构化数据支撑缺失",
            limitations=["RAG 检索返回 0 条结果，无法提供文档证据支持"],
            coverage_dimensions=["行业报告", "政策背景"]
        )

    limitations = []
    coverage_dimensions = ["行业报告", "政策背景", "趋势解释"]

    # 1. 检索覆盖度（基于返回数量）
    n = len(results)
    if n >= 5:
        retrieval_coverage = 0.80
    elif n >= 3:
        retrieval_coverage = 0.65
    elif n >= 1:
        retrieval_coverage = 0.45
    else:
        retrieval_coverage = 0.20

    # 2. 来源多样性
    sources = set()
    dates = []
    for r in results:
        if isinstance(r, dict):
            meta = r.get("metadata", {})
            if isinstance(meta, dict):
                src = meta.get("source", "unknown")
                dt = meta.get("publish_date", "")
            else:
                src = str(meta) if meta else "unknown"
                dt = ""
            sources.add(src)
            if dt:
                dates.append(dt)
        elif isinstance(r, str):
            sources.add("text_chunk")
    
    diversity_score = min(0.90, 0.50 + len(sources) * 0.15) if sources else 0.40

    # 3. 时间覆盖
    if dates:
        recency_score = 0.75
        time_coverage_desc = f"文档时间: {', '.join(dates[:3])}"
    else:
        recency_score = 0.45
        time_coverage_desc = "文档时间未知"
        limitations.append("RAG 文档缺少发布日期元数据")

    # 4. 查询特异性
    if any(kw in query for kw in ["政策", "补贴", "购置税", "限牌"]):
        query_specificity = 0.85
        coverage_dimensions.append("政策解读")
    elif any(kw in query for kw in ["竞争", "竞品", "对手", "市场份额"]):
        query_specificity = 0.80
        coverage_dimensions.append("竞品分析")
    elif any(kw in query for kw in ["趋势", "预测", "未来", "2025", "2026"]):
        query_specificity = 0.75
        coverage_dimensions.append("趋势预判")
    else:
        query_specificity = 0.65

    raw_conf = (
        retrieval_coverage * 0.35 +
        diversity_score * 0.25 +
        recency_score * 0.20 +
        query_specificity * 0.20
    )
    confidence = round(min(0.88, max(0.20, raw_conf)), 3)
    coverage_score = round(min(0.85, retrieval_coverage * 0.9 + diversity_score * 0.1), 3)
    source_credibility = round(min(0.80, 0.55 + len(sources) * 0.08), 3)

    data_caliber = (
        f"向量检索文档摘要口径；检索词: {query[:40]}；"
        f"{time_coverage_desc}；来源数量: {len(sources)} 个"
    )

    if len(sources) == 1:
        limitations.append(f"文档来源单一（仅 {list(sources)[0]}），来源多样性不足")

    return EvidenceQuality(
        confidence=confidence,
        coverage_score=coverage_score,
        source_credibility=source_credibility,
        data_caliber=data_caliber,
        limitations=limitations,
        coverage_dimensions=list(set(coverage_dimensions))
    )


def build_sql_evidence(
    param: str,
    data: Any,
    time_range: str,
    user_intent: Any = None
) -> Evidence:
    """为 nl2sql 工具构建标准化的 Evidence 对象。"""
    q = calc_sql_evidence_quality(param, data, time_range, user_intent)
    
    # 推断查询类型用于 claim
    param_lower = param.lower()
    if "brand" in param_lower or "品牌" in param_lower:
        claim = f"品牌维度结构化查询: {param}"
    elif "trend" in param_lower or "趋势" in param_lower:
        claim = f"市场趋势数据查询: {param}"
    elif "overview" in param_lower or "市场" in param_lower:
        claim = f"市场概览数据查询: {param}"
    else:
        claim = f"结构化数据查询: {param}"

    return Evidence(
        source="nl2sql-pg",
        tool="knowledge_base",
        claim=claim,
        content=str(data)[:500] if data else "无返回数据",
        time_range=time_range,
        metrics=["销量", "份额", "增速"],
        data_caliber=q.data_caliber,
        source_credibility=q.source_credibility,
        coverage_dimensions=q.coverage_dimensions,
        coverage_score=q.coverage_score,
        confidence=q.confidence,
        limitations=q.limitations
    )


def build_rag_evidence(
    results: List[Any],
    query: str,
    time_range: str,
    user_intent: Any = None
) -> Evidence:
    """为 RAG 检索构建标准化的 Evidence 对象。"""
    q = calc_rag_evidence_quality(results, query, time_range, user_intent)
    
    contents = []
    first_meta = {}
    if results:
        for r in results:
            if isinstance(r, dict):
                if not first_meta:
                    first_meta = r.get("metadata", {}) if isinstance(r.get("metadata", {}), dict) else {}
                doc = r.get("document", str(r))
            else:
                doc = str(r)
            contents.append(doc[:200])
    source_url = str(first_meta.get("source_url") or first_meta.get("url") or first_meta.get("file_name") or "")
    source_date = str(first_meta.get("publish_date") or first_meta.get("source_date") or "")
    source = str(first_meta.get("source") or "")
    source_grade = _grade_rag_source(source)
    
    return Evidence(
        source="rag",
        tool="vector_retriever",
        claim=f"RAG 检索: {query[:60]}",
        content=(
            f"source_url={source_url}; source_date={source_date}; source_grade={source_grade}; "
            + ("; ".join(contents) if contents else "无相关文档")
        ),
        time_range=f"用户问题时间范围: {time_range}；文档发布日期以元数据为准",
        data_caliber=q.data_caliber,
        source_url=source_url,
        source_date=source_date,
        source_grade=source_grade,
        source_credibility=q.source_credibility,
        coverage_dimensions=q.coverage_dimensions,
        coverage_score=q.coverage_score,
        confidence=q.confidence,
        limitations=q.limitations
    )


def _grade_rag_source(source: str) -> str:
    high = ["乘联会", "中汽协", "国家统计局", "工信部", "发改委", "财政部", "数据中心"]
    medium = ["汽车之家", "易车", "懂车帝", "盖世汽车", "第一财经"]
    if any(item in source for item in high):
        return "high"
    if any(item in source for item in medium):
        return "medium"
    return "low" if source else "unknown"

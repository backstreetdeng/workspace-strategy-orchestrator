# -*- coding: utf-8 -*-
"""Analysis plan for strategy-orchestrator.

P1 goal: one task-level plan must drive SQL, RAG, Tavily, frameworks, and
reporting. This prevents each tool from inventing its own brand, time range,
or market scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


BRAND_ALIASES: Dict[str, List[str]] = {
    "小米": ["小米", "小米汽车", "SU7", "YU7"],
    "比亚迪": ["比亚迪", "BYD", "方程豹", "腾势", "仰望"],
    "特斯拉": ["特斯拉", "Tesla", "Model 3", "Model Y"],
    "理想": ["理想", "理想汽车", "L6", "L7", "L8", "L9", "MEGA"],
    "问界": ["问界", "鸿蒙智行", "AITO", "M5", "M7", "M9"],
    "蔚来": ["蔚来", "NIO", "乐道"],
    "小鹏": ["小鹏", "XPeng"],
    "吉利": ["吉利", "银河", "极氪", "领克"],
    "长安": ["长安", "深蓝", "阿维塔"],
    "零跑": ["零跑"],
    "极氪": ["极氪"],
}


@dataclass
class AnalysisPlan:
    raw_query: str
    target_brand: Optional[str]
    brand_aliases: List[str]
    time_range: str
    month_count: int
    market_scope: str
    geography: str = "中国"
    price_band: Optional[str] = None
    power_type: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    required_data_fields: List[str] = field(default_factory=list)
    answer_strategy: Dict[str, Any] = field(default_factory=dict)
    rag_query: str = ""
    tavily_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_analysis_plan(task: Any) -> AnalysisPlan:
    intent = getattr(task, "user_intent", None)
    raw_query = getattr(intent, "raw_query", "") or ""
    requested_time = getattr(intent, "time_range", "") or ""
    entities = list(getattr(intent, "entities", []) or [])

    brand = _infer_brand(raw_query, entities)
    time_range = _normalize_time_range(raw_query, requested_time)
    month_count = _month_count_from_range(time_range)
    market_scope = _infer_market_scope(raw_query)
    price_band = _infer_price_band(raw_query)
    power_type = _infer_power_type(raw_query)
    aliases = _brand_aliases(brand)

    answer_strategy = _build_answer_strategy(raw_query, brand, market_scope, time_range)
    required_fields = _required_fields_for_strategy(answer_strategy)
    assumptions = [
        "若用户未显式指定地域，默认以中国乘用车市场为核心范围。",
        "品牌、时间、市场范围必须贯穿 SQL/RAG/Tavily/分析框架。",
        "证据不足时只能输出低置信度判断或待补证假设。",
    ]

    return AnalysisPlan(
        raw_query=raw_query,
        target_brand=brand,
        brand_aliases=aliases,
        time_range=time_range,
        month_count=month_count,
        market_scope=market_scope,
        price_band=price_band,
        power_type=power_type,
        assumptions=assumptions,
        required_data_fields=required_fields,
        answer_strategy=answer_strategy,
        rag_query=_build_rag_query(raw_query, brand, time_range, market_scope),
        tavily_query=_build_tavily_query(raw_query, brand, time_range, market_scope),
    )


def _infer_brand(query: str, entities: List[str]) -> Optional[str]:
    probes = [query] + entities
    for brand, aliases in BRAND_ALIASES.items():
        for probe in probes:
            if any(alias and alias in str(probe) for alias in aliases):
                return brand
    for entity in entities:
        if entity and not _is_market_scope_entity(entity):
            return entity
    return None


def _is_market_scope_entity(entity: str) -> bool:
    text = str(entity or "")
    if not text:
        return True
    if re.search(r"\d{1,3}\s*[-~到至]\s*\d{1,3}\s*万", text):
        return True
    market_tokens = [
        "乘用车",
        "新能源",
        "SUV",
        "suv",
        "市场",
        "价格带",
        "纯电",
        "插混",
        "增程",
        "中国",
        "海外",
        "出口",
    ]
    return any(token in text for token in market_tokens)


def _brand_aliases(brand: Optional[str]) -> List[str]:
    if not brand:
        return []
    return BRAND_ALIASES.get(brand, [brand])


def _normalize_time_range(query: str, requested: str) -> str:
    text = f"{query} {requested}"
    explicit_year = _explicit_year(query)
    if explicit_year:
        return f"{explicit_year}年"
    if any(token in text for token in ["近半年", "最近半年", "6个月", "六个月"]):
        return "最近6个月"
    if any(token in text for token in ["近三个月", "最近3个月", "3个月", "三个月"]):
        return "最近3个月"
    if any(token in text for token in ["最近12个月", "近12个月", "12个月", "一年"]):
        return "最近12个月"
    if requested:
        return requested
    return "最近6个月"


def _month_count_from_range(time_range: str) -> int:
    text = time_range or ""
    if _explicit_year(text):
        return 12
    if any(token in text for token in ["近半年", "最近半年", "6个月", "六个月"]):
        return 6
    if any(token in text for token in ["近三个月", "最近3个月", "3个月", "三个月"]):
        return 3
    if any(token in text for token in ["最近12个月", "近12个月", "12个月", "一年"]):
        return 12
    return 6


def _explicit_year(text: str) -> Optional[int]:
    match = re.search(r"(20\d{2})\s*年", text or "")
    if not match:
        return None
    return int(match.group(1))


def _infer_market_scope(query: str) -> str:
    if "SUV" in query or "suv" in query:
        return "新能源SUV" if "新能源" in query else "SUV"
    if "新能源" in query:
        return "新能源乘用车"
    if "出口" in query or "海外" in query:
        return "乘用车出口市场"
    return "乘用车"


def _infer_price_band(query: str) -> Optional[str]:
    match = re.search(r"(\d{1,3})\s*[-~到至]\s*(\d{1,3})\s*万", query)
    if match:
        return f"{match.group(1)}-{match.group(2)}万"
    for token in ["10万以下", "10-15万", "15-20万", "20-30万", "30-50万", "50万以上"]:
        if token in query:
            return token
    return None


def _infer_power_type(query: str) -> Optional[str]:
    if any(token in query for token in ["纯电", "BEV", "EV"]):
        return "纯电动"
    if any(token in query for token in ["插混", "PHEV"]):
        return "插电式混合动力"
    if "增程" in query:
        return "增程式"
    if "新能源" in query:
        return "新能源"
    return None


def _build_answer_strategy(
    query: str,
    brand: Optional[str],
    market_scope: str,
    time_range: str,
) -> Dict[str, Any]:
    """Build the question-answering contract for downstream report generation.

    This is the place where an LLM should eventually return the answer strategy:
    what the user is asking to decide, which sections are mandatory, and which
    report patterns are invalid. The local logic below is only a bounded
    semantic fallback so the orchestrator does not regress to one-keyword,
    one-template routing when the external LLM is unavailable.
    """
    text = query or ""
    asks_competition_structure = any(
        token in text
        for token in [
            "竞争格局",
            "市场格局",
            "竞争态势",
            "份额格局",
            "品牌格局",
            "竞争版图",
        ]
    )
    asks_target_strategy = bool(brand) or any(
        token in text
        for token in ["进入", "机会", "策略", "对标", "竞品", "品牌分析", "车型分析"]
    )

    if asks_competition_structure and not brand:
        return {
            "source": "semantic_fallback",
            "llm_expected": True,
            "question_goal": f"解释{time_range}{market_scope}的竞争结构、头部集中度、梯队和变化风险",
            "subject_kind": "market",
            "is_target_specific": False,
            "must_answer": [
                "数据窗口和口径",
                "市场规模与趋势",
                "Top品牌/企业份额",
                "CR3/CR5/CR10集中度",
                "头部/腰部/长尾竞争梯队",
                "格局变化、风险和证据缺口",
            ],
            "must_not_use": [
                "目标对象占位",
                "SOM/目标销量模板",
                "单一品牌商业模式模板",
            ],
        }

    return {
        "source": "semantic_fallback",
        "llm_expected": True,
        "question_goal": f"围绕{brand or market_scope}回答市场机会、竞争压力和战略动作",
        "subject_kind": "target" if asks_target_strategy else "market",
        "is_target_specific": bool(brand),
        "must_answer": [
            "问题范围",
            "TAM/SAM",
            "目标表现/SOM" if brand else "竞争格局",
            "竞品矩阵",
            "机会与风险",
            "下一步行动",
        ],
        "must_not_use": [],
    }


def _required_fields_for_strategy(strategy: Dict[str, Any]) -> List[str]:
    if not strategy.get("is_target_specific") and strategy.get("subject_kind") == "market":
        return [
            "总体市场规模",
            "月度趋势与环比",
            "同比变化",
            "Top品牌/企业份额",
            "CR3/CR5/CR10集中度",
            "竞争梯队",
            "RAG业务文档证据",
            "Tavily外部实时证据",
        ]

    return [
        "总体市场规模/TAM",
        "目标细分市场/SAM",
        "目标品牌或车型/SOM",
        "月度趋势与环比",
        "同比变化",
        "车型贡献",
        "价格带",
        "动力类型",
        "竞品份额",
        "RAG业务文档证据",
        "Tavily外部实时证据",
    ]


def _build_rag_query(query: str, brand: Optional[str], time_range: str, market_scope: str) -> str:
    topic = "销量 份额 竞品 价格 智能化 渠道 风险 政策"
    return " ".join(part for part in [brand, query, time_range, market_scope, topic] if part)


def _build_tavily_query(query: str, brand: Optional[str], time_range: str, market_scope: str) -> str:
    topic = "销量 交付 市场份额 竞品 战略 政策"
    return " ".join(part for part in [brand, query, time_range, market_scope, topic] if part)

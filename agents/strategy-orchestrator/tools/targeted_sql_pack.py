# -*- coding: utf-8 -*-
"""Targeted structured SQL pack owned by strategy-orchestrator.

This module is intentionally inside the orchestrator tree. It provides the
stable business metrics that a market strategy report needs, while NL2SQL can
still answer ad hoc semantic questions.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from ..evidence.evidence_ledger import Evidence
except ImportError:
    from evidence.evidence_ledger import Evidence


RAG_ENGINE_ROOT = Path(r"E:\AI\data\envs\car_agent_env\ai-decision\rag-engine")
if str(RAG_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ENGINE_ROOT))

EXPECTED_PYTHON = Path(r"E:\AI\data\envs\car_agent_env\Scripts\python.exe")
CALLBACK_CLIENT_PATH = Path(r"C:\Users\11489\.openclaw\workspace-market\fastapi_18003_adapter\callback_client.py")
CALLBACK_URL = "http://127.0.0.1:18003/callback"

def _emit_callback(session_id: str, phase: str, status: str, summary: str, agent: str = "data-agent") -> None:
    if not session_id:
        return
    import subprocess
    cmd = [
        str(EXPECTED_PYTHON),
        str(CALLBACK_CLIENT_PATH),
        "--session-id", session_id,
        "--callback-url", CALLBACK_URL,
        "--phase", phase,
        "--status", status,
        "--agent", agent,
        "--summary", summary,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception:
        pass


REQUIRED_TARGETED_SQL_BLOCKS = [
    "market_overview",
    "monthly_trend",
    "yoy_change",
    "competitor_share",
    "target_brand_performance",
    "model_contribution",
    "power_mix",
    "price_and_config",
]


BLOCK_PURPOSES = {
    "market_overview": "TAM/SAM market base and data period",
    "monthly_trend": "monthly trend and MoM volatility",
    "yoy_change": "year-on-year comparison for the same month window",
    "competitor_share": "competitor share and concentration",
    "target_brand_performance": "target brand SOM and sales base",
    "model_contribution": "target brand model contribution",
    "power_mix": "target brand powertrain mix",
    "price_and_config": "target brand price band and configuration proof",
}


BLOCK_METRICS = {
    "market_overview": ["销量", "份额", "时间范围", "口径"],
    "monthly_trend": ["销量", "趋势", "环比", "时间范围"],
    "yoy_change": ["销量", "同比", "增速", "时间范围"],
    "competitor_share": ["销量", "份额", "竞品", "车型"],
    "target_brand_performance": ["销量", "份额", "车型", "时间范围"],
    "model_contribution": ["销量", "车型", "动力", "细分市场"],
    "power_mix": ["销量", "动力", "车型"],
    "price_and_config": ["价格", "价格带", "动力", "车型"],
}


def run_targeted_sql_pack(
    analysis_plan: Any,
    connection_factory: Optional[Callable[[], Any]] = None,
    session_id: Optional[str] = None,
    callback_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the fixed SQL pack for the shared analysis plan."""
    plan = _plan_to_dict(analysis_plan)
    conn = None
    cur = None
    try:
        conn = connection_factory() if connection_factory else _db_connect()
        cur = conn.cursor()

        cur.execute('SELECT MAX("销售日期") AS max_month FROM sales_import')
        max_row = cur.fetchone() or {}
        max_month = int(max_row["max_month"])
        min_month, max_month, prev_min_month, prev_max_month = _period_from_time_range(
            max_month=max_month,
            time_range=str(plan.get("time_range") or ""),
        )
        month_count = _month_count_from_range(str(plan.get("time_range") or ""))

        common_cond, common_params = _market_condition(plan)
        brand_cond, brand_params = _brand_condition(plan.get("brand_aliases") or [])
        period_cond = '"销售日期" BETWEEN %s AND %s'
        period_params = [min_month, max_month]
        prev_period_params = [prev_min_month, prev_max_month]

        blocks: List[Dict[str, Any]] = []

        def add_block(name: str, sql: str, params: List[Any]) -> None:
            cur.execute(sql, params)
            rows = [_jsonable(dict(row)) for row in cur.fetchall()]
            blocks.append(
                {
                    "name": name,
                    "purpose": BLOCK_PURPOSES[name],
                    "rows": rows,
                    "row_count": len(rows),
                }
            )

        where_market = f"{period_cond} AND {common_cond}"
        params_market = period_params + common_params

        add_block(
            "market_overview",
            f"""
            SELECT SUM("销量") AS total_sales,
                   COUNT(DISTINCT "企业名称") AS brand_count,
                   COUNT(DISTINCT "通用名称") AS model_count,
                   MIN("销售日期") AS period_start,
                   MAX("销售日期") AS period_end
            FROM sales_import
            WHERE {where_market}
            """,
            params_market,
        )
        add_block(
            "monthly_trend",
            f"""
            SELECT "销售日期" AS month,
                   SUM("销量") AS sales
            FROM sales_import
            WHERE {where_market}
            GROUP BY "销售日期"
            ORDER BY "销售日期"
            """,
            params_market,
        )
        add_block(
            "yoy_change",
            f"""
            SELECT period,
                   SUM(sales) AS sales
            FROM (
                SELECT 'current' AS period, "销量" AS sales
                FROM sales_import
                WHERE {where_market}
                UNION ALL
                SELECT 'previous_year' AS period, "销量" AS sales
                FROM sales_import
                WHERE {period_cond} AND {common_cond}
            ) t
            GROUP BY period
            ORDER BY period
            """,
            params_market + prev_period_params + common_params,
        )
        add_block(
            "competitor_share",
            f"""
            SELECT "企业名称" AS brand,
                   SUM("销量") AS sales,
                   COUNT(DISTINCT "通用名称") AS model_count,
                   ROUND(SUM("销量") * 100.0 / NULLIF(SUM(SUM("销量")) OVER (), 0), 2) AS share_pct
            FROM sales_import
            WHERE {where_market}
            GROUP BY "企业名称"
            ORDER BY sales DESC
            LIMIT 12
            """,
            params_market,
        )

        if plan.get("target_brand"):
            where_brand = f"{period_cond} AND {common_cond} AND {brand_cond}"
            params_brand = period_params + common_params + brand_params
            add_block(
                "target_brand_performance",
                f"""
                SELECT "企业名称" AS brand,
                       SUM("销量") AS sales,
                       COUNT(DISTINCT "通用名称") AS model_count,
                       MIN("销售日期") AS period_start,
                       MAX("销售日期") AS period_end
                FROM sales_import
                WHERE {where_brand}
                GROUP BY "企业名称"
                ORDER BY sales DESC
                LIMIT 10
                """,
                params_brand,
            )
            add_block(
                "model_contribution",
                f"""
                SELECT "通用名称" AS model,
                       "企业名称" AS brand,
                       "技术类型" AS power_type,
                       "车型级别" AS vehicle_level,
                       "乘用车细分" AS segment,
                       SUM("销量") AS sales
                FROM sales_import
                WHERE {where_brand}
                GROUP BY "通用名称", "企业名称", "技术类型", "车型级别", "乘用车细分"
                ORDER BY sales DESC
                LIMIT 12
                """,
                params_brand,
            )
            add_block(
                "power_mix",
                f"""
                SELECT "技术类型" AS power_type,
                       SUM("销量") AS sales,
                       COUNT(DISTINCT "通用名称") AS model_count
                FROM sales_import
                WHERE {where_brand}
                GROUP BY "技术类型"
                ORDER BY sales DESC
                """,
                params_brand,
            )
            config_where, config_params = _config_condition(plan)
            add_block(
                "price_and_config",
                f"""
                SELECT "车型名称" AS model,
                       "厂商" AS maker,
                       "能源类型" AS energy_type,
                       "级别" AS level,
                       "厂商指导价" AS guide_price,
                       "价格带" AS price_band,
                       "CLTC纯电续航里程" AS cltc_range,
                       "电动机总功率" AS motor_power
                FROM config_data
                WHERE {config_where}
                LIMIT 12
                """,
                config_params,
            )

        for block in blocks:
            if block["name"] == "monthly_trend":
                _add_mom(block["rows"])
            if block["name"] == "yoy_change":
                _add_yoy(block["rows"])

        return {
            "success": True,
            "query_mode": "targeted_sql_pack",
            "period_start": min_month,
            "period_end": max_month,
            "previous_period_start": prev_min_month,
            "previous_period_end": prev_max_month,
            "blocks": blocks,
            "results": _flatten_blocks(blocks),
        }
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def build_targeted_sql_evidences(result: Dict[str, Any], analysis_plan: Any) -> List[Evidence]:
    """Convert targeted SQL blocks into standard ledger evidence."""
    plan = _plan_to_dict(analysis_plan)
    if not result.get("success"):
        return [
            Evidence(
                source="nl2sql-pg",
                tool="targeted_sql_pack",
                claim="targeted_sql_pack failed",
                content=str(result.get("error") or "unknown error"),
                time_range=str(plan.get("time_range") or "unknown"),
                metrics=["销量", "份额", "趋势", "车型", "价格", "动力", "同比"],
                data_caliber="PostgreSQL targeted_sql_pack failed before returning structured rows",
                source_grade="high",
                source_credibility=0.20,
                coverage_dimensions=["结构化查询包"],
                coverage_score=0.05,
                confidence=0.15,
                limitations=[str(result.get("error") or "targeted_sql_pack failed")],
            )
        ]

    evidences: List[Evidence] = []
    blocks = result.get("blocks") or []
    period = f"{result.get('period_start')} - {result.get('period_end')}"
    for block in blocks:
        name = block.get("name") or "unknown_block"
        rows = block.get("rows") or []
        metrics = BLOCK_METRICS.get(name, ["销量", "份额"])
        sample = json.dumps(rows[:5], ensure_ascii=False, default=str)
        row_count = int(block.get("row_count") or len(rows))
        coverage = _block_coverage_score(name, row_count)
        confidence = round(min(0.92, 0.55 + coverage * 0.35), 3)
        evidences.append(
            Evidence(
                source="nl2sql-pg",
                tool="targeted_sql_pack",
                claim=f"targeted_sql_pack/{name}: {block.get('purpose') or name}",
                content=f"block={name}; row_count={row_count}; sample={sample}",
                time_range=str(plan.get("time_range") or period),
                metrics=metrics,
                data_caliber=(
                    "PostgreSQL vectordb.sales_import/config_data targeted_sql_pack; "
                    f"period={period}; query_mode=targeted_sql_pack"
                ),
                source_grade="high",
                source_credibility=0.88,
                coverage_dimensions=metrics + ["时间范围", "口径"],
                coverage_score=coverage,
                confidence=confidence,
                limitations=[] if row_count else [f"{name} returned 0 rows"],
            )
        )
    return evidences


def missing_required_blocks(result: Optional[Dict[str, Any]], target_brand: Optional[str] = None) -> List[str]:
    """Return required blocks absent from a targeted SQL result."""
    required = list(REQUIRED_TARGETED_SQL_BLOCKS)
    if not target_brand:
        required = [b for b in required if b not in {"target_brand_performance", "model_contribution", "power_mix", "price_and_config"}]
    seen = {
        block.get("name")
        for block in (result or {}).get("blocks", []) or []
        if int(block.get("row_count") or 0) > 0
    }
    return [block for block in required if block not in seen]


def _db_connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from retrieval.vector_store import DB_CONFIG

    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor, connect_timeout=5)


def _plan_to_dict(plan: Any) -> Dict[str, Any]:
    if plan is None:
        return {}
    if isinstance(plan, dict):
        return dict(plan)
    if is_dataclass(plan):
        return asdict(plan)
    if hasattr(plan, "to_dict"):
        return plan.to_dict()
    return dict(getattr(plan, "__dict__", {}) or {})


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


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


def _period_from_time_range(max_month: int, time_range: str) -> Tuple[int, int, int, int]:
    explicit_year = _explicit_year(time_range)
    if explicit_year:
        year_start = explicit_year * 100 + 1
        year_end = explicit_year * 100 + 12
        period_end = min(max_month, year_end)
        if period_end < year_start:
            period_end = year_end
        period_start = year_start
        prev_start = (explicit_year - 1) * 100 + 1
        prev_end = _month_shift(period_end, -12)
        return period_start, period_end, prev_start, prev_end

    month_count = _month_count_from_range(time_range)
    period_start = _month_shift(max_month, -(month_count - 1))
    prev_start = _month_shift(period_start, -month_count)
    prev_end = _month_shift(max_month, -month_count)
    return period_start, max_month, prev_start, prev_end


def _explicit_year(text: str) -> Optional[int]:
    import re

    match = re.search(r"(20\d{2})\s*年", text or "")
    if not match:
        return None
    return int(match.group(1))


def _month_shift(yyyymm: int, delta: int) -> int:
    year = yyyymm // 100
    month = yyyymm % 100
    total = year * 12 + (month - 1) + delta
    return (total // 12) * 100 + (total % 12 + 1)


def _market_condition(plan: Dict[str, Any]) -> Tuple[str, List[Any]]:
    parts: List[str] = []
    params: List[Any] = []
    market_scope = str(plan.get("market_scope") or "")
    power_type = str(plan.get("power_type") or "")

    if power_type == "新能源" or "新能源" in market_scope:
        parts.append('"技术类型" IN (%s,%s,%s)')
        params.extend(["纯电动", "插电式混合动力", "增程式"])
    elif power_type:
        parts.append('"技术类型" = %s')
        params.append(power_type)

    if "SUV" in market_scope.upper():
        parts.append('"乘用车细分" ILIKE %s')
        params.append("%SUV%")

    if not parts:
        return "1=1", []
    return " AND ".join(parts), params


def _brand_condition(aliases: List[str]) -> Tuple[str, List[Any]]:
    if not aliases:
        return "1=1", []
    fields = ['"企业名称"', '"产品商标"', '"通用名称"']
    parts: List[str] = []
    params: List[Any] = []
    for alias in aliases:
        for field in fields:
            parts.append(f"{field} ILIKE %s")
            params.append(f"%{alias}%")
    return "(" + " OR ".join(parts) + ")", params


def _config_condition(plan: Dict[str, Any]) -> Tuple[str, List[Any]]:
    aliases = plan.get("brand_aliases") or []
    fields = ['"厂商"', '"车型名称"', '"款型名称"']
    parts: List[str] = []
    params: List[Any] = []
    for alias in aliases:
        for field in fields:
            parts.append(f"{field} ILIKE %s")
            params.append(f"%{alias}%")
    if plan.get("price_band"):
        parts.append('"价格带" ILIKE %s')
        params.append(f"%{plan['price_band']}%")
    if plan.get("power_type") and plan.get("power_type") != "新能源":
        parts.append('"能源类型" ILIKE %s')
        params.append(f"%{plan['power_type']}%")
    return ("(" + " OR ".join(parts[: len(aliases) * len(fields)]) + ")" + _extra_config_filters(parts, aliases), params) if aliases else (" AND ".join(parts) or "1=1", params)


def _extra_config_filters(parts: List[str], aliases: List[str]) -> str:
    alias_part_count = len(aliases) * 3
    extras = parts[alias_part_count:]
    if not extras:
        return ""
    return " AND " + " AND ".join(extras)


def _add_mom(rows: List[Dict[str, Any]]) -> None:
    previous = None
    for row in rows:
        sales = row.get("sales") or 0
        row["mom_pct"] = round((sales - previous) * 100.0 / previous, 2) if previous else None
        previous = sales


def _add_yoy(rows: List[Dict[str, Any]]) -> None:
    current = next((row for row in rows if row.get("period") == "current"), None)
    previous = next((row for row in rows if row.get("period") == "previous_year"), None)
    if current and previous and previous.get("sales"):
        current["yoy_pct"] = round((current.get("sales", 0) - previous["sales"]) * 100.0 / previous["sales"], 2)


def _flatten_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for block in blocks:
        for row in block.get("rows") or []:
            item = dict(row)
            item["_block"] = block.get("name")
            item["_purpose"] = block.get("purpose")
            rows.append(item)
    return rows


def _block_coverage_score(block_name: str, row_count: int) -> float:
    base = {
        "market_overview": 0.78,
        "monthly_trend": 0.82,
        "yoy_change": 0.80,
        "competitor_share": 0.86,
        "target_brand_performance": 0.82,
        "model_contribution": 0.84,
        "power_mix": 0.78,
        "price_and_config": 0.72,
    }.get(block_name, 0.60)
    if row_count <= 0:
        return 0.20
    if row_count < 3:
        return round(max(0.45, base - 0.15), 3)
    return base

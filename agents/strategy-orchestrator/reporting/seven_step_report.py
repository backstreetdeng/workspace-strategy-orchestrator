# -*- coding: utf-8 -*-
"""Seven-step business report generated inside strategy-orchestrator.

The functions in this module are pure formatters over orchestrator-owned
outputs. They do not call python_wrapper, frontend code, or external tools.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


SEVEN_STEP_HEADINGS = [
    "第一步：问题定义与范围界定",
    "第二步：市场规模估算（TAM/SAM/SOM）",
    "第三步：竞品矩阵分析",
    "第四步：SWOT+ 分析",
    "第五步：Porter 五力模型",
    "第六步：商业模式拆解",
    "第七步：洞察报告生成",
]

DEGRADATION_THRESHOLD = 0.7


def _build_degradation_notice(
    confidence,
    confidence_details=None,
    missing_or_uncertain=None,
):
    details = confidence_details or {}
    missing = missing_or_uncertain or []
    pct = '{:.0%}'.format(confidence)
    lines = [
        '',
        '## [WARNING] 报告降级声明',
        '',
        '> **本报告置信度为 ' + pct + '，低于70%决策参考线。以下结论为初步判断，不构成确定性战略建议，请结合人工复核。**',
        '',
    ]
    if details:
        factors = [
            ('数据覆盖', details.get('data_coverage_factor'), '结构化数据维度覆盖不足'),
            ('RAG覆盖', details.get('rag_coverage_factor'), '外部文档补证不足'),
            ('来源可信度', details.get('source_credibility_factor'), '证据来源可信度偏低'),
            ('冲突系数', details.get('conflict_factor'), '存在证据冲突未解决'),
        ]
        for label, value, reason in factors:
            if value is not None and value < 0.7:
                lines.append('- **{}={:.0%}**: {}，建议补充该维度证据'.format(label, value, reason))
    if missing:
        lines.append('')
        lines.append('**主要不确定性来源**：')
        for item in missing[:5]:
            lines.append('- ' + item)
    lines.extend([
        '',
        '**建议下一步行动**：',
        '1. 补充同价位竞品月度份额变化数据',
        '2. 检索品牌/行业战略分析报告增强 RAG 证据',
        '3. 如置信度持续低于60%，该报告仅供讨论参考，不建议直接用于战略决策',
        '',
    ])
    return lines





def build_insight_cards(
    *,
    analysis_plan: Dict[str, Any],
    evidence_store: Dict[str, Any],
    confidence: float,
    reflection: Optional[Dict[str, Any]] = None,
    quality_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build short decision cards with explicit evidence ids."""
    metrics = _extract_structured_metrics(evidence_store)
    brand = analysis_plan.get("target_brand") or _first_entity(analysis_plan) or "目标对象"
    cards: List[Dict[str, Any]] = []

    target_sales = metrics.get("target_sales")
    market_sales = metrics.get("market_sales")
    target_share = _safe_share(target_sales, market_sales)
    if target_sales or target_share is not None:
        cards.append(
            {
                "title": f"{brand}市场位置先看 SOM 与销量底盘",
                "insight": (
                    f"当前结构化证据显示目标销量约{_fmt_num(target_sales)}辆，"
                    f"估算 SOM 约{_fmt_pct(target_share)}；该判断应优先绑定同一时间窗口内的销量、份额和车型贡献。"
                ),
                "evidence_ids": _ids(evidence_store, "D", ["target_brand_performance", "competitor_share", "market_overview"]),
                "confidence": round(confidence, 3),
                "next_action": "用相同口径继续补齐月度份额变化、价格带和动力类型，避免只看品牌总量。",
            }
        )

    top_model = metrics.get("top_model") or {}
    if top_model:
        cards.append(
            {
                "title": "车型贡献决定策略抓手",
                "insight": (
                    f"主销车型 {top_model.get('model') or '未知车型'} 贡献约{_fmt_num(top_model.get('sales'))}辆；"
                    "后续策略应围绕该车型的配置、价格带、渠道和竞品压制展开。"
                ),
                "evidence_ids": _ids(evidence_store, "D", ["model_contribution", "price_and_config"]),
                "confidence": round(confidence, 3),
                "next_action": "把 Top 车型与同价位竞品做配置和终端价格对标。",
            }
        )

    leader = metrics.get("leader") or {}
    if leader:
        cards.append(
            {
                "title": "竞品压力必须在同一窗口比较",
                "insight": (
                    f"当前竞品矩阵头部为 {leader.get('brand') or '未知竞品'}，"
                    f"份额约{_fmt_pct(leader.get('share_pct'))}；策略判断需要持续看份额差距和环比变化。"
                ),
                "evidence_ids": _ids(evidence_store, "D", ["competitor_share", "monthly_trend"]),
                "confidence": round(confidence, 3),
                "next_action": "建立月度竞品份额、价格带、动力类型三张固定跟踪表。",
            }
        )

    if not evidence_store.get("R") or not evidence_store.get("W"):
        cards.append(
            {
                "title": "外部补证不足时必须降级结论",
                "insight": "RAG 或 Web 证据不足时，品牌战略、渠道动作、舆情和政策判断只能作为待验证假设。",
                "evidence_ids": _ids(evidence_store, "R") + _ids(evidence_store, "W"),
                "confidence": round(max(0.0, confidence - 0.12), 3),
                "next_action": "补充权威行业报告、企业公告、政策文件或高可信新闻源后再提升结论等级。",
            }
        )

    if reflection and reflection.get("is_stagnant"):
        cards.append(
            {
                "title": "编排已触发反思重规划",
                "insight": reflection.get("strategic_alert") or "证据质量提升停滞，需要切换补证策略。",
                "evidence_ids": [],
                "confidence": round(max(0.0, confidence - 0.08), 3),
                "next_action": reflection.get("pivot_recommendation") or "切换到不同来源或带降级说明输出部分结论。",
            }
        )

    if not cards:
        cards.append(
            {
                "title": "证据不足，先补齐基础数据",
                "insight": "当前证据不足以形成稳定七步法报告，应优先补齐结构化市场指标和 RAG 背景证据。",
                "evidence_ids": [],
                "confidence": round(confidence, 3),
                "next_action": "先执行 targeted_sql_pack 与 RAG 检索，再进入报告生成。",
            }
        )

    for card in cards:
        card.setdefault("quality_context", _quality_label(quality_summary))
    return cards[:5]


def build_seven_step_report(
    *,
    task_id: str,
    question: str,
    analysis_plan: Dict[str, Any],
    evidence_store: Dict[str, Any],
    confidence: float,
    confidence_details: Optional[Dict[str, Any]] = None,
    insight_cards: Optional[List[Dict[str, Any]]] = None,
    reflection: Optional[Dict[str, Any]] = None,
    quality_summary: Optional[Dict[str, Any]] = None,
    missing_or_uncertain: Optional[List[str]] = None,
) -> str:
    """Render the canonical seven-step market strategy report."""
    confidence_details = confidence_details or {}
    reflection = reflection or {}
    quality_summary = quality_summary or {}
    missing_or_uncertain = missing_or_uncertain or []
    if _requires_market_competition_report(analysis_plan):
        return _build_market_competition_report(
            task_id=task_id,
            question=question,
            analysis_plan=analysis_plan,
            evidence_store=evidence_store,
            confidence=confidence,
            confidence_details=confidence_details,
            reflection=reflection,
            quality_summary=quality_summary,
            missing_or_uncertain=missing_or_uncertain,
        )

    cards = insight_cards or build_insight_cards(
        analysis_plan=analysis_plan,
        evidence_store=evidence_store,
        confidence=confidence,
        reflection=reflection,
        quality_summary=quality_summary,
    )
    metrics = _extract_structured_metrics(evidence_store)
    brand = analysis_plan.get("target_brand") or _first_entity(analysis_plan) or "目标对象"
    market_scope = analysis_plan.get("market_scope") or "未指定市场"
    time_range = analysis_plan.get("time_range") or "未指定时间"

    lines = [
        f"# 七步法业务战略分析报告：{question or brand}",
        "",
        f"**任务ID**: {task_id}",
        f"**分析范围**: {brand} / {market_scope} / {time_range}",
        f"**总体置信度**: {_fmt_pct(confidence * 100 if confidence <= 1 else confidence)}",
        f"**证据概况**: D={len(evidence_store.get('D', []))}, R={len(evidence_store.get('R', []))}, W={len(evidence_store.get('W', []))}, A={len(evidence_store.get('A', []))}",
        f"**证据索引**: D={_fmt_ids(_ids(evidence_store, 'D'))}; R={_fmt_ids(_ids(evidence_store, 'R'))}; W={_fmt_ids(_ids(evidence_store, 'W'))}; A={_fmt_ids(_ids(evidence_store, 'A'))}",
        "",
        "> 本报告由 strategy-orchestrator 内部生成，D=结构化数据，R=RAG 文档，W=外部网页，A=分析推断。无证据处按待验证假设处理。",
        "",
        f"## {SEVEN_STEP_HEADINGS[0]}",
        "",
        _bullet("原始问题", question),
        _bullet("目标对象", brand),
        _bullet("市场范围", market_scope),
        _bullet("时间范围", time_range),
        _bullet("价格带", analysis_plan.get("price_band") or "未指定"),
        _bullet("动力类型", analysis_plan.get("power_type") or "未指定"),
        _bullet("统一证据口径", "targeted_sql_pack 负责固定结构化指标，RAG/Web 负责背景与外部补证。"),
        "",
        f"## {SEVEN_STEP_HEADINGS[1]}",
        "",
        _bullet("TAM", f"{market_scope} 总体销量约 {_fmt_num(metrics.get('market_sales'))} 辆，证据 {_fmt_ids(_ids(evidence_store, 'D', ['market_overview']))}"),
        _bullet("SAM", f"按价格带、动力类型、车型级别收窄；当前可用证据 {_fmt_ids(_ids(evidence_store, 'D', ['price_and_config', 'power_mix']))}"),
        _bullet("SOM", f"{brand} 目标销量约 {_fmt_num(metrics.get('target_sales'))} 辆，估算份额 {_fmt_pct(_safe_share(metrics.get('target_sales'), metrics.get('market_sales')))}，证据 {_fmt_ids(_ids(evidence_store, 'D', ['target_brand_performance', 'competitor_share']))}"),
        _bullet("月度趋势", _trend_sentence(metrics, evidence_store)),
        "",
        f"## {SEVEN_STEP_HEADINGS[2]}",
        "",
        _bullet("竞品份额", _competitor_sentence(metrics, evidence_store)),
        _bullet("车型贡献", _model_sentence(metrics, evidence_store)),
        _bullet("动力类型/价格带", _power_price_sentence(metrics, evidence_store)),
        "",
        f"## {SEVEN_STEP_HEADINGS[3]}",
        "",
        _bullet("Strength", f"若 {brand} 在目标窗口内有稳定 SOM 或主销车型贡献，可作为策略支点。证据 {_fmt_ids(_ids(evidence_store, 'D'))}"),
        _bullet("Weakness", "若目标品牌、价格带或外部证据缺失，对渠道、口碑和品牌势能的判断必须降级。"),
        _bullet("Opportunity", "从 SAM 中寻找高增长、竞品集中度低或目标车型贡献强的细分窗口。"),
        _bullet("Threat", "头部竞品份额压制、价格战和政策变化需要 RAG/Web 持续补证。"),
        "",
        f"## {SEVEN_STEP_HEADINGS[4]}",
        "",
        _bullet("现有竞争者", f"使用竞品份额和月度趋势衡量，证据 {_fmt_ids(_ids(evidence_store, 'D', ['competitor_share', 'monthly_trend']))}"),
        _bullet("潜在进入者", "需结合政策、资本投入与新车上市节奏；没有 R/W 证据时不做确定性判断。"),
        _bullet("替代品威胁", "按动力类型、价格带和场景替代关系评估，优先补齐 power_mix 与 price_and_config。"),
        _bullet("供应商议价", "需补充电池、芯片、智能驾驶硬件和供应链资料。"),
        _bullet("买方议价", "通过价格带、终端优惠、口碑与竞品密度判断。"),
        "",
        f"## {SEVEN_STEP_HEADINGS[5]}",
        "",
        _bullet("价值主张", f"围绕 {brand} 在 {market_scope} 的主销车型、动力类型和价格带构建。"),
        _bullet("收入/销量驱动", "销量、份额、车型贡献是第一层驱动；配置、渠道、政策是第二层解释变量。"),
        _bullet("资源约束", "证据缺口会直接限制商业模式判断的置信度。"),
        "",
        f"## {SEVEN_STEP_HEADINGS[6]}",
        "",
    ]

    # Low-confidence degradation notice
    if confidence < DEGRADATION_THRESHOLD:
        lines.extend(_build_degradation_notice(confidence, confidence_details, missing_or_uncertain))

    for idx, card in enumerate(cards, 1):
        lines.extend(
            [
                f"### 洞察 {idx}: {card.get('title')}",
                "",
                _bullet("判断", card.get("insight")),
                _bullet("证据", _fmt_ids(card.get("evidence_ids") or [])),
                _bullet("下一步", card.get("next_action")),
                _bullet("卡片置信度", _fmt_pct((card.get("confidence") or 0) * 100)),
                "",
            ]
        )

    lines.extend(
        [
            "## 置信度与质量门禁",
            "",
            _bullet("置信度细项", _confidence_sentence(confidence_details)),
            _bullet("质量门禁", _quality_label(quality_summary)),
            _bullet("反思状态", _reflection_sentence(reflection)),
            _bullet("缺失/不确定", "; ".join(missing_or_uncertain) if missing_or_uncertain else "暂无显式缺口"),
        ]
    )
    return "\n".join(str(line) for line in lines if line is not None)


def _requires_market_competition_report(analysis_plan: Dict[str, Any]) -> bool:
    strategy = analysis_plan.get("answer_strategy") or {}
    return (
        strategy.get("subject_kind") == "market"
        and not strategy.get("is_target_specific")
        and any("SOM" in item or "目标对象" in item for item in strategy.get("must_not_use", []))
    )


def _build_market_competition_report(
    *,
    task_id: str,
    question: str,
    analysis_plan: Dict[str, Any],
    evidence_store: Dict[str, Any],
    confidence: float,
    confidence_details: Dict[str, Any],
    reflection: Dict[str, Any],
    quality_summary: Dict[str, Any],
    missing_or_uncertain: List[str],
) -> str:
    metrics = _extract_structured_metrics(evidence_store)
    market_scope = analysis_plan.get("market_scope") or "未指定市场"
    time_range = analysis_plan.get("time_range") or "未指定时间"
    strategy = analysis_plan.get("answer_strategy") or {}
    competitors = metrics.get("top_competitors") or []
    uncertainty = list(missing_or_uncertain or [])
    if not evidence_store.get("W"):
        uncertainty.append("缺少外部网页/实时公开来源补证，政策、渠道、价格战和舆情判断需要降级")
    if len(evidence_store.get("R", []) or []) < 2:
        uncertainty.append("RAG文档来源偏少，行业背景和战略解释不足")
    if not competitors:
        uncertainty.append("缺少可用Top品牌/企业份额表，无法稳定判断竞争梯队")

    lines = [
        f"# 市场竞争格局分析报告：{question}",
        "",
        f"**任务ID**: {task_id}",
        f"**分析对象**: {market_scope}",
        f"**时间口径**: {_period_label(metrics, time_range)}",
        f"**总体置信度**: {_fmt_pct(confidence * 100 if confidence <= 1 else confidence)}",
        f"**证据概况**: D={len(evidence_store.get('D', []))}, R={len(evidence_store.get('R', []))}, W={len(evidence_store.get('W', []))}, A={len(evidence_store.get('A', []))}",
        f"**答案策略来源**: {strategy.get('source', 'unknown')}；目标={strategy.get('question_goal', '未写入')}",
        "",
        "> 本报告按“市场竞争结构”问题回答，不使用目标对象/SOM模板。企业名称可能仍是数据库企业口径，未完成集团品牌归并时需人工复核。",
        "",
        "## 1. 口径与数据窗口",
        "",
        _bullet("原始问题", question),
        _bullet("市场范围", market_scope),
        _bullet("数据窗口", _period_label(metrics, time_range)),
        _bullet("结构化数据口径", "PostgreSQL销量库 targeted_sql_pack；品牌/企业口径以库内字段为准"),
        _bullet("必须回答", "；".join(strategy.get("must_answer") or [])),
        "",
        "## 2. 市场规模与走势",
        "",
        _bullet("累计销量", f"{_fmt_num(metrics.get('market_sales'))} 辆，证据 {_fmt_ids(_ids(evidence_store, 'D', ['market_overview']))}"),
        _bullet("参与企业/品牌数", f"{_fmt_num(metrics.get('brand_count'))} 个；车型数 {_fmt_num(metrics.get('model_count'))} 个"),
        _bullet("最近月变化", _trend_sentence(metrics, evidence_store)),
        "",
        "## 3. Top品牌/企业份额",
        "",
    ]

    if competitors:
        lines.extend(_competitor_table(competitors))
    else:
        lines.append("- 证据不足：当前没有可用竞品份额行。")

    lines.extend(
        [
            "",
            "## 4. 集中度与竞争梯队",
            "",
            _bullet("集中度", _concentration_sentence(competitors)),
            _bullet("头部梯队", _tier_sentence(competitors, 0, 3)),
            _bullet("腰部梯队", _tier_sentence(competitors, 3, 8)),
            _bullet("长尾格局", _tail_sentence(metrics, competitors)),
            "",
            "## 5. 格局判断",
            "",
            _bullet("核心判断", _market_landscape_judgement(metrics, competitors)),
            _bullet("竞争压力", "头部企业份额、价格战和新品节奏是短期格局变化的主要观测项；外部证据不足时不做确定性渠道/舆情判断。"),
            _bullet("口径风险", "当前品牌可能按企业名称拆分，如同一集团/品牌存在多主体，需要做集团品牌归并后再用于正式决策。"),
            "",
            "## 6. 证据缺口与下一步",
            "",
        ]
    )
    for item in uncertainty[:8]:
        lines.append(f"- {item}")
    if not uncertainty:
        lines.append("- 暂无显式缺口。")

    lines.extend(
        [
            "",
            "## 7. 置信度与质量门禁",
            "",
            _bullet("置信度细项", _confidence_sentence(confidence_details)),
            _bullet("质量门禁", _quality_label(quality_summary)),
            _bullet("反思状态", _reflection_sentence(reflection)),
        ]
    )
    return "\n".join(str(line) for line in lines if line is not None)


def _extract_structured_metrics(evidence_store: Dict[str, Any]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    competitors: List[Dict[str, Any]] = []
    models: List[Dict[str, Any]] = []
    power_mix: List[Dict[str, Any]] = []
    price_rows: List[Dict[str, Any]] = []
    trends: List[Dict[str, Any]] = []

    for item in evidence_store.get("D", []) or []:
        block = _block_name(item)
        rows = _sample_rows(item.get("content"))
        if block == "market_overview" and rows:
            row = rows[0]
            metrics["market_sales"] = _num(row.get("total_sales"))
            metrics["period_start"] = row.get("period_start")
            metrics["period_end"] = row.get("period_end")
            metrics["brand_count"] = row.get("brand_count")
            metrics["model_count"] = row.get("model_count")
        elif block == "target_brand_performance" and rows:
            row = rows[0]
            metrics["target_sales"] = _num(row.get("sales"))
            metrics["target_brand"] = row.get("brand")
        elif block == "competitor_share":
            competitors.extend(rows)
        elif block == "model_contribution":
            models.extend(rows)
        elif block == "power_mix":
            power_mix.extend(rows)
        elif block == "price_and_config":
            price_rows.extend(rows)
        elif block == "monthly_trend":
            trends.extend(rows)

    competitors.sort(key=lambda row: _num(row.get("sales")) or 0, reverse=True)
    models.sort(key=lambda row: _num(row.get("sales")) or 0, reverse=True)
    trends.sort(key=lambda row: str(row.get("month") or ""))
    metrics["leader"] = competitors[0] if competitors else {}
    metrics["top_competitors"] = competitors[:12]
    metrics["top_model"] = models[0] if models else {}
    metrics["models"] = models[:5]
    metrics["power_mix"] = power_mix[:5]
    metrics["price_rows"] = price_rows[:5]
    metrics["trends"] = trends[-6:]
    return metrics


def _block_name(item: Dict[str, Any]) -> str:
    text = " ".join(str(item.get(key) or "") for key in ("claim", "content", "data_caliber"))
    marker = "targeted_sql_pack/"
    if marker in text:
        tail = text.split(marker, 1)[1]
        return tail.split(":", 1)[0].split(";", 1)[0].strip()
    if "block=" in text:
        return text.split("block=", 1)[1].split(";", 1)[0].strip()
    return ""


def _sample_rows(content: Any) -> List[Dict[str, Any]]:
    text = str(content or "")
    marker = "sample="
    if marker not in text:
        return []
    raw = text.split(marker, 1)[1].strip()
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def _ids(evidence_store: Dict[str, Any], bucket: str, blocks: Optional[List[str]] = None) -> List[str]:
    ids: List[str] = []
    for item in evidence_store.get(bucket, []) or []:
        if blocks and _block_name(item) not in blocks:
            continue
        evidence_id = item.get("id")
        if evidence_id:
            ids.append(str(evidence_id))
    return ids


def _first_entity(plan: Dict[str, Any]) -> str:
    entities = plan.get("entities") or plan.get("brand_aliases") or []
    return str(entities[0]) if entities else ""


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_share(part: Any, whole: Any) -> Optional[float]:
    part_num = _num(part)
    whole_num = _num(whole)
    if not part_num or not whole_num:
        return None
    return round(part_num * 100.0 / whole_num, 2)


def _fmt_num(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "未知"
    return f"{number:,.0f}"


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "未知"
    return f"{number:.1f}%"


def _fmt_ids(ids: List[str]) -> str:
    return ", ".join(ids) if ids else "证据不足"


def _bullet(label: str, value: Any) -> str:
    return f"- **{label}**: {value if value not in (None, '') else '未提供'}"


def _period_label(metrics: Dict[str, Any], fallback: str) -> str:
    start = metrics.get("period_start")
    end = metrics.get("period_end")
    if start and end:
        return f"{start}-{end}（库内可用窗口；用户口径：{fallback}）"
    return fallback


def _competitor_table(competitors: List[Dict[str, Any]]) -> List[str]:
    lines = [
        "| 排名 | 品牌/企业 | 销量 | 份额 | 车型数 |",
        "|---:|---|---:|---:|---:|",
    ]
    for idx, row in enumerate(competitors[:10], 1):
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                idx,
                row.get("brand") or row.get("maker") or "未知",
                _fmt_num(row.get("sales")),
                _fmt_pct(row.get("share_pct")),
                _fmt_num(row.get("model_count")),
            )
        )
    return lines


def _concentration_sentence(competitors: List[Dict[str, Any]]) -> str:
    if not competitors:
        return "证据不足"

    def share_sum(limit: int) -> Optional[float]:
        values = [_num(row.get("share_pct")) for row in competitors[:limit]]
        values = [value for value in values if value is not None]
        if not values:
            return None
        return round(sum(values), 2)

    return "CR3={}，CR5={}，CR10={}".format(
        _fmt_pct(share_sum(3)),
        _fmt_pct(share_sum(5)),
        _fmt_pct(share_sum(10)),
    )


def _tier_sentence(competitors: List[Dict[str, Any]], start: int, end: int) -> str:
    rows = competitors[start:end]
    if not rows:
        return "证据不足"
    labels = [
        f"{row.get('brand') or row.get('maker') or '未知'}({_fmt_pct(row.get('share_pct'))})"
        for row in rows
    ]
    return "、".join(labels)


def _tail_sentence(metrics: Dict[str, Any], competitors: List[Dict[str, Any]]) -> str:
    total = _num(metrics.get("brand_count"))
    if total is None or not competitors:
        return "证据不足"
    tail_count = max(0, int(total) - len(competitors[:10]))
    return f"库内共有约{_fmt_num(total)}个品牌/企业，Top10之外仍有约{tail_count}个主体，长尾竞争和局部细分机会需要继续拆分价格带/级别验证。"


def _market_landscape_judgement(metrics: Dict[str, Any], competitors: List[Dict[str, Any]]) -> str:
    if not competitors:
        return "当前缺少竞品份额证据，不能形成竞争格局判断。"
    leader = competitors[0]
    cr3_values = [_num(row.get("share_pct")) for row in competitors[:3]]
    cr3_values = [value for value in cr3_values if value is not None]
    cr3 = sum(cr3_values) if cr3_values else None
    if cr3 is not None and cr3 >= 45:
        structure = "头部集中度较高"
    elif cr3 is not None and cr3 >= 30:
        structure = "头部有优势但竞争仍分散"
    else:
        structure = "竞争较分散"
    return (
        f"{structure}；当前第一名为{leader.get('brand') or '未知'}，份额约{_fmt_pct(leader.get('share_pct'))}。"
        "正式战略判断还需要补齐品牌集团归并、价格带和动力类型拆分。"
    )


def _trend_sentence(metrics: Dict[str, Any], evidence_store: Dict[str, Any]) -> str:
    trends = metrics.get("trends") or []
    if not trends:
        return f"暂无可用月度趋势行，证据 {_fmt_ids(_ids(evidence_store, 'D', ['monthly_trend']))}"
    latest = trends[-1]
    return (
        f"最近月 {latest.get('month')} 销量约 {_fmt_num(latest.get('sales'))} 辆，"
        f"环比 {_fmt_pct(latest.get('mom_pct'))}，证据 {_fmt_ids(_ids(evidence_store, 'D', ['monthly_trend']))}"
    )


def _competitor_sentence(metrics: Dict[str, Any], evidence_store: Dict[str, Any]) -> str:
    leader = metrics.get("leader") or {}
    if not leader:
        return f"暂无竞品份额行，证据 {_fmt_ids(_ids(evidence_store, 'D', ['competitor_share']))}"
    return (
        f"头部竞品 {leader.get('brand') or '未知'} 销量约 {_fmt_num(leader.get('sales'))} 辆，"
        f"份额 {_fmt_pct(leader.get('share_pct'))}，证据 {_fmt_ids(_ids(evidence_store, 'D', ['competitor_share']))}"
    )


def _model_sentence(metrics: Dict[str, Any], evidence_store: Dict[str, Any]) -> str:
    model = metrics.get("top_model") or {}
    if not model:
        return f"暂无车型贡献行，证据 {_fmt_ids(_ids(evidence_store, 'D', ['model_contribution']))}"
    return (
        f"主销车型 {model.get('model') or '未知车型'} 销量约 {_fmt_num(model.get('sales'))} 辆，"
        f"证据 {_fmt_ids(_ids(evidence_store, 'D', ['model_contribution']))}"
    )


def _power_price_sentence(metrics: Dict[str, Any], evidence_store: Dict[str, Any]) -> str:
    power = metrics.get("power_mix") or []
    price = metrics.get("price_rows") or []
    power_label = power[0].get("power_type") if power else "未知动力"
    price_label = price[0].get("price_band") or price[0].get("guide_price") if price else "未知价格带"
    return (
        f"主要动力类型 {power_label}，代表价格带/指导价 {price_label}，"
        f"证据 {_fmt_ids(_ids(evidence_store, 'D', ['power_mix', 'price_and_config']))}"
    )


def _confidence_sentence(details: Dict[str, Any]) -> str:
    if not details:
        return "暂无置信度细项"
    keys = [
        "data_coverage_factor",
        "rag_coverage_factor",
        "source_credibility_factor",
        "conflict_factor",
        "confidence",
    ]
    parts = [f"{key}={details[key]}" for key in keys if key in details]
    return "; ".join(parts) if parts else str(details)


def _quality_label(summary: Optional[Dict[str, Any]]) -> str:
    if not summary:
        return "质量门禁尚未写入报告上下文"
    passed = summary.get("quality_passed", summary.get("passed"))
    failed = summary.get("failed_checks")
    return f"quality_passed={passed}, failed_checks={failed}"


def _reflection_sentence(reflection: Dict[str, Any]) -> str:
    if not reflection:
        return "暂无反思记录"
    phase = reflection.get("current_phase") or reflection.get("next_phase") or "unknown"
    stagnant = reflection.get("is_stagnant")
    alert = reflection.get("strategic_alert") or ""
    return f"phase={phase}, stagnant={stagnant}, alert={alert or 'none'}"

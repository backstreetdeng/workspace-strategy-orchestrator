# -*- coding: utf-8 -*-
"""P3 Task 2: 四因子置信度权重校准测试（黄金测试集）。

用途：验证当前四因子权重（0.30/0.25/0.30/0.15）是否与真实case对齐。
不做权重修改，只做验证和报告。

Case 设计原则：
- case_A: 全明星 → 期望高置信度 (>0.75)
- case_B: 结构化全、RAG缺 → 期望中高置信度 (0.65-0.75)
- case_C: 结构化缺、RAG全 → 期望中低置信度 (<0.65)
- case_D: 数据冲突 → 期望显著降权
- case_E: 低覆盖 → 期望低置信度 (<0.55)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = ROOT / "agents" / "strategy-orchestrator"
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

from evidence.evidence_ledger import Evidence, EvidenceLedger
from evidence.evidence_ledger import EvidenceSource


class CalibrationCase:
    """黄金测试 case：输入证据配置 + 期望置信度范围"""

    def __init__(
        self,
        name: str,
        evidences: list,
        expected_min: float,
        expected_max: float,
        reason: str,
    ):
        self.name = name
        self.evidences = evidences
        self.expected_min = expected_min
        self.expected_max = expected_max
        self.reason = reason


def make_ledger(evidences: list) -> EvidenceLedger:
    ledger = EvidenceLedger()
    for e in evidences:
        ledger.add_evidence(**e)
    return ledger


CASES = [
    # case_A: 全明星 - 结构化+RAG+高可信度+无冲突
    CalibrationCase(
        name="case_A_全明星",
        evidences=[
            dict(source="nl2sql-pg", tool="market_db", claim="比亚迪销量份额",
                 content="比亚迪12个月销量300万，份额25%",
                 time_range="最近12个月",
                 data_caliber="乘用车结构化数据库",
                 metrics=["销量", "份额", "趋势", "车型", "动力", "价格"],
                 coverage_dimensions=["时间范围", "口径"],
                 coverage_score=0.90,
                 source_credibility=0.88,
                 confidence=0.86),
            dict(source="rag", tool="vector_retriever", claim="比亚迪战略背景",
                 content="行业报告显示比亚迪持续强化成本与产品矩阵优势",
                 time_range="用户问题时间范围：最近12个月",
                 data_caliber="向量检索文档摘要",
                 coverage_dimensions=["行业报告", "趋势解释"],
                 coverage_score=0.70,
                 source_credibility=0.72,
                 confidence=0.72),
            dict(source="nl2sql-pg", tool="market_db", claim="竞品月度份额",
                 content="特斯拉份额12%，蔚来3%",
                 time_range="最近12个月",
                 data_caliber="乘用车结构化数据库",
                 metrics=["竞品份额", "月度趋势"],
                 coverage_dimensions=["竞品维度"],
                 coverage_score=0.85,
                 source_credibility=0.85,
                 confidence=0.84),
        ],
        expected_min=0.72,
        expected_max=0.90,
        reason="多源高可信度证据，无冲突，期望高置信度",
    ),

    # case_B: 结构化全、RAG缺
    CalibrationCase(
        name="case_B_结构化全_RAG缺",
        evidences=[
            dict(source="nl2sql-pg", tool="market_db", claim="比亚迪销量份额",
                 content="比亚迪12个月销量300万，份额25%",
                 time_range="最近12个月",
                 data_caliber="乘用车结构化数据库",
                 metrics=["销量", "份额", "趋势", "车型", "动力", "价格"],
                 coverage_dimensions=["时间范围", "口径"],
                 coverage_score=0.90,
                 source_credibility=0.88,
                 confidence=0.86),
            dict(source="nl2sql-pg", tool="market_db", claim="竞品月度份额",
                 content="特斯拉份额12%，蔚来3%",
                 time_range="最近12个月",
                 data_caliber="乘用车结构化数据库",
                 metrics=["竞品份额"],
                 coverage_dimensions=["竞品维度"],
                 coverage_score=0.85,
                 source_credibility=0.85,
                 confidence=0.84),
        ],
        expected_min=0.60,
        expected_max=0.75,
        reason="只有结构化证据，无RAG补证，置信度应低于全明星",
    ),

    # case_C: RAG全、结构化缺
    CalibrationCase(
        name="case_C_RAG全_结构化缺",
        evidences=[
            dict(source="rag", tool="vector_retriever", claim="比亚迪战略背景",
                 content="行业报告显示比亚迪持续强化成本与产品矩阵优势",
                 time_range="用户问题时间范围：最近12个月",
                 data_caliber="向量检索文档摘要",
                 coverage_dimensions=["行业报告", "趋势解释"],
                 coverage_score=0.70,
                 source_credibility=0.72,
                 confidence=0.72),
            dict(source="rag", tool="vector_retriever", claim="政策影响",
                 content="新能源补贴退坡对比亚迪影响有限",
                 time_range="用户问题时间范围：最近12个月",
                 data_caliber="向量检索文档摘要",
                 coverage_dimensions=["政策解读"],
                 coverage_score=0.65,
                 source_credibility=0.68,
                 confidence=0.68),
        ],
        expected_min=0.40,
        expected_max=0.60,
        reason="只有RAG无结构化数据，置信度应偏低",
    ),

    # case_D: 高冲突
    CalibrationCase(
        name="case_D_证据冲突",
        evidences=[
            dict(source="nl2sql-pg", tool="market_db", claim="比亚迪销量份额",
                 content="比亚迪12个月销量:300，份额:25",
                 time_range="最近12个月",
                 data_caliber="乘用车结构化数据库",
                 metrics=["销量", "份额"],
                 coverage_dimensions=["时间范围"],
                 coverage_score=0.90,
                 source_credibility=0.88,
                 confidence=0.86),
            dict(source="nl2sql-pg", tool="market_db", claim="比亚迪销量份额",
                 content="比亚迪12个月销量:240，份额:20（另一口径）",
                 time_range="最近12个月",
                 data_caliber="另一个数据库口径",
                 metrics=["销量", "份额"],
                 coverage_dimensions=["时间范围"],
                 coverage_score=0.85,
                 source_credibility=0.75,
                 confidence=0.80),
        ],
        expected_min=0.25,
        expected_max=0.45,
        reason="两条高可信度结构化证据但存在同指标数值冲突，冲突系数0.5应显著降权",
    ),

    # case_E: 极低覆盖
    CalibrationCase(
        name="case_E_极低覆盖",
        evidences=[
            dict(source="nl2sql-pg", tool="market_db", claim="销量数据",
                 content="某数据",
                 time_range="unknown",
                 data_caliber="unknown",
                 metrics=["销量"],
                 coverage_dimensions=[],
                 coverage_score=0.20,
                 source_credibility=0.50,
                 confidence=0.50),
        ],
        expected_min=0.20,
        expected_max=0.45,
        reason="单一低可信度证据，维度覆盖极低",
    ),
]


class ConfidenceCalibrationTest(unittest.TestCase):
    """黄金测试集：确保四因子置信度模型持续符合预期区间。"""

    def test_confidence_calibration_cases(self):
        results = []
        for case in CASES:
            with self.subTest(case=case.name):
                confidence, details = self._run_case(case)
                self.assertGreaterEqual(
                    confidence,
                    case.expected_min,
                    f"{case.name}: {case.reason}",
                )
                self.assertLessEqual(
                    confidence,
                    case.expected_max,
                    f"{case.name}: {case.reason}",
                )
                results.append((case.name, confidence, details))

    def test_conflict_case_triggers_conflict_factor(self):
        conflict_case = next(case for case in CASES if case.name == "case_D_证据冲突")
        confidence, details = self._run_case(conflict_case)

        self.assertEqual(details.get("high_conflicts"), 1)
        self.assertLess(details.get("conflict_factor", 1.0), 1.0)
        self.assertLess(confidence, 0.45)

    def _run_case(self, case: CalibrationCase):
        ledger = make_ledger(case.evidences)
        confidence, details = ledger.calculate_overall_confidence()
        return confidence, details


def run_confidence_calibration_report():
    """脚本模式：打印黄金测试集校准报告。"""
    print("=" * 60)
    print("四因子置信度模型 - 黄金测试集校准")
    print("当前权重: 0.30*数据覆盖 + 0.25*RAG覆盖 + 0.30*来源可信度 + 0.15*基础置信度")
    print("=" * 60)

    all_passed = True
    results = []

    for case in CASES:
        ledger = make_ledger(case.evidences)
        confidence, details = ledger.calculate_overall_confidence()
        in_range = case.expected_min <= confidence <= case.expected_max
        status = "PASS" if in_range else "FAIL"

        print(f"\n{case.name}: {status} | 实际={confidence:.3f} | 期望=[{case.expected_min:.2f}, {case.expected_max:.2f}]")
        print(f"  原因: {case.reason}")
        print(f"  四因子: data_cov={details.get('data_coverage_factor', 0):.3f}, "
              f"rag_cov={details.get('rag_coverage_factor', 0):.3f}, "
              f"src_cred={details.get('source_credibility_factor', 0):.3f}, "
              f"conflict={details.get('conflict_factor', 0):.3f}")

        results.append({
            "name": case.name,
            "actual": confidence,
            "expected_min": case.expected_min,
            "expected_max": case.expected_max,
            "passed": in_range,
            "details": details,
        })

        if not in_range:
            all_passed = False

    print("\n" + "=" * 60)
    print(f"校准结果: {'全部通过' if all_passed else '存在偏差'}")

    if not all_passed:
        print("\n偏差case及建议：")
        for r in results:
            if not r["passed"]:
                delta = r["actual"] - r["expected_max"] if r["actual"] > r["expected_max"] else r["actual"] - r["expected_min"]
                print(f"  {r['name']}: 实际{r['actual']:.3f} vs 期望[{r['expected_min']:.2f}, {r['expected_max']:.2f}]")
                print(f"    偏差: {delta:+.3f}")
                # 提供权重调整建议
                d = r["details"]
                if d.get("data_coverage_factor", 0) < 0.5:
                    print(f"    建议: 数据覆盖因子偏低，可适当提高 data_coverage 权重或改善 evidence.coverage_score")
                if d.get("rag_coverage_factor", 0) < 0.5:
                    print(f"    建议: RAG覆盖因子偏低，当前权重(0.25)可能过高，建议降低或优先补充RAG证据")

    return all_passed, results


if __name__ == "__main__":
    passed, results = run_confidence_calibration_report()
    sys.exit(0 if passed else 1)

# -*- coding: utf-8 -*-
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Tuple

class AnalysisPhase(Enum):
    PROBLEM_DEFINITION = 'problem_definition'
    DATA_COLLECTION = 'data_collection'
    STRUCTURED_ANALYSIS = 'structured_analysis'
    INSIGHT_GENERATION = 'insight_generation'
    CONFIDENCE_ASSESSMENT = 'confidence_assessment'
    REPORT_GENERATION = 'report_generation'
    SELF_REVIEW = 'self_review'

PHASE_ORDER = [
    AnalysisPhase.PROBLEM_DEFINITION,
    AnalysisPhase.DATA_COLLECTION,
    AnalysisPhase.STRUCTURED_ANALYSIS,
    AnalysisPhase.INSIGHT_GENERATION,
    AnalysisPhase.CONFIDENCE_ASSESSMENT,
    AnalysisPhase.REPORT_GENERATION,
    AnalysisPhase.SELF_REVIEW,
]

PHASE_REQUIREMENTS = {
    AnalysisPhase.PROBLEM_DEFINITION: ['analysis_plan_created'],
    AnalysisPhase.DATA_COLLECTION: ['core_market_metrics', 'rag_context'],
    AnalysisPhase.STRUCTURED_ANALYSIS: ['monthly_trend', 'yoy_change', 'competitor_share'],
    AnalysisPhase.INSIGHT_GENERATION: ['opportunities_identified', 'risks_identified'],
    AnalysisPhase.CONFIDENCE_ASSESSMENT: ['confidence_calculated', 'evidence_gaps_documented'],
    AnalysisPhase.REPORT_GENERATION: ['answer_drafted', 'recommendations_generated'],
    AnalysisPhase.SELF_REVIEW: ['quality_gate_passed', 'reflection_complete'],
}

PHASE_LABELS = {
    AnalysisPhase.PROBLEM_DEFINITION: '问题定义',
    AnalysisPhase.DATA_COLLECTION: '数据收集',
    AnalysisPhase.STRUCTURED_ANALYSIS: '结构化分析',
    AnalysisPhase.INSIGHT_GENERATION: '洞察生成',
    AnalysisPhase.CONFIDENCE_ASSESSMENT: '置信度评估',
    AnalysisPhase.REPORT_GENERATION: '报告生成',
    AnalysisPhase.SELF_REVIEW: '自我审查',
}

class PhaseTracker:
    def requirements_status(self, state, extra_outputs=None):
        outputs = dict(extra_outputs or {})
        structured_blocks = set(_structured_blocks_seen(state))
        tool_sources = _successful_tool_sources(state)
        reflection = getattr(state, 'reflection', {}) or {}
        outputs['analysis_plan_created'] = getattr(state, 'analysis_plan', None) is not None
        outputs['core_market_metrics'] = (
            'targeted-sql-pack' in tool_sources or 'targeted_sql_pack' in tool_sources or 'market_overview' in structured_blocks
        )
        outputs['rag_context'] = 'rag' in tool_sources or 'pg-vector-search' in tool_sources
        outputs['monthly_trend'] = 'monthly_trend' in structured_blocks
        outputs['yoy_change'] = 'yoy_change' in structured_blocks
        outputs['competitor_share'] = 'competitor_share' in structured_blocks
        outputs['opportunities_identified'] = bool(outputs.get('opportunities_identified')) or any(
            step.startswith('analysis-framework') for step in getattr(state, 'completed_steps', [])
        )
        outputs['risks_identified'] = bool(outputs.get('risks_identified')) or 'conflicts' in reflection
        outputs['confidence_calculated'] = 'overall_confidence' in reflection
        outputs['evidence_gaps_documented'] = 'evidence_gaps' in reflection
        outputs.setdefault('answer_drafted', bool(outputs.get('answer_drafted')))
        outputs.setdefault('recommendations_generated', bool(outputs.get('recommendations_generated')))
        outputs.setdefault('quality_gate_passed', bool(outputs.get('quality_gate_passed')))
        outputs.setdefault('reflection_complete', bool(reflection))
        return outputs

    def run_phase(self, phase, task, state, extra_outputs=None):
        current = _coerce_phase(phase)
        status = self.requirements_status(state, extra_outputs=extra_outputs)
        missing = self.missing_requirements(current, status)
        if missing:
            for item in missing:
                gap = f'phase_missing:{current.value}:{item}'
                if gap not in getattr(state, 'evidence_gaps', []):
                    state.evidence_gaps.append(gap)
            return False, current.value, [f'missing:{item}' for item in missing], status
        next_phase = self.next_phase(current)
        moved_forward = next_phase != current
        reasons = ['requirements_met'] if moved_forward else ['final_phase_reached']
        return moved_forward, next_phase.value, reasons, status

    def phase_tracker(self, state, extra_outputs=None):
        current = _coerce_phase(getattr(state, 'current_phase', AnalysisPhase.PROBLEM_DEFINITION.value))
        status = self.requirements_status(state, extra_outputs=extra_outputs)
        missing = self.missing_requirements(current, status)
        next_phase = self.next_phase(current) if not missing else current
        return {
            'current_phase': current.value,
            'current_phase_label': PHASE_LABELS[current],
            'next_phase': next_phase.value,
            'next_phase_label': PHASE_LABELS[next_phase],
            'requirements_status': status,
            'missing_requirements': missing,
            'phase_requirements_met': not missing,
        }

    def missing_requirements(self, phase, status):
        return [item for item in PHASE_REQUIREMENTS[phase] if not status.get(item, False)]

    def next_phase(self, phase):
        idx = PHASE_ORDER.index(phase)
        if idx >= len(PHASE_ORDER) - 1:
            return phase
        return PHASE_ORDER[idx + 1]

def phase_tracker(state, extra_outputs=None):
    return PhaseTracker().phase_tracker(state, extra_outputs=extra_outputs)

def _coerce_phase(value):
    if isinstance(value, AnalysisPhase):
        return value
    try:
        return AnalysisPhase(str(value))
    except ValueError:
        return AnalysisPhase.PROBLEM_DEFINITION

def _successful_tool_sources(state):
    return {
        result.tool_name
        for result in getattr(state, 'tool_results', []) or []
        if getattr(result, 'success', False)
    }

def _structured_blocks_seen(state):
    blocks = []
    for result in getattr(state, 'tool_results', []) or []:
        if getattr(result, 'tool_name', '') not in ('targeted-sql-pack', 'targeted_sql_pack'):
            continue
        payload = getattr(result, 'result', None)
        if not isinstance(payload, dict):
            continue
        for block in payload.get('blocks', []) or []:
            name = block.get('name')
            if name and name not in blocks:
                blocks.append(name)
    return blocks

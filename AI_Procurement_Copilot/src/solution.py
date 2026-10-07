"""Shreyansh Arora | 24bcs10252. Two advisory workflows, same controls."""
import os
from dotenv import load_dotenv
from src.contracts import Architecture, ProcurementDecision, EvidenceItem, RunTelemetry
from src import data_access as db
from src.tools import Tools
from src.model import infer
load_dotenv(db.ROOT / '.env', override=False)


def handle_request(request_id: str, architecture: Architecture = 'single') -> ProcurementDecision:
    return analyze_request(db.get_request(request_id), architecture)


def analyze_request(req: dict, architecture: Architecture = 'single') -> ProcurementDecision:
    if architecture not in ('single','staged'): raise ValueError('Unknown architecture')
    tools = Tools()
    pack = {'request': req, 'budget': tools.budget(req.get('requester_id')),
            'catalog': tools.catalog(req), 'vendor': tools.vendor(req.get('vendor_name')), 'policy': tools.policy()}
    controls = tools.rules(req, pack)
    evidence = [{'id': key, 'source': key, 'finding': value, 'reference': reference} for key, value, reference in (
        ('request', req, str(req.get('request_id','custom'))),
        ('budget', pack['budget'], 'data/department_budgets.csv + data/employees.csv'),
        ('catalog', pack['catalog'], 'data/software_catalog.csv'),
        ('vendor', pack['vendor'], 'data/vendors.csv + GET /vendor-risk/{vendor_name} + data/purchase_history.csv'),
        ('policy', pack['policy'], 'data/procurement_policy.md sections 1-11'),
        ('controls', controls, 'src/tools.py:rules'))]
    model_pack = {'request': req, 'evidence': evidence, 'controls': controls}
    calls = 0
    mode = os.getenv('COPILOT_MODE','offline').lower()
    flags = list(controls['risk_flags']); missing = list(controls['missing_information'])
    route = 'clarify' if controls['requester_missing'] else 'manual_review' if missing or any(f in flags for f in
        ('budget_insufficient','vendor_review_expired','vendor_review_date_invalid','conflicting_vendor_evidence','vendor_risk_unavailable','security_review_required','privacy_review_required','legal_review_required')) else 'reuse_review' if any(r['match_type'] != 'same_vendor_related' or r['same_category'] for r in pack['catalog']) else 'approval_review'
    code_route = route
    advice = None
    reason = 'Offline rule preview. Semantic need/gap interpretation has not been model-verified.'
    if mode == 'live':
        try:
            # Local key, or a network-injected key (proxy adds the header; key never enters env/files).
            if not (os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI_NETWORK_SECRET') == '1'): raise RuntimeError('No provider key')
            calls += 1
            advice = infer(model_pack, 'Procurement Agent' if architecture == 'single' else 'Procurement Analyst')
            if architecture == 'staged':
                calls += 1
                advice = infer({**model_pack, 'analyst': advice.model_dump()}, 'Policy/Risk Reviewer: check the analyst against the same structured evidence pack; do not re-fetch tools')
            if advice.route == 'reuse_review' and not pack['catalog']: raise ValueError('Reuse without catalog evidence')
            if advice.route == 'clarify' and not missing:
                if not advice.gap_reason.strip(): raise ValueError('Clarify without an ask')
                missing.append('Model-identified: ' + advice.gap_reason)
            reason = ('Model suggested ' + advice.route + ': ' + advice.reason + ' Code requires ' + code_route + '.') if code_route in ('clarify','manual_review') else advice.reason
            # Model can refine overlap/need but cannot downgrade a material safety route.
            if route not in ('clarify','manual_review'): route = advice.route
        except Exception as exc:
            flags.append('llm_unavailable_or_invalid'); missing.append('valid model recommendation')
            reason = 'Model inference failed safely (' + type(exc).__name__ + '); no approval inferred.'
            route = 'manual_review'
    elif mode != 'offline': raise ValueError('COPILOT_MODE must be offline or live')
    import json
    evidence.append({'id':'model_advice','source':'model_advice','finding':{'mode':mode,'code_route':code_route,'final_route':route,'route_locked_by_code':code_route in ('clarify','manual_review'), 'advice':advice.model_dump() if advice else None},'reference':'src/model.py + src/solution.py'})
    label = {'clarify':'Request clarification', 'manual_review':'Hold for manual review',
             'reuse_review':'Review existing tool before new purchase', 'approval_review':'Route for human approval'}[route]
    next_step = ('Ask requester to supply: ' + ', '.join(controls['requester_missing'] or missing) + '. Then rerun checks.' if route == 'clarify' else
                 'Human reviewer must examine evidence, confirm business need and seat availability, and collect: ' + ', '.join(controls['required_approvals']) + '. Do not purchase or override controls.')
    import json
    return ProcurementDecision(request_id=str(req.get('request_id','CUSTOM')), recommendation=label + '. ' + reason,
        evidence=[EvidenceItem(source=e['source'], finding=json.dumps(e['finding'],default=str), reference=e['reference']) for e in evidence],
        required_approvals=controls['required_approvals'], missing_information=missing, risk_flags=flags,
        next_step=next_step, human_review_required=True,
        telemetry=RunTelemetry(llm_calls=calls, tool_calls=len(tools.calls), tool_names=tools.calls))

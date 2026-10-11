"""Shreyansh Arora | 24bcs10252. Two advisory workflows, same controls."""
import json
import os
from dotenv import load_dotenv
from src.contracts import Architecture, ProcurementDecision, EvidenceItem, RunTelemetry
from src import data_access as db
from src.tools import Tools
from src.model import infer, infer_anthropic_agentic, provider_key_name
load_dotenv(db.ROOT / '.env', override=False)

# Flags that always force a human manual review, whatever the model suggests.
MANUAL_REVIEW_FLAGS = (
    'budget_insufficient', 'budget_unverified',
    'vendor_review_expired', 'vendor_review_date_invalid', 'conflicting_vendor_evidence',
    'vendor_risk_unavailable', 'security_review_required', 'privacy_review_required',
    'legal_review_required', 'prompt_injection_detected', 'tool_input_mismatch',
)

MANDATORY_TOOLS = ('budget_lookup', 'catalog_lookup', 'vendor_risk_lookup', 'policy_lookup')


def handle_request(request_id: str, architecture: Architecture = 'single') -> ProcurementDecision:
    return analyze_request(db.get_request(request_id), architecture)


def analyze_request(req: dict, architecture: Architecture = 'single') -> ProcurementDecision:
    if architecture not in ('single', 'staged'):
        raise ValueError('Unknown architecture')
    tools = Tools()
    mode = os.getenv('COPILOT_MODE', 'offline').lower()
    if mode not in ('offline', 'live'):
        raise ValueError('COPILOT_MODE must be offline or live')
    provider = os.getenv('MODEL_PROVIDER', 'anthropic')
    agentic = mode == 'live' and provider_key_name() == 'FDE3_ANTHROPIC_API_KEY'

    # In the Anthropic live path the model drives the four retrieval tools itself; the executor
    # records which tools it actually called. Every other path is code-orchestrated.
    model_tool_calls = []
    model_tool_inputs = []
    tool_input_mismatches = []

    def execute_tool(name, inputs):
        # Tool inputs are pinned to the request's own identifiers: the model chooses WHICH tools to
        # call, never WHICH employee, vendor or product they run against. A contradicting model
        # input is recorded and fails closed to manual review via the tool_input_mismatch flag.
        inputs = dict(inputs or {})
        model_tool_calls.append(name)
        if name == 'budget_lookup':
            pinned = {'requester_id': req.get('requester_id')}
            result = tools.budget(str(pinned['requester_id']))
        elif name == 'catalog_lookup':
            pinned = {key: inputs.get(key) or req.get(key) for key in ('category', 'vendor_name', 'product_name')}
            pinned = {key: req.get(key) or pinned.get(key) for key in pinned}
            result = tools.catalog(pinned)
        elif name == 'vendor_risk_lookup':
            pinned = {'vendor_name': inputs.get('vendor_name') or req.get('vendor_name')}
            if req.get('vendor_name'):
                pinned = {'vendor_name': req.get('vendor_name')}
            result = tools.vendor(str(pinned['vendor_name']))
        elif name == 'policy_lookup':
            pinned = {}
            result = tools.policy()
        else:
            raise ValueError('Unknown tool: ' + str(name))
        mismatch = {key: [inputs.get(key), value] for key, value in pinned.items()
                    if inputs.get(key) not in (None, '')
                    and str(inputs.get(key)).strip().lower() != str(value).strip().lower()}
        model_tool_inputs.append({'tool': name, 'model_input': inputs, 'used_input': pinned,
                                  'input_mismatch': mismatch or None})
        if mismatch:
            tool_input_mismatches.append({'tool': name, 'mismatch': mismatch})
        return result

    advice = None
    calls = 0
    failure = None
    if agentic:
        role = 'Procurement Agent' if architecture == 'single' else 'Procurement Analyst'
        try:
            if not os.getenv(provider_key_name()):
                raise RuntimeError('No provider key')
            agentic_counter = [0]
            try:
                advice, made_calls, retrieved = infer_anthropic_agentic(req, role, execute_tool, call_counter=agentic_counter)
                calls += made_calls
            except Exception as exc:
                calls += agentic_counter[0]  # partial API calls still count toward telemetry
                failure = exc
        except Exception as exc:
            failure = exc

    # Mandatory completion: code runs any tool the model skipped (and every tool in the
    # code-orchestrated paths), then the deterministic controls always run on full evidence.
    code_completed_tools = []
    if 'budget_lookup' not in tools.calls:
        tools.budget(req.get('requester_id'))
        code_completed_tools.append('budget_lookup')
    if 'catalog_lookup' not in tools.calls:
        tools.catalog(req)
        code_completed_tools.append('catalog_lookup')
    if 'vendor_risk_lookup' not in tools.calls:
        tools.vendor(req.get('vendor_name'))
        code_completed_tools.append('vendor_risk_lookup')
    if 'policy_lookup' not in tools.calls:
        tools.policy()
        code_completed_tools.append('policy_lookup')
    pack = {'budget': tools.budget(req.get('requester_id')), 'catalog': tools.catalog(req),
            'vendor': tools.vendor(req.get('vendor_name')), 'policy': tools.policy()}
    controls = tools.rules(req, pack)
    retrieval = 'model_driven_tool_calling' if agentic else ('code_orchestrated_live' if mode == 'live' else 'code_orchestrated_offline')

    evidence = [{'id': key, 'source': key, 'finding': value, 'reference': reference} for key, value, reference in (
        ('request', req, str(req.get('request_id', 'custom'))),
        ('budget', pack['budget'], 'data/department_budgets.csv + data/employees.csv'),
        ('catalog', pack['catalog'], 'data/software_catalog.csv'),
        ('vendor', pack['vendor'], 'data/vendors.csv + GET /vendor-risk/{vendor_name} + data/purchase_history.csv'),
        ('policy', pack['policy'], 'data/procurement_policy.md sections 1-11'),
        ('controls', controls, 'src/tools.py:rules'))]
    model_pack = {'request': req, 'evidence': evidence, 'controls': controls}

    flags = list(controls['risk_flags'])
    missing = list(controls['missing_information'])
    if tool_input_mismatches:
        flags.append('tool_input_mismatch')
    if controls['requester_missing']:
        route = 'clarify'
    elif missing or any(f in flags for f in MANUAL_REVIEW_FLAGS):
        route = 'manual_review'
    elif any(r['match_type'] != 'same_vendor_related' or r['same_category'] for r in pack['catalog']):
        route = 'reuse_review'
    else:
        route = 'approval_review'
    code_route = route
    reason = 'Offline rule preview. Semantic need/gap interpretation has not been model-verified.'

    if mode == 'live':
        try:
            if failure is not None:
                raise failure
            if not os.getenv(provider_key_name()):
                raise RuntimeError('No provider key')
            if not agentic:
                calls += 1
                advice = infer(model_pack, 'Procurement Agent' if architecture == 'single' else 'Procurement Analyst')
            if architecture == 'staged':
                analyst_advice = advice
                calls += 1
                advice = infer({**model_pack, 'analyst': advice.model_dump()},
                               'Policy/Risk Reviewer: check the analyst against the same structured evidence pack; do not re-fetch tools')
                if getattr(analyst_advice, 'injection_suspected', False) and not getattr(advice, 'injection_suspected', False):
                    # The reviewer's advice replaces the analyst's; keep the analyst's suspicion alive.
                    advice = advice.model_copy(update={
                        'injection_suspected': True,
                        'reason': ('Analyst suspected injected instructions: ' + analyst_advice.reason
                                   + ' Reviewer: ' + advice.reason)[:700]})
            injection_reported = getattr(advice, 'injection_suspected', False)
            if injection_reported:
                if 'prompt_injection_detected' not in flags:
                    flags.append('prompt_injection_detected')
                if route not in ('clarify', 'manual_review'):
                    route = 'manual_review'
            if advice.route == 'reuse_review' and not pack['catalog']:
                raise ValueError('Reuse without catalog evidence')
            if advice.route == 'clarify' and not missing:
                if not advice.gap_reason.strip():
                    raise ValueError('Clarify without an ask')
                missing.append('Model-identified: ' + advice.gap_reason)
            reason = ('Model suggested ' + advice.route + ': ' + advice.reason + ' Code requires ' + code_route + '.'
                      ) if code_route in ('clarify', 'manual_review') else advice.reason
            if injection_reported:
                reason = ('Model also reported suspected injected instructions. ' if route == 'clarify' else
                          'Model reported suspected injected instructions; held for human review. ') + reason
            # Model can refine overlap/need but cannot downgrade a material safety route.
            if route not in ('clarify', 'manual_review'):
                route = advice.route
        except Exception as exc:
            flags.append('llm_unavailable_or_invalid')
            missing.append('valid model recommendation')
            reason = 'Model inference failed safely (' + type(exc).__name__ + '); no approval inferred.'
            route = 'manual_review'

    evidence.append({'id': 'model_advice', 'source': 'model_advice', 'finding': {
        'mode': mode, 'provider': provider,
        'model': os.getenv('MODEL_NAME', 'claude-sonnet-5-5' if provider == 'anthropic' else 'gemini-2.5-flash'),
        'retrieval': retrieval,
        'model_tool_calls': model_tool_calls,
        'model_tool_inputs': model_tool_inputs,
        'tool_input_mismatches': tool_input_mismatches,
        'code_completed_tools': code_completed_tools,
        'code_route': code_route, 'final_route': route,
        'route_locked_by_code': code_route in ('clarify', 'manual_review'),
        'advice': advice.model_dump() if advice else None},
        'reference': 'src/model.py + src/solution.py'})
    label = {'clarify': 'Request clarification from the requester, then route the answered request to human review',
             'manual_review': 'Hold for manual review',
             'reuse_review': 'Review existing tool before new purchase', 'approval_review': 'Route for human approval'}[route]
    next_step = ('Ask requester to supply: ' + ', '.join(controls['requester_missing'] or missing) + '. Then rerun checks.' if route == 'clarify' else
                 'Human reviewer must examine evidence, confirm business need and seat availability, and collect: ' + ', '.join(controls['required_approvals']) + '. Do not purchase or override controls.')
    return ProcurementDecision(request_id=str(req.get('request_id', 'CUSTOM')), recommendation=label + '. ' + reason,
        evidence=[EvidenceItem(source=e['source'], finding=json.dumps(e['finding'], default=str), reference=e['reference']) for e in evidence],
        required_approvals=controls['required_approvals'], missing_information=missing, risk_flags=flags,
        next_step=next_step, human_review_required=True,
        telemetry=RunTelemetry(llm_calls=calls, tool_calls=len(tools.calls), tool_names=tools.calls))

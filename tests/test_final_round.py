"""Final remediation round: business-purpose routing rule (prompt-level, Policy section 1) and a clean
single-instruction recommendation on the clarify route."""
from unittest.mock import patch

from src.model import SYSTEM
from src.solution import analyze_request
from tests.test_agentic_tools import get_request, live_env
from tests.test_wave4_fixes import _Resp
from tests.test_wave5_fixes import _rounds_submit


def test_system_prompt_routes_missing_business_purpose_to_clarify():
    text = ' '.join(SYSTEM.split())
    assert 'Policy section 1 requires a business purpose' in text
    assert 'states no business purpose' in text and 'route to clarify' in text


def test_clarify_with_injection_is_one_instruction():
    # REQ-1006 is missing required fields (code route clarify, locked) and carries an injection.
    rounds = _rounds_submit({'route': 'clarify', 'reason': 'cost, users and data access are missing',
                             'evidence_ids': ['request'], 'gap_reason': 'supply cost, users and data access',
                             'injection_suspected': True})
    state = {'r': 0}

    def api(url, headers=None, json=None, timeout=None):
        resp = _Resp(rounds[min(state['r'], len(rounds) - 1)])
        state['r'] += 1
        return resp
    with live_env(), patch('httpx.post', api), patch('src.tools.get_vendor_risk', return_value={'security_review_status': 'approved', 'last_review_date': '2026-06-20'}):
        d = analyze_request(get_request('REQ-1006'), 'single')
    assert d.recommendation.startswith('Request clarification from the requester, then route the answered request to human review.')
    assert 'held for human review' not in d.recommendation
    assert 'prompt_injection_detected' in d.risk_flags

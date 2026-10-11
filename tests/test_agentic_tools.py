# Shreyansh Arora | 24bcs10252. Model-driven tool calling (Anthropic live path).
import json
import os
import pytest
from unittest.mock import patch
from src.solution import analyze_request
from src.data_access import get_request
import src.model as m

APPROVED_VENDOR = {'security_review_status': 'approved', 'last_review_date': '2026-06-20', 'stores_data_outside_region': False}


def tool_use(name, inputs, uid):
    return {'type': 'tool_use', 'id': uid, 'name': name, 'input': inputs}


def submit(route='approval_review', ids=('budget', 'catalog', 'vendor', 'policy')):
    return tool_use('submit_advice', {'route': route, 'reason': 'Grounded in retrieved evidence.',
                                      'evidence_ids': list(ids), 'gap_reason': ''}, 'sub1')


class FakeAPI:
    """Scripted Anthropic responses; asserts request shape."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.bodies = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        assert url == 'https://api.anthropic.com/v1/messages'
        self.bodies.append(json)
        content = self.turns.pop(0)
        stop = 'tool_use' if any(b.get('type') == 'tool_use' for b in content) else 'end_turn'
        return type('R', (), {'raise_for_status': lambda self: None,
                              'json': lambda self: {'stop_reason': stop, 'content': content}})()


def live_env():
    return patch.dict(os.environ, {'COPILOT_MODE': 'live', 'MODEL_PROVIDER': 'anthropic',
                                   'FDE3_ANTHROPIC_API_KEY': 'fake', 'MODEL_NAME': 'claude-sonnet-5-5'})


def model_advice(decision):
    return json.loads(next(e.finding for e in decision.evidence if e.source == 'model_advice'))


def test_model_calls_all_four_tools_itself():
    api = FakeAPI([
        [tool_use('budget_lookup', {'requester_id': 'E004'}, 't1'), tool_use('catalog_lookup', {}, 't2'),
         tool_use('vendor_risk_lookup', {'vendor_name': 'SignFlow'}, 't3'), tool_use('policy_lookup', {}, 't4')],
        [submit('approval_review')],
    ])
    with live_env(), patch('httpx.post', api), patch('src.tools.get_vendor_risk', return_value=APPROVED_VENDOR):
        d = analyze_request(get_request('REQ-1010'), 'single')
    meta = model_advice(d)
    assert meta['retrieval'] == 'model_driven_tool_calling'
    assert sorted(meta['model_tool_calls']) == ['budget_lookup', 'catalog_lookup', 'policy_lookup', 'vendor_risk_lookup']
    assert meta['code_completed_tools'] == []
    assert d.telemetry.llm_calls == 2 and d.telemetry.tool_calls == 5  # 4 retrieval + deterministic check
    assert d.recommendation.startswith('Route for human approval')
    # tools were offered, and no forced choice on round 1
    assert 'tool_choice' not in api.bodies[0]
    assert {t['name'] for t in api.bodies[0]['tools']} == {'budget_lookup', 'catalog_lookup', 'vendor_risk_lookup', 'policy_lookup', 'submit_advice'}


def test_code_completes_skipped_tools():
    api = FakeAPI([
        [tool_use('budget_lookup', {'requester_id': 'E004'}, 't1')],
        [submit('approval_review', ids=('budget',))],
    ])
    with live_env(), patch('httpx.post', api), patch('src.tools.get_vendor_risk', return_value=APPROVED_VENDOR):
        d = analyze_request(get_request('REQ-1010'), 'single')
    meta = model_advice(d)
    assert sorted(meta['code_completed_tools']) == ['catalog_lookup', 'policy_lookup', 'vendor_risk_lookup']
    assert d.telemetry.tool_calls == 5  # full evidence + deterministic check
    assert d.evidence  # evidence panel complete


def test_route_lock_overrides_model_under_escalation():
    api = FakeAPI([
        [tool_use('budget_lookup', {'requester_id': 'E003'}, 't1'), tool_use('policy_lookup', {}, 't2')],
        [submit('approval_review', ids=('budget', 'policy'))],
    ])
    with live_env(), patch('httpx.post', api):
        d = analyze_request(get_request('REQ-1005'), 'single')  # PII + over budget
    meta = model_advice(d)
    assert meta['advice']['route'] == 'approval_review'
    assert meta['final_route'] == 'manual_review' and meta['route_locked_by_code']
    assert d.recommendation.startswith('Hold for manual review')
    assert {'Finance', 'Privacy', 'Security'} <= set(d.required_approvals)


def test_ungrounded_evidence_rejected_fail_safe():
    api = FakeAPI([
        [tool_use('budget_lookup', {'requester_id': 'E004'}, 't1')],
        [submit('approval_review', ids=('budget', 'mars_server'))],
    ])
    with live_env(), patch('httpx.post', api), patch('src.tools.get_vendor_risk', return_value=APPROVED_VENDOR):
        d = analyze_request(get_request('REQ-1010'), 'single')
    assert 'llm_unavailable_or_invalid' in d.risk_flags
    assert d.recommendation.startswith('Hold for manual review')


def test_forced_submit_on_last_round():
    api = FakeAPI([
        [tool_use('policy_lookup', {}, 't1')],
        [{'type': 'text', 'text': 'I have enough evidence now.'}],
        [tool_use('catalog_lookup', {}, 't2')],
        [submit('approval_review', ids=('policy', 'catalog'))],
    ])
    with live_env(), patch('httpx.post', api), patch('src.tools.get_vendor_risk', return_value=APPROVED_VENDOR):
        d = analyze_request(get_request('REQ-1010'), 'single')
    # Forced tool_choice is rejected by the API while thinking is enabled; the last round asks in text.
    assert 'tool_choice' not in api.bodies[-1]
    last_user = [msg for msg in api.bodies[-1]['messages'] if msg['role'] == 'user'][-1]['content']
    assert any(b.get('type') == 'text' and 'Final round' in b.get('text', '') for b in last_user)
    assert 'llm_unavailable_or_invalid' not in d.risk_flags


def test_never_submitting_is_fail_safe():
    api = FakeAPI([[{'type': 'text', 'text': 'thinking out loud'}]] * 4)
    # last-round forced submit returns prose -> no tool_use at all
    api.turns[-1] = [{'type': 'text', 'text': 'still no tool'}]
    with live_env(), patch('httpx.post', api), patch('src.tools.get_vendor_risk', return_value=APPROVED_VENDOR):
        d = analyze_request(get_request('REQ-1010'), 'single')
    assert 'llm_unavailable_or_invalid' in d.risk_flags
    assert d.recommendation.startswith('Hold for manual review')


def test_staged_analyst_uses_tools_reviewer_does_not():
    api = FakeAPI([
        [tool_use('budget_lookup', {'requester_id': 'E004'}, 't1'), tool_use('catalog_lookup', {}, 't2'),
         tool_use('vendor_risk_lookup', {'vendor_name': 'SignFlow'}, 't3'), tool_use('policy_lookup', {}, 't4')],
        [submit('approval_review')],
        [{'type': 'text', 'text': json.dumps({'route': 'approval_review', 'reason': 'Reviewer agrees with analyst.',
                                              'evidence_ids': ['budget', 'controls'], 'gap_reason': ''})}],
    ])
    with live_env(), patch('httpx.post', api), patch('src.tools.get_vendor_risk', return_value=APPROVED_VENDOR):
        d = analyze_request(get_request('REQ-1010'), 'staged')
    assert d.telemetry.llm_calls == 3
    assert 'tools' not in api.bodies[-1]  # reviewer: single-shot structured call, no tools
    assert 'llm_unavailable_or_invalid' not in d.risk_flags


def test_missing_key_fail_safe_no_calls():
    env = {'COPILOT_MODE': 'live', 'MODEL_PROVIDER': 'anthropic', 'FDE3_ANTHROPIC_API_KEY': ''}
    with patch.dict(os.environ, env), patch('httpx.post') as post, patch('src.tools.get_vendor_risk', return_value=APPROVED_VENDOR):
        d = analyze_request(get_request('REQ-1010'), 'single')
    post.assert_not_called()
    assert 'llm_unavailable_or_invalid' in d.risk_flags
    assert d.telemetry.tool_calls == 5  # code still gathered the full pack + checks

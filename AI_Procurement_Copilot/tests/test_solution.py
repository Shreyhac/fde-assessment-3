import json
# Shreyansh Arora | 24bcs10252
import os
import pytest
from src.solution import analyze_request
from src.data_access import get_request
from src.tools import rules, Tools
from unittest.mock import patch

@pytest.mark.parametrize('amount,expected',[(0,['Manager']),(1000,['Manager']),(1000.01,['Department Head','Procurement']),(10000,['Department Head','Procurement']),(10000.01,['Department Head','Finance','Procurement']),(25000,['Department Head','Finance','Procurement']),(25000.01,['Department Head','Finance','CFO','Procurement'])])
def test_thresholds(amount,expected):
    req=get_request('REQ-1010'); req['annual_cost_usd']=amount
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-20'}):
        decision=analyze_request(req)
    assert decision.required_approvals==expected

@pytest.mark.parametrize('amount',[None,-1,float('nan'),float('inf'),'nope'])
def test_invalid_amount(amount):
    req=get_request('REQ-1010'); req['annual_cost_usd']=amount
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-20'}): decision=analyze_request(req)
    assert 'annual cost' in decision.missing_information
    assert 'Manager' not in decision.required_approvals

@pytest.mark.parametrize('arch',['single','staged'])
def test_api_failure(arch):
    with patch('src.tools.get_vendor_risk',side_effect=TimeoutError): decision=analyze_request(get_request('REQ-1001'),arch)
    assert 'vendor_risk_unavailable' in decision.risk_flags
    assert 'Security' in decision.required_approvals
    assert decision.human_review_required


def test_tool_reuse():
    tools=Tools(); tools.budget('E001'); tools.budget('E001')
    assert tools.calls==['budget_lookup']


def test_model_failure():
    with patch.dict(os.environ,{'COPILOT_MODE':'live','GEMINI_API_KEY':'placeholder'}),patch('src.solution.infer',side_effect=ValueError),patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-20'}):
        d=analyze_request(get_request('REQ-1010'))
    assert 'llm_unavailable_or_invalid' in d.risk_flags
    assert d.telemetry.llm_calls==1 and d.human_review_required


def test_injection_no_approval():
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-03-02'}): d=analyze_request(get_request('REQ-1006'))
    assert 'prompt_injection_detected' in d.risk_flags
    assert d.human_review_required and 'CFO' not in d.required_approvals


def test_model_cannot_remove_controls():
    from src.model import Advice
    with patch.dict(os.environ,{'COPILOT_MODE':'live','GEMINI_API_KEY':'placeholder'}),patch('src.solution.infer',return_value=Advice(route='approval_review',reason='Test only',evidence_ids=['budget'])),patch('src.tools.get_vendor_risk',return_value={'security_review_status':'not_completed','last_review_date':None,'stores_data_outside_region':False}):
        d=analyze_request(get_request('REQ-1005'),'staged')
    assert 'Finance' in d.required_approvals and 'Privacy' in d.required_approvals
    assert d.recommendation.startswith('Hold for manual review') and d.telemetry.llm_calls==2

@pytest.mark.parametrize('access',['unknown','top_secret_new_class',''])
def test_unknown_data_class_fails_closed(access):
    req=get_request('REQ-1010');req['data_access_level']=access
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-20'}): d=analyze_request(req)
    assert any('data access' in x for x in d.missing_information)
    assert 'Security' in d.required_approvals


def test_pending_equivalent_not_conflict():
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'not_completed','last_review_date':None,'stores_data_outside_region':False}):d=analyze_request(get_request('REQ-1002'))
    assert 'conflicting_vendor_evidence' not in d.risk_flags


def test_residency_unavailable_not_favorable():
    with patch('src.tools.get_vendor_risk',side_effect=TimeoutError):d=analyze_request(get_request('REQ-1009'))
    assert 'Privacy' in d.required_approvals and 'data residency unverified' in d.missing_information


def test_unknown_identity_clarifies():
    req=get_request('REQ-1010');req['requester_id']='E999'
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-20','stores_data_outside_region':False}):d=analyze_request(req)
    assert d.recommendation.startswith('Request clarification') and 'requester and department identity' in d.missing_information


def test_training_not_duplicate():
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-20','stores_data_outside_region':False}):d=analyze_request(get_request('REQ-1010'))
    assert d.recommendation.startswith('Route for human approval')


def test_api_gap_manual_not_requester():
    with patch('src.tools.get_vendor_risk',side_effect=TimeoutError):d=analyze_request(get_request('REQ-1009'))
    assert d.recommendation.startswith('Hold for manual review')
    assert not d.next_step.startswith('Ask requester')


def test_existing_tracker_reuse():
    with patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-03','stores_data_outside_region':False}):d=analyze_request(get_request('REQ-1008'))
    assert d.recommendation.startswith('Review existing tool')

@pytest.mark.parametrize('route,gap',[('clarify',''),('reuse_review','')])
def test_invalid_advice_guard(route,gap):
    from src.model import Advice
    req=get_request('REQ-1010');req['vendor_name']='Independent Training';req['category']='Training'
    with patch.dict(os.environ,{'COPILOT_MODE':'live','GEMINI_API_KEY':'placeholder'}),patch('src.solution.infer',return_value=Advice(route=route,reason='Test',evidence_ids=['policy'],gap_reason=gap)),patch('src.tools.get_vendor_risk',return_value={'security_review_status':'approved','last_review_date':'2026-06-20','stores_data_outside_region':False}):d=analyze_request(req)
    assert 'llm_unavailable_or_invalid' in d.risk_flags


def test_forced_tool_output_parsing():
    from unittest.mock import MagicMock
    from src.model import infer
    def resp(ids):
        m=MagicMock(); m.json.return_value={'candidates':[{'content':{'parts':[{'text':json.dumps({'route':'approval_review','reason':'test','evidence_ids':ids,'gap_reason':''})}]}}]}; return m
    with patch.dict(os.environ,{'GEMINI_API_KEY':'placeholder'}),patch('httpx.post') as post:
        post.return_value=resp(['policy'])
        assert infer({'evidence':[{'id':'policy'}]},'test').route=='approval_review'
        post.return_value=resp(['fabricated'])
        with pytest.raises(ValueError):infer({'evidence':[{'id':'policy'}]},'test')

"""Regression: Anthropic output-length contract (descriptions + prompt; no unsupported raw-schema constraints; overlength still rejected)."""
import json
import pytest
from pydantic import ValidationError
import src.model as m

class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p

def _call(monkeypatch, reason, gap=''):
    seen = {}
    def fake_post(url, headers=None, json=None, timeout=None):
        seen['body'] = json
        text = __import__('json').dumps({'route': 'manual_review', 'reason': reason, 'evidence_ids': ['policy'], 'gap_reason': gap})
        return _Resp({'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': text}]})
    monkeypatch.setenv('MODEL_PROVIDER', 'anthropic'); monkeypatch.setenv('FDE3_ANTHROPIC_API_KEY', 'dummy-test-value')
    monkeypatch.setattr('httpx.post', fake_post)
    return seen, (lambda: m.infer_anthropic({'evidence': [{'id': 'policy'}]}, 'test'))

def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values(): yield from _walk(v)
    elif isinstance(node, list):
        for v in node: yield from _walk(v)

def test_schema_descriptions_state_limits_and_no_unsupported_constraints(monkeypatch):
    seen, run = _call(monkeypatch, 'ok')
    run()
    schema = seen['body']['output_config']['format']['schema']
    props = schema['properties']
    assert '700' in props['reason']['description'] and '500' in props['reason']['description']
    assert '400' in props['gap_reason']['description'] and '250' in props['gap_reason']['description']
    for node in _walk(schema):
        assert 'maxLength' not in node and 'minLength' not in node

def test_system_prompt_states_length_limits():
    for token in ('500', '700', '250', '400', 'reason', 'gap_reason'):
        assert token in m.SYSTEM

def test_advice_limits_not_relaxed():
    assert any(getattr(x, 'max_length', None) == 700 for x in m.Advice.model_fields['reason'].metadata)
    assert any(getattr(x, 'max_length', None) == 400 for x in m.Advice.model_fields['gap_reason'].metadata)

def test_limit_lengths_accepted(monkeypatch):
    _, run = _call(monkeypatch, 'r' * 700, 'g' * 400)
    a = run(); assert len(a.reason) == 700 and len(a.gap_reason) == 400   # not truncated

@pytest.mark.parametrize('reason,gap', [('r' * 701, ''), ('r' * 1040, ''), ('ok', 'g' * 401)])
def test_overlength_rejected_not_truncated(monkeypatch, reason, gap):
    _, run = _call(monkeypatch, reason, gap)
    with pytest.raises(ValidationError): run()

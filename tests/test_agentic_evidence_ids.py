"""Regression: agentic Anthropic path must tell the model the evidence-ID vocabulary, never force
tool_choice while thinking is enabled, and still reject ungrounded citations."""
import json
import pytest
import src.model as m


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


def _run(monkeypatch, script):
    """script: list of assistant content lists, one per round."""
    bodies = []
    def fake_post(url, headers=None, json=None, timeout=None):
        bodies.append(__import__('copy').deepcopy(json))
        content = script[min(len(bodies) - 1, len(script) - 1)]
        stop = 'tool_use' if any(b['type'] == 'tool_use' for b in content) else 'end_turn'
        return _Resp({'stop_reason': stop, 'content': content})
    monkeypatch.setenv('FDE3_ANTHROPIC_API_KEY', 'dummy-test-value')
    monkeypatch.setattr('httpx.post', fake_post)
    return bodies, (lambda: m.infer_anthropic_agentic({'request_id': 'R'}, 'test', lambda name, inputs: {'ok': name}))


def _use(i, name, inp): return {'type': 'tool_use', 'id': f't{i}', 'name': name, 'input': inp}
def _submit(i, ids): return _use(i, 'submit_advice', {'route': 'manual_review', 'reason': 'ok', 'evidence_ids': ids, 'gap_reason': ''})


def test_submit_schema_lists_evidence_ids_and_shared_schema_unchanged():
    items = m.SUBMIT_TOOL['input_schema']['properties']['evidence_ids']['items']
    assert items['enum'] == ['request', 'budget', 'catalog', 'vendor', 'policy']
    assert 'enum' not in m.ADVICE_SCHEMA['properties']['evidence_ids']['items']


def test_tool_results_labelled_and_valid_citation_accepted(monkeypatch):
    bodies, run = _run(monkeypatch, [[_use(1, 'budget_lookup', {'requester_id': 'E1'})], [_submit(2, ['request', 'budget'])]])
    advice, calls, retrieved = run()
    assert calls == 2 and retrieved == ['budget'] and advice.route == 'manual_review'
    result_block = bodies[1]['messages'][-1]['content'][0]
    assert json.loads(result_block['content'])['evidence_id'] == 'budget'


def test_ungrounded_citation_still_rejected(monkeypatch):
    _, run = _run(monkeypatch, [[_use(1, 'budget_lookup', {})], [_submit(2, ['catalog'])]])
    with pytest.raises(ValueError, match='Ungrounded'):
        run()


def test_no_forced_tool_choice_with_thinking_and_final_round_prompt(monkeypatch):
    bodies, run = _run(monkeypatch, [[_use(1, 'policy_lookup', {})]])
    with pytest.raises(ValueError, match='never submitted'):
        run()
    assert len(bodies) == 4
    for body in bodies:
        assert 'tool_choice' not in body and body['thinking'] == {'type': 'adaptive'}
    last_user = bodies[3]['messages'][-1]['content']
    assert any(b.get('type') == 'text' and 'Final round' in b['text'] for b in last_user)

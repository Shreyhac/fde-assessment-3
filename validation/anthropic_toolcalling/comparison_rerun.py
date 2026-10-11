"""Comparison-set rerun (live, checkpointed): the 10 comparison cases (REQ-1001..REQ-1010), both architectures,
one repeat each, with the current prompt. Row fields and route expectations are the same as checkpoint_runner.py
(expected routes from evals/run_comparison.py). Each row also records the archived comparison final routes
(checkpoint/decisions, 3 repeats per architecture) and whether the new final route matches them.
usage: comparison_rerun.py <ckpt_dir>   (run under callmeter_anthropic.py from the repo root)
The wave label (decision "source" and summary file name) comes from the checkpoint's parent directory,
e.g. .../wave7/checkpoint -> anthropic_live_wave7 and summary_wave7.json."""
import ast, json, os, sys, time
ROOT = os.getcwd(); sys.path.insert(0, ROOT)
import src.solution as sol
from evals.run_public_evals import evaluate

ck = sys.argv[1]; os.makedirs(f'{ck}/decisions', exist_ok=True)
wave = os.path.basename(os.path.dirname(os.path.abspath(ck)))
pub = json.load(open(f'{ROOT}/evals/public_cases.json'))
ext = expected = None
for n in ast.walk(ast.parse(open(f'{ROOT}/evals/run_comparison.py').read())):
    if isinstance(n, ast.AugAssign) and getattr(n.target, 'id', '') == 'cases': ext = ast.literal_eval(n.value)
    if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'expected': expected = ast.literal_eval(n.value)
comp = pub + ext
archive_dir = f'{ROOT}/validation/anthropic_toolcalling/checkpoint/decisions'
archived = {}
for f in sorted(os.listdir(archive_dir)):
    x = json.load(open(f'{archive_dir}/{f}'))
    if x['key'].startswith('comparison|'):
        _, a, cid, _ = x['key'].split('|'); archived.setdefault((a, cid), []).append(x['row']['final_route'])
key = lambda a, cid: f'comparison|{a}|{cid}|0'
def path(k): return f"{ck}/decisions/{k.replace('|', '__')}.json"

for arch in ('single', 'staged'):
    for case in comp:
        k = key(arch, case['case_id'])
        if os.path.exists(path(k)):
            print('[ckpt]', k, 'banked'); continue
        t0 = time.perf_counter(); d = sol.handle_request(case['request_id'], arch); ms = (time.perf_counter() - t0) * 1000
        failures = evaluate(d, case['expectations'])
        ai = json.loads(next(e.finding for e in d.evidence if e.source == 'model_advice'))
        ctrl = json.loads(next(e.finding for e in d.evidence if e.source == 'controls'))
        prior = archived[(arch, case['case_id'])]
        row = {'architecture': arch, 'case_id': case['case_id'], 'request_id': case['request_id'],
               'correctness_minimum': not failures and 'llm_unavailable_or_invalid' not in d.risk_flags,
               'grounded_source_refs': all(e.reference and e.source in ('request', 'budget', 'catalog', 'vendor', 'policy', 'controls', 'model_advice') for e in d.evidence),
               'deterministic_rule_following': set(ctrl['required_approvals']).issubset(d.required_approvals) and set(ctrl['risk_flags']).issubset(d.risk_flags),
               'expected_route': expected[case['request_id']], 'route_match': ai['final_route'] == expected[case['request_id']],
               'model_route': ai['advice']['route'] if ai['advice'] else '', 'final_route': ai['final_route'],
               'route_locked_by_code': ai['route_locked_by_code'], 'archived_final_routes': prior,
               'matches_archived': all(r == ai['final_route'] for r in prior),
               'injection_suspected': bool(ai['advice'] and ai['advice'].get('injection_suspected')),
               'human_escalation': d.human_review_required, 'latency_ms': round(ms, 1),
               'llm_calls': d.telemetry.llm_calls, 'tool_calls': d.telemetry.tool_calls, 'failures': ' | '.join(failures)}
        tmp = path(k) + '.tmp'
        json.dump({'key': k, 'source': f'anthropic_live_{wave}', 'row': row, 'decision': d.model_dump()}, open(tmp, 'w'), indent=1, default=str)
        os.replace(tmp, path(k))
        print('[ckpt]', k, row['final_route'], 'model', row['model_route'], 'archived-match' if row['matches_archived'] else 'ARCHIVED-DIFF',
              'injection' if row['injection_suspected'] else '', flush=True)
recs = [json.load(open(f'{ck}/decisions/{f}')) for f in sorted(os.listdir(f'{ck}/decisions')) if f.endswith('.json')]
rows = [r['row'] for r in recs]
summ = {a: {m: sum(r[m] for r in rows if r['architecture'] == a) for m in
            ('correctness_minimum', 'grounded_source_refs', 'deterministic_rule_following', 'route_match', 'matches_archived',
             'route_locked_by_code', 'injection_suspected', 'human_escalation', 'llm_calls', 'tool_calls')}
        | {'runs': sum(r['architecture'] == a for r in rows)} for a in ('single', 'staged')}
json.dump({'wave': wave, 'cases': len(rows), 'per_architecture': summ, 'rows': rows}, open(f'{ck}/summary_{wave}.json', 'w'), indent=1, default=str)
print(f'[ckpt] {wave}: ' + '; '.join(f"{a} route_match {s['route_match']}/{s['runs']} matches_archived {s['matches_archived']}/{s['runs']}"
                                   for a, s in summ.items()), flush=True)

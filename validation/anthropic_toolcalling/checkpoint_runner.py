"""Checkpointed live evaluation harness (guarded, resumable).
Reuses the documented semantics: cases from evals/public_cases.json; comparison extra cases + expected routes parsed
(ast.literal_eval) from evals/run_comparison.py; evaluate() from evals/run_public_evals.py; row fields copied from
run_comparison. Each valid decision is saved atomically (temp + os.replace) keyed phase/arch/case/repeat BEFORE the
next case starts. Banked keys are skipped. Run under callmeter_guarded_v6 (it wraps src.solution.handle_request).
usage: checkpoint_runner.py <ckpt_dir> [--seed attempt10_decisions.jsonl]"""
import ast, csv, json, math, os, statistics, sys, time
ROOT = os.getcwd(); sys.path.insert(0, ROOT)
import src.solution as sol
from src.contracts import ProcurementDecision
from evals.run_public_evals import evaluate
ck = sys.argv[1]; os.makedirs(f'{ck}/decisions', exist_ok=True)
pub = json.load(open(f'{ROOT}/evals/public_cases.json'))
tree = ast.parse(open(f'{ROOT}/evals/run_comparison.py').read())
ext = expected = None
for n in ast.walk(tree):
    if isinstance(n, ast.AugAssign) and getattr(n.target, 'id', '') == 'cases': ext = ast.literal_eval(n.value)
    if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'expected': expected = ast.literal_eval(n.value)
comp = pub + ext
plan = [('public', a, c, 0) for a in ('single', 'staged') for c in pub] + \
       [('comparison', a, c, r) for a in ('single', 'staged') for r in range(3) for c in comp]
key = lambda p, a, cid, r: f'{p}|{a}|{cid}|{r}'
def path(k): return f"{ck}/decisions/{k.replace('|', '__')}.json"
def save(k, obj):
    tmp = path(k) + '.tmp'; json.dump(obj, open(tmp, 'w'), indent=1, default=str); os.replace(tmp, path(k))
def public_row(case, arch, d, ms):
    f = evaluate(d, case['expectations']); t = d.telemetry
    return {'case_id': case['case_id'], 'request_id': case['request_id'], 'architecture': arch, 'passed_minimum_checks': not f,
            'latency_ms': round(ms, 1), 'llm_calls': t.llm_calls if t else '', 'tool_calls': t.tool_calls if t else '', 'failures': ' | '.join(f)}
def comp_row(case, arch, r, d, ms):
    failures = evaluate(d, case['expectations'])
    grounded = all(e.reference and e.source in ('request','budget','catalog','vendor','policy','controls','model_advice') for e in d.evidence)
    ai = json.loads(next(e.finding for e in d.evidence if e.source == 'model_advice'))
    ctrl = json.loads(next(e.finding for e in d.evidence if e.source == 'controls'))
    rules_ok = set(ctrl['required_approvals']).issubset(d.required_approvals) and set(ctrl['risk_flags']).issubset(d.risk_flags)
    correct = not failures and 'llm_unavailable_or_invalid' not in d.risk_flags
    return {'architecture': arch, 'mode': os.getenv('COPILOT_MODE', 'offline'), 'case_id': case['case_id'], 'repeat': r,
        'correctness_minimum': correct, 'grounded_source_refs': grounded, 'deterministic_rule_following': rules_ok,
        'route_match': ai['final_route'] == expected[case['request_id']], 'expected_route': expected[case['request_id']],
        'model_route': ai['advice']['route'] if ai['advice'] else '', 'final_route': ai['final_route'], 'route_locked_by_code': ai['route_locked_by_code'],
        'gap_reason': ai['advice']['gap_reason'] if ai['advice'] else '', 'human_escalation': d.human_review_required, 'latency_ms': round(ms, 2),
        'llm_calls': d.telemetry.llm_calls, 'tool_calls': d.telemetry.tool_calls, 'failures': ' | '.join(failures)}
def done(): return {json.load(open(f'{ck}/decisions/{f}'))['key'] for f in os.listdir(f'{ck}/decisions') if f.endswith('.json')}
if '--seed' in sys.argv:
    for line in open(sys.argv[sys.argv.index('--seed') + 1]):
        x = json.loads(line); d = ProcurementDecision.model_validate(x['decision'])
        case = next(c for c in pub if c['request_id'] == x['request_id']); k = key('public', x['architecture'], case['case_id'], 0)
        if k not in done(): save(k, {'key': k, 'source': 'attempt10_banked', 'row': public_row(case, x['architecture'], d, x['latency_ms']), 'decision': x['decision']})
def rebuild():
    recs = [json.load(open(f'{ck}/decisions/{f}')) for f in sorted(os.listdir(f'{ck}/decisions')) if f.endswith('.json')]
    order = {key(*p[:2], p[2]['case_id'], p[3]): i for i, p in enumerate(plan)}; recs.sort(key=lambda x: order[x['key']])
    out = {}
    for name, sel in (('public_results_single_live.csv', 'public|single'), ('public_results_staged_live.csv', 'public|staged'), ('comparison_live.csv', 'comparison|')):
        rows = [x['row'] for x in recs if x['key'].startswith(sel)]
        if rows:
            with open(f'{ck}/{name}.tmp', 'w', newline='') as f: w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
            os.replace(f'{ck}/{name}.tmp', f'{ck}/{name}')
    summ = {}
    for arch in ('single', 'staged'):
        rs = [x['row'] for x in recs if x['key'].startswith('comparison|' + arch)]
        if not rs: summ[arch] = {'runs': 0, 'complete': False}; continue
        lat = sorted(r['latency_ms'] for r in rs)
        summ[arch] = {'runs': len(rs), 'planned': 30, 'complete': len(rs) == 30, 'correctness_minimum': sum(r['correctness_minimum'] for r in rs),
            'grounded_source_refs': sum(r['grounded_source_refs'] for r in rs), 'rule_following': sum(r['deterministic_rule_following'] for r in rs),
            'route_matches': sum(r['route_match'] for r in rs), 'code_locked_routes': sum(r['route_locked_by_code'] for r in rs),
            'model_route_differs_from_final': sum(r['model_route'] != r['final_route'] for r in rs), 'human_escalation': sum(r['human_escalation'] for r in rs),
            'median_ms': statistics.median(lat), 'p95_ms': lat[math.ceil(.95 * len(lat)) - 1], 'total_llm_calls': sum(r['llm_calls'] for r in rs), 'total_tool_calls': sum(r['tool_calls'] for r in rs)}
    pubsum = {a: {'done': len([x for x in recs if x['key'].startswith('public|' + a)]), 'planned': 6,
                  'passed': sum(x['row']['passed_minimum_checks'] for x in recs if x['key'].startswith('public|' + a))} for a in ('single', 'staged')}
    json.dump({'mode': os.getenv('COPILOT_MODE'), 'harness': 'checkpointed live-run harness (validation/anthropic_toolcalling)',
               'latency_note': 'latency includes any 503 retry waits', 'decisions_saved': len(recs), 'planned': len(plan), 'public': pubsum,
               'comparison': summ, 'semantic_ai_evaluation_complete': False}, open(f'{ck}/summary_live.json', 'w'), indent=1)
    return len(recs)
have = done(); pending = [p for p in plan if key(p[0], p[1], p[2]['case_id'], p[3]) not in have]
print(f'[ckpt] planned={len(plan)} saved={len(have)} pending={len(pending)}', flush=True); rebuild()
for ph, arch, case, r in pending:
    k = key(ph, arch, case['case_id'], r); t = time.perf_counter()
    d = sol.handle_request(case['request_id'], arch); ms = (time.perf_counter() - t) * 1000
    row = public_row(case, arch, d, ms) if ph == 'public' else comp_row(case, arch, r, d, ms)
    save(k, {'key': k, 'source': 'anthropic_live', 'row': row, 'decision': d.model_dump()})
    n = rebuild(); print(f'[ckpt] saved {k} ({ms:.0f} ms) total={n}/{len(plan)}', flush=True)
print('[ckpt] ALL PLANNED DECISIONS SAVED', flush=True)

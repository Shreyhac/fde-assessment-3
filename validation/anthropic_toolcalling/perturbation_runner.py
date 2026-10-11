"""Perturbation verification runner (live, checkpointed).
Runs a cases file from validation/anthropic_toolcalling/ through analyze_request for both
architectures, one repeat each, saving each decision atomically before the next case.
usage: perturbation_runner.py <ckpt_dir> [cases_file] [CASE-ID,CASE-ID,...]
       (run under callmeter_anthropic.py from the repo root)
The wave label (decision "source" and summary file name) comes from the checkpoint's parent
directory, e.g. .../wave5/checkpoint -> anthropic_live_wave5 and summary_wave5.json.
expect.route may be a single route or a list of routes that are all correct by policy.
A cases file is either a list of cases or {"note": ..., "cases": [...]}.
"""
import json, os, sys, time
ROOT = os.getcwd(); sys.path.insert(0, ROOT)
import src.solution as sol
import src.tools as tools_mod

ck = sys.argv[1]; os.makedirs(f'{ck}/decisions', exist_ok=True)
cases_file = sys.argv[2] if len(sys.argv) > 2 else 'perturbation_cases.json'
cases = json.load(open(f'{ROOT}/validation/anthropic_toolcalling/{cases_file}'))
if isinstance(cases, dict):  # a cases file may carry a top-level note: {"note": ..., "cases": [...]}
    cases = cases['cases']
only = set(sys.argv[3].split(',')) if len(sys.argv) > 3 and sys.argv[3] else None
if only:
    cases = [c for c in cases if c['case_id'] in only]
    assert len(cases) == len(only), 'unknown case id in filter'
wave = os.path.basename(os.path.dirname(os.path.abspath(ck)))
reqs = {r['request_id']: r for r in json.load(open(f'{ROOT}/data/requests.json'))}
key = lambda a, cid: f'perturbation|{a}|{cid}|0'
def path(k): return f"{ck}/decisions/{k.replace('|', '__')}.json"

failures = []
for arch in ('single', 'staged'):
    for case in cases:
        k = key(arch, case['case_id'])
        if os.path.exists(path(k)):
            print('[ckpt]', k, 'banked'); continue
        req = dict(case['request']) if case.get('request') else dict(reqs[case['base']])
        req.update(case.get('overrides') or {})
        original = tools_mod.get_vendor_risk
        if case.get('vendor_override'):
            tools_mod.get_vendor_risk = lambda name, timeout_seconds=None, _o=case["vendor_override"]: _o
        t0 = time.time()
        try:
            d = sol.analyze_request(req, arch)
        finally:
            tools_mod.get_vendor_risk = original
        ms = (time.time() - t0) * 1000
        meta = json.loads(next(e.finding for e in d.evidence if e.source == 'model_advice'))
        exp = case['expect']
        accepted = exp['route'] if isinstance(exp['route'], list) else [exp['route']]
        checks = {
            'route_match': meta['final_route'] in accepted,
            'flags_present': all(f in d.risk_flags for f in exp['flags']),
            'flags_absent': all(f not in d.risk_flags for f in exp['flags_absent']),
            'no_model_failure': 'llm_unavailable_or_invalid' not in d.risk_flags,
        }
        row = {'architecture': arch, 'case_id': case['case_id'], 'note': case.get('note', ''),
               'expected_route': '|'.join(accepted), 'model_route': meta['advice']['route'] if meta['advice'] else '',
               'final_route': meta['final_route'], 'risk_flags': d.risk_flags, 'checks': checks,
               'passed': all(checks.values()), 'latency_ms': round(ms, 1),
               'llm_calls': d.telemetry.llm_calls, 'tool_calls': d.telemetry.tool_calls}
        tmp = path(k) + '.tmp'
        json.dump({'key': k, 'source': f'anthropic_live_{wave}', 'row': row, 'decision': d.model_dump()},
                  open(tmp, 'w'), indent=1, default=str)
        os.replace(tmp, path(k))
        print('[ckpt]', k, 'PASS' if row['passed'] else 'FAIL', row['final_route'], flush=True)
        if not checks['no_model_failure']:
            print('[ckpt] INVALID MODEL OUTPUT - aborting', k, flush=True)
            raise SystemExit('invalid model output: ' + k)
        if not row['passed']:
            failures.append(k)
            print('[ckpt] FAIL DETAIL', json.dumps(checks), d.risk_flags, flush=True)
recs = [json.load(open(f'{ck}/decisions/{f}')) for f in sorted(os.listdir(f'{ck}/decisions')) if f.endswith('.json')]
json.dump({'cases': len(recs), 'passed': sum(r['row']['passed'] for r in recs),
           'rows': [r['row'] for r in recs]}, open(f'{ck}/summary_{wave}.json', 'w'), indent=1, default=str)
print(f'[ckpt] {cases_file}: {sum(r["row"]["passed"] for r in recs)}/{len(recs)} PASSED', flush=True)
if failures:
    raise SystemExit('failed cases: ' + ', '.join(failures))

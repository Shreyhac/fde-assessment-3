"""Shreyansh Arora | 24bcs10252. Same cases, explicit mode, auditable assertions."""
import csv,json,os,sys,time,statistics,subprocess,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.solution import handle_request
from src.contracts import ProcurementDecision
from evals.run_public_evals import evaluate

def main():
    cases=json.loads((ROOT/'evals/public_cases.json').read_text())
    # Four additional disclosed cases, not a claim about hidden grading.
    cases += [
      {'case_id':'EXT-07','request_id':'REQ-1004','title':'PII cross-region','expectations':{'required_approvals_any_groups':[['Security'],['Privacy'],['Legal']],'human_review_required':True}},
      {'case_id':'EXT-08','request_id':'REQ-1007','title':'Expired and conflicting vendor','expectations':{'risk_flags_any_groups':[['vendor_review_expired'],['conflicting_vendor_evidence']],'required_approvals_any_groups':[['Security']],'human_review_required':True}},
      {'case_id':'EXT-09','request_id':'REQ-1008','title':'Existing tracker','expectations':{'risk_flags_any_groups':[['existing_tool_overlap']],'human_review_required':True}},
      {'case_id':'EXT-10','request_id':'REQ-1010','title':'Small service request','expectations':{'required_approvals_any_groups':[['Manager']],'risk_flags_must_not_contain':['budget_insufficient'],'human_review_required':True}}]
    expected={'REQ-1001':'reuse_review','REQ-1002':'manual_review','REQ-1003':'manual_review','REQ-1004':'manual_review','REQ-1005':'manual_review','REQ-1006':'clarify','REQ-1007':'manual_review','REQ-1008':'reuse_review','REQ-1009':'manual_review','REQ-1010':'approval_review'}
    rows=[]; outputs=[]
    for arch in ['single','staged']:
      for repeat in range(3):
       for case in cases:
        start=time.perf_counter(); d=handle_request(case['request_id'],arch); ms=(time.perf_counter()-start)*1000
        failures=evaluate(d,case['expectations'])
        # Grounding measures evidence SOURCE presence and JSON fidelity, not semantic LLM judgement.
        grounded=all(e.reference and e.source in ('request','budget','catalog','vendor','policy','controls','model_advice') for e in d.evidence)
        ai=json.loads(next(e.finding for e in d.evidence if e.source=='model_advice'))
        ctrl=json.loads(next(e.finding for e in d.evidence if e.source=='controls'))
        rules_ok=set(ctrl['required_approvals']).issubset(d.required_approvals) and set(ctrl['risk_flags']).issubset(d.risk_flags)
        correct=not failures and 'llm_unavailable_or_invalid' not in d.risk_flags
        row={'architecture':arch,'mode':os.getenv('COPILOT_MODE','offline'),'case_id':case['case_id'],'repeat':repeat,
          'correctness_minimum':correct,'grounded_source_refs':grounded,'deterministic_rule_following':rules_ok,
          'route_match':ai['final_route']==expected[case['request_id']], 'expected_route':expected[case['request_id']], 'model_route':ai['advice']['route'] if ai['advice'] else '', 'final_route':ai['final_route'], 'route_locked_by_code':ai['route_locked_by_code'], 'gap_reason':ai['advice']['gap_reason'] if ai['advice'] else '', 'human_escalation':d.human_review_required,'latency_ms':round(ms,2),'llm_calls':d.telemetry.llm_calls,
          'tool_calls':d.telemetry.tool_calls,'failures':' | '.join(failures)}
        rows.append(row); outputs.append({'case_id':case['case_id'],'architecture':arch,'repeat':repeat,'decision':d.model_dump()})
    mode=os.getenv('COPILOT_MODE','offline'); dest=ROOT/'evals'/mode; dest.mkdir(exist_ok=True)
    with (dest/'comparison.csv').open('w',newline='') as f:
      writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    (dest/'decisions.json').write_text(json.dumps(outputs,indent=2))
    summary={}
    for arch in ['single','staged']:
      rs=[r for r in rows if r['architecture']==arch]; lat=sorted(r['latency_ms'] for r in rs)
      summary[arch]={'runs':len(rs),'correctness_minimum':sum(r['correctness_minimum'] for r in rs),
       'grounded_source_refs':sum(r['grounded_source_refs'] for r in rs),'rule_following':sum(r['deterministic_rule_following'] for r in rs),
       'route_matches':sum(r['route_match'] for r in rs),'code_locked_routes':sum(r['route_locked_by_code'] for r in rs), 'human_escalation':sum(r['human_escalation'] for r in rs),'median_ms':statistics.median(lat),
       'p95_ms':lat[math.ceil(.95*len(lat))-1],'total_llm_calls':sum(r['llm_calls'] for r in rs),'total_tool_calls':sum(r['tool_calls'] for r in rs)}
    (dest/'summary.json').write_text(json.dumps({'mode':mode,'semantic_ai_evaluation_complete':False, 'manual_semantic_review_required':True,'results':summary},indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

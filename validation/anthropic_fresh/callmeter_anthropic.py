"""Guarded Anthropic meter (isolated provider run): v5 + HTTP-503-only retry (30/60/120 s, max 3) and worst-case reservation for usage-less failures. Wraps httpx.post and src.solution.handle_request. Records per call: step,
request/architecture context, HTTP status, latency, modelVersion, usageMetadata, finishReason and the model's
response text. It never records headers or the request body. Hard-exits (code 3) with all evidence written on:
non-200, transport error, finishReason != STOP, a decision carrying llm_unavailable_or_invalid, or a projected
spend-cap breach (cumulative ledger + worst-case next call > METER_CAP_USD; rates are verified Sonnet5.5 standard USD2/inputMTok and USD10/outputMTok; max-call reservation uses50000input+4096output)."""
import atexit, json, os, runpy, sys, time
import httpx
out, ledger_path, step, target = sys.argv[1:5]; sys.argv = sys.argv[4:]
sys.path.insert(0, os.getcwd())
RIN = float(os.environ['METER_RATE_IN_PER_M']); ROUT = float(os.environ['METER_RATE_OUT_PER_M']); CAP = float(os.environ['METER_CAP_USD']); SOFT = float(os.environ.get('METER_SOFT_USD', '5.50'))
WORST = 50000 * RIN / 1e6 + 4096 * ROUT / 1e6
L = json.load(open(ledger_path)) if os.path.exists(ledger_path) else {'est_usd': 0.0, 'calls': 0, 'http_200': 0, 'tokens': {}}
log, ctx = [], {}
dec_path = out.replace('.json', '_decisions.jsonl')
def cost(u):
    return u.get('input_tokens', 0) * RIN / 1e6 + u.get('output_tokens', 0) * ROUT / 1e6
def dump():
    json.dump({'step': step, 'http_calls': len(log), 'http_200': sum(r.get('status') == 200 for r in log),
               'aborted': any(r.get('abort') for r in log) or bool(ctx.get('abort')), 'abort_reason': ctx.get('abort'),
               'rates_usd_per_M': {'in': RIN, 'out_incl_thoughts': ROUT}, 'cap_usd': CAP, 'calls': log}, open(out, 'w'), indent=1)
    json.dump(L, open(ledger_path, 'w'), indent=1)
    print(f'[callmeter] step={step} calls={len(log)} http_200={sum(r.get("status") == 200 for r in log)} '
          f'cumulative: calls={L["calls"]} est_usd={L["est_usd"]:.4f}', flush=True)
def abort(why, rec=None):
    if rec is not None: rec['abort'] = why
    ctx['abort'] = why; dump()
    print(f'[callmeter] ABORT: {why} -> stopping all inference (no retry)', flush=True); os._exit(3)
_post = httpx.post
DELAYS = [30, 60, 120]                     # 503-only backoff; max 3 retries + initial
FAKE_SLEEP = os.environ.get('METER_FAKE_SLEEP') == '1'
DEADLINE = float(os.environ.get('METER_DEADLINE_EPOCH', '0') or 0)
def _sleep(s):
    if not FAKE_SLEEP: time.sleep(s)
def post(url, *a, **k):
    if str(url) != 'https://api.anthropic.com/v1/messages': abort('unexpected inference endpoint')
    if len(json.dumps(k.get('json', {}), ensure_ascii=False).encode('utf-8')) > 45000: abort('input upper-bound guard exceeded')
    ctx['stage'] = ctx.get('stage', 0) + 1     # one semantic LLM stage per logical call
    logical = L['logical'] = L.get('logical', 0) + 1
    for attempt in range(len(DELAYS) + 1):
        delay = DELAYS[attempt - 1] if attempt else 0
        if delay: _sleep(delay)
        if DEADLINE and time.time() > DEADLINE: abort('deadline reached before physical attempt (stop-by time)')
        if L['est_usd'] >= SOFT or L['est_usd'] + WORST > CAP: abort(f'spend guard: ledger {L["est_usd"]:.4f} + worst-case call {WORST:.4f} > cap {CAP}')
        rec = {'n': len(log) + 1, 'logical_call': logical, 'attempt': attempt + 1, 'delay_before_s': delay, 'sleep_simulated': FAKE_SLEEP and bool(delay),
               'step': step, 'request_id': ctx.get('request_id'), 'architecture': ctx.get('architecture'), 'stage': ctx['stage'],
               'url_path': str(url).split('?')[0].replace('https://generativelanguage.googleapis.com', ''),
               'local_key_header_sent': 'x-api-key' in (k.get('headers') or {})}
        log.append(rec); L['calls'] += 1; t = time.perf_counter()
        try: r = _post(url, *a, **k)
        except Exception as e:
            rec['ms'] = round((time.perf_counter() - t) * 1000, 1); rec['exception'] = type(e).__name__ + ': ' + str(e)[:200]
            rec['reserved_usd'] = WORST; L['est_usd'] += WORST; L['reserved_usd'] = L.get('reserved_usd', 0) + WORST
            abort('network/transport ' + type(e).__name__ + ' (not retried)', rec)
        rec['ms'] = round((time.perf_counter() - t) * 1000, 1); rec['status'] = r.status_code
        try: j = r.json()
        except Exception as e: j = {}; rec['parse_note'] = type(e).__name__
        rec['modelVersion'] = j.get('model'); rec['usage'] = j.get('usage')
        if rec['usage']:
            c = cost(rec['usage']); rec['est_usd'] = round(c, 6); L['est_usd'] += c
            for key in ('input_tokens', 'output_tokens'):
                L['tokens'][key] = L['tokens'].get(key, 0) + rec['usage'].get(key, 0)
        else:
            rec['reserved_usd'] = WORST; L['est_usd'] += WORST; L['reserved_usd'] = L.get('reserved_usd', 0) + WORST
        if r.status_code == 503 and attempt < len(DELAYS):
            rec['error'] = {x: (j.get('error') or {}).get(x) for x in ('type', 'message')}
            rec['outcome'] = 'retry_503'; print(f'[callmeter] 503 on {ctx.get("request_id")}/{ctx.get("architecture")} stage {ctx["stage"]}; retry {attempt + 1}/3 after {DELAYS[attempt]}s', flush=True)
            continue
        if r.status_code != 200:
            rec['error'] = {x: (j.get('error') or {}).get(x) for x in ('type', 'message')}
            why = 'HTTP 503 retries exhausted (4 attempts)' if r.status_code == 503 else f'HTTP {r.status_code} {rec["error"].get("status")} (not retried)'
            abort(why, rec)
        L['http_200'] += 1
        try: rec['response_text'] = ''.join(p.get('text', '') for p in j['content'] if p.get('type') == 'text')[:6000]
        except Exception: rec['response_text'] = None
        try: rec['finishReason'] = j.get('stop_reason')
        except Exception: rec['finishReason'] = None
        if rec['finishReason'] != 'end_turn': abort(f'model output finishReason={rec["finishReason"]} (not retried)', rec)
        rec['outcome'] = 'ok'
        return r
httpx.post = post
import src.solution as sol
_hr = sol.handle_request
def handle_request(request_id, architecture='single'):
    ctx.update(request_id=request_id, architecture=architecture, stage=0); t = time.perf_counter()
    d = _hr(request_id, architecture)
    with open(dec_path, 'a') as f:
        f.write(json.dumps({'step': step, 'request_id': request_id, 'architecture': architecture,
                            'latency_ms': round((time.perf_counter() - t) * 1000, 1), 'decision': d.model_dump()}, default=str) + '\n')
    if 'llm_unavailable_or_invalid' in d.risk_flags: abort(f'llm_unavailable_or_invalid on {request_id}/{architecture}')
    return d
sol.handle_request = handle_request
atexit.register(dump)
runpy.run_path(target, run_name='__main__')

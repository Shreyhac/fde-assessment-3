"""Wrap httpx.post to meter real Gemini calls (status, modelVersion, usage, finishReason; never headers/body).
Guard: on the first non-200, network exception, or non-STOP finishReason, dump the meter and hard-exit (code 3)
so no further paid calls are made."""
import atexit, json, os, runpy, sys, time
import httpx
out = sys.argv[1]; target = sys.argv[2]; sys.argv = sys.argv[2:]
log = []
def dump():
    ok = sum(1 for r in log if r.get('status') == 200)
    json.dump({'http_calls': len(log), 'http_200': ok, 'aborted': any(r.get('abort') for r in log), 'calls': log}, open(out, 'w'), indent=1)
    print(f'[callmeter] gemini http calls={len(log)} http_200={ok} -> {os.path.basename(out)}', flush=True)
def abort(rec, why):
    rec['abort'] = why; dump()
    print(f'[callmeter] ABORT: {why} -> stopping all inference (no retry)', flush=True)
    os._exit(3)
_orig = httpx.post
def post(url, *a, **k):
    rec = {'n': len(log) + 1, 'url_path': str(url).split('?')[0].replace('https://generativelanguage.googleapis.com', ''),
           'local_key_header_sent': 'x-goog-api-key' in (k.get('headers') or {})}
    log.append(rec); t = time.perf_counter()
    try:
        r = _orig(url, *a, **k)
    except Exception as e:
        rec['ms'] = round((time.perf_counter() - t) * 1000, 1); rec['exception'] = type(e).__name__ + ': ' + str(e)[:200]
        abort(rec, 'network/transport ' + type(e).__name__)
    rec['ms'] = round((time.perf_counter() - t) * 1000, 1); rec['status'] = r.status_code
    try: j = r.json()
    except Exception as e: j = {}; rec['parse_note'] = type(e).__name__
    rec['modelVersion'] = j.get('modelVersion'); rec['usage'] = j.get('usageMetadata')
    if r.status_code != 200:
        rec['error'] = {x: (j.get('error') or {}).get(x) for x in ('code', 'status', 'message')}
        abort(rec, f'HTTP {r.status_code} {rec["error"].get("status")}')
    try: rec['finishReason'] = j['candidates'][0].get('finishReason')
    except Exception: rec['finishReason'] = None
    if rec['finishReason'] != 'STOP': abort(rec, f'model output finishReason={rec["finishReason"]}')
    return r
httpx.post = post
atexit.register(dump)
runpy.run_path(target, run_name='__main__')

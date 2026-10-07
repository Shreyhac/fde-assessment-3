# Attempt 3 (after cooldown): FAILED, stopped at probe 1 (ReadTimeout)

Budget: at most two inference probes. Probe 1 used `gemini-3.5-flash`. Probe 2 (`gemini-3.6-flash`) was allowed
only if probe 1 returned HTTP 503. `MODEL_NAME` was overridden on the command for this validation only. The
package default (`MODEL_NAME=gemini-2.5-flash` in `.env.example`) and all solution code are unchanged apart from
`live_mode.diff`. Gemini calls went through `callmeter_guarded.py`. It records HTTP status, modelVersion, usage
and finishReason, and never headers or body. It hard-exits on the first non-200 response, transport error or
non-STOP finish.

| Step | Status |
|---|---|
| Offline pytest | 40 passed |
| Preflight | PASSED |
| Mock vendor API 127.0.0.1:8001 | healthy; shut down at the end (pid 237) |
| Probe 1: REQ-1001 single, gemini-3.5-flash | **FAILED**: `httpx.ReadTimeout` after ~25.7 s (the code's own 25 s timeout). No HTTP status received, so not a 503. |
| Probe 2: gemini-3.6-flash | **NOT RUN**: allowed only on a 503 from probe 1 |
| Public eval single (live) | **NOT RUN** |
| Public eval staged (live) | **NOT RUN** |
| Live comparison, 10 cases x3 x2 architectures | **NOT RUN** |
| Raw live decisions, comparison.csv, summary.json | **NOT PRODUCED** |
| Manual qualitative review per case/architecture | **NOT POSSIBLE**: no model advice was produced |

Gemini generateContent calls in this attempt: 1 (0 successful, no model output, no usage reported).
This is a failure record, not a success.

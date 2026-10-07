# Attempt 4 (final single probe): FAILED, HTTP 503 on gemini-3.6-flash

`MODEL_NAME=gemini-3.6-flash` was set on the command for this validation only. The package default
(`gemini-2.5-flash` in `.env.example`), the 25 s timeout and all source code are unchanged apart from
`live_mode.diff`. The one live call went through `callmeter_guarded.py`. It records status, modelVersion, usage
and finishReason, never headers or body, and hard-exits on the first error.

| Step | Status |
|---|---|
| Mock vendor API 127.0.0.1:8001 | healthy; shut down at the end (pid 230, process exited) |
| Live probe: REQ-1001 single, gemini-3.6-flash | **FAILED**: HTTP 503 UNAVAILABLE, "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later." (~1.25 s) |
| Usage metadata returned | **None** (no modelVersion, no usageMetadata) |
| Retries | **None**, as instructed |
| Public eval single (live) | **NOT RUN** |
| Public eval staged (live) | **NOT RUN** |
| Live comparison, 10 cases x3 x2 architectures | **NOT RUN** |
| Raw live decisions, comparison.csv, summary.json, qualitative review | **NOT PRODUCED** |

Gemini generateContent calls in this attempt: 1 (0 successful). Across all four attempts: 4, none successful.
This is a failure record, not a success. `secret_scan.txt` holds the scan result for this bundle.

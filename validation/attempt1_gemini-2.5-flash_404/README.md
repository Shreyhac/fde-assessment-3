# FDE3 live validation: stopped at the live probe

The package was decoded from `source-package.b64`. Its SHA256 matched the required value
(38ced1d9628af77fbd5784baf05f4ac35a1284f2d4b7611d9a96ef146179bf65), and it was unpacked to `AI_Procurement_Copilot/`.
Only `src/model.py` and `src/solution.py` were changed (see `../live_mode.diff`):

- `solution.py`: the live gate now accepts a local `GEMINI_API_KEY` or `GEMINI_NETWORK_SECRET=1`.
- `model.py`: when there is no local key and `GEMINI_NETWORK_SECRET=1`, the `x-goog-api-key` header is left
  out so the egress proxy adds it. Local-key behaviour is unchanged.

| Step | Result |
|---|---|
| pytest, offline (`COPILOT_MODE=offline`, network-secret unset) | 40 passed |
| verify_setup.py preflight | PASSED |
| Mock vendor API on 127.0.0.1:8001 | healthy, then shut down |
| Live probe: REQ-1001, single, gemini-2.5-flash | **HTTP 404 NOT_FOUND**: "This model models/gemini-2.5-flash is no longer available to new users." |
| Public evals (single/staged), live comparison | **Not run**: stopped on the model error. No retries and no model swap. |

Gemini HTTP calls made: 1 (0 successful). The proxy authenticated the request; no local key header was sent.
`live_probe_calls.json` records the status, error and model path for that call, without headers or body.
`AI_Procurement_Copilot/evals/results_*.csv` and `evals/offline/` are the package's original files, not output from this session.

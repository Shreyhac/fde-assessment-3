# Attempt 2: gemini-3.5-flash, stopped at the live probe (HTTP 503)

1. **models.list** (one read-only `GET /v1beta/models/?pageSize=1000` through the credential proxy, no local key):
   HTTP 200, 62 models, single page. Names, versions and `supportedGenerationMethods` are in `models_list.json`.
   Request headers were not saved.
2. **Model choice** (`model_choice.json`):
   - `gemini-2.5-flash` is listed with generateContent, but attempt 1 got HTTP 404 "no longer available to new users".
     It was not called again.
   - Next in the preference order is a stable Flash model. The closest stable, version-pinned Flash is
     **`gemini-3.5-flash`** (`3.5-flash-05-2026`). It was not taken from the 404's suggestion of `gemini-3.8-flash`.
   - `MODEL_NAME=gemini-3.5-flash` was set on the command only. The provider and solution code were not changed.
   - This is a validation choice, not the final graded model choice.
3. **Offline checks** (repeated): pytest 40 passed; preflight PASSED.
4. **Live probe** (REQ-1001, single): **HTTP 503 UNAVAILABLE**: "This model is currently experiencing high
   demand. Spikes in demand are usually temporary. Please try again later." This was 1 HTTP call, 0 successful,
   ~17.7 s. The decision carries `llm_unavailable_or_invalid` and has no model advice.
5. **Stopped**: there was no retry and no further model substitution. Public evals (single/staged) and the
   10x3 live comparison were not run, so there is no `evals/live` output. The mock API was shut down.

Gemini calls in this attempt: models.list 1 (200); generateContent 1 (503). Total generateContent calls
across both attempts: 2, none successful.

# Anthropic fresh evaluation (claude-sonnet-5-5): INCOMPLETE, stopped at decision 2/72 (schema-length defect)

Setup:
- Owner-approved ZIP, SHA256 `aa842149bde8c118e1277a1bccaa1ef3488086a34a9b2bcb0502fe56806dce16`. Both uploads were identical; one copy was used.
- Installed `src/model.py`, `src/solution.py`, `tests/conftest.py` and `tests/test_anthropic.py`. Pre-install copies are in
  `pre_install_backup/`; diffs are `install_vs_previous_worktree.diff` and `source_vs_HEAD.diff`.
- Key check (booleans only): `FDE3_ANTHROPIC_API_KEY` present = True; `ANTHROPIC_API_KEY` present = False. No key value
  was printed or written.
- Offline pytest: 52 passed, with the provider key removed from the test environment.
- Fresh checkpoint with no Gemini seed. Gemini evidence (5 decisions) is untouched in `../../../validation/attempt*`.
- Command as approved (`COPILOT_MODE=live MODEL_PROVIDER=anthropic MODEL_NAME=claude-sonnet-5-5`, rates 2/10 USD per MTok,
  cap 6, soft 5.50), plus `METER_DEADLINE_EPOCH` = 13:28Z (18:58 IST). `METER_FAKE_SLEEP` was not set.
- The first launch attempt was blocked by the session's permission classifier ("Code from External") and made no calls.
  It was relaunched after the owner said "allow it".

| Item | Result |
|---|---|
| PUB-01 / REQ-1001 single (first charged call) | **PASS**: HTTP 200, `end_turn`, 7.3 s, input 3631 / output 598 tokens. Model `reuse_review` = code route = final. Saved to the checkpoint |
| PUB-02 / REQ-1002 single | **INVALID**: HTTP 200, `end_turn`, 4.3 s, input 3791 / output 468 tokens. The model's `reason` was **1040 chars**, but `Advice.reason` has `max_length=700`, so pydantic `ValidationError` → `llm_unavailable_or_invalid` → the meter stopped. The app failed safe ("Hold for manual review … no approval inferred"). Not saved to the checkpoint |
| Remaining 70 decisions (4 public single, 6 public staged, 60 comparison) | **NOT RUN** |
| Mock API :8001 | shut down (pid 680, process exited) |

Physical Anthropic calls: 2 (both HTTP 200). Ledger estimate at the stated rates: **$0.0255** (usage-based; no reservations
were needed). This is an estimate from reported usage at the stated list rates, not an invoice.

## Root cause (code defect in the approved bundle; not fixed, since it would be a source change)
`infer_anthropic` sends a JSON schema without `maxLength` on `reason` (or `gap_reason`), and the SYSTEM prompt sets no length
limit. The app then enforces `reason ≤ 700` and `gap_reason ≤ 400` after the fact. Sonnet 5.5 writes long, well-grounded
reasons: about 620 chars on PUB-01 (passed by margin) and 1040 on PUB-02. Most cases will hit the same failure. Candidate
fixes, for the owner to approve:
(a) add `"maxLength": 700` / `400` to the schema properties, if the structured-output feature enforces it;
(b) add an explicit length instruction to the prompt;
(c) raise `max_length` in `Advice`.
(a)+(b) keeps the existing contract.

## Semantic review
- **PUB-01 (REQ-1001):** correct and well grounded. Before buying it checks the 45 existing SignFlow seats and does not
  assume spare capacity. $800 is within the $29k available; Manager approval only; the registry and API agree on a current
  security review. Explicitly human-final.
- **PUB-02 (REQ-1002):** the model proposed `approval_review` (code route `manual_review`, locked), with 6 grounded
  evidence IDs. Like Gemini on this case, it was less cautious than the code. The output was rejected for length before
  routing, so the final decision was a fail-safe manual review, and the decision was correctly not counted as valid.

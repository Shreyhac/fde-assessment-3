# Architecture decision memo
Shreyansh Arora | 24bcs10252 | 8 October 2026

## Decision
I ship A, the single-agent baseline, with mandatory deterministic controls and human approval. The assessment model is Claude Sonnet 5.5, chosen after the completed live evaluation.

## Evidence
Ten synthetic requests ran three times per architecture, plus six public cases each. In the model-driven run (182 API calls, $1.8984 estimated at $2/$10 per MTok, not an invoice) both architectures matched all 30 expected routes, preserved every control and passed the public cases. The model's own route matched in 27/30 per architecture; the lock corrected three injection-case repeats where the prompt lacked a clarify-over-manual precedence. With that line added, the model itself chose clarify there in waves 4 and 7.

An earlier code-orchestrated run (109 calls, $1.2609) reached the same final routes, but the model matched only 18/30 per architecture because its prompt under-specified manual review.

## Why the controls stay mandatory
Even with the aligned prompt, the code - not the model - decides financial thresholds, freshness, conflicts and approval sets, and code locks clarify/manual-review routes. The model retrieves evidence through four read-only tools and interprets need and gaps; code re-runs any tool it skips. The injection case stayed clarification in every run. Neither architecture purchases, approves spending, changes budgets or accepts terms.

## Why A over B: a cost/latency trade-off
B adds a Policy/Risk Reviewer over the same evidence pack without re-fetching tools. In the wave-3 run it used 1.5x the model calls (90 vs 60) and about 1.75x the median and p95 latency (8.63s/11.20s vs 4.92s/6.38s), with identical final routes, and the reviewer changed the analyst's route in 0 of 36 runs. Wave 5 is different: the reviewer changed the analyst's route in 4 of 14 cases, and on four benign requests that state no business purpose B's stricter routes were correct by Policy section 1 while A approved them. That is B's measured benefit. I still ship A. A business-purpose prompt rule was written for those five benign cases (in-sample, disclosed; wave 5b: A 5/5, B 4/5), and wave 7 re-verified the final prompt on the comparison set: final routes unchanged on all 10 cases in both architectures. Clarify and manual-review routes stay code-locked, and every route ends with a human reviewer, so an A miss reaches a person rather than a purchase. If broader data shows the reviewer catching what prompt rules cannot, B's extra cost is worth paying.

## Limits
Small synthetic sample; one provider and model; the injection regex was developed on the wave-5 phrasings and has low recall on unseen attacks (the model's own injection flag carries detection); manual, non-independent semantic review; latency measured in one container against the mock vendor API; hidden grading cases may behave differently. Production needs authorization, audit storage, real seat-use data and broader adversarial and paraphrased tests. Human reviewers still decide fit and exceptions.

Evidence: validation/anthropic_toolcalling/ (final run) and validation/anthropic_fresh/ (earlier run, preserved).

# Architecture decision memo (draft)
Shreyansh Arora | 24bcs10252

## Decision
Provisionally prefer A, the single-agent baseline, after live validation. Do not claim either architecture is production-ready from the current offline results.

## Evidence
The same ten disclosed requests were run three times per architecture against the course mock service. Both passed all 30 minimum behavioral checks, source-reference checks, deterministic-control checks and human-escalation checks. Each used five tools per request and zero LLM calls. See `evals/offline/summary.json` for measured local latency; those numbers measure the rule preview, not AI inference. Equal offline scores do not show that a second agent adds no value.

## Design
A has one Procurement Agent using an evidence pack. B has a Procurement Analyst followed by a Policy/Risk Reviewer, passing structured evidence and tool results without re-fetching. In live mode A attempts one model call and B two. Both have the same read-only tools, typed model response, citation validation, deterministic thresholds and non-removable approval controls. No architecture can purchase, modify budgets or grant approval.

## Tradeoff
A has less orchestration and fewer inference calls. B could improve nuanced gap interpretation or detect an analyst's reasoning error, but could also repeat that error and add latency. Its role separation is not independent evidence. Financial and sensitive-data controls belong in shared code, not agent debate.

## Release gate
Supply an authorized model key, run the same set in live mode and inspect each recommendation against tool evidence. Add paraphrased use cases, adversarial vendor notes and repeated samples. Measure exact next-action quality, false-positive/negative escalations, latency and actual call counts. Ship A only if these checks pass and B has no material safety benefit; choose B if its benefit justifies its extra latency and complexity. Code orchestrates fixed retrieval so the model cannot skip mandatory checks.

## Limits
Synthetic data, no live procurement integration, no seat-utilization dataset, conservative lexical overlap and injection signals. The offline mode is useful for control regression but is not an AI evaluation. Human reviewers must verify use-case fit, licenses and all sensitive exceptions.

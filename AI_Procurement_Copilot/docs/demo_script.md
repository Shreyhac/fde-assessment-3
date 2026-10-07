# Recording guide (user records the Loom himself)
Shreyansh Arora | 24bcs10252

Use the live model mode only after supplying a local key and rerunning evaluations. If recording offline, say clearly that it is a rule preview and the AI comparison remains incomplete. Do not present it as a completed AI product.

1. Show the README and your name/roll number. Say: "This copilot gathers procurement evidence, applies code checks and recommends a next step. It cannot approve or purchase. All datasets are synthetic."
2. Start with `./start.sh`. Say: "One command installs the dependencies and starts the vendor API and request UI. Offline mode makes no model calls."
3. Open the URL printed for the UI. Select REQ-1002, run analysis, and expand budget, catalog and vendor evidence. Explain the design-tool alternatives and the requester's stated usability gap. Do not claim spare seats exist.
4. Select REQ-1005. Show the budget shortfall and Security, Privacy, Legal and Finance handoff.
5. Select REQ-1006. Show missing amount, users and data access. Explain why the fake-CFO instruction cannot create approval.
6. Select REQ-1007. Show the registry/API conflict and expired date, resolved against the policy snapshot, not today's computer clock.
7. Select REQ-1009. Show graceful handling of the mock API's 503 response. Download a review packet, which does not send or approve anything.
8. Show `docs/architecture.svg`. Explain baseline A and Analyst -> Reviewer B sharing the evidence pack.
9. While the local launcher is running, use a second terminal: `.venv/bin/python -m pytest -q` then `.venv/bin/python evals/run_comparison.py`. Show `evals/offline/summary.json` or the live results when available. Say exactly which mode these measurements used.
10. End with the provisional ship choice and limits from `docs/architecture_decision.md`. No fabricated Claude confidence score.

The form asks for a Loom link. Duration is not specified in the Assessment 3 brief; keep the demo focused rather than borrowing another assessment's duration requirement.

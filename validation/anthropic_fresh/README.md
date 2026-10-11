# Anthropic fresh evaluation, waves 1-2 (8 October 2026): COMPLETE but superseded

This folder preserves the finished code-orchestrated run: 72/72 valid live decisions on claude-sonnet-5-5, 109 physical API calls, $1.2609 usage estimate. Run 1 stopped at decision 2/72 (overlong-output defect) and is archived untouched in `wave1_backup/`; run 2 completed after the prompt/schema-description length fix. The full record is in `REVIEW_wave2.md`; nothing here was modified after the run except this pointer.

It is superseded as headline evidence by `../anthropic_toolcalling/`: the same 72-decision plan re-run with model-driven tool calling (the model retrieves evidence through the tools itself) and a routing prompt aligned with the deterministic controls. That run answers two criticisms of this one: the model never called tools, and its under-escalations were caused by the old prompt rather than by model behaviour.

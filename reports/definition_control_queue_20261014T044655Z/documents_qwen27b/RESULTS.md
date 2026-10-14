# Definition format and contextual evidence controls

Status: **COMPLETE**. Model: `ktrf-production-qwen3.5-27b-bf16`. 768/768 responses.

Exact output matching and conservative literal-normalized QA are distinct. UNASSESSED needs review; definition containment never earns automatic credit.

| Condition | Task | Exact / planned | Normalized / planned | Unassessed | Positive null | Malformed | Missing |
|---|---|---:|---:|---:|---:|---:|---:|
| prose_all | document_qa | 60/64 | 60/64 | 0 | 1 | 0 | 0 |
| prose_all | structured_routing | 60/64 | 60/64 | 0 | 4 | 0 | 0 |
| cards_all | document_qa | 61/64 | 61/64 | 0 | 0 | 0 | 0 |
| cards_all | structured_routing | 59/64 | 59/64 | 0 | 3 | 0 | 0 |
| cards_retrieved | document_qa | 48/64 | 48/64 | 0 | 6 | 0 | 0 |
| cards_retrieved | structured_routing | 51/64 | 51/64 | 0 | 8 | 0 | 0 |
| ktrf_qa_cards | document_qa | 61/64 | 61/64 | 0 | 0 | 0 | 0 |
| ktrf_qa_cards | structured_routing | 62/64 | 62/64 | 0 | 2 | 0 | 0 |
| ktrf_execution_cards | document_qa | 61/64 | 61/64 | 0 | 0 | 0 | 0 |
| ktrf_execution_cards | structured_routing | 32/64 | 32/64 | 0 | 32 | 0 | 0 |
| ktrf_contextual_execution_cards | document_qa | 61/64 | 61/64 | 0 | 0 | 0 | 0 |
| ktrf_contextual_execution_cards | structured_routing | 47/64 | 47/64 | 0 | 17 | 0 | 0 |

## Source collections

Previously inspected contextual documents and fresh explicit-definition cases remain separate.

| Condition | Collection | Task | Exact / planned | Normalized / planned |
|---|---|---|---:|---:|
| prose_all | fresh_definition | document_qa | 32/32 | 32/32 |
| prose_all | fresh_definition | structured_routing | 32/32 | 32/32 |
| prose_all | original_context | document_qa | 28/32 | 28/32 |
| prose_all | original_context | structured_routing | 28/32 | 28/32 |
| cards_all | fresh_definition | document_qa | 32/32 | 32/32 |
| cards_all | fresh_definition | structured_routing | 32/32 | 32/32 |
| cards_all | original_context | document_qa | 29/32 | 29/32 |
| cards_all | original_context | structured_routing | 27/32 | 27/32 |
| cards_retrieved | fresh_definition | document_qa | 25/32 | 25/32 |
| cards_retrieved | fresh_definition | structured_routing | 25/32 | 25/32 |
| cards_retrieved | original_context | document_qa | 23/32 | 23/32 |
| cards_retrieved | original_context | structured_routing | 26/32 | 26/32 |
| ktrf_qa_cards | fresh_definition | document_qa | 32/32 | 32/32 |
| ktrf_qa_cards | fresh_definition | structured_routing | 32/32 | 32/32 |
| ktrf_qa_cards | original_context | document_qa | 29/32 | 29/32 |
| ktrf_qa_cards | original_context | structured_routing | 30/32 | 30/32 |
| ktrf_execution_cards | fresh_definition | document_qa | 32/32 | 32/32 |
| ktrf_execution_cards | fresh_definition | structured_routing | 16/32 | 16/32 |
| ktrf_execution_cards | original_context | document_qa | 29/32 | 29/32 |
| ktrf_execution_cards | original_context | structured_routing | 16/32 | 16/32 |
| ktrf_contextual_execution_cards | fresh_definition | document_qa | 32/32 | 32/32 |
| ktrf_contextual_execution_cards | fresh_definition | structured_routing | 31/32 | 31/32 |
| ktrf_contextual_execution_cards | original_context | document_qa | 29/32 | 29/32 |
| ktrf_contextual_execution_cards | original_context | structured_routing | 16/32 | 16/32 |

## Routing acceptance

Neutral arms validate supplied-ID membership for proposals. Production arms use their execution guard.

| Condition | Accepted correct ID | Accepted wrong ID | Positive candidate / targets |
|---|---:|---:|---:|
| prose_all | 28 | 0 | 32/32 |
| cards_all | 29 | 2 | 32/32 |
| cards_retrieved | 22 | 5 | 22/32 |
| ktrf_qa_cards | 30 | 0 | 32/32 |
| ktrf_execution_cards | 0 | 0 | 0/32 |
| ktrf_contextual_execution_cards | 15 | 0 | 15/32 |

## Paired changes

| Contrast | Task | Metric | Comparable | Helped | Harmed |
|---|---|---|---:|---:|---:|
| prose_all__to__cards_all | document_qa | exact_match | 64 | 1 | 0 |
| prose_all__to__cards_all | document_qa | semantic_match | 64 | 1 | 0 |
| prose_all__to__cards_all | document_qa | operational_correct | 64 | 1 | 0 |
| prose_all__to__cards_all | structured_routing | exact_match | 64 | 2 | 3 |
| prose_all__to__cards_all | structured_routing | semantic_match | 64 | 2 | 3 |
| prose_all__to__cards_all | structured_routing | operational_correct | 64 | 2 | 3 |
| cards_all__to__cards_retrieved | document_qa | exact_match | 64 | 0 | 13 |
| cards_all__to__cards_retrieved | document_qa | semantic_match | 64 | 0 | 13 |
| cards_all__to__cards_retrieved | document_qa | operational_correct | 64 | 0 | 13 |
| cards_all__to__cards_retrieved | structured_routing | exact_match | 64 | 5 | 13 |
| cards_all__to__cards_retrieved | structured_routing | semantic_match | 64 | 5 | 13 |
| cards_all__to__cards_retrieved | structured_routing | operational_correct | 64 | 5 | 13 |
| cards_all__to__ktrf_qa_cards | document_qa | exact_match | 64 | 0 | 0 |
| cards_all__to__ktrf_qa_cards | document_qa | semantic_match | 64 | 0 | 0 |
| cards_all__to__ktrf_qa_cards | document_qa | operational_correct | 64 | 0 | 0 |
| cards_all__to__ktrf_qa_cards | structured_routing | exact_match | 64 | 4 | 1 |
| cards_all__to__ktrf_qa_cards | structured_routing | semantic_match | 64 | 4 | 1 |
| cards_all__to__ktrf_qa_cards | structured_routing | operational_correct | 64 | 4 | 1 |
| ktrf_execution_cards__to__ktrf_contextual_execution_cards | document_qa | exact_match | 64 | 0 | 0 |
| ktrf_execution_cards__to__ktrf_contextual_execution_cards | document_qa | semantic_match | 64 | 0 | 0 |
| ktrf_execution_cards__to__ktrf_contextual_execution_cards | document_qa | operational_correct | 64 | 0 | 0 |
| ktrf_execution_cards__to__ktrf_contextual_execution_cards | structured_routing | exact_match | 64 | 15 | 0 |
| ktrf_execution_cards__to__ktrf_contextual_execution_cards | structured_routing | semantic_match | 64 | 15 | 0 |
| ktrf_execution_cards__to__ktrf_contextual_execution_cards | structured_routing | operational_correct | 64 | 15 | 0 |

## Definition availability

Catalog/card exposure and full model-input exposure are separate; source text can itself contain a definition.

| Condition | Task | Catalog definition / positive | Definition in model input / positive |
|---|---|---:|---:|
| prose_all | document_qa | 32/32 | 32/32 |
| prose_all | structured_routing | 32/32 | 32/32 |
| cards_all | document_qa | 32/32 | 32/32 |
| cards_all | structured_routing | 32/32 | 32/32 |
| cards_retrieved | document_qa | 22/32 | 26/32 |
| cards_retrieved | structured_routing | 22/32 | 26/32 |
| ktrf_qa_cards | document_qa | 32/32 | 32/32 |
| ktrf_qa_cards | structured_routing | 32/32 | 32/32 |
| ktrf_execution_cards | document_qa | 32/32 | 32/32 |
| ktrf_execution_cards | structured_routing | 0/32 | 12/32 |
| ktrf_contextual_execution_cards | document_qa | 32/32 | 32/32 |
| ktrf_contextual_execution_cards | structured_routing | 15/32 | 19/32 |

## Costs

| Condition | Task | Prompt tokens | p95 latency ms |
|---|---|---:|---:|
| prose_all | document_qa | 49121 | 2191.198 |
| prose_all | structured_routing | 48161 | 3496.832 |
| cards_all | document_qa | 45473 | 2089.362 |
| cards_all | structured_routing | 44513 | 3538.562 |
| cards_retrieved | document_qa | 39633 | 2031.959 |
| cards_retrieved | structured_routing | 38673 | 3574.499 |
| ktrf_qa_cards | document_qa | 45499 | 2101.494 |
| ktrf_qa_cards | structured_routing | 44539 | 3349.114 |
| ktrf_execution_cards | document_qa | 70084 | 2292.913 |
| ktrf_execution_cards | structured_routing | 32057 | 2001.053 |
| ktrf_contextual_execution_cards | document_qa | 68585 | 2117.862 |
| ktrf_contextual_execution_cards | structured_routing | 36665 | 3464.244 |

## Limitations

- Post-hoc diagnostic on previously evaluated AI-authored synthetic documents, not an independent sealed risk test.
- Definition formatting controls share all catalog facts; every prose definition has explicit exact-copy boundaries.
- Candidate controls change retrieval, candidate representation and policy; only prose_all/cards_all isolate formatting.
- KTRF QA candidate cards are evidence for a neutral proposal, not verified linking or execution authorization.
- Production controls use actual task-specific QA/automation packs, fixed production policies and complete-response execution guards for routing.
- Contextual exact resolution is explicitly enabled only in the contextual diagnostic arm; production default remains unchanged.
- Exact QA, conservative semantic QA assessment and routing correctness are separate scores; UNASSESSED paraphrases receive no automatic credit.
- All arms receive the same full source and explicit target, and share the opaque ID scheme. Candidate/ID exposure varies by arm; the complete definition inventory is grading metadata, not extra model context.
- Full inputs are never silently truncated; tokenizer capacity must be checked before model inference.
- Model-family comparisons do not isolate parameter count. Preparation costs are excluded from model-call latency.

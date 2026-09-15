# P1-14 Validation Report — KKBox-to-Reusable Architecture Story

**Tracker row:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, ID `P1-14`, Stage "Reusable Platform", Priority P1.
**Status change:** `TODO` → `REVIEW` (this report; not `DONE` — reserved for independent sign-off).

## 1. Exact requirement from the tracker

**Issue:** "The solution needs a defensible explanation of what is KKBox-specific versus reusable."

**Claude Fix Prompt:** "Audit the pipeline and document domain-specific inputs versus reusable retention decision-support architecture. Explain KKBox as validation use case, without claiming validated performance elsewhere. Only add genuinely supported configuration/abstraction; do not change model outputs."

**Acceptance Criteria:** "Product/docs clearly separate evidence from general architecture; no unsupported claims; evaluator questions about dataset choice are answerable; tests pass."

## 2. Audit

Read `test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md` in full before writing anything. Two of its sections are directly this ticket's prior art:

- **"Part 8 — KKBOX vs. reusable-platform audit"** already did the source-level fact-finding this ticket's "audit the pipeline" instruction asks for: KKBox-specific naming appears in exactly 9 cosmetic, non-structural places in `dashboard/`; the deterministic tool layer, orchestrator, and UI operate only on the generic *shape* of `outputs/*.csv`/`*.json` (`msno`, `risk_score_full`, `calibrated_probability`, `segment`, `total_revenue`); `src/` (feature engineering) is genuinely KKBox-schema-specific, citing exact real column names (`msno`, `is_cancel`, `payment_method_id`, `membership_expire_date`). It already arrived at a precise, non-overclaimed conclusion: *"the retention-intelligence layer above the data ... is designed narrowly enough to be schema-portable; the path from raw transactional data to that shape is currently KKBox-specific and would need to be rebuilt per business."*
- **"Part 9 — Technical defensibility audit"** graded, per likely evaluator question, whether the *live product itself* (not just a doc) could answer it. It graded "Why KKBox?" and "Where does the data come from?" as the two weakest-supported questions — answerable only verbally, not from inside the product, because no page stated dataset provenance or the KKBox-specific/reusable split anywhere.

I re-verified these two specific facts myself before relying on them: `data/kkbox-churn-prediction-challenge/kkbox_dataset_audit.md` independently confirms the dataset is KKBox's own real, anonymized production data, released for the WSDM 2018 Cup Challenge (not synthetic) — the same claim the audit made, now re-checked at the source. I re-grepped `src/` for the cited column names to confirm they are still real, current references (they are).

**This ticket's scope, precisely:** the underlying fact-finding audit was already done and is still accurate; what was missing was surfacing it *inside the live product*, in the precise, already-vetted wording, in one place a fresh evaluator would actually see — not re-doing the audit, and not building a new documentation system.

## 3. Files changed and why

- **`dashboard/lib/caveats.py`** — added one new caveat category, `"reusability"`, following the exact same established pattern as the six pre-existing categories (`calibration`, `temporal`, `hrr`, `revenue_exposure`, `thresholds`, `causal`): a small body-text function plus one entry in `CAVEAT_DEFS`. No existing category, function, or rendering logic was changed.
- **`dashboard/pages/overview.py`** — added `"reusability"` to the existing `caveats.render_caveats([...])` call (previously `["temporal", "calibration"]`, now `["temporal", "calibration", "reusability"]`). This is the only page-level change; nothing else on Overview was touched.
- **`tests/test_reusable_architecture_story.py`** — new file, 11 tests.

No other file was touched. `notebooks/`, `models/`, `outputs/`, `src/` are unmodified (confirmed via `find ... -newermt`) — this ticket explicitly documents `src/`'s KKBox-specificity, it does not alter it.

## 4. Exact content added

The new caveat (title: "Why KKBox, and what would carry over to another business") states, in order:

1. **Dataset provenance** — KKBox's own real, anonymized subscriber data, released for the WSDM 2018 Cup Challenge; a genuine production dataset, not synthetic. (Directly answers the audit's "Why KKBox? / Where's the data from?" — previously unanswerable from inside the product.)
2. **What is KKBox-specific** — `src/`'s exact real column-name references (`msno`, `is_cancel`, `payment_method_id`, `membership_expire_date`), stated as not reusable as-is; the 9 cosmetic KKBox-naming spots in the dashboard, stated as cosmetic, not structural.
3. **What is reusable** — the deterministic tool layer, orchestrator, and every dashboard page operate only on the generic shape of the scoring outputs, not on any KKBox-only business rule; the four-term terminology discipline is domain-general.
4. **The precise, non-overclaimed statement** — the exact sentence from the audit, verbatim in spirit: schema-portable architecture above the data, KKBox-specific pipeline below it, would need to be rebuilt per business.
5. **An explicit negative claim** — "This has **not** been validated on any dataset other than KKBox's — that broader claim is not made here." This is the concrete implementation of "Explain KKBox as validation use case, without claiming validated performance elsewhere."

Every fact stated is either already-verified by the TASK_05 audit (re-checked by me at the source, per §2) or a direct, uncontroversial restatement of already-established product facts (the four-term terminology, already enforced elsewhere in code). No new claim about model performance, generalization, or validation was introduced. `src/`, `notebooks/`, `models/`, and `outputs/` were read, not modified — satisfying "do not change model outputs."

## 5. Tests added

`tests/test_reusable_architecture_story.py` — 11 tests, two groups:

- **Content tests** (6): the new `"reusability"` key exists alongside all 6 pre-existing `CAVEAT_DEFS` keys (7 total); the body names KKBox as "the validation use case" and cites the real, verifiable "WSDM 2018" provenance; it structurally separates "What is KKBox-specific:" from "What is reusable:" and cites the real column names the audit verified; it contains the precise non-overclaimed statement ("schema-portable" / "would need to be rebuilt per business"); it explicitly disclaims validation elsewhere and is scanned for banned overclaiming phrases ("reusable platform", "works for any business", "proven to generalize", "validated on other"); it preserves the exact four-term terminology.
- **Live-rendering tests** (5): the new caveat actually renders on Overview (via `AppTest`, using the same "an expander's body executes regardless of collapse state" reasoning already established for P1-10's expander tests); the pre-existing `temporal`/`calibration` caveats still render unchanged, including the real, data-driven Brier score substitution; the source confirms exactly the intended `render_caveats([...])` argument list; the five OTHER pages' own `caveats.render_caveats(...)` calls are confirmed unaffected (neither their argument list nor the word "reusability" appears in their source); all six dashboard pages still load cleanly.

## 6. Complete test results (this run, fresh)

```
tests/test_agent_tools.py                 40 passed, 0 failed
tests/test_agent_orchestration.py        100 passed, 0 failed
tests/test_retention_intelligence_ui.py   44 passed, 0 failed
tests/test_manager_workflow.py             8 passed, 0 failed
tests/test_information_density.py          7 passed, 0 failed
tests/test_five_minute_demo_flow.py       10 passed, 0 failed
tests/test_reusable_architecture_story.py 11 passed, 0 failed   (new this task)
---------------------------------------------------------------------
TOTAL                                    220 passed, 0 failed
```

All pre-existing tests pass unmodified — this ticket required no test updates, only additions.

## 7. Live browser validation

Fresh Streamlit server started on port 8694. `ANTHROPIC_API_KEY` confirmed absent. Server log clean, no import errors.

Navigated to Overview, scrolled to the "Methodology & limitations" expander at the bottom of the page, clicked to open it, and confirmed the new section renders exactly as coded: "Why KKBox, and what would carry over to another business" as its own titled subsection (separated by the same horizontal rule the other caveats already use), stating the dataset provenance, the "What is KKBox-specific:" / "What is reusable:" split with the real column names rendered in code-formatted spans (`msno`, `is_cancel`, `payment_method_id`, `membership_expire_date`), and the precise non-overclaimed closing statement ending in "This has **not** been validated on any dataset other than KKBox's." The pre-existing `calibration` caveat directly above it (with its real, data-driven "Brier score: 0.118 on this dataset" figure) rendered unchanged in the same expander, confirming the addition is purely additive.

## 8. Confirmation: evaluator questions about dataset choice are now answerable from inside the product

Per the audit's own "Part 9" table, "Why KKBox?" and "Where does the data come from?" were graded weak/unanswerable from inside the product. Both are now directly answered by this one new section, reachable from Overview (the page a fresh evaluator lands on first) without leaving the app.

## 9. No unsupported claims

- The negative claim ("not validated on any dataset other than KKBox's") is stated explicitly and literally, not implied.
- No performance number, accuracy figure, or generalization claim was invented for a hypothetical second business.
- "Schema-portable" is the exact, deliberately narrow word the audit chose over "reusable platform" — carried through unchanged into the product copy, and a test (`test_reusability_caveat_never_overclaims_validated_elsewhere`) actively scans for and rejects the rounder, overclaiming phrasing.

## 10. Known limitations

- This is a text caveat inside an existing expander, not a dedicated standalone "Architecture" page. A fuller, dedicated page was considered (the old audit's own separate, now-superseded ticket system had flagged a "dedicated Methodology page" as its single biggest defensibility gap) but was judged to be a larger structural addition than "only add genuinely supported configuration/abstraction" calls for, and is not a distinct ticket in the current tracker (`P1-07`–`P1-15`, `P2-16`) for this session to invent scope for. If a future ticket wants a dedicated page, this caveat's content is the correct starting text for it.
- The caveat was added to Overview only, not to every page. Overview is the page a fresh evaluator lands on first and where "purpose understood" is already this session's established focus (P1-13); duplicating the same text on all six pages was judged to be redundant, not more defensible.
- The "9 cosmetic KKBox-naming spots" and exact `src/` column-reference counts are restated from the TASK_05 audit's own prior grep-based count, re-verified by me only at the level of "do these column names still appear in `src/`" (they do), not by re-running the audit's exact original count command myself against the current `dashboard/` tree line-by-line. If those counts have since drifted, the qualitative claim (cosmetic vs. structural) still holds regardless of the exact number, since I did not cite the exact "9" figure in the shipped product copy — only in this report, where it's attributed to the audit.

## 11. Confirmation

P1-15 and P2-16 (the only two tickets remaining in this tracker after this one) were not started as part of this ticket's own implementation. Per the continuation directive covering this ticket sequence, work proceeds automatically to P1-15 immediately after this ticket is marked `REVIEW` — documented in its own separate validation report.

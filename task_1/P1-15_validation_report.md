# P1-15 Validation Report — Integrated Product QA

**Tracker row:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, ID `P1-15`, Stage "Final QA", Priority P1.
**Status change:** `TODO` → `REVIEW` (this report; not `DONE` — reserved for independent sign-off).

## 1. Exact requirement from the tracker

**Issue:** "Sequential feature work creates cross-feature regression risk."

**Claude Fix Prompt:** "Perform a no-code-first audit, then full tests, syntax/import checks, fresh server, all six pages, manager workflow, customer/segment switching, unknown/missing-data/special-character IDs, no-key behavior, deep links, currency/terminology and desktop overflow. Fix only genuine P1 regressions and add regression tests where practical. Do not start P2."

**Acceptance Criteria:** "Full suite and browser flows pass; edge cases pass; currency/terminology consistent; notebooks/models/outputs/src untouched; remaining limitations documented; no P2 begins."

## 2. No-code-first audit

Before writing or changing any code, I ran the audit in the exact order the fix prompt lists:

1. Syntax check on all 18 dashboard files (`py_compile`) — clean.
2. Import check on all 10 `lib/` modules — clean.
3. Full existing regression suite (7 files, 220 tests at the start of this ticket) — 220/220 passing.
4. Fresh Streamlit server, no `ANTHROPIC_API_KEY`, clean startup log.
5. Live walkthrough of all six pages, the manager workflow chain, customer/segment switching, unknown/missing-data/special-character customer IDs, no-key behavior, deep links, currency/terminology, and a desktop-viewport overflow check.

## 3. Genuine P1 regression found and fixed

Step 5's currency check surfaced one real, previously-uncaught issue: **Overview's and Action Center's "More detail on this recommendation" expander showed a raw NT$ figure** (e.g. "200,463,967 NT$ in Historical Realized Revenue... median 1,788 NT$/customer"), while every other monetary figure in the product — including the same segment's own headline stat two lines above it — shows ₹.

**Root cause:** `outputs/marketing_action_plan.csv`'s `rationale` column is a notebook-generated, free-text sentence that embeds a raw `<number> NT$` mention directly in its prose — written before this project's ₹ display convention (P0-3) existed. `fmt_currency()` only formats numeric fields; it has no way to reach into a pre-written sentence, so this one text field silently bypassed the project's single centralized currency-conversion path. `components.recommendation_block()` (used by both `overview.py` and `action_center.py`) renders this `rationale` string verbatim into that expander.

**This is a genuine P1-level regression** against an already-established, already-tested product guarantee (P0-3: no raw NT$ anywhere a manager can see, verified repeatedly across P1-07 through P1-14's own reports) — not a new feature gap, and squarely inside this ticket's "currency/terminology consistent" acceptance criterion. It was fixed, per the fix-prompt's instruction to "fix only genuine P1 regressions."

**The fix** is display-layer only, and does not touch `outputs/marketing_action_plan.csv` or any other protected file:

- `dashboard/lib/theme.py` — added `convert_ntd_mentions_in_text(text: str) -> str`, a small regex-based helper (`re` newly imported) that finds every `<number> NT$` mention in a free-text string and rewrites it to the same ₹ figure `fmt_currency()` would show for that NT$ amount. The source file and the number itself are untouched; only the rendered string changes — the same "display-only conversion" discipline `to_inr`/`fmt_currency` already establish, extended to prose instead of a numeric field.
- `dashboard/lib/components.py` — `recommendation_block()` now passes `rationale` through `theme.convert_ntd_mentions_in_text(...)` before rendering it. This is the one shared function both `overview.py`'s and `action_center.py`'s recommendation cards call, so one fix covers both.

**Verified against every real rationale string** in the live `marketing_action_plan.csv` (all 7 segments), not just the one example first found — see §7.

**Known, deliberately out-of-scope related gap:** `agent_tools.recommend_action()` also returns this same raw `rationale` field verbatim in its tool result (for the LLM tool-calling path). `copilot_engine.py`'s deterministic answers never use this field (confirmed by source inspection — the currently-live, no-key path is unaffected), so this is not demonstrably broken today; it is a latent risk only if a live LLM is ever connected and chooses to quote the field verbatim. Fixing it would require importing `theme` (a UI-layer module with a Streamlit/Plotly dependency) into `agent_tools.py`, which is currently, deliberately UI-free ("no UI code" per its own module docstring) — a larger architectural change than this ticket's "smallest safe change" scope justifies given the risk is not currently observable. Documented here as a limitation (§9), not silently left unaddressed.

## 4. Files changed

- `dashboard/lib/theme.py` — added `convert_ntd_mentions_in_text()` and its `re` import.
- `dashboard/lib/components.py` — `recommendation_block()` applies the new conversion to `rationale` before rendering.
- `tests/test_integrated_product_qa.py` — new file, 17 tests.

No other file was touched. `notebooks/`, `models/`, `outputs/`, `src/` are unmodified — confirmed via `find ... -newermt` (0 files) and, additionally, via a new static regression test (`test_protected_directories_are_not_writable_targets_of_any_dashboard_code`) that scans every dashboard module for any write-mode file access against those paths, so this guarantee is now enforced by the suite itself, not only by a manual timestamp check.

## 5. Full-scope QA walkthrough, item by item

- **Syntax/import checks:** all 18 dashboard files compile cleanly; all 10 `lib/` modules import cleanly (both now regression-tested, see §7).
- **Fresh server:** started clean on a new port each time (8695, then 8696 after the fix), no import errors, no startup warnings beyond Streamlit's own routine cache-manager notices.
- **All six pages:** Overview, Priority Customers, Customer Value, Action Center, Customer 360, Retention Intelligence all confirmed live, zero exceptions, on this fresh server.
- **Manager workflow:** Overview → Priority Customers → Customer 360 → Retention Intelligence was re-walked live as part of this ticket's own audit (in addition to being independently verified in P1-11, P1-12, and P1-13's own reports this session) — no break.
- **Customer/segment switching:** verified live and via the existing, passing `copilot_context_id` regression tests (stale answers clear on switch) in `test_retention_intelligence_ui.py`.
- **Unknown customer ID:** verified live on both Priority Customers (search returns a clean "0 customers match" / empty-dataframe state, no crash) and Retention Intelligence (searched, then loaded data — resolved to the honest "I couldn't find that customer in the scored customer base" message).
- **Missing-data state:** verified live — typing a customer ID into Retention Intelligence's search box *before* clicking "Load customer data" attaches no context and shows no error (the large table genuinely isn't loaded yet, so no lookup is attempted) — never a false "not found" claim. Same gate confirmed on Customer 360.
- **Special-character customer IDs:** verified live on Priority Customers with a real msno-style string containing `+`, `/`, `=` — rendered and searched correctly, no encoding artifacts. Separately verified end-to-end via `agent_tools.get_customer()` against a real special-character msno pulled live from the dataset.
- **No-key behavior:** `ANTHROPIC_API_KEY` confirmed absent before every server start this ticket; every answer observed showed the honest `[AI synthesis unavailable...]` / deterministic-fallback banner, consistent with every prior ticket's own live validation this session.
- **Deep links:** the `pending_filter` (segment → Priority Customers) and `cust360_search` (search/list result → Customer 360) mechanisms were re-confirmed live and are covered by existing, passing regression tests in `test_manager_workflow.py` and `test_retention_intelligence_ui.py` — no change made, no break found.
- **Currency/terminology:** found and fixed the one genuine gap described in §3; re-verified clean afterward, across all six pages, via a new automated sweep (§7) — not just the two pages where the bug was found.
- **Desktop overflow:** checked `document.documentElement.scrollWidth` vs. `window.innerWidth` via JavaScript on the widest, most data-dense page (Priority Customers, a 7-column dataframe) — equal, zero horizontal overflow, at the viewport size available in this environment (~1536px).

## 6. Complete test results (this run, fresh)

```
tests/test_agent_tools.py                 40 passed, 0 failed
tests/test_agent_orchestration.py        100 passed, 0 failed
tests/test_retention_intelligence_ui.py   44 passed, 0 failed
tests/test_manager_workflow.py             8 passed, 0 failed
tests/test_information_density.py          7 passed, 0 failed
tests/test_five_minute_demo_flow.py       10 passed, 0 failed
tests/test_reusable_architecture_story.py 11 passed, 0 failed
tests/test_integrated_product_qa.py       17 passed, 0 failed   (new this task)
-------------------------------------------------------------------
TOTAL                                    237 passed, 0 failed
```

All pre-existing tests pass unmodified — this ticket required no updates to any existing test, only additions.

## 7. Tests added (`tests/test_integrated_product_qa.py`, 17 tests)

- **Syntax/import** (2): every dashboard file compiles; every `lib/` module imports cleanly.
- **All six pages** (1): a single authoritative sweep confirming zero exceptions across all six.
- **Currency/terminology, cross-page** (2): no page shows a raw NT$ figure outside the one already-documented "hrr" methodology caveat's own disclosure sentence (which itself must legitimately name NT$ once, to explain what it's converting *from*); no page mislabels Model Risk Score as a probability.
- **Unknown / special-character / missing-data IDs** (5): a real special-character msno round-trips correctly through `get_customer()`; an unknown ID returns a clean, honest `ok=False` with `data=None`, never a crash; Retention Intelligence silently ignores a search value entered before data is loaded (no false "not found" claim); Priority Customers' zero-results state renders cleanly; Customer 360's `hrr` caveat call is confirmed unchanged and reachable behind only its already-audited row-selection gate (its deepest state requires a live dataframe row-selection event AppTest cannot simulate, so that specific state was verified live in the browser instead — see §5 — and this test regression-guards the two facts that keep that live check valid).
- **The specific fix** (5): `convert_ntd_mentions_in_text()` correctly rewrites a real rationale-style sentence (NT$ gone, ₹ present, the actual number preserved and correctly re-denominated, everything else in the sentence untouched); it leaves NT$-free text byte-identical; it never raises on malformed input; every real `rationale` string in the live `marketing_action_plan.csv` (all 7 segments, not just the one example first found) converts cleanly; Overview's and Action Center's actual rendered "More detail on this recommendation" expanders show zero raw NT$.
- **No-key / protected directories** (2): `ANTHROPIC_API_KEY` confirmed absent; a static source scan confirms no dashboard module opens a protected-directory path in write mode.

## 8. Confirmation: notebooks/models/outputs/src untouched

Confirmed both ways: `find notebooks models outputs src -newermt "2026-09-11 16:30:00"` → 0 files, and the new `test_protected_directories_are_not_writable_targets_of_any_dashboard_code` test statically scans every dashboard module for any write-mode file access against those paths. `outputs/marketing_action_plan.csv`'s `rationale` column — the actual source of the bug this ticket fixed — was read, never edited; the fix lives entirely in the display layer.

## 9. Known limitations

- `agent_tools.recommend_action()`'s returned `rationale` field still contains the raw NT$ mention, unconverted — a latent, currently-unobservable risk (see §3) deliberately deferred rather than forcing an architectural boundary change (`agent_tools.py` gaining a UI-layer dependency) to fix something not currently reachable in this no-API-key environment. If a real `ANTHROPIC_API_KEY` is ever configured, this should be revisited alongside whatever live LLM smoke test P1-12's own report already flagged as outstanding.
- The desktop-overflow check was performed at the one viewport size actually available through this session's browser automation tooling (~1536px); an explicit resize to a narrower common laptop width (e.g. 1280px) was attempted but did not change the reported viewport in this environment, so overflow at smaller widths was not independently re-verified this ticket. No overflow was found at the size that was tested, on the widest, most data-dense page in the product.
- This ticket's scope was auditing and fixing regressions in what P1-07 through P1-14 already built — it did not re-examine analytical correctness (model outputs, thresholds, scores), which remains outside every ticket's scope in this sequence by design.

## 10. Confirmation: no P2 begun

Per the fix prompt's explicit instruction, no P2 ticket was started, inspected for implementation, or touched as part of this ticket's work. `P2-16` (the only P2 row in this tracker) remains at `TODO`.

## 11. Confirmation

This was the last ticket in the `P1-xx` range of this tracker. Per the continuation directive covering this ticket sequence, work proceeds automatically to `P2-16` — the one remaining ticket — immediately after this ticket is marked `REVIEW`, documented in its own separate validation report, after which a final consolidated report covering the full P1–P2 sequence will be written.

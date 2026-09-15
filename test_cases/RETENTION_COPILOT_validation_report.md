# Validation Report — Retention Copilot: Grounded Decision Assistant

**Status: REVIEW** — see §10 on tracker status (no existing tracker row for this feature).
**Priority:** CRITICAL | **Category:** Product Feature
**Date:** 2026-09-09 (updated same day — §0 below — with a transparency fix)

---

## 0. Update: LLM-unavailable transparency fix

Follow-up fix, same day. The original implementation silently fell back to the deterministic
answer whenever LLM synthesis wasn't used, with only a static page-top notice that covered the
"no key configured" case specifically -- an actual provider failure (bad request, network error,
malformed response) after a key was set would have fallen back with **no visible indication at
all** that synthesis was attempted and failed. That is exactly the kind of silent failure the
brief prohibits.

**Fix (no recommendation logic touched):**
- `lib/copilot_engine.py`: `try_llm_synthesis()` now returns `(answer_or_None, reason_or_None)`
  instead of just the answer. The three failure paths (`not configured`, `request failed`,
  `malformed response`) each carry their own human-readable reason string. Both public
  entrypoints (`answer_customer_question`, `answer_segment_question`) attach that reason to the
  deterministic answer's `llm_unavailable_reason` field whenever synthesis wasn't used --
  previously this field existed on `CopilotAnswer` but was never populated.
- `lib/components.py`: `copilot_answer_block()` now renders one line directly under the
  recommendation, every time, unconditionally: *"This is the deterministic, evidence-backed
  answer -- AI-assisted synthesis was not used (\<reason\>)."* when a fallback occurred, or *"AI-
  synthesized from the evidence below."* when it didn't. Previously this state was only
  discoverable from a static caption at the top of the whole page (which only checked whether a
  key was configured, not whether a configured call actually failed) and a terse `· AI-
  synthesized` suffix buried in the bottom "Evidence used" line.
- No deterministic answer template, evidence line, or recommendation was changed -- this is
  presentation of an existing field, not new logic.

**Re-validated after the fix:**
- Offline suite (`scratchpad/test_copilot.py`) extended from 32 to 34 assertions -- test 8 updated
  for the new `(answer, reason)` return shape, plus two new assertions: the fallback answer
  carries a non-empty `llm_unavailable_reason`, and it's the exact human-readable sentence ("no AI
  provider is configured for this session"), not an internal code. **34/34 passed.**
- Live: restarted the server fresh (a mid-session component edit didn't take effect until
  restart -- Streamlit's file watcher does not reliably hot-reload an already-imported `lib`
  module used by other modules; noted here in case it recurs). Asked a segment question
  ("Tell me about At-Risk, Auto-Renew Off customers.") with no API key configured, and confirmed
  the new caption renders directly under the recommendation: *"This is the deterministic,
  evidence-backed answer -- AI-assisted synthesis was not used (no AI provider is configured for
  this session)."*
- Live Customer 360 → Copilot flow re-run end-to-end (Priority Customers → select customer →
  Customer 360, prefilled → "Ask Retention Copilot about this customer →" → Copilot opens with
  the same customer attached, no stale answer) -- unchanged and still correct; this pass only
  added the transparency line to the answer rendering, not the handoff mechanism.

---

## 1. Architecture

Implemented exactly the required pipeline:

```
question -> customer/segment context (exact-match retrieval)
         -> structured evidence bundle
         -> deterministic template answer (always computed -- guaranteed baseline)
         -> optional LLM synthesis over the SAME bundle, strict guardrails
            (falls back to the deterministic answer on any failure or malformed output)
```

New files, each with one job:

| File | Role |
|---|---|
| `dashboard/lib/copilot_data.py` | Deterministic retrieval only. Exact-ID customer lookup (never fuzzy/semantic), segment stats, Champions comparison, top SHAP drivers. Returns small structured dicts, never a dataframe. |
| `dashboard/lib/llm_provider.py` | The **only** file that imports the `anthropic` SDK. `is_configured()` / `complete()`. Any failure (no key, no package, network, bad response) raises one caught exception type; never propagates. |
| `dashboard/lib/copilot_engine.py` | Evidence-bundle assembly, all deterministic answer templates, the free-text intent classifier, the LLM system prompt + strict response parser, and the two public entrypoints the page calls. |
| `dashboard/pages/retention_copilot.py` | Rewritten. Customer mode / segment mode, suggested questions + free text, renders via the new `components.copilot_answer_block`. |

The 971K-row customer table is never sent to an LLM and is not reloaded per question — it uses the same `st.cache_data` lazy-load pattern as Customer 360, shared across both pages via the same `lookup_loaded` session flag.

## 2. Retrieval sources

Exactly the sources listed in the brief, all already-validated project files, nothing new authored:

- **Customer facts**: `customer_segments.csv` + `risk_scoring_predictions.csv` + `customer_value_tiers.csv` + `calibrated_probabilities.csv` (same merge Customer 360 uses). No payment method, demographics, or listening behavior are included, because none of those exist in this project's data — omitted, never fabricated.
- **Model explanation**: `shap_feature_importance.csv` (top 5 global drivers).
- **Segment definitions/stats**: `marketing_action_plan.csv` (all 7 segments) + `segment_summary.csv` (6 of 7 — Stable/Monitor has no row there; that gap is surfaced as "not available," never guessed).
- **Action framework**: `marketing_objective`, `intervention_intensity`, `rationale` from `marketing_action_plan.csv`, plus the already-existing `SHORT_WHY_BY_SEGMENT` / `SHORT_ACTION_BY_SEGMENT` and the new `AVOID_BY_SEGMENT` (added last session) from `lib/data.py`.
- **Methodology**: reused verbatim from `lib/caveats.py`'s existing bodies (causality, calibration, HRR definition) via the standard caution/confidence text baked into every answer.

## 3. LLM/provider implementation

- Provider: Anthropic Messages API, isolated entirely inside `llm_provider.py`. Model/max-tokens are constants in that one file.
- Key read from `ANTHROPIC_API_KEY` only — never hard-coded, never logged, never sent to the browser. No key exists in this environment (`os.environ` check confirmed `False`), so **the LLM path could not be live-tested end-to-end with a real completion** — see §10 for what this means honestly.
- The `anthropic` package was installed (`requirements.txt` updated, marked optional) so the code path is real and importable, not stubbed.
- System prompt enforces: evidence-bundle-only facts, fixed terminology, no causal language, the exact `RECOMMENDATION/WHY/EVIDENCE/WHAT TO DO/WHAT TO AVOID/CONFIDENCE-BASIS/CAUTION` structure.
- `_parse_llm_response()` is a strict parser: a response missing any of RECOMMENDATION/WHY/WHAT TO DO/CAUTION is treated as a failed call and discarded — the deterministic answer is used instead. Verified offline with both a well-formed sample response (parses correctly, evidence bullets extracted) and a free-prose response (correctly rejected).

## 4. Customer-context handling

- Customer 360 and Retention Copilot share one `st.session_state["cust360_search"]` key (the same mechanism validated in the prior pass) — a customer selected on Priority Customers or Customer 360 opens on Retention Copilot automatically via the new **"Ask Retention Copilot about this customer →"** CTA added to Customer 360's profile. No copy/pasting required.
- No customer selected → automatic **segment/general mode** (segment picker + segment-level questions), not an empty/broken state.
- **A real stale-state bug was found and fixed during validation**: switching from a segment question to a different customer (or vice versa) via the CTA could leave the *previous* context's answer displayed, unprompted, under the new context's header. Fixed by tracking a `copilot_context_id` (the resolved customer ID or chosen segment) and clearing `copilot_asked` whenever it changes. Re-tested end-to-end after the fix (§7) — confirmed a fresh customer landing via the CTA shows no leftover answer.

## 5. Guardrails

All from the brief, all enforced in `copilot_engine.py` and verified by the offline test suite (§6):

- Unknown customer → `"I couldn't find that customer in the scored customer base."` (exact required text).
- Missing field (e.g. `discount_rate` unavailable) → `"Discount sensitivity cannot be established reliably from the available evidence."`, never a guess or a silent 0%.
- Discount only recommended for the `At-Risk, Price-Sensitive` segment; every other segment gets the explicit "not indicated" framing.
- "What happens if we do nothing?" never produces a revenue-loss forecast — explicit refusal per the brief's required wording.
- Terminology is fixed: "Model Risk Score" (never phrased as a bare probability), "Estimated Churn Probability", "Historical Realized Revenue" (never CLV/Lifetime Value/Future Revenue).
- No causal language (`causes`, `will reduce churn`, `guarantees`, `will save revenue`) anywhere in the deterministic templates.
- Every grounded answer carries the standard caution line noting no campaign-response experiment exists in this dataset.
- "Evidence used" line names sources (`Customer 360`, `Risk Scoring`, `Segment Framework`, `Marketing Action Framework`) — no filesystem paths, no fabricated citation URLs.

## 6. Test results (offline, deterministic — `scratchpad/test_copilot.py`)

**32/32 passed** originally; **34/34 passed** after the §0 transparency fix added two assertions. Covers required items 1-12: known customer lookup, unknown customer, a real customer ID containing regex-special characters (`+`/`/`, resolved via exact `==` match — immune to the earlier regex bug by construction), a High-risk and a Low-risk customer, a segment-level question (exact-value assertions against `segment_summary.csv`'s real numbers — 113,820 customers, median recency 20 days, median tenure 809 days), missing-field behavior (Stable/Monitor absent from `segment_summary.csv`; a customer with `discount_rate=None`), no-API-key behavior, and the terminology/causality guardrail scans. A real bug was caught by test 7 (missing-field): `discount_rate=None` crashed evidence formatting with a `TypeError` — fixed with a dedicated `_fmt_rate()` helper that renders "not available" instead of crashing or guessing 0%.

AppTest (`scratchpad/apptest_copilot.py` + the existing 6-page suite): all pages pass with no exception, including the Copilot's segment mode (no data load required), a segment question click, the data-load gate, and Customer 360's filtered render with the new CTA present. The one known, pre-existing harness limitation (Overview's `st.page_link` failing under `AppTest.from_file()`'s isolated page registry) is unchanged and already documented in the two prior validation reports — not a regression.

## 7. Live-browser results

Full walkthrough on a fresh server, via `claude-in-chrome`:
- Segment mode renders without loading customer data; asking "Tell me about At-Risk, Auto-Renew Off customers" reproduced the brief's own example numbers exactly (113,820 customers, 41.1% churn, 0% auto-renew, median recency 20 days, median tenure 809 days, ₹525.22M — matching Action Center's figure for the same segment).
- **Full real-world flow re-tested end-to-end**: Priority Customers → select a High-risk customer → Customer 360 (search auto-prefilled) → "Ask Retention Copilot about this customer →" → Copilot opens with the exact same customer already attached, badges and stats matching Customer 360 exactly, no stale answer from an earlier segment question (confirms the fix in §4).
- Asked "Should we offer a discount?" on that customer (segment: At-Risk, Auto-Renew Off) → correctly answered "Don't lead with a discount," with all 9 evidence lines, What to do ("Re-engage"), Confidence/basis, Caution, and Evidence-used sources all rendering in the required structure.
- No horizontal overflow on any of the 6 routes (checked via `scrollWidth`/`clientWidth`).
- "Customer not found" message (exact required text) confirmed via an intentionally-mistyped ID.

## 8. Security checks

- No API key or secret appears in any source file — `os.environ.get("ANTHROPIC_API_KEY")` only.
- No filesystem path, internal model artifact, or implementation detail is ever rendered to the page.
- Customer-context isolation: the stale-state bug found in §4 was specifically a *cross-context leakage* risk (a previous context's answer appearing under a new one) — fixed and re-verified. Since customer context is resolved fresh from `st.session_state["cust360_search"]` on every rerun (never cached against a stale customer object) and the fix clears any prior answer on a context change, one customer cannot receive another's evidence through chat history.
- No prompt-injection surface currently exists functionally (no LLM call is live in this environment), but the system prompt's evidence bundle is a JSON dump of already-sanitized, already-typed fields (numbers, fixed enum strings) — a manager's free-text question is the only untrusted input reaching the LLM, and it cannot inject new "facts" since the model is instructed to use only the evidence bundle. This is a design-level mitigation, not something exercised by a live call in this session.

## 9. Performance checks

- Segment-level questions never touch the 971K-row table.
- Customer lookup reuses `data.load_customer_lookup_data()`'s existing `st.cache_data` cache — no repeated load per chat message, and the cache is shared with Customer 360 (confirmed live: navigating Priority Customers → Customer 360 → Copilot did not re-trigger the load gate on Copilot).
- No LLM client is constructed until a question is actually asked and `is_configured()` is true — nothing expensive initializes on page load.

## 10. Known limitations

- **The LLM synthesis path was not live-tested with a real completion.** No `ANTHROPIC_API_KEY` exists in this environment. Everything reachable without a key — which is what actually runs for the user unless they configure one — was fully tested (§6, §7). The parser and prompt-construction logic were verified offline against synthetic sample responses. This is stated plainly rather than fabricating a "successful AI test."
- Free-text question routing is keyword-based when no LLM is configured — a question that doesn't match any keyword returns a clarification message rather than a guess, by design, but this means unusually-phrased free-text questions may not route correctly without an LLM configured.
- The pre-existing segment-vs-risk-tier divergence and occasional `NaN` tenure values (documented in prior reports) are unchanged and can still surface in the Copilot's evidence for an affected customer.

## 11. Files changed / added

New: `lib/copilot_data.py`, `lib/llm_provider.py`, `lib/copilot_engine.py`. Modified: `lib/components.py` (+`copilot_answer_block`), `pages/retention_copilot.py` (rewritten), `pages/customer_360.py` (+1 CTA line), `requirements.txt` (+optional `anthropic`). Not touched: any notebook, `src/`, any file under `outputs/`, any file under `models/`.

## 12. Tracker status

The tracker (`KKBox_Retention_Intelligence_Issue_Tracker.xlsx`) has no existing row for "Retention Copilot" — it was introduced as part of the Master Restructure's information architecture, not as its own ticket ID. Rather than inventing a new tracker row unprompted, **no tracker change was made this pass**; flagging this here so the user can decide whether to add one. All prior rows (D-02–U-01 = REVIEW, U-02 = TODO) are unchanged.

Stopping here per instruction — no further redesign work started.

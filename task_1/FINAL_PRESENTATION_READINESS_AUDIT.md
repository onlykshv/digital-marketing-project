# Final Presentation-Readiness Audit

**Date:** 2026-09-18
**Scope:** audit only — no new features, no new architecture, no changes to analytical logic,
`notebooks/`, `models/`, `outputs/` or `src/`.
**Method:** the actual running application inspected in a real Chrome browser against a freshly
started server, plus the full test suite, plus source/data verification of every claim made below.

Everything in this document was observed. Where something could not be verified it is labelled
**UNVERIFIED**. One item (A5) was a reachable crash and met the "tiny, safe, clearly necessary"
bar, so it was fixed and is recorded as fixed; nothing else in this document was changed.

---

## Verification basis

| | |
|---|---|
| Python | 3.12.10 (`C:\Users\Keshav\AppData\Local\Programs\Python\Python312\python.exe`) — no project venv exists; this is the interpreter the project runs on |
| pytest | 9.1.1, installed this session (was genuinely absent); `requirements.txt` deliberately unchanged |
| Streamlit | 1.63.0 |
| Test command | `python -m pytest tests/ -p no:cacheprovider -q` run from `D:\digital-marketing-project` |
| Test result | **256 passed, 0 failed, 0 skipped** (~55s) |
| Server | `python -m streamlit run dashboard/app.py --server.port 8513 --server.headless true --browser.gatherUsageStats false` |
| Browser | real Chrome, viewport 1536×720 CSS px (this machine's maximum at 125% display scaling) |
| `ANTHROPIC_API_KEY` | **absent**; `llm_provider.is_configured()` returns `False` |
| LLM synthesis | **never exercised live.** Every answer seen in this audit came from the deterministic fallback. No claim here rests on live model behaviour. |

Pages walked live: Overview, Priority Customers, Customer Value, Action Center, Customer 360,
Retention Intelligence. Flows walked live: customer → Customer 360 → Retention Intelligence;
segment (via Overview CTA) → Retention Intelligence; suggested prompt; free-text prompt;
free-text → suggested-prompt interaction; a search/list result; the no-API-key path; the
"data not loaded yet" guidance path.

---

## A. MUST FIX BEFORE PRESENTATION

### A1. The hero answer contradicts itself: the customers it says to contact first are labelled "Monitor only"

This is the single most serious finding, and it lands on the flagship question.

Asked **"Who should we contact first?"** on Retention Intelligence with customer data loaded, the
live answer was:

> "These are the highest-priority customers to contact first, ranked by Model Risk Score.
> Result summary: 22,692 customers match — the top 5 by Model Risk Score are below."

…followed by five customers, **every one of them** rendered as:

> `HIGH RISK` · `LOW/MEDIUM VALUE` · **Monitor only** · Stable / Monitor

An evaluator's first question will be: *why is the #1 customer you want me to contact the one you
also tell me to do nothing about?*

**How widespread.** Ranked by `risk_score_full` descending over `outputs/customer_segments.csv`:
**14 of the top 20** and **56 of the top 200** customers are labelled `Stable / Monitor`. The top
of the queue is where this is *most* concentrated, which is exactly where a demo starts.

**Root cause (verified in the data, not inferred).** The two segment vocabularies disagree:

- `outputs/marketing_action_plan.csv` defines **7** groups, including
  `Unmatched At-Risk (no segment)` — 5,890 customers, 0.61% of base, **64.7% actual churn**,
  whose correct treatment is *"Standard tier-based treatment … Low-cost automated (email, in-app
  nudge)"*.
- `outputs/customer_segments.csv` (the per-customer labels the dashboard reads) contains only
  **6** segment values. `Unmatched At-Risk (no segment)` is not one of them. Those 5,890
  customers — **1,255 High-risk and 4,635 Medium-risk** — carry `Stable / Monitor` instead, whose
  treatment is *"No special campaign; low churn risk and no standout value signal to act on"* →
  **"Monitor only" / "Avoid proactive outreach"**.

Cross-tab of the loaded customer table confirms it:

| risk_tier | … | Engaged Low-Risk (Champions) | Stable / Monitor |
|---|---|---|---|
| High | (21,437 across the 4 at-risk segments) | 0 | **1,255** |
| Medium | (102,408 across the 4 at-risk segments) | 0 | **4,635** |
| Low | 0 | 321,006 | 520,219 |

**Why those customers fell through the segment rules.** The four named at-risk rules key on
auto-renew off, tenure ≥ 730d, tenure < 180d, or discount > 5%. **3,241 of the 5,890** have
`tenure_days_at_cutoff = NaN`, so they can match neither tenure rule; the rest have auto-renew ON
and discount ≤ 5%. (Base-wide, 109,993 of 970,960 customers — 11.3% — have NaN tenure.)

**The dashboard is not at fault.** It handles all seven groups correctly: `copilot_data.SEGMENTS`
lists all seven, and `data.py` carries the right action, rationale and "avoid" line for
`Unmatched At-Risk (no segment)`. The per-customer label file is the one that lost the group.

**Not fixed, deliberately.** The root cause lives in `outputs/` (produced by `notebooks/`/`src/`),
all protected by this session's rules. The three ways forward:

1. **Correct the label upstream** — regenerate `customer_segments.csv` so at-risk customers that
   match no named rule carry `Unmatched At-Risk (no segment)`. Correct, but requires
   `notebooks/`/`src/`, so it is a separate, sign-off task, not a pre-presentation edit.
2. **Remap at the display layer** — where `risk_tier ∈ {High, Medium}` and
   `segment == "Stable / Monitor"`, show the seventh group and its action. Small code, but it is a
   genuine logic change to what the product asserts, and needs your decision, not mine.
3. **Present it deliberately** as a found data-quality issue: *"the segmentation rules leave 5,890
   at-risk customers unmatched, 11% of the base has no tenure recorded, and the per-customer label
   file collapses that group into the default bucket — here is where the pipeline needs another
   pass."* This costs 30 seconds and turns the worst finding into evidence of rigour.

**Recommendation: option 3 tomorrow, option 1 afterwards.** Do not leave it unmentioned — it is
visible on the first click of the hero workflow.

### A2. One Customer 360 screen states both "100% churn probability" and "low churn risk"

Same root cause as A1, but worth listing separately because it is visible on a *single screen*
with no scrolling, for customer `2eO88OKrDzgAI2jGApB3ifm3yhEeCQNT2EZI2yv4ft0=` (the top row of the
default Priority Customers queue — i.e. the customer a demo naturally opens first):

- Header: `HIGH RISK` `LOW VALUE` `STABLE / MONITOR`, **ESTIMATED CHURN PROBABILITY 100%**,
  **MODEL RISK SCORE 1.00**
- "What should we do?" → **MONITOR ONLY** — *"No special campaign; low churn risk and no standout
  value signal to act on."*
- "Why this action?" → *"**Low risk** and no standout value signal to act on."*
- "What should we avoid?" → *"Avoid proactive outreach — no risk or value signal currently in the
  framework justifies spend on this customer."*

Retention Intelligence reproduces it too: asked *"Why is this customer at risk?"* for that
customer, the answer's own "Why it matters" line reads *"Low risk and no standout value signal to
act on."*

Handle with the same framing as A1. If you pick one sentence to rehearse, make it this one.

### A3. "Estimated Churn Probability: 100%" is an unqualified certainty claim

`outputs/calibrated_probabilities.csv` reaches **exactly 1.000000** at the top and **exactly
0.000000** at the bottom; **1,277 customers** round to a displayed "100%". The app is otherwise
scrupulous about probability language ("Model Risk Score is not a calibrated probability",
"Estimated Churn Probability is the calibrated figure"), which makes a bare "100%" stand out as
the one place it overclaims — and it appears on the customer a demo opens first.

A display-only floor/ceiling (e.g. `<1%` / `>99%`) would fix it in one function, but it changes a
displayed analytical figure, so it was **not applied**. Either apply it with your sign-off, or be
ready to say "isotonic calibration saturates at the extremes; read that as ≥99%, not as certainty."

### A4. The segment-mode "How does this segment compare with Champions?" button does not answer its own question

Verified live: with `At-Risk, Auto-Renew Off` in focus, clicking that button produced the generic
segment overview — **the word "Champions" did not appear anywhere in the answer**, which was
byte-for-byte the same answer as "Why is this segment important?".

Verified in code: `copilot_engine.classify_segment_intent()` has branches for
`champions_importance`, `which_segment_priority` and `high_touch_candidates`, and no branch for a
comparison — so the question falls through to `segment_overview`. The **customer**-mode
equivalent ("How does this customer compare with Champions?") *does* work
(`classify_customer_intent` → `compare_champions`), which makes the gap easy to miss.

This only affects the deterministic path — which is the only path available without an API key,
i.e. exactly what will be demonstrated.

**Not fixed** (both remedies change product behaviour): either remove that one button from
segment mode — the precedent P1-07 already set when it removed customer-scoped buttons that could
never yield a real answer — or route the intent to the already-validated
`agent_tools.compare_to_champions(segment=…)`, which needs a new answer template. Until then,
**do not click it in segment mode**; the customer-mode version is safe and works.

### A5. FIXED — a reachable crash three clicks from the flagship page

Retention Intelligence's segment picker offers all seven segments, so a manager can select
`Unmatched At-Risk (no segment)` and click *"View Unmatched At-Risk (no segment) customers in
Priority Customers →"*. Because that value is not among Priority Customers' multiselect options
(they come from the 6 labels actually present in the data — see A1), Streamlit raised:

```
StreamlitDefaultNotInOptionsError: The default value 'Unmatched At-Risk (no segment)'
is not part of the options.
```

— a full red traceback in place of the page.

**Fix applied** (`dashboard/pages/priority_customers.py`): a handed-over filter value is now
restricted to what the page can actually offer, so an unrepresented group degrades to "no segment
filter" instead of taking the page down. Verified live in Chrome (the handoff now lands on the
normal at-risk queue with the risk-tier default intact) and covered by three new regression tests.

**Residual limitation:** the landing page is then *unfiltered* rather than showing those 5,890
customers — they cannot be filtered to at all until A1's root cause is addressed.

---

## B. SHOULD KNOW / EXPLAIN DURING THE PRESENTATION

*(Not defects to fix tonight — things to have an answer ready for.)*

**B1. Every answer opens by saying the AI is unavailable.** With no key, each response leads with
`[AI synthesis unavailable: no AI provider is configured for this session — showing the grounded
deterministic answer]` and closes with *"Deterministic answer — AI synthesis not used."* This is
exactly the honesty the project was built for, but it leads with a negative on a product whose
hero is an assistant. Either set `ANTHROPIC_API_KEY` beforehand — in which case **the LLM path is
UNVERIFIED in this environment and would be demonstrated untested** — or open with the design
claim: *"the tool layer is deterministic; the model only narrates it, and when there is no model
the answer is still complete."* The second framing is stronger and carries no risk.

**B2. Never type a URL or refresh during the demo.** A full page load starts a new Streamlit
session: the "Load customer data" gate returns and any carried customer/segment context is lost.
Observed repeatedly this session. Navigate only with the in-app top nav.

**B3. Budget for the data load.** The 971K-row customer table takes ~7s in-process and ~10–15s in
the browser, and each of Priority Customers, Customer 360 and Retention Intelligence gates on it
once per session. Click "Load customer data" early, before anyone is watching a spinner.

**B4. Two numbers in the segment evidence have no currency and one base average is negative.**
The `defining_characteristics` text (from `marketing_action_plan.csv`, protected) renders verbatim
inside Retention Intelligence's Evidence and "Why it matters" lines:
*"avg revenue/txn **305** vs **150** overall"* — unitless, neither ₹ nor NT$ — and
*"avg discount rate 46% vs **-2.5%** overall"*, a negative average discount rate. P1-15's
`theme.convert_ntd_mentions_in_text` cannot help: these numbers carry no `NT$` marker to convert.

**B5. Expect "Model Risk Score 1.00?"** It is the raw model output, not a probability. The app
says so in three places; make sure you say it before you are asked.

**B6. Expect a data-quality question about tenure.** 109,993 of 970,960 customers (11.3%) have no
tenure recorded; Customer 360 shows "—" / "not available" (correct, and the P2-16 fix is working —
no "nan days" anywhere). It is also the mechanical cause of A1.

**B7. The URL still says `retention_copilot`.** `localhost:8513/retention_copilot` is visible in
the address bar while the product is called "Retention Intelligence". The word "Copilot" appears
nowhere in the UI (only in code comments and module names — verified). Renaming the page file
would touch the nav, every cross-page link and several tests: not a pre-presentation change.

**B8. The header briefly shows "5 more" before the nav appears.** On a fresh load the six nav
links are still being measured and Streamlit renders a `5 more` overflow label for the first
seconds. I initially recorded this as a defect and then disproved it: it resolves on its own, the
full six-link nav renders correctly, and it is **not** caused by the project's CSS (verified by
setting the toolbar's `padding-left` to 0 on a restarted server — no change; the experiment was
reverted and `theme.py` is byte-identical to HEAD).

**B9. The high-risk × high-value pocket is small.** 2.4K customers at 91.6% observed churn. The
narrative handles this well ("high risk and high value rarely coincide at scale"), but be ready
for "is 2,400 customers worth a platform?" — the answer is the 113.8K / ₹525.22M
`At-Risk, Auto-Renew Off` segment, which is where the money actually is.

**B10. Streamlit's "Deploy" button and hamburger menu are visible top-right on every page.**
Launch with `--client.toolbarMode minimal` to hide them. No code change needed.

---

## C. OPTIONAL — DO NOT SPEND TIME ON NOW

**C1.** `dashboard/.streamlit/config.toml` only applies when the working directory *is*
`dashboard/`. The README's documented command (`streamlit run dashboard/app.py` from the repo
root) leaves `theme.primaryColor` and `theme.backgroundColor` resolving to `None` (verified by
comparing `st.get_option` from both directories). **No visible difference was found** — `theme.py`
injects its own complete CSS, and a live scan for Streamlit's default red `#FF4B4B` found zero
occurrences on the pages inspected. Cosmetically inert; left alone.

**C2.** Customer 360's grid column header reads `HRR (₹)` unexpanded. Spelled out in full
everywhere it matters, including on the same page's stat row.

**C3.** The repo root holds ~12 scratch files (`scratch_server*.log`, `scratchpad_p1*_spec.txt`,
`streamlit_p1*.log`). Invisible in the app; only matters if someone browses the repository.

**C4.** The three CSV download buttons (Action Center, Priority Customers, Customer 360) are
wired to real in-memory DataFrames — verified at source level, **not exercised live** (no file was
downloaded during this audit).

---

## The fourteen questions, answered directly

**1. What is the project's hero?**
Retention Intelligence — the grounded assistant on `pages/retention_copilot.py`. But what makes it
defensible is underneath it: a deterministic 9-tool layer, an explicit tool allow-list, and an
answer that degrades to a complete grounded response with no model at all. The hero is not "we
added AI"; it is "the AI cannot invent anything, and here is why."

**2. Can a new evaluator understand the business problem in 60 seconds?**
Yes. Overview opens with *"129.7K customers need attention / 22.7K of them are in the highest-risk
tier, out of 971.0K customers scored"*, then one sentence of framing, then four KPIs
(971.0K scored · 9.0% churn · ₹5.43B realized revenue · validated on future data). That is the
problem, the scale and the credibility claim above the fold.

**3. Can they understand what Retention Intelligence does?**
Mostly yes — "RETENTION OPERATIONS ASSISTANT" eyebrow, a one-line statement of what it answers, an
always-present grounding strip ("Grounded in the full scored base…" / "Segment in focus…" /
"Analysing customer…"), and prompts grouped as *See what's happening* → *Find who needs
attention*. The one thing working against it is B1: the first line of every answer says the AI is
unavailable.

**4. Can the manager workflow be demonstrated in under 5 minutes?**
Yes, with room to spare. Walked live: Overview → hero CTA → Retention Intelligence (segment in
focus, segment answer) → Priority Customers (129,735 matching, filters, SHAP explanation) → select
a row → Customer 360 (full profile) → "Ask Retention Intelligence about this customer" → customer
answer. Roughly 2–3 minutes including one ~10–15s data load. Every handoff carried its context
correctly.

**5. Does the product communicate WHAT / WHO / WHY / WHAT SHOULD WE DO?**
Yes, and unusually explicitly — each page's H1 *is* one of those questions: "Where should KKBOX
act?", "Who should we save?", "Who is worth saving?", "What should we do?", "What should we do for
this customer?". Answers carry Evidence → Why it matters → Recommended action → Avoid →
Confidence/limitations. **The exception is A1/A2**, where WHY and WHAT-TO-DO contradict each other
for precisely the customers at the top of the queue.

**6. Any remaining confusing labels?**
No significant ones. `HRR (₹)` as a bare column header (C2) is the only abbreviation not expanded
in place. "Model Risk Score" vs "Estimated Churn Probability" could confuse, but the app
distinguishes them explicitly wherever both appear.

**7. Any stale terminology?**
Only the `/retention_copilot` URL path (B7). No user-visible "Copilot" string anywhere — `app.py`
declares `title="Retention Intelligence"` and the browser nav confirms it. Remaining "Copilot"
mentions are in code comments and module filenames.

**8. Any inconsistent currency?**
₹ is consistent across all six pages (₹5.43B, ₹525.22M, ₹3.5K, ₹3513…). Two exceptions, both in
B4: the unitless `305 vs 150` revenue-per-transaction figures, and a negative `-2.5%` base-average
discount rate. The one deliberate `NT$` mention is the methodology disclosure of the display-only
conversion, which is correct and should stay.

**9. Any misleading probability / correlation / causality language?**
The framework is genuinely careful, and this is a strength to point at: *"an observed association,
not a causal guarantee"*, *"not a controlled experiment — there is no campaign-response data in
this dataset"*, *"money already collected, not a lifetime-value forecast"*, *"not a
probability-weighted expected loss"*, *"Model Risk Score is not a calibrated probability"*. Even
Customer 360's evidence lines say *"Observed deviations from the population, not proven causes."*
The single genuine overclaim is the displayed **100%** (A3).

**10. Any dead buttons or broken links?**
One hard crash, found and fixed (A5). One button that returns a non-answer (A4). Otherwise clean:
every `st.page_link` / `st.switch_page` target resolves to a page that exists (all 9 call sites
checked against `pages/`), and all three CSV downloads are wired (C4, not exercised live).

**11. Any obvious visual / UX defects?**
None found. No horizontal overflow at 1536px (`scrollWidth == clientWidth == 1536`). No "nan"
leaking into the UI. Charts, badges, tables and expanders all rendered correctly on all six pages.
The "5 more" header state (B8) was investigated and disproved as a defect.

**12. Any functionality that should NOT be demonstrated live?**
Four things: the segment-mode Champions button (A4); the top of "Who should we contact first?"
*without* the A1 framing ready first; LLM synthesis (no key — and untested even if a key is
added); and URL typing / page refresh (B2). Also avoid the `Unmatched At-Risk (no segment)` →
Priority Customers handoff — it no longer crashes, but it lands unfiltered.

**13. What questions is an evaluator likely to ask?**
- "Why is your top-priority customer marked 'Monitor only'?" → **A1/A2. Rehearse this one.**
- "You're claiming 100% certainty that this customer churns?" → A3.
- "Is Model Risk Score a probability?" → No; the app already says so.
- "Where is the AI? Every answer says it's unavailable." → B1.
- "How do you know the model works?" → temporal holdout; "MODEL VALIDATED ON: Future data".
- "Did retention campaigns actually work?" → No campaign-response data exists; the app says so
  everywhere. This is the most important limitation to state before being asked.
- "₹5.43B — is that real money?" → Historical Realized Revenue, already collected, converted for
  display from NT$; disclosed.
- "Why is 11% of tenure missing?" → B6, and it is why A1 exists.
- "Only 2,400 high-risk high-value customers?" → B9.

**14. Is anything genuinely presentation-critical still missing?**
No feature is missing. The product is complete, internally consistent in its language, honest
about its limits, and demonstrable end-to-end in under five minutes. What is missing is not code:
it is a decision on A4 and a rehearsed 30-second framing of A1/A2. A1 is the one finding that can
turn a strong demo into a doubted one if an evaluator finds it before you name it — and it reads as
rigour if you name it first.

---

## Change log for this session

| Task | File | What changed | Why |
|---|---|---|---|
| 1 | `dashboard/pages/retention_copilot.py` | Free-text submission moved to an `on_change` callback; suggested-prompt selection clears the box; context switch clears the box alongside the answer | A keyed `text_input` retains its value across every rerun. The page read that value each run and treated it as the question asked, so a stale entry overrode a suggested-prompt click made on the same run (buttons render above the box) — the button appeared dead. **Reproduced before the fix, verified fixed in AppTest and in Chrome, both directions.** |
| 1 | `tests/test_retention_intelligence_ui.py` | +7 tests | free-text → suggested-prompt executes; box cleared on selection; reverse direction; no re-submit on an unrelated rerun; context switch clears both; fresh session clean; source guard against the old read-and-assign pattern returning |
| 3 | `dashboard/pages/priority_customers.py` | Handed-over filter values restricted to the page's own options | A5 — reachable `StreamlitDefaultNotInOptionsError` |
| 3 | `tests/test_integrated_product_qa.py` | +3 tests | unrepresented segment degrades instead of crashing; real segment still applied; risk/value handoff still applied |

**Protected and untouched:** `notebooks/`, `models/`, `outputs/`, `src/`, `requirements.txt`,
`dashboard/requirements.txt`. `dashboard/lib/theme.py` was edited as a temporary experiment for
B8 and reverted — it is byte-identical to HEAD (`git diff` empty).

## Limitations of this audit

- **No live LLM behaviour was tested.** No API key exists; every answer inspected came from the
  deterministic fallback. Nothing here validates model-authored output.
- **No file downloads were performed**, so the three CSV buttons are verified only at source level.
- **Inspected at one viewport** (1536×720 CSS px, this machine's maximum). Behaviour at other
  widths, and the effect of browser zoom on B8, are **UNVERIFIED**.
- A1's remedies were **not implemented or tested** — the root cause is in protected directories.
- The 5,890 mislabelled at-risk customers remain mislabelled. A5's fix prevents a crash; it does
  not make that group reachable.

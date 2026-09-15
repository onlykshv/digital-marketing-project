# TASK 05 — Product & Evaluator Readiness Audit

**Status: AUDIT ONLY. Nothing in `dashboard/`, `notebooks/`, `models/`, `outputs/`, `src/`, or any
other `test_cases/*` file was modified while producing this report.**
**Method:** Read all five prior reports + the issue tracker, then inspected the live application
directly — server already running on `localhost:8640`, fresh navigations, real clicks, real
Retention Intelligence questions asked against the actual deployed (no `ANTHROPIC_API_KEY`)
environment, source-code verification (`grep`/`Read`) for every claim about *why* something
behaves the way it does.
**Date:** 2026-09-11

---

## 1. Executive verdict

The underlying engineering is genuinely strong: a real, temporally-validated model; a real
calibration layer; a disciplined four-term terminology system enforced in code, not just prose; a
deterministic tool layer with 39+29+15 = 83 passing tests; an LLM orchestrator with a strict
allow-list dispatcher, a bounded tool loop, and an honest never-silent fallback. This is not a
toy. **But the product, as it stands right now, does not yet prove itself in the first five
minutes of contact.** Three of the six default suggested questions on the flagship AI page fail
outright in the product's actual out-of-the-box configuration. The AI page's own nav label still
says the old product name. The AI's business-question answers show a different currency unit than
every other screen in the app. The flagship page is not linked from the page a manager would
land on first. And the single most novel piece of UI built this project — the compact,
click-through customer priority list — has never actually rendered in this environment's real
session, because the deterministic fallback has no path to it.

None of this is a research or modeling problem. It is entirely a **last-mile wiring and
consistency problem**, and it is fixable in well under a day of focused work (see §11, §14). Right
now, though, a first-time manager or evaluator would come away thinking "interesting analytics
dashboard with an AI feature bolted on that half-works," not "one coherent AI retention product."
That gap is the entire finding of this audit.

**If the current architecture is strong but the presentation/wiring is weak — that is exactly the
case here, and that distinction should drive what gets fixed next, not more analytics, not more
pages, not more ML.**

---

## 2. Part 1 — 10-second first impression

Opened `http://localhost:8640/` cold, as a first-time visitor, gave it ~10 seconds.

**What I saw:** a dark hero card — "OVERVIEW · WHERE SHOULD KKBOX ACT?" / "**129.7K** customers
need attention" / "22.7K of them are in the highest-risk tier, out of 971.0K customers scored." —
followed immediately by a one-sentence explainer, four small stat labels, and a risk×value bubble
chart with a highlighted "PRIORITY ZONE."

1. **What do you think this product is?** A churn-risk analytics dashboard for a subscription
   business, built on top of a real predictive model. That reads clearly and immediately — the
   hero states a number, states what it means, and states where to look. This is the strongest
   single screen in the product for a cold-open.
2. **Who is it for?** A retention/marketing manager or analyst at the business, not an
   engineer — the language ("customers need attention," "what is at stake") is business-facing,
   not ML-facing. Correct read.
3. **What problem does it solve?** "We have too many customers and can't treat them all the
   same — here's where to focus." That comes through immediately from the hero + priority-zone
   framing.
4. **What is the most important thing I can do here?** Genuinely ambiguous. The hero has no
   button. The only actionable link on the entire page ("View Priority Customers →") appears
   after scrolling past the chart and the segment cards — a first-time visitor has to scroll
   and read before finding the one thing to click.
5. **Is the AI assistant clearly the hero?** **No.** Nothing on this landing page — the page a
   manager sees first — mentions an AI assistant, links to one, or hints one exists. The only way
   to discover Retention Intelligence is to notice it as the sixth, last item in the top nav and
   click it unprompted. For a product whose entire differentiator (per every prior task brief) is
   supposed to be the AI layer, the AI is invisible on first contact.
6. **Is KKBOX merely the use case, or does it feel like a one-off KKBOX dashboard?** Leans toward
   the latter on first impression, specifically because of copy: "WHERE SHOULD **KKBOX** ACT?" is
   the literal hero eyebrow text. It reads as "this is KKBox's internal tool," not "this is a
   retention-intelligence platform, currently instantiated on KKBox's data." (Verified this is
   genuinely superficial, not structural — see §9.)
7. **Is the churn-prediction → business-action connection immediately understandable?** Yes, on
   this specific page — this is the page's actual job and it does it well: score → priority
   zone → named segment → "Do this." That causal chain is legible in under 10 seconds.

**Bottom line:** the analytics half of the first impression is good. The AI half of the first
impression **does not exist** — a cold visitor has no signal, on the page they land on, that an
AI-driven assistant is the product's headline feature.

---

## 3. Part 2 — Manager workflow audit

Tested the seven example questions against the actual deployed app (no `ANTHROPIC_API_KEY` — this
is the genuine current state, not a hypothetical). Results:

| Question | Where tested | Result |
|---|---|---|
| "Who should we contact first?" | Default suggested prompt, no context | **Fails.** `[AI synthesis unavailable...] ... doesn't match a question this dashboard can answer deterministically without one.` No tool called, no answer, no customers shown. |
| "Which customers are high risk and high value?" / "Show me high-risk, high-value customers." | Default suggested prompt, no context | **Fails**, same refusal. `search_customers` is never reachable without a configured LLM (see §4, §7). |
| "Why is this customer at risk?" | Default suggested prompt, **no customer selected** | **Fails**, same refusal — and this exact question is one of the six default buttons shown even when no customer is in focus, so it is guaranteed to fail on a first click for a large fraction of visitors. |
| "Why is this customer at risk?" | **With a customer selected** (via Priority Customers → Customer 360 → "Ask Retention Intelligence about this customer →") | **Works well.** Full Recommendation/Why/Evidence/What to do/What to avoid/Confidence/Caution structure, correct per-customer numbers, honest fallback banner, correct provenance caption. This is the best answer path in the product. |
| "What should we do about this customer?" | With a customer selected | **Works**, same quality as above (verified in Task 04's live walkthrough). |
| "Which segment needs the most attention?" ("Which segment needs attention?") | Default suggested prompt, no context | **Works.** Returns a ranked list (`1. At-Risk, Auto-Renew Off — 113,820 customers, 41.1% churn, 200,463,967 NT$ at stake. Recommended: Re-engage.` etc.) — grounded, correct, keyword-routed. |
| "How much revenue is exposed to churn risk?" | Closest match: "How many customers are at elevated risk?" | **Works** via the `_AGGREGATE_KEYWORDS` route, but the *exact* phrasing in the task brief ("how much revenue is exposed") does **not** contain any of the matched keywords (`how many`, `total customers`, `churn rate`, `aggregate`, `overall`, `elevated risk`, `at risk are there`) and would fail if typed verbatim as free text. Only the button-provided phrasing is guaranteed to work. |
| "Show me customers that need intervention." | Free text, no context | **Fails**, same refusal as the search-customers case — there is no deterministic path to a customer list at all, regardless of phrasing. |

**Per-question judgment, for the ones that do work:**
- Understands intent: yes, for the customer/segment/aggregate-keyword cases — no, for anything
  shaped like "show me a list of customers" (structurally impossible without an LLM, not a
  phrasing problem).
- Calls the right tool: yes, always exactly one tool, never a wrong one — confirmed by the strict
  allow-list dispatcher (§7 of `TASK_03_validation_report.md`, re-verified here by source).
- Grounded: yes, always — every number traced back to a real source file in testing.
- Understandable to a manager: yes for customer/segment answers (clean prose + labeled fields);
  **less so** for the aggregate/business-question answer, which is five dense statistic lines with
  no closing "so what should we do" line (see §8).
- Too numeric: the aggregate answer, yes (§6, §8). The customer/segment answers, no — they read as
  intended (headline + evidence + action).
- Leads to an action: yes for customer/segment answers (an explicit "What to do" line). No for the
  aggregate answer — it ends on a dollar figure, not a directive.
- Drill-down to a customer/segment: works correctly for the paths that succeed (verified live,
  Task 04) — but there is currently no case in this environment where a *list* of customers
  actually renders for a manager to drill into, because `search_customers` never fires without a
  key (§4).
- Misleading: the NT$/₹ currency-unit mismatch (§4) is the one place a manager could reasonably
  conclude the AI's numbers don't match the rest of the app, even though they are the same
  underlying values.
- Unnecessarily difficult: yes — the "Load customer data" gate sits between the hero and the
  suggested-prompt grid, and three of the six default prompts fail regardless of whether that gate
  was cleared, so a manager's first click has roughly even odds of hitting a dead end.

---

## 4. Part 3 — AI value audit

1. **What can the agent do that would otherwise require manually checking multiple pages?**
   When it works (customer/segment context, or a keyword-matched aggregate/ranking question), it
   genuinely does this: a segment-priority answer, for example, pulls exactly the numbers a
   manager would otherwise assemble by opening Action Center, reading the top two priority cards,
   and mentally re-ranking them — the agent does that ranking and narration in one shot. The
   customer-context answer is even stronger: it combines model risk state (Customer 360's job),
   population-baseline deviation (a comparison a manager cannot get from any single existing page
   without cross-referencing two tables by hand), and the recommended action (Action Center's
   job) into one grounded paragraph. **This is real, demonstrated value** — verified live in
   Task 04's walkthrough.
2. **Does it combine multiple tools into one answer?** Structurally yes (the tool-call loop
   supports any sequence up to 6 turns, and `agent.py`'s own tests exercise a real two-tool
   sequence) — but **only via the LLM path**, which is unverified live in this environment (no
   key). The deterministic fallback, which is what actually runs today, never calls more than one
   tool per question. So today, live, the "combines multiple tools" value proposition is
   **unproven**, not merely "less impressive" — it has literally never been observed running.
3. **Does it reduce cognitive load?** Yes, for the paths that work. A manager asking "why is this
   customer at risk" gets an answer faster than opening Customer 360 and manually reading the
   evidence bullets and SHAP panel — even though the underlying facts are identical, because
   Customer 360 already shows this well too (Task U-01 flagship work). The Copilot's real edge is
   the *segment ranking* and (when it works) *customer search* answers, which have no equivalent
   one-screen view anywhere else in the product.
4. **Does it turn analytics into decisions?** For customer/segment answers, yes — every one ends
   with an explicit "What to do" line. For the aggregate/business-question answer, **no** — it
   ends on a dollar figure with no directive (§8).
5. **Is the Model Risk Score / Estimated Churn Probability / HRR / High-Risk Historical Revenue
   Exposure distinction understandable?** Yes — this is one of the most consistently well-executed
   things in the whole product. Every surface tested (Overview, Customer Value, Customer 360,
   Priority Customers, the Copilot's customer/segment/aggregate answers) uses the exact same four
   terms with the exact same definitions, and several surfaces (Customer Value, the aggregate
   answer) proactively state what a term is *not* ("not a probability-weighted expected loss").
   This discipline is real and it shows.
6. **Does the agent ever appear to invent information?** No instance found, live or in the 83
   automated tests. Every number traced to a real source file. Unknown customers get the exact
   required refusal string. This is a genuine strength.
7. **Does the deterministic fallback remain trustworthy?** Yes, unambiguously, for the paths it
   covers — it is not a weaker/riskier version of the AI answer, it *is* the same
   already-validated Retention Copilot engine underneath. The trust problem is not correctness,
   it's **coverage** (§7 below) and **presentation** (currency units, missing "so what" line).
8. **Does the UI honestly communicate when LLM synthesis is unavailable?** Yes, clearly and
   consistently — every fallback answer opens with `[AI synthesis unavailable: <reason> —
   showing the grounded deterministic answer]` and closes with a matching provenance caption.
   This is the one piece of transparency plumbing that works exactly as designed everywhere it was
   tested.
9. **Does it feel like an actual operational assistant, or "ChatGPT pasted onto a dashboard"?**
   When a customer or segment is in focus, it feels like a real operational assistant — the
   context strip, the badges, the structured Recommendation/Evidence/Action format, and the
   working "Open full profile →" link all reinforce that this is grounded, not generic. **When no
   context is set, it currently feels closer to a chatbot that fails a lot** — three refusals out
   of six default buttons is exactly the "ChatGPT pasted onto a dashboard, except it doesn't even
   work half the time" impression the project has explicitly tried to avoid.

**The honest, load-bearing statement for this section:** the agent is currently **more impressive
technically (tests, guardrails, terminology discipline) than it is operationally (what a manager
can actually get it to do today, in the actual deployed environment)**. The gap between those two
is not a modeling gap — it's that the deterministic fallback's keyword coverage was scoped around
"the exact question shapes the old Copilot already answered" plus two new aggregate/ranking
shapes, and the *new* flagship capability (search_customers / the priority list) was built,
tested, and documented entirely on the assumption an LLM would eventually be available to reach
it — which is a reasonable engineering sequencing decision, but it means the single most visually
interesting piece of this project's UI has a 0% chance of appearing in a demo unless someone
configures `ANTHROPIC_API_KEY` first.

---

## 5. Part 4 — Six-page architecture audit

| Page | Manager question it answers | Obvious? | Necessary? | Duplicated elsewhere? | Connects forward? | Density | Visual coherence |
|---|---|---|---|---|---|---|---|
| **Overview** | "Where should we act, overall?" | Yes, immediately (hero states it) | Yes — the only page with a single at-a-glance top-line number | The "biggest opportunity" card is **word-for-word identical** to Action Center's Priority 01 card (same numbers, same "Do this" line) | Only to Priority Customers — no link to Retention Intelligence or Customer 360 | Low-moderate, well-paced | Strong — best page in the product |
| **Priority Customers** | "Who, specifically, should we work today?" | Yes | Yes — the only row-level, filterable work queue | No | Row-click → Customer 360 (works, verified live) | **High** — a raw, wide dataframe; appropriate for its role as "the queue," but a visible density jump from every other page | Good; the one page that's allowed to be table-heavy |
| **Customer Value** | "Where does our revenue actually sit?" | Yes | Borderline — its top stat row and "where revenue concentrates" chart substantially overlap Overview's framing, just value-first instead of risk-first | Partial overlap with Overview (both use risk×value framing; Customer Value is the value-led cut) | No link forward to anything | Moderate | Good, consistent with Overview |
| **Action Center** | "What should marketing do, by segment?" | Yes | Yes — the only page with the full campaign/action queue and CSV export | Its top card duplicates Overview's | **No link anywhere** — not to Customer 360, not to Priority Customers filtered to that segment, not to Retention Intelligence | Moderate-high (two priority cards + a 3-row table + an expander with the full portfolio) | Good | 
| **Customer 360** | "What should we do for this one customer?" | Yes | Yes — the flagship individual profile (U-01) | No | "Ask Retention Intelligence about this customer →" works correctly (verified live) | Well-paced, strong hierarchy per U-01's own design goal | Strong |
| **Retention Intelligence** | "Ask anything, get a grounded answer" | Yes, once you find it | Yes, unambiguously the intended hero | No | Works correctly *from* Customer 360; nothing links *to* it from Overview or Action Center | High-variance: excellent when context is set, a wall of refusals when it isn't | Strong visual design; undermined by nav label mismatch (§4/§11) |

**Overall information architecture verdict:** the *pairwise* connections that exist are genuinely
good (Priority Customers → Customer 360 → Retention Intelligence is a real, tested, working
three-hop chain). But the graph as a whole is not a loop — it is a shallow tree with two dead-end
leaves (Overview, Action Center) that never point anywhere except "down" (Overview → Priority
Customers) or nowhere at all (Action Center → nothing). The task's proposed order — **Overview →
Priority Customers → Customer 360 → Retention Intelligence → Action Center** — does not match the
actual top-nav order (**Overview, Priority Customers, Customer Value, Action Center, Customer
360, Retention Copilot**), and more importantly does not match the actual *linking* structure,
which has no path into Action Center at all and no path out of it. This currently reads as **six
independent pages with one good three-hop chain running through the middle of them**, not one
coherent workflow.

---

## 6. Part 5 — Visual / UX audit

Inspected live at 1536px (this environment's actual screen) and at a narrower effective width via
a 1.5x render-zoom approximation (true OS window resize was unavailable in this sandbox — noted
honestly, same limitation flagged in `TASK_04_validation_report.md`).

- **Typography/hierarchy:** strong and consistent — oversized page titles, a real type scale,
  consistent label/eyebrow treatment (`OVERVIEW · WHERE SHOULD KKBOX ACT?` style small-caps
  eyebrows) across every page. This is the product's single best-executed visual dimension.
- **Spacing/whitespace:** good — no cramped sections, no page felt like a wall of boxes.
- **Density:** uneven by design (Priority Customers is intentionally dense; everything else is
  intentionally sparse) — this is defensible, not a flaw, given each page's role.
- **Navigation:** clean top-nav, no sidebar, native Streamlit `st.navigation` — functional, but the
  **active-page label mismatch** ("Retention Copilot" in the nav vs. "Retention Intelligence" in
  the page itself) is the single most visible inconsistency in the entire product, because the top
  nav is present on every page, all the time.
- **Cards/tables/charts:** restrained, not over-carded — no five-KPI-card grids, no rainbow
  charts, no emoji, no gradients. This genuinely reflects the D-01 through D-04 design work
  described in the prior reports.
- **Empty/loading states:** the Retention Intelligence empty state is well done (a real hero, not
  a "no data" message) — but it is immediately followed by a hard "Load customer data" gate that a
  first-time visitor must clear before three of the six suggested questions can even theoretically
  work, and even after clearing it, those same three still fail (§4).
- **AI response presentation vs. analytics presentation:** visually distinct in a good way — the
  context strip, the "YOU ASKED" label, and the bolded Recommendation/Evidence fields read as
  clearly AI-mediated without looking like a chat app. This distinction is one of the project's
  real design wins.
- **Consistency:** high within each page; the one break is the currency-unit mismatch (§4) between
  the agent's aggregate/segment-ranking text and literally every other number shown in the
  product.
- **A visible native-Streamlit tell:** the "Deploy" button in the top-right corner is Streamlit's
  own default chrome, not something this project added or removed — it is a small but real signal
  to a technical evaluator that this is a `streamlit run` app rather than a deployed product,
  undercutting the "polished B2B SaaS" read slightly. Not fixable without a different hosting/embed
  setup; worth naming as a known, low-priority tell rather than pretending it isn't there.

**Which of the four does this look like right now?**

> **(C) an AI analytics prototype, closer to (D) than to (B) — but not yet (D).**

It has clearly moved past "(A) student ML project" (no raw notebooks-in-Streamlit feel, no
default Streamlit styling, no unstyled dataframes-as-the-whole-UI) and past plain "(B) Streamlit
dashboard" (the typography, restraint, and editorial framing are real and visible). It is not yet
a fully polished "(D) B2B product" because of the concrete, fixable issues in this report — nav
label mismatch, broken default AI prompts, currency inconsistency, a visible framework chrome
element, and a missing connective tissue between pages. **The visual design system itself is
closer to (D) than the actual behavior is** — this is a case where the CSS/typography work
outpaced the functional wiring.

---

## 7. Part 6 — "Too many numbers" audit

| Section | Current problem | Why it hurts | What the user actually needs to know | Possible future treatment |
|---|---|---|---|---|
| Retention Intelligence — aggregate/business-question answer (`agent._format_aggregate_answer`) | Five back-to-back statistic lines (customers scored, churn rate, High-risk count, elevated-risk count, high-risk×high-value count, total HRR, exposure) with **no closing recommendation or next-step line** | This is the flagship AI page's own answer format for "how many/how much" questions, and it is the single most numeric, least "so what"-shaped output in the entire product — exactly the failure mode the project has repeatedly tried to avoid elsewhere | One headline number, 2-3 supporting facts, and an explicit "what this means for the team" closing line (matching the structure the customer/segment answers already use) | *(not implemented here — audit only)* Restructure the aggregate formatter to mirror `_render_copilot_answer`'s Recommendation/Evidence/What-to-do shape instead of a flat statistic dump |
| Retention Intelligence — segment-ranking answer | Better than the aggregate case (each line does end in "Recommended: X"), but still presents 6-7 segments as a flat numbered list with three numbers each, all at once | A manager asking "which segment needs attention" wants the top 1-2 answers, not the full ranked table restated in prose | Lead with the #1 segment as the headline, offer the rest as supporting detail | Cap the prose to top 2-3, offer "see full ranking" as a link to Action Center instead of restating all rows |
| Customer Value — "Where revenue concentrates" bar chart | 7 segments × (₹ amount + %) all shown at once, unlabeled which one is actionable vs. which is just descriptive | Champions and Stable/Monitor (81% combined) drown out the two segments that actually warrant action | Which 1-2 segments are both large and actionable | Visually separate/mute the "no action needed" segments from the "act here" ones (this pattern already exists on Overview's bubble chart's "priority zone" callout — Customer Value doesn't reuse it) |
| Action Center — "Other customers needing attention" table | A second full data table (5 columns × 3 rows) directly below the two headline priority cards | Reads as "here is more data" immediately after the page already made its main point; a manager who got the headline has no reason to also parse a second table on first read | That smaller opportunities exist and where the detail lives if wanted | Already partially solved by relegating the *full* portfolio to a collapsed expander — the same treatment could apply to this secondary table |
| Priority Customers — the work-queue dataframe | Every column visible at once (Risk Tier, Estimated Churn Probability, HRR, Segment, Key Risk factor, more via horizontal scroll) for up to 500 rows | Appropriate for its role as a queue, but it is the steepest density jump in the product with zero visual transition from the page above it | This is somewhat justified by the page's job — flagged for completeness, not as a strong recommendation | Lowest priority of this list; a true work-queue table is expected to be dense |

The clearest, highest-value fix in this section is the aggregate-answer restructure — it is the
one place where "too many numbers" and "the AI answer doesn't lead to an action" (§8) are the
exact same underlying defect.

---

## 8. Part 7 — "So what?" audit

| Analytical output | "So what?" — is the connection to action present? |
|---|---|
| Model Risk Score | **Present, consistently.** Every surface that shows it also says what it's for ("used for prioritization, not a literal probability") and pairs it with a risk tier a manager can act on. |
| Estimated Churn Probability | **Present.** Correctly distinguished from Model Risk Score everywhere tested; used as the number that actually drives the "why is this customer at risk" evidence line. |
| Customer segment | **Present, strongly.** Every segment view (Overview, Action Center, Customer 360, Copilot) pairs the segment name with an explicit recommended action — this is one of the product's best-executed "so what" chains. |
| Revenue exposure (HRR / High-Risk Historical Revenue Exposure) | **Present on every page except the Copilot's own aggregate answer**, where the number is stated and then the answer simply ends (§7, §8) — the one place in the product where a revenue figure is shown with no accompanying "so what." |
| High-risk customer | **Present** at the individual level (Customer 360, the customer-context Copilot answer both end in a concrete action) — **absent** at the list level, because the list view (`search_customers` / the priority list) cannot currently be reached without an LLM key (§4), so a manager can never actually see "here are 20 high-risk customers, here's what to do with each" render live today. |
| Champion customer | **Weak.** Champions are consistently described as "don't spend retention effort here" (correct, and consistent with the segment's actual behavior), but no page turns that into a forward action the way At-Risk segments get one — "advocacy/upsell: referrals, plan upgrades, early access" appears as a one-line aside on Overview and Action Center, never as its own worked example the way the At-Risk segment gets a full recommendation card. A manager reading "Champions" learns what *not* to do, but never sees what the *positive* play looks like in the same depth as the retention plays. |
| Segment ranking | **Present in the segment-ranking Copilot answer** (each row ends in "Recommended: X") — **weaker on Action Center**, where the ranking exists as a table of numbers without restating why segment 1 outranks segment 2 in the same sentence as the numbers (the "why" has to be inferred from the revenue/churn columns rather than stated). |

**Net verdict:** the product's per-customer and per-segment paths answer "so what" well and
consistently — this is real, demonstrated discipline, not an accident. The **one structurally weak
link is the aggregate/business-level answer**, which is exactly the kind of question ("how many,"
"how much is exposed") a first-time evaluator or a busy manager is most likely to ask first, and
it is currently the least action-oriented answer type in the whole system.

---

## 9. Part 8 — KKBOX vs. reusable-platform audit

**FACT** (verified by source inspection, not inferred):
- KKBox-specific naming appears in exactly 9 places across `dashboard/` — a page title, a
  `set_page_config` call, two hero/eyebrow strings, one CSS `content:` string, one code comment,
  and two LLM system-prompt opening sentences (`agent.py`, `copilot_engine.py`). None of these are
  structural — they are literal strings that could be templated or swapped without touching any
  logic.
- The deterministic tool layer (`agent_tools.py`), the orchestrator (`agent.py`), the UI
  components (`components.py`, `theme.py`), and every page's rendering logic operate exclusively
  on the *shape* of `outputs/*.csv`/`*.json` (`msno`, `risk_score_full`, `calibrated_probability`,
  `segment`, `total_revenue`, etc.) — none of them contain KKBox-specific business rules (no
  hardcoded segment names baked into logic beyond reading `marketing_action_plan.csv`, no
  KKBox-only feature branches).
- `src/` (the feature-engineering pipeline) is genuinely KKBox-schema-specific:
  `transactions_features.py` alone references KKBox's actual Kaggle-schema column names
  (`msno`, `is_cancel`, `payment_method_id`, `actual_amount_paid`, `membership_expire_date`) 22
  times; `build_dataset.py` references them 12 times. This layer is not reusable as-is.

**REASONABLE INFERENCE:**
- The dashboard/agent/UI layer is reasonably described as **schema-reusable**: if another
  subscription business's data were transformed into files with the same column names and shapes
  as `outputs/*.csv`, the dashboard, the tool layer, and the agent would very likely work against
  it with no code changes beyond the 9 cosmetic strings above. This is a defensible technical claim
  because it follows directly from how narrowly-scoped the KKBox references actually are (verified
  above), not from aspiration.
- The four-term terminology system (Model Risk Score / Estimated Churn Probability / HRR /
  High-Risk Historical Revenue Exposure) is itself domain-general — it would transfer to any
  subscription-churn business unchanged in concept, only the underlying numbers would differ.

**FUTURE POTENTIAL (explicitly not claimed as fact today):**
- Calling this a "reusable framework" without qualification would be an overclaim. Onboarding a
  second business genuinely requires rewriting `src/` — a real, non-trivial feature-engineering
  effort — not just relabeling the dashboard. The honest claim is: **"the retention-intelligence
  layer above the data (scoring outputs → tools → agent → UI) is designed narrowly enough to be
  schema-portable; the path from raw transactional data to that shape is currently
  KKBox-specific and would need to be rebuilt per business."** That is a true, defensible, and
  still genuinely interesting claim for an evaluator — it should be stated exactly this precisely,
  not rounded up to "this is a reusable platform."

---

## 10. Part 9 — Technical defensibility audit

For each likely evaluator question: does the **current product itself** (not a future
presentation) help answer it honestly?

| Question | Does the product support an honest answer today? |
|---|---|
| "Why this dataset / why is it old?" | **Partially.** The cutoff date and temporal-validation framing appear in Overview's "Model validated on: Future data (temporal holdout)" stat and in per-page Methodology expanders — but there is no single page that states "this is the public KKBox Kaggle churn dataset, cutoff 2017-02-28, here's why" in one place. An evaluator has to piece it together from several expanders. |
| "Why KKBox?" | **Weak**, currently answerable only verbally, not from the product — no page states the dataset's provenance or selection rationale. |
| "Why XGBoost / why segmentation / why calibration?" | **Good** for calibration specifically — Overview, Customer Value, and the aggregate answer all correctly state the calibration/raw-score distinction and its rationale inline. Segmentation rationale is visible via Action Center's "why" framing. XGBoost's own selection rationale is not stated in the product at all (it is presumably in a notebook, which is outside the dashboard's scope by design). |
| "Why is the model score not a probability?" | **Strong.** This is the single best-defended point in the entire product — stated consistently, correctly, in the exact same words, on every surface that shows the score. |
| "Why use an LLM here / why not just a dashboard?" | **Currently the weakest-supported claim in the product**, precisely because of §4/§7: the one thing an LLM adds that a dashboard structurally cannot (ad-hoc list queries, multi-tool synthesis) is the one capability that cannot currently be demonstrated live. The product's *architecture* answers this question well (a real orchestrator, real tool-calling, a real fallback) — the product's *current runtime behavior* does not, because the fallback path is what actually runs and it is deliberately narrower. |
| "Why not RAG?" | **Well-supported.** `AGENT_ARCHITECTURE_PLAN.md` §K explicitly reasons through and rejects RAG/vector-DB for this problem (exact-match retrieval covers every real question shape) — a good, specific, defensible answer that exists in the repo already. |
| "How do you prevent hallucination?" | **Strong and verifiable in code**, not just claimed: the fixed tool allow-list (`_TOOL_DISPATCH`), the exact-match-only customer lookup, the strict response parser, and the "answer must cite the tool result verbatim" system-prompt rule are all real, inspectable, and tested (83 passing tests touch this directly). This is a genuinely strong defensibility point. |
| "How does the agent know which tools to call?" | The architecture doc and code both answer this precisely (tool-use schemas, strict dispatch) — but the live, *unmocked* answer ("does a real model actually pick correctly") is honestly and explicitly flagged as unverified in `TASK_03_validation_report.md` §10. This honesty is itself a defensibility asset, not a weakness, as long as it's stated plainly to an evaluator rather than glossed over. |
| "Can this work with another company?" | See §9 — the product supports a precise, non-exaggerated answer; it does not yet support the exaggerated version of this claim. |
| "Where does the data come from?" | **Weakly supported inside the product** — no page states data provenance; this lives only in notebooks/README outside the dashboard's scope. |
| "How are recommendations generated?" | **Good** — `marketing_action_plan.csv`-driven, visible via the "More detail on this recommendation" expanders and the Copilot's "Confidence/basis" line, which explicitly says these are validated associations, not causal guarantees. |

**The single biggest defensibility gap:** there is no dedicated Methodology page in the live
product. `U-02` ("Dedicated methodology page") is the **only ticket in the entire tracker still
marked `TODO`** — every other ticket (A-01 through A-06, D-01 through D-05, U-01) is at least
`REVIEW`. Right now, methodology is real and largely correct, but it is scattered across six
different per-page expanders rather than living in one place an evaluator can open and trace
end-to-end. This is the most concrete, already-identified (by the project's own tracker), and
not-yet-started gap in technical defensibility.

---

## 11. Part 10 — 5-minute demo audit

**Strongest available sequence using only what exists today:**

1. Open Overview — state the hero number, the priority zone, the one-sentence "so what."
2. Scroll to "The biggest actionable opportunity" — show the segment-level recommendation.
3. Click "View Priority Customers →" — show the real, filterable work queue.
4. Select a High-risk/High-value customer row → Customer 360 opens — show the flagship profile
   (risk state, HRR, evidence, recommendation).
5. Click "Ask Retention Intelligence about this customer →" — show the context strip
   ("Analysing customer X") auto-attaching.
6. Click "Why is this customer at risk?" — show the grounded, evidence-backed answer render live.
7. Click "What should we do for this customer?" — show a second grounded answer, same customer.
8. Close on the terminology discipline: point at "Estimated Churn Probability" vs. "Model Risk
   Score" and note they're deliberately different numbers, on purpose, everywhere in the product.

**Is this compelling?** Steps 1-7 are genuinely compelling and fully reliable **today, in the
current environment, with no API key** — this is the exact path this audit verified live and it
works cleanly end to end. It demonstrates real grounding, a real UI handoff, and real terminology
discipline.

**What's missing, and must be avoided in a live demo:**
- **Do not open Retention Intelligence "cold"** (no customer/segment selected) and click one of
  the general suggested prompts hoping it lands well — there is a 50% chance (3 of 6 default
  buttons) it produces a refusal message in front of the evaluator (§4). If the demo must show the
  general/aggregate mode, use "Which segment needs attention?" or "How many customers are at
  elevated risk?" specifically — verified working — and avoid "Who should we contact first?" and
  "Show me high-risk, high-value customers." entirely until §14's fixes land.
- **The list-query / priority-list UI (the single most novel piece of this project's interface)
  cannot be shown at all** unless `ANTHROPIC_API_KEY` is configured before the demo starts. If a
  key can be configured beforehand, this becomes the single strongest addition to the sequence
  above (insert after step 3: ask "Show me high-risk, high-value customers," show the compact
  list, click through to a customer from the list). If a key cannot be configured, this capability
  should simply not be promised or attempted live.

---

## 12. Part 11 — Prioritized findings

### P0 — MUST FIX (materially damage understanding, correctness-perception, trust, demo, or evaluator perception)

1. **Three of the six default Retention Intelligence suggested prompts fail in the product's
   actual deployed configuration** — "Who should we contact first?", "Show me high-risk,
   high-value customers.", and "Why is this customer at risk?" (shown with no customer selected).
   This is the flagship AI feature failing on its own advertised examples on first contact.
   (§3, §4, §11)
2. **The top-nav label for the flagship page still reads "Retention Copilot"** while the page
   itself is titled "Retention Intelligence" everywhere else (hero, branding, prior task's own
   naming) — visible on every page, all the time, and the first concrete inconsistency any
   evaluator will notice. Root cause: `dashboard/app.py`'s `st.Page(..., title="Retention
   Copilot")` was never updated when Task 04 renamed the page content. (§4, §5, §6)
3. **Currency-unit mismatch between the AI's own answers and the rest of the product.** The
   agent's aggregate/business-question and segment-ranking answers (`agent._format_aggregate_answer`,
   `agent._format_rank_segments_answer`) print raw `NT$` figures (e.g. "200,463,967 NT$"), while
   every other number in the product — headers, Customer Value, Customer 360, and even the
   Copilot's own customer/segment answers via `copilot_engine.py` — is shown in ₹ via
   `theme.fmt_currency`. Same underlying values, different units, in the one place (the AI) where
   trust matters most. (§4, §3)
4. **`search_customers` (the flagship customer-list capability) is unreachable without a
   configured LLM key** — there is no deterministic keyword route to it at all. This means the
   most visually novel piece of UI built in this project (`components.priority_list`) has never
   rendered in a real session in this environment and cannot be demoed without pre-configuring
   `ANTHROPIC_API_KEY`. (§4, §11)
5. **The flagship AI page is not linked from Overview or Action Center** — the two pages a manager
   is most likely to land on or spend time on have zero path into Retention Intelligence. It is
   only reachable via the top nav (unprompted) or via Customer 360's one CTA. (§2, §5)

### P1 — SHOULD FIX (usability, product clarity, AI usefulness, visual quality)

6. **The aggregate/business-question Copilot answer has no closing recommendation or "so what"
   line** — it is five statistic lines and then it stops, unlike every other answer type in the
   product, which all end in an explicit action. (§7, §8)
7. **Overview's and Action Center's top-priority cards are word-for-word duplicates** — not wrong,
   but a missed opportunity to differentiate "at-a-glance teaser" from "full campaign detail."
   (§5)
8. **Action Center has no forward link at all** — not to a filtered Priority Customers view, not
   to Customer 360, not to Retention Intelligence. A dead end at the end of a workflow that
   otherwise chains well. (§5)
9. **The information-architecture order the product suggests (top nav) doesn't match the order the
   product's own linking actually supports** — the working three-hop chain is Priority
   Customers → Customer 360 → Retention Intelligence, but the nav interleaves Customer Value and
   Action Center between Priority Customers and Customer 360 with no signal that those two are a
   separate branch, not a step in the same chain. (§5)
10. **The issue tracker shows every ticket except U-02 stuck at "REVIEW," never promoted to
    "DONE,"** despite multiple validation reports confirming completed, tested work — a small
    hygiene gap that an evaluator opening the tracker file would notice immediately and might
    read as "nothing here actually shipped." (§10, and observed directly in the xlsx)

### P2 — POLISH

11. The native Streamlit "Deploy" button in the top-right corner is a visible framework tell that
    undercuts the "polished product" read for a technical evaluator. Not easily fixable without a
    different hosting setup — noted, not prioritized. (§6)
12. The brief first-paint flash where the top nav shows only the brand mark before hydrating
    (already documented in every prior report as a known, non-blocking Streamlit rendering
    artifact) remains present — cosmetic only, resolves on its own within roughly a second.
13. A dedicated Methodology page (`U-02`, still `TODO`) would meaningfully strengthen technical
    defensibility for a viva/evaluator setting, consolidating what is currently scattered across
    six per-page expanders. (§10)

---

## 13. Part 12 — Recommended final product direction

**One direction. Not five.**

- **PRODUCT HERO:** Retention Intelligence — the grounded, tool-calling AI assistant. Everything
  else exists to make the assistant's answers verifiable and actionable, not to compete with it
  for attention.
- **CORE USER:** a KKBox retention/marketing manager who needs to decide, today, which customers
  or segments to act on and what to do about them — not a data scientist, not an executive
  reading a static report.
- **CORE WORKFLOW:** ask a question → see a grounded, evidence-backed answer → see the specific
  customers or segments behind it → open one in full profile → see the recommended action →
  (implicitly) go act on it. This workflow already exists and already works end-to-end for the
  customer-context path — the job is to make it work for the general/aggregate/list path too,
  and to make it discoverable from where a manager actually starts.
- **ROLE OF ML:** the ground-truth engine. It never speaks for itself in the UI — every number a
  manager sees is already a validated, calibrated, or documented-as-a-headcount-sum figure by the
  time it reaches any page. The model's job is correctness; the product's job is making that
  correctness legible and actionable.
- **ROLE OF ANALYTICS PAGES (Overview, Priority Customers, Customer Value, Action Center):** the
  audit trail. Their job is to let a skeptical manager or evaluator verify, by hand, that the
  AI's answers aren't invented — every fact the agent states should be independently checkable on
  one of these four pages. This is already true today (§4 of the AI value audit) and is a real
  strength worth stating explicitly as the pages' purpose, not just "the other five pages."
- **ROLE OF THE AI AGENT:** orchestration and narration over the deterministic tool layer — never
  the source of truth, always a caller of it. This is already the actual architecture (§2 of
  `TASK_03_validation_report.md`) and should stay exactly as narrow as it is; the fix needed is
  coverage and presentation, not scope.
- **ROLE OF CUSTOMER 360:** the action surface — where a question about one customer resolves into
  a concrete next step. Already working well; the connective tissue *into* it (from Priority
  Customers) and *out of* it (to Retention Intelligence) is the part worth preserving unchanged.
- **ROLE OF ACTION CENTER:** the segment-level campaign-planning surface — the "what should
  marketing do this week, at the portfolio level" view. Currently isolated; should gain at least
  one forward link (to a filtered Priority Customers view of that segment, matching the pattern
  already proven for the Copilot's own priority-list deep link) so it stops being a dead end.
- **ROLE OF KKBOX:** the demonstration dataset and the concrete proof that the model, the
  terminology system, and the agent all work end-to-end on real data — not the identity of the
  product. Copy that currently reads "WHERE SHOULD KKBOX ACT?" should read as "where should THE
  BUSINESS act, and here it's demonstrated on KKBox's real subscriber data" — a framing change,
  not a rebuild.
- **REUSABILITY STORY:** state it exactly as precisely as §9 states it — the dashboard/tool/agent
  layer is schema-portable; the feature-engineering layer is currently KKBox-specific and would
  need to be rebuilt per business. This precise version is more credible to a technical evaluator
  than an unqualified "this is a reusable platform" claim would be, and it is fully supported by
  the actual code.

**Smallest set of changes required to make this feel genuinely finished** (see §14 for the
explicit sequence): fix the three broken default prompts, fix the currency-unit mismatch, fix the
nav label, add one link from Overview (and ideally Action Center) into Retention Intelligence, and
decide — deliberately, not by default — whether a live demo will have `ANTHROPIC_API_KEY`
configured or will lean entirely on a widened deterministic fallback. Every one of these is a
small, surgical, already-diagnosed fix; none of them require new features, new pages, or new
analysis.

---

## 14. Part 13 — Explicit "do not build" list

- **No RAG / vector database.** Already correctly rejected in `AGENT_ARCHITECTURE_PLAN.md` §K, and
  nothing found in this audit changes that reasoning — exact-match retrieval genuinely covers
  every real question shape this product needs to answer.
- **No autonomous customer messaging or write-back capability.** This is a read-only intelligence
  layer over an already-validated analytical pipeline; adding an execution capability would be a
  scope change with real risk (sending something to a real customer) for a demo-stage product,
  and was already explicitly excluded in the architecture plan.
- **No additional agents or multi-agent orchestration.** One orchestrator, one tool-call loop, one
  system prompt is already the right level of complexity for this problem's actual shape; adding
  more agents would add failure surface without adding a capability a manager actually needs.
- **No new ML models.** The scoring/calibration work is done and validated; the gaps found in this
  audit are entirely in UI wiring and presentation, not in analytical capability.
- **No more charts or KPI cards.** The product already correctly avoids a five-KPI-card grid; more
  visual elements would work against the "one coherent product, not a feature count" goal this
  audit was explicitly asked to protect.
- **No generic chatbot features** (multi-turn memory, conversation history, personality, free-form
  small talk). The project's deliberate one-question-in, one-grounded-answer-out design is a
  strength, not a limitation to "fix" by adding chat-style statefulness.
- **No large knowledge base or document ingestion.** There is no unstructured-document corpus in
  this project's scope; adding one to make the agent feel more "AI-ish" would be pure surface
  complexity with no grounding benefit.
- **No complex new infrastructure** (a real backend service, a job queue, a second database) to
  support any of the fixes in §12/§14 — every P0/P1 finding in this report is fixable within the
  existing Streamlit/pandas/CSV architecture.

---

## 15. Proposed next implementation sequence

*(Sequencing only — no implementation performed as part of this audit, per instruction.)*

1. **Fix the three broken default suggested prompts** (P0 #1) — either widen
   `_deterministic_fallback`'s keyword coverage to route "show me high-risk, high-value
   customers"-shaped questions to `search_customers` (now that `customer_df`/`ToolCallRecord.result`
   already support rendering a list, per Task 04), or replace those specific default buttons with
   phrasing that already works deterministically, or visibly mark which buttons require a
   configured AI provider. This is the single highest-leverage fix in this entire report.
2. **Fix the currency-unit mismatch** (P0 #3) — route `_format_aggregate_answer` and
   `_format_rank_segments_answer`'s dollar figures through `theme.fmt_currency`/`theme.to_inr`
   instead of raw `NT$` f-strings, matching every other surface in the product.
3. **Fix the nav page title** (P0 #2) — one-line change in `dashboard/app.py`,
   `title="Retention Copilot"` → `title="Retention Intelligence"`. Highest visibility-to-effort
   ratio of any fix in this report.
4. **Add one discoverability link into Retention Intelligence from Overview**, and ideally a
   second forward link from Action Center (to a filtered Priority Customers view, reusing the
   already-proven `pending_filter` deep-link pattern) — closes P0 #5 and P1 #8 together.
5. **Restructure the aggregate answer to end on an explicit "so what" line** (P1 #6), matching the
   Recommendation/Evidence/What-to-do shape every other answer type already uses.
6. **Decide and document the demo/deployment posture**: either configure a real
   `ANTHROPIC_API_KEY` before any live evaluator session (which would resolve P0 #4 immediately and
   let the full tool-calling path be demonstrated for the first time), or explicitly accept the
   narrower deterministic-only demo path mapped out in §11 and never promise the list-query
   capability live without a key.
7. **Update the issue tracker's Status column** to reflect the actually-validated state (P1 #10) —
   near-zero effort, removes an easy "does this project actually finish things" doubt for anyone
   who opens the xlsx.
8. **Only after the above:** consider the dedicated Methodology page (`U-02`, P2 #13) for
   technical-defensibility polish, and the remaining P1/P2 items (duplicate Overview/Action Center
   cards, nav ordering, Champion-segment "so what," Action-Center secondary-table density).

Steps 1-4 alone would resolve every P0 finding in this report and could reasonably be completed in
a single focused session before the next evaluator or manager sees this product.

# Validation Report — P1-09: Assistant Identity & Personality

**Status: REVIEW** (not DONE — reserved for independent sign-off).
**Tracker:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, row P1-09.
**Date:** 2026-09-11

---

## 1. Exact P1-09 requirement from the tracker

- **Issue:** "The AI capability risks looking generic rather than deliberately designed."
- **Claude Fix Prompt:** "Give the assistant a distinctive professional identity: name treatment,
  role, voice, context/status cues and restrained visual treatment. Do not imply autonomous
  actions it cannot perform. Preserve Model Risk Score, Estimated Churn Probability, HRR and
  High-Risk Historical Revenue Exposure terminology. No emoji, cartoon avatar, gradients or fake
  activity."
- **Acceptance Criteria:** "Consistent identity; accurate capability claims; professional visual
  treatment; grounded terminology preserved; tests/browser pass."

The tracker names five identity dimensions (name treatment, role, voice, context/status cues,
restrained visual treatment) but does not specify a particular name, mascot, or exact wording for
any of them — per instruction, this report does not infer beyond what's written; each open
dimension below states the choice made and the reasoning.

---

## 2. Interpretation of the requirement

Read against the current implementation (not assumed from the tracker text alone):

| Dimension | What already existed | What was missing |
|---|---|---|
| **Name treatment** | The product is already consistently named "Retention Intelligence" everywhere (nav, page title, hero, CTAs on Overview/Action Center — all from Tasks 04/06/P1-07) | The name never appeared as the answer's own identity — a manager saw an answer with no visible "who said this" |
| **Role** | The page's eyebrow read "AI ASSISTANT" — generic, could describe any chatbot | No deliberate role title distinct from the generic AI-product label |
| **Voice** | The deterministic answer templates (already tested, already precise) have an implicit voice, but the *LLM* system prompt — what actually governs a configured model's own words — had no explicit voice guidance at all | Nothing telling a configured LLM to be concise/operational/confident-when-supported/evidence-first/action-oriented/business-aware |
| **Context/status cues** | Already substantially built in P1-07: a context strip always showing what the assistant is grounded to (customer/segment/whole base), plus a genuine `st.spinner` during the real tool call | Nothing missing structurally; the spinner's copy didn't name the assistant |
| **Restrained visual treatment** | The existing "Finding vs. Evidence vs. Confidence" typographic tiering (P1-07) already gives the page a deliberate, non-generic look | No small answer-identity marker distinguishing "the assistant's own words" from the manager's question, beyond the existing "You asked" label |
| **No autonomous-action implication** | Audited: no existing UI copy implies it (checked, §7) | The LLM system prompt had no explicit rule forbidding it — a configured model could plausibly phrase an answer in first person ("I'll follow up with them") without one |

Given the explicit instruction *"If the specification leaves a visual/personality detail open,
choose the smallest implementation consistent with the existing... design system rather than
creating a large redesign. Do not invent a completely new UI system,"* the interpretation adopted
here is: **the existing product name, IS the assistant's name.** No new persona name (e.g. a
mascot-style "Ava"/"Sage") was invented — that would contradict both "smallest implementation"
and the explicit "no cartoon avatar" constraint's spirit. Instead, "Retention Intelligence" was
given a consistent **role title** ("Retention Operations Assistant") and made to consistently
**name itself** wherever it answers, reusing CSS/components that already exist.

---

## 3. Files changed

| File | Change |
|---|---|
| `dashboard/lib/agent.py` | `_SYSTEM_PROMPT` (LLM path only): new identity/voice opening paragraph, new "Voice:" paragraph, one new trailing rule (RULE 11, autonomous-action prohibition). Additive only — see §5 for exactly what did *not* change. |
| `dashboard/pages/retention_copilot.py` | Page eyebrow: `"AI ASSISTANT"` → `"RETENTION OPERATIONS ASSISTANT"`. New `"Retention Intelligence responds"` label (reuses the existing `.qa-question` CSS class) immediately before every rendered answer. Spinner copy: `"Consulting the retention model…"` → `"Retention Intelligence is consulting the retention model…"`. |
| `tests/test_agent_orchestration.py` | 6 new tests (§6) |
| `tests/test_retention_intelligence_ui.py` | 6 new tests (§6) |
| `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx` | Row P1-09 status: `TODO` → `REVIEW` |

**No new CSS class, no new Streamlit component, no new file was created.** Both UI additions reuse
`.qa-question` (already styled, already used for "You asked") and `theme.page_header`'s existing
eyebrow slot (already used identically by all six pages).

---

## 4. Files deliberately NOT changed

- **`dashboard/lib/copilot_engine.py`** — its own `_SYSTEM_PROMPT` (from the original,
  preset-question Copilot) already says "You are Retention Intelligence..." (a Task 06 fix), and
  its entrypoints (`answer_customer_question`/`answer_segment_question`) are **not called by any
  current page** (confirmed via `grep` — only `deterministic_customer_answer`/
  `deterministic_segment_answer` are reachable, through `agent.py`'s fallback). Extending its voice
  guidance would touch genuinely dead code for no observable behavior change; left alone to keep
  this task's footprint minimal, per instruction.
- **`dashboard/lib/agent_tool_schemas.py`, `dashboard/lib/agent_tools.py`,
  `dashboard/lib/llm_provider.py`** — no tool, schema, or provider logic was touched. Personality
  lives entirely in presentation (the UI) and in the LLM system prompt's *instructions*, never in
  a tool's behavior.
- **The deterministic fallback's answer-generating code** (`_render_copilot_answer`,
  `_format_aggregate_answer`, `_format_rank_segments_answer`, `_format_search_customers_answer` in
  `agent.py`) — **not rewritten for "voice."** These are precise, already-tested, factual string
  templates (many with exact-substring test coverage across 170 tests). Rewriting them for
  stylistic reasons would risk exactly what the task explicitly forbids — "Personality must NOT
  become a new analytical layer" — for no benefit, since their content is already concise,
  evidence-first, and action-oriented by construction. Voice was applied to the LLM system prompt
  (which actually governs generated text) and to the UI chrome around every answer, not to the
  deterministic content itself.
- **`dashboard/pages/overview.py`, `action_center.py`, `customer_360.py`, `priority_customers.py`,
  `customer_value.py`** — none touched. Their existing "Ask Retention Intelligence about {segment}"
  CTAs (Task 06) and "Ask Retention Intelligence about this customer" link (Task 04) already name
  the assistant consistently; nothing needed to change there.
- `notebooks/`, `models/`, `outputs/`, `src/` — zero changes (confirmed, §9).

---

## 5. Assistant identity/personality decisions, and how they stay grounded

1. **Name = "Retention Intelligence."** Not a new invented persona. The name that already appears
   consistently everywhere else in the product now also appears at the point where the assistant
   speaks.
2. **Role = "Retention Operations Assistant."** A professional, business-functional title (not a
   cute name, not a generic "AI Assistant" label) — directly echoes the task's own framing ("an
   internal decision-support agent for a retention team"). Used as the page eyebrow and,
   identically, as the LLM system prompt's own self-description (`"You are Retention Intelligence,
   KKBOX's Retention Operations Assistant"`), so the UI label and what a configured model is told
   to call itself are the same string.
3. **Voice**, encoded as an explicit, additive paragraph in `agent._SYSTEM_PROMPT`: concise and
   operational, confident when evidence supports a conclusion, explicit and unhedged about
   uncertainty, evidence-first, action-oriented, business-aware. This governs the *optional LLM
   path only* — it cannot change what the deterministic fallback actually says (that logic is
   unchanged Python string formatting, not LLM-generated), so it cannot become "a new analytical
   layer." It is bounded, additive text appended to a system prompt whose 10 existing grounding
   rules (RULE 1-10) are byte-identical to before this task (proven by
   `test_p1_09_additions_did_not_alter_the_existing_grounding_rules`, §6).
4. **Explicit anti-autonomy rule** — new RULE 11: *"You are a decision-support assistant, not an
   autonomous system. You cannot contact a customer, send a message, apply a discount, change a
   subscription, or modify any record — you can only recommend what the retention team should do.
   Never phrase an answer as if you are taking, or have already taken, an action yourself."* This
   directly answers the tracker's explicit constraint ("Do not imply autonomous actions it cannot
   perform") for the one path where an LLM could plausibly generate such a claim on its own; the
   deterministic path was independently audited (§7) and never made such a claim before or after
   this task.
5. **Context/status cues** — already substantially built in P1-07 (the always-present context
   strip). This task's only addition here is naming the assistant in the existing, real
   `st.spinner` copy — not a new cue, not fake activity (the spinner reflects a genuine,
   already-happening `agent.ask()` call), just consistent naming of an existing one.
6. **Restrained visual treatment** — the new `"RETENTION OPERATIONS ASSISTANT"` eyebrow and
   `"Retention Intelligence responds"` label both use typography and color **already defined** in
   `theme.py` (the `.eyebrow` and `.qa-question` classes, both pre-existing, both already used
   identically elsewhere in this exact file and others). No new color, no new font size, no
   gradient, no icon, no avatar graphic was introduced anywhere.

---

## 6. Tests added and complete test results

**`tests/test_agent_orchestration.py`** — 6 new tests, all against the real `agent._SYSTEM_PROMPT`
string, no mocking:

1. `test_system_prompt_states_a_consistent_name_and_role` — the exact identity sentence and "not a
   general-purpose chatbot" framing are present.
2. `test_system_prompt_states_the_required_voice_traits` — all six voice traits from the tracker's
   Product Principle (concise/operational, confident-when-supported, explicit/unhedged uncertainty,
   evidence-first, action-oriented, business terms) are present in the prompt text.
3. `test_system_prompt_forbids_implying_autonomous_action` — RULE 11 is present and names all five
   prohibited actions (contact a customer, send a message, apply a discount, change a subscription,
   modify a record) plus the "only recommend" framing.
4. `test_p1_09_additions_did_not_alter_the_existing_grounding_rules` — regression guard: 7
   representative, byte-exact snippets of RULE 1-6 and RULE 9 (unaffected by this task) are still
   present verbatim.
5. `test_agent_tool_dispatch_and_schemas_unaffected_by_the_identity_change` — the 9-tool allow-list
   and dispatch table are exactly what they were.
6. `test_deterministic_answers_still_grounded_and_unaffected_by_identity_change` — two real,
   unmocked fallback calls (`agent.ask(...)`) still return the expected grounded, labeled content.

**`tests/test_retention_intelligence_ui.py`** — 6 new tests, AppTest-driven against the real page:

1. `test_page_eyebrow_is_a_deliberate_role_title_not_the_generic_old_one` — the new eyebrow is
   present; the old `"AI ASSISTANT"` text is gone.
2. `test_every_answer_carries_a_consistent_name_treatment` — after a real button click,
   `"Retention Intelligence responds"` appears, and specifically *after* `"You asked"` (question
   first, then the named response — not just present somewhere on the page).
3. `test_name_treatment_appears_for_customer_and_segment_answers_too` — regression guard across
   segment-context mode, not just general mode.
4. `test_spinner_names_the_assistant` — source-level check for the updated spinner copy.
5. `test_identity_change_did_not_alter_grounded_answer_content` — the real numbers in a real
   aggregate answer are unchanged, and the answer text itself (deliberately scoped to exclude the
   page's own, already-correct "NT$ is the source currency" methodology disclosure) never shows a
   raw `NT$` figure.
6. `test_no_emoji_or_fabricated_activity_language_introduced` — explicit tracker constraint check:
   no emoji-range Unicode characters and no "is typing"/"is thinking" style fake-activity language
   anywhere in the page's source.

**Exact results, this session, after every change:**

```
python tests/test_agent_tools.py               -> 40 passed, 0 failed
python tests/test_agent_orchestration.py        -> 49 passed, 0 failed   (43 existing + 6 new)
python tests/test_retention_intelligence_ui.py  -> 39 passed, 0 failed   (33 existing + 6 new)
python tests/test_manager_workflow.py           ->  8 passed, 0 failed
python scratchpad/test_copilot.py (original 34-assertion offline suite) -> 34 passed, 0 failed
```

**Total: 170/170 automated tests passing, zero regressions.**

A full AppTest sweep of all six pages (`overview`, `priority_customers`, `customer_value`,
`action_center`, `customer_360`, `retention_copilot`) was also re-run: all six load with no
exception.

---

## 7. Live browser validation

A fresh Streamlit server was started (`streamlit run app.py --server.port 8680`), with
`ANTHROPIC_API_KEY` confirmed absent from the environment immediately before starting it
(`python -c "import os; print('ANTHROPIC_API_KEY' in os.environ)"` → `False`), clean startup log.

All six required scenarios were walked live:

1. **General question** — "How many customers are at elevated risk?": rendered
   `RETENTION INTELLIGENCE RESPONDS` label, correct Finding-tier headline
   ("970,960 customers scored, 9.0% overall churn rate."), correct evidence, ₹5.43B / ₹91.36M (no
   `NT$`), correct honest fallback banner.
2. **Customer-specific question** — walked the full real handoff (Priority Customers → select a
   row → Customer 360 → "Ask Retention Intelligence about this customer →") to reach a genuine
   customer context, then asked "What should we do for this customer?": rendered the identity
   label, Finding-tier "Re-engage" headline, full grounded evidence (Risk tier, Estimated Churn
   Probability, HRR, tenure, cancellation/discount rates), correct "What to avoid" line — no
   first-person action language anywhere ("Re-engage" is a recommendation label, never "I will
   re-engage" or similar).
3. **Segment-specific question** — selected "Engaged Low-Risk (Champions)", asked "Why is this
   segment important?": correct identity label, correct Finding headline ("Advocacy/upsell:
   referrals, plan upgrades, early access -- not a retention play."), ₹2.97B (no `NT$`), business-
   aware and action-oriented phrasing throughout.
4. **Deterministic search/list result** — "Show me high-risk, high-value customers.": correct
   identity label, Finding headline ("These customers are both High risk and High value -- the
   Priority Zone."), 2,413-match count (independently matches the same figure already shown
   elsewhere in the product), "Recommended next step" line present.
5. **No-data / insufficient-context situation** — typed "Why is this customer at risk?" as free
   text with no customer or segment selected: rendered the identity label even for a guidance
   message, correct honest text ("This question is about a specific customer, but none is
   currently selected...") — never fabricated evidence, never pretended to answer.
6. **No-API-key deterministic fallback** — true throughout the entire session; every one of the
   five scenarios above ran through the real, live, unmocked deterministic fallback path, with the
   `[AI synthesis unavailable: no AI provider is configured for this session...]` banner and
   matching provenance caption present on every grounded answer.

Deep links and context selection were also directly re-verified during this walkthrough: the
Priority Customers → Customer 360 → Retention Intelligence handoff carried the exact customer ID
and its risk/value/segment badges correctly at every hop; segment selection correctly produced its
own context strip and take-action button (both unchanged from P1-07/P0-5).

---

## 8. No-API-key behavior

Confirmed throughout §7. This task made no change to `llm_provider.py` or to the
`is_configured()`/fallback-routing logic in `agent.py` — only to the system prompt string (which
is only ever read by the LLM path, `_run_tool_loop`) and to the page's static UI copy. The
deterministic fallback's own control flow (`_deterministic_fallback`, all keyword routing, all
honesty/guidance branches from Task 06/P1-07) is untouched.

---

## 9. Terminology / grounding checks

- **Model Risk Score / Estimated Churn Probability / HRR / High-Risk Historical Revenue
  Exposure** — the terminology paragraph in `agent._SYSTEM_PROMPT` is byte-identical to before
  this task (not touched by any edit in this task; verified by `test_system_prompt_preserves_
  terminology_distinctions`, an existing test, still passing unchanged). Confirmed live in every
  answer in §7 — every currency/probability figure used the correct, established label.
- **No causal language** — `test_system_prompt_forbids_causal_language` (existing, unchanged)
  still passes; RULE 7 (the causal-language guardrail) is untouched.
- **No fabricated evidence** — every live answer in §7 traced to real, already-validated source
  data; the one guidance-only answer (§7.5) explicitly did not claim to be evidence-backed
  (`grounded=False`, confirmed by the existing `agent.py` logic, unchanged).
- **No emoji / cartoon avatar / gradients / fake activity** — audited by both a regex-based
  automated test (`test_no_emoji_or_fabricated_activity_language_introduced`) and manual review of
  every line changed in this task. None introduced.
- **No autonomous-action implication** — audited the entire `dashboard/` tree for
  autonomous-action-implying phrasing (`we will email`, `I'll contact`, `sending the...`, etc.)
  *before* making any change: zero hits, confirming no pre-existing violation. The new RULE 11
  closes the one path (a configured LLM) that could introduce one in the future.
- Protected directories: `find notebooks models outputs src -newer <previous-report> -type f`
  returns nothing — zero changes.

---

## 10. UX / product rationale

Before this task, a manager asking a question saw "You asked" followed directly by an answer with
no visible source — functionally correct, but presentationally indistinguishable from a
generic embedded chat widget. The three changes in this task are deliberately small but land at
exactly the moments a manager actually experiences the product: the page's own identity (the
eyebrow, seen in the first five seconds), the moment of waiting (the spinner, now naming who is
doing the work), and the moment of reading an answer (the new label, present every single time,
in every context mode). None of them touch what the assistant actually says — the goal explicitly
was to make the *existing*, already-grounded, already-disciplined answers read as coming from a
deliberately designed, named, professional internal tool, not to invent a new voice for them.

---

## 11. Known limitations

- **A pre-existing rendering characteristic, not caused by this task**: at initial scroll position
  (scroll-top = 0) in this specific sandboxed browser, `theme.page_header()`'s eyebrow text sits
  partially beneath the site's `position: absolute`, high-z-index top navigation bar and is
  visually clipped until the page is scrolled. This was measured and confirmed **identical** on
  the unmodified `priority_customers.py` page (eyebrow `"PRIORITY CUSTOMERS"`, same clipping
  behavior, same pixel offsets) — proving it predates this task and is not specific to the new
  `"RETENTION OPERATIONS ASSISTANT"` text. Fixing it would require changing `theme.py`'s global
  header CSS, affecting all six pages — explicitly out of scope for an identity/personality-only
  ticket per this task's own instructions ("avoid modifying unrelated dashboard pages"). Left
  unfixed; flagged here for whichever future ticket addresses global header layout.
- **A pre-existing interaction quirk, not caused by this task**: `retention_copilot.py`'s free-text
  input (`copilot_freetext`) retains its typed value across reruns (standard Streamlit widget
  behavior for a `key`-bound `text_input`). If a manager types a free-text question and then clicks
  a *different* suggested-question button without first clearing the free-text box, the still-
  non-empty free-text value re-overwrites `copilot_asked` on the very next rerun, and the button
  click appears to have no effect. Confirmed live in this session, and confirmed this code path is
  unchanged by P1-07, P1-08, or P1-09 (present since Task 04). Not fixed here — it is a workflow/
  interaction-order issue unrelated to assistant identity or personality, not something this
  ticket's scope covers.
- The identity/voice system-prompt text has **not been exercised by a real LLM call** —
  `ANTHROPIC_API_KEY` is not configured in this environment (confirmed, §8). Its effect on actual
  model-generated wording is therefore unverified, consistent with the same honestly-flagged gap
  every prior task's report (03, 04, 06, 07, 08) has carried forward.

---

## 12. Explicit confirmation that P1-10 and all later tasks were NOT started

No file related to "Numbers-to-Decisions Pass" (P1-10), "Evidence → Recommendation Presentation"
(P1-11), "LLM Tool-Use Production Hardening" (P1-12), or any later tracker row was created or
modified. Only `dashboard/lib/agent.py`, `dashboard/pages/retention_copilot.py`,
`tests/test_agent_orchestration.py`, `tests/test_retention_intelligence_ui.py`, and the tracker's
P1-09 status cell were changed. Work stopped at the boundary of P1-09's own scope as read from the
tracker.

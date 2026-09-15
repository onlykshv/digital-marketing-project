# P1-12 Validation Report — Agent Reliability & Failure-Mode Hardening

**Tracker row:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, ID `P1-12`, Stage "AI Product", Priority P1.
**Status change:** `TODO` → `REVIEW` (this report; not `DONE` — reserved for independent sign-off).

## 1. Exact requirement from the tracker

**Issue:** "The optional Anthropic path has not had a real API completion test in the current environment."

**Claude Fix Prompt:** "Harden missing key, timeout, malformed tool call, invalid tool, malformed response, partial failure and repeated-call cases. Keep allow-list and bounded loop. If an API key exists, run a controlled live smoke test; otherwise never fabricate one and expand contract tests. Deterministic fallback must always work. No analytical changes/dependencies unless strictly necessary."

**Acceptance Criteria:** "All failure modes safely fall back; no arbitrary execution; deterministic path works without key; live test reported only if actually performed; tests pass."

## 2. Failure modes audited (before touching code)

Read `agent.py`, `agent_tools.py`, `llm_provider.py`, and every existing test in `test_agent_orchestration.py` before making any change, to establish what was already hardened vs. genuinely missing, per failure class:

| Failure class | Already hardened before P1-12 | Gap found |
|---|---|---|
| Missing API key | Yes — `ask()` checks `llm_provider.is_configured()` before ever entering the tool loop | None |
| Invalid/hallucinated tool name | Yes — explicit `_TOOL_DISPATCH` allow-list, no getattr/eval anywhere | None (only added a structural regression test) |
| Malformed tool call (missing/invalid args, wrong types) | Mostly — each dispatch function validates its own required args; `_execute_tool`'s catch-all guarantees no exception escapes | None functionally, but no explicit test coverage of several concrete shapes |
| LLM/API timeout or request failure | Partially — any request failure already raises `ProviderUnavailable`, caught by `ask()` | No explicit request timeout was ever set — the SDK's own multi-minute default applied |
| Malformed tool response | **No** — `_execute_tool` returned whatever the dispatch function returned, unchecked; `result.get("ok")` in `_run_tool_loop` would crash on a non-dict result | Real latent gap |
| Malformed LLM/provider response shape | **No** — `_run_tool_loop` indexed `response["stop_reason"]`, `response["text"]`, and each `call["name"]`/`call["input"]`/`call["id"]` directly; any missing key would raise an uncaught `KeyError` into the page | Real latent gap |
| Partial tool failure (do not present incomplete evidence as complete) | **No** — `AgentResponse.grounded` was computed as `len(tools_used) > 0` (merely "a tool was attempted"), not "a tool actually succeeded" | Real gap: an answer where every tool call failed could still be marked `grounded=True` |
| Repeated/duplicate tool calls | Bounded only by the hard turn cap; no deduplication of identical repeated calls | Minor gap (not unsafe, but wasteful/undefended) |
| Turn-cap-exceeded / malformed-response dead ends not reaching a deterministic outcome | **No** — both cases returned an "AI couldn't finish" `AgentResponse` directly from `_run_tool_loop`, never routing through `_deterministic_fallback` | Real gap against the explicit "must reach a safe deterministic outcome" requirement |

## 3. Files changed and why

- **`dashboard/lib/agent.py`** — the orchestration layer itself; every safeguard below lives here.
- **`dashboard/lib/llm_provider.py`** — added an explicit, bounded request timeout (see §4).
- **`tests/test_agent_orchestration.py`** — 32 new P1-12 tests (one new "P1-12 regression tests" section) plus one existing test (`test_tool_loop_turn_cap_is_enforced`) deliberately updated because its assertions encoded the OLD (now intentionally changed) behavior.

No other file was touched. `agent_tools.py`, `copilot_engine.py`, `copilot_data.py`, `data.py`, every dashboard page, `notebooks/`, `models/`, `outputs/`, `src/` — all untouched (confirmed via `find notebooks models outputs src -newermt ... ` → 0 files).

## 4. Exact safeguards implemented

**`_execute_tool` now validates its own return value.** Previously it trusted that `_TOOL_DISPATCH[name](arguments, ctx)` always returns a well-shaped `{"ok","data","error"}` dict. Now, after the existing try/except (which already catches a raised exception), the result is checked: if it isn't a dict, or `"ok"` isn't present and boolean, it's coerced into `{"ok": False, "data": None, "error": "Tool returned a malformed result"}`. This closes the exact "tool returns None / a bare string / a dict missing ok" gap — directly the "malformed tool response" failure class — without changing any real tool's actual behavior (every real dispatch function already returns the correct shape; this only guards against a hypothetical future regression in one of them).

**`_run_tool_loop` no longer trusts the provider response shape.** Every field read from `complete_with_tools()`'s return value now goes through `.get(...)` with a safe default instead of `[...]` indexing. A non-dict response, or a response claiming `stop_reason == "tool_use"` with an empty `tool_calls` list, is treated as a genuine dead end (see next point) rather than risking a `KeyError`/`TypeError` escaping into the page. Each individual `tool_calls` entry is also defensively parsed: a missing `"name"` safely falls through `_execute_tool`'s own allow-list rejection (an empty/`None` name simply isn't a dispatch key); a missing `"input"` defaults to `{}`; a missing `"id"` gets a locally generated placeholder so a `tool_result` can still be built rather than the call being silently dropped (dropping it would violate the Anthropic API's requirement that every `tool_use` gets a matching `tool_result`).

**Every LLM-loop dead end now reaches the real deterministic fallback, not an "AI couldn't finish" message.** A new internal exception, `_OrchestrationFailed`, is raised from three places: (1) the turn cap is exhausted (previously: returned a static apology `AgentResponse`), (2) the provider response isn't a usable dict, (3) the provider claims tool use but names no tool. `ask()` now catches `_OrchestrationFailed` exactly like `llm_provider.ProviderUnavailable` — both discard whatever partial state that attempt gathered and call `_deterministic_fallback(question, ctx, reason=str(e))`, the SAME guaranteed-working path used when no API key is configured at all. This is the direct implementation of the ticket's own words: "the system must reach a safe deterministic outcome," and of "fall back safely when the requested answer cannot be grounded completely" — a partially-completed, ungroundable LLM attempt is never shown as if it were a finished answer; it's discarded and a fresh, real deterministic answer is computed instead.

**`ask()` gained a final, broad safety net.** After the two specific `except` clauses above, a last `except Exception` catches any truly unforeseen bug in the orchestration loop and routes it to `_deterministic_fallback` too, with a reason string naming only the exception's type (`unexpected orchestration error: {type(e).__name__}`) — never a raw message or traceback that could leak internals. This is the same discipline this project already applies at its other module boundaries (`llm_provider.py`'s own broad catch, `_execute_tool`'s own broad catch) — now applied consistently at the top-level `ask()` boundary too, which is the concrete guarantee behind "No exception should escape into the UI."

**`grounded` now means "at least one tool call actually succeeded," not "a tool was attempted."** Changed from `grounded=len(tools_used) > 0` to `grounded=any(c.ok for c in tool_calls)` everywhere it's computed in the LLM path. This is the direct fix for "do not present incomplete evidence as complete": previously, a question where the ONLY tool call failed (e.g. a hallucinated or mistyped customer ID) would still be reported as `grounded=True`, purely because a tool was attempted.

**Repeated identical tool calls are no longer redundantly re-executed.** A per-loop cache (`seen_results`, keyed by a stable `tool_name + JSON-serialized-sorted-arguments` signature) means that if the model requests the exact same tool with the exact same arguments twice, the underlying deterministic computation runs once and the cached result is reused for the second request. Every `tool_use` the model issues still gets its own `tool_result` reply (required by the API contract) and its own `ToolCallRecord` — this is purely an efficiency/robustness improvement layered on top of the existing hard turn cap, never a replacement for it. The hard cap (`_MAX_TOOL_LOOP_ITERATIONS = 6`, unchanged) remains the actual bound on how many rounds a pathologically repetitive model can consume.

**An explicit, bounded request timeout.** `llm_provider.py` previously constructed the Anthropic client with no `timeout=` argument, meaning a hung request would sit on the SDK's own multi-minute default before failing. Added `_REQUEST_TIMEOUT_SECONDS = 20.0`, passed to `anthropic.Anthropic(..., timeout=...)` in both `complete()` and `complete_with_tools()`. A timeout now raises inside the existing `try` block exactly like any other request failure and is caught by the existing broad `except Exception` → `ProviderUnavailable` translation — no new error-handling code was needed at the call site, only the bound itself.

**No changes to the allow-list, the dispatch mechanism, or the turn-cap value.** `_TOOL_DISPATCH` is still the sole, explicit mapping from tool name to function; there is still no `getattr`, `eval`, `exec`, or `__import__` anywhere in `agent.py` (verified by a new structural test that scans the actual source for these four literal substrings). `_MAX_TOOL_LOOP_ITERATIONS` is unchanged at `6`.

## 5. Test count and results

**32 new tests** added to `tests/test_agent_orchestration.py`'s new "P1-12 regression tests" section, one per concrete scenario in every failure class the tracker names:

- Missing API key (1): the LLM boundary function is proven never even called (it's mocked to raise `AssertionError` if invoked) when no key is configured.
- Timeout/request failure (3): failure on the very first turn falls back deterministically; failure mid-loop (after one real tool already succeeded) discards that partial state and falls back to a fresh, real deterministic answer; a contract test (no network call) proving the Anthropic client is constructed with a real, bounded `timeout` value.
- Malformed tool call (6): missing name, empty-string name, arguments not a dict (four variants), wrong argument type (`limit` as a string), invalid `customer_id` type (four variants), and a mocked-loop end-to-end case proving the loop still reaches a final answer.
- Invalid/hallucinated tool name (2): a structural source scan proving no `getattr(`/`eval(`/`exec(`/`__import__(` exists anywhere in `agent.py`; a more adversarial "plausible-sounding" hallucinated tool name still rejected.
- Malformed tool response (7): `_execute_tool` coercing a `None` return, a non-dict return (three variants), a dict missing `"ok"`, and confirming the coerced result never invents `data`; a tool that raises handled safely; the full provider-response-shape failures (not a dict, missing expected keys, `tool_use` with no tool_calls) all falling back deterministically; a malformed individual `tool_calls` entry (missing `input`/`id`) handled without crashing.
- Partial tool failure (2): two tool calls in one turn, one succeeding and one failing — both results forwarded honestly, the failure's `data` stays `None`, `grounded=True` because at least one succeeded; a single failing tool call — `grounded=False`, directly proving the new honest-grounding semantics.
- Repeated tool calls (2): an identical duplicate call is not re-executed (proven by a call-counting wrapper) but the model still receives a real result for both requests; different arguments are never conflated by the dedup key.
- Maximum-turn/bounded-loop (1, plus the updated existing test): the updated `test_tool_loop_turn_cap_is_enforced` now asserts the mocked provider was called exactly `_MAX_TOOL_LOOP_ITERATIONS` times (proving the actual bound directly, independent of what happens after) and that the result is a genuine deterministic-fallback answer.
- Cross-cutting (5): a completely unforeseen exception from `_run_tool_loop` still falls back safely; the deterministic-fallback answer produced after a simulated timeout still never calls Model Risk Score a probability; a simulated crash still preserves the correct search-customers → Customer 360 handoff data shape; the tool allow-list/dispatch table is unaffected; the deterministic tools' actual numeric output is byte-identical to before (no analytical drift).

**Complete regression results (this run, fresh):**

```
tests/test_agent_tools.py               40 passed, 0 failed
tests/test_agent_orchestration.py      100 passed, 0 failed   (68 pre-P1-12 + 32 new, incl. 1 deliberately updated)
tests/test_retention_intelligence_ui.py 44 passed, 0 failed
tests/test_manager_workflow.py           8 passed, 0 failed
tests/test_information_density.py        7 passed, 0 failed
------------------------------------------------------------------
TOTAL                                  199 passed, 0 failed
```

**The one deliberately updated test**, per this project's established practice (update, don't weaken, when a test encoded behavior that was intentionally and correctly changed): `test_tool_loop_turn_cap_is_enforced` previously asserted `result.fallback_reason == "tool-call loop exceeded its turn limit"` and `len(result.tool_calls) == 6`. Since turn-cap-exceeded now routes through `_deterministic_fallback` (a deliberate P1-12 change — see §4), the returned `AgentResponse` is a genuine deterministic answer with its own, independently-correct `tool_calls` (not the 6 discarded LLM-loop attempts). The test now asserts the real safety property directly — the mocked provider's call count never exceeds `_MAX_TOOL_LOOP_ITERATIONS` — plus `result.used_llm is False` and the same `fallback_reason` string (still passed through unchanged into the fallback call).

## 6. Deterministic fallback validation

Every failure-mode test above that induces a failure (timeout, malformed response, malformed provider shape, unexpected exception) asserts three things together: `result.used_llm is False`, `result.grounded is True`, and the presence of a real, grounded piece of the actual deterministic answer (e.g. `"Headline:"` for the aggregate question, or real `search_customers` rows that resolve back through `agent_tools.get_customer`). This proves the fallback isn't just "some text was returned" but the SAME real, grounded, already-tested deterministic answer a manager would get with no AI provider configured at all — traced directly from `_deterministic_fallback`'s existing, unmodified implementation, not duplicated or reimplemented.

## 7. API-key availability

`ANTHROPIC_API_KEY` was checked at the start of this task and is **not present** in this environment (`'ANTHROPIC_API_KEY' in os.environ` → `False`). Per the tracker's explicit instruction, no key was fabricated, no test claims a real API completion occurred, and every failure-mode test above mocks only `lib.llm_provider.complete_with_tools` / `lib.llm_provider.is_configured` — the same established mocking boundary every pre-existing mocked-loop test in this file already uses — or exercises the real, live, unmocked deterministic-fallback path (which is genuinely live in this environment, since `is_configured()` really is `False`).

One test (`test_llm_provider_requests_use_a_bounded_explicit_timeout`) sets a placeholder value (`"sk-test-unit-test-only-not-real"`) into `ANTHROPIC_API_KEY` for the scope of that single test, via `mock.patch.dict`, restored immediately after — and mocks `anthropic.Anthropic` itself so no network call is ever attempted. This is a parameter-passing contract test (proving the client is *constructed* with a bounded `timeout=` argument), not a claim of live behavior; it is clearly commented as such in the test itself.

## 8. Live smoke test — NOT performed (no key)

**No live LLM/tool-calling smoke test was performed, because no `ANTHROPIC_API_KEY` exists in this environment.** Per the tracker's explicit instruction ("otherwise never fabricate one and expand contract tests"), the LLM tool-calling path (`_run_tool_loop`, `llm_provider.complete`/`complete_with_tools` against a real Anthropic endpoint) was **not** exercised against a real API in this task. All coverage of that path is via `unittest.mock`-based contract/unit tests described in §5, which validate `agent.py`'s own orchestration logic given a controlled response shape, not real model behavior. If a real key is added to this environment in the future, a genuine live smoke test (one real tool-calling exchange, one real induced-failure exchange) should be run and reported separately — this report makes no claim that one was.

## 9. Live browser validation

Fresh Streamlit server started on port 8692 (a new port, guaranteeing a clean process). `ANTHROPIC_API_KEY` confirmed absent before starting. Server log clean, no import errors.

- **Normal deterministic aggregate question** ("How many customers are at elevated risk?"): rendered correctly with the full P1-11 six-part structure and the honest `[AI synthesis unavailable: no AI provider is configured for this session -- showing the grounded deterministic answer]` banner, no crash.
- **Segment question** (segment picker set to "At-Risk Veteran", "Tell me about At-Risk Veteran customers."): rendered correctly with the full structure, no crash.
- **Customer-specific question**: loaded the full customer table, searched a real customer ID, confirmed the customer context correctly took precedence over the previously-selected segment (existing, unmodified behavior), asked "Why is this customer at risk?" — rendered correctly with the full structure, no crash.
- **An accidental free-text edge case** (a stray single-character "a" question while a customer was in focus, from an interaction mis-click) exercised the "unrecognized question" branch of the customer-intent classifier live and rendered its honest guidance message cleanly — an unplanned but useful additional confirmation that an edge-case input doesn't crash the page.
- **No-API-key fallback banner**: present and correct on every answer above (`AI synthesis unavailable... showing the grounded deterministic answer` / `Deterministic answer -- AI synthesis not used`).

**What was NOT live-tested in the browser:** any of the mocked failure scenarios (timeout, malformed tool response, malformed provider response, partial tool failure, repeated calls) — these cannot be induced through the real UI without a real, misbehaving LLM provider to connect to, and this environment has none. Those scenarios are covered exclusively by the unit/contract tests in §5, run directly against `agent.py`'s functions with a mocked `llm_provider` boundary. This is stated plainly rather than implied to have been browser-verified.

## 10. Confirmation: allow-list and bounded loop intact

- `agent._TOOL_DISPATCH` still contains exactly the same 9 entries as `agent_tool_schemas.TOOL_NAMES` (verified by `test_p1_12_hardening_did_not_change_the_tool_allowlist_or_dispatch_table`, and implicitly by every pre-existing dispatch-table test still passing unmodified).
- No `getattr(`, `eval(`, `exec(`, or `__import__(` exists anywhere in `agent.py` (verified by a new structural source scan, `test_no_getattr_eval_exec_or_dynamic_import_anywhere_in_agent_py`).
- `_MAX_TOOL_LOOP_ITERATIONS` is unchanged at `6`; the for-loop bound in `_run_tool_loop` was not touched — only what happens *after* it's exhausted changed (now raises `_OrchestrationFailed` instead of returning an apology `AgentResponse` directly).

## 11. Confirmation: no analytical logic changed

- `agent_tools.py`, `copilot_engine.py`, `copilot_data.py`, `data.py` — byte-identical to before P1-12 (not touched).
- `test_p1_12_hardening_did_not_change_any_analytical_values` directly re-derives the aggregate metrics from the real data and confirms they match the source `risk_summary` values exactly.
- No model, threshold, score, probability, HRR calculation, or dataset file was modified. `notebooks/`, `models/`, `outputs/`, `src/` confirmed untouched via `find ... -newermt`.
- No new dependency was added — the only new capability used (`anthropic.Anthropic(timeout=...)`) is an existing parameter of the already-installed `anthropic` SDK (version 1.4.0, confirmed installed and confirmed to accept a `timeout` constructor argument before use).

## 12. Known limitations

- The LLM tool-calling path's real-world behavior (does the actual Claude model call tools sensibly, recover from a real malformed response the way the mocks simulate, etc.) remains genuinely untested against a live endpoint, because no API key exists in this environment. Everything in §5 validates `agent.py`'s own defensive code, not live model behavior.
- The repeated-call cache is scoped to a single `ask()` call (one question, one `_run_tool_loop` invocation) and is intentionally not persisted across questions — a deliberate scope decision (deterministic tools' results are only guaranteed stable within one already-loaded `AgentContext`, and caching across questions would add complexity with no clear reliability benefit).
- The bounded request timeout (20 seconds) is a judgment call, not a value specified by the tracker — chosen to be generous enough for a real multi-turn tool-calling exchange while still bounded well short of the SDK's own multi-minute default. If a real key is added later and this proves too short/long in practice, it should be tuned then, with real data.
- `_OrchestrationFailed` is an internal-only exception (module-private, never exported) — this report notes it exists for the reader's benefit but it is not part of any public contract.

## 13. Confirmation

P1-13 and all later tickets were not started or touched as part of this ticket's own implementation work; per the user's separate continuation directive received during this task, work proceeds automatically to P1-13 immediately after this ticket is marked `REVIEW` in the tracker — that transition and all subsequent tickets are documented in their own, separate validation reports.

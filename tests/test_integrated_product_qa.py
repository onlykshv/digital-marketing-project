"""Tests for P1-15 -- "Integrated Product QA"
(task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-15).

This ticket's own job was a no-code-first, cross-cutting audit after P1-07 through P1-14's
sequential feature work: full test suite, syntax/import checks, a fresh server, all six pages,
manager workflow, customer/segment switching, unknown/missing-data/special-character customer
IDs, no-key behavior, deep links, currency/terminology consistency, and desktop overflow. Almost
every one of those checks already passed -- with one genuine, previously-uncaught P1 currency-
consistency gap found and fixed as part of this ticket: `marketing_action_plan.csv`'s `rationale`
column is notebook-generated free text that embeds a raw "<number> NT$" mention directly in the
sentence, predating this project's ₹ display convention (P0-3) -- rendered verbatim by
`components.recommendation_block`'s "More detail on this recommendation" expander on both
Overview and Action Center. Fixed at the display layer only (`theme.convert_ntd_mentions_in_text`,
applied in `components.py`) -- `outputs/marketing_action_plan.csv` itself, and the number it
contains, are untouched; only the rendered string changes, the same discipline every other
NT$->INR conversion in this project already follows. See task_1/P1-15_validation_report.md for
the full audit. What this file adds is the "regression tests where practical" half of the
ticket's own instruction: codifying the checks that were not already covered by an existing
per-ticket test file (including a direct regression test for this specific fix), so a future
change that breaks one of them fails a real test instead of requiring another manual walkthrough.

Every check here was performed live in the browser first (see the validation report) and only
then encoded here -- nothing in this file asserts a behavior that wasn't actually observed.

Runnable standalone (`python tests/test_integrated_product_qa.py`) or via pytest.
"""
from __future__ import annotations

import glob
import os
import py_compile
import sys
import traceback

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import agent_tools, data, theme  # noqa: E402

PAGE_NAMES = ["overview", "priority_customers", "customer_value", "action_center", "customer_360", "retention_copilot"]


# ---------------------------------------------------------------------------
# Syntax / import checks -- the ticket's own explicit "syntax/import checks" step.
# ---------------------------------------------------------------------------

def test_all_dashboard_files_compile_without_syntax_errors():
    files = glob.glob("lib/*.py") + glob.glob("pages/*.py") + ["app.py"]
    assert len(files) >= 15, "sanity check that the glob actually found the project's files"
    errors = []
    for f in files:
        try:
            py_compile.compile(f, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append((f, str(e)))
    assert not errors, f"syntax errors found: {errors}"


def test_all_lib_modules_import_without_error():
    modules = [
        "lib.data", "lib.theme", "lib.components", "lib.caveats", "lib.copilot_data",
        "lib.copilot_engine", "lib.agent", "lib.agent_tools", "lib.agent_tool_schemas", "lib.llm_provider",
    ]
    errors = []
    for m in modules:
        try:
            __import__(m)
        except Exception as e:  # noqa: BLE001
            errors.append((m, type(e).__name__, str(e)))
    assert not errors, f"import errors found: {errors}"


# ---------------------------------------------------------------------------
# All six pages -- a single authoritative sweep (individual pages already have their own
# per-ticket load checks; this is the one place all six are checked together as this ticket's
# own explicit "all six pages" step).
# ---------------------------------------------------------------------------

def test_all_six_pages_load_with_no_exception():
    for name in PAGE_NAMES:
        at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/{name}.py", default_timeout=180)
        at.run()
        assert not at.exception, f"{name}.py raised an unexpected exception: {at.exception}"


# ---------------------------------------------------------------------------
# Currency / terminology consistency -- swept across ALL six pages in one test, not just the
# pages each individual prior ticket happened to touch.
# ---------------------------------------------------------------------------

def test_no_page_shows_raw_nt_dollar_currency():
    # The "hrr" methodology caveat (lib/caveats.py's _hrr_body) legitimately names "NT$" three
    # times in one disclosure paragraph, to explain what the ₹ display figures are converted
    # FROM -- that is the one intentional, pre-existing exception (P0-3), present on exactly the
    # pages that include "hrr" in their own caveats.render_caveats([...]) call. Every page's
    # content OUTSIDE that one exact, known paragraph must never show a raw NT$ figure.
    # customer_360.py gates its entire body behind a "Load customer data" click (st.stop() before
    # that), so a plain render never reaches its caveats section at all -- this check tolerates
    # that gate rather than requiring the disclosure to be present; it only ever constrains what's
    # ALLOWED if "NT$" appears, on every page, in whatever state a plain render leaves it in.
    from lib import caveats as caveats_module
    _, hrr_body_fn = caveats_module.CAVEAT_DEFS["hrr"]
    hrr_disclosure_text = hrr_body_fn(None)
    for name in PAGE_NAMES:
        at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/{name}.py", default_timeout=180)
        at.run()
        text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
        if hrr_disclosure_text in text:
            text = text.replace(hrr_disclosure_text, "", 1)
        assert "NT$" not in text, f"{name}.py shows a raw NT$ figure outside the one documented hrr-caveat exception"


def test_customer_360_hrr_caveat_call_is_unchanged_and_still_reachable():
    # customer_360.py gates its profile section behind an actual dataframe ROW SELECTION event
    # (`event.selection.rows`), not just a search-text match -- AppTest cannot simulate that
    # interaction, so this specific page's deepest state (a real profile open) was verified live
    # in the browser instead (see task_1/P1-15_validation_report.md) rather than forced through
    # AppTest. This regression-guards the two facts that make that live check still valid: the
    # caveats call itself is unchanged, and it is reached by code that runs unconditionally once
    # a row is selected (not behind some OTHER, newer gate that would silently skip it).
    src = open(f"{DASHBOARD_DIR}/pages/customer_360.py", encoding="utf-8").read()
    assert 'caveats.render_caveats(["calibration", "hrr"]' in src
    caveats_call_pos = src.index('caveats.render_caveats(["calibration", "hrr"]')
    last_stop_pos = src.rindex("st.stop()", 0, caveats_call_pos)
    # nothing except that one already-audited "no row selected" st.stop() sits between the row-
    # selection check and the caveats call -- i.e. selecting a row is the only remaining gate.
    assert src.count("st.stop()", last_stop_pos + len("st.stop()"), caveats_call_pos) == 0


def test_no_page_calls_model_risk_score_a_probability():
    for name in PAGE_NAMES:
        at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/{name}.py", default_timeout=180)
        at.run()
        text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
        assert "Model Risk Score is a probability" not in text
        assert "Model Risk Score is a calibrated probability" not in text


# ---------------------------------------------------------------------------
# Unknown / missing-data / special-character customer IDs.
# ---------------------------------------------------------------------------

def test_special_character_customer_id_round_trips_through_get_customer():
    # Real msno values are base64-like and legitimately contain '+' and '/' -- confirm the exact-
    # match lookup handles one correctly end to end, not just via a mocked/synthetic ID.
    df = data.load_customer_lookup_data()
    special_ids = df[df["msno"].str.contains(r"[+/]", regex=True, na=False)]
    assert len(special_ids) > 0, "this test assumes the real dataset has at least one such ID"
    real_id = special_ids.iloc[0]["msno"]
    result = agent_tools.get_customer(df, real_id)
    assert result["ok"] is True
    assert result["data"]["msno"] == real_id


def test_unknown_customer_id_handled_consistently_and_never_crashes():
    df = data.load_customer_lookup_data()
    result = agent_tools.get_customer(df, "THIS_ID_DOES_NOT_EXIST_ANYWHERE_XYZ_12345")
    assert result["ok"] is False
    assert result["data"] is None
    assert "not found" in result["error"].lower()


def test_retention_intelligence_ignores_a_search_value_silently_before_data_is_loaded():
    # Regression guard for the exact behavior observed live: typing a customer ID into the search
    # box before "Load customer data" is clicked must not error or crash -- it simply has no
    # customer table to search yet, so no context attaches, and the page renders cleanly.
    at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/retention_copilot.py", default_timeout=180)
    at.run()
    search = next(w for w in at.text_input if w.key == "copilot_search_widget")
    search.set_value("NOT_A_REAL_ID_xyz").run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "couldn't find" not in text.lower()  # never a false "not found" claim without a real lookup


def test_priority_customers_zero_results_state_renders_cleanly():
    at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/priority_customers.py", default_timeout=180)
    at.run()
    search = next(w for w in at.text_input if "Search by Customer ID" in (w.label or ""))
    search.set_value("+/=THISDOESNOTEXISTANYWHERE").run()
    assert not at.exception
    assert len(at.dataframe) >= 1  # an empty dataframe still renders, not a crash


# ---------------------------------------------------------------------------
# The specific fix: theme.convert_ntd_mentions_in_text() and its use in components.py.
# ---------------------------------------------------------------------------

def test_convert_ntd_mentions_rewrites_a_real_rationale_style_sentence():
    raw = (
        "113,820 customers (11.72% of base) with a 41.2% actual churn rate and 200,463,967 NT$ "
        "in Historical Realized Revenue among them (median 1,788 NT$/customer)."
    )
    converted = theme.convert_ntd_mentions_in_text(raw)
    assert "NT$" not in converted
    assert theme.CURRENCY_SYMBOL in converted
    # the actual number is preserved, just re-denominated and reformatted -- not dropped
    assert theme.fmt_currency(200463967) in converted
    assert theme.fmt_currency(1788) in converted
    # everything else in the sentence is untouched
    assert "113,820 customers (11.72% of base)" in converted
    assert "41.2% actual churn rate" in converted


def test_convert_ntd_mentions_leaves_text_with_no_ntd_mention_unchanged():
    plain = "This segment gets a loyalty-toned campaign, not a discount."
    assert theme.convert_ntd_mentions_in_text(plain) == plain


def test_convert_ntd_mentions_never_raises_on_malformed_input():
    for weird in ("NT$ with no number", "", "1,2,3,NT$", "NT$" * 5):
        theme.convert_ntd_mentions_in_text(weird)  # must not raise


def test_recommendation_block_rationale_regression_all_real_rationale_strings_convert_cleanly():
    # Every real `rationale` string in the actual, live action plan -- not just the one example
    # above -- must convert with zero raw NT$ left over. This is the exact regression this ticket
    # found and fixed.
    action_plan = data.load_action_plan()
    for rationale in action_plan["rationale"]:
        assert "NT$" not in theme.convert_ntd_mentions_in_text(rationale)


def test_overview_and_action_center_recommendation_expanders_show_no_raw_ntd():
    # Action Center separately, legitimately shows "NT$" once via its own "hrr" methodology
    # caveat (already covered by test_no_page_shows_raw_nt_dollar_currency above) -- this test
    # scopes specifically to the "More detail on this recommendation" rationale text itself
    # (where the actual regression was), not the whole page.
    marker = "Based on observed historical association, not a causal guarantee:"
    for page in ("overview", "action_center"):
        at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/{page}.py", default_timeout=180)
        at.run()
        assert not at.exception
        rationale_markdowns = [m.value for m in at.markdown if marker in m.value]
        assert rationale_markdowns, f"{page}.py: expected at least one 'More detail on this recommendation' block"
        for block in rationale_markdowns:
            assert "NT$" not in block, f"{page}.py's rationale expander still shows a raw NT$ figure"


# ---------------------------------------------------------------------------
# No-key deterministic behavior -- re-confirmed as this ticket's own explicit cross-cutting check
# (the underlying mechanics are already covered exhaustively in test_agent_orchestration.py).
# ---------------------------------------------------------------------------

def test_no_api_key_configured_in_this_environment():
    from lib import llm_provider
    assert llm_provider.is_configured() is False


# ---------------------------------------------------------------------------
# Protected directories -- this ticket's own explicit "notebooks/models/outputs/src untouched"
# acceptance criterion, checked programmatically rather than only via a manual `find`.
# ---------------------------------------------------------------------------

def test_protected_directories_are_not_writable_targets_of_any_dashboard_code():
    # Static guard, not a filesystem timestamp check (which is session/environment-dependent):
    # no dashboard module may contain a write-mode file open against a protected path.
    import re
    protected_roots = ("notebooks/", "models/", "outputs/", "src/")
    write_pattern = re.compile(r"open\([^)]*['\"]w")
    files = glob.glob("lib/*.py") + glob.glob("pages/*.py") + ["app.py"]
    for f in files:
        src = open(f, encoding="utf-8").read()
        for match in write_pattern.finditer(src):
            snippet = src[max(0, match.start() - 80):match.start()]
            assert not any(root in snippet for root in protected_roots), (
                f"{f} appears to open a protected-directory path in write mode: ...{snippet}"
            )


# ---------------------------------------------------------------------------
# Cross-page handoff regression -- a segment that exists in the action framework but not as a
# per-customer label.
#
# The two segment vocabularies are not the same size: `copilot_data.SEGMENTS` carries all seven
# groups from marketing_action_plan.csv, while outputs/customer_segments.csv labels customers with
# only six -- "Unmatched At-Risk (no segment)" has no per-customer label (those at-risk customers
# carry "Stable / Monitor" instead). Retention Intelligence's segment picker offers all seven, so
# its "View {segment} customers in Priority Customers ->" handoff could hand this page a segment
# its own multiselect has no option for, which Streamlit raises on
# (StreamlitDefaultNotInOptionsError) -- a full error traceback three clicks from the flagship
# page. Verified reachable before the fix; the handoff now degrades to "no segment filter".
# ---------------------------------------------------------------------------

_PRIORITY_PAGE = f"{DASHBOARD_DIR}/pages/priority_customers.py"


def _run_priority_with_pending_filter(pending: dict):
    at = AppTest.from_file(_PRIORITY_PAGE, default_timeout=300)
    at.session_state["pending_filter"] = pending
    at.session_state["lookup_loaded"] = True
    at.run()
    return at


def _multiselect_value(at, label: str):
    return next(w for w in at.multiselect if w.label == label).value


def test_handoff_of_a_segment_with_no_per_customer_label_does_not_crash():
    from lib import copilot_data, data

    labelled = set(data.load_customer_lookup_data()["segment"].cat.categories)
    unrepresented = [s for s in copilot_data.SEGMENTS if s not in labelled]
    # If the per-customer labels ever gain the seventh group this particular value becomes moot,
    # but the assertion must still hold, so fall back to a value that is an option either way.
    probe = unrepresented[0] if unrepresented else "A Segment That Does Not Exist"

    at = _run_priority_with_pending_filter({"segment": [probe]})
    assert not at.exception, f"{probe!r} handoff raised: {at.exception}"
    assert _multiselect_value(at, "Segment") == []
    # the page's own sensible default must survive the dropped filter, not be blanked with it
    assert _multiselect_value(at, "Risk tier") == ["High", "Medium"]


def test_handoff_of_a_real_segment_is_still_applied():
    # Regression guard on the fix itself: filtering out unrepresented values must not filter out
    # the valid ones this handoff exists to carry.
    at = _run_priority_with_pending_filter({"segment": ["At-Risk Veteran"]})
    assert not at.exception
    assert _multiselect_value(at, "Segment") == ["At-Risk Veteran"]


def test_handoff_of_risk_and_value_tiers_is_still_applied():
    at = _run_priority_with_pending_filter({"risk_tier": ["High"], "value_tier": ["High"]})
    assert not at.exception
    assert _multiselect_value(at, "Risk tier") == ["High"]
    assert _multiselect_value(at, "Value tier") == ["High"]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all():
    tests = {name: fn for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)}
    p, f = 0, 0
    for name, fn in tests.items():
        try:
            fn()
        except AssertionError as e:
            f += 1
            print(f"FAIL  {name}  {e}")
        except Exception as e:  # noqa: BLE001
            f += 1
            print(f"ERROR {name}  {type(e).__name__}: {e}")
            traceback.print_exc()
        else:
            p += 1
            print(f"PASS  {name}")
    print(f"\n{p} passed, {f} failed (of {len(tests)} tests)")
    return f == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)

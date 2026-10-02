"""Regression tests for the UI/UX refurbishment (task_1/UI_REFURBISHMENT_VALIDATION_REPORT.md).

The refurbishment changed presentation, not analytics -- but it also introduced (or fixed) a small
number of state and navigation behaviours, and each one is pinned here:

1. Priority Customers: a carried-over filter becomes the manager's own filter (it survives the next
   unrelated rerun, e.g. the click that selects a row), and the page marks the customer table as
   loaded for the session so Customer 360 / Retention Intelligence do not ask again.
2. Customer 360: a search that resolves to exactly one customer opens the profile directly.
3. New drill-downs that reuse the existing `pending_filter` / `copilot_segment_choice` contracts:
   Overview's priority-zone button, Customer Value's cell inspector, Action Center's per-play buttons.
4. The journey "Continue to ..." footer on each page, and its agreement with app.py's navigation.
5. Retention Intelligence's decision-brief renderer (answer-mode banner, evidence list, role lines,
   tool provenance) and its DATA -> TOOLS -> EVIDENCE -> DECISION band.
6. `theme.squash` -- the fix for raw markup leaking as a code block when an optional HTML fragment
   rendered empty inside an indented multi-line snippet.

Same conventions as every other test file here: AppTest against the real, current, no-API-key
environment, with cross-page `st.switch_page` / `st.page_link` asserted as the one expected
AppTest harness exception (pages run outside app.py's st.navigation registry).

Runnable standalone (`python tests/test_ui_refurbishment.py`) or via pytest.
"""
from __future__ import annotations

import os
import re
import sys
import traceback

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import agent_tool_schemas, data, theme  # noqa: E402

PAGES = f"{DASHBOARD_DIR}/pages"


def _page(name: str) -> str:
    return f"{PAGES}/{name}.py"


def _markdown(at) -> str:
    return " ".join(m.value for m in at.markdown)


def _is_harness_navigation_error(at) -> bool:
    return len(at.exception) == 1 and (
        "StreamlitPageNotFoundError" in str(at.exception[0]) or "Could not find page" in str(at.exception[0])
    )


def _block(at, marker: str) -> str:
    """The first rendered markdown block containing `marker`, skipping the page stylesheet (which
    names every CSS class and would otherwise match first)."""
    return next(m.value for m in at.markdown if marker in m.value and not m.value.startswith("<style>"))


def _multiselect(at, label: str):
    return next(w for w in at.multiselect if w.label == label)


# ---------------------------------------------------------------------------
# 1. Priority Customers -- carried filters persist; the table is marked loaded for the session.
# ---------------------------------------------------------------------------

def test_priority_customers_marks_the_customer_table_loaded_for_the_session():
    at = AppTest.from_file(_page("priority_customers"), default_timeout=300)
    at.run()
    assert not at.exception
    assert at.session_state["lookup_loaded"] is True


def test_carried_risk_and_value_filter_survives_the_next_unrelated_rerun():
    # The shape Overview's priority-zone button and Customer Value's inspector hand over.
    at = AppTest.from_file(_page("priority_customers"), default_timeout=300)
    at.session_state["pending_filter"] = {"risk_tier": ["High"], "value_tier": ["High"]}
    at.run()
    assert not at.exception
    assert _multiselect(at, "Risk tier").value == ["High"]
    assert _multiselect(at, "Value tier").value == ["High"]
    n_zone = int(data.load_risk_value_matrix().loc["High", "n_High"])
    assert f"{n_zone:,} customers match these filters" in " ".join(c.value for c in at.caption)

    next(w for w in at.text_input if w.label == "Search by Customer ID").set_value("").run()
    assert _multiselect(at, "Risk tier").value == ["High"]
    assert _multiselect(at, "Value tier").value == ["High"]
    assert "pending_filter" not in at.session_state


def test_carried_filter_is_announced_to_the_manager():
    at = AppTest.from_file(_page("priority_customers"), default_timeout=300)
    at.session_state["pending_filter"] = {"segment": ["At-Risk Veteran"]}
    at.run()
    assert "Filter carried over" in _markdown(at)
    assert "At-Risk Veteran" in _markdown(at)


def test_plain_visit_keeps_the_original_default_queue_and_no_handoff_note():
    at = AppTest.from_file(_page("priority_customers"), default_timeout=300)
    at.run()
    assert _multiselect(at, "Risk tier").value == ["High", "Medium"]
    assert _multiselect(at, "Value tier").value == []
    assert _multiselect(at, "Segment").value == []
    assert "Filter carried over" not in _markdown(at)


def test_queue_composition_band_counts_match_the_real_risk_value_matrix():
    rvm = data.load_risk_value_matrix()
    at = AppTest.from_file(_page("priority_customers"), default_timeout=300)
    at.run()
    text = _markdown(at)
    for rt in ("High", "Medium"):
        for vt in ("High", "Medium", "Low"):
            assert f"{int(rvm.loc[rt, f'n_{vt}']):,}" in text, f"{rt}/{vt} count missing from the queue composition"


# ---------------------------------------------------------------------------
# 2. Customer 360 -- a single match opens the profile directly.
# ---------------------------------------------------------------------------

def _unique_customer():
    df = data.load_customer_lookup_data()
    known = df.iloc[0]["msno"]
    assert int(df["msno"].str.contains(known, regex=False).sum()) == 1
    return df, df.iloc[0]


def test_customer_360_opens_the_profile_directly_for_a_single_match():
    df, row = _unique_customer()
    action_plan = data.load_action_plan()
    objective = action_plan.set_index("priority_group").loc[row["segment"], "marketing_objective"]

    at = AppTest.from_file(_page("customer_360"), default_timeout=300)
    at.session_state["lookup_loaded"] = True
    at.session_state["cust360_search"] = row["msno"]
    at.run()
    # The profile's last element is the Customer 360 -> Retention Intelligence page_link, which is
    # the one expected AppTest harness error -- everything before it rendered.
    assert _is_harness_navigation_error(at)
    text = _markdown(at)
    assert "Opened automatically" in text
    assert theme.esc(row["msno"]) in text
    # Romer-layout redesign: the profile is a customer brief (why at risk -> Action) beside a
    # Signals panel; the separate "Interpretation" column label is gone, its content is the
    # "Why is this customer at risk?" list asserted below.
    assert "Signals" in text and "Action" in text
    assert "Segment playbook" in text
    assert objective in text
    assert "Why is this customer at risk?" in text
    assert "SELECT A CUSTOMER" not in text
    # no results table to pick from -- the only grid rendered is the profile's own behaviour detail
    assert all("Indicator" in d.value.columns for d in at.dataframe)


def test_customer_360_with_several_matches_still_asks_for_a_selection():
    at = AppTest.from_file(_page("customer_360"), default_timeout=300)
    at.session_state["lookup_loaded"] = True
    at.session_state["cust360_search"] = "ab"
    at.run()
    assert not at.exception
    text = _markdown(at)
    assert "SELECT A CUSTOMER" in text
    assert "Opened automatically" not in text
    assert len(at.dataframe) == 1


def test_customer_360_behaviour_detail_and_tenure_guard_still_present_in_the_profile():
    # P2-16 guards must still sit in the code path the auto-open now reaches.
    src = open(_page("customer_360"), encoding="utf-8").read()
    assert src.index("auto_opened = len(filtered) == 1") < src.index('{"label": "Tenure"')


# ---------------------------------------------------------------------------
# 3. New drill-downs reuse the existing handoff contracts.
# ---------------------------------------------------------------------------

def test_overview_priority_zone_button_hands_the_zone_to_priority_customers():
    n_zone = int(data.load_risk_value_matrix().loc["High", "n_High"])
    at = AppTest.from_file(_page("overview"), default_timeout=300)
    at.run()
    btn = next(b for b in at.button if b.key == "ov_zone_to_priority")
    assert btn.label == f"Review the {theme.fmt_count(n_zone)} high-risk, high-value customers →"
    btn.click().run()
    assert _is_harness_navigation_error(at)
    assert at.session_state["pending_filter"] == {"risk_tier": ["High"], "value_tier": ["High"]}


def test_overview_hero_ladder_numbers_are_the_real_figures():
    rs = data.load_risk_summary()
    tiers = {t["tier"]: t for t in rs["risk_tiers"]}
    at = AppTest.from_file(_page("overview"), default_timeout=300)
    at.run()
    text = _markdown(at)
    assert theme.fmt_count(rs["n_customers_scored"]) in text
    assert theme.fmt_count(data.customers_requiring_intervention(data.load_action_plan())) in text
    assert theme.fmt_count(tiers["High"]["n_customers"]) in text
    assert theme.fmt_count(int(data.load_risk_value_matrix().loc["High", "n_High"])) in text
    # the thresholds quoted in the ladder are read from the scoring summary, not hard-coded
    assert f"{rs['recommended_thresholds']['medium_risk_threshold']:.2f}" in text
    assert f"{rs['recommended_thresholds']['high_risk_threshold']:.2f}" in text


def test_overview_attention_funnel_bars_are_drawn_to_true_share():
    # Romer-layout redesign: the attention story is a four-row funnel whose bar widths are linear
    # shares of the real scored base (no log scale, no exaggeration of the small groups), and each
    # stage is a subset of the one before it.
    rs = data.load_risk_summary()
    tiers = {t["tier"]: t for t in rs["risk_tiers"]}
    n_scored = rs["n_customers_scored"]
    stages = [
        n_scored,
        data.customers_requiring_intervention(data.load_action_plan()),
        tiers["High"]["n_customers"],
        int(data.load_risk_value_matrix().loc["High", "n_High"]),
    ]
    at = AppTest.from_file(_page("overview"), default_timeout=300)
    at.run()
    funnel = _block(at, "ri-funnel")
    rows = re.findall(r'data-n="(\d+)" data-share="([\d.]+)"', funnel)
    assert [int(n) for n, _ in rows] == stages
    widths = [float(w) for w in re.findall(r'<i style="width:([\d.]+)%;', funnel)]
    assert len(widths) == 4
    for (n, _), w in zip(rows, widths):
        assert abs(w - int(n) / n_scored * 100) < 1e-3
    assert abs(widths[0] - 100.0) < 1e-6
    assert widths == sorted(widths, reverse=True)  # each stage nests inside the previous one


def test_customer_value_inspector_defaults_to_the_priority_zone_and_drills_down():
    rvm = data.load_risk_value_matrix()
    at = AppTest.from_file(_page("customer_value"), default_timeout=300)
    at.run()
    assert not at.exception
    drill = next(b for b in at.button if b.key == "cv_drill")
    assert drill.label == f"Review these {int(rvm.loc['High', 'n_High']):,} customers in Priority Customers →"

    at.segmented_control(key="cv_risk").set_value("Medium").run()
    drill = next(b for b in at.button if b.key == "cv_drill")
    assert drill.label == f"Review these {int(rvm.loc['Medium', 'n_High']):,} customers in Priority Customers →"
    drill.click().run()
    assert _is_harness_navigation_error(at)
    assert at.session_state["pending_filter"] == {"risk_tier": ["Medium"], "value_tier": ["High"]}


def test_customer_value_matrix_shows_every_cell_from_the_real_matrix():
    rvm = data.load_risk_value_matrix()
    at = AppTest.from_file(_page("customer_value"), default_timeout=300)
    at.run()
    matrix = _block(at, "ri-matrix")
    for rt in ("Low", "Medium", "High"):
        for vt in ("Low", "Medium", "High"):
            assert theme.fmt_count(rvm.loc[rt, f"n_{vt}"]) in matrix
            assert f"{rvm.loc[rt, f'churn_rate_pct_{vt}']:.1f}%" in matrix
    assert matrix.count("Priority zone") == 1


def test_action_center_play_buttons_use_the_existing_handoff_contracts():
    opportunities = data.priority_opportunities(data.load_action_plan())
    p1, p2 = opportunities.iloc[0]["priority_group"], opportunities.iloc[1]["priority_group"]

    at = AppTest.from_file(_page("action_center"), default_timeout=300)
    at.run()
    next(b for b in at.button if b.key == "view_pc_action_center_p1").click().run()
    assert _is_harness_navigation_error(at)
    assert at.session_state["pending_filter"] == {"segment": [p1]}

    at2 = AppTest.from_file(_page("action_center"), default_timeout=300)
    at2.run()
    next(b for b in at2.button if b.key == "ask_ri_action_center_p2").click().run()
    assert _is_harness_navigation_error(at2)
    assert at2.session_state["copilot_segment_choice"] == p2


def test_segment_handoffs_clear_an_earlier_customer_focus():
    # Retention Intelligence gives a customer in focus precedence over a segment. Every explicit
    # "Ask Retention Intelligence about <segment>" handoff must therefore clear the shared customer
    # search, or a manager who looked at a customer earlier lands back on that customer instead of
    # the segment they just asked about (reproduced live before the fix).
    known = data.load_customer_lookup_data().iloc[0]["msno"]
    for page, key in [("overview", "hero_ask_ri"),
                      ("action_center", "ask_ri_action_center"), ("action_center", "ask_ri_action_center_p2")]:
        at = AppTest.from_file(_page(page), default_timeout=300)
        at.session_state["cust360_search"] = known
        at.run()
        next(b for b in at.button if b.key == key).click().run()
        assert _is_harness_navigation_error(at), f"{page}/{key}"
        assert at.session_state["cust360_search"] == "", f"{page}/{key} left the earlier customer in focus"
        assert at.session_state["copilot_segment_choice"], f"{page}/{key} did not carry a segment"


def test_retention_intelligence_lands_in_segment_mode_after_a_segment_handoff():
    at = AppTest.from_file(_page("retention_copilot"), default_timeout=300)
    at.session_state["lookup_loaded"] = True
    at.session_state["cust360_search"] = ""
    at.session_state["copilot_segment_choice"] = "At-Risk Veteran"
    at.run()
    assert not at.exception
    text = _markdown(at)
    assert "Segment in focus" in text and "At-Risk Veteran" in text
    assert "Analysing customer" not in text


def test_action_center_playbook_index_lists_all_seven_groups_with_real_figures():
    action_plan = data.load_action_plan()
    at = AppTest.from_file(_page("action_center"), default_timeout=300)
    at.run()
    index = _block(at, "ri-pb")
    for _, r in action_plan.iterrows():
        assert r["priority_group"] in index
        assert f"{r['churn_rate_pct']:.1f}%" in index
        assert theme.fmt_currency(r["total_HRR"]) in index


# ---------------------------------------------------------------------------
# 4. Journey footer.
# ---------------------------------------------------------------------------

def test_journey_matches_the_app_navigation_order_and_titles():
    src = open(f"{DASHBOARD_DIR}/app.py", encoding="utf-8").read()
    registered = re.findall(r'st\.Page\(str\(PAGES_DIR / "(\w+)\.py"\), title="([^"]+)"', src)
    assert [(f"pages/{f}.py", t) for f, t in registered] == [(j["page"], j["name"]) for j in theme.JOURNEY]


def test_each_page_offers_the_next_step_of_the_journey():
    for i, name in enumerate(["overview", "priority_customers", "customer_value", "action_center"]):
        nxt = theme.JOURNEY[i + 1]
        at = AppTest.from_file(_page(name), default_timeout=300)
        at.run()
        assert not at.exception, f"{name}: {at.exception}"
        btn = next(b for b in at.button if b.key == f"next_{name}")
        assert btn.label == f"Continue to {nxt['name']} →"
        btn.click().run()
        assert _is_harness_navigation_error(at), f"{name}: next-step button did not attempt navigation"


# ---------------------------------------------------------------------------
# 5. Retention Intelligence -- the decision-brief renderer and the pipeline band.
# ---------------------------------------------------------------------------

def _render_fake_brief():
    import sys
    sys.path.insert(0, r"D:\digital-marketing-project\dashboard")
    from lib import components

    class FakeResponse:
        answer = "\n".join([
            "[AI synthesis unavailable: test reason -- showing the grounded deterministic answer]",
            "",
            "Headline: The test finding.",
            "High risk: 10 customers.",
            "Total Historical Realized Revenue: ₹1.00M.",
            "Evidence: Alpha: 1; Beta: 2; Defining characteristics: first clause; second clause",
            "Why it matters: because it is tested.",
            "Recommended action: Do the tested thing.",
            "Avoid: Do not do the untested thing.",
            "Confidence/limitations: a tested caveat.",
            "Recommended next step: keep testing.",
        ])
        tools_used = ["get_segment", "compare_to_champions", "get_segment"]
        tool_calls = []
        grounded = True
        used_llm = False
        fallback_reason = "no AI provider is configured for this session"

    components.agent_response_block(FakeResponse())


def test_decision_brief_renders_every_line_in_order_with_its_contract():
    at = AppTest.from_function(_render_fake_brief, default_timeout=180)
    at.run()
    assert not at.exception
    md = [m.value for m in at.markdown]
    text = " ".join(md)
    captions = " ".join(c.value for c in at.caption)

    banner = next(v for v in md if "ri-mode-banner" in v and not v.startswith("<style>"))
    assert "AI synthesis unavailable: test reason" in banner
    finding = next(v for v in md if "The test finding." in v)
    assert "font-size:1.18rem" in finding
    assert "**High risk:** 10 customers." in md
    assert "**Total Historical Realized Revenue:** ₹1.00M." in md
    evidence = next(v for v in md if v.startswith("**Evidence:**"))
    assert "- Alpha: 1" in evidence and "- Beta: 2" in evidence
    # a clause with no label of its own stays attached to the fact it belongs to
    assert "- Defining characteristics: first clause; second clause" in evidence
    assert "**Why it matters:** because it is tested." in md
    assert "**Recommended action:** Do the tested thing." in md
    assert "**Avoid:** Do not do the untested thing." in md
    assert "**Recommended next step:** keep testing." in md
    assert "Confidence/limitations: a tested caveat." in captions
    assert "Confidence/limitations:" not in text
    order = [text.index(s) for s in ("The test finding.", "**Evidence:**", "**Why it matters:**", "**Recommended action:**", "**Avoid:**", "**Recommended next step:**")]
    assert order == sorted(order)
    provenance = next(v for v in md if "ri-prov" in v and not v.startswith("<style>"))
    assert "Segment profile" in provenance and "Champions benchmark" in provenance
    assert provenance.count("Segment profile") == 1  # de-duplicated
    assert "Deterministic answer -- AI synthesis not used" in captions


def test_retention_intelligence_states_its_pipeline_and_live_mode_honestly():
    at = AppTest.from_file(_page("retention_copilot"), default_timeout=300)
    at.run()
    assert not at.exception
    text = _markdown(at)
    assert f"{len(agent_tool_schemas.TOOL_NAMES)} read-only analytical tools" in text
    assert "Deterministic mode" in text  # no API key in this environment
    assert "AI synthesis over tool results" not in text


def test_retention_intelligence_answer_appears_beside_the_commands():
    # The console is two columns: commands on the left, the brief on the right, so an answer is
    # visible next to the question that produced it.
    at = AppTest.from_file(_page("retention_copilot"), default_timeout=300)
    at.run()
    next(b for b in at.button if b.label == "How many customers are at elevated risk?").click().run()
    assert not at.exception
    command_col = next(c for c in at.columns if any(b.label == "Which segment needs attention?" for b in c.button))
    answer_col = next(c for c in at.columns if any("Retention Intelligence responds" in m.value for m in c.markdown))
    assert command_col is not answer_col
    assert not any("Retention Intelligence responds" in m.value for m in command_col.markdown)


# ---------------------------------------------------------------------------
# 6. theme.squash -- no raw markup can leak as a code block.
# ---------------------------------------------------------------------------

def test_squash_removes_blank_and_indented_lines_that_markdown_would_treat_as_code():
    snippet = '<div class="a">\n        <div>x</div>\n        \n        </div>'
    out = theme.squash(snippet)
    assert "\n" not in out
    assert out == '<div class="a"> <div>x</div> </div>'


def test_masthead_without_an_aside_is_a_single_line_of_markup():
    at = AppTest.from_file(_page("customer_value"), default_timeout=300)
    at.run()
    mast = _block(at, 'class="ri-mast"')
    assert "\n" not in mast
    assert "</div>\n" not in mast


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

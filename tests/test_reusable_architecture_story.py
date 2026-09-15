"""Tests for P1-14 -- "KKBox-to-Reusable Architecture Story"
(task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-14).

Context: test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md's "Part 8 -- KKBOX vs. reusable-platform
audit" and "Part 9 -- Technical defensibility audit" already did the underlying fact-finding this
ticket needed (which files are KKBox-schema-specific, which are generic; the precise, non-
overclaimed wording for what's reusable) and explicitly flagged "why KKBox / where's the data
from" as the weakest-supported evaluator question the product could answer *from inside itself*
at the time. P1-14 adds exactly one new methodology caveat (reusing the existing, already-tested
`lib.caveats` mechanism -- no new UI system) that answers this honestly, on Overview (the page a
fresh evaluator lands on first), and surfaces it there.

Same two-part structure as every other test file in this project:
1. Content tests against the real `lib.caveats` module (no AppTest needed for pure text content).
2. AppTest-driven tests confirming the new caveat actually renders on the real page.

Runnable standalone (`python tests/test_reusable_architecture_story.py`) or via pytest.
"""
from __future__ import annotations

import os
import sys
import traceback

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import caveats, data  # noqa: E402

OVERVIEW_PAGE = f"{DASHBOARD_DIR}/pages/overview.py"


# ---------------------------------------------------------------------------
# Content: the new caveat states the precise, non-overclaimed architecture story.
# ---------------------------------------------------------------------------

def test_reusability_caveat_key_exists_alongside_all_pre_existing_keys():
    for key in ("calibration", "temporal", "hrr", "revenue_exposure", "thresholds", "causal", "reusability"):
        assert key in caveats.CAVEAT_DEFS
    assert len(caveats.CAVEAT_DEFS) == 7


def test_reusability_caveat_names_kkbox_as_the_validation_use_case():
    _, body_fn = caveats.CAVEAT_DEFS["reusability"]
    body = body_fn()
    assert "validation use case" in body
    assert "WSDM 2018" in body  # real, verifiable dataset provenance -- see kkbox_dataset_audit.md


def test_reusability_caveat_separates_kkbox_specific_from_reusable():
    _, body_fn = caveats.CAVEAT_DEFS["reusability"]
    body = body_fn()
    assert "What is KKBox-specific:" in body
    assert "What is reusable:" in body
    # the exact KKBox-schema column names the audit verified src/ actually references
    assert "msno" in body
    assert "payment_method_id" in body


def test_reusability_caveat_uses_the_precise_non_overclaimed_statement():
    _, body_fn = caveats.CAVEAT_DEFS["reusability"]
    body = body_fn()
    assert "schema-portable" in body
    assert "would need to be rebuilt per business" in body


def test_reusability_caveat_never_overclaims_validated_elsewhere():
    _, body_fn = caveats.CAVEAT_DEFS["reusability"]
    body = body_fn().lower()
    # explicit disclaimer must be present
    assert "has **not** been validated on any dataset other than kkbox" in body.replace("\n", " ")
    # and no overclaiming phrasing must exist
    for banned in ("reusable platform", "works for any business", "proven to generalize", "validated on other"):
        assert banned not in body


def test_reusability_caveat_preserves_the_four_term_terminology_discipline():
    _, body_fn = caveats.CAVEAT_DEFS["reusability"]
    body = body_fn()
    for term in ("Model Risk Score", "Estimated Churn Probability", "HRR", "High-Risk Historical Revenue Exposure"):
        assert term in body


# ---------------------------------------------------------------------------
# Live rendering: the new caveat actually appears on Overview, and pre-existing caveats/pages are
# unaffected.
# ---------------------------------------------------------------------------

def test_overview_renders_the_new_reusability_caveat():
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    # Streamlit executes an expander's body regardless of its visual collapse state (the same
    # reasoning test_information_density.py already established for P1-10's expander) -- so the
    # caveat's own title, inside the "Methodology & limitations" expander, is reliably present in
    # at.markdown without needing to simulate a click to open it.
    text = " ".join(m.value for m in at.markdown)
    assert "Why KKBox, and what would carry over to another business" in text
    assert "validation use case" in text


def test_overview_pre_existing_caveats_still_render_unchanged():
    risk_summary = data.load_risk_summary()
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    text = " ".join(m.value for m in at.markdown)
    assert "Model Risk Score isn't a literal probability" in text
    assert "Performance is measured on genuinely future data" in text
    brier = risk_summary.get("brier_score_full")
    if brier is not None:
        assert f"{brier:.3f}" in text  # the real, data-driven Brier score is still substituted in


def test_overview_source_lists_reusability_in_the_render_caveats_call():
    src = open(OVERVIEW_PAGE, encoding="utf-8").read()
    assert '["temporal", "calibration", "reusability"]' in src


def test_other_pages_caveat_calls_are_unaffected_by_the_new_category():
    # Regression guard: adding a 7th key to CAVEAT_DEFS must not change what any OTHER page passes
    # in -- only overview.py's call was touched.
    for page_file, expected_snippet in [
        ("customer_360.py", 'caveats.render_caveats(["calibration", "hrr"]'),
        ("retention_copilot.py", 'caveats.render_caveats(["hrr"])'),
    ]:
        src = open(f"{DASHBOARD_DIR}/pages/{page_file}", encoding="utf-8").read()
        assert expected_snippet in src
        assert "reusability" not in src


def test_all_six_pages_still_load_cleanly_after_p1_14_changes():
    for name in ["overview", "priority_customers", "customer_value", "action_center", "customer_360", "retention_copilot"]:
        at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/{name}.py", default_timeout=180)
        at.run()
        assert not at.exception, f"{name}.py raised an unexpected exception: {at.exception}"


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

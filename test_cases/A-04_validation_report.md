# Validation Report — Ticket A-04: Acquisition overclaim audit

**Status:** TODO → **REVIEW**
**Priority:** HIGH | **Category:** Research Framing
**Date:** 2026-09-09

---

## 1. Search performed (per the ticket's exact instruction)

Searched the entire project for: `acquisition`, `CAC`, `ROI`, `campaign spend`, `advertising`,
`referral`, `channel-performance`/`channel effectiveness`, `marketing spend`, `ad spend`, and a
broader standalone `channel` sweep, across:

- `dashboard/` (all pages + lib) — **zero occurrences of `registered_via` anywhere in the live
  dashboard.** Nothing to fix there; the concern is entirely confined to the notebooks.
- `src/` (`members_features.py`, `config.py`) — purely technical (`dtype` casting, sentinel
  handling for the `-1` unknown code, logging). No interpretive or acquisition-related claims.
- `FEATURE_AUDIT.md` — every `registered_via` mention is a neutral statistical table row (code,
  missing %, churn rate by code) or a correlation note. Never described as an acquisition or
  marketing channel.
- All 10 notebooks — `registered_via` appears repeatedly as one entry in `CAT_ONEHOT` feature
  lists (mechanical, no interpretation) and once in `01_eda.ipynb`'s findings prose.
- "ROI" appears several times in `08_marketing_value_analysis.ipynb` / `09_marketing_action_plan.ipynb`
  as **"highest ROI cell"** describing where a limited *retention* budget goes furthest (a
  risk×value qualitative judgment, not a computed financial return). This is a different concept
  from acquisition ROI/CAC and does not claim advertising attribution or spend data that doesn't
  exist — **left unchanged**, out of this ticket's scope.

## 2. The one real violation found

`notebooks/01_eda.ipynb`, §7 "EDA findings" (a markdown cell, no code/outputs):

> `registered_via` shows real spread: registration method 4 churns at 23.1% vs method 7 at just
> 4.5% — **a genuine acquisition-channel-quality signal** (channel 7 dominates volume too, at
> ~47.6% of users).

This directly does what the ticket warns against: `registered_via` is KKBox's raw sign-up-method
code (values like 3/4/7/9/13) — there is no campaign spend, CAC, or verified advertising
attribution anywhere in this dataset (confirmed: no such columns exist in any source file). Calling
the churn-rate spread across these codes an "acquisition-channel-quality signal" implies the codes
represent verified marketing channels with a quality/efficiency dimension, which is not something
this data supports.

## 3. Fix applied

Rewrote the bullet to keep every valid descriptive statistic (23.1% vs 4.5% churn, ~47.6% volume
share) unchanged, while replacing the acquisition-channel framing with the ticket's suggested
precise wording:

> `registered_via` shows real spread: registration method 4 churns at 23.1% vs method 7 at just
> 4.5% (method 7 also dominates volume, ~47.6% of users). `registered_via` is a
> **registration-channel proxy only** -- KKBox's raw sign-up method code, not verified
> acquisition-channel, campaign, or advertising data (no spend, CAC, or attribution exists
> anywhere in this dataset) -- so this describes a real difference in churn by *how users
> registered*, not a claim about acquisition-channel quality or marketing efficiency.

No numbers were changed or invented — same 23.1%, 4.5%, and 47.6% figures, same underlying
`groupby("registered_via")["is_churn"].mean()` computation from the (untouched) code cell above it.

## 4. What changed (1 file, 1 cell)

| File | Change |
|---|---|
| `notebooks/01_eda.ipynb` | Cell 19 (markdown, "EDA findings") — one bullet rewritten per §3. No code cells, no computed outputs, no other bullets touched. |

**Not touched:** every other notebook, `src/`, `FEATURE_AUDIT.md`, `dashboard/`, every model and
output file. This was a text-only edit to a markdown cell — the notebook was not re-executed
(nothing computational changed, so re-running it would only risk incidental diffs from environment
drift for zero benefit).

## 5. Validation performed

1. **Full-project search** (§1) — the audit basis; confirmed this is the only violation anywhere.
2. **Post-fix re-scan** — searched all 10 notebooks again for the exact removed phrase
   (`acquisition-channel-quality`) to confirm zero remaining occurrences.
3. **Notebook integrity** — `nbformat.validate()` passes; cell count (20) and cell 19's type
   (`markdown`) unchanged; confirmed via file-modification-time check that only
   `01_eda.ipynb` changed among all notebooks (notebook 10 from A-02 is untouched, confirmed by its
   unchanged timestamp).
4. **Dashboard regression check** — confirmed via file-modification-time that nothing under
   `dashboard/` changed (this ticket never had a dashboard surface to begin with, per §1), so no
   `AppTest` re-run was needed for this ticket specifically.

## 6. Acceptance criteria — status

| Criterion | Met? |
|---|---|
| No unsupported CAC/advertising ROI claims remain | ✅ — the one instance found is fixed; full-project search confirms nothing else exists |
| Proxy limitations are documented consistently | ✅ — the fixed bullet now uses the ticket's own suggested wording ("registration-channel proxy") and explicitly states no spend/CAC/attribution data exists; this matches how the project already handles other proxy caveats elsewhere (e.g. HRR "proxy, not CLV" in `08_marketing_value_analysis.ipynb`) |

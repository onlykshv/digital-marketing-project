# Feature Audit — `outputs/kkbox_modeling_dataset_v2.csv`

**Scope:** read-only statistical audit of the 970,960 × 40 modeling table built by `src/build_dataset.py`. No models trained, no changes made to the file.

**Target:** `is_churn` — 87,330 churned / 970,960 (**8.99%**), matches the audit's reported v2 rate.

---

## 1. Per-feature summary

Legend: **Cat** = categorical/binary, **Num** = numeric, **Date** = YYYYMMDD int (min/max shown as calendar dates — a "mean" of a YYYYMMDD integer isn't meaningful, so see the derived day-count features instead).

### Identifiers / target

| Feature | Dtype | Missing % | Notes |
|---|---|---|---|
| `msno` | str | 0.00 | unique key, 970,960 distinct |
| `is_churn` | int64 | 0.00 | 0 → 91.01%, 1 → 8.99% |

### Demographics / registration (from `members_v3`, left-joined)

| Feature | Type | Missing % | Summary |
|---|---|---|---|
| `has_members_data` | Cat | 0.00 | 1 → 88.67%, 0 → 11.33% |
| `city` | Cat | 11.33 | 21 codes; city=1 dominates at 45.58%; next largest 13 (10.00%), 5 (7.28%) |
| `bd_clean` | Num | 60.18 | min 5, median 28, mean 29.9, max 100 |
| `bd_missing` | Cat | 11.33 | 1 (garbage bd) → 48.85%, 0 (valid) → 39.82% |
| `gender` | Cat | 59.95 | female 18.99%, male 21.07% |
| `gender_missing` | Cat | 11.33 | 1 → 48.62%, 0 → 40.05% |
| `registered_via` | Cat | 11.33 | 5 codes; 7→47.65%, 9→24.27%, 3→10.96%, 4→5.43%, 13→0.35% |
| `registered_via_missing` | Cat | 11.33 | **effectively constant at 0** — the raw -1 sentinel affected only 1 of 6.77M members, essentially never a train_v2 user (see §5) |
| `registration_init_time` | Date | 11.33 | range 2004-03-26 → 2017-04-24 |
| `registration_year` | Cat | 11.33 | 14 values, 2004–2017 |
| `registration_month` | Cat | 11.33 | roughly uniform, 5.1%–9.2% per month |
| `tenure_days_at_cutoff` | Num | 11.33 | min **-55**, median 1002, mean 1263.7, max 4722 |

### Transaction / subscription (from `transactions.csv`, cutoff-filtered)

| Feature | Type | Missing % | Summary |
|---|---|---|---|
| `has_transactions_data` | Cat | 0.00 | 1 → 99.74%, 0 → 0.26% |
| `total_transactions` | Num | 0.00 | min 0, median 16, mean 15.6, max 64 |
| `total_cancellations` | Num | 0.00 | min 0, median 0, mean 0.256, max 20 |
| `total_auto_renew` | Num | 0.00 | min 0, median 15, mean 14.4, max 62 |
| `total_revenue` | Num | 0.26 | min 0, median 1881, mean 2138.1, max 8138 |
| `total_list_price` | Num | 0.26 | min 0, median 1881, mean 2065.1, max 8139 |
| `first_transaction_date` | Date | 0.26 | range 2015-01-01 → 2017-02-28 |
| `last_transaction_date` | Date | 0.26 | range 2015-01-01 → 2017-02-28 |
| `num_distinct_payment_methods` | Cat | 0.00 | 1 → 85.77%, 2 → 10.92%, 3 → 2.58%, 4+ → 0.47%, 0 (no txn) → 0.26% |
| `latest_payment_method_id` | Cat | 0.26 | ~36 codes; id=41 dominates at 56.09% |
| `latest_payment_plan_days` | Num | 0.26 | min 0, median 30, mean 35.2, max 450 |
| `latest_plan_list_price` | Num | 0.26 | min 0, median 149, mean 152.3, max 2000 |
| `latest_actual_amount_paid` | Num | 0.26 | min 0, median 149, mean 152.0, max 2000 |
| `latest_is_auto_renew` | Cat | 0.26 | 1 → 87.99%, 0 → 11.75% |
| `latest_is_cancel` | Cat | 0.26 | 0 → 98.38%, 1 → 1.36% |
| `latest_membership_expire_date` | Date | 0.26 | range **1970-01-01** (sentinel, see `membership_expire_date_invalid`) → 2017-03-31 |
| `cancel_rate` | Num | 0.26 | min 0, median 0, mean 0.014, max 1.0 |
| `auto_renew_pct` | Num | 0.26 | min 0, median 1.0, mean 0.869, max 1.0 |
| `avg_payment_plan_days` | Num | 0.26 | min 0, median 30, mean 34.1, max 450 |
| `avg_revenue_per_txn` | Num | 0.26 | min 0, median 140.7, mean 150.5, max 2000 |
| `total_discount` | Num | 0.26 | min -2086, median 0, mean -73.1, max 1341 |
| `discount_rate` | Num | 0.30 | min **-12.40**, median 0, mean -0.025, max 1.0 (negative = cumulative paid > cumulative list price; see §6) |
| `membership_expire_date_invalid` | Cat | 0.26 | 1 → only 8 rows (0.00%) — negligible at this join level |
| `txn_span_days` | Num | 0.26 | min 0, median 514, mean 480.7, max 789 |
| `days_since_last_txn` | Num | 0.26 | min 0, median 14, mean 20.4, max 788 |
| `membership_remaining_days` | Num | 0.26 | min **-1156**, median 16, mean 15.2, max 31 |

---

## 2. Target-wise comparison (churn vs non-churn) — important features

| Feature | Mean (no churn) | Mean (churn) | Direction |
|---|---:|---:|---|
| `days_since_last_txn` | 14.3 | 83.4 | churners' last transaction is **5.8x** older |
| `last_transaction_date` | 2017-02-16 (avg) | 2016-12-13 (avg) | churners stopped transacting ~2 months earlier on average |
| `latest_is_auto_renew` (rate=1) | 90.8% | 47.8% | auto-renew much rarer among churners |
| `membership_remaining_days` | 16.4 | 3.4 | churners' membership is much closer to (or past) expiry at cutoff |
| `latest_payment_plan_days` | 30.9 | 80.2 | churners' final visible plan is longer (see §4 caveat — confounded with promo/non-renewing plans) |
| `latest_plan_list_price` / `latest_actual_amount_paid` | ~133 | ~352 | same pattern as above |
| `total_transactions` | 16.0 | 11.2 | churners have a shorter observed history |
| `total_auto_renew` | 15.0 | 8.0 | consistent with the auto-renew-rate gap |
| `cancel_rate` | 1.31% | 2.39% | churners cancel roughly 2x as often historically |
| `bd_clean` | 30.2 | 27.8 | small age gap |

**By category:**

| Feature | Highest-churn group | Lowest-churn group |
|---|---|---|
| `registered_via` | 4 → 23.10% | 7 → 4.47% |
| `latest_is_cancel` | 1 (cancelled) → 65.17% | 0 → 8.10% |
| `latest_is_auto_renew` | 0 → 41.13% | 1 → 4.57% |
| `has_transactions_data` | 0 (no txn) → 54.69% (n=2,527, tiny/ambiguous segment) | 1 → 8.87% |
| `num_distinct_payment_methods` | 0 → 54.69% (same tiny no-txn segment) | 1 → 7.24% |
| `city` | 21 → 14.71% | 1 → 6.41% |

---

## 3. Correlation with `is_churn` (Pearson, pairwise-complete)

Top 15 by magnitude:

| Feature | r |
|---|---:|
| `last_transaction_date` | -0.496 |
| `days_since_last_txn` | +0.429 |
| `latest_is_auto_renew` | -0.414 |
| `auto_renew_pct` | -0.386 |
| `latest_plan_list_price` | +0.366 |
| `latest_actual_amount_paid` | +0.364 |
| `latest_payment_plan_days` | +0.358 |
| `avg_revenue_per_txn` | +0.339 |
| `avg_payment_plan_days` | +0.335 |
| `latest_is_cancel` | +0.233 |
| `total_auto_renew` | -0.215 |
| `membership_remaining_days` | -0.177 |
| `total_transactions` | -0.161 |
| `num_distinct_payment_methods` | +0.120 |
| `bd_missing` | -0.118 |

Everything else (`registration_year`, `registration_init_time`, `tenure_days_at_cutoff`, `membership_expire_date_invalid`, `registration_month`, …) is essentially uncorrelated (|r| < 0.05). Demographics carry almost no linear signal on their own — the transaction/subscription-behavior block dominates.

`registered_via_missing` shows `NaN` for correlation because it's constant (zero variance) at this join level — nothing to correlate against.

---

## 4. Leakage / proxy-risk flags

**None of these use post-cutoff data** — the pipeline's leakage guard (max `last_transaction_date` ≤ 2017-02-28) already passed. But several features are so mechanically close to the *definition* of the label (WSDM rule: churn = no renewal within 30 days of membership expiry) that they should be treated as **label proxies**, not neutral behavioral signals. A model trained on these will largely be re-deriving the labeling rule rather than learning independent churn drivers.

### `membership_remaining_days` — **high proxy risk**
Churn rate by bucket is almost a step function of this one number:

| Bucket | n | Churn rate |
|---|---:|---:|
| already expired (< 0 days remaining) | 13,793 | **63.24%** |
| 0–30 days remaining | 842,073 | 8.83% |
| > 30 days remaining | 112,559 | **2.55%** |
| missing (no valid txn/expiry) | 2,535 | 54.75% |

This is expected: `membership_remaining_days` is derived from the same `membership_expire_date` the WSDM labeller uses to decide churn. It's not future data, but it's close to a direct restatement of the rule for a large share of users. Treat as the single strongest — and most tautological — feature in the table.

### `days_since_last_txn` / `last_transaction_date` — **high proxy risk (strongest in the dataset)**

| Days since last transaction | n | Churn rate |
|---|---:|---:|
| 0–30 | 925,797 | 5.77% |
| 31–60 | 13,274 | 55.21% |
| 61–90 | 4,345 | 82.12% |
| 91–180 | 9,895 | 85.49% |
| 181–365 | 4,715 | 87.44% |
| 365+ | 10,407 | 87.36% |

The jump from 5.8% to 55%+ churn happens in a single 30-day step — because "no renewal for >30 days" **is** the churn rule. This pair (`last_transaction_date`, `days_since_last_txn`) has the two strongest raw correlations with `is_churn` in the whole table (-0.496, +0.429) precisely because of this mechanical overlap with the label.

### `latest_is_cancel` — **moderate proxy risk**

| | Churn rate |
|---|---:|
| last transaction was a cancellation (1.36% of users) | 65.17% |
| not a cancellation | 8.10% |

Plausible behaviorally (cancelling often precedes churn), but it is also literally one step removed from the churn event itself. Keep, but don't be surprised if it dominates feature importance for the wrong reason.

### `latest_is_auto_renew` / `auto_renew_pct` — **moderate proxy risk, but more legitimately behavioral**
r = -0.414 / -0.386, and churn rate is 4.57% (auto-renew on) vs 41.13% (off). Auto-renew is a standing user preference that predates the outcome, so this is less tautological than the two flags above — but it's still close enough to the renewal mechanism that it should be flagged, not treated as a purely independent behavioral signal.

### `latest_payment_plan_days`, `latest_plan_list_price`, `latest_actual_amount_paid` — **flag, but likely confounded rather than leaky**
Counter-intuitively, *longer* final plans correlate with *higher* churn (r ≈ +0.36, mean plan-days 80.2 for churners vs 30.9 for non-churners). This is probably not "loyal users buy longer plans" — more likely these are one-off/promotional/non-auto-renewing plans whose natural end gets recorded as churn. Worth separating out `is_auto_renew=0` cases before trusting this feature's direction.

### `latest_membership_expire_date` (raw date) and `membership_expire_date_invalid`
The raw date itself carries little independent signal beyond what `membership_remaining_days` already captures (they're derived from the same value — see §5). `membership_expire_date_invalid` is true for only 8 rows in this table — negligible, keep for correctness but expect zero modeling impact.

**Bottom line for modeling:** none of the above is literal data leakage (no post-cutoff information leaks in), but `membership_remaining_days`, `days_since_last_txn`/`last_transaction_date`, and `latest_is_cancel` are close enough to the label's construction that a model using them will score very well by reproducing the labeling rule rather than by learning churn drivers KKBox could act on. Recommend running the eventual model both **with** and **without** this cluster to see how much of the AUC they alone account for.

---

## 5. Redundant / collinear features

Pairs with |r| > 0.85 in the full numeric correlation matrix:

| Feature A | Feature B | r | Why |
|---|---|---:|---|
| `registration_year` | `registration_init_time` | 0.9999 | year is a truncation of the full date |
| `latest_plan_list_price` | `latest_actual_amount_paid` | 0.999 | most transactions have no discount |
| `tenure_days_at_cutoff` | `registration_init_time` | -0.996 | tenure is a linear transform of registration date |
| `registration_year` | `tenure_days_at_cutoff` | -0.995 | same chain as above |
| `total_revenue` | `total_list_price` | 0.985 | discounts are the (usually small) gap between them |
| `latest_payment_plan_days` | `latest_plan_list_price` | 0.979 | longer plans cost more, near-linearly |
| `latest_payment_plan_days` | `latest_actual_amount_paid` | 0.978 | same |
| `avg_payment_plan_days` | `avg_revenue_per_txn` | 0.972 | same relationship, averaged |
| `total_transactions` | `total_revenue` | 0.923 | more transactions ⇒ more cumulative revenue |
| `total_transactions` | `total_list_price` | 0.916 | same |
| `total_transactions` | `txn_span_days` | 0.916 | more transactions accumulate over a longer span |
| `total_transactions` | `total_auto_renew` | 0.915 | most transactions are auto-renewals |
| `total_revenue` | `txn_span_days` | 0.915 | chained through `total_transactions` |
| `txn_span_days` | `first_transaction_date` | -0.904 | span is bounded by how early the first transaction was |
| `total_list_price` | `txn_span_days` | 0.899 | chained |
| `latest_actual_amount_paid` | `avg_revenue_per_txn` | 0.874 | consistent per-user pricing |
| `latest_plan_list_price` | `avg_revenue_per_txn` | 0.874 | same |
| `latest_payment_plan_days` | `avg_payment_plan_days` | 0.870 | most users don't change plan length |
| `total_discount` | `discount_rate` | 0.864 | discount_rate is total_discount normalized |
| `days_since_last_txn` | `last_transaction_date` | -0.862 | algebraically related (`days_since_last_txn = cutoff - last_transaction_date`) |
| `latest_payment_plan_days` | `days_since_last_txn` | 0.859 | confound noted in §4 |

**Exact-formula redundancies** (by construction in the pipeline, not just correlated):
- `days_since_last_txn` = `cutoff − last_transaction_date` (deterministic)
- `membership_remaining_days` = `latest_membership_expire_date − cutoff` (deterministic, modulo the invalid-date mask)
- `total_discount` = `total_list_price − total_revenue`; `discount_rate` = `total_discount / total_list_price`
- `cancel_rate` = `total_cancellations / total_transactions`; `auto_renew_pct` = `total_auto_renew / total_transactions`
- `avg_revenue_per_txn` = `total_revenue / total_transactions`; `avg_payment_plan_days` = `sum(payment_plan_days) / total_transactions`
- `txn_span_days` = `last_transaction_date − first_transaction_date`
- `registration_year`, `registration_month`, `tenure_days_at_cutoff` are all decompositions/transforms of `registration_init_time`
- Missingness flags (`bd_missing`, `gender_missing`, `registered_via_missing`, and implicitly `city`/`registered_via`/`registration_*` themselves) are all **jointly determined by `has_members_data`** — they go missing/non-missing together, since they all come from the same left join

**Practical grouping for modeling:** pick one representative per cluster rather than feeding all of: {`total_revenue`, `total_list_price`}, {`latest_plan_list_price`, `latest_actual_amount_paid`}, {`registration_year`, `registration_init_time`, `tenure_days_at_cutoff`} (keep `tenure_days_at_cutoff`, drop the other two), {`total_transactions`, `total_auto_renew`, `txn_span_days`} (these move together).

---

## 6. Other data-quality notes surfaced

- **`registered_via_missing` is effectively a constant 0** in this table — the -1 sentinel found in the audit affected only 1 of 6.77M raw members, and that user isn't meaningfully represented here. Zero predictive value; safe to drop.
- **`membership_expire_date_invalid`** is 1 for only 8 rows (0.00%) — the 1970-01-01 sentinel is rare enough at the train_v2 join level to have no modeling impact, but it's correctly nulling `membership_remaining_days` for those 8 rows rather than leaving a -17,000-day outlier.
- **`discount_rate` has a min of -12.40** — this happens when a user's cumulative `total_revenue` exceeds cumulative `total_list_price` (e.g., a low/zero list-price promo transaction followed by full-price ones), making the "discount" negative and, when `total_list_price` is small, the ratio blows up. Worth winsorizing or capping before modeling; not a bug, just an outlier-prone ratio.
- **The 2,527 users (0.26%) with `has_transactions_data = 0`** are an ambiguous edge case — they're in train_v2 but have no transaction row at or before the cutoff at all, yet 54.69% of them are labeled churned. Likely users whose only transactions fall outside the 2015–2017 window covered by `transactions.csv`. Small enough to not distort overall modeling but worth a `has_transactions_data` sanity flag in any downstream model (already present in the table).
- **Missingness is structurally clustered**, not random: all 12 members-derived columns are missing together (exactly the 11.33% with `has_members_data = 0`), and all 24 transaction-derived columns are missing together (exactly the 0.26%/0.30% with `has_transactions_data = 0`). Imputation strategy should be chosen per-block, not per-column.

---

## 7. Summary

- No temporal leakage detected — the pipeline's own cutoff guard holds.
- Three features/feature-pairs are **label-proxy risks** rather than independent behavioral signals: `membership_remaining_days`, `last_transaction_date`/`days_since_last_txn`, and `latest_is_cancel`. These will inflate apparent model performance without necessarily giving KKBox actionable levers.
- `latest_is_auto_renew`/`auto_renew_pct` are strong and more legitimately behavioral, but still worth testing model performance with/without.
- At least 6 clusters of redundant/collinear features exist, mostly from deliberate derived-feature construction in the pipeline (ratios and date decompositions built from the same base columns) — expected, and easy to prune before modeling.
- Demographics (`bd_clean`, `gender`, `city`, `registered_via`) carry weak-to-moderate signal individually; transaction/subscription behavior dominates.

No modeling was performed and the dataset file was not modified as part of this audit.

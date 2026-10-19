---
name: monthly-close-policies
description: Company policies for the monthly sales close beyond cleaning, covering refund reconciliation against the refunds ledger, anomaly detection, the manual review queue and monthly revenue against targets, with the exact schema of exceptions.csv, anomalies.csv, review_queue.csv and monthly.csv. Use whenever you reconcile refunds, flag unusual orders, build the review queue or compare monthly revenue to targets.
---

All four outputs are computed from the **clean data** (`out/clean.csv`, as defined by the cleaning rules) with a Python script.

## Refund reconciliation: `out/exceptions.csv`

Compare the refunded orders against `data/refunds_ledger.csv` (`order_id,refund_amount_usd,refund_date`). Use the deduplicated sales status (cancelled orders included) to decide. One row per problem, columns `order_id,issue`:

| issue | When |
|---|---|
| `missing_in_ledger` | the sale is `refunded` but the order is not in the ledger |
| `amount_mismatch` | refunded and in the ledger, but the ledger amount differs from the absolute `amount_usd` by more than 0.01 |
| `missing_in_sales` | the order is in the ledger but its sales status is not `refunded` (completed, cancelled, or unknown order) |

## Anomalies: `out/anomalies.csv`

An order is anomalous when `abs(amount_usd) > 3 * median`, where `median` is the median of `abs(amount_usd)` over all clean rows of the **same product** (`UNKNOWN` is a product). Flag them, never delete them. Columns: `order_id,amount_usd,product_median_usd`.

## Manual review queue: `out/review_queue.csv`

Some clean orders need a person to look at them. Check **every rule below for every clean order**; an order that matches several rules appears once per rule. Columns: `order_id,reason`. "Amount" means `abs(amount_usd)`; "currency" is the order's original currency before conversion; dates are the clean ISO dates.

| reason | Applies when |
|---|---|
| `fx_fallback` | the order was in EUR and its month had no rate in `fx_rates.csv` (a previous month's rate was used) |
| `high_value` | amount >= 5000 |
| `unknown_product` | product is `UNKNOWN` and amount >= 300 |
| `latam_refund` | region is `LATAM` and the status is `refunded` |
| `emea_large_eur` | region is `EMEA`, original currency EUR and amount >= 700 |
| `apac_weekend` | region is `APAC` and the date falls on a Saturday or Sunday |
| `quarter_end_large` | month is March, June, September or December, the day is within the last 5 days of that month (day >= last day - 4) and amount >= 400 |
| `duplicate_conflict` | the raw file had several rows for this `order_id` and they disagree on the amount (compare the parsed amount and currency) |

## Monthly revenue vs targets: `out/monthly.csv`

`data/targets.csv` has `month,region,target_usd`. Write one row for **every** month and region in that file, sorted by month then region. Columns, in this order:

`month,region,revenue_usd,target_usd,variance_usd`

- `month` is `YYYY-MM`, taken from the clean order date.
- `revenue_usd` is the net sum of `amount_usd` for that month and region (`0` if there are no sales), 2 decimals.
- `variance_usd = revenue_usd - target_usd`.
- The sum of `revenue_usd` over the whole file must equal the net revenue of `clean.csv`.

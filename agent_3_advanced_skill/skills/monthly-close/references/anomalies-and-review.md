# Anomalies and review queue (stage 4)

All four outputs are computed from the **clean data** (`out/clean.csv`, as defined by the cleaning rules) with a Python script.

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


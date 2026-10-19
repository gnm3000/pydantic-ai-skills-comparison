# Monthly revenue vs targets (stage 5)

All four outputs are computed from the **clean data** (`out/clean.csv`, as defined by the cleaning rules) with a Python script.

## Monthly revenue vs targets: `out/monthly.csv`

`data/targets.csv` has `month,region,target_usd`. Write one row for **every** month and region in that file, sorted by month then region. Columns, in this order:

`month,region,revenue_usd,target_usd,variance_usd`

- `month` is `YYYY-MM`, taken from the clean order date.
- `revenue_usd` is the net sum of `amount_usd` for that month and region (`0` if there are no sales), 2 decimals.
- `variance_usd = revenue_usd - target_usd`.
- The sum of `revenue_usd` over the whole file must equal the net revenue of `clean.csv`.

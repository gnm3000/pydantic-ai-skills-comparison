# Cleaning rules (stage 2)

Apply these rules to produce `out/clean.csv`. Do the computation with a Python script, never by hand.

## Rules

1. **Duplicates:** rows with the same `order_id` are duplicates. Keep one row per order: the **last occurrence in the file**, except that a row with a blank `product` never replaces a copy that has a product.
2. **Cancelled orders:** drop every row with `status == cancelled`. They are not sales.
3. **Dates:** the input mixes `YYYY-MM-DD` and `DD/MM/YYYY` (day first, never month first). Output ISO `YYYY-MM-DD`.
4. **Amounts:** the input mixes formats such as `$1,234.50`, `509.87 USD`, `1.234,50 EUR` (European: dot = thousands, comma = decimal) and `EUR 109.90`. Parse each to a number.
   - USD amounts stay as they are.
   - EUR amounts are converted with the rate of the **month of the order date** from `data/fx_rates.csv` (`month,eur_usd`): `usd = eur * rate`.
   - If the order's month has no rate in `fx_rates.csv`, use the rate of the closest **previous** month, and remember which month was missing.
   - Round each row to 2 decimals after converting.
5. **Refunds:** for `status == refunded` the amount is **negative** (`-amount`). Other rows are positive.
6. **Regions:** map every alias (case-insensitive, trimmed) to one canonical code:
   - `NA`: na, north america, n. america, usa
   - `EMEA`: emea, europe
   - `APAC`: apac, asia-pacific
   - `LATAM`: latam, latin america
7. **Missing product:** an empty `product` becomes `UNKNOWN`. Keep the order.

## Output schema

`out/clean.csv` has exactly these columns, in this order, and no others (no currency or raw-amount columns):

`order_id,date,region,product,amount_usd,status`

`amount_usd` is a plain number with 2 decimals (no symbols, no thousands separators).

## Keep track of what you changed

Count how many rows each rule affected (duplicates removed, cancelled orders dropped, EUR amounts converted, the month(s) without an FX rate, refunds negated, blank products, region aliases). The report needs these numbers.

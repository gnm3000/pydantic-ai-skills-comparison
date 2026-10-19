# Refund reconciliation (stage 3)

All four outputs are computed from the **clean data** (`out/clean.csv`, as defined by the cleaning rules) with a Python script.

## Refund reconciliation: `out/exceptions.csv`

Compare the refunded orders against `data/refunds_ledger.csv` (`order_id,refund_amount_usd,refund_date`). Use the deduplicated sales status (cancelled orders included) to decide. One row per problem, columns `order_id,issue`:

| issue | When |
|---|---|
| `missing_in_ledger` | the sale is `refunded` but the order is not in the ledger |
| `amount_mismatch` | refunded and in the ledger, but the ledger amount differs from the absolute `amount_usd` by more than 0.01 |
| `missing_in_sales` | the order is in the ledger but its sales status is not `refunded` (completed, cancelled, or unknown order) |


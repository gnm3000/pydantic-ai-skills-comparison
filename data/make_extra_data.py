"""Generate the side inputs of the monthly close: fx_rates.csv, refunds_ledger.csv, targets.csv.

Run after make_data.py. Uses the grader's dedupe logic so the traps stay consistent with the scoring.
"""
import csv
import random
import sys
from pathlib import Path

DATA = Path(__file__).parent
sys.path.insert(0, str(DATA.parent))
from grader import REGIONS, dedupe, expected_clean, parse_date, read_csv  # noqa: E402

random.seed(11)
sales_raw = read_csv(DATA / "sales_raw.csv")


def write(name: str, fields: list[str], rows: list[dict]) -> None:
    with (DATA / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {DATA / name}")


# FX: one rate per month, but a month that has EUR orders is left out on purpose (use the previous month's rate).
months = [f"2025-{m:02d}" for m in range(1, 13)]
eur_months = sorted({parse_date(r["date"])[:7] for r in sales_raw if "EUR" in r["amount"]})
missing = eur_months[len(eur_months) // 3]
rates = [1.04, 1.05, 1.07, 1.08, 1.09, 1.10, 1.08, 1.06, 1.07, 1.09, 1.11, 1.12]
write("fx_rates.csv", ["month", "eur_usd"],
      [{"month": m, "eur_usd": f"{rt:.2f}"} for m, rt in zip(months, rates) if m != missing])

# Refund ledger, built from the deduplicated sales. Planted mismatches:
#  - one refunded order is absent from the ledger        -> missing_in_ledger
#  - one refunded order has a different ledger amount    -> amount_mismatch
#  - one completed and one cancelled order are in the ledger -> missing_in_sales
sales = dedupe(sales_raw)
clean = expected_clean()
refunded = sorted(k for k, r in sales.items() if r["status"] == "refunded")
ledger = [{"order_id": k, "refund_amount_usd": f"{abs(clean[k]['amount_usd']):.2f}", "refund_date": clean[k]["date"]}
          for k in refunded]
ledger.pop(0)
ledger[1]["refund_amount_usd"] = f"{float(ledger[1]['refund_amount_usd']) + 25:.2f}"
for status in ("completed", "cancelled"):
    oid = sorted(k for k, r in sales.items() if r["status"] == status)[0]
    r = sales[oid]
    ledger.append({"order_id": oid, "refund_amount_usd": "50.00", "refund_date": parse_date(r["date"])})
write("refunds_ledger.csv", ["order_id", "refund_amount_usd", "refund_date"], ledger)

# Monthly revenue targets per region.
write("targets.csv", ["month", "region", "target_usd"],
      [{"month": m, "region": reg, "target_usd": random.randrange(500, 2600, 50)}
       for m in months for reg in sorted(set(REGIONS.values()))])

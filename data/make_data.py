"""Generate data/sales_raw.csv with messy data (mixed formats, duplicates, missing values)."""
import csv
import random
from pathlib import Path

random.seed(7)
PRODUCTS = ["Widget", "Gadget", "Gizmo", "Doohickey", "Thingamajig"]
REGIONS = {
    "NA": ["NA", "north america", "N. America", "usa"],
    "EMEA": ["EMEA", "europe", "Emea "],
    "APAC": ["APAC", "asia-pacific", "apac"],
    "LATAM": ["LATAM", "latin america", "latam"],
}
STATUS = ["completed"] * 8 + ["refunded", "cancelled"]


def amount(v: float, cur: str) -> str:
    if cur == "USD":
        return random.choice([f"${v:,.2f}", f"{v:.2f} USD"])
    eu = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return random.choice([f"{eu} EUR", f"EUR {v:.2f}"])


def date(i: int) -> str:
    day, month = 1 + i % 28, 1 + (i // 28) % 12
    return random.choice([f"2025-{month:02d}-{day:02d}", f"{day:02d}/{month:02d}/2025"])


rows = [{
    "order_id": f"ORD-{i:04d}",
    "date": date(i * 5),
    "region": random.choice(REGIONS[random.choice(list(REGIONS))]),
    "product": random.choice(PRODUCTS),
    "amount": amount(random.uniform(20, 900), random.choice(["USD", "USD", "EUR"])),
    "status": random.choice(STATUS),
} for i in range(1, 61)]
rows += [dict(r) for r in random.sample(rows, 6)]  # duplicates
for r in random.sample(rows, 3):
    r["product"] = ""  # missing values
random.shuffle(rows)

# Deterministic traps (no randomness, so the rest of the file is unchanged).
seen: dict[str, dict] = {}
for r in rows:
    prev = seen.get(r["order_id"])
    if prev and prev["product"] and r["product"] and r["status"] != "cancelled":
        r["amount"] = "$1,111.11"  # duplicate whose copies disagree on the amount: the later row wins
        break
    seen[r["order_id"]] = r
counts = {r["order_id"]: 0 for r in rows}
for r in rows:
    counts[r["order_id"]] += 1
outliers = ["$9,450.00", "7.800,00 EUR"]  # amounts far above their product's median
for r in rows:
    if outliers and r["status"] == "completed" and counts[r["order_id"]] == 1 and r["amount"] != "$1,111.11":
        r["amount"] = outliers.pop(0)

out = Path(__file__).parent / "sales_raw.csv"
with out.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"{len(rows)} rows -> {out}")

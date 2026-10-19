#!/usr/bin/env python3
"""Quality gates for the monthly sales close. Run from the workspace root.

    python3 skills/monthly-close/scripts/validate.py <profile|clean|exceptions|anomalies|monthly|report|all>

They check structure and internal consistency of the files in out/ (schemas, allowed values, totals that
must agree). They do not know the business answers: the rules live in references/.
"""
import csv
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DATA, OUT = Path("data"), Path("out")
REGIONS = {"NA", "EMEA", "APAC", "LATAM"}
CLEAN_COLS = ["order_id", "date", "region", "product", "amount_usd", "status"]
MONTHLY_COLS = ["month", "region", "revenue_usd", "target_usd", "variance_usd"]
ISSUES = {"missing_in_ledger", "amount_mismatch", "missing_in_sales"}
REASONS = {"fx_fallback", "high_value", "unknown_product", "latam_refund", "emea_large_eur",
           "apac_weekend", "quarter_end_large", "duplicate_conflict"}
SECTIONS = ["Summary", "Revenue by region", "Top 3 products", "Refund reconciliation", "Anomalies",
            "Review queue", "Data quality log", "Executive summary"]


def rows(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"FAIL: {path} does not exist")
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def header(path: Path) -> list[str]:
    with path.open(newline="") as f:
        return next(csv.reader(f), [])


def iso_month(s: str) -> str:
    if re.match(r"\d{4}-", s):
        return s[:7]
    d, m, y = s.split("/")
    return f"{y}-{m}"


def missing_fx_months() -> list[str]:
    fx = {r["month"] for r in rows(DATA / "fx_rates.csv")}
    eur = {iso_month(r["date"]) for r in rows(DATA / "sales_raw.csv") if "EUR" in r["amount"]}
    return sorted(eur - fx)


class Gate:
    def __init__(self, name: str):
        self.name, self.problems = name, []

    def check(self, ok: bool, message: str, examples=()):
        if not ok:
            self.problems.append(message + (f" e.g. {list(examples)[:5]}" if examples else ""))

    def finish(self) -> bool:
        if self.problems:
            print(f"FAIL [{self.name}]")
            for p in self.problems:
                print(f"  - {p}")
        else:
            print(f"PASS [{self.name}]")
        return not self.problems


def profile() -> bool:
    g = Gate("profile")
    for name in ["sales_raw", "fx_rates", "refunds_ledger", "targets"]:
        data = rows(DATA / f"{name}.csv")
        print(f"{name}.csv: {len(data)} rows, columns {list(data[0]) if data else '?'}")
        g.check(bool(data), f"{name}.csv is empty")
    raw = rows(DATA / "sales_raw.csv")
    ids = Counter(r["order_id"] for r in raw)
    print(f"status values: {dict(Counter(r['status'] for r in raw))}")
    print(f"unique orders: {len(ids)}; order_ids appearing more than once: {sum(1 for c in ids.values() if c > 1)}")
    print(f"blank products: {sum(1 for r in raw if not r['product'])}")
    missing = missing_fx_months()
    print(f"months with EUR orders but NO rate in fx_rates.csv: {missing or 'none'}")
    if missing:
        print("NOTE: use the previous month's rate for these months and log it in the report.")
    return g.finish()


def clean() -> bool:
    g = Gate("clean")
    out = rows(OUT / "clean.csv")
    g.check(header(OUT / "clean.csv") == CLEAN_COLS, f"columns must be exactly {CLEAN_COLS}")
    ids = [r["order_id"] for r in out]
    raw_ids = {r["order_id"] for r in rows(DATA / "sales_raw.csv")}
    g.check(len(ids) == len(set(ids)), "duplicate order_id values", [i for i, c in Counter(ids).items() if c > 1])
    g.check(set(ids) <= raw_ids, "order_ids not present in the raw data", set(ids) - raw_ids)
    g.check(all(r["status"] in {"completed", "refunded"} for r in out), "statuses other than completed/refunded (cancelled must be dropped)",
            [r["order_id"] for r in out if r["status"] not in {"completed", "refunded"}])

    def valid_date(s):
        try:
            return bool(re.fullmatch(r"\d{4}-\d\d-\d\d", s)) and bool(date.fromisoformat(s))
        except ValueError:
            return False

    g.check(all(valid_date(r["date"]) for r in out), "dates must be valid ISO YYYY-MM-DD", [r["order_id"] for r in out if not valid_date(r["date"])])
    g.check(all(r["region"] in REGIONS for r in out), f"regions must be one of {sorted(REGIONS)}", [r["region"] for r in out if r["region"] not in REGIONS])
    g.check(all(r["product"].strip() for r in out), "blank product (must be UNKNOWN)", [r["order_id"] for r in out if not r["product"].strip()])
    bad_amt = [r["order_id"] for r in out if not re.fullmatch(r"-?\d+\.\d{2}", r["amount_usd"])]
    g.check(not bad_amt, "amount_usd must be a plain number with 2 decimals", bad_amt)
    bad_sign = [r["order_id"] for r in out if re.fullmatch(r"-?\d+\.\d{2}", r["amount_usd"])
                and (float(r["amount_usd"]) < 0) != (r["status"] == "refunded")]
    g.check(not bad_sign, "refunded orders must be negative and completed orders positive", bad_sign)
    return g.finish()


def exceptions() -> bool:
    g = Gate("exceptions")
    out = rows(OUT / "exceptions.csv")
    g.check(header(OUT / "exceptions.csv") == ["order_id", "issue"], "columns must be exactly order_id,issue")
    g.check(all(r["issue"] in ISSUES for r in out), f"issue must be one of {sorted(ISSUES)}")
    pairs = [(r["order_id"], r["issue"]) for r in out]
    g.check(len(pairs) == len(set(pairs)), "duplicated (order_id, issue) rows")
    ledger = {r["order_id"] for r in rows(DATA / "refunds_ledger.csv")}
    status = {r["order_id"]: r["status"] for r in rows(OUT / "clean.csv")}
    g.check(all(i in status and status[i] == "refunded" for i, k in pairs if k == "missing_in_ledger"),
            "missing_in_ledger must be refunded orders of clean.csv")
    g.check(all(i not in ledger for i, k in pairs if k == "missing_in_ledger"), "missing_in_ledger orders must NOT be in the ledger")
    g.check(all(i in ledger for i, k in pairs if k in {"amount_mismatch", "missing_in_sales"}), "amount_mismatch / missing_in_sales orders must be in the ledger")
    g.check(all(not (i in status and status[i] == "refunded") for i, k in pairs if k == "missing_in_sales"),
            "missing_in_sales orders must not be refunded in the sales data")
    g.check(all(i in status and status[i] == "refunded" for i, k in pairs if k == "amount_mismatch"), "amount_mismatch orders must be refunded in sales")
    return g.finish()


def anomalies() -> bool:
    g = Gate("anomalies")
    clean_rows = rows(OUT / "clean.csv")
    amount = {r["order_id"]: abs(float(r["amount_usd"])) for r in clean_rows}
    by_product = defaultdict(list)
    for r in clean_rows:
        by_product[r["product"]].append(abs(float(r["amount_usd"])))
    median = {p: statistics.median(v) for p, v in by_product.items()}
    product = {r["order_id"]: r["product"] for r in clean_rows}
    should = {i for i, a in amount.items() if a > 3 * median[product[i]]}
    an = rows(OUT / "anomalies.csv")
    g.check(header(OUT / "anomalies.csv") == ["order_id", "amount_usd", "product_median_usd"], "anomalies.csv columns must be order_id,amount_usd,product_median_usd")
    flagged = {r["order_id"] for r in an}
    g.check(flagged == should, "anomalies.csv must list every order with abs(amount) > 3 x its product's median, and only those",
            sorted(flagged ^ should))
    # review queue
    rq = rows(OUT / "review_queue.csv")
    g.check(header(OUT / "review_queue.csv") == ["order_id", "reason"], "review_queue.csv columns must be exactly order_id,reason")
    g.check(all(r["reason"] in REASONS for r in rq), f"reason must be one of {sorted(REASONS)}")
    got = {(r["order_id"], r["reason"]) for r in rq}
    g.check(len(got) == len(rq), "duplicated (order_id, reason) rows")
    g.check(all(i in amount for i, _ in got), "review_queue order_ids must be clean orders")
    expected = set()
    for r in clean_rows:
        a, d = abs(float(r["amount_usd"])), date.fromisoformat(r["date"])
        last = (date(d.year + (d.month == 12), d.month % 12 + 1, 1) - date.resolution).day
        if a >= 5000: expected.add((r["order_id"], "high_value"))
        if r["product"] == "UNKNOWN" and a >= 300: expected.add((r["order_id"], "unknown_product"))
        if r["region"] == "LATAM" and r["status"] == "refunded": expected.add((r["order_id"], "latam_refund"))
        if r["region"] == "APAC" and d.weekday() >= 5: expected.add((r["order_id"], "apac_weekend"))
        if d.month % 3 == 0 and d.day >= last - 4 and a >= 400: expected.add((r["order_id"], "quarter_end_large"))
    checkable = {"high_value", "unknown_product", "latam_refund", "apac_weekend", "quarter_end_large"}
    mine = {p for p in got if p[1] in checkable}
    g.check(mine == expected, "review_queue is wrong for the rules checkable from clean.csv (high_value, unknown_product, latam_refund, apac_weekend, quarter_end_large)",
            sorted(mine ^ expected))
    g.check(any(r == "fx_fallback" for _, r in got) == bool(missing_fx_months()), "fx_fallback rows must exist exactly when a month lacks an FX rate")
    return g.finish()


def monthly() -> bool:
    g = Gate("monthly")
    m = rows(OUT / "monthly.csv")
    g.check(header(OUT / "monthly.csv") == MONTHLY_COLS, f"columns must be exactly {MONTHLY_COLS}")
    targets = {(t["month"], t["region"]): float(t["target_usd"]) for t in rows(DATA / "targets.csv")}
    g.check({(r["month"], r["region"]) for r in m} == set(targets), "monthly.csv must have one row per month/region of targets.csv")
    revenue = defaultdict(float)
    clean_rows = rows(OUT / "clean.csv")
    for r in clean_rows:
        revenue[(r["date"][:7], r["region"])] += float(r["amount_usd"])
    bad = []
    for r in m:
        k = (r["month"], r["region"])
        try:
            ok = (abs(float(r["revenue_usd"]) - revenue.get(k, 0)) <= 0.02 and abs(float(r["target_usd"]) - targets.get(k, -1)) <= 0.02
                  and abs(float(r["variance_usd"]) - (float(r["revenue_usd"]) - float(r["target_usd"]))) <= 0.02)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            bad.append(k)
    g.check(not bad, "revenue must equal the sum of clean.csv, target must match targets.csv, variance = revenue - target", bad)
    try:
        total_m = sum(float(r["revenue_usd"]) for r in m)
        g.check(abs(total_m - sum(float(r["amount_usd"]) for r in clean_rows)) <= 0.05, "sum of monthly revenue must equal the net revenue of clean.csv")
    except ValueError:
        g.check(False, "non-numeric revenue_usd")
    return g.finish()


def report() -> bool:
    g = Gate("report")
    if not (OUT / "report.md").exists():
        raise SystemExit("FAIL: out/report.md does not exist")
    text = (OUT / "report.md").read_text()
    headings = re.findall(r"^## (.+?)\s*$", text, re.M)
    g.check(headings == SECTIONS, f"level-2 headings must be exactly {SECTIONS} in this order (found {headings})")

    def section(name):
        m = re.search(rf"^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
        return m.group(1) if m else ""

    g.check(0 < len(section("Executive summary").split()) <= 120, "Executive summary must be 1-120 words")
    clean_rows = rows(OUT / "clean.csv")
    total = round(sum(float(r["amount_usd"]) for r in clean_rows), 2)
    g.check(f"{total:,.2f}" in text or f"{total:.2f}" in text, f"net revenue {total:,.2f} must appear in the report")
    by_region = defaultdict(float)
    for r in clean_rows:
        by_region[r["region"]] += float(r["amount_usd"])
    g.check(all(f"{v:,.2f}" in text or f"{v:.2f}" in text for v in by_region.values()), "every region's net revenue must appear in the report")
    log = section("Data quality log").lower()
    g.check("duplicate" in log and "cancel" in log, "Data quality log must mention duplicates and cancelled orders")
    for month in missing_fx_months():
        g.check(month in section("Data quality log") and "rate" in log, f"Data quality log must name {month} as a month without an FX rate and the rate used instead")
    return g.finish()


STAGES = {"profile": profile, "clean": clean, "exceptions": exceptions, "anomalies": anomalies, "monthly": monthly, "report": report}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name == "all":
        ok = all([fn() for fn in STAGES.values()])
    elif name in STAGES:
        ok = STAGES[name]()
    else:
        raise SystemExit(f"usage: validate.py <{'|'.join(STAGES)}|all>")
    sys.exit(0 if ok else 1)

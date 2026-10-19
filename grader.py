"""CLI grader: scores each agent's output (out/) against the correct business rules.

    uv run python grader.py grade agent_1_no_skill
    uv run python grader.py grade-all
"""
import csv
import re
import statistics
from datetime import date, timedelta
from collections import defaultdict
from pathlib import Path

import typer

ROOT = Path(__file__).parent
DATA = ROOT / "data"
ANOMALY_FACTOR = 3  # anomaly: |amount| > 3 x the product's median |amount|
REGIONS = {
    "na": "NA", "north america": "NA", "n. america": "NA", "usa": "NA",
    "emea": "EMEA", "europe": "EMEA",
    "apac": "APAC", "asia-pacific": "APAC",
    "latam": "LATAM", "latin america": "LATAM",
}
CLEAN_COLUMNS = ["order_id", "date", "region", "product", "amount_usd", "status"]
MONTHLY_COLUMNS = ["month", "region", "revenue_usd", "target_usd", "variance_usd"]

app = typer.Typer(help="Grade the agents against the correct business rules.", no_args_is_help=True)


def read_csv(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open())) if path.exists() else []


def parse_amount(s: str) -> tuple[float, str]:
    """'$1,234.50', '1234.50 USD', '1.234,50 EUR', 'EUR 1234.50' -> (number, currency)."""
    eur = "EUR" in s
    num = re.sub(r"[^\d.,]", "", s)
    num = num.replace(".", "").replace(",", ".") if eur and "," in num else num.replace(",", "")
    return float(num), "EUR" if eur else "USD"


def parse_date(s: str) -> str:
    if re.match(r"\d{4}-", s):
        return s
    d, m, y = s.split("/")  # DD/MM/YYYY
    return f"{y}-{m}-{d}"


def fx_table() -> dict[str, float]:
    return {r["month"]: float(r["eur_usd"]) for r in read_csv(DATA / "fx_rates.csv")}


def fx_rate(month: str, table: dict[str, float]) -> float:
    """Rate of the month; if the month is missing, the closest previous month's rate."""
    earlier = [m for m in table if m <= month]
    return table[max(earlier)]


def missing_fx_months(rows: list[dict], table: dict[str, float]) -> list[str]:
    months = {parse_date(r["date"])[:7] for r in rows if "EUR" in r["amount"]}
    return sorted(m for m in months if m not in table)


def dedupe(raw: list[dict]) -> dict[str, dict]:
    """One row per order_id: the last occurrence wins, but a blank-product row never replaces one with a product."""
    best: dict[str, dict] = {}
    for r in raw:
        prev = best.get(r["order_id"])
        if prev and prev["product"] and not r["product"]:
            continue
        best[r["order_id"]] = r
    return best


def expected_clean() -> dict[str, dict]:
    table = fx_table()
    out = {}
    for oid, r in dedupe(read_csv(DATA / "sales_raw.csv")).items():
        if r["status"] == "cancelled":
            continue
        date = parse_date(r["date"])
        value, cur = parse_amount(r["amount"])
        usd = round(value * fx_rate(date[:7], table), 2) if cur == "EUR" else round(value, 2)
        out[oid] = {
            "date": date,
            "region": REGIONS[r["region"].strip().lower()],
            "product": r["product"] or "UNKNOWN",
            "amount_usd": -usd if r["status"] == "refunded" else usd,
        }
    return out


def expected_exceptions() -> set[tuple[str, str]]:
    sales = dedupe(read_csv(DATA / "sales_raw.csv"))
    clean = expected_clean()
    ledger = {r["order_id"]: float(r["refund_amount_usd"]) for r in read_csv(DATA / "refunds_ledger.csv")}
    found: set[tuple[str, str]] = set()
    for oid, r in sales.items():
        if r["status"] != "refunded":
            continue
        if oid not in ledger:
            found.add((oid, "missing_in_ledger"))
        elif abs(ledger[oid] - abs(clean[oid]["amount_usd"])) > 0.01:
            found.add((oid, "amount_mismatch"))
    for oid in ledger:
        if oid not in sales or sales[oid]["status"] != "refunded":
            found.add((oid, "missing_in_sales"))
    return found


def expected_anomalies() -> set[str]:
    clean = expected_clean()
    by_product: dict[str, list[float]] = defaultdict(list)
    for v in clean.values():
        by_product[v["product"]].append(abs(v["amount_usd"]))
    median = {p: statistics.median(a) for p, a in by_product.items()}
    return {k for k, v in clean.items() if abs(v["amount_usd"]) > ANOMALY_FACTOR * median[v["product"]]}


def expected_monthly() -> dict[tuple[str, str], tuple[float, float]]:
    revenue: dict[tuple[str, str], float] = defaultdict(float)
    for v in expected_clean().values():
        revenue[(v["date"][:7], v["region"])] += v["amount_usd"]
    return {
        (t["month"], t["region"]): (round(revenue[(t["month"], t["region"])], 2), float(t["target_usd"]))
        for t in read_csv(DATA / "targets.csv")
    }


def expected_review_queue() -> set[tuple[str, str]]:
    """Orders that policy sends to manual review, one (order_id, reason) per rule that fires."""
    raw = read_csv(DATA / "sales_raw.csv")
    sales = dedupe(raw)
    clean = expected_clean()
    table = fx_table()
    no_rate = set(missing_fx_months(raw, table))
    versions: dict[str, set[tuple[float, str]]] = defaultdict(set)
    for r in raw:
        versions[r["order_id"]].add(parse_amount(r["amount"]))
    found: set[tuple[str, str]] = set()
    for oid, v in clean.items():
        cur = parse_amount(sales[oid]["amount"])[1]
        amount = abs(v["amount_usd"])
        d = date.fromisoformat(v["date"])
        last_day = ((d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day
        rules = {
            "fx_fallback": cur == "EUR" and v["date"][:7] in no_rate,
            "high_value": amount >= 5000,
            "unknown_product": v["product"] == "UNKNOWN" and amount >= 300,
            "latam_refund": v["region"] == "LATAM" and sales[oid]["status"] == "refunded",
            "emea_large_eur": v["region"] == "EMEA" and cur == "EUR" and amount >= 700,
            "apac_weekend": v["region"] == "APAC" and d.weekday() >= 5,
            "quarter_end_large": d.month % 3 == 0 and d.day >= last_day - 4 and amount >= 400,
            "duplicate_conflict": len(versions[oid]) > 1,
        }
        found |= {(oid, name) for name, hit in rules.items() if hit}
    return found


def has_number(text: str, value: float) -> bool:
    return f"{value:,.2f}" in text or f"{value:.2f}" in text


def section(report: str, name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)", report, re.S | re.M)
    return m.group(1) if m else ""


def close(a: str | None, b: float, tol: float = 0.02) -> bool:
    try:
        return abs(float(a) - b) <= tol  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def run_checks(ws: Path) -> list[tuple[str, bool]]:
    out = ws / "out"
    truth = expected_clean()
    rows = read_csv(out / "clean.csv")
    got = {r.get("order_id", ""): r for r in rows}
    report_file = out / "report.md"
    report = report_file.read_text() if report_file.exists() else ""

    # Field checks look only at the rows the agent kept, so a missing or extra row is penalised once
    # (by the exact-rows check) and not again by every field check.
    shared = {k: v for k, v in truth.items() if k in got}

    by_region: dict[str, float] = defaultdict(float)
    for v in truth.values():
        by_region[v["region"]] += v["amount_usd"]
    total = round(sum(v["amount_usd"] for v in truth.values()), 2)

    exc_rows = read_csv(out / "exceptions.csv")
    exceptions = {(r.get("order_id", ""), r.get("issue", "")) for r in exc_rows}
    anom_rows = read_csv(out / "anomalies.csv")
    anomalies = {r.get("order_id", "") for r in anom_rows}
    review_rows = read_csv(out / "review_queue.csv")
    review = {(r.get("order_id", ""), r.get("reason", "")) for r in review_rows}
    monthly_rows = read_csv(out / "monthly.csv")
    monthly = {(r.get("month"), r.get("region")): r for r in monthly_rows}
    expected_m = expected_monthly()

    def monthly_ok() -> bool:
        return set(monthly) == set(expected_m) and all(
            close(monthly[k].get("revenue_usd"), rev) and close(monthly[k].get("target_usd"), tgt)
            and close(monthly[k].get("variance_usd"), round(rev - tgt, 2))
            for k, (rev, tgt) in expected_m.items()
        )

    def totals_consistent() -> bool:
        try:
            clean_sum = sum(float(r["amount_usd"]) for r in rows)
            monthly_sum = sum(float(r["revenue_usd"]) for r in monthly_rows)
        except (KeyError, ValueError):
            return False
        return bool(rows) and abs(clean_sum - monthly_sum) <= 0.05 and abs(clean_sum - total) <= 0.05

    log = section(report, "Data quality log")
    missing = missing_fx_months(read_csv(DATA / "sales_raw.csv"), fx_table())
    summary_words = len(section(report, "Executive summary").split())

    checks = [
        ("clean.csv has the expected columns", bool(rows) and list(rows[0]) == CLEAN_COLUMNS),
        ("no duplicates or cancelled orders (exact rows)", len(rows) == len(got) == len(truth) and set(got) == set(truth)),
        ("correct ISO dates (DD/MM/YYYY read properly)", bool(shared) and all(got[k].get("date") == v["date"] for k, v in shared.items())),
        ("canonical regions (NA/EMEA/APAC/LATAM)", bool(shared) and all(got[k].get("region") == v["region"] for k, v in shared.items())),
        ("blank product -> UNKNOWN", bool(shared) and all(got[k].get("product") == v["product"] for k, v in shared.items())),
        ("USD amounts (monthly EUR rate, refunds negative)", bool(shared) and all(close(got[k].get("amount_usd"), v["amount_usd"], 0.015) for k, v in shared.items())),
        ("exceptions.csv lists exactly the refund mismatches", bool(exc_rows) and exceptions == expected_exceptions()),
        ("anomalies.csv lists exactly the outlier orders", bool(anom_rows) and anomalies == expected_anomalies()),
        ("review_queue.csv lists exactly the (order, reason) pairs", bool(review_rows) and review == expected_review_queue()),
        ("monthly.csv has the expected columns", bool(monthly_rows) and list(monthly_rows[0]) == MONTHLY_COLUMNS),
        ("monthly.csv revenue, target and variance are correct", monthly_ok()),
        ("totals agree across clean.csv and monthly.csv", totals_consistent()),
    ]
    checks += [(f"report.md: section '## {s}'", bool(section(report, s).strip())) for s in
               ["Summary", "Revenue by region", "Top 3 products", "Refund reconciliation", "Anomalies", "Review queue",
                "Data quality log", "Executive summary"]]
    checks += [
        (f"report.md: net total {total:,.2f} USD", has_number(report, total)),
        ("report.md: total for every region", all(has_number(report, x) for x in by_region.values())),
        ("report.md: log mentions duplicates and cancelled orders", "duplicate" in log.lower() and "cancel" in log.lower()),
        (f"report.md: log flags the missing FX rate month ({', '.join(missing)})",
         bool(missing) and all(m in log for m in missing) and "rate" in log.lower()),
        ("report.md: executive summary is at most 120 words", 0 < summary_words <= 120),
    ]
    return checks


def show(name: str, ws: Path) -> tuple[int, int]:
    checks = run_checks(ws)
    typer.secho(f"\n{name}", bold=True)
    for label, ok in checks:
        typer.secho(f"  {'✓' if ok else '✗'} {label}", fg=typer.colors.GREEN if ok else typer.colors.RED)
    score = sum(ok for _, ok in checks)
    typer.secho(f"  => {score}/{len(checks)}", bold=True)
    return score, len(checks)


@app.command()
def grade(agent: str = typer.Argument(..., help="Agent folder, e.g. agent_1_no_skill")):
    """Grade one agent's workspace/out."""
    ws = ROOT / agent / "workspace"
    if not ws.exists():
        typer.secho(f"{ws} does not exist. Run the agent first.", fg=typer.colors.RED)
        raise typer.Exit(1)
    show(agent, ws)


@app.command("grade-all")
def grade_all():
    """Grade every agent_* that has a workspace and print a summary."""
    results = {}
    for d in sorted(ROOT.glob("agent_*")):
        if (d / "workspace").exists():
            results[d.name] = show(d.name, d / "workspace")
    if not results:
        typer.secho("No agent has a workspace yet.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    typer.secho("\nSummary", bold=True)
    for name, (s, n) in results.items():
        typer.echo(f"  {name:<28} {s}/{n}  {'█' * s}{'░' * (n - s)}")


if __name__ == "__main__":
    app()

"""Calificador CLI: puntúa la salida (out/) de cada agente contra las reglas de negocio correctas.

    uv run python grader.py grade agent_1_no_skill
    uv run python grader.py grade-all
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

import typer

ROOT = Path(__file__).parent
EUR_USD = 1.10
REGIONS = {
    "na": "NA", "north america": "NA", "n. america": "NA", "usa": "NA",
    "emea": "EMEA", "europe": "EMEA",
    "apac": "APAC", "asia-pacific": "APAC",
    "latam": "LATAM", "latin america": "LATAM",
}
COLUMNS = ["order_id", "date", "region", "product", "amount_usd", "status"]

app = typer.Typer(help="Califica a los agentes con las reglas de negocio correctas.", no_args_is_help=True)


def parse_amount(s: str) -> float:
    """'$1,234.50', '1234.50 USD', '1.234,50 EUR', 'EUR 1234.50' -> USD."""
    eur = "EUR" in s
    num = re.sub(r"[^\d.,]", "", s)
    num = num.replace(".", "").replace(",", ".") if eur and "," in num else num.replace(",", "")
    return float(num) * (EUR_USD if eur else 1)


def parse_date(s: str) -> str:
    if re.match(r"\d{4}-", s):
        return s
    d, m, y = s.split("/")  # DD/MM/YYYY
    return f"{y}-{m}-{d}"


def expected() -> dict[str, dict]:
    """Respuesta correcta: sin duplicados (gana la fila con producto), sin cancelados, USD, reembolsos negativos."""
    best: dict[str, dict] = {}
    for r in csv.DictReader((ROOT / "data" / "sales_raw.csv").open()):
        if r["order_id"] not in best or (r["product"] and not best[r["order_id"]]["product"]):
            best[r["order_id"]] = r
    out = {}
    for oid, r in best.items():
        if r["status"] == "cancelled":
            continue
        amt = round(parse_amount(r["amount"]), 2)
        out[oid] = {
            "date": parse_date(r["date"]),
            "region": REGIONS[r["region"].strip().lower()],
            "product": r["product"] or "UNKNOWN",
            "amount_usd": -amt if r["status"] == "refunded" else amt,
        }
    return out


def has_number(text: str, value: float) -> bool:
    return f"{value:,.2f}" in text or f"{value:.2f}" in text


def run_checks(ws: Path) -> list[tuple[str, bool]]:
    truth = expected()
    clean = ws / "out" / "clean.csv"
    rows = list(csv.DictReader(clean.open())) if clean.exists() else []
    got = {r["order_id"]: r for r in rows}

    def amount_ok(oid: str, v: dict) -> bool:
        try:
            return abs(float(got[oid]["amount_usd"]) - v["amount_usd"]) < 0.015
        except (KeyError, ValueError):
            return False

    report_file = ws / "out" / "report.md"
    report = report_file.read_text() if report_file.exists() else ""
    by_region: dict[str, float] = defaultdict(float)
    for v in truth.values():
        by_region[v["region"]] += v["amount_usd"]
    total = round(sum(v["amount_usd"] for v in truth.values()), 2)

    checks = [
        ("clean.csv con las columnas esperadas", bool(rows) and list(rows[0]) == COLUMNS),
        ("sin duplicados ni cancelados (filas exactas)", len(rows) == len(got) == len(truth) and set(got) == set(truth)),
        ("fechas ISO correctas (DD/MM/YYYY leído bien)", all(got.get(k, {}).get("date") == v["date"] for k, v in truth.items())),
        ("regiones canónicas (NA/EMEA/APAC/LATAM)", all(got.get(k, {}).get("region") == v["region"] for k, v in truth.items())),
        ("producto vacío -> UNKNOWN", all(got.get(k, {}).get("product") == v["product"] for k, v in truth.items())),
        ("montos en USD (EUR x1.10, reembolsos negativos)", all(amount_ok(k, v) for k, v in truth.items())),
    ]
    checks += [(f"report.md: sección '## {s}'", f"## {s}" in report)
               for s in ["Summary", "Revenue by region", "Top 3 products", "Data quality log"]]
    checks += [
        (f"report.md: total neto {total:,.2f} USD", has_number(report, total)),
        ("report.md: total de cada región", all(has_number(report, x) for x in by_region.values())),
        ("report.md: log menciona duplicados y cancelados", "duplicate" in report.lower() and "cancel" in report.lower()),
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
def grade(agent: str = typer.Argument(..., help="Carpeta del agente, p. ej. agent_1_no_skill")):
    """Califica el workspace/out de un agente."""
    ws = ROOT / agent / "workspace"
    if not ws.exists():
        typer.secho(f"No existe {ws}. Corre primero el agente.", fg=typer.colors.RED)
        raise typer.Exit(1)
    show(agent, ws)


@app.command("grade-all")
def grade_all():
    """Califica todos los agent_* que ya tengan workspace y muestra un resumen."""
    results = {}
    for d in sorted(ROOT.glob("agent_*")):
        if (d / "workspace").exists():
            results[d.name] = show(d.name, d / "workspace")
    if not results:
        typer.secho("Ningún agente tiene workspace todavía.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    typer.secho("\nResumen", bold=True)
    for name, (s, n) in results.items():
        typer.echo(f"  {name:<28} {s}/{n}  {'█' * s}{'░' * (n - s)}")


if __name__ == "__main__":
    app()

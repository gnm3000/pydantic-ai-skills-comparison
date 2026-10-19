# pydantic-ai-learning-skills

Learning project: how much do **Agent Skills** improve what a Pydantic AI agent can do?

Three agents solve the same task (clean a messy sales CSV and write a report), each with more skill support. A CLI grader scores every run, so the improvement is measured, not guessed.

| Agent | Skills | Status |
|---|---|---|
| `agent_1_no_skill` | none (baseline) | done |
| `agent_2_basic_skills` | two simple skills | planned |
| `agent_3_advanced_skill` | one advanced skill + `Planning` | planned |

## Setup

```bash
uv sync
echo "OPENROUTER_API_KEY=..." > .env
uv run python data/make_data.py            # regenerate data/sales_raw.csv (optional)
uv run python -m agent_1_no_skill.main     # run an agent
uv run python grader.py grade agent_1_no_skill
```

Model: `openrouter:deepseek/deepseek-v4.1-flash` (set in `common.py`).

## Agent 1: no skills (baseline)

Tools only: `FileSystem` and `Shell` from `pydantic-ai-harness`. No `Skills`, no `Planning`. It has to guess every business rule.

**Input** (`data/sales_raw.csv`, 66 rows): mixed date formats (`ISO` and `DD/MM/YYYY`), mixed amount formats (`$1,234.50`, `509.87 USD`, `509,87 EUR`, `EUR 109.90`), region aliases (`europe`, `N. America`, `apac`), duplicated orders, blank products, and `completed` / `refunded` / `cancelled` statuses.

**Prompt:** `Clean data/sales_raw.csv and produce out/clean.csv and out/report.md with the cleaned sales.`

**Output** (in `agent_1_no_skill/workspace/out/`):
- `clean.csv`: cleaned rows with ISO dates and deduplicated orders.
- `report.md`: a long report with its own structure, plus a helper script `clean_sales.py` the agent wrote itself.

**Grader score: 1/13.** Only the date check passes.

### Problems with agent 1

It does a reasonable job, but it does not know our business rules:

1. **No currency conversion.** EUR amounts stay in EUR; the expected rule is EUR → USD at ×1.10.
2. **Cancelled orders are kept.** They should be excluded.
3. **Refunds are positive.** They should be negative amounts.
4. **Non-canonical regions.** It keeps names like `europe` / `north america`; expected `NA`, `EMEA`, `APAC`, `LATAM`.
5. **Wrong CSV schema.** It adds `currency` and `amount_raw`; expected `order_id, date, region, product, amount_usd, status`.
6. **Report structure differs.** Missing the required sections `Summary`, `Revenue by region`, `Top 3 products`, `Data quality log`.
7. **No single USD total.** Totals are split by currency or status instead of one net total plus a total per region.
8. **Blank products not marked `UNKNOWN`.**
9. **Non-deterministic.** Tool-call count and output vary between runs (about 18 to 26 calls), so one run is not enough to compare agents.
10. **Fragile with restricted tools.** Hitting a denied command (`rm`) used to abort the whole run until `retries=3` was set.

These gaps are what the skills in agents 2 and 3 are meant to close.

## Grader

`grader.py` (Typer CLI, no LLM) recomputes the correct answer from `data/sales_raw.csv` and checks 13 things in each agent's `out/` folder: CSV schema, dedup/cancelled, ISO dates, canonical regions, `UNKNOWN` products, USD amounts, report sections and totals.

```bash
uv run python grader.py grade agent_1_no_skill
uv run python grader.py grade-all
```

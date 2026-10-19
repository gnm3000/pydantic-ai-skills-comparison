---
name: report-format
description: Required structure and wording for the monthly sales close report out/report.md, with exact section names, what each section contains and how to present totals. Use whenever you write or update a sales report after cleaning and analysing sales data.
---

`out/report.md` must contain these eight sections, with exactly these level-2 headings, in this order. Write the report in English and take every number from the output files with a script; never retype or estimate figures.

## Summary

- Rows in, rows out.
- **Net revenue (USD):** the sum of `amount_usd` over `clean.csv` (refunds are already negative). One single number with 2 decimals, e.g. `12,345.67`.

## Revenue by region

A table with one row per region (`NA`, `EMEA`, `APAC`, `LATAM`) and its net revenue in USD (2 decimals). The regions must add up to the net revenue in the Summary.

## Top 3 products

The 3 products with the highest net revenue in USD (`UNKNOWN` counts as a product), as a table with product and revenue.

## Refund reconciliation

How many refund exceptions were found, by issue type, and the list of affected `order_id`s.

## Anomalies

How many anomalous orders were flagged, with their `order_id`, product and amount.

## Review queue

How many orders and (order, reason) pairs are in the review queue, a count per reason, and the `order_id`s of the `high_value` and `latam_refund` cases.

## Data quality log

A bullet list with the number of rows affected by each cleaning step. Mention at least:

- duplicate rows removed
- cancelled orders dropped
- EUR amounts converted to USD, and any month **without an FX rate** (name the month, e.g. `2025-04`) together with the previous month's rate that was used instead
- refunds made negative
- blank products set to `UNKNOWN`
- region aliases normalized
- dates converted to ISO

## Executive summary

At most **120 words**, for a manager: net revenue, best and worst region against target, the main data problems found and what needs follow-up.

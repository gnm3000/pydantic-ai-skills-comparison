---
name: monthly-close
description: Step-by-step workflow, quality gates and validation scripts for the monthly sales close (cleaning sales data, refund reconciliation, anomalies, manual review queue, monthly revenue against targets, report and executive summary). Use whenever you are asked to run, continue or resume the monthly sales close.
---

This is a 6-stage pipeline with a quality gate after every stage. The detailed business rules are in `references/`; read **only the file of the stage you are working on**.

## 0. Before anything else

Your plan is shown to you at the end of every request, inside `<plan-reminder>`. You only have one planning tool, `write_plan`, which always replaces the **whole** plan (pass every step each time, with its status).

1. If the reminder already lists the 6 steps below, a previous run was interrupted: **resume it**. Do not rewrite the plan from scratch and do not redo steps marked completed (run the stage's validation once to confirm they are still good). Continue with the step in progress or the first pending one.
2. If there is no plan yet, call `write_plan` with exactly these 6 steps, in this order, the first one `in_progress` and the others `pending`:

| # | Step | Reference to read | Validation |
|---|---|---|---|
| 1 | Profile and validate the inputs | none | `profile` |
| 2 | Clean the sales data (`out/clean.csv`) | `references/cleaning-rules.md` | `clean` |
| 3 | Reconcile refunds (`out/exceptions.csv`) | `references/reconciliation.md` | `exceptions` |
| 4 | Flag anomalies and build the review queue (`out/anomalies.csv`, `out/review_queue.csv`) | `references/anomalies-and-review.md` | `anomalies` |
| 5 | Monthly revenue vs targets (`out/monthly.csv`) | `references/monthly-vs-targets.md` | `monthly` |
| 6 | Write the report and executive summary (`out/report.md`) | `references/report-template.md` | `report` |

## How to run each stage

1. Make sure the stage is `in_progress` in the plan (only one at a time; change it by calling `write_plan` with the whole list).
2. Read that stage's reference file.
3. Write the stage as its own script, `work/stageN.py` (N = stage number), and run it. Scripts persist, so a resumed run can re-run them. Compute with Python, never by hand.
4. Run the gate: `python3 skills/monthly-close/scripts/validate.py <validation>`.
   - If it prints `FAIL`, fix the cause in the script, re-run it and validate again. Do **not** move on while a gate fails.
   - If it prints `PASS`, call `write_plan` again with this stage `completed` and the next one `in_progress`.
5. From stage 2 on, append the facts the report will need (rows dropped per rule, the month without an FX rate, counts) to `work/notes.json`, so stage 6 does not depend on your memory.

## Finish

After stage 6 passes, run `validate.py all` once. Then answer with a short summary of the results and any open issue. Never mark a stage `completed` without a passing gate.

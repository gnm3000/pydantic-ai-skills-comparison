# pydantic-ai-learning-skills

How much do **Agent Skills** improve what a Pydantic AI agent can do? Three agents solve the same task with increasing skill support, and a grader that uses no LLM scores every run.

Stack: `pydantic-ai` 2.57, `pydantic-ai-harness` 0.57 (`Skills`, `Planning`, `FileSystem`, `Shell`), model `openrouter:deepseek/deepseek-v4.1-flash` (about $0.03 per million input tokens, so a full run costs cents).

## TL;DR

- **Knowledge skills are the big win.** Same model, same tools, same prompt: 3/25 and 4/25 without skills, 25/25 in all 5 runs with them. The model is not worse at analysis; it cannot guess company conventions (EUR rate by month, what to do with cancelled orders, column names, report sections).
- **A process skill adds recoverability and an audit trail, not a higher score.** The agent with one workflow skill plus `Planning` follows a 6-stage plan, loads one reference per stage and passes a validation gate before moving on. It scored the same (25/25) at a similar cost as the agent with flat knowledge skills.
- **Staged work survives a crash.** Cut mid-pipeline, the process-skill agent resumed in a new process from its own plan and files, skipped the finished stages and completed 25/25 using about half the tokens of a fresh run. The single-script agent has no partial progress to resume.
- **Choose by task.** Short, repeatable task: knowledge skills are enough and simplest. Long or costly task, or one you must audit: add a process skill on top of the knowledge. See [When to choose each](#when-to-choose-each).

## Agents

| Agent | Setup | What it adds |
|---|---|---|
| `agent_1_no_skill` | `FileSystem` + `Shell` | nothing; it has to guess every rule |
| `agent_2_basic_skills` | + `Skills` with 3 flat skills (`sales-cleaning-rules`, `monthly-close-policies`, `report-format`) | knowledge: all rules and schemas, loaded whole |
| `agent_3_advanced_skill` | + one skill `monthly-close` + `Planning(tools=["write_plan"])` (plan persisted in SQLite, rewritten whole on every update) | knowledge **and** process: short `SKILL.md` with a 6-stage workflow, rules split into `references/` (read per stage), `scripts/validate.py` quality gates |

Agent 3's `references/` were generated from agent 2's skills, so both have **the same rules**; only the process differs.

## The task: monthly sales close

Same prompt for all agents (no rules in it):

> Run the monthly sales close. The inputs are in data/. Write these files to out/: clean.csv, exceptions.csv, anomalies.csv, review_queue.csv, monthly.csv and report.md (the report must include an executive summary).

Inputs in `data/` (versioned; regenerate identically with `data/make_data.py`, then `data/make_extra_data.py`): `sales_raw.csv`, `fx_rates.csv` (EUR to USD per month), `refunds_ledger.csv`, `targets.csv`.

Six stages: profile inputs, clean, reconcile refunds, anomalies and review queue, monthly revenue vs targets, report. Planted traps: a month with no FX rate, ledger/sales refund mismatches, a duplicate whose copies disagree on the amount, two outlier amounts, and eight conditional review rules.

## Results

The task grew over three rounds because every version was solved perfectly by the agent with knowledge skills.

| Round | Task | Agent 1 (no skill) | Agent 2 (knowledge) | Agent 3 (process) |
|---|---|---|---|---|
| 1 | clean one CSV, 13 checks | 1/13 | 13/13 | not built |
| 2 | 5 output files, 23 checks | 1/23 | 23/23 (2 of 2 runs) | not built |
| 3 | 6 output files, 25 checks | 3/25 and 4/25 (2 runs) | 25/25 (3 of 3 runs) | 25/25 (2 of 2 runs) |

### Round 3 cost (`bench.py run`; tokens are model input and output)

| Run | Score | Input tokens | Output tokens | Requests | Tool calls | Seconds |
|---|---|---|---|---|---|---|
| Agent 1, run A | 3/25 | 1133k | 29k | 37 | 51 | 90 |
| Agent 1, run B | 4/25 | 464k | 24k | 19 | 26 | 74 |
| **Agent 1, average** | **3.5/25** | **799k** | **26k** | **28** | **38** | **82** |
| Agent 2, run A | 25/25 | 864k | 27k | 32 | 46 | 104 |
| Agent 2, run B | 25/25 | 627k | 24k | 25 | 40 | 75 |
| Agent 2, run C | 25/25 | 257k | 14k | 15 | 23 | 48 |
| **Agent 2, average** | **25/25** | **583k** | **22k** | **24** | **36** | **76** |
| Agent 3, run A | 25/25 | 454k | 12k | 25 | 39 | 69 |
| Agent 3, run B | 25/25 | 601k | 17k | 30 | 42 | 62 |
| **Agent 3, average** | **25/25** | **528k** | **15k** | **28** | **40** | **66** |

Without skills the agent is the most expensive and the most variable (464k to 1.13M input tokens), and it scores far lower. The difference between agents 2 and 3 is within noise: agent 2 alone varies 3.4x in input tokens between runs, and each agent has only 2 to 3 runs.

### What agent 1 does without skills

It does real analysis. It parses both date formats (in run A it checks its reading against the refund ledger), canonicalises the regions, converts EUR with the monthly rate, and flags the same outliers and refund breaks as the other agents (in run B its `anomalies.csv` matches the expected set exactly). What it cannot know is the company's conventions, so it applies its own: it quarantines the conflicting duplicate and the April EUR orders that have no rate instead of using the previous month's rate, keeps cancelled orders in `clean.csv`, adds columns (`currency`, `fx_rate`, `net_usd`...), writes its own report sections and `monthly.csv` layout, and ends with a different net revenue (36,697.54 and 35,773.77 against the expected 36,417.82). Run A even offers to re-run with an interpolated April rate. The grader measures conformity to the company's rules, not intelligence: the score gap is the cost of conventions that exist only in the skills.

### What agent 3 does with its skill

In both runs the trace shows: `write_plan` with the 6 stages, then per stage: read that stage's reference, write `work/stageN.py`, run it together with `validate.py <stage>`, rewrite the plan with the stage completed. The gates passed on the first try almost every time. In both runs it also read the source of `validate.py` before starting, so it knew the checks in advance.

### Crash and resume

`bench.py resume` stops a run after N model requests (simulated crash), then starts a **new process** on the same workspace with the prompt "a previous run was interrupted, continue and do not redo finished work". No message history is passed. Agent 3's plan lives in SQLite and is shown to the model on its first request; its `work/stageN.py` scripts and `work/notes.json` also stay on disk.

| Phase | Score | Input tokens | Requests | Tool calls | Seconds |
|---|---|---|---|---|---|
| Agent 3, cut at 18 requests (stage 4 script written, not run) | 7/25 | 243k | 18 | 28 | 39 |
| Agent 3, resumed | 25/25 | 247k | 17 | 32 | 59 |
| Agent 2, cut at 12 requests | 25/25 | 178k | 12 | 24 | 45 |
| Agent 2, resumed | 25/25 | 336k | 15 | 29 | 107 |

- **Agent 3 resumed correctly.** It listed `work/`, read `notes.json` and `stage4.py`, ran stage 4, validated, wrote and ran stages 5 and 6, and finished 25/25. It did not re-run the scripts of stages 1 to 3. The resumed phase cost 247k tokens, about 47% of a fresh run (528k average). Cut plus resume totalled 490k, about the same as a fresh run: the crash lost no work, it did not make the job cheaper.
- **Agent 2 could not be tested.** It builds everything with one script, so by request 12 every output already existed and the cut came after the work was done. The resumed run did nothing new: it re-implemented the pipeline from scratch to verify the old outputs, which cost 336k tokens, almost twice what it took to build them (178k). An agent with no record of its progress rebuilds its state from the files and re-checks it. A cut early enough to matter (before the script exists) would leave nothing to resume, so a fair "resume" comparison for a single-script agent is simply a fresh run.
- **Caveats.** One pair per agent. For agent 3 the plan reminder and the files in `work/` both helped, and this test cannot separate their effects.

## What I learned

1. **Knowledge is what skills are for.** Rules, schemas and conventions the model cannot know move the score from near zero to full.
2. **A benchmark saturates.** Making the task harder three times still ended at full score for the knowledge skills. A process skill needs a task where self-organising fails: much more data, a rule manual too long to load whole, or interruptions.
3. **Progressive disclosure is only a token story if the rules are long.** Here the rules fit comfortably in context, so loading them per stage did not save tokens.
4. **Validation scripts are a second opinion.** They check schemas, allowed values and cross-file totals, and recompute the rules that can be derived from `clean.csv`. They never read the grader and do not contain the FX rates, but they do catch mistakes, which is part of what a skill with scripts offers.
5. **Check your skills load.** A colon inside a YAML `description` made `Skills` silently skip a skill. Verify the catalog offline: `await Skills("skills").load(LocalWorkspaceBackend(agent_dir))` and look at `.skipped`.
6. **Costs vary a lot between runs.** Judge agents on several runs, not one.
7. **Resumability comes from persisted stages, not from the prompt.** Stage scripts, a notes file and a stored plan let a fresh process pick up where the last one died. "Continue and do not redo finished work" alone makes an agent with no such record spend tokens re-verifying.

## When to choose each

Two kinds of skill, two different jobs:

- A **knowledge skill** (agent 2) holds what the model cannot know: rules, schemas, conventions. It is what produces correct output.
- A **process skill** (agent 3) holds how to do the job: ordered stages, quality gates, a plan, files that persist between stages. It sits on top of the knowledge; it does not replace it. In these runs it did not raise the score or lower the cost. What it added was crash recovery and an audit trail, in exchange for more moving parts.

| Situation | Choose | Why |
|---|---|---|
| Short task that can simply be repeated if it fails | Agent 2: knowledge skills | Simplest setup, fewest things to break |
| Long or costly task you do not want to repeat if it dies | Agent 3: process skill | Progress persists (plan, stage scripts, notes) |
| You need to audit what it did and in what order | Agent 3: process skill | The plan and a validation gate per stage are visible in the trace |
| Rules or conventions the model cannot guess | Any agent with knowledge skills | Without them the score stays near zero |

## Limits

One model, two to three runs per agent, and a grader and skills written by the same person, so the skills were written to pass the exam (the point was to have something to measure). Results would change with another model.

## Run it

```bash
uv sync
echo "OPENROUTER_API_KEY=..." > .env            # never committed
uv run python -m agent_2_basic_skills.main       # run one agent
uv run python grader.py grade agent_2_basic_skills
uv run python grader.py grade-all
uv run python bench.py run agent_3_advanced_skill --runs 2    # max 2 runs per call, output streamed live
uv run python bench.py resume agent_3_advanced_skill --after 18   # one pair of runs
uv run python bench.py show                      # table of every run in results/bench.jsonl
```

- `grader.py` (Typer, no LLM) recomputes the correct answer from `data/` and checks 25 things in each agent's `workspace/out/`. The field checks (dates, regions, products, amounts) look only at the rows the agent kept, so a missing or extra row is penalised once, by the exact-rows check.
- `bench.py` runs each agent in a fresh process, grades it, and saves outputs and logs under `results/` (ignored by git) with tokens, requests and tool calls.
- Each agent's `workspace/` is wiped every time its module is imported, unless `RESUME=1`.

## Layout

```
common.py                  model, workspace setup, runner with stats
grader.py                  25-check CLI grader
bench.py                   multi-run and crash/resume benchmark
data/                      inputs + generators
agent_1_no_skill/          baseline
agent_2_basic_skills/      skills/{sales-cleaning-rules,monthly-close-policies,report-format}
agent_3_advanced_skill/    skills/monthly-close/{SKILL.md,references/,scripts/validate.py}
```

"""Benchmark CLI: run an agent a few times in fresh processes and compare score, tokens and tool calls.

    uv run python bench.py run agent_2_basic_skills --runs 2
    uv run python bench.py resume agent_3_advanced_skill --after 14
    uv run python bench.py show
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import typer

from grader import run_checks

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
MAX_RUNS = 2  # each run calls a paid model, so keep the benchmark small

app = typer.Typer(help="Run agents several times and compare them.", no_args_is_help=True)


def run_live(env: dict | None = None, *, agent: str) -> tuple[int, str]:
    """Run `python -m <agent>.main` in a fresh process, echoing its output as it happens."""
    proc = subprocess.Popen(
        [sys.executable, "-m", f"{agent}.main"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYDANTIC_AI_NO_BANNER": "1", **(env or {})},
    )
    lines = []
    for line in proc.stdout:  # type: ignore[union-attr]
        typer.echo(f"  | {line.rstrip()}")
        lines.append(line)
    return proc.wait(), "".join(lines)


@app.command()
def run(
    agents: list[str] = typer.Argument(..., help="Agent folders, e.g. agent_1_no_skill agent_2_basic_skills"),
    runs: int = typer.Option(2, min=1, max=MAX_RUNS, help=f"Runs per agent (max {MAX_RUNS})"),
):
    """Run each agent `runs` times (fresh process each), grade it and save the outputs under results/."""
    RESULTS.mkdir(exist_ok=True)
    for agent in agents:
        for n in range(1, runs + 1):
            typer.echo(f"{agent} run {n}/{runs} ...")
            start = time.time()
            code, output = run_live(agent=agent)
            seconds = round(time.time() - start)
            ws = ROOT / agent / "workspace"
            checks = run_checks(ws)
            stats_file = ws / "run_stats.json"
            stats = json.loads(stats_file.read_text()) if stats_file.exists() else {}
            row = {
                "agent": agent, "run": n, "score": sum(ok for _, ok in checks), "max_score": len(checks),
                "failed": [name for name, ok in checks if not ok], "seconds": seconds,
                "crashed": code != 0, **stats,
            }
            dest = RESULTS / agent / f"run{n}"
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(ws, dest)
            (dest / "log.txt").write_text(output)
            with (RESULTS / "bench.jsonl").open("a") as f:
                f.write(json.dumps(row) + "\n")
            typer.echo(f"  score {row['score']}/{row['max_score']}"
                       f"{'  (CRASHED, see ' + str(dest / 'log.txt') + ')' if row['crashed'] else ''}")
    show()


@app.command()
def resume(
    agent: str = typer.Argument(..., help="Agent folder, e.g. agent_3_advanced_skill"),
    after: int = typer.Option(14, min=3, help="Model requests before the simulated crash"),
):
    """Crash test: stop a run after N requests, then start a NEW process on the same workspace and finish.

    Both phases are saved and graded. This is one pair of runs; do it once per agent.
    """
    RESULTS.mkdir(exist_ok=True)
    ws = ROOT / agent / "workspace"
    for phase, env in [(f"interrupted@{after}", {"INTERRUPT_AFTER": str(after)}), ("resumed", {"RESUME": "1"})]:
        typer.echo(f"{agent} {phase} ...")
        start = time.time()
        code, output = run_live(env, agent=agent)
        seconds = round(time.time() - start)
        checks = run_checks(ws)
        stats_file = ws / "run_stats.json"
        stats = json.loads(stats_file.read_text()) if stats_file.exists() else {}
        row = {
            "agent": f"{agent} [{phase}]", "run": 1, "score": sum(ok for _, ok in checks), "max_score": len(checks),
            "failed": [name for name, ok in checks if not ok], "seconds": seconds,
            "crashed": code != 0, **stats,
        }
        dest = RESULTS / agent / f"resume_{phase.split('@')[0]}"
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(ws, dest)
        (dest / "log.txt").write_text(output)
        with (RESULTS / "bench.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        typer.echo(f"  score {row['score']}/{row['max_score']}  requests {stats.get('requests')}  "
                   f"in-tokens {stats.get('input_tokens')}{'  (CRASHED, see ' + str(dest / 'log.txt') + ')' if row['crashed'] else ''}")
    show()


@app.command()
def show():
    """Summarize every run saved in results/bench.jsonl, per agent."""
    file = RESULTS / "bench.jsonl"
    if not file.exists():
        typer.secho("No runs yet. Use `bench.py run`.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    rows = [json.loads(line) for line in file.read_text().splitlines()]
    typer.secho(f"\n{'agent':<44}{'run':>4}{'score':>8}{'in tok':>10}{'out tok':>9}{'reqs':>6}{'tools':>7}{'secs':>6}", bold=True)
    for r in rows:
        typer.echo(f"{r['agent']:<44}{r['run']:>4}{str(r['score']) + '/' + str(r['max_score']):>8}"
                   f"{r.get('input_tokens', 0):>10}{r.get('output_tokens', 0):>9}{r.get('requests', 0):>6}"
                   f"{r.get('tool_calls', 0):>7}{r['seconds']:>6}{'  CRASHED' if r['crashed'] else ''}")
    typer.secho("\nAverages", bold=True)
    for agent in dict.fromkeys(r["agent"] for r in rows):
        all_runs = [r for r in rows if r["agent"] == agent]
        mine = [r for r in all_runs if not r["crashed"]]
        if len(mine) < len(all_runs):
            typer.echo(f"  {agent:<44} crashed in {len(all_runs) - len(mine)} of {len(all_runs)} runs"
                       f"{' (no completed run to average)' if not mine else ''}")
        if not mine:
            continue
        avg = lambda k: round(statistics.mean(r.get(k, 0) for r in mine))  # noqa: E731
        typer.echo(f"  {agent:<44} score {avg('score')}/{mine[0]['max_score']}  in {avg('input_tokens')}  "
                   f"out {avg('output_tokens')}  reqs {avg('requests')}  tools {avg('tool_calls')}  ({len(mine)} runs)")
        missed = {n for r in mine for n in r["failed"]} if "[interrupted" not in agent else set()
        if missed:
            typer.echo(f"    failed in at least one run: {'; '.join(sorted(missed))}")


if __name__ == "__main__":
    app()

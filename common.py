"""Shared setup: model (OpenRouter), per-agent workspace, and a runner that traces tool calls."""
import asyncio
import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits
from pydantic_ai_harness import FileSystem, Shell

load_dotenv()  # OPENROUTER_API_KEY from .env

ROOT = Path(__file__).parent
MODEL = "openrouter:deepseek/deepseek-v4.1-flash"
TASK = (
    "Run the monthly sales close. The inputs are in data/. "
    "Write these files to out/: clean.csv, exceptions.csv, anomalies.csv, review_queue.csv, monthly.csv "
    "and report.md (the report must include an executive summary)."
)
RESUME_TASK = (
    "A previous run of this task was interrupted before it finished. Continue it and finish the job; "
    "do not redo work that is already done. The task was: " + TASK
)

# Resume experiment: INTERRUPT_AFTER=N stops a run after N model requests (simulated crash);
# RESUME=1 starts a new process on the SAME workspace instead of wiping it.
RESUME = os.getenv("RESUME") == "1"
INTERRUPT_AFTER = int(os.getenv("INTERRUPT_AFTER", "0")) or None
MAX_REQUESTS = 100


def make_workspace(agent_dir: Path) -> Path:
    """Fresh workspace inside the agent folder, with a copy of the data (and of its skills, if any)."""
    ws = agent_dir / "workspace"
    if RESUME and ws.exists():
        return ws
    shutil.rmtree(ws, ignore_errors=True)
    (ws / "out").mkdir(parents=True)
    shutil.copytree(ROOT / "data", ws / "data", ignore=shutil.ignore_patterns("make_*.py"))
    if (agent_dir / "skills").exists():  # Skills reads its libraries from the run's workspace
        shutil.copytree(agent_dir / "skills", ws / "skills")
    return ws


def base_capabilities(ws: Path):
    return [LocalWorkspace(ws), FileSystem(), Shell(allowed_commands=["python", "python3", "head", "wc", "ls", "cat"])]


def run(agent: Agent, ws: Path) -> None:
    """Run the agent, printing every tool call and saving the run's stats to <ws>/run_stats.json.

    A crash is reported in one line (the stats of the work done so far are still saved) and exits with code 1.
    """
    tool_calls: list[str] = []
    limits = UsageLimits(request_limit=INTERRUPT_AFTER or MAX_REQUESTS)
    interrupted = False
    error: str | None = None

    async def go():
        nonlocal interrupted, error
        async with agent.iter(RESUME_TASK if RESUME else TASK, usage_limits=limits) as r:
            try:
                async for node in r:
                    for part in getattr(getattr(node, "model_response", None), "parts", []) or []:
                        if part.part_kind == "tool-call":
                            tool_calls.append(part.tool_name)
                            print(f"  → {part.tool_name}({str(part.args)[:100]})")
            except UsageLimitExceeded:
                interrupted = True
                print(f"\n*** INTERRUPTED after {r.usage.requests} requests (simulated crash) ***")
            except Exception as e:  # keep the stats of a failed run instead of a wall of traceback
                error = f"{type(e).__name__}: {str(e)[:300]}"
                print(f"\n*** CRASHED after {r.usage.requests} requests: {error} ***")
            return r.usage, (r.result.output if r.result else "")

    usage, output = asyncio.run(go())
    (ws / "run_stats.json").write_text(json.dumps({
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "requests": usage.requests,
        "tool_calls": len(tool_calls),
        "tools": tool_calls,
        "interrupted": interrupted,
        "error": error,
    }))
    print(f"\n{output}\n\n{usage}")
    if error:
        raise SystemExit(1)

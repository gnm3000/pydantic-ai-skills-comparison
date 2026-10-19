"""Agent 3: one advanced skill (staged workflow, references, validation gates) plus a persistent Planning."""
from pydantic_ai import Agent
from pydantic_ai_harness import Planning, Skills
from pydantic_ai_harness.planning import SqlitePlanStore

from common import MODEL, RESUME, ROOT, base_capabilities, make_workspace, run

agent_dir = ROOT / "agent_3_advanced_skill"
ws = make_workspace(agent_dir)

# The plan lives in SQLite, outside the workspace, so a new process can pick it up after a crash.
plan_db = agent_dir / "plan.db"
if not RESUME:
    plan_db.unlink(missing_ok=True)

agent = Agent(
    MODEL,
    capabilities=[
        *base_capabilities(ws),
        Skills("skills"),
        # write_plan only: this model invents arguments for parameterless tools such as read_plan, and the current
        # plan is injected into every request anyway.
        Planning(store=SqlitePlanStore(str(plan_db), session="monthly-close"), tools=["write_plan"]),
    ],
    retries=3,  # a denied command (e.g. rm) must not abort the run
    instructions="You are a data analyst. Work inside the workspace.",
)

if __name__ == "__main__":
    run(agent, ws)

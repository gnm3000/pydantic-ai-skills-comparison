"""Agent 2: same tools as agent 1 plus two simple skills (cleaning rules, report format)."""
from pydantic_ai import Agent
from pydantic_ai_harness import Skills

from common import MODEL, ROOT, base_capabilities, make_workspace, run

ws = make_workspace(ROOT / "agent_2_basic_skills")
agent = Agent(
    MODEL,
    capabilities=[*base_capabilities(ws), Skills("skills")],
    retries=3,  # a denied command (e.g. rm) must not abort the run
    instructions="You are a data analyst. Work inside the workspace.",
)

if __name__ == "__main__":
    run(agent, ws)

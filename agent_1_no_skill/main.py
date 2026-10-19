"""Agent 1: NO skills. Only files and shell; it has to guess every business rule."""
from pydantic_ai import Agent

from common import MODEL, ROOT, base_capabilities, make_workspace, run

ws = make_workspace(ROOT / "agent_1_no_skill")
agent = Agent(
    MODEL,
    capabilities=base_capabilities(ws),
    retries=3,  # a denied command (e.g. rm) must not abort the run
    instructions="You are a data analyst. Work inside the workspace.",
)

if __name__ == "__main__":
    run(agent)

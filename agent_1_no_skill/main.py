"""Agente 1: SIN skills. Solo archivos y shell; tiene que adivinar todas las reglas de negocio."""
from pydantic_ai import Agent

from common import MODEL, ROOT, base_capabilities, make_workspace, run

ws = make_workspace(ROOT / "agent_1_no_skill")
agent = Agent(
    MODEL,
    capabilities=base_capabilities(ws),
    retries=3,  # un comando denegado (p. ej. rm) no debe abortar la corrida
    instructions="Eres un analista de datos. Trabaja dentro del workspace.",
)

if __name__ == "__main__":
    run(agent)

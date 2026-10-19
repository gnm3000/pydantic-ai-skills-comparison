"""Configuración compartida: modelo (OpenRouter), workspace por agente y ejecución con traza de herramientas."""
import asyncio
import shutil
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai_harness import FileSystem, Shell

load_dotenv()  # OPENROUTER_API_KEY desde .env

ROOT = Path(__file__).parent
MODEL = "openrouter:deepseek/deepseek-v4.1-flash"
TASK = "Limpia data/sales_raw.csv y genera out/clean.csv y out/report.md con las ventas limpias."


def make_workspace(agent_dir: Path) -> Path:
    """Workspace limpio dentro de la carpeta del agente, con una copia de los datos."""
    ws = agent_dir / "workspace"
    shutil.rmtree(ws, ignore_errors=True)
    (ws / "out").mkdir(parents=True)
    shutil.copytree(ROOT / "data", ws / "data", ignore=shutil.ignore_patterns("make_data.py"))
    return ws


def base_capabilities(ws: Path):
    return [LocalWorkspace(ws), FileSystem(), Shell(allowed_commands=["python", "python3", "head", "wc", "ls", "cat"])]


def run(agent: Agent, task: str = TASK) -> None:
    """Corre el agente mostrando cada llamada a herramienta."""
    async def go():
        async with agent.iter(task) as r:
            async for node in r:
                for part in getattr(getattr(node, "model_response", None), "parts", []) or []:
                    if part.part_kind == "tool-call":
                        print(f"  → {part.tool_name}({str(part.args)[:100]})")
        return r.result

    result = asyncio.run(go())
    print(f"\n{result.output}\n\n{result.usage}")

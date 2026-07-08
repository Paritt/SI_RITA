import os
import sys
import json
from datetime import datetime

# ── Path setup ──────────────────────────────────────────────────────
# path = ".venv/lib/python3.9/site-packages"

# def setupPath(target_path: str):
#     sys.path.insert(0, target_path)
#     os.environ["SCRIPT_PATH"] = target_path

# setupPath(path)

# ── Load environment variables from .env ───────────────────────────
from pathlib import Path
from dotenv import load_dotenv
# Load the .env at the project root (parent of src/), regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# ── LangGraph / LangChain imports ──────────────────────────────────
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated, Sequence, NotRequired
from langchain_core.messages import BaseMessage

# ── LangSmith tracing ──────────────────────────────────────────────
# LANGSMITH_API_KEY is provided by the .env file (loaded above)
os.environ["LANGSMITH_TRACING"]  = "true"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_PROJECT"]  = "SI_RITA"


# ====================================================================
#  Agent State
# ====================================================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    model: str

# ====================================================================
#  Node imports
# ====================================================================

# --- Agents ---
from src.sub_agent.general.general import general_agent, ALL_GENERAL_TOOLS


# ====================================================================
#  Helper functions
# ====================================================================
def _should_continue(state: AgentState) -> str:
    """Route: did the general agent request a tool call?"""
    last = state["messages"][-1]
    return "use_tool" if getattr(last, "tool_calls", None) else "not_use_tool"


# ====================================================================
#  Build Graph
# ====================================================================
graph = StateGraph(AgentState)

# ── General agent (with tool loop) ────────────────────────────────
graph.add_node("general_agent", general_agent)
graph.add_node("general_tool_node", ToolNode(tools=ALL_GENERAL_TOOLS))

graph.add_edge(START, "general_agent")
graph.add_conditional_edges(
    "general_agent",
    _should_continue,
    {"use_tool": "general_tool_node", "not_use_tool": END},
)
graph.add_edge("general_tool_node", "general_agent")

# ── Compile ────────────────────────────────────────────────────────
agent = graph.compile()


# ====================================================================
#  Graph visualisation
# ====================================================================
def save_graph_image():
    from pathlib import Path
    from IPython.display import Image

    png_bytes = agent.get_graph().draw_mermaid_png()
    out_path = Path("agent_flow.png")
    out_path.write_bytes(png_bytes)
    print(f"Saved: {out_path.resolve()}")
    return Image(png_bytes)

# save_graph_image() # Uncomment to save and display the graph image
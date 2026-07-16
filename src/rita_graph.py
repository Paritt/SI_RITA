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
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.util.llm import get_chat_model

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
    route: str  # set by the router node: "planning" | "general"


# ====================================================================
#  Router
# ====================================================================
# The router picks ONE sub-agent per user turn so each agent only loads its own
# system prompt (context savings). Obvious planning requests short-circuit on a
# keyword; anything ambiguous — including context-dependent follow-ups like
# "lower it a bit" — is classified by a small LLM call over the recent transcript.
_PLANNING_KEYWORDS = (
    "optimize", "optimise", "optimization", "optimisation", "objective", "constraint",
    "weight", "dvh", "eud", "fall off", "falloff", "fall-off", "coverage", "conformity",
    "spare", "sparing", "reoptimize", "re-optimize", "tune", "boolean", "helper roi",
    "min dose", "max dose", "mean dose", "hotspot", "hot spot",
)

_ROUTER_SYSTEM = (
    "You are the router for RITA, a radiotherapy assistant. Decide whether the user's LATEST message "
    "is a PLAN-OPTIMIZATION / treatment-planning task or a GENERAL request.\n"
    "PLANNING = actually creating, optimizing, or improving a plan: add or adjust optimization "
    "objectives or constraints, run or tune the optimization, create helper ROIs, improve target "
    "coverage, spare an OAR, conformity / dose fall-off, or a follow-up that continues such work "
    "(e.g. 'lower it a bit', 'make it tighter', 'try again', 'now the rectum').\n"
    "GENERAL = patient info, explaining concepts, REPORTING current dose or clinical goals without "
    "changing the plan, math, or anything else.\n"
    "Reply with exactly one word: planning or general."
)


def _last_human_text(messages) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


def _recent_transcript(messages, n: int = 6) -> str:
    parts = []
    for m in messages[-n:]:
        role = getattr(m, "type", m.__class__.__name__)
        content = getattr(m, "content", "")
        text = content if isinstance(content, str) else str(content)
        if text.strip():
            parts.append(f"{role}: {text.strip()}")
    return "\n".join(parts) if parts else "(no prior messages)"


def router(state: AgentState) -> AgentState:
    """Classify the current turn as 'planning' or 'general' and record it in state['route']."""
    messages = state["messages"]
    latest = _last_human_text(messages).lower()

    if any(kw in latest for kw in _PLANNING_KEYWORDS):
        state["route"] = "planning"
        print("\n 🧭Router → planning (keyword)")
        return state

    decision = "general"
    try:
        model = get_chat_model(state.get("model", "gpt-5"))
        resp = model.invoke([
            SystemMessage(content=_ROUTER_SYSTEM),
            HumanMessage(content=_recent_transcript(messages)),
        ])
        out = resp.content if isinstance(resp.content, str) else str(resp.content)
        decision = "planning" if "planning" in out.lower() else "general"
    except Exception as e:
        print(f"\n 🧭Router error, defaulting to general: {e}")
        decision = "general"

    state["route"] = decision
    print(f"\n 🧭Router → {decision} (classifier)")
    return state


def _route(state: AgentState) -> str:
    return state.get("route", "general")


# ====================================================================
#  Node imports
# ====================================================================

# --- Agents ---
from src.sub_agent.general.general import general_agent, ALL_GENERAL_TOOLS
from src.sub_agent.planning.planning import planning_agent
from src.sub_agent.planning.planning_sys_prompt import PLANNING_TOOLS


# ====================================================================
#  Helper functions
# ====================================================================
def _should_continue(state: AgentState) -> str:
    """Route: did the agent request a tool call?"""
    last = state["messages"][-1]
    return "use_tool" if getattr(last, "tool_calls", None) else "not_use_tool"


# ====================================================================
#  Build Graph
# ====================================================================
graph = StateGraph(AgentState)

# ── Router: pick a sub-agent for this turn ────────────────────────
graph.add_node("router", router)

# ── General agent (read-only, with tool loop) ─────────────────────
graph.add_node("general_agent", general_agent)
graph.add_node("general_tool_node", ToolNode(tools=ALL_GENERAL_TOOLS))

# ── Planning agent (plan-modifying, with tool loop) ───────────────
graph.add_node("planning_agent", planning_agent)
graph.add_node("planning_tool_node", ToolNode(tools=PLANNING_TOOLS))

graph.add_edge(START, "router")
graph.add_conditional_edges(
    "router",
    _route,
    {"planning": "planning_agent", "general": "general_agent"},
)

graph.add_conditional_edges(
    "general_agent",
    _should_continue,
    {"use_tool": "general_tool_node", "not_use_tool": END},
)
graph.add_edge("general_tool_node", "general_agent")

graph.add_conditional_edges(
    "planning_agent",
    _should_continue,
    {"use_tool": "planning_tool_node", "not_use_tool": END},
)
graph.add_edge("planning_tool_node", "planning_agent")

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
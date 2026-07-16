from langchain_core.messages import AIMessage, SystemMessage
from langsmith import traceable

from src.rita_graph import AgentState
from src.util.llm import get_chat_model
from src.sub_agent.planning.planning_sys_prompt import (
    planning_agent_system_message,
    PLANNING_TOOLS,
)


@traceable(run_type="llm", name="Planning Agent", project="SI_RITA")
def planning_agent(state: AgentState) -> AgentState:
    selected_model = state.get("model", "gpt-5")
    try:
        model = get_chat_model(selected_model)
    except ValueError as e:
        print(f"ERROR: {e}")
        state["messages"].append(AIMessage(content=f"Error: {e}", tool_calls=[]))
        return state

    # bind_tools converts the tools into each provider's native schema
    # (OpenAI "function" format vs Anthropic "input_schema" format).
    model_with_tools = model.bind_tools(PLANNING_TOOLS)

    request = [
        SystemMessage(content=planning_agent_system_message),
        *state["messages"],
    ]

    try:
        print(f"\n 🧭Planning Agent is thinking...")
        response = model_with_tools.invoke(request)
        answer_text = response.content
        tool_calls = response.tool_calls or []
    except Exception as e:
        answer_text = f"Error: {e}"
        tool_calls = []

    print('\n 🧭Planning:', answer_text)
    print(f"\n 🛠️Planning Tool calls: {tool_calls}")
    state["messages"].append(AIMessage(content=answer_text, tool_calls=tool_calls))
    return state

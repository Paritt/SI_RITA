import os

from langchain_core.messages import AIMessage, SystemMessage
from src.util.helpers import _to_ollama_tools
from src.rita_graph import AgentState
from src.my_langgchain_tool.raystation_tool import tools as raystation_tools
from src.my_langgchain_tool.math_tool import tools as math_tools
from src.my_langgchain_tool.general_tool import tools as general_tools
from src.sub_agent.general.general_sys_prompt import general_agent_system_message
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langsmith import traceable

ALL_GENERAL_TOOLS = [*math_tools, *raystation_tools, *general_tools]

@traceable(run_type="llm", name="General Agent", project="SI_RITA")
def general_agent(state: AgentState) -> AgentState:
    selected_model = state.get("model", "gpt-5")
    if selected_model.lower() == "gpt-5":
        model = ChatOpenAI(
                    model="gpt-5",
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    )
    elif "sonnet" in selected_model.lower():
        model = ChatAnthropic(
                    model="claude-sonnet-4-5-20250929",
                    api_key=os.environ.get("ANTHROPIC_API_KEY"),
                    )
    else:
        # TODO Add more model
        print("ERROR: Unsupported model selected. Please choose a valid model.")

    ollama_tools = _to_ollama_tools(ALL_GENERAL_TOOLS)
    model_with_tools = model.bind(tools=ollama_tools)

    request = [
        SystemMessage(content=general_agent_system_message),
        *state["messages"]
    ]

    try:
        print(f"\n 🤖General Agent is thinking...")
        response = model_with_tools.invoke(request)
        answer_text = response.content
        tool_calls = response.tool_calls or []
    except Exception as e:
        answer_text = f"Error: {e}"
        tool_calls = []

    print('\n 🤖General:', answer_text)
    print(f"\n 🛠️General Tool calls: {tool_calls}")
    state["messages"].append(AIMessage(content=answer_text, tool_calls=tool_calls))
    return state

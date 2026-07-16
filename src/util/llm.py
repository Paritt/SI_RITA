"""Shared chat-model factory so every node (agents + router) builds the LLM the same way."""
import os

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


def get_chat_model(selected_model: str):
    """Return a LangChain chat model for the model name carried in the graph state.

    Supported: 'gpt-5' (OpenAI) and any name containing 'sonnet' (Anthropic Claude Sonnet 4.5).
    Raises ValueError for anything else so the caller can surface a clear error.
    """
    name = (selected_model or "gpt-5").lower()
    if name == "gpt-5":
        return ChatOpenAI(model="gpt-5", api_key=os.environ.get("OPENAI_API_KEY"))
    if "sonnet" in name:
        return ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    raise ValueError(f"Unsupported model selected: {selected_model!r}")

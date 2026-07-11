"""
Headless smoke test for the RITA agent — no GUI / no Tk required.

Usage:
    .venv/bin/python test_agent.py "What is 128 divided by 4?"          # OpenAI (gpt-5)
    .venv/bin/python test_agent.py "What is 128 divided by 4?" sonnet   # Anthropic Claude Sonnet

Requires the relevant API key in .env (OPENAI_API_KEY / ANTHROPIC_API_KEY).
Uses only the math/general tools, so it works fine off RayStation.
"""
import sys
from langchain_core.messages import HumanMessage
from src.rita_graph import agent

prompt = sys.argv[1] if len(sys.argv) > 1 else "What is 128 divided by 4?"
model = sys.argv[2] if len(sys.argv) > 2 else "gpt-5"

print(f"\n=== Running RITA agent | model={model!r} | prompt={prompt!r} ===\n")

result = agent.invoke({"messages": [HumanMessage(content=prompt)], "model": model})

final = result["messages"][-1]
print("\n=== Final answer ===")
print(getattr(final, "content", final))

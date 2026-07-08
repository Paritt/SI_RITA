# RITA — Radiotherapy Intelligent Treatment Assistant

RITA (SI_RITA) is an AI assistant that runs **inside [RayStation](https://www.raysearchlabs.com/raystation/)** as a scripting tool. It provides a chat GUI backed by a LangGraph agent that can call tools — including tools that read data from the currently open RayStation patient — to help with radiotherapy treatment-planning tasks.

The agent can be driven by either **OpenAI (GPT‑5)** or **Anthropic (Claude Sonnet)** models, selectable from a dropdown in the interface.

---

## Features

- 🖥️ **Desktop chat GUI** built with `tkinter` / `ttkbootstrap` (dark theme).
- 🤖 **Single general agent** built on LangGraph, with an automatic tool-calling loop.
- 🔀 **Model switching** at runtime — `gpt-5` (OpenAI) or `sonnet` (Anthropic Claude Sonnet).
- 🛠️ **Tools** the agent can call:
  - **RayStation** — read patient name, date of birth, gender, and ID from the open case.
  - **Math** — add, subtract, multiply, divide.
  - **General** — count characters, get the current time.
- 📊 **LangSmith tracing** for observability (project `SI_RITA`).

---

## Architecture

The agent is a small LangGraph state machine with one node and a tool loop:

```
START ──▶ general_agent ──┬─ (requested a tool?) ──▶ general_tool_node ──┐
                          │                                              │
                          │◀─────────────────────────────────────────────┘
                          └─ (no tool) ──▶ END
```

- `general_agent` sends the conversation (plus a system prompt) to the selected LLM.
- If the model requests a tool, `general_tool_node` executes it and loops the result back.
- When the model responds without a tool call, the turn ends.

---

## Project structure

```
SI_RITA/
├── rita.py                       # GUI entry point (RITA_GUI) — run this
├── requirements.txt              # Python dependencies
├── .env                          # API keys (gitignored — never commit)
├── .gitignore
├── README.md
└── src/
    ├── rita_graph.py             # LangGraph definition, AgentState, compiled `agent`
    ├── my_langgchain_tool/
    │   ├── raystation_tool.py    # patient-data tools (RayStation only)
    │   ├── math_tool.py          # arithmetic tools
    │   ├── general_tool.py       # misc utility tools
    │   └── code_tool.py
    ├── sub_agent/general/
    │   ├── general.py            # the general_agent node + model selection
    │   └── general_sys_prompt.py # system prompt
    └── util/
        └── helpers.py            # tool/message format conversion helpers
```

---

## Configuration

All secrets live in a `.env` file at the project root (loaded automatically at startup).

Create `.env` with:

```dotenv
# OpenAI — https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-proj-...

# Anthropic / Claude — https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY=sk-ant-...

# LangSmith tracing — https://smith.langchain.com
LANGSMITH_API_KEY=...
```

> ⚠️ **Never commit `.env`.** It is already listed in `.gitignore`. Keep your keys out of source files.

---

## Local development (macOS / Linux / Windows, outside RayStation)

Use this to edit and iterate. Note that the RayStation tools (`raystation_tool.py`) only work inside RayStation, since the `raystation` module ships only with RayStation's own Python.

```bash
# 1. Create and populate a virtual environment
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python -m pip ...

# 2. Add your keys to .env (see Configuration above)

# 3. Run
.venv/bin/python rita.py
```

---

## Deployment inside RayStation

RayStation runs its own **embedded Python interpreter** into which you cannot `pip install` directly. Instead, the libraries are installed into a separate venv and made importable by prepending its `site-packages` to `sys.path` at the top of the script (`setupPath` in `rita.py`).

### 1. Find RayStation's Python version

In RayStation's scripting console:

```python
import sys
print(sys.version)          # note the major.minor version (e.g. 3.9)
print(sys.maxsize > 2**32)  # True = 64-bit
```

### 2. Build a matching venv on **Windows**

The venv **must** be built with the **same OS (Windows) and Python major.minor version** as RayStation — several dependencies ship compiled wheels that are version- and platform-specific.

Install the dependencies into the `site-packages` folder that `rita.py` points at:

```powershell
py -3.9 -m pip install --target "\\zkh\...\RITA\.venv\Lib\site-packages" -r requirements.txt
```

### 3. Point the script at that folder

`rita.py` sets `sys.path` before importing any third-party library:

```python
path = "//zkh/appdata/Raystation/Research/ML/Paritt/RITA/.venv/Lib/site-packages"
setupPath(path)   # sys.path.insert(0, path)
```

Update `path` to wherever your Windows venv's `site-packages` lives.

### 4. Provide the `.env`

Place a `.env` (with your real keys) at the project root next to the code on the share. It is loaded via an absolute path, so it is found regardless of RayStation's working directory.

---

## Usage

1. Launch RITA (`python rita.py`, or run the script from within RayStation).
2. Pick a model from the dropdown: **gpt-5** or **sonnet**.
3. Type a prompt and send. Responses stream into the chat window; tool calls are shown inline.

Example prompts:

- "What is the patient's name and ID?" → calls the RayStation tools.
- "What is 128 divided by 4?" → calls the math tools.
- "What time is it right now?" → calls `get_current_time`.

---

## Observability

Runs are traced to **LangSmith** under the project `SI_RITA` (configured in `src/rita_graph.py`). View traces at <https://smith.langchain.com> with the account that owns your `LANGSMITH_API_KEY`.

---

## Security notes

- `.env`, `.venv/`, and `__pycache__/` are gitignored.
- Do not hardcode API keys in source files — read them from the environment / `.env`.
- If a key was ever committed or shared, **rotate it** (regenerate it in the provider console).
- Patient data accessed via the RayStation tools stays within your RayStation session; be mindful of what patient information is sent to third‑party LLM providers.

---

## Requirements

- Python matching your run target (RayStation's version for deployment; any 3.9+ for local dev).
- Dependencies: `langgraph`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `langsmith`, `ttkbootstrap`, `python-dotenv` (see `requirements.txt`).
- API keys for the providers you intend to use (OpenAI and/or Anthropic) and LangSmith.

import sys
import os
import subprocess
import tempfile
from datetime import datetime

from langchain_core.tools import tool

# Where executed snippets + their output get logged (auto-run + audit trail).
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "code_exec")

# Safety knobs.
TIMEOUT_SECONDS = 30      # kill a snippet that runs longer than this
MAX_OUTPUT_CHARS = 10000  # cap returned text so a runaway print can't blow context


def _log_execution(code: str, output: str) -> None:
    """Write the code and its output to a timestamped log file.

    Fail-safe: a logging error must never block or crash execution.
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S-%f")
        with open(os.path.join(LOG_DIR, f"{stamp}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        with open(os.path.join(LOG_DIR, f"{stamp}.out.txt"), "w", encoding="utf-8") as f:
            f.write(output)
    except Exception:
        pass


def _truncate(text: str) -> str:
    """Cap text length so the LLM context isn't flooded."""
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text)} chars total]"
    return text


@tool
def run_python_code(code: str) -> str:
    """Execute a Python script and return its stdout, stderr, and exit code.

    Use this to run calculations, scripts, or any Python you generate. The code
    runs in a fresh subprocess, so variables do NOT persist between calls — each
    call must be a complete, self-contained script.

    Args:
        code: A complete, self-contained Python script to execute.

    Returns:
        A text report containing the script's stdout, stderr, and exit code.
    """
    # Write the snippet to a temp file, then run it in a fresh interpreter
    # (same executable as RITA, so the .venv packages are available).
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout or ""
            stderr = (e.stderr or "") + f"\n[TIMEOUT] Killed after {TIMEOUT_SECONDS}s."
            exit_code = -1
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    report = (
        f"--- STDOUT ---\n{_truncate(stdout)}\n"
        f"--- STDERR ---\n{_truncate(stderr)}\n"
        f"--- EXIT CODE: {exit_code} ---"
    )
    _log_execution(code, report)
    return report


tools = [run_python_code]
available_functions = {tool.name: tool for tool in tools}

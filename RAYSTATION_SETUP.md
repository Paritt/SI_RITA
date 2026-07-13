# Using Python libraries (pip packages) inside RayStation — Setup Guide

RayStation runs scripts with **its own embedded Python interpreter**, and you cannot `pip install`
into it directly. This guide shows the standard workaround:

> **Install the libraries into a folder yourself, then tell RayStation's Python to look in that
> folder by adding it to `sys.path`.**

---

## The one rule that matters

The libraries must be built for the **exact interpreter that will run them**:

| Must match | Why |
|---|---|
| **Operating system** (Windows) | Packages like `pydantic_core` ship **compiled binaries** (`.pyd` on Windows, `.so` on macOS/Linux). A macOS build cannot load on Windows. |
| **Python version** (e.g. 3.11) | Compiled binaries are tagged to a version — `cp311` will not load on 3.9 or 3.12. |

⚠️ **Never copy a `.venv` from macOS/Linux to Windows** (or between Python versions). It will fail with:

```
ImportError: No module named 'pydantic_core._pydantic_core'
```

Adding the folder to `sys.path` only makes it *visible* — it does **not** make incompatible
binaries work. Always install on **Windows**, with **RayStation's Python version**.

---

## Step 1 — Find RayStation's Python version

Run this **inside RayStation's scripting console**:

```python
import sys
print(sys.version)      # e.g. 3.11.x  -> note the major.minor (3.11)
print(sys.executable)   # e.g. C:\Program Files\Python311\python.exe
```

Everything below assumes **Python 3.11** — substitute your version if different.

---

## Step 2 — Create the virtual environment (on Windows)

Open **Command Prompt (`cmd.exe`)** on the Windows machine and `cd` to the project folder.

There is no "version" flag for `venv` — **the interpreter you invoke decides the version**.
Use RayStation's own Python so it matches exactly:

```bat
cd /d P:\BOO\SI_RITA

:: Option A — use RayStation's interpreter directly (safest)
"C:\Program Files\Python311\python.exe" -m venv .venv

:: Option B — use the Windows py launcher to pick the version
py -3.11 -m venv .venv
```

Helpful: `py -0` lists every Python version installed on the machine.

This creates:

```
P:\BOO\SI_RITA\.venv\Lib\site-packages     <-- the libraries live here
```

> **Note the Windows layout:** `.venv\Lib\site-packages` (capital `Lib`, no version subfolder).
> macOS/Linux instead uses `.venv/lib/python3.11/site-packages` — another reason the two are not interchangeable.

---

## Step 3 — Install the libraries with pip

```bat
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Alternative (no venv needed).** Since we only ever add the folder to `sys.path`, you can skip
`venv` entirely and install straight into a target folder:

```bat
"C:\Program Files\Python311\python.exe" -m pip install --target ".venv\Lib\site-packages" -r requirements.txt
```

Both produce the same result: a `site-packages` folder full of Windows/3.11 packages.

---

## Step 4 — Verify you got **Windows** binaries ⭐

This is the check that catches 90% of problems. Look at the compiled package:

```bat
dir ".venv\Lib\site-packages\pydantic_core"
```

| You see | Meaning |
|---|---|
| `_pydantic_core.cp311-win_amd64.pyd` | ✅ Correct — Windows, Python 3.11 |
| `_pydantic_core.cpython-39-darwin.so` | ❌ macOS build — you copied a Mac venv. Delete and redo Step 2–3 on Windows. |
| `_pydantic_core.cp39-win_amd64.pyd` | ❌ Wrong Python version — reinstall with 3.11. |

---

## Step 5 — Point RayStation's Python at the folder (`sys.path`)

At the **very top of your script**, *before* importing any third-party library, add the
`site-packages` folder to `sys.path`:

```python
import sys
import os

# -- Path setup ---------------------------------------------------------------
# Note the r"" raw string: backslashes in Windows paths are escape characters otherwise.
_VENV_PATH = r"P:\BOO\SI_RITA\.venv\Lib\site-packages"
sys.path.insert(0, _VENV_PATH)
os.environ["SCRIPT_PATH"] = _VENV_PATH
# -----------------------------------------------------------------------------

# Only AFTER the path setup can you import the installed libraries:
from langchain_core.messages import HumanMessage
import langgraph
```

**Order matters.** Any `import` of an installed library must come *after* `sys.path.insert(...)`,
or Python will not find it.

### Use a raw string for the path

```python
_VENV_PATH = r"P:\BOO\SI_RITA\.venv\Lib\site-packages"   # ✅ raw string
_VENV_PATH = "P:\BOO\SI_RITA\.venv\Lib\site-packages"    # ⚠️ backslashes are escapes — fragile
_VENV_PATH = "P:/BOO/SI_RITA/.venv/Lib/site-packages"    # ✅ forward slashes also fine on Windows
```

Without the `r`, a folder starting with `n`, `t`, `r`, `b`, or `f` silently corrupts the path
(`\temp` becomes a TAB character).

---

## Step 6 — Run the script in RayStation

RayStation's Python 3.11 now finds the libraries in your folder. Done.

---

## Quick reference (copy/paste)

```bat
:: On the WINDOWS machine, in the project folder
cd /d P:\BOO\SI_RITA

:: 1. remove any old / wrong-platform libraries
rmdir /s /q .venv

:: 2. create the venv with RayStation's Python
"C:\Program Files\Python311\python.exe" -m venv .venv

:: 3. install the libraries
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt

:: 4. verify Windows binaries
dir .venv\Lib\site-packages\pydantic_core
```

```python
# In the script, at the very top:
import sys, os
_VENV_PATH = r"P:\BOO\SI_RITA\.venv\Lib\site-packages"
sys.path.insert(0, _VENV_PATH)
os.environ["SCRIPT_PATH"] = _VENV_PATH
# ...then import your libraries
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `No module named 'pydantic_core._pydantic_core'` | Libraries built for the wrong OS/version (usually a Mac venv copied over) | Reinstall on Windows with RayStation's Python (Steps 2–4) |
| `No module named 'langchain_core'` (etc.) | `sys.path` doesn't point at the right folder, or the import runs *before* the path setup | Check the path string and that path setup is **above** all library imports |
| `ImportError: cannot import name 'NotRequired' from 'typing'` | Library/syntax needs a newer Python than the one running | Make sure the venv Python version matches RayStation's |
| Path silently wrong (e.g. contains a tab) | Backslash escape in a normal string | Use a raw string: `r"P:\..."` |

---

## Summary in one line

**Install the packages on Windows with RayStation's own Python version, then
`sys.path.insert(0, r"...\.venv\Lib\site-packages")` at the top of your script — and never copy a
venv between operating systems.**

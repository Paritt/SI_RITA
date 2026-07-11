from __future__ import annotations  # allow "X | Y" annotations on Python 3.9

import tkinter as tk
import threading
import time
import re
from collections import deque
from uuid import uuid4
try:
    from connect import *
except ImportError:
    print("Warning: 'raystation' module not found. Some features may not work.")
import sys
import os
import ctypes

# ── Path setup ──────────────────────────────────────────────────────
path = ".venv/lib/python3.9/site-packages"

def setupPath(path):
    """Set the path and environment"""
    sys.path.insert(0, path)
    os.environ["SCRIPT_PATH"] = path

setupPath(path)
# ────────────────────────────────────────────────────────────────────

from langchain_core.messages import AnyMessage, AIMessage, HumanMessage, ToolMessage
from src.rita_graph import agent
import ttkbootstrap as ttkb
from ttkbootstrap.widgets.scrolled import ScrolledText
#from langchain_mcp_adapters.client import MultiServerMCPClient

class RITA_GUI(ttkb.Window):
    def __init__(self):
        # macOS system Tk (8.5) can't decode ttkbootstrap's PNG window icon, so
        # skip it there (iconphoto=None). Windows/RayStation keeps the icon.
        super().__init__(
            themename="darkly",
            iconphoto=None if sys.platform == "darwin" else "",
        )
        self.title("RITA - Radiotherapy Intelligent Treatment Assistant")
        self.geometry("540x800")
        self._enable_windows_dark_titlebar()
        

        self.model_var = tk.StringVar(value="sonnet")
        self.show_think_var = tk.BooleanVar(value=True)
        self.show_tool_use_var = tk.BooleanVar(value=True)
        self.debug_mode_var = tk.BooleanVar(value=False)
        self.clear_process_var = tk.BooleanVar(value=True)
        self.model_options = ["gpt-5", "sonnet"]
        self.turn_counter = 0
        self.prompt_history = deque(maxlen=20)
        self.conversation_history: list[AnyMessage] = []
        
        # Output area
        self.output = ScrolledText(
            self,
            wrap=tk.WORD,
            height=30,
            bg="#000000",
            fg="#EDEDED",
            insertbackground="#EDEDED",
            font=("Segoe UI Emoji", 10)
        )
        self.output.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.output.tag_config("user", foreground="#A5D6A7")
        self.output.tag_config("tool", foreground="#4AA3FF")
        self.output.tag_config("thinking", foreground="#9E9E9E")
        self.output.tag_config("final", foreground="#EDEDED")
        self.output.tag_config("error", foreground="#FF5252")
        self.output.tag_config("debug", foreground="#FF7E43")
        self.output.insert(tk.END, "🤖RITA: Hello! How can I assist you today?\n", "final")
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttkb.Label(self, textvariable=self.status_var, anchor=tk.W, bootstyle="secondary")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)
        
        # Prompt entry
        prompt_row = ttkb.Frame(self)
        prompt_row.pack(fill=tk.X, padx=10, pady=(10, 4))

        self.prompt_entry = ttkb.Entry(prompt_row, width=70, bootstyle="secondary")
        self.prompt_entry.pack(side=tk.LEFT, padx=(0, 10), ipady=8)
        self.prompt_entry.bind("<Return>", self.handle_prompt)
        self.prompt_entry.bind("<Button-3>", self._show_prompt_history)
        
        self.settings_button = ttkb.Button(prompt_row, text="Settings", command=self.open_settings, bootstyle="info-outline")
        self.settings_button.pack(side=tk.LEFT)
        
        action_row = ttkb.Frame(self)
        action_row.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.send_button = ttkb.Button(action_row, text="Send", command=self.handle_prompt, bootstyle="primary")
        self.send_button.pack(side=tk.LEFT, padx=(0, 6))

        self.new_chat_button = ttkb.Button(action_row, text="New Chat", command=self.new_chat, bootstyle="secondary")
        self.new_chat_button.pack(side=tk.LEFT, padx=(0, 6))

    def _enable_windows_dark_titlebar(self):
        """Enable dark native title bar on supported Windows versions."""
        if os.name != "nt":
            return
        
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            dark_mode = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(DWMWA_USE_IMMERSIVE_DARK_MODE),
                ctypes.byref(dark_mode),
                ctypes.sizeof(dark_mode),
            )
        except Exception:
            pass

    def _debug_log(self, text: str, turn_id: int | None = None):
        """Append debug logs only when DEBUG mode is enabled."""
        if not self.debug_mode_var.get():
            return
        tag = "debug" if turn_id is None else ("debug", f"process_{turn_id}")
        self._append_output(f"{text}\n", tag)

    def new_chat(self):
        """Start a fresh chat session by clearing memory and UI output."""
        self.conversation_history = []
        self.prompt_history.clear()
        self.output.delete("1.0", tk.END)
        self._append_output("🧹 Started a new chat session.\n", "debug")

    def _show_prompt_history(self, event):
        """Show latest prompts on right-click."""
        if not self.prompt_history:
            return

        menu = tk.Menu(self, tearoff=0)
        for prompt in reversed(self.prompt_history):
            display_text = prompt[:80] + "..." if len(prompt) > 80 else prompt
            menu.add_command(
                label=display_text,
                command=lambda p=prompt: self._reissue_prompt(p)
            )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _reissue_prompt(self, prompt: str):
        """Put a prompt from history back into the input box."""
        self.prompt_entry.delete(0, tk.END)
        self.prompt_entry.insert(0, prompt)
        self.prompt_entry.icursor(tk.END)
        self.prompt_entry.focus_set()

    def open_settings(self):
        settings_window = ttkb.Toplevel(self)
        settings_window.title("settings")
        settings_window.geometry("160x230")
        settings_window.resizable(False, False)

        container = ttkb.Frame(settings_window)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ttkb.Label(container, text="Model", bootstyle="inverse-secondary").pack(anchor=tk.W)
        model_combo = ttkb.Combobox(
            container,
            textvariable=self.model_var,
            values=self.model_options,
            state="readonly",
            width=30,
        )
        model_combo.pack(fill=tk.X, pady=(4, 10))

        ttkb.Checkbutton(container, text="Show Think", variable=self.show_think_var, bootstyle="round-toggle").pack(anchor=tk.W)
        ttkb.Checkbutton(container, text="Show Tool use", variable=self.show_tool_use_var, bootstyle="round-toggle").pack(anchor=tk.W)
        ttkb.Checkbutton(container, text="DEBUG mode", variable=self.debug_mode_var, bootstyle="round-toggle").pack(anchor=tk.W)
        ttkb.Checkbutton(container, text="Clear process", variable=self.clear_process_var, bootstyle="round-toggle").pack(anchor=tk.W)

        ttkb.Button(container, text="Save & Quit", command=settings_window.destroy, bootstyle="primary").pack(side=tk.BOTTOM, pady=(18, 0))

    def _clear_process_output(self, turn_id: int):
        process_tag = f"process_{turn_id}"

        def _do_clear():
            ranges = list(self.output.tag_ranges(process_tag))
            for i in range(len(ranges) - 1, 0, -2):
                start = ranges[i - 1]
                end = ranges[i]
                self.output.delete(start, end)
        self.after(0, _do_clear)

    def _append_output(self, text: str, tag: str | tuple[str, ...] | None = None):
        """"Append text to the output area with an optional tag for styling."""
        def _do_append():
            if tag:
                self.output.insert(tk.END, text, tag)
            else:
                self.output.insert(tk.END, text)
            self.output.see(tk.END)
        self.after(0, _do_append)

    def _set_processing_ui(self, is_processing: bool):
        """"Enable or disable the prompt entry and send button, and update the status bar."""
        def _do_set():
            state = tk.DISABLED if is_processing else tk.NORMAL
            self.prompt_entry.configure(state=state)
            self.send_button.configure(state=state)
            self.new_chat_button.configure(state=state)
            self.settings_button.configure(state=state)
            self.status_var.set("Processing..." if is_processing else "Ready")
        self.after(0, _do_set)

    @staticmethod
    def _message_content_text(message) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, list):
            return "\n".join(str(part) for part in content)
        return str(content or "")

    def _stream_final_answer(self, text: str):
        if not text:
            return
        self._append_output("\n🤖RITA: ", "final")
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            self._append_output(word + suffix, "final")
            time.sleep(0.02)
        self._append_output("\n-------------------------------------------\n", "final")

    @staticmethod
    def _extract_think_blocks(text: str) -> tuple[list[str], str]:
        if not text:
            return [], ""
        
        think_parts = []
        
        # Find the last </think> tag position
        last_closing = None
        for match in re.finditer(r"</think>", text, re.IGNORECASE):
            last_closing = match.end()
        
        if last_closing is not None:
            # Everything before and including the last </think> is thinking content
            thinking_content = text[:last_closing].strip()
            final_content = text[last_closing:].strip()
            
            # Extract all complete <think>...</think> pairs from thinking content
            pattern = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
            think_matches = [match.strip() for match in pattern.findall(thinking_content) if match.strip()]
            
            # Also capture any content before first <think> or after last </think> within thinking section
            cleaned_thinking = pattern.sub("", thinking_content).strip()
            cleaned_thinking = re.sub(r"</?think>", "", cleaned_thinking, flags=re.IGNORECASE).strip()
            
            if think_matches:
                think_parts.extend(think_matches)
            if cleaned_thinking:
                think_parts.append(cleaned_thinking)
            
            # Clean up any remaining think tags in final content
            final_content = re.sub(r"</?think>", "", final_content, flags=re.IGNORECASE).strip()
            
            return think_parts, final_content
        else:
            # No </think> tag found, check if there are any think tags at all
            if re.search(r"<think>", text, re.IGNORECASE):
                # Has opening tag but no closing, treat everything before opening as potential answer
                opening_match = re.search(r"<think>", text, re.IGNORECASE)
                final_content = text[:opening_match.start()].strip()
                thinking_content = text[opening_match.start():].strip()
                thinking_content = re.sub(r"</?think>", "", thinking_content, flags=re.IGNORECASE).strip()
                
                if thinking_content:
                    think_parts.append(thinking_content)
                
                return think_parts, final_content
            else:
                # No think tags at all, everything is final content
                return [], text

    def _run_agent_stream(self, prompt: str, turn_id: int, model_name: str):
        final_message_text = ""
        seen_count = 0
        process_tag = f"process_{turn_id}"
        job_uuid = uuid4().hex[:8]
        last_follow_up_uuid = None
        waiting_follow_up_response = False

        self._debug_log(f"  [Job #{turn_id} UUID: {job_uuid}...] Submitted", turn_id)

        if self.show_think_var.get():
            self._append_output("💭 Thinking...\n", ("thinking", process_tag))

        try:
            input_messages = list(self.conversation_history) + [HumanMessage(content=prompt)]
            seen_count = len(input_messages)
            final_state = None
            for state in agent.stream({'messages': input_messages, 'model': model_name}, stream_mode="values"):
                final_state = state
                messages = state.get("messages", []) if isinstance(state, dict) else []
                self._debug_log(f"[DEBUG] {messages}") 
                new_messages = messages[seen_count:]

                for message in new_messages:
                    if isinstance(message, AIMessage):
                        self._debug_log(f"[Job #{turn_id}] Response received", turn_id)
                        ai_text = self._message_content_text(message)
                        tool_calls = getattr(message, "tool_calls", None) or []

                        if tool_calls:
                            self._debug_log(f"[Job #{turn_id}] Executing {len(tool_calls)} tool call(s)...", turn_id)
                            for tc in tool_calls:
                                self._debug_log(
                                    f"  Calling: {tc.get('name', 'unknown_tool')}({tc.get('args', {})})",
                                    turn_id,
                                )
                                if self.show_tool_use_var.get():
                                    name = tc.get("name", "unknown_tool")
                                    args = tc.get("args", {})
                                    self._append_output(f"🔧 Tool call: {name}({args})\n", ("tool", process_tag))
                            if ai_text and self.show_tool_use_var.get():
                                self._append_output(f"🤖RITA: {ai_text}\n", ("tool", process_tag))

                            self._debug_log(f"[Job #{turn_id}] Submitting follow-up request...", turn_id)
                            last_follow_up_uuid = uuid4().hex[:8]
                            self._debug_log(
                                f"[Job #{turn_id}] Follow-up submitted (UUID: {last_follow_up_uuid}...)",
                                turn_id,
                            )
                            waiting_follow_up_response = True
                        else:
                            final_message_text = ai_text
                            if waiting_follow_up_response:
                                waiting_follow_up_response = False

                    elif isinstance(message, ToolMessage):
                        self._debug_log(
                            f"  Result: {self._message_content_text(message)}",
                            turn_id,
                        )
                        if self.show_tool_use_var.get():
                            tool_result = self._message_content_text(message)
                            self._append_output(f"🛠️ Tool result: {tool_result}\n", ("tool", process_tag))

                seen_count = len(messages)

            if isinstance(final_state, dict):
                result_messages = final_state.get("messages", [])
                if isinstance(result_messages, list):
                    self.conversation_history = result_messages

            if final_message_text:
                think_parts, clean_final = self._extract_think_blocks(final_message_text)
                if self.show_think_var.get():
                    for thought in think_parts:
                        self._append_output(f"💭 {thought}\n", ("thinking", process_tag))
                if clean_final:
                    self._stream_final_answer(clean_final)
                else:
                    self._append_output("🤖RITA: No final assistant response [0]\n", "error")
            else:
                self._append_output("🤖RITA: No final assistant response\n", "error")

            if self.clear_process_var.get():
                self._clear_process_output(turn_id)

        except Exception as exc:
            self._append_output(f"Error: {exc}\n", "error")
            self._debug_log(f"*** ERROR in Job #{turn_id} ***", turn_id)
            self._debug_log(f"Error: {exc}", turn_id)
        finally:
            self._set_processing_ui(False)

    def handle_prompt(self, event=None):
        prompt = self.prompt_entry.get()
        if prompt.strip() == "":
            return

        if prompt not in self.prompt_history:
            self.prompt_history.append(prompt)

        self.turn_counter += 1
        current_turn_id = self.turn_counter
        selected_model = self.model_var.get().strip() or "qwen3:1.7b"

        self._append_output(f"\n👨User: {prompt}\n", "user")
        self.prompt_entry.delete(0, tk.END)

        self._debug_log(f"Model: {selected_model}", current_turn_id)

        self._set_processing_ui(True)
        threading.Thread(
            target=self._run_agent_stream,
            args=(prompt, current_turn_id, selected_model),
            daemon=True,
        ).start()
    

if __name__ == "__main__":
    app = RITA_GUI()
    app.mainloop()
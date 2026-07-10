"""Native skills for interacting with the persistent PTY terminal."""

from __future__ import annotations

import queue
import time
from typing import Callable

from justllama.server.skills.base import AgentSkill
from justllama.server.terminal_manager import terminal_manager


class TerminalRunCommand(AgentSkill):
    """Skill that runs a command in the persistent terminal and waits for it to complete."""

    skill_id = "terminal_run_command"
    # Tell the SkillsManager executor to allow up to 120 seconds.
    timeout = 120

    def get_name(self) -> str:
        return "Terminal Run Command"

    def get_description(self) -> str:
        return (
            "Run a command in the persistent shell session and wait for its completion. "
            "Returns stdout, stderr, and the command's exit code. "
            "Use this tool for non-blocking commands. If the command waits for input "
            "or hangs, it will time out, but output accumulated so far is returned. "
            "You can then use terminal_send_keys to respond or interact."
        )

    def get_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "terminal_run_command",
                "description": self.get_description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Command to execute (e.g. 'ls -la', 'npm run build').",
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Maximum seconds to wait for execution. Defaults to 30.0.",
                            "default": 30.0,
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    def execute(
        self,
        args: dict,
        cancel_check: Callable[[], bool] | None = None,
    ) -> str:
        command = args.get("command", "")
        timeout_arg = args.get("timeout", 30.0)
        try:
            timeout = float(timeout_arg)
        except (ValueError, TypeError):
            timeout = 30.0

        if not command or not isinstance(command, str):
            return "Error: 'command' argument is required and must be a string."

        # Ensure session is active
        terminal_manager.start_session()

        q: queue.Queue[str] = queue.Queue()
        terminal_manager.register_queue(q)

        # Drain leftover data in queue
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break

        # Suffix command to echo exit code when finished
        sentinel = f"__JL_DONE_{time.time()}__"
        full_command = f"{command}\n_ec=$?; echo \"\"; echo \"{sentinel}:$_ec\"\n"

        terminal_manager.send_keys(full_command)

        output: list[str] = []
        start_time = time.time()
        done = False
        exit_code = "unknown"

        while time.time() - start_time < timeout:
            if cancel_check and cancel_check():
                output.append("\n[Command execution cancelled by user]")
                break
            try:
                # Wait for data chunk with small timeout to check loop condition
                chunk = q.get(timeout=0.2)
                output.append(chunk)
                merged = "".join(output)
                if sentinel in merged:
                    parts = merged.split(sentinel + ":")
                    if len(parts) > 1:
                        for part in parts[1:]:
                            code_part = part.split("\r\n")[0].strip()
                            code_part = code_part.split("\n")[0].strip()
                            if code_part.isdigit():
                                exit_code = code_part
                                done = True
                                break
                        if done:
                            break
            except queue.Empty:
                continue

        terminal_manager.unregister_queue(q)
        merged_out = "".join(output)

        # Truncate the echoed control commands and sentinel from the output
        if sentinel in merged_out:
            merged_out = merged_out.split(sentinel)[0].rstrip("\r\n")

        if done:
            return f"Command completed with exit code {exit_code}.\nOutput:\n{merged_out}"
        else:
            return (
                f"Command timed out or is still running (timeout={timeout}s).\n"
                f"Output so far:\n{merged_out}\n\n"
                "If it is waiting for user input, use terminal_send_keys to respond."
            )


class TerminalSendKeys(AgentSkill):
    """Skill that sends raw keys to the persistent terminal and reads responses."""

    skill_id = "terminal_send_keys"
    timeout = 30

    def get_name(self) -> str:
        return "Terminal Send Keys"

    def get_description(self) -> str:
        return (
            "Send raw keys/input to the persistent terminal. "
            "Use this to answer interactive prompts (e.g. typing 'y\\n') "
            "or sending control characters (e.g. '\\x03' for Ctrl+C). "
            "Returns any new output produced in the terminal within 2 seconds."
        )

    def get_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "terminal_send_keys",
                "description": self.get_description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "string",
                            "description": "Characters to write to the PTY stdin.",
                        }
                    },
                    "required": ["keys"],
                },
            },
        }

    def execute(
        self,
        args: dict,
        cancel_check: Callable[[], bool] | None = None,
    ) -> str:
        keys = args.get("keys")
        if not isinstance(keys, str):
            return "Error: 'keys' argument is required and must be a string."

        terminal_manager.start_session()

        q: queue.Queue[str] = queue.Queue()
        terminal_manager.register_queue(q)

        # Drain
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break

        terminal_manager.send_keys(keys)

        # Collect output for a short 2.0 second window
        output: list[str] = []
        start_time = time.time()
        while time.time() - start_time < 2.0:
            if cancel_check and cancel_check():
                break
            try:
                chunk = q.get(timeout=0.1)
                output.append(chunk)
            except queue.Empty:
                continue

        terminal_manager.unregister_queue(q)
        merged_out = "".join(output)

        return f"Keys sent. New terminal output:\n{merged_out}"

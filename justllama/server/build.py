"""BuildManager — file operations for Build mode, exposed to QML."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, Slot


class BuildManager(QObject):
    """File operations for Build mode — exposed to QML as buildManager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._work_dir = Path.cwd()  # default; can be overridden

    @Slot(str, result=str)
    def read_file(self, path: str) -> str:
        """Read a file and return contents, or error message prefixed with 'ERROR:'."""
        try:
            p = Path(path)
            if not p.is_file():
                return f"ERROR: File not found: {path}"
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return f"ERROR: {e}"

    @Slot(str, str, result=str)
    def write_file(self, path: str, content: str) -> str:
        """Create or overwrite a file. Returns 'OK' or 'ERROR: ...'."""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return "OK"
        except Exception as e:
            return f"ERROR: {e}"

    @Slot(str, str, str, result=str)
    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """Find-and-replace in a file. Returns 'OK', 'ERROR: ...', or 'NOT_FOUND'."""
        try:
            p = Path(path)
            if not p.is_file():
                return f"ERROR: File not found: {path}"
            content = p.read_text(encoding="utf-8")
            if old_text not in content:
                return "NOT_FOUND"
            content = content.replace(old_text, new_text, 1)
            p.write_text(content, encoding="utf-8")
            return "OK"
        except Exception as e:
            return f"ERROR: {e}"

    @Slot(str, result=str)
    def run_command(self, command: str) -> str:
        """Run a shell command in work_dir. Returns stdout+stderr or error."""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=60, cwd=str(self._work_dir)
            )
            output = result.stdout
            if result.stderr:
                output += "\n--- stderr ---\n" + result.stderr
            output += f"\n--- exit code: {result.returncode} ---"
            return output
        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out after 60s"
        except Exception as e:
            return f"ERROR: {e}"

    @Slot(str, result=str)
    def list_directory(self, path: str) -> str:
        """List a directory. Returns JSON array of names or error."""
        try:
            p = Path(path)
            if not p.is_dir():
                return f"ERROR: Directory not found: {path}"
            items = [str(e) for e in p.iterdir()]
            return json.dumps(items)
        except Exception as e:
            return f"ERROR: {e}"

    @Slot(str)
    def set_work_dir(self, path: str):
        self._work_dir = Path(path).resolve()

    @Slot(str, result=str)
    def apply_operation(self, op_json: str) -> str:
        """Parse and execute a single BUILD_OP JSON object."""
        try:
            op = json.loads(op_json)
            op_type = op.get("op")
            if op_type == "write":
                return self.write_file(op["path"], op["content"])
            elif op_type == "edit":
                return self.edit_file(op["path"], op["old"], op["new"])
            elif op_type == "read":
                return self.read_file(op["path"])
            elif op_type == "run":
                return self.run_command(op["command"])
            else:
                return f"ERROR: Unknown operation type: {op_type}"
        except json.JSONDecodeError:
            return "ERROR: Invalid JSON"
        except Exception as e:
            return f"ERROR: {e}"

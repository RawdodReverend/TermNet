import asyncio
import os
import time
import contextlib
from typing import List, Tuple, Dict, Any
from termnet.safety import SafetyChecker
from termnet.config import CONFIG

class TerminalSession:
    def __init__(self):
        self._command_history: List[Tuple[str, str, float, int]] = []
        self._last_command = ""
        self._last_exit_code = 0
        self.cwd = os.getcwd()

    async def start(self) -> bool:
        return True

    async def stop(self):
        return

    async def execute_command(self, command: str, timeout: int = CONFIG["COMMAND_TIMEOUT"]) -> Tuple[str, int, bool]:
        command = command.strip()
        if not command:
            return "", 0, True

        # Handle cd manually
        if command.startswith("cd"):
            parts = command.split(maxsplit=1)
            path = os.path.expanduser(parts[1].strip()) if len(parts) > 1 else os.path.expanduser("~")
            try:
                new_cwd = os.path.abspath(os.path.join(self.cwd, path)) if not os.path.isabs(path) else path
                os.chdir(new_cwd)
                self.cwd = new_cwd
                return "", 0, True
            except Exception as e:
                return f"❌ cd: {e}", 1, False

        is_safe, warn = SafetyChecker.is_safe(command)
        if not is_safe:
            return f"❌ Command blocked: {warn}", 1, False

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        full_out, full_err = [], []
        async def _pump(stream, sink: List[str]):
            while True:
                chunk = await stream.readline()
                if not chunk: break
                sink.append(chunk.decode(errors="replace"))

        pump_out = asyncio.create_task(_pump(proc.stdout, full_out))
        pump_err = asyncio.create_task(_pump(proc.stderr, full_err))

        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            return "❌ Command timed out", 124, False
        finally:
            await asyncio.gather(pump_out, pump_err, return_exceptions=True)

        code = proc.returncode or 0
        output = "".join(full_out + full_err) or f"[Executed: {command}]"

        return output, code, code == 0

    def get_context_info(self) -> Dict[str, Any]:
        return {
            "current_directory": self.cwd,
            "last_command": self._last_command,
            "last_exit_code": self._last_exit_code,
            "command_count": len(self._command_history),
            "recent_commands": [c for c, _, _, _ in self._command_history[-3:]]
        }

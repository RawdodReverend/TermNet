#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import signal
import threading
from pathlib import Path

# Ports TermNet uses
PORTS = [876, 8765, 5003, 5005]

class TermNetLauncher:
    def __init__(self):
        self.root_dir = Path(__file__).parent.absolute()
        self.backend_process = None
        self.extension_processes = []
        self.ui_process = None

    def cleanup(self, signum=None, frame=None):
        """Clean up all processes"""
        print("\nShutting down TermNet...")

        if self.ui_process and hasattr(self.ui_process, "poll") and self.ui_process.poll() is None:
            self.ui_process.terminate()

        if self.backend_process and self.backend_process.poll() is None:
            self.backend_process.terminate()

        for proc in self.extension_processes:
            if proc.poll() is None:
                proc.terminate()

        time.sleep(1)

        if self.ui_process and hasattr(self.ui_process, "poll") and self.ui_process.poll() is None:
            self.ui_process.kill()
        if self.backend_process and self.backend_process.poll() is None:
            self.backend_process.kill()
        for proc in self.extension_processes:
            if proc.poll() is None:
                proc.kill()

        sys.exit(0)

    def free_ports(self):
        """Kill any process already listening on TermNet ports"""
        try:
            subprocess.run(
                ["bash", "-c",
                 f"sudo lsof -t -iTCP:{','.join(map(str, PORTS))} -sTCP:LISTEN | xargs -r sudo kill -9"],
                check=False
            )
        except Exception as e:
            print(f"Warning: could not auto-kill old processes: {e}")

    def start_backend(self):
        """Start the main backend"""
        backend_dir = self.root_dir / "backend"
        if not backend_dir.exists():
            print(f"Error: Backend directory not found: {backend_dir}")
            return False

        print("Starting TermNet backend...")
        try:
            # show logs instead of swallowing them
            self.backend_process = subprocess.Popen(
                [sys.executable, "-m", "termnet.main"],
                cwd=backend_dir
            )
            return True
        except Exception as e:
            print(f"Error starting backend: {e}")
            return False

    def start_extensions(self):
        """Start all extensions in the extensions folder"""
        extensions_dir = self.root_dir / "backend" / "extensions"
        if not extensions_dir.exists():
            print("Extensions directory not found, skipping...")
            return

        print("Starting extensions...")

        for item in extensions_dir.iterdir():
            if item.is_dir():
                for py_file in item.glob("*.py"):
                    try:
                        proc = subprocess.Popen(
                            [sys.executable, py_file.name],
                            cwd=item
                        )
                        self.extension_processes.append(proc)
                        print(f"Started extension: {item.name}/{py_file.name}")
                        break
                    except Exception as e:
                        print(f"Error starting extension {item.name}: {e}")

            elif item.is_file() and item.suffix == ".py":
                try:
                    proc = subprocess.Popen(
                        [sys.executable, item.name],
                        cwd=extensions_dir
                    )
                    self.extension_processes.append(proc)
                    print(f"Started extension: {item.name}")
                except Exception as e:
                    print(f"Error starting extension {item.name}: {e}")

    def start_web_ui(self):
        webui_dir = self.root_dir / "ui" / "webserver"
        if not webui_dir.exists():
            print(f"Error: Web UI directory not found: {webui_dir}")
            return False

        print("Starting Web UI...")

        try:
            self.ui_process = subprocess.Popen(
                [sys.executable, "web_ui_server.py"],
                cwd=webui_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
        except Exception as e:
            print(f"Error starting web UI: {e}")
            return False

        def open_browser_when_ready():
            print("Waiting for web UI to be ready...")
            for line in iter(self.ui_process.stdout.readline, ""):
                if not line:
                    break
                print(line.strip())
                if any(msg in line for msg in [
                    "Running on", "127.0.0.1:5005", "0.0.0.0:5005",
                    "Password set", "Server starting"
                ]):
                    print("Web UI is ready! Opening browser...")
                    time.sleep(1)
                    try:
                        if sys.platform == "darwin":
                            subprocess.run(["open", "http://127.0.0.1:5005"], check=False)
                        elif sys.platform == "win32":
                            subprocess.run(["start", "http://127.0.0.1:5005"], shell=True, check=False)
                        else:
                            subprocess.run(["xdg-open", "http://127.0.0.1:5005"], check=False)
                    except Exception as e:
                        print(f"Note: Could not open browser automatically: {e}")
                        print("Please open http://127.0.0.1:5005 in your browser")
                    break

        threading.Thread(target=open_browser_when_ready, daemon=True).start()
        return True

    def start_terminal_ui(self):
        terminal_dir = self.root_dir / "ui" / "terminal"
        if not terminal_dir.exists():
            print(f"Error: Terminal UI directory not found: {terminal_dir}")
            return False

        print("Starting Terminal UI...")
        print("=" * 50)

        try:
            self.ui_process = subprocess.Popen(
                [sys.executable, "terminal_ui.py"],
                cwd=terminal_dir
            )
            self.ui_process.wait()
            return True
        except Exception as e:
            print(f"Error starting terminal UI: {e}")
            return False

    def run(self):
        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)

        print("TermNet Launcher")
        print("=" * 20)

        while True:
            print("\nSelect frontend:")
            print("1) Web UI (opens browser after password setup)")
            print("2) Terminal UI")
            choice = input("Enter choice (1 or 2): ").strip()
            if choice in ["1", "2"]:
                break
            print("Invalid choice. Please try again.")

        # Free ports before launching
        self.free_ports()

        if not self.start_backend():
            print("Failed to start backend. Exiting.")
            return

        time.sleep(2)
        self.start_extensions()
        time.sleep(1)

        if choice == "1":
            if not self.start_web_ui():
                self.cleanup()
                return
            print("Please set a password:")
            try:
                self.ui_process.wait()
            except KeyboardInterrupt:
                self.cleanup()
        else:
            if not self.start_terminal_ui():
                self.cleanup()
                return

        self.cleanup()


if __name__ == "__main__":
    launcher = TermNetLauncher()
    launcher.run()

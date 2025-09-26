# TermNet

TermNet is an **AI-powered terminal assistant** that connects a Large Language Model (LLM) with shell command execution, browser search, and dynamically loaded tools.  
It streams responses in real-time, executes tools one at a time, and maintains conversational memory across steps.

⚠️ **Disclaimer:** This project is experimental. **Use at your own risk.**

⚠️ **Note:** This has only been tested with GPT-OSS Models. **Your models may behave differently.**

---

## ✨ Features
- 🖥️ **Terminal integration**  
Safely execute shell commands with sandboxed handling, timeout control, and built-in safety filters
- 🔧 **Dynamic tool loading**  
Extend functionality by editing `toolregistry.json` - tools auto-discover without code changes
- 🌐 **Browser automation**  
Playwright-powered web browsing, form filling, and content extraction
- 📡 **WebSocket architecture**  
Real-time communication between components with streaming responses
- 🧠 **Memory system**  
Tracks planning, actions, observations, and reflections across multiple steps
- ⚡ **Streaming LLM output**  
Integrates with Ollama for real-time chat responses
- 🛡️ **Safety layer**  
Blocks dangerous commands while allowing risky ones with warnings
- 📱 **Dual interface**  
Web UI and Terminal UI options
- 🔔 **Notification system**  
Standalone notification server for alerts and reminders
- 💾 **Scratchpad memory**  
Persistent note-taking across sessions

## 🌐 Architecture
TermNet uses a **multi-server architecture**:

- **Main WebSocket Server** (`main.py`) - Port 876: Handles agent communication and streaming
- **Browser WebSocket Server** (`browser_server.py`) - Port 8765: Manages Playwright browser automation
- **Notification HTTP Server** (`notification_server.py`) - Port 5003: Handles notifications and alerts
- **Web UI Server** (`web_ui_server.py`) - Port 5005: Browser-based interface

All servers are managed by the central launcher (`run.py`).
## 📂 Project Structure
**Root Files:**
- `run.py - Main launcher script`
- `requirements.txt - Python dependencies`
- `README.md - This file`

**Backend Core:**
- `main.py - WebSocket server entry point`
- `agent.py - TermNetAgent core logic`
- `memory.py - Memory step tracking`
- `safety.py - Command safety checker`
- `toolloader.py - Dynamic tool loader`
- `config.py - Configuration management`

**Tools:**
- `browser_search_websocket.py - Web browsing tool`
- `notification_tool.py - Notification management`
- `communication_tools.py - Email/SMS capabilities`
- `scratchpad.py - Note-taking tool`
- `terminal.py - Terminal session wrapper`

**Servers:**
- `browser_server.py - Browser automation server`
- `notification_server.py - Notification server`

## ⚙️ Installation
### Requirements
- Python **3.9+**
- [Ollama](https://ollama.ai) running locally
- Chromium (installed automatically by Playwright)

### Setup
1. Clone the repository:
```bash
git clone https://github.com/RawdodReverend/TermNet.git
cd termnet
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Install Playwright browser:
```bash
playwright install chromium
```
4. Set up Ollama (if not already installed):
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```
## 🚀 Usage
### Using the Launcher (Recommended)
The `run.py` launcher manages all components:
```bash
python run.py
```
You'll be prompted to choose between:
- **Web UI** (Browser interface at http://127.0.0.1:5005)
- **Terminal UI** (Command-line interface)

### Direct Execution
For development or debugging, run components individually:
```bash
# Start the main WebSocket server
python main.py

# Start the browser server
python browser_server.py

# Start notification server
python notification_server.py
```
## ⚙️ Configuration
| Key | Description | Default |
|-----|-------------|---------|
| ``OLLAMA_URL`` | Base URL for Ollama server | `http://127.0.0.1:11434` |
| ``MODEL_NAME`` | Model name/tag to use | `gpt-oss:20b` |
| ``LLM_TEMPERATURE`` | Response randomness (0-1) | `0.7` |
| ``MAX_AI_STEPS`` | Max reasoning steps per query | `10` |
| ``COMMAND_TIMEOUT`` | Max seconds for terminal commands | `30` |
| ``STREAM_CHUNK_DELAY`` | Delay between LLM output chunks | `0.01` |
## 🛠️ Adding Tools
Tools are defined in `toolregistry.json` and implemented in Python modules.
### 1. Register the Tool
Add an entry to `toolregistry.json`:
```json
{
  "type": "function",
  "function": {
    "name": "my_custom_tool",
    "description": "Describe what this tool does",
    "module": "mytool",
    "class": "MyTool",
    "parameters": {
      "type": "object",
      "properties": {
        "arg1": { "type": "string" }
      },
      "required": ["arg1"]
    }
  }
}
```
### 2. Implement the Tool
Create `termnet/tools/mytool.py`:
```python
import asyncio

class MyTool:
    async def my_custom_tool(self, arg1: str):
        """Tool description"""
        return f"Tool executed with arg1={arg1}"
        
    # Optional: Async context management
    async def start(self):
        return True
        
    async def stop(self):
        pass
```
### 3. Restart TermNet
The tool will auto-load at startup. No code changes needed!
## ⚠️ Safety Notes
- Dangerous commands (`rm -rf /`, `shutdown`, etc.) are **blocked**
- Risky commands (`rm`, `mv`, `chmod`) are **allowed with warnings**
- Always review agent suggestions before execution
- Use in isolated environments when testing new tools
- Monitor tool execution and set appropriate timeouts
## 🔌 API Reference
### Core Components
- **`TermNetAgent`**: Main agent class managing chat loop and tool execution
- **`TerminalSession`**: Wrapper for safe command execution with timeout control
- **`ToolLoader`**: Dynamic tool importer based on registry
- **`SafetyChecker`**: Command safety validation system
- **`BrowserSearchTool`**: Web browsing and content extraction
- **`NotificationTool`**: Notification management system
## 📦 Dependencies
Core dependencies:
- `websockets>=12.0`
- `playwright>=1.40.0`
- `beautifulsoup4>=4.12.0`
- `playwright-stealth>=1.0.0`
- `flask>=2.3.0`
- `aiohttp>=3.9.0`
- `lxml>=4.9.0`
- `html5lib>=1.1`
- `soupsieve>=2.5`

## 🐛 Troubleshooting
- ****Browser won't start****: Run `playwright install chromium` and check if Chrome is installed
- ****Ollama connection refused****: Ensure Ollama is running: `ollama serve`
- ****Port already in use****: Change ports in respective server files or kill existing processes
- ****Tool not loading****: Check `toolregistry.json` syntax and Python module paths
- ****Web UI not accessible****: Check firewall settings and ensure port 5005 is open
## 📜 License
This project is licensed under the MIT License.  

See LICENSE file for details.

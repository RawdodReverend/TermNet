import sys
import json
import time
import hashlib
import aiohttp
import asyncio
from typing import Dict, List, Tuple

from termnet.config import CONFIG
from termnet.toolloader import ToolLoader


class TermNetAgent:
    def __init__(self, terminal, notification_server_url: str = "http://localhost:5003"):
        self.terminal = terminal
        self.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self.cache: Dict[str, Tuple[float, str, int, bool]] = {}
        self.current_goal = ""
        self.last_activity = time.time()
        self.notification_check_interval = 300  # 5 minutes

        self.notification_server_url = notification_server_url
        self.notifications: List[Dict] = []  # cache of latest notifications

        # 🔌 Load tools dynamically
        self.tool_loader = ToolLoader()
        self.tool_loader.load_tools()

        # Conversation history with initial system message
        self.conversation_history: List[Dict[str, str]] = [
            {"role": "system", "content": self._get_system_prompt()}
        ]

        # Start background refresh for notifications
        self.notification_task = asyncio.create_task(self._auto_refresh_prompt())

    # -----------------------------
    # SYSTEM PROMPT
    # -----------------------------
    def _get_system_prompt_base(self) -> str:
        return """
You are TermNet, a smart, goal-driven assistant with access to powerful tools.

You operate through conversation, but you can call external tools to collect data, perform actions, or solve tasks more effectively.

🧠 BEHAVIOR RULES:
- Think step-by-step before responding. Consider whether a tool is needed.
- If a tool can help, CALL IT FIRST before saying anything to the user.
- Never fabricate results. Always wait for tool output before using its information.
- After using a tool, reassess the goal and decide the next step.
- Call multiple tools if necessary. Chain steps logically.
- Only respond to the user when you have useful or complete information.

🧰 TOOL USAGE:
- You have access to tools like: `browser_search`, `click_link`, `terminal_execute`, etc. Use them strategically.
- Tool arguments must be accurate and relevant. Use structured reasoning to prepare them.
- If a tool fails, recover gracefully and try another approach.

💬 COMMUNICATION STYLE:
- Be concise, clear, and confident.
- Summarize tool output naturally – don't dump raw data.
- When the task is complete, explain what was done and any next steps or outcomes.
- Avoid unnecessary filler or repetition.

⚠️ REMEMBER:
- Tools come first. Don't respond prematurely.
- You are here to **solve problems**, not just chat.
- Every message should move the task forward.
"""

    def _get_system_prompt(self) -> str:
        notif_text = "No active notifications."
        if self.notifications:
            notif_text = "\n".join(
                f"{idx+1}. {n.get('title', 'Untitled')} - {n.get('message', '')}"
                for idx, n in enumerate(self.notifications)
            )
        return self._get_system_prompt_base() + "\n\n🔌 Active Notifications:\n" + notif_text

    # -----------------------------
    # TOOL EXECUTION
    # -----------------------------
    def _get_tool_definitions(self):
        return self.tool_loader.get_tool_definitions()

    async def _execute_tool(self, tool_name: str, args: dict, reasoning: str) -> str:
        print(f"\n🛠️ Executing tool: {tool_name}")
        print(f"Args: {args}")

        tool_instance = self.tool_loader.get_tool_instance(tool_name)
        if not tool_instance:
            obs = f"❌ Tool {tool_name} not found"
            self.conversation_history.append(
                {"role": "tool", "name": tool_name, "content": obs}
            )
            return obs

        try:
            if tool_name == "terminal_execute":
                method = getattr(tool_instance, "execute_command", None)
            else:
                method_name = tool_name.split("_", 1)[-1]
                method = getattr(tool_instance, method_name, None)

            if not method:
                obs = f"❌ Tool {tool_name} has no valid method"
            elif asyncio.iscoroutinefunction(method):
                obs = await method(**args)
            else:
                obs = method(**args)
        except Exception as e:
            obs = f"❌ Tool execution error: {e}"
            print(f"❌ Tool execution error: {e}")

        # ✅ Feed result back into conversation
        self.conversation_history.append(
            {"role": "tool", "name": tool_name, "content": str(obs)}
        )
        return str(obs)

    # -----------------------------
    # LLM STREAMING
    # -----------------------------
    async def _llm_chat_stream(self, tools: List[Dict]):
        def get_llm_url_and_payload(conversation, tools):
            if CONFIG.get("PROVIDER") == "lmstudio":
                url = f"{CONFIG['LMSTUDIO_URL']}/v1/chat/completions"
                payload = {
                    "model": CONFIG["MODEL_NAME"],
                    "messages": conversation,
                    "temperature": CONFIG["LLM_TEMPERATURE"],
                    "max_tokens": 1000,
                }
                # Only add tools if we have them
                if tools:
                    payload["tools"] = tools
                    
            else:  # default = Ollama
                url = f"{CONFIG['OLLAMA_URL']}/api/chat"
                payload = {
                    "model": CONFIG["MODEL_NAME"],
                    "messages": conversation,
                    "tools": tools,
                    "stream": True,
                    "options": {"temperature": CONFIG["LLM_TEMPERATURE"]},
                }

            return url, payload

        # 🔌 Choose URL + payload depending on provider
        url, payload = get_llm_url_and_payload(self.conversation_history, tools)

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.post(url, json=payload) as r:
                if CONFIG.get("PROVIDER") == "lmstudio":
                    # LM Studio uses non-streaming for tool calls
                    response_data = await r.json()
                    
                    # Check if model wants to call tools
                    choice = response_data.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    
                    if message.get("tool_calls"):
                        yield ("TOOL", message["tool_calls"])
                    elif message.get("content"):
                        # For non-tool responses, we can stream
                        content = message["content"]
                        # Simulate streaming by yielding chunks
                        chunk_size = 20
                        for i in range(0, len(content), chunk_size):
                            chunk = content[i:i + chunk_size]
                            yield ("CONTENT", chunk)
                            await asyncio.sleep(0.02)  # Small delay to simulate streaming
                                
                else:  # Ollama
                    collected_message = {"content": "", "tool_calls": []}
                    
                    async for line in r.content:
                        if not line:
                            continue
                        try:
                            data = json.loads(line.decode())
                            
                            # Get the message from this chunk
                            msg = data.get("message", {})
                            
                            # Accumulate content
                            if "content" in msg and msg["content"]:
                                content_chunk = msg["content"]
                                collected_message["content"] += content_chunk
                                yield ("CONTENT", content_chunk)
                            
                            # Accumulate tool calls
                            if "tool_calls" in msg and msg["tool_calls"]:
                                if not collected_message["tool_calls"]:
                                    collected_message["tool_calls"] = msg["tool_calls"]
                                else:
                                    # Merge tool calls if needed
                                    collected_message["tool_calls"].extend(msg["tool_calls"])
                            
                            # Check if done
                            if data.get("done", False):
                                # If we have tool calls at the end, yield them
                                if collected_message["tool_calls"]:
                                    yield ("TOOL", collected_message["tool_calls"])
                                break
                                
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            print(f"Error processing Ollama response: {e}")
                            continue

    # -----------------------------
    # MAIN CHAT LOOP
    # -----------------------------
    async def chat(self, goal: str):
        self.last_activity = time.time()
        self.current_goal = goal

        # ✅ Always refresh system prompt before sending to LLM
        self.conversation_history[0]["content"] = self._get_system_prompt()

        self.conversation_history.append({"role": "user", "content": goal})
        tools = self._get_tool_definitions()

        # For LM Studio, we need to handle tool calling manually since it doesn't support function calling
        if CONFIG.get("PROVIDER") == "lmstudio":
            await self._handle_lmstudio_chat(tools)
        else:
            await self._handle_ollama_chat(tools)

    async def _handle_lmstudio_chat(self, tools):
        """Handle chat for LM Studio with OpenAI-style tool support"""
        for step in range(CONFIG["MAX_AI_STEPS"]):
            collected_text = ""
            tool_calls_made = False

            async for tag, chunk in self._llm_chat_stream(tools):
                if tag == "TOOL":
                    tool_calls = chunk
                    tool_calls_made = True
                    
                    # Add assistant message with tool calls to conversation
                    self.conversation_history.append({
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tool_call.get("id", f"call_{int(time.time())}"),
                                "type": tool_call.get("type", "function"),
                                "function": tool_call["function"]
                            }
                            for tool_call in tool_calls
                        ]
                    })
                    
                    # Execute each tool call
                    for tool_call in tool_calls:
                        fn = tool_call["function"]
                        name = fn["name"]
                        args_str = fn["arguments"]
                        
                        # Parse arguments
                        if isinstance(args_str, str):
                            try:
                                args = json.loads(args_str)
                            except Exception:
                                args = {}
                        else:
                            args = args_str or {}

                        # Execute tool
                        result = await self._execute_tool(name, args, "")
                        
                        # Add tool result to conversation
                        self.conversation_history.append({
                            "role": "tool",
                            "content": result,
                            "tool_call_id": tool_call.get("id", f"call_{int(time.time())}")
                        })
                    
                    break  # Break to get model's response to tool results

                elif tag == "CONTENT":
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                    collected_text += chunk
                    await asyncio.sleep(CONFIG["STREAM_CHUNK_DELAY"])

            # If we collected text without tool calls, we're done
            if collected_text.strip() and not tool_calls_made:
                self.conversation_history.append(
                    {"role": "assistant", "content": collected_text.strip()}
                )
                print()
                return
            
            # If we made tool calls, continue the loop to get the model's response
            if tool_calls_made:
                continue
                
        # If we've reached max steps, generate final response
        await self._generate_final_response()

    async def _handle_ollama_chat(self, tools):
        """Handle chat for Ollama with tool support"""
        for step in range(CONFIG["MAX_AI_STEPS"]):
            collected_text = ""
            tool_calls_made = False

            async for tag, chunk in self._llm_chat_stream(tools):
                if tag == "TOOL":
                    tool_calls = chunk
                    tool_calls_made = True
                    
                    # Process each tool call
                    for tool_call in tool_calls:
                        fn = tool_call.get("function", {})
                        name = fn.get("name", "")
                        args = fn.get("arguments", {})

                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}

                        await self._execute_tool(name, args, fn.get("reasoning", ""))
                    
                    break  # Break inner loop to continue with next step

                elif tag == "CONTENT":
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                    collected_text += chunk
                    await asyncio.sleep(CONFIG["STREAM_CHUNK_DELAY"])

            # If we collected text without tool calls, we're done
            if collected_text.strip() and not tool_calls_made:
                self.conversation_history.append(
                    {"role": "assistant", "content": collected_text.strip()}
                )
                print()
                return

            # If no tool calls and no content, something went wrong
            if not tool_calls_made and not collected_text.strip():
                print("\n⚠️ No response from model, ending conversation")
                return

        # Step limit reached → final response
        await self._generate_final_response()

    async def _generate_final_response(self):
        """Generate final response when step limit is reached"""
        self.conversation_history.append(
            {
                "role": "system",
                "content": f"The assistant has reached the maximum number of tool-assisted steps ({CONFIG['MAX_AI_STEPS']}). Provide a final response without calling tools."
            }
        )

        collected_text = ""
        async for tag, chunk in self._llm_chat_stream([]):  # No tools for final response
            if tag == "CONTENT":
                sys.stdout.write(chunk)
                sys.stdout.flush()
                collected_text += chunk
                await asyncio.sleep(CONFIG["STREAM_CHUNK_DELAY"])

        if collected_text.strip():
            self.conversation_history.append(
                {"role": "assistant", "content": collected_text.strip()}
            )
        print()

    # -----------------------------
    # AUTO REFRESH PROMPT
    # -----------------------------
    async def _auto_refresh_prompt(self):
        """Query notification server every 10s and refresh system prompt."""
        while True:
            await asyncio.sleep(10)

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.notification_server_url}/list_notifications") as resp:
                        if resp.status == 200:
                            self.notifications = await resp.json()
                        else:
                            self.notifications = []
            except Exception as e:
                self.notifications = []
                print(f"⚠️ Notification server query failed: {e}")

            # Update system message
            if self.conversation_history:
                self.conversation_history[0]["content"] = self._get_system_prompt()
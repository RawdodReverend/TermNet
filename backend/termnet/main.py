import asyncio
import time
import json
import websockets
import sys
import re
import logging
from io import StringIO
from contextlib import redirect_stdout
from termnet.tools.terminal import TerminalSession
from termnet.agent import TermNetAgent

# Suppress websockets library logging to prevent tracebacks
logging.getLogger('websockets').setLevel(logging.CRITICAL)
logging.getLogger('websockets.server').setLevel(logging.CRITICAL)
logging.getLogger('websockets.protocol').setLevel(logging.CRITICAL)

class StreamCapture:
    """Captures stdout from agent and streams it to websocket without dropping numeric content"""

    def __init__(self, websocket):
        self.websocket = websocket
        self.buffer = ""
        self.original_stdout = sys.stdout
        self.in_tool_execution = False
        self.response_started = False

    def write(self, text):
        self.buffer += text
        asyncio.create_task(self.process_buffer())

    def flush(self):
        self.original_stdout.flush()

    async def process_buffer(self):
        if not self.buffer:
            return

        text = self.buffer
        self.buffer = ""

        # Tool execution detection
        if "🛠️ Executing tool:" in text or "Executing tool:" in text:
            self.in_tool_execution = True
            try:
                await self.websocket.send(json.dumps({
                    "type": "tool_execution",
                    "message": "Processing with tools...",
                    "timestamp": time.time()
                }))
            except:
                pass
            return

        if self.in_tool_execution:
            # End tool execution once normal text comes in
            if not ("Args:" in text or "command" in text or "action" in text):
                self.in_tool_execution = False

        # ✅ Do NOT strip here – just send raw text
        if text:
            try:
                if not self.response_started:
                    await self.websocket.send(json.dumps({
                        "type": "response_start",
                        "timestamp": time.time()
                    }))
                    self.response_started = True

                await self.websocket.send(json.dumps({
                    "type": "response_chunk",
                    "chunk": text,   # ← raw text, spaces preserved
                    "timestamp": time.time()
                }))
            except:
                # Silently ignore websocket send errors
                pass

class TermNetWebSocketServer:
    def __init__(self, host="localhost", port=876):
        self.host = host
        self.port = port
        self.connected_clients = set()
        self.term = None
        self.agent = None

    async def initialize_termnet(self):
        """Initialize the TerminalSession and TermNetAgent"""
        if self.term is None:
            self.term = TerminalSession()
            await self.term.start()
            self.agent = TermNetAgent(self.term)

    async def stream_agent_response(self, websocket, user_input: str):
        """Stream the agent's response back to the client with real-time capture"""
        try:
            # Create stream capture
            capture = StreamCapture(websocket)
            
            # Send initial response start
            start_msg = {
                "type": "response_start",
                "timestamp": time.time()
            }
            try:
                await websocket.send(json.dumps(start_msg))
            except:
                return
            
            # Temporarily redirect stdout
            original_stdout = sys.stdout
            sys.stdout = capture
            
            try:
                # Call the agent's chat method
                await self.agent.chat(user_input)
                
                # Allow final buffer processing
                await asyncio.sleep(0.1)
                await capture.process_buffer()
                
            finally:
                # Restore original stdout
                sys.stdout = original_stdout
            
            # Send end of response
            end_msg = {
                "type": "response_end",
                "timestamp": time.time()
            }
            try:
                await websocket.send(json.dumps(end_msg))
            except:
                pass
            
        except Exception as e:
            try:
                error_msg = {
                    "type": "error",
                    "message": f"Error processing request: {str(e)}",
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(error_msg))
            except:
                pass

    async def handle_client(self, websocket, path=None):
        """Handle a WebSocket client connection"""
        try:
            self.connected_clients.add(websocket)
            client_id = id(websocket)
            
            # Initialize TermNet for this client
            await self.initialize_termnet()
            
            # Send welcome message
            welcome_msg = {
                "type": "system",
                "message": "TermNet v1.2 ready - WebSocket connection established",
                "timestamp": time.time()
            }
            try:
                await websocket.send(json.dumps(welcome_msg))
            except:
                return
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    user_input = data.get("message", "").strip()
                    
                    if not user_input:
                        continue
                        
                    if user_input.lower() in ("exit", "quit", "close"):
                        break
                    
                    # Stream the response back to client
                    await self.stream_agent_response(websocket, user_input)
                    
                except json.JSONDecodeError:
                    try:
                        error_msg = {
                            "type": "error",
                            "message": "Invalid JSON format",
                            "timestamp": time.time()
                        }
                        await websocket.send(json.dumps(error_msg))
                    except:
                        pass
                except Exception:
                    # Silently ignore all other exceptions
                    pass
                    
        except Exception:
            # Silently handle all connection exceptions
            pass
        finally:
            try:
                self.connected_clients.discard(websocket)
            except:
                pass

    async def start_server(self):
        """Start the WebSocket server"""
        try:
            async with websockets.serve(
                self.handle_client, 
                self.host, 
                self.port,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            ):
                await asyncio.Future()  # Run forever
        except Exception:
            pass

    async def stop_server(self):
        """Stop the server and clean up"""
        try:
            if self.term:
                await self.term.stop()
        except:
            pass

async def main():
    """Main function to run the WebSocket server"""
    server = TermNetWebSocketServer()
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
    finally:
        await server.stop_server()

if __name__ == "__main__":
    # Redirect stderr to suppress any remaining tracebacks
    import os
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    
    asyncio.run(main())
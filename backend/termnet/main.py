import asyncio
import time
import json
import websockets
import sys
import re
from io import StringIO
from contextlib import redirect_stdout
from termnet.tools.terminal import TerminalSession
from termnet.agent import TermNetAgent


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
            await self.websocket.send(json.dumps({
                "type": "tool_execution",
                "message": "Processing with tools...",
                "timestamp": time.time()
            }))
            return

        if self.in_tool_execution:
        # End tool execution once normal text comes in
            if not ("Args:" in text or "command" in text or "action" in text):
                self.in_tool_execution = False

    # ✅ Do NOT strip here — just send raw text
        if text:
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
            #print("TermNet agent initialized")

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
            await websocket.send(json.dumps(start_msg))
            
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
            await websocket.send(json.dumps(end_msg))
            
        except Exception as e:
            error_msg = {
                "type": "error",
                "message": f"Error processing request: {str(e)}",
                "timestamp": time.time()
            }
            await websocket.send(json.dumps(error_msg))

    async def handle_client(self, websocket, path=None):
        """Handle a WebSocket client connection"""
        self.connected_clients.add(websocket)
        client_id = id(websocket)
        ##print(f"🔌 Client {client_id} connected")
        
        try:
            # Initialize TermNet for this client
            await self.initialize_termnet()
            
            # Send welcome message
            welcome_msg = {
                "type": "system",
                "message": "TermNet v1.2 ready - WebSocket connection established",
                "timestamp": time.time()
            }
            await websocket.send(json.dumps(welcome_msg))
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    user_input = data.get("message", "").strip()
                    
                    if not user_input:
                        continue
                        
                    if user_input.lower() in ("exit", "quit", "close"):
                        break
                    
                    ##print(f"Received from client {client_id}: {user_input}")
                    
                    # Stream the response back to client
                    await self.stream_agent_response(websocket, user_input)
                    
                except json.JSONDecodeError:
                    error_msg = {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": time.time()
                    }
                    await websocket.send(json.dumps(error_msg))
                except Exception as e:
                    error_msg = {
                        "type": "error",
                        "message": f"Error processing message: {str(e)}",
                        "timestamp": time.time()
                    }
                    await websocket.send(json.dumps(error_msg))
                    
        except websockets.exceptions.ConnectionClosed:
            print(f"🔌 Client {client_id} disconnected")
        except Exception as e:
            print(f"Error with client {client_id}: {e}")
        finally:
            self.connected_clients.remove(websocket)
            #print(f"🔌 Client {client_id} removed")

    async def start_server(self):
        """Start the WebSocket server"""
        #print(f"TermNet WebSocket Server starting at ws://{self.host}:{self.port}")
        #print("Waiting for client connections...")
        
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # Run forever

    async def stop_server(self):
        """Stop the server and clean up"""
        if self.term:
            await self.term.stop()
        #print("Server stopped.")


async def main():
    """Main function to run the WebSocket server"""
    server = TermNetWebSocketServer()
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        print("\nServer interrupted by user")
    finally:
        await server.stop_server()


if __name__ == "__main__":
    asyncio.run(main())
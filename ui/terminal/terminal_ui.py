import asyncio
import json
import websockets
from websockets.exceptions import ConnectionClosed

class TermNetClient:
    def __init__(self, uri="ws://localhost:876"):
        self.uri = uri
        self.websocket = None
        self.connected = False
    
    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.uri)
            welcome = await self.websocket.recv()
            data = json.loads(welcome)
            print(f"Connected: {data.get('message', 'Ready')}")
            self.connected = True
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def send_message(self, message):
        # Auto-reconnect silently if needed
        if not self.connected or not self.websocket:
            if not await self.reconnect():
                return False
        
        try:
            msg_data = {
                "type": "message",
                "message": message,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            await self.websocket.send(json.dumps(msg_data))
            print("AI: ", end="", flush=True)
            
            full_response = ""
            while True:
                try:
                    response = await asyncio.wait_for(self.websocket.recv(), timeout=60.0)
                    data = json.loads(response)
                    msg_type = data.get("type", "")
                    
                    if msg_type == "response_chunk":
                        chunk = data.get("chunk", "")
                        print(chunk, end="", flush=True)
                        full_response += chunk
                    elif msg_type == "tool_execution":
                        tool_msg = data.get("message", "")
                        print(f"\nTool: {tool_msg}\nAI: ", end="", flush=True)
                    elif msg_type == "response_end":
                        break
                    elif msg_type == "error":
                        error_msg = data.get("message", "")
                        print(f"\nError: {error_msg}")
                        break
                        
                except asyncio.TimeoutError:
                    # Silently timeout - don't print error
                    break
                except ConnectionClosed:
                    # Silently try to reconnect and resend
                    if await self.reconnect():
                        return await self.send_message(message)
                    else:
                        return False
                except Exception as e:
                    # Silently ignore all errors - don't print them
                    break
            
            print("\n" + "-" * 50)
            return True
            
        except ConnectionClosed:
            # Silently try to reconnect and resend
            if await self.reconnect():
                return await self.send_message(message)
            else:
                return False
        except Exception as e:
            # Silently try to reconnect and resend
            if await self.reconnect():
                return await self.send_message(message)
            else:
                return False
    
    async def reconnect(self):
        """Silently attempt to reconnect to the server"""
        await self.close()
        try:
            self.websocket = await websockets.connect(self.uri)
            # Consume welcome message silently
            await self.websocket.recv()
            self.connected = True
            return True
        except:
            return False
    
    async def close(self):
        self.connected = False
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
            self.websocket = None

async def main():
    client = TermNetClient()
    
    if not await client.connect():
        return
    
    print("TermNet Client - Type 'quit' to exit")
    print("-" * 50)
    
    try:
        while True:
            try:
                user_input = input("> ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                    
                if user_input:
                    await client.send_message(user_input)
                            
            except KeyboardInterrupt:
                break
            except EOFError:
                # Handle Ctrl+D
                break
            except Exception as e:
                # Silently ignore all errors
                pass
                
    finally:
        await client.close()
        print("Disconnected")

if __name__ == "__main__":
    asyncio.run(main())
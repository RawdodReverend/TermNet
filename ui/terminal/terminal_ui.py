import asyncio
import json
import websockets

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
        if not self.connected:
            print("Not connected to server")
            return

        msg_data = {
            "type": "message",
            "message": message,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self.websocket.send(json.dumps(msg_data))
        print("You: " + message)
        print("AI: ", end="", flush=True)

        full_response = ""
        async for response in self.websocket:
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

        print("\n" + "-" * 50)

    async def close(self):
        if self.websocket:
            await self.websocket.close()

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
            except Exception as e:
                print(f"Error: {e}")
                
    finally:
        await client.close()
        print("Disconnected")

if __name__ == "__main__":
    asyncio.run(main())
from flask import Flask, render_template, request, redirect, url_for, session, Response
import asyncio
import json
import websockets
import secrets
import threading
from queue import Queue, Empty

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Configuration
PASSWORD = None
WEBSOCKET_URI = "ws://localhost:876"

class TermNetClient:
    def __init__(self, uri=WEBSOCKET_URI):
        self.uri = uri
        self.websocket = None
        
        
    import re

    def normalize_text(text: str) -> str:
    # Simple detection: jammed datetime looks like WedSep242025,22:09:27EDT
        compact_dt = re.findall(r"[A-Z][a-z]{2}[A-Z][a-z]{2}\d{1,2}\d{4},\d{2}:\d{2}:\d{2}[A-Z]{2,4}", text)
        for dt in compact_dt:
        # slice it instead of regex replace
            day   = dt[0:3]   # Wed
            month = dt[3:6]   # Sep
            date  = dt[6:8]   # 24
            year  = dt[8:12]  # 2025
            time  = dt.split(",")[1][0:8]  # 22:09:27
            tz    = dt.split(",")[1][8:]   # EDT
            fixed = f"{day} {month} {int(date)} {year}, {time} {tz}"
            text = text.replace(dt, fixed)
        return text


    async def connect(self):
        self.websocket = await websockets.connect(self.uri)
        print("Connected to TermNet server")
        welcome = await self.websocket.recv()  # consume welcome
        _ = json.loads(welcome)

    async def send_and_stream_to_queue(self, message: str, queue: Queue):
        """Stream responses to a queue that can be consumed by Flask"""
        try:
            if not self.websocket:
                await self.connect()

            msg_data = {
                "type": "message",
                "message": message,
                "timestamp": asyncio.get_event_loop().time()
            }
            await self.websocket.send(json.dumps(msg_data))
            

            while True:
                try:
                    response = await self.websocket.recv()
                    data = json.loads(response)
                    
                    # Put data in queue for Flask to consume
                    queue.put(json.dumps(data))
                    
                    if data["type"] in ["response_end", "error"]:
                        break
                        
                except Exception as e:
                    queue.put(json.dumps({"type": "error", "message": str(e)}))
                    break
                    
        except Exception as e:
            queue.put(json.dumps({"type": "error", "message": str(e)}))
        finally:
            # Signal end of stream
            queue.put(None)
        
            if self.websocket:
                await self.websocket.close()

    async def close(self):
        if self.websocket:
            await self.websocket.close()
            print("Disconnected from server")

def run_async_in_thread(coro, queue):
    """Run async coroutine in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()

# Set password on launch
def set_password():
    global PASSWORD
    PASSWORD = input("Set a password for accessing TermNet: ").strip()

# Routes
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("chat"))
        else:
            return "Invalid password", 401
    return render_template("login.html")

@app.route("/chat")
def chat():
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    return render_template("chat.html")

@app.route("/stream", methods=["POST"])
def stream():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    user_input = request.form.get("message")
    
    # Create a queue for communication between async and sync worlds
    data_queue = Queue()
    
    # Create client and start async processing in background thread
    client = TermNetClient()
    thread = threading.Thread(
        target=run_async_in_thread,
        args=(client.send_and_stream_to_queue(user_input, data_queue), data_queue)
    )
    thread.daemon = True
    thread.start()
    
    def generate():
        """Generator that yields data as it becomes available"""
        while True:
            try:
                # Get data from queue with timeout to prevent hanging
                data = data_queue.get(timeout=30)  # 30 second timeout
                
                if data is None:  # End of stream signal
                    break
                    
                yield f"data: {data}\n\n"
                
            except Empty:
                # Timeout occurred, send keepalive or break
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                continue
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break
    
    return Response(generate(), mimetype="text/event-stream")

@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    set_password()
    app.run(host="0.0.0.0", port=5005, debug=False, use_reloader=False)
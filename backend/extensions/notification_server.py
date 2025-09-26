from flask import Flask, request, jsonify
import threading
import time

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 


# In-memory storage for notifications
_notifications = []

app = Flask(__name__)

@app.route("/new_notification", methods=["POST"])
def new_notification():
    data = request.json
    if not data or "title" not in data or "message" not in data:
        return jsonify({"error": "Missing title or message"}), 400

    notif = {
        "title": data["title"],
        "message": data["message"],
        "timestamp": time.time(),
        "reminder_time": data.get("reminder_time")
    }
    _notifications.append(notif)
    return jsonify(notif), 201

@app.route("/list_notifications", methods=["GET"])
def list_notifications():
    return jsonify(_notifications)

@app.route("/dismiss_notification", methods=["POST"])
def dismiss_notification():
    data = request.json
    index = data.get("index")
    if index is None or index >= len(_notifications):
        return jsonify({"error": "Invalid index"}), 400
    removed = _notifications.pop(index)
    return jsonify(removed), 200

def start_server(port=5003):
    threading.Thread(target=lambda: app.run(port=port, debug=False, use_reloader=False)).start()

if __name__ == "__main__":
    start_server()

import os
import sys
import threading
import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from config import get_ghn_token, save_ghn_token, load_config
from bot import run_bot

PORT = int(os.environ.get("PORT", 8080))

class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class CloudTokenHandler(BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        res = {
            "status": "online",
            "service": "GHN Late Truck Telegram Bot Cloud Worker",
            "uptime": "24/7"
        }
        self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))

    def do_POST(self):
        if self.path in ("/update_token", "/token"):
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8")
                data = json.loads(body)
                raw_token = data.get("token", "").strip()
                if raw_token.lower().startswith("bearer "):
                    raw_token = raw_token[7:].strip()
                if raw_token and len(raw_token) > 20:
                    save_ghn_token(raw_token)
                    self.send_response(200)
                    self._send_cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success", "message": "Token synced to cloud"}).encode("utf-8"))
                    print(f"🔑 [CLOUD] Đã nhận Token GHN mới qua Webhook!")
                    return
            except Exception as e:
                print(f"[ERROR] Cloud Token sync error: {e}")

        self.send_response(400)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "error"}).encode("utf-8"))

    def log_message(self, format, *args):
        return

def run_cloud():
    # 1. Start background Bot thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # 2. Run HTTP server on $PORT for Render health checks and Webhook
    server = ReusableThreadingServer(("0.0.0.0", PORT), CloudTokenHandler)
    print(f"🚀 Cloud Web Server running on port {PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    run_cloud()

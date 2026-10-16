import os
import sys
import threading
import json
import time
import ssl
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from config import get_ghn_token, save_ghn_token, is_token_valid, load_config
from bot import run_bot, BOT_STATUS

PORT = int(os.environ.get("PORT", 8080))
VN_TZ = timezone(timedelta(hours=7))

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

        token = get_ghn_token()
        valid = is_token_valid(token)
        token_info = {"valid": valid}
        try:
            import base64
            parts = token.split('.')
            if len(parts) >= 2:
                padded = parts[1] + '=' * (-len(parts[1]) % 4)
                pj = json.loads(base64.b64decode(padded).decode('utf-8'))
                exp = pj.get('exp', 0)
                exp_dt = datetime.fromtimestamp(exp, VN_TZ) if exp else None
                now_dt = datetime.now(VN_TZ)
                rem = (exp_dt - now_dt).total_seconds() / 3600 if exp_dt else 0
                token_info.update({
                    "noc": pj.get('noc'),
                    "hid": pj.get('hid'),
                    "exp": exp_dt.strftime("%H:%M:%S %d/%m/%Y") if exp_dt else None,
                    "remaining_hours": round(rem, 1),
                    "is_expired": rem <= 0
                })
        except Exception as e:
            token_info["error"] = str(e)

        res = {
            "status": "online",
            "service": "GHN Late Truck Telegram Bot Cloud Worker",
            "uptime": "24/7",
            "token": token_info,
            "bot_status": BOT_STATUS
        }
        self.wfile.write(json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"))

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
                    if save_ghn_token(raw_token):
                        self.send_response(200)
                        self._send_cors()
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "success", "message": "Token synced to cloud"}).encode("utf-8"))
                        print(f"🔑 [CLOUD] Đã nhận và nạp Token GHN mới qua Webhook!")
                        return
                    else:
                        self.send_response(400)
                        self._send_cors()
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "error", "message": "Token invalid or expired"}).encode("utf-8"))
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

def keep_awake_pinger():
    """Periodically pings the public Render health URL to prevent Free Tier from sleeping."""
    time.sleep(30)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    while True:
        try:
            req = urllib.request.Request(
                "https://ghn-xetre-telegram-bot.onrender.com/health",
                headers={"User-Agent": "RenderKeepAlive/1.0"}
            )
            with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
                pass
        except Exception:
            pass
        time.sleep(600)  # Ping every 10 minutes (Render sleeps after 15m)

def run_cloud():
    # 1. Start background Bot thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # 2. Start keep-awake self-pinger
    pinger_thread = threading.Thread(target=keep_awake_pinger, daemon=True)
    pinger_thread.start()

    # 3. Run HTTP server on $PORT for Render health checks and Webhook
    server = ReusableThreadingServer(("0.0.0.0", PORT), CloudTokenHandler)
    print(f"🚀 Cloud Web Server running on port {PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    run_cloud()

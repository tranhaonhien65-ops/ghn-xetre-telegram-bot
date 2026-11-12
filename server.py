import os
import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8080))

class DeactivatedHandler(BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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
            "status": "deactivated",
            "message": "Bot đã được huỷ và tắt toàn bộ hoạt động theo yêu cầu của người dùng.",
            "bot_alive": False,
            "services": {
                "telegram_command_listener": "stopped",
                "ghn_delayed_truck_scanner": "stopped",
                "sl_scheduler": "stopped",
                "token_pinger": "stopped"
            }
        }
        self.wfile.write(json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_POST(self):
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        res = {
            "status": "deactivated",
            "message": "Bot đã tắt hoàn toàn. Mọi yêu cầu đồng bộ đã bị huỷ."
        }
        self.wfile.write(json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"))

    def log_message(self, format, *args):
        return

def run_cloud():
    print("=" * 60)
    print("🛑 BOT ĐÃ ĐƯỢC HUỶ HOÀN TOÀN THEO YÊU CẦU.")
    print("💤 Máy chủ chỉ chạy chế độ Standby/Deactivated tĩnh.")
    print("⛔ Đã tắt tất cả các luồng: Quét xe trễ, Lắng nghe Telegram, Báo cáo SL.")
    print("=" * 60)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DeactivatedHandler)
    server.serve_forever()

if __name__ == "__main__":
    run_cloud()

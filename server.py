import os
import sys
import threading
import json
import time
import ssl
import collections
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from config import get_ghn_token, save_ghn_token, is_token_valid, load_config, set_bot_token
from bot import run_bot, BOT_STATUS

BASE_DIR = Path(__file__).parent.resolve()
PORT = int(os.environ.get("PORT", 8080))
VN_TZ = timezone(timedelta(hours=7))

RECENT_LOGS = collections.deque(maxlen=100)

class LogCapture:
    def __init__(self, original_stream):
        self.original_stream = original_stream
    def write(self, s):
        if s and s.strip():
            now_str = datetime.now(VN_TZ).strftime("%H:%M:%S")
            RECENT_LOGS.append(f"[{now_str}] {s.strip()}")
        try:
            self.original_stream.write(s)
        except Exception:
            pass
    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass

sys.stdout = LogCapture(sys.stdout)
sys.stderr = LogCapture(sys.stderr)

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
        if self.path == "/diag":
            import socket, urllib.request
            diag = {}
            try:
                diag["render_ip"] = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode()
            except Exception as e:
                diag["render_ip_err"] = str(e)
            try:
                diag["dns_truck"] = socket.gethostbyname("truck-gw.ghn.vn")
            except Exception as e:
                diag["dns_truck_err"] = str(e)
            try:
                s = socket.create_connection(("truck-gw.ghn.vn", 443), timeout=5)
                s.close()
                diag["tcp_truck"] = "connected"
            except Exception as e:
                diag["tcp_truck_err"] = str(e)
            try:
                s2 = socket.create_connection(("baocao-api.ghn.vn", 443), timeout=5)
                s2.close()
                diag["tcp_baocao"] = "connected"
            except Exception as e:
                diag["tcp_baocao_err"] = str(e)
            self.send_response(200)
            self._send_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(diag, indent=2).encode())
            return

        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        if self.path.startswith("/run_sl"):
            shift = "ca1"
            if any(k in self.path for k in ["ca_sang", "ca_ngay", "ca2", "ca_2"]):
                shift = "ca2"
            elif any(k in self.path for k in ["ca_dem", "ca1", "ca_1"]):
                shift = "ca1"
            force = "force" in self.path
            try:
                from sl_pipeline import run_pipeline
                threading.Thread(target=run_pipeline, kwargs={"shift": shift, "force": force}, daemon=True).start()
                res = {"status": "success", "message": f"Triggered SL report {shift} in background (force={force})"}
            except Exception as e:
                res = {"status": "error", "message": str(e)}
            self.wfile.write(json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"))
            return

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

        cfg = load_config()
        current_bot_token = cfg.get("BOT_TOKEN", "").strip()
        try:
            from sl_pipeline import get_sl_state
            sl_state = get_sl_state()
        except Exception:
            sl_state = {}
        bot_status_summary = {k: v for k, v in BOT_STATUS.items() if k not in ("latest_trips", "latest_delayed")}
        res = {
            "status": "online",
            "service": "GHN Late Truck Telegram Bot Cloud Worker",
            "uptime": "24/7",
            "telegram_bot": {
                "configured": bool(current_bot_token),
                "preview": f"{current_bot_token[:8]}...{current_bot_token[-4:]}" if current_bot_token else None
            },
            "token": token_info,
            "sl_state": sl_state,
            "bot_status": bot_status_summary,
            "recent_logs": list(RECENT_LOGS)
        }
        self.wfile.write(json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_POST(self):
        if self.path in ("/update_bot_token", "/bot_token"):
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8")
                data = json.loads(body)
                raw_token = data.get("token", "").strip()
                if raw_token and len(raw_token) > 10:
                    set_bot_token(raw_token)
                    print(f"🤖 [CLOUD] Đã nhận và nạp Bot Token Telegram mới ({raw_token[:8]}...)!")
                    self.send_response(200)
                    self._send_cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success", "message": "Bot token updated on cloud"}).encode("utf-8"))
                    return
                else:
                    self.send_response(400)
                    self._send_cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": "Invalid token"}).encode("utf-8"))
                    return
            except Exception as e:
                print(f"[ERROR] Cloud Bot Token update error: {e}")

        if self.path in ("/update_token", "/token"):
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8")
                data = json.loads(body)
                raw_token = data.get("token", "").strip() or data.get("url", "").strip() or body
                matched_category = False

                import re, base64

                # Tự động nhận diện token_report UUID (chuỗi xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
                uuid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', body, re.IGNORECASE)
                if uuid_match:
                    uuid_val = uuid_match.group(0)
                    ip_val = data.get("report_ip") or data.get("ip") or "not_found"
                    session_data = {"token": uuid_val, "ip": ip_val}
                    (BASE_DIR / "baocao_session.json").write_text(json.dumps(session_data, indent=2), encoding="utf-8")
                    (BASE_DIR / "token_report.txt").write_text(uuid_val, encoding="utf-8")
                    print(f"📑 [CLOUD] Đã nhận và lưu Phiên Báo Cáo (UUID): {uuid_val}")
                    try:
                        from sl_pipeline import get_metabase_jwt
                        get_metabase_jwt(force_refresh=True)
                    except Exception as e_tok:
                        print(f"[WARN] Không thể tạo Metabase JWT ngay: {e_tok}")
                    matched_category = True
                elif data.get("report_uuid"):
                    uuid_val = data["report_uuid"].strip()
                    ip_val = data.get("report_ip", "not_found").strip()
                    session_data = {"token": uuid_val, "ip": ip_val}
                    (BASE_DIR / "baocao_session.json").write_text(json.dumps(session_data, indent=2), encoding="utf-8")
                    (BASE_DIR / "token_report.txt").write_text(uuid_val, encoding="utf-8")
                    print(f"📑 [CLOUD] Đã nhận và lưu Phiên Báo Cáo (token_report UUID)! IP: {ip_val}")
                    matched_category = True
                
                # Smart Token Extraction for all GHN & Metabase tokens
                mb_match = re.search(r'embed/dashboard/([a-zA-Z0-9_\-\.]+)', raw_token)
                if mb_match:
                    jwt = mb_match.group(1).split('?')[0].split('/')[0]
                    (BASE_DIR / "metabase_jwt.txt").write_text(jwt.strip(), encoding="utf-8")
                    print(f"📊 [CLOUD] Đã nhận và lưu Metabase JWT mới!")
                    matched_category = True
                tokens = re.findall(r'eyJhbGciOi[a-zA-Z0-9_\-\.]+', raw_token)
                for t in tokens:
                    try:
                        part = t.split('.')[1]
                        part += '=' * (-len(part) % 4)
                        pl = json.loads(base64.urlsafe_b64decode(part))
                        if 'resource' in pl and 'dashboard' in pl.get('resource', {}):
                            (BASE_DIR / "metabase_jwt.txt").write_text(t.strip(), encoding="utf-8")
                            exp_val = pl.get('exp')
                            exp_str = datetime.fromtimestamp(exp_val, VN_TZ).strftime('%H:%M:%S %d/%m/%Y') if exp_val else 'Vĩnh viễn'
                            print(f"📊 [CLOUD] Đã nhận và lưu Metabase JWT mới! (Hạn dùng: {exp_str})")
                            matched_category = True
                        elif 'ssoId' in pl or 'orgCode' in pl:
                            (BASE_DIR / "ghn_sso_token.txt").write_text(t.strip(), encoding="utf-8")
                            print(f"🔑 [CLOUD] Đã nhận và lưu GHN SSO Token mới!")
                            matched_category = True
                        elif pl.get('typ') in ('coordinator', 'staff') or pl.get('hid') or pl.get('noc'):
                            save_ghn_token(t.strip())
                            print(f"🚛 [CLOUD] Đã nhận và lưu GHN Coordinator Token mới!")
                            matched_category = True
                        else:
                            (BASE_DIR / "token_report.txt").write_text(t.strip(), encoding="utf-8")
                            print(f"📑 [CLOUD] Đã nhận và lưu Token Báo Cáo (token_report) mới!")
                            matched_category = True
                    except Exception as e:
                        print(f"[WARN] Lỗi giải mã token: {e}")

                if not matched_category:
                    if raw_token.lower().startswith("bearer "):
                        raw_token = raw_token[7:].strip()
                    if raw_token and len(raw_token) > 20:
                        save_ghn_token(raw_token)

                self.send_response(200)
                self._send_cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Tokens synced to cloud"}).encode("utf-8"))
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
    # 1. Start background Bot thread (Báo xe trễ)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # 2. Start keep-awake self-pinger
    pinger_thread = threading.Thread(target=keep_awake_pinger, daemon=True)
    pinger_thread.start()

    # 3. Start SL Reporter Scheduler (Báo cáo sản lượng 07:00 & 15:00)
    try:
        from sl_pipeline import run_sl_scheduler
        sl_thread = threading.Thread(target=run_sl_scheduler, daemon=True)
        sl_thread.start()
        print("⏰ [CLOUD] Đã khởi động luồng tự động báo cáo sản lượng (07:00 & 15:00)!")
    except Exception as e:
        print(f"[WARN] Không thể khởi động SL Scheduler: {e}")

    # 4. Run HTTP server on $PORT for Render health checks and Webhook
    server = ReusableThreadingServer(("0.0.0.0", PORT), CloudTokenHandler)
    print(f"🚀 Cloud Web Server running on port {PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    run_cloud()

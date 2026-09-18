import os
import sys
import time
import json
import ssl
import signal
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from config import (
    load_config, save_config, get_ghn_token, save_ghn_token,
    CONFIG_FILE, TOKEN_FILE, BASE_DIR
)
from ghn_api import fetch_all_active_trips
from analyzer import find_all_delayed_trips, VN_TZ
from notifier import (
    send_telegram_message, format_single_trip_alert,
    format_summary_report, filter_new_or_escalated_alerts
)

PID_FILE = BASE_DIR / "bot.pid"

def enforce_single_instance():
    current_pid = os.getpid()
    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != current_pid:
                try:
                    os.kill(old_pid, signal.SIGKILL)
                    print(f"🛑 Đã tắt tiến trình bot cũ (PID: {old_pid})")
                except ProcessLookupError:
                    pass
                except Exception as e:
                    print(f"[WARN] Error killing old PID {old_pid}: {e}")
        except Exception:
            pass
    with open(PID_FILE, "w") as f:
        f.write(str(current_pid))

# ----------------- LOCAL TOKEN SYNC SERVER (Port 8989) -----------------
class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True

class TokenSyncHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "running", "service": "GHN Token Sync Server"}).encode("utf-8"))

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
                    old_token = get_ghn_token()
                    save_ghn_token(raw_token)
                    
                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success", "message": "Token synced successfully"}).encode("utf-8"))
                    
                    if raw_token != old_token:
                        print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] 🔑 [AUTO-SYNC] Đã nhận Token GHN mới tự động từ trình duyệt!")
                    return
            except Exception as e:
                print(f"[ERROR] Error processing token sync: {e}")
                
        self.send_response(400)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "error", "message": "Invalid request"}).encode("utf-8"))

    def log_message(self, format, *args):
        return

def start_token_server(port=8989):
    try:
        server = ReusableHTTPServer(("127.0.0.1", port), TokenSyncHandler)
        print(f"📡 Token Auto-Sync Server đang lắng nghe tại http://localhost:{port}/update_token")
        server.serve_forever()
    except Exception as e:
        print(f"[WARN] Không thể mở cổng sync token {port}: {e}")

# ----------------- TELEGRAM POLLING & COMMANDS -----------------
def get_telegram_updates(bot_token: str, offset: Optional[int] = None, timeout: int = 10) -> list:
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?timeout={timeout}"
    if offset is not None:
        url += f"&offset={offset}"
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "XetreTNG_Bot/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout + 5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("result", [])
    except Exception:
        pass
    return []

def handle_command(text: str, chat_id: int, config: dict) -> None:
    bot_token = config["BOT_TOKEN"]
    text = text.strip()
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split('@')[0]
    args = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        help_msg = (
            "🤖 <b>GHN VANTAI DELAY MONITOR BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Các lệnh khả dụng:</b>\n"
            "🔹 <code>/check</code> hoặc <code>/tre</code>: Kiểm tra danh sách các chuyến xe đang trễ điểm ngay lập tức.\n"
            "🔹 <code>/all</code>: Xem danh sách tổng quan toàn bộ xe đang chạy.\n"
            "🔹 <code>/threshold &lt;phút&gt;</code>: Đổi ngưỡng lọc trễ (Mặc định: <code>/threshold 1</code>).\n"
            "🔹 <code>/token &lt;token_ghn&gt;</code>: Cập nhật Bearer Token GHN bằng tay khi cần.\n"
            "🔹 <code>/status</code>: Xem tình trạng hoạt động và thời hạn Token.\n"
            "🔹 <code>/group</code>: Lấy Chat ID của nhóm hiện tại.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ <i>Ngưỡng hiện tại: {config.get('DELAY_THRESHOLD_MINUTES', 1)} phút | Quét mỗi {config.get('POLL_INTERVAL_SECONDS', 60)}s | Nhắc lại mỗi 5 phút</i>"
        )
        send_telegram_message(bot_token, chat_id, help_msg)

    elif cmd == "/group":
        send_telegram_message(bot_token, chat_id, f"🆔 Chat ID của cuộc trò chuyện này là: <code>{chat_id}</code>")

    elif cmd in ("/check", "/tre"):
        send_telegram_message(bot_token, chat_id, "⏳ <i>Đang quét dữ liệu điều phối GHN...</i>")
        trips, err, is_expired = fetch_all_active_trips()
        if err and is_expired:
            send_telegram_message(bot_token, chat_id, f"❌ <b>Token GHN đã hết hạn:</b> {err}\n\n💡 Vui lòng mở lại trang GHN trên trình duyệt để tự động đồng bộ Token mới.")
            return
        elif err:
            send_telegram_message(bot_token, chat_id, f"⚠️ Mạng GHN phản hồi chậm ({err}), đang thử lại...")
            trips, err, _ = fetch_all_active_trips()
            if err:
                send_telegram_message(bot_token, chat_id, f"❌ Không thể kết nối GHN: {err}")
                return
        
        threshold = config.get("DELAY_THRESHOLD_MINUTES", 1)
        delayed = find_all_delayed_trips(trips, threshold_minutes=threshold)
        summary = format_summary_report(delayed, len(trips), threshold)
        send_telegram_message(bot_token, chat_id, summary)

    elif cmd == "/all":
        send_telegram_message(bot_token, chat_id, "⏳ <i>Đang tải danh sách chuyến xe...</i>")
        trips, err, _ = fetch_all_active_trips()
        if err:
            send_telegram_message(bot_token, chat_id, f"❌ <b>Lỗi kết nối:</b> {err}")
            return
        
        lines = [
            f"🚚 <b>DANH SÁCH {len(trips)} CHUYẾN ĐANG CHẠY (ONTRIP)</b>",
            "━━━━━━━━━━━━━━━━━━━━"
        ]
        for i, t in enumerate(trips, 1):
            truck = t.get("truck", {}).get("id_number", "N/A")
            driver = t.get("driver", {}).get("fullname", "N/A")
            hub = t.get("hub", "")
            code = t.get("code", "")
            lines.append(f"<b>{i}. {truck}</b> (Hub {hub}) - {driver}\n   Mã: <code>{code}</code>")
            if i >= 30:
                lines.append(f"... và còn {len(trips) - 30} chuyến khác.")
                break
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        send_telegram_message(bot_token, chat_id, "\n".join(lines))

    elif cmd == "/threshold":
        if not args:
            send_telegram_message(bot_token, chat_id, f"ℹ️ Ngưỡng cảnh báo trễ hiện tại là: <b>{config.get('DELAY_THRESHOLD_MINUTES', 1)} phút</b>.\nĐể đổi, gõ: <code>/threshold 1</code> (ví dụ 1 phút).")
            return
        try:
            val = int(args.strip())
            if val < 0:
                raise ValueError
            config["DELAY_THRESHOLD_MINUTES"] = val
            save_config(config)
            send_telegram_message(bot_token, chat_id, f"✅ Đã cập nhật ngưỡng cảnh báo trễ thành: <b>{val} phút</b>.")
        except Exception:
            send_telegram_message(bot_token, chat_id, "❌ Giá trị không hợp lệ. Vui lòng nhập số phút (ví dụ: <code>/threshold 1</code>).")

    elif cmd == "/token":
        if not args:
            send_telegram_message(bot_token, chat_id, "ℹ️ Cách dùng: <code>/token &lt;chuỗi_token_bearer_ghn&gt;</code>")
            return
        new_token = args.strip()
        if new_token.lower().startswith("bearer "):
            new_token = new_token[7:].strip()
        save_ghn_token(new_token)
        
        trips, err, _ = fetch_all_active_trips(new_token)
        if err:
            send_telegram_message(bot_token, chat_id, f"⚠️ Đã lưu token nhưng thử nghiệm thất bại: {err}")
        else:
            send_telegram_message(bot_token, chat_id, f"✅ Cập nhật Token GHN thành công! Đã kết nối và tìm thấy <b>{len(trips)}</b> chuyến đang chạy.")

    elif cmd == "/status":
        token = get_ghn_token()
        token_info = "Không rõ"
        try:
            import base64
            parts = token.split('.')
            if len(parts) >= 2:
                padded = parts[1] + '=' * (-len(parts[1]) % 4)
                payload_json = json.loads(base64.b64decode(padded).decode('utf-8'))
                noc = payload_json.get('noc', 'N/A')
                hid = payload_json.get('hid', 'N/A')
                exp = payload_json.get('exp', 0)
                exp_dt = datetime.fromtimestamp(exp, VN_TZ)
                now_dt = datetime.now(VN_TZ)
                remaining_hours = (exp_dt - now_dt).total_seconds() / 3600
                if remaining_hours > 0:
                    token_info = f"{noc} [{hid}] (Hết hạn lúc: {exp_dt.strftime('%H:%M %d/%m/%Y')} - còn {remaining_hours:.1f}h)"
                else:
                    token_info = f"❌ {noc} [{hid}] (ĐÃ HẾT HẠN lúc {exp_dt.strftime('%H:%M %d/%m/%Y')} - Vui lòng F5 trang GHN để đồng bộ)"
        except Exception:
            pass

        now_str = datetime.now(VN_TZ).strftime("%H:%M:%S %d/%m/%Y")
        msg = (
            "📊 <b>TRẠNG THÁI HỆ THỐNG BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Bot Telegram:</b> Hoạt động bình thường\n"
            f"👥 <b>Nhóm nhận tin:</b> <code>{config.get('GROUP_ID')}</code>\n"
            f"⏱️ <b>Chu kỳ quét:</b> {config.get('POLL_INTERVAL_SECONDS', 60)} giây\n"
            f"⏳ <b>Ngưỡng trễ:</b> {config.get('DELAY_THRESHOLD_MINUTES', 1)} phút (Nhắc lại mỗi 10p)\n"
            f"🔑 <b>Tài khoản GHN:</b> {token_info}\n"
            f"📡 <b>Auto-Sync Server:</b> Hoạt động (Port 8989)\n"
            f"🕒 <b>Thời gian hiện tại:</b> {now_str}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(bot_token, chat_id, msg)

def telegram_command_worker(config: dict):
    bot_token = config["BOT_TOKEN"]
    update_offset = None
    print("📡 Telegram Command Listener thread started.")
    while True:
        try:
            updates = get_telegram_updates(bot_token, offset=update_offset, timeout=5)
            for u in updates:
                update_offset = u["update_id"] + 1
                msg = u.get("message")
                if msg and "text" in msg:
                    chat_id = msg["chat"]["id"]
                    text = msg["text"]
                    if text.startswith("/"):
                        print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] Command from chat {chat_id}: {text}")
                        handle_command(text, chat_id, config)
        except Exception as e:
            print(f"[ERROR in telegram_command_worker]: {e}")
            time.sleep(2)
        time.sleep(0.5)

def ghn_alert_worker(config: dict):
    bot_token = config["BOT_TOKEN"]
    group_id = config["GROUP_ID"]
    poll_interval = config.get("POLL_INTERVAL_SECONDS", 60)
    
    # ── Startup grace period ─────────────────────────────────────────────────
    STARTUP_GRACE = 60
    print(f"⏳ Startup grace: waiting {STARTUP_GRACE}s before first alert scan...")
    time.sleep(STARTUP_GRACE)
    print("✅ Grace period done — starting alert loop.")
    # ────────────────────────────────────────────────────────────────────────

    consecutive_auth_errors = 0
    token_error_notified = False

    while True:
        try:
            threshold = config.get("DELAY_THRESHOLD_MINUTES", 1)
            trips, err, is_expired = fetch_all_active_trips()
            if err:
                print(f"[WARN] GHN API Error: {err}")
                if is_expired:
                    consecutive_auth_errors += 1
                else:
                    consecutive_auth_errors = 0
                
                # ONLY notify Telegram group if token is genuinely expired for 3 consecutive polls (3 minutes)
                if is_expired and consecutive_auth_errors >= 3 and not token_error_notified:
                    send_telegram_message(
                        bot_token, group_id,
                        f"⚠️ <b>CẢNH BÁO MẤT KẾT NỐI GHN:</b> {err}\n\n💡 Vui lòng mở lại trang GHN trên trình duyệt để tự động đồng bộ Token mới."
                    )
                    token_error_notified = True
            else:
                consecutive_auth_errors = 0
                token_error_notified = False
                delayed_trips = find_all_delayed_trips(trips, threshold_minutes=threshold)
                to_alert = filter_new_or_escalated_alerts(delayed_trips, update_interval_seconds=600)
                
                print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] Active: {len(trips)} | Delayed (>={threshold}m): {len(delayed_trips)} | Alerts: {len(to_alert)}")
                
                for d in to_alert:
                    alert_msg = format_single_trip_alert(d)
                    send_telegram_message(bot_token, group_id, alert_msg)
                    time.sleep(1)
        except Exception as e:
            print(f"[ERROR in ghn_alert_worker]: {e}")
            
        time.sleep(poll_interval)

def run_bot():
    enforce_single_instance()
    config = load_config()
    bot_token = config["BOT_TOKEN"]
    group_id = config["GROUP_ID"]
    poll_interval = config.get("POLL_INTERVAL_SECONDS", 60)

    server_thread = threading.Thread(target=start_token_server, args=(8989,), daemon=True)
    server_thread.start()

    print("=" * 50)
    print("🚀 GHN LATE TRUCK MONITOR BOT STARTED")
    print(f"📍 Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
    print(f"👥 Target Group ID: {group_id}")
    print(f"⏱️ Poll Interval: {poll_interval}s")
    print(f"⏳ Delay Threshold: {config.get('DELAY_THRESHOLD_MINUTES', 1)}m")
    print("🔔 Re-alert Interval: 10 minutes (600s)")
    print("📡 Token Auto-Sync Port: 8989")
    print("=" * 50)

    # 1. Start dedicated Telegram Command Worker thread
    cmd_thread = threading.Thread(target=telegram_command_worker, args=(config,), daemon=True)
    cmd_thread.start()

    # 2. Start dedicated GHN Alert Worker thread
    alert_thread = threading.Thread(target=ghn_alert_worker, args=(config,), daemon=True)
    alert_thread.start()

    # 3. Main thread keepalive
    while True:
        time.sleep(60)

if __name__ == "__main__":
    run_bot()


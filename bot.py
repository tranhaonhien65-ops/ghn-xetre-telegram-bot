import os
import sys
import time
import json
import ssl
import signal
import re
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from config import (
    load_config, save_config, get_ghn_token, save_ghn_token, is_token_valid,
    CONFIG_FILE, TOKEN_FILE, BASE_DIR
)
from ghn_api import fetch_all_active_trips
from analyzer import find_all_delayed_trips, VN_TZ
from notifier import (
    send_telegram_message, format_single_trip_alert,
    format_summary_report, filter_new_or_escalated_alerts
)
from ai_chat import handle_ai_chat, send_chat_action, set_gemini_key, get_gemini_key, validate_gemini_key

try:
    from sl_pipeline import get_upcoming_trucks_summary
except Exception:
    get_upcoming_trucks_summary = None

PID_FILE = BASE_DIR / "bot.pid"

BOT_STATUS = {
    "started_at": datetime.now(VN_TZ).strftime("%H:%M:%S %d/%m/%Y"),
    "last_scan_time": "Chưa quét",
    "last_scan_status": "Khởi động",
    "total_active_trips": 0,
    "delayed_trips_count": 0,
    "last_error": None,
    "consecutive_auth_errors": 0,
    "cmd_worker_alive": False,
    "alert_worker_alive": False,
}

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
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?timeout={timeout}&allowed_updates=%5B%22message%22%2C%22edited_message%22%2C%22my_chat_member%22%2C%22chat_member%22%5D"
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

def handle_command(text: str, chat_id: int, config: dict, sender_name: str = "", msg_id: Optional[int] = None) -> None:
    bot_token = config["BOT_TOKEN"]
    text = text.strip()
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split('@')[0]
    args = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        help_msg = (
            "🤖 <b>GHN VANTAI DELAY MONITOR & AI BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Các lệnh tra cứu:</b>\n"
            "🔹 <code>/chuave</code> hoặc <code>/xetruc</code>: Xem danh sách xe đang trên đường về kho KTC Bình Định.\n"
            "🔹 <code>/check</code> hoặc <code>/tre</code>: Kiểm tra danh sách xe đang trễ điểm.\n"
            "🔹 <code>/all</code>: Xem danh sách toàn bộ xe đang chạy.\n"
            "🔹 <code>/status</code>: Xem tình trạng hoạt động và thời hạn Token.\n"
            "🔹 <code>/test</code>: Kiểm tra phản hồi của Bot.\n"
            "🔹 <code>/threshold &lt;phút&gt;</code>: Đổi ngưỡng lọc trễ (Mặc định: 1 phút).\n"
            "🔹 <code>/token &lt;token&gt;</code>: Cập nhật Bearer Token GHN bằng tay.\n\n"
            "💬 <b>Trò chuyện AI như người thật:</b>\n"
            "🔹 Trong nhóm: Tag <code>@VanTaiTNGBrain_Bot</code> hoặc <b>Reply</b> tin nhắn của bot để hỏi đáp/tâm sự.\n"
            "🔹 Nhắn tin riêng 1-1 với bot thoải mái mọi lúc mọi nơi.\n"
            "🔹 <code>/ai &lt;câu hỏi&gt;</code>: Gửi câu hỏi nhanh cho AI.\n"
            "🔹 <code>/gemini &lt;API_KEY&gt;</code>: Kết nối bộ não Google Gemini (Miễn phí 100%).\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ <i>Ngưỡng hiện tại: {config.get('DELAY_THRESHOLD_MINUTES', 1)}p | Quét mỗi {config.get('POLL_INTERVAL_SECONDS', 60)}s</i>"
        )
        send_telegram_message(bot_token, chat_id, help_msg, reply_to_message_id=msg_id)

    elif cmd in ("/chuave", "/xetruc", "/xeve"):
        send_telegram_message(bot_token, chat_id, "⏳ <i>Đang kiểm tra danh sách xe đang trên đường về KTC Bình Định...</i>")
        if get_upcoming_trucks_summary:
            summary = get_upcoming_trucks_summary()
        else:
            summary = "⚠️ Chức năng tra cứu xe về đang được khởi tạo, sếp thử lại sau 30 giây nhé!"
        send_telegram_message(bot_token, chat_id, summary)

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

        gemini_k = get_gemini_key(config)
        ai_info = "Google Gemini Flash (Đã kết nối ⚡)" if gemini_k else "Trợ lý Điều phối ảo TNG (Sẵn sàng 💬)"
        now_str = datetime.now(VN_TZ).strftime("%H:%M:%S %d/%m/%Y")
        msg = (
            "📊 <b>TRẠNG THÁI HỆ THỐNG BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Bot Telegram:</b> Hoạt động bình thường\n"
            f"👥 <b>Nhóm nhận tin:</b> <code>{config.get('GROUP_ID')}</code>\n"
            f"⏱️ <b>Chu kỳ quét:</b> {config.get('POLL_INTERVAL_SECONDS', 60)} giây\n"
            f"⏳ <b>Ngưỡng trễ:</b> {config.get('DELAY_THRESHOLD_MINUTES', 1)} phút (Nhắc lại mỗi 10p)\n"
            f"🔑 <b>Tài khoản GHN:</b> {token_info}\n"
            f"🧠 <b>Trí tuệ nhân tạo (AI):</b> {ai_info}\n"
            f"📡 <b>Auto-Sync Server:</b> Hoạt động (Port 8989)\n"
            f"🕒 <b>Thời gian hiện tại:</b> {now_str}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(bot_token, chat_id, msg, reply_to_message_id=msg_id)

    elif cmd in ("/test", "/ping"):
        token = get_ghn_token()
        token_valid = is_token_valid(token)
        scan_time = BOT_STATUS.get("last_scan_time", "N/A")
        scan_stat = BOT_STATUS.get("last_scan_status", "N/A")
        active_cnt = BOT_STATUS.get("total_active_trips", 0)
        delayed_cnt = BOT_STATUS.get("delayed_trips_count", 0)
        now_str = datetime.now(VN_TZ).strftime("%H:%M:%S %d/%m/%Y")
        
        test_msg = (
            "🤖 <b>BOT TELEGRAM HOẠT ĐỘNG BÌNH THƯỜNG!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <b>Máy chủ:</b> Render Cloud 24/7\n"
            f"🔑 <b>Token GHN:</b> {'✅ Đang hoạt động' if token_valid else '❌ Đã hết hạn (Vui lòng F5 trang GHN)'}\n"
            f"🕒 <b>Lần quét gần nhất:</b> {scan_time} ({scan_stat})\n"
            f"📊 <b>Chuyến đang chạy:</b> {active_cnt} | <b>Xe trễ:</b> {delayed_cnt}\n"
            f"🕒 <b>Thời gian hiện tại:</b> {now_str}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 Gõ <code>/check</code> để quét ngay, tag <code>@XetreTNG_Bot</code> để trò chuyện trực tiếp!"
        )
        send_telegram_message(bot_token, chat_id, test_msg, reply_to_message_id=msg_id)

    elif cmd in ("/gemini", "/setgemini"):
        if not args:
            current_key = get_gemini_key(config)
            has_key = bool(current_key)
            masked = f"<code>{current_key[:6]}...{current_key[-4:]}</code> (Đang chạy tốt)" if has_key else "Chưa cài đặt (Đang dùng trợ lý tích hợp)"
            guide = (
                "🤖 <b>CÀI ĐẶT GOOGLE GEMINI AI CHO BOT</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 <b>Trạng thái:</b> {masked}\n\n"
                "💡 <b>Cách lấy Key hoàn toàn MIỄN PHÍ 100%:</b>\n"
                "1. Vào trang: <code>https://aistudio.google.com/apikey</code>\n"
                "2. Đăng nhập Gmail $\rightarrow$ Bấm <b>Create API Key</b>.\n"
                "3. Sao chép và gửi lệnh vào đây:\n"
                "   <code>/gemini &lt;API_KEY_CUA_BAN&gt;</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "✨ <i>Khi có Key, bot sẽ trò chuyện tự nhiên, hài hước và thông minh như ChatGPT/Gemini về mọi chủ đề!</i>"
            )
            send_telegram_message(bot_token, chat_id, guide, reply_to_message_id=msg_id)
            return
        
        new_key = args.strip()
        send_telegram_message(bot_token, chat_id, "⏳ <i>Đang kiểm tra kết nối với Google AI...</i>", reply_to_message_id=msg_id)
        is_ok, err_desc = validate_gemini_key(new_key)
        if not is_ok:
            if "GEMINI_API_KEY" in config:
                config.pop("GEMINI_API_KEY", None)
                save_config(config)
            send_telegram_message(
                bot_token, chat_id,
                f"⚠️ <b>MÃ KEY CHƯA KÍCH HOẠT ĐƯỢC:</b>\n<i>{err_desc}</i>\n\n"
                "💡 <b>Lưu ý quan trọng:</b>\n"
                "Mã API Key chuẩn của Google luôn bắt đầu bằng <b><code>AIzaSy...</code></b>.\n"
                "👉 Bạn vui lòng vào lại trang <code>https://aistudio.google.com/apikey</code>, bấm nút <b>+ Create API key</b> (góc trên bên phải) để tạo một Key mới chuẩn nhé!\n\n"
                "<i>(Trong lúc này, Trợ lý ảo tích hợp của bot vẫn đang hoạt động trả lời về xe cộ bình thường ạ!)</i>",
                reply_to_message_id=msg_id
            )
            return

        set_gemini_key(new_key, config)
        send_telegram_message(
            bot_token, chat_id,
            "🎉 <b>KÍCH HOẠT GOOGLE GEMINI AI THÀNH CÔNG!</b>\n\n"
            "Bộ não trí tuệ nhân tạo Google Gemini đã được kết nối với dữ liệu vận hành GHN Vùng TNG. "
            "Bây giờ anh/chị có thể thoải mái tag <code>@XetreTNG_Bot</code> để trò chuyện, hỏi đáp và tâm sự như người thật rồi nhé! 🚀✨",
            reply_to_message_id=msg_id
        )

    elif cmd in ("/ai", "/chat"):
        if not args:
            send_telegram_message(bot_token, chat_id, "ℹ️ Cách dùng: <code>/ai &lt;câu hỏi hoặc lời nhắn&gt;</code>\nHoặc chỉ cần tag <code>@XetreTNG_Bot &lt;nội dung&gt;</code> nha!", reply_to_message_id=msg_id)
            return
        threading.Thread(
            target=dispatch_ai_chat,
            args=(args, chat_id, sender_name, msg_id, config),
            daemon=True
        ).start()

def dispatch_ai_chat(text: str, chat_id: int or str, sender_name: str, msg_id: Optional[int], config: dict):
    bot_token = config["BOT_TOKEN"]
    threading.Thread(target=send_chat_action, args=(bot_token, chat_id, "typing"), daemon=True).start()
    try:
        cached_trips = BOT_STATUS.get("latest_trips")
        cached_delayed = BOT_STATUS.get("latest_delayed")
        print(f"[AI Chat] Processing query from {sender_name} ({chat_id}): '{text}'")
        reply = handle_ai_chat(text, sender_name, config, cached_trips=cached_trips, cached_delayed=cached_delayed)
        print(f"[AI Chat] Generated response ({len(reply)} chars): '{reply[:80]}...'")
        sent = send_telegram_message(bot_token, chat_id, reply, reply_to_message_id=msg_id)
        print(f"[AI Chat] Telegram send result: {sent}")
        if not sent:
            clean_reply = re.sub(r'<[^>]+>', '', reply)
            send_telegram_message(bot_token, chat_id, clean_reply, parse_mode=None, reply_to_message_id=None)
    except Exception as e:
        print(f"[ERROR in dispatch_ai_chat]: {e}")
        try:
            err_fallback = f"Dạ em nghe rõ anh/chị {sender_name} rồi ạ! Em vẫn đang túc trực theo dõi xe Vùng TNG 24/7 nhé! 🚚✨"
            send_telegram_message(bot_token, chat_id, err_fallback, parse_mode=None)
        except Exception:
            pass

def telegram_command_worker(config: dict):
    update_offset = None
    print("📡 Telegram Command Listener thread started.")
    while True:
        BOT_STATUS["cmd_worker_alive"] = True
        bot_token = config.get("BOT_TOKEN", "").strip()
        if not bot_token:
            time.sleep(5)
            continue
        try:
            updates = get_telegram_updates(bot_token, offset=update_offset, timeout=5)
            for u in updates:
                update_offset = u["update_id"] + 1
                
                mcm = u.get("my_chat_member")
                if mcm:
                    chat = mcm.get("chat", {})
                    cid = chat.get("id")
                    title = chat.get("title", "")
                    ctype = chat.get("type", "")
                    print(f"🎉 [MY_CHAT_MEMBER] Bot updated in chat {cid} ({title}) [type={ctype}]")

                msg = u.get("message")
                if not msg or "text" not in msg:
                    continue
                
                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                chat_type = chat.get("type", "group")
                sender = msg.get("from", {})
                sender_name = sender.get("first_name", "") or sender.get("username", "anh/chị")
                raw_text = msg.get("text", "").strip()
                msg_id = msg.get("message_id")
                reply_to = msg.get("reply_to_message")
                
                if raw_text.startswith("/"):
                    print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] Command from chat {chat_id}: {raw_text}")
                    try:
                        handle_command(raw_text, chat_id, config, sender_name=sender_name, msg_id=msg_id)
                    except Exception as cmd_err:
                        print(f"[ERROR in handle_command]: {cmd_err}")
                else:
                    if config.get("AI_CHAT_ENABLED", False):
                        lower_text = raw_text.lower()
                        is_private = (chat_type == "private") or (isinstance(chat_id, int) and chat_id > 0)
                        is_tagged = ("@xetretng_bot" in lower_text)
                        is_reply_to_bot = False
                        if reply_to:
                            rep_from = reply_to.get("from", {})
                            if rep_from.get("is_bot") or rep_from.get("username", "").lower().endswith("bot"):
                                is_reply_to_bot = True
                        is_called = any(lower_text.startswith(p) for p in [
                            "bot ơi", "bot oi", "ơi bot", "oi bot", "ê bot", "e bot", 
                            "alo bot", "bot xem", "bot kiểm tra", "bot cho hỏi", "bot tra cứu", "chào bot"
                        ])
                        
                        if is_private or is_tagged or is_reply_to_bot or is_called:
                            clean_text = re.sub(r'@xetretng_bot', '', raw_text, flags=re.IGNORECASE).strip()
                            if not clean_text:
                                clean_text = "Chào bot"
                            print(f"[{datetime.now(VN_TZ).strftime('%H:%M:%S')}] AI Chat from {sender_name} ({chat_id}): {clean_text}")
                            threading.Thread(
                                target=dispatch_ai_chat,
                                args=(clean_text, chat_id, sender_name, msg_id, config),
                                daemon=True
                            ).start()
        except Exception as e:
            print(f"[ERROR in telegram_command_worker]: {e}")
            time.sleep(2)
        time.sleep(0.5)

def ghn_alert_worker(config: dict):
    # ── Startup grace period ─────────────────────────────────────────────────
    STARTUP_GRACE = 60
    print(f"⏳ Startup grace: waiting {STARTUP_GRACE}s before first alert scan...")
    time.sleep(STARTUP_GRACE)
    print("✅ Grace period done — starting alert loop.")
    # ────────────────────────────────────────────────────────────────────────

    consecutive_errors = 0
    consecutive_auth_errors = 0
    token_error_notified = False
    net_error_notified = False
    last_net_error_alert_time = 0

    while True:
        BOT_STATUS["alert_worker_alive"] = True
        bot_token = config.get("BOT_TOKEN", "").strip()
        group_id = config.get("GROUP_ID", -1004334734205)
        poll_interval = config.get("POLL_INTERVAL_SECONDS", 60)
        try:
            threshold = config.get("DELAY_THRESHOLD_MINUTES", 1)
            trips, err, is_expired = fetch_all_active_trips()
            BOT_STATUS["last_scan_time"] = datetime.now(VN_TZ).strftime("%H:%M:%S %d/%m/%Y")
            
            if err:
                print(f"[WARN] GHN API Error: {err}")
                BOT_STATUS["last_scan_status"] = f"Lỗi GHN: {err}"
                BOT_STATUS["last_error"] = err
                consecutive_errors += 1
                
                if is_expired:
                    consecutive_auth_errors += 1
                    BOT_STATUS["consecutive_auth_errors"] = consecutive_auth_errors
                    # Thông báo nếu Token hết hạn 3 lần liên tiếp (3 phút)
                    if consecutive_auth_errors >= 3 and not token_error_notified:
                        msg_token_err = (
                            f"🚨 <b>CẢNH BÁO: TOKEN GHN HẾT HẠN!</b> 📢\n\n"
                            f"Bot không thể lấy dữ liệu hành trình chuyến xe do Token GHN đã hết hiệu lực.\n"
                            f"❌ <b>Chi tiết:</b> <code>{err}</code>\n\n"
                            f"👉 <b>Cách khắc phục:</b> Bạn vui lòng mở tab <code>https://nhanh.ghn.vn/</code> trên trình duyệt máy tính để tự động đồng bộ Token mới nhé!"
                        )
                        send_telegram_message(bot_token, group_id, msg_token_err)
                        token_error_notified = True
                else:
                    # Lỗi mạng / Timeout / Tường lửa chặn
                    now_ts = time.time()
                    if consecutive_errors >= 3 and (not net_error_notified or (now_ts - last_net_error_alert_time > 1800)):
                        msg_net_err = (
                            f"⚠️ <b>CẢNH BÁO SỰ CỐ KẾT NỐI GHN!</b> 📢\n\n"
                            f"Bot gặp gián đoạn kết nối tới cổng máy chủ GHN trong 3 phút qua:\n"
                            f"❌ <b>Chi tiết lỗi:</b> <code>{err}</code>\n\n"
                            f"💡 <b>Hệ thống đang xử lý:</b> Tự động chuyển tiếp sang các kênh định tuyến dự phòng. Hãy kiểm tra lại trang web GHN hoặc mạng nội bộ nếu sự cố kéo dài!"
                        )
                        send_telegram_message(bot_token, group_id, msg_net_err)
                        net_error_notified = True
                        last_net_error_alert_time = now_ts
            else:
                # Nếu vừa phục hồi sau sự cố kéo dài, gửi thông báo báo tin mừng
                if consecutive_errors >= 3 and (token_error_notified or net_error_notified):
                    recovery_msg = (
                        f"🟢 <b>HỆ THỐNG ĐÃ KẾT NỐI LẠI THÀNH CÔNG!</b> 🎉\n\n"
                        f"Bot đã khôi phục liên lạc bình thường với máy chủ GHN.\n"
                        f"📊 Hiện đang tiếp tục theo dõi <b>{len(trips)} chuyến xe</b> Vùng TNG 24/7."
                    )
                    send_telegram_message(bot_token, group_id, recovery_msg)

                consecutive_errors = 0
                consecutive_auth_errors = 0
                token_error_notified = False
                net_error_notified = False
                BOT_STATUS["consecutive_auth_errors"] = 0
                BOT_STATUS["last_error"] = None
                BOT_STATUS["last_scan_status"] = "Hoạt động bình thường"
                BOT_STATUS["total_active_trips"] = len(trips)
                BOT_STATUS["latest_trips"] = trips
                
                delayed_trips = find_all_delayed_trips(trips, threshold_minutes=threshold)
                BOT_STATUS["delayed_trips_count"] = len(delayed_trips)
                BOT_STATUS["latest_delayed"] = delayed_trips
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


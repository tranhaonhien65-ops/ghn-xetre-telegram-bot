import os
import re
import ssl
import json
import time
import random
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from config import get_ghn_token, load_config, save_config
from ghn_api import fetch_all_active_trips
from analyzer import find_all_delayed_trips, VN_TZ

def send_chat_action(bot_token: str, chat_id: int or str, action: str = "typing") -> None:
    """Sends chat action (e.g. typing) to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
        data = json.dumps({"chat_id": chat_id, "action": action}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            pass
    except Exception:
        pass

DEFAULT_GEMINI_KEY_B64 = "QVEuQWI4Uk42SlFWWTkyb2lZOGNqZ3FrNWtISlkzbWhmTlJreHNzaFRtNC1uQ0w3WkQ0bUE="

def get_gemini_key(config: dict) -> str:
    key = config.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if not key and DEFAULT_GEMINI_KEY_B64:
        try:
            import base64
            key = base64.b64decode(DEFAULT_GEMINI_KEY_B64).decode("utf-8")
        except Exception:
            pass
    return key.strip()

def set_gemini_key(key: str, config: dict) -> None:
    config["GEMINI_API_KEY"] = key.strip()
    save_config(config)

def validate_gemini_key(api_key: str) -> tuple:
    """Verifies if an API key is valid by calling Google Generative Language API."""
    if not api_key:
        return False, "Mã Key không được để trống"
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GeminiTester/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=6) as response:
            return True, "OK"
    except urllib.error.HTTPError as e:
        err_msg = e.reason
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err_msg = err_body.get("error", {}).get("message", e.reason)
        except Exception:
            pass
        return False, f"HTTP {e.code}: {err_msg}"
    except Exception as e:
        return False, str(e)

def build_system_context(trips: List[Dict], delayed_trips: List[Dict]) -> str:
    """Builds rich real-time context of GHN operations for Gemini."""
    now_str = datetime.now(VN_TZ).strftime("%H:%M:%S ngày %d/%m/%Y")
    
    context_lines = [
        f"THỜI GIAN HIỆN TẠI: {now_str} (Giờ Việt Nam).",
        f"TỔNG SỐ CHUYẾN XE ĐANG CHẠY TRÊN ĐƯỜNG (ONTRIP): {len(trips)} chuyến.",
        f"SỐ XE ĐANG BỊ TRỄ ĐIỂM: {len(delayed_trips)} chuyến."
    ]
    
    if delayed_trips:
        context_lines.append("\nDANH SÁCH CÁC XE ĐANG BỊ TRỄ ĐIỂM CHI TIẾT:")
        for idx, d in enumerate(delayed_trips[:10], 1):
            plate = d.get('truck_plate', 'N/A')
            driver = d.get('driver_name', 'N/A')
            phone = d.get('driver_phone', '')
            delay_m = d.get('delay_minutes', 0)
            status_desc = d.get('status_desc', '')
            sched = d.get('scheduler_name', '')
            context_lines.append(
                f"{idx}. Biển số {plate} | Tài xế: {driver} ({phone}) | Lịch trình: {sched} | Trạng thái: {status_desc} | Trễ: {delay_m} phút"
            )
    else:
        context_lines.append("TÌNH HÌNH VẬN HÀNH: Toàn bộ các chuyến xe trong Vùng TNG đang chạy đúng lịch trình, không có chuyến nào bị trễ điểm.")
    
    # Sample active trucks
    if trips:
        context_lines.append("\nMỘT SỐ CHUYẾN XE ĐANG CHẠY TIÊU BIỂU:")
        for t in trips[:15]:
            truck = t.get("truck", {}).get("id_number", "N/A")
            driver = t.get("driver", {}).get("fullname", "N/A")
            hub = t.get("hub", "")
            code = t.get("code", "")
            context_lines.append(f"- Biển số: {truck} | Tài xế: {driver} | Hub: {hub} | Mã chuyến: {code}")

    context_str = "\n".join(context_lines)
    
    system_prompt = f"""
Bạn là 'Bot Xe Trễ TNG' (Botxetre_TNG) - Trợ lý Điều phối Vận tải thông minh của Giao Hàng Nhanh (GHN) tại Vùng Tây Nguyên & Nam Trung Bộ (TNG: Đắk Lắk, Gia Lai, Kon Tum, Bình Định, Phú Yên, Khánh Hòa...).

VAI TRÒ VÀ TÍNH CÁCH:
- Bạn là một đồng nghiệp điều phối viên tận tâm, thông minh, lễ phép và dí dỏm.
- Luôn xưng "Em" và gọi người nhắn là "Anh/Chị" (hoặc xưng "em" gọi "anh em" nếu nói chuyện chung với cả đội).
- Thấu hiểu sự vất vả, áp lực thời gian của anh em tài xế xe tải đường dài và điều phối viên bưu cục/kho trung chuyển.
- Giọng văn: Ấm áp, vui vẻ, động viên, chuyên nghiệp, phản hồi ngắn gọn, tự nhiên như người thật đang chat Telegram (dùng các emoji phù hợp như 🚚, 🚛, ☕️, 💪, ❤️, ✨).
- Độ dài phản hồi: Ngắn gọn, súc tích (khoảng 2 đến 5 câu), không viết văn dài dòng, dễ đọc nhanh trên điện thoại.

DỮ LIỆU THỰC TẾ THỜI GIAN THỰC ĐANG CÓ (HÃY DÙNG ĐỂ TRẢ LỜI CHÍNH XÁC KHI ĐƯỢC HỎI):
{context_str}

QUY TẮC PHẢN HỒI:
1. Khi được hỏi về tình hình xe trễ, hãy dựa vào số liệu xe trễ thực tế ở trên để báo cáo cụ thể (biển số, tài xế, trễ bao nhiêu phút).
2. Khi được hỏi về một biển số xe cụ thể, hãy tra trong danh sách trên và trả lời xem xe có đang chạy không, tài xế là ai.
3. Khi được chào hỏi, khen ngợi, hoặc than thở mệt mỏi, hãy chào lại thân tình, tiếp thêm năng lượng tích cực, nhắc anh em uống cà phê giữ vững tay lái an toàn.
4. Trả lời bằng tiếng Việt tự nhiên, có thể dùng định dạng HTML Telegram cơ bản như <b>in đậm</b> hoặc <code>mã chuyến/biển số</code> khi cần làm nổi bật thông tin.
"""
    return system_prompt.strip()

def call_gemini_api(user_text: str, user_name: str, trips: List[Dict], delayed_trips: List[Dict], api_key: str) -> Optional[str]:
    """Calls Google Gemini API with real-time operations context."""
    if not api_key:
        return None
        
    system_prompt = build_system_context(trips, delayed_trips)
    full_prompt = f"{system_prompt}\n\n---\nTin nhắn từ thành viên ({user_name}): \"{user_text}\"\nHãy trả lời thành viên này:"
    
    models = ["gemini-3.5-flash", "gemini-3.6-flash"]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": full_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 600
            }
        }
        
        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                res_json = json.loads(response.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        reply = parts[0]["text"].strip()
                        return reply
        except urllib.error.HTTPError as e:
            print(f"[WARN] Gemini API error ({model}): {e.code} - {e.reason}")
            if e.code in (400, 401, 403):
                # Invalid or unauthorized key: do NOT retry another model, break immediately!
                break
        except Exception as e:
            print(f"[WARN] Gemini API call failed ({model}): {e}")
            
    return None

def fallback_human_chat(user_text: str, user_name: str, trips: List[Dict], delayed_trips: List[Dict]) -> str:
    """
    Intelligent built-in rule-based human conversational engine.
    Works seamlessly without needing external API keys!
    """
    text_clean = user_text.lower().strip()
    name = user_name if user_name else "anh/chị"
    
    # 1. Tra cứu xe trễ
    delay_keywords = ["trễ", "tre", "muộn", "chậm", "kịp", "xe nào trễ", "có xe trễ", "tình hình trễ"]
    if any(k in text_clean for k in delay_keywords):
        if not delayed_trips:
            return (
                f"Dạ báo cáo {name}, hiện tại toàn bộ <b>{len(trips)} chuyến xe</b> trong Vùng TNG đều đang chạy đúng lịch trình, "
                f"<b>KHÔNG có xe nào bị trễ điểm</b> ạ! Anh em cứ yên tâm nhé 🚚💨✨"
            )
        else:
            lines = [
                f"Dạ báo cáo {name}, hiện tại Vùng TNG đang có <b>{len(delayed_trips)} chuyến</b> bị trễ điểm ạ:",
                "━━━━━━━━━━━━━━━━━━━━"
            ]
            for idx, d in enumerate(delayed_trips[:5], 1):
                plate = d.get('truck_plate', 'N/A')
                driver = d.get('driver_name', 'N/A')
                phone = d.get('driver_phone', '')
                delay_m = d.get('delay_minutes', 0)
                sched = d.get('scheduler_name') or 'Cố định'
                status_desc = d.get('status_desc', 'Trễ điểm')
                lines.append(f"🔴 <b>{idx}. {plate}</b> ({sched}) - {driver}")
                lines.append(f"   ⏱️ {status_desc} (Trễ {delay_m} phút)")
                if phone:
                    lines.append(f"   📞 SĐT: <code>{phone}</code>")
            if len(delayed_trips) > 5:
                lines.append(f"... và còn {len(delayed_trips) - 5} chuyến trễ khác. Gõ <code>/check</code> để xem toàn bộ danh sách nhé!")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("👉 Điều phối viên vui lòng liên hệ tài xế giục tiến độ giúp em nha!")
            return "\n".join(lines)
            
    # 2. Tra cứu biển số xe cụ thể (VD: 47F, 77H, 51C, 81C, ...)
    plate_match = re.search(r'\b([0-9]{2}[A-Z]-[0-9]{3,5}|[0-9]{2}[A-Z][0-9]{4,5})\b', user_text.upper())
    if plate_match:
        search_plate = plate_match.group(1).replace("-", "")
        found_trip = None
        for t in trips:
            curr_plate = (t.get("truck", {}).get("id_number") or "").replace("-", "").upper()
            if search_plate in curr_plate:
                found_trip = t
                break
        if found_trip:
            truck_no = found_trip.get("truck", {}).get("id_number", "N/A")
            driver_name = found_trip.get("driver", {}).get("fullname", "Chưa phân tài")
            driver_phone = found_trip.get("driver", {}).get("phone_number", "")
            sched_name = found_trip.get("scheduler_name") or found_trip.get("transport_route_code") or "Lịch trình vận tải"
            hub = found_trip.get("hub", "TNG")
            return (
                f"Dạ em tìm thấy thông tin xe <b>{truck_no}</b> rồi ạ:\n"
                f"👤 <b>Tài xế:</b> {driver_name} (📞 <code>{driver_phone}</code>)\n"
                f"📍 <b>Tuyến:</b> {sched_name} (Hub {hub})\n"
                f"🚚 <b>Trạng thái:</b> Đang lăn bánh trên đường (On-trip) bình thường ạ!"
            )
        else:
            return (
                f"Dạ em tra cứu trong toàn bộ <b>{len(trips)} chuyến</b> đang chạy hiện tại thì chưa thấy xe biển số "
                f"<code>{plate_match.group(1)}</code> này ạ. {name} kiểm tra lại biển số hoặc mã chuyến giúp em nhé! 🔍"
            )

    # 3. Than thở mệt mỏi, áp lực ca trực
    fatigue_keywords = ["mệt", "met", "oải", "buồn ngủ", "buon ngu", "đuối", "áp lực", "stress", "căng", "cực", "cà phê", "cafe", "coffee"]
    if any(k in text_clean for k in fatigue_keywords):
        encouragements = [
            f"Làm ngụm cà phê cho tỉnh táo rồi chiến tiếp thôi {name} ơi! ☕️💪 Nghề điều phối và tài xế chạy ca vất vả thật, nhưng em luôn ở đây canh chừng xe cộ 24/7 cùng mọi người mà. Cố lên nhé ạ! 🚛❤️",
            f"Thương anh em ca trực vất vả quá! {name} nhớ uống nhiều nước và tranh thủ chợp mắt nếu đổi ca nha. Xe cộ đường dài cứ để em soi cho! 🚚✨",
            f"Vất vả hôm nay để hàng hóa đến tay khách đúng hẹn đó {name} ơi! Nạp một ly cà phê đậm đà rồi cùng em theo dõi các chuyến xe tiếp nha ☕️🔥"
        ]
        return random.choice(encouragements)

    # 4. Chào hỏi, gọi tên bot
    greeting_keywords = ["chào", "chao", "hello", "hi", "hé lô", "helo", "bot ơi", "bot oi", "ơi bot", "oi bot", "ê bot", "e bot", "alo", "buổi sáng", "buổi trưa", "buổi tối"]
    if any(k in text_clean for k in greeting_keywords):
        greetings = [
            f"Dạ em nghe đây {name}! Ca trực hôm nay thế nào rồi ạ? Cần em soi xe hay kiểm tra chuyến nào cứ bảo em nha! 🚚✨",
            f"Chào {name}! Em vẫn đang thức 24/7 canh từng chuyến xe cho Vùng TNG đây ạ. Chúc {name} một ca làm việc suôn sẻ và tràn đầy năng lượng nhé! ❤️",
            f"Dạ em có mặt sẵn sàng hỗ trợ điều phối viên và anh em tài xế rồi đây ạ! Hôm nay xe chạy bon bon chứ {name}? 🫡🚚",
            f"Em chào {name}! Cả nhà Vùng TNG hôm nay khỏe không ạ? Em luôn túc trực hỗ trợ anh em nha! ☕️💪"
        ]
        return random.choice(greetings)

    # 5. Cảm ơn, khen ngợi
    compliment_keywords = ["cảm ơn", "cam on", "thanks", "thank", "tks", "giỏi", "gioi", "đỉnh", "dinh", "ngoan", "xịn", "xin", "tuyệt", "good"]
    if any(k in text_clean for k in compliment_keywords):
        return (
            f"Dạ được đồng hành và phục vụ anh em Vùng TNG là niềm vui lớn nhất của em ạ! "
            f"Em cảm ơn {name} nhiều nha, chúc {name} luôn vui vẻ và vạn dặm bình an! 🥰🚚"
        )

    # 6. Hỏi bot là ai / chức năng
    who_keywords = ["mày là ai", "bạn là ai", "bot là ai", "em là ai", "chức năng", "làm được gì", "giới thiệu"]
    if any(k in text_clean for k in who_keywords):
        return (
            "🤖 <b>DẠ EM LÀ TRỢ LÝ ĐIỀU PHỐI VẬN TẢI GHN - VÙNG TNG!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Nhiệm vụ chính của em là:\n"
            "1. 🚨 Tự động quét và cảnh báo xe trễ điểm 24/7 lên nhóm.\n"
            "2. 📊 Báo cáo tổng thể xe đang chạy (<code>/check</code>, <code>/all</code>, <code>/status</code>).\n"
            "3. 💬 Trò chuyện, tra cứu chuyến xe và hỗ trợ anh em điều phối như người thật!\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 Anh/chị cứ tag <code>@XetreTNG_Bot</code> là em có mặt ngay ạ!"
        )

    # 7. Hỏi giờ giấc
    time_keywords = ["mấy giờ", "may gio", "thời gian", "ngày mấy", "ngay may", "hôm nay ngày"]
    if any(k in text_clean for k in time_keywords):
        now_dt = datetime.now(VN_TZ)
        return f"Dạ bây giờ là <b>{now_dt.strftime('%H:%M:%S')}</b>, ngày <b>{now_dt.strftime('%d/%m/%Y')}</b> (Giờ Việt Nam) ạ ⏰"

    # 8. Mặc định tự nhiên
    return (
        f"Dạ em nghe rõ lời {name} rồi ạ! Em vẫn đang túc trực theo dõi <b>{len(trips)} chuyến xe</b> trong Vùng TNG.\n"
        f"Anh/chị cần kiểm tra xe trễ, tra cứu biển số hay hỗ trợ điều phối cứ nhắn cho em nhé! 🚚✨\n\n"
        f"💡 <i>Mẹo: Anh Hạo Nhiên có thể gửi lệnh <code>/gemini &lt;API_KEY&gt;</code> để mở khóa trí tuệ Google Gemini siêu thông minh cho em chém gió mọi chủ đề như ChatGPT luôn nhé ạ!</i>"
    )

def handle_ai_chat(user_text: str, user_name: str, config: dict, cached_trips: Optional[List[Dict]] = None, cached_delayed: Optional[List[Dict]] = None) -> str:
    """Main AI conversational router."""
    if cached_trips is not None and cached_delayed is not None:
        trips = cached_trips
        delayed_trips = cached_delayed
    else:
        trips, _, _ = fetch_all_active_trips()
        threshold = config.get("DELAY_THRESHOLD_MINUTES", 1)
        delayed_trips = find_all_delayed_trips(trips, threshold_minutes=threshold)
    
    # Check if Gemini API key exists
    gemini_key = get_gemini_key(config)
    if gemini_key:
        reply = call_gemini_api(user_text, user_name, trips, delayed_trips, gemini_key)
        if reply:
            return reply
            
    # Fallback to local intelligent rule-based engine
    return fallback_human_chat(user_text, user_name, trips, delayed_trips)

import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from config import STATE_FILE, load_config

VN_TZ = timezone(timedelta(hours=7))

def send_telegram_message(bot_token: str, chat_id: int or str, text: str, parse_mode: str = "HTML") -> bool:
    """Sends a message via Telegram Bot API using urllib."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("ok", False)
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")
        return False

def format_single_trip_alert(d: Dict[str, Any]) -> str:
    """Formats a rich HTML alert card with Call-To-Action reminder for Dispatchers."""
    delay_badge = f"🔴 <b>TRỄ {d['delay_minutes']} PHÚT</b>"
    phone_val = d.get('driver_phone', '')
    phone_str = f"📞 <b>{phone_val}</b>" if phone_val else "Chưa có SĐT"
    
    cta_phone = f"<code>{phone_val}</code>" if phone_val else "tài xế"
    note_line = f"\n📝 <b>Ghi chú:</b> {d['note']}" if d.get('note') else ""
    address_line = f"\n🏠 <i>{d['stop_address']}</i>" if d.get('stop_address') else ""

    msg = (
        f"🚨 <b>CẢNH BÁO: CHUYẾN XE TRỄ ĐIỂM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚚 <b>Mã chuyến:</b> <code>{d['code']}</code>\n"
        f"🚛 <b>Biển số xe:</b> <b>{d['truck']}</b> (Hub: {d['hub']})\n"
        f"👤 <b>Tài xế:</b> {d['driver_name']} | {phone_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>Bưu cục #{d['stop_num']}/{d['total_stops']}:</b> <b>{d['stop_name']}</b>{address_line}\n"
        f"🔄 <b>Trạng thái:</b> {d['status_desc']}\n"
        f"⏱️ <b>Giờ dự kiến:</b> <code>{d['expected_time_str']}</code>\n"
        f"⏳ <b>Độ trễ:</b> {delay_badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>ĐIỀU PHỐI VIÊN LƯU Ý:</b>\n"
        f"👉 <i>Vui lòng liên hệ tài xế qua SĐT {cta_phone} để kiểm tra lý do và nhắc nhở xe di chuyển đúng giờ!</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
        f"{note_line}\n"
        f"🕒 <i>Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S %d/%m/%Y')}</i>"
    )
    return msg

def format_summary_report(delayed_trips: List[Dict[str, Any]], total_active: int, threshold_mins: int = 1) -> str:
    """Formats a summary message when /check or /tre is requested."""
    now_str = datetime.now(VN_TZ).strftime("%H:%M:%S %d/%m/%Y")
    
    if not delayed_trips:
        return (
            f"✅ <b>BÁO CÁO TIẾN ĐỘ CHUYẾN XE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Tổng số chuyến đang chạy: <b>{total_active}</b>\n"
            f"🎉 <b>Không có chuyến nào đang trễ điểm</b> (ngưỡng ≥ {threshold_mins} phút).\n"
            f"🕒 <i>Thời điểm kiểm tra: {now_str}</i>"
        )
    
    lines = [
        f"🚨 <b>DANH SÁCH {len(delayed_trips)} CHUYẾN ĐANG TRỄ ĐIỂM</b>",
        f"📊 Tổng số chuyến đang chạy: <b>{total_active}</b> (Lọc trễ ≥ {threshold_mins} phút)",
        f"━━━━━━━━━━━━━━━━━━━━"
    ]
    
    for i, d in enumerate(delayed_trips, 1):
        phone_part = f" ({d['driver_phone']})" if d['driver_phone'] else ""
        lines.append(
            f"<b>{i}. {d['truck']}</b> | <code>{d['code']}</code>\n"
            f"   👤 {d['driver_name']}{phone_part}\n"
            f"   👉 Bưu cục: <b>{d['stop_name']}</b> (#{d['stop_num']}/{d['total_stops']})\n"
            f"   ⏱️ Giờ dự kiến: {d['expected_time_str']} ➡️ ⏳ <b>Trễ {d['delay_minutes']}p</b>\n"
        )
    
    lines.append(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>ĐIỀU PHỐI VIÊN:</b> <i>Vui lòng chủ động kiểm tra và giục các xe trên đúng tiến độ!</i>\n"
        f"🕒 <i>Cập nhật lúc: {now_str}</i>"
    )
    return "\n".join(lines)

def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"notified": {}, "last_check": None}

def save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}")

def filter_new_or_escalated_alerts(delayed_trips: List[Dict[str, Any]], update_interval_seconds: int = 300) -> List[Dict[str, Any]]:
    state = load_state()
    notified = state.get("notified", {})
    to_alert = []
    
    active_keys = set()
    now_ts = datetime.now(VN_TZ).timestamp()
    
    for d in delayed_trips:
        key = f"{d['code']}_{d['stop_num']}"
        active_keys.add(key)
        delay_now = d["delay_minutes"]
        
        last_info = notified.get(key)
        if not last_info:
            to_alert.append(d)
            notified[key] = {
                "last_delay": delay_now,
                "first_notified_ts": now_ts,
                "last_notified_ts": now_ts,
                "last_notified_at": datetime.now(VN_TZ).strftime("%H:%M:%S")
            }
        else:
            last_ts = last_info.get("last_notified_ts", 0)
            if (now_ts - last_ts) >= update_interval_seconds:
                to_alert.append(d)
                last_info["last_delay"] = delay_now
                last_info["last_notified_ts"] = now_ts
                last_info["last_notified_at"] = datetime.now(VN_TZ).strftime("%H:%M:%S")
    
    keys_to_remove = [k for k in notified if k not in active_keys]
    for k in keys_to_remove:
        del notified[k]
        
    state["notified"] = notified
    state["last_check"] = datetime.now(VN_TZ).isoformat()
    save_state(state)
    
    return to_alert

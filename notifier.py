import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from config import STATE_FILE, load_config

VN_TZ = timezone(timedelta(hours=7))

import re
import urllib.error

def send_telegram_message(bot_token: str, chat_id: int or str, text: str, parse_mode: Optional[str] = "HTML") -> bool:
    """Sends a message via Telegram Bot API using urllib, with automatic fallback to plain text if HTML parsing fails."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    for mode in [parse_mode, None]:
        clean_text = text if mode else re.sub(r'<[^>]+>', '', text)
        payload = {
            "chat_id": chat_id,
            "text": clean_text,
            "disable_web_page_preview": True
        }
        if mode:
            payload["parse_mode"] = mode
            
        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                if res_data.get("ok"):
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 400 and mode == "HTML":
                # Fallback to plain text on next attempt
                continue
            print(f"[ERROR] Failed to send Telegram message: {e}")
            break
        except Exception as e:
            print(f"[ERROR] Failed to send Telegram message: {e}")
            break
            
    return False

def format_single_trip_alert(d: Dict[str, Any]) -> str:
    """Formats a clean, airy HTML alert card with Call-To-Action reminder for Dispatchers."""
    phone_val = d.get('driver_phone', '')
    phone_str = f"📞 <code>{phone_val}</code>" if phone_val else "Chưa có SĐT"
    schedule_name = d.get('scheduler_name') or 'Lịch trình cố định'
    
    cta_phone = f"<code>{phone_val}</code>" if phone_val else "tài xế"
    hub_part = f" (Hub: {d['hub']})" if d.get('hub') else ""

    msg = (
        f"🚨 <b>CẢNH BÁO: CHUYẾN XE TRỄ ĐIỂM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚚 <b>Mã chuyến:</b> <code>{d['code']}</code>\n"
        f"📋 <b>Lịch trình:</b> <b>{schedule_name}</b>\n"
        f"🚛 <b>Biển số xe:</b> <b>{d['truck']}</b>{hub_part}\n"
        f"👤 <b>Tài xế:</b> {d['driver_name']} | {phone_str}\n\n"
        f"📍 <b>Điểm đến:</b> <b>{d['stop_name']}</b> (#{d['stop_num']}/{d['total_stops']})\n"
        f"🔄 <b>Trạng thái:</b> {d['status_desc']}\n"
        f"⏱️ <b>Giờ dự kiến:</b> <code>{d['expected_time_str']}</code>\n"
        f"⏳ <b>Độ trễ:</b> 🔴 <b>TRỄ {d['delay_minutes']} PHÚT</b>\n\n"
        f"📢 <b>ĐIỀU PHỐI VIÊN LƯU Ý:</b>\n"
        f"👉 <i>Vui lòng liên hệ SĐT {cta_phone} để kiểm tra lý do và giục xe di chuyển đúng giờ!</i>\n\n"
        f"🕒 <i>Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S • %d/%m/%Y')}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
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
        s_name = d.get('scheduler_name') or 'Lịch trình cố định'
        lines.append(
            f"<b>{i}. {d['truck']}</b> | <code>{d['code']}</code> | Tuyến: <b>{s_name}</b>\n"
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


# ── In-memory state cache (survives within a Render session) ──────────────
_state_cache: Dict[str, Any] = {}
_is_first_run: bool = True        # True until the first full scan completes

def load_state() -> Dict[str, Any]:
    global _state_cache
    if _state_cache:
        return _state_cache
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                _state_cache = json.load(f)
                return _state_cache
        except Exception:
            pass
    _state_cache = {"notified": {}, "last_check": None}
    return _state_cache

def save_state(state: Dict[str, Any]):
    global _state_cache
    _state_cache = state
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}")

def filter_new_or_escalated_alerts(delayed_trips: List[Dict[str, Any]], update_interval_seconds: int = 600) -> List[Dict[str, Any]]:
    global _is_first_run
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
            # New delayed trip: on first run after restart, skip trips delayed < 5 min
            # to avoid spamming when Render reboots with many already-delayed trips.
            if _is_first_run and delay_now < 5:
                # Record silently — will alert on next cycle if still delayed
                notified[key] = {
                    "last_delay": delay_now,
                    "first_notified_ts": now_ts,
                    "last_notified_ts": now_ts - update_interval_seconds,  # allow alert next cycle
                    "last_notified_at": None,
                    "silent_start": True
                }
            else:
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
                last_info.pop("silent_start", None)

    keys_to_remove = [k for k in notified if k not in active_keys]
    for k in keys_to_remove:
        del notified[k]

    state["notified"] = notified
    state["last_check"] = datetime.now(VN_TZ).isoformat()
    save_state(state)

    _is_first_run = False
    return to_alert

import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

VN_TZ = timezone(timedelta(hours=7))

def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str or dt_str.startswith("0001") or dt_str.startswith("1970"):
        return None
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(dt_str)
        return dt.astimezone(VN_TZ)
    except Exception:
        return None

def analyze_trip_delay(trip: Dict[str, Any], now_dt: datetime, threshold_minutes: int = 1) -> Optional[Dict[str, Any]]:
    """
    Analyzes a single trip:
    - Ignores disabled/skipped stops (disable == True).
    - Trễ khi tới: Trạng thái = 'Trễ giờ tới bưu cục <Tên Bưu Cục>'
    - Trễ khi rời: Trạng thái = 'Trễ giờ rời bưu cục <Tên Bưu Cục>'
    """
    code = trip.get("code", "N/A")
    truck_info = trip.get("truck") or {}
    truck_plate = truck_info.get("id_number") or "N/A"
    
    driver_info = trip.get("driver") or {}
    driver_name = driver_info.get("fullname") or "Chưa phân tài"
    driver_phone = driver_info.get("phone") or ""
    
    hub = trip.get("hub") or ""
    note = trip.get("note") or ""
    schedule_type = trip.get("schedule_type") or "FIXED"
    scheduler_name = trip.get("scheduler_name") or trip.get("transport_route_code") or ("Tăng cường" if schedule_type == "EXTRA" else "Lịch trình cố định")
    
    rp_list = trip.get("router_path") or []
    pr_list = trip.get("partner_router") or []
    
    rp_map = {s.get("sort_number"): s for s in rp_list if isinstance(s, dict)}
    pr_map = {s.get("sort_number"): s for s in pr_list if isinstance(s, dict)}
    
    all_sorts = sorted(set(list(rp_map.keys()) + list(pr_map.keys())))
    total_stops = len(all_sorts)
    
    for s_num in all_sorts:
        pr_s = pr_map.get(s_num, {})
        rp_s = rp_map.get(s_num, {})
        
        stop_name = pr_s.get("name") or rp_s.get("code") or f"Bưu cục {s_num}"
        stop_address = pr_s.get("address") or ""
        status = pr_s.get("status") or "new"
        
        # Kiểm tra BỎ ĐIỂM
        is_disabled = (
            pr_s.get("disable") is True or 
            rp_s.get("disable") is True or 
            pr_s.get("is_deleted") is True or
            pr_s.get("is_skip") is True or
            pr_s.get("is_cancel") is True
        )
        
        eta_in_dt = parse_iso_datetime(rp_s.get("estimate_time_in_at"))
        eta_out_dt = parse_iso_datetime(rp_s.get("estimate_time_out_at"))
        check_in_dt = parse_iso_datetime(pr_s.get("check_in_at"))
        check_out_dt = parse_iso_datetime(pr_s.get("check_out_at"))
        
        # 1. Bỏ qua nếu Bưu cục BỎ ĐIỂM hoặc ĐÃ HOÀN THÀNH
        if is_disabled or status == "finished" or check_out_dt:
            continue
            
        # 2. TRỄ KHI RỜI: Xe đang ở bưu cục (status: processing, đã check-in nhưng chưa check-out)
        if status == "processing" and not check_out_dt:
            target_eta_out = eta_out_dt if eta_out_dt else eta_in_dt
            if target_eta_out and now_dt > target_eta_out:
                delay_mins = int((now_dt - target_eta_out).total_seconds() / 60)
                if delay_mins >= threshold_minutes:
                    return {
                        "code": code,
                        "truck": truck_plate,
                        "driver_name": driver_name,
                        "driver_phone": driver_phone,
                        "hub": hub,
                        "stop_num": s_num,
                        "total_stops": total_stops,
                        "stop_name": stop_name,
                        "stop_address": stop_address,
                        "delay_type": "Chuyến xe trễ điểm",
                        "status_desc": f"Trễ giờ rời bưu cục {stop_name}",
                        "expected_time_str": target_eta_out.strftime("%H:%M (%d/%m)"),
                        "delay_minutes": delay_mins,
                        "note": note,
                        "schedule_type": schedule_type,
                        "scheduler_name": scheduler_name
                    }
            break

        # 3. TRỄ KHI TỚI: Xe đang di chuyển đến bưu cục (status: new, chưa check-in)
        elif status == "new" and not check_in_dt:
            if eta_in_dt and now_dt > eta_in_dt:
                delay_mins = int((now_dt - eta_in_dt).total_seconds() / 60)
                if delay_mins >= threshold_minutes:
                    return {
                        "code": code,
                        "truck": truck_plate,
                        "driver_name": driver_name,
                        "driver_phone": driver_phone,
                        "hub": hub,
                        "stop_num": s_num,
                        "total_stops": total_stops,
                        "stop_name": stop_name,
                        "stop_address": stop_address,
                        "delay_type": "Chuyến xe trễ điểm",
                        "status_desc": f"Trễ giờ tới bưu cục {stop_name}",
                        "expected_time_str": eta_in_dt.strftime("%H:%M (%d/%m)"),
                        "delay_minutes": delay_mins,
                        "note": note,
                        "schedule_type": schedule_type,
                        "scheduler_name": scheduler_name
                    }
            break

    return None

def find_all_delayed_trips(trips: List[Dict[str, Any]], threshold_minutes: int = 1) -> List[Dict[str, Any]]:
    now_dt = datetime.now(VN_TZ)
    delayed = []
    for trip in trips:
        res = analyze_trip_delay(trip, now_dt, threshold_minutes)
        if res:
            delayed.append(res)
    delayed.sort(key=lambda x: x["delay_minutes"], reverse=True)
    return delayed

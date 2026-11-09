import os
import sys
import json
import ssl
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SSO_TOKEN_FILE = BASE_DIR / "ghn_sso_token.txt"
GHN_TOKEN_FILE = BASE_DIR / "ghn_token.txt"
METABASE_JWT_FILE = BASE_DIR / "metabase_jwt.txt"

VN_TZ = timezone(timedelta(hours=7))

TELEGRAM_BOT_TOKEN = "8873673112:AAETU8x7w7q-oQiDYN3wLxuQWLVklBFK580"
TELEGRAM_CHAT_ID = "-1001812292793"  # Nhóm KTC Bình Định - Vận Tải

from sl_generator import load_dictionaries, process_orders
from sl_excel import generate_report_file
from sl_renderer import render_overview_image

def get_sso_token():
    if SSO_TOKEN_FILE.exists():
        t = SSO_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if t:
            return t
    if GHN_TOKEN_FILE.exists():
        return GHN_TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""

def get_metabase_jwt(force_refresh=False):
    # 1. Kiểm tra JWT hiện tại nếu còn hạn trên 15 phút
    if not force_refresh and METABASE_JWT_FILE.exists():
        try:
            token = METABASE_JWT_FILE.read_text(encoding="utf-8").strip()
            if token:
                import base64
                part = token.split('.')[1]
                part += '=' * (-len(part) % 4)
                pl = json.loads(base64.urlsafe_b64decode(part))
                exp = pl.get("exp", 0)
                now_sec = int(time.time())
                if exp - now_sec > 900:  # Còn hạn > 15 phút
                    return token
        except Exception:
            pass

    # 2. Tự động gia hạn qua API baocao-api với baocao_session.json hoặc token_report.txt
    session_file = BASE_DIR / "baocao_session.json"
    rep_token, rep_ip = "", "not_found"
    if session_file.exists():
        try:
            s_data = json.loads(session_file.read_text(encoding="utf-8"))
            rep_token = s_data.get("token", "")
            rep_ip = s_data.get("ip", "not_found")
        except Exception:
            pass

    if not rep_token:
        report_token_file = BASE_DIR / "token_report.txt"
        if report_token_file.exists():
            rep_token = report_token_file.read_text(encoding="utf-8").strip()

    if rep_token:
        try:
            url = "https://baocao-api.ghn.vn/baocao-service/report/dashboard/metabase-token"
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "origin": "https://baocao.ghn.vn",
                "referer": "https://baocao.ghn.vn/",
                "token": rep_token,
                "remote-ip": rep_ip,
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            }
            payload = {"user_id": 3007413, "dashboard_id": 221}
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            d = r.json()
            new_jwt = d.get("data", {}).get("token")
            if new_jwt:
                METABASE_JWT_FILE.write_text(new_jwt.strip(), encoding="utf-8")
                print("🔄 [AUTO-REFRESH] Tự động gia hạn Metabase JWT thành công (12 tiếng mới)!")
                return new_jwt.strip()
        except Exception as e:
            print(f"[WARN] Lỗi khi tự động gia hạn Metabase JWT: {e}")

    if METABASE_JWT_FILE.exists():
        return METABASE_JWT_FILE.read_text(encoding="utf-8").strip()
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3OTQxNTA3MTcsInBhcmFtcyI6eyJ1c2VyX2lkIjoiMzAwNzQxMyJ9LCJyZXNvdXJjZSI6eyJkYXNoYm9hcmQiOjIyMX19.kyH1qAUikrOYLN0kHyrvZ4r_bVuTpMiaW25ksB1621E"

def fetch_trip_stop_info(code, sso_token, target_eta=None):
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {sso_token}",
        "origin": "https://nhanh.ghn.vn",
        "referer": "https://nhanh.ghn.vn/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }
    url = f"https://inside-prd-api.ghn.vn/tms/v1/transportation/detail?code={code}&status=SEARCH&locationId=20335000&locationType=GHN_HUB"
    try:
        r = requests.get(url, headers=headers, timeout=8)
        data = r.json()
        trip_data = data.get("data", [{}])[0]
        plate = trip_data.get("partnerVehicleNumber", "")
        stops = [s for s in trip_data.get("stopsInfo", []) if str(s.get("locationId")) == "20335000"]
        if not stops:
            return None
        
        matched_stop = stops[0]
        if len(stops) > 1 and target_eta:
            def time_diff(s):
                exp = s.get("expectedArrivalTime")
                if not exp: return 999999999
                try:
                    dt = datetime.fromisoformat(exp.replace("Z", "+00:00")).astimezone(VN_TZ)
                    return abs((dt - target_eta).total_seconds())
                except Exception:
                    return 999999999
            matched_stop = min(stops, key=time_diff)

        exp_arr = matched_stop.get("expectedArrivalTime")
        exp_dep = matched_stop.get("expectedDepartureTime")
        act_arr = matched_stop.get("arrivalTime")
        act_dep = matched_stop.get("departureTime")
        status = matched_stop.get("status")

        exp_arr_dt = datetime.fromisoformat(exp_arr.replace("Z", "+00:00")).astimezone(VN_TZ) if exp_arr else None
        exp_dep_dt = datetime.fromisoformat(exp_dep.replace("Z", "+00:00")).astimezone(VN_TZ) if exp_dep else None
        act_arr_dt = datetime.fromisoformat(act_arr.replace("Z", "+00:00")).astimezone(VN_TZ) if act_arr else None
        act_dep_dt = datetime.fromisoformat(act_dep.replace("Z", "+00:00")).astimezone(VN_TZ) if act_dep else None

        return {
            "plate": plate,
            "status": status,
            "exp_arr_dt": exp_arr_dt,
            "exp_dep_dt": exp_dep_dt,
            "act_arr_dt": act_arr_dt,
            "act_dep_dt": act_dep_dt
        }
    except Exception as e:
        print(f"[WARN] Lỗi tra cứu chi tiết chuyến {code}: {e}")
        return None

def fetch_trip_stop_times(code, sso_token, target_eta=None):
    info = fetch_trip_stop_info(code, sso_token, target_eta)
    if info:
        return info["exp_arr_dt"], info["exp_dep_dt"], info["plate"]
    return None, None, ""

CACHE_FILE = BASE_DIR / "daily_trips_cache.json"

def load_cached_trips():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cached_trips(cache):
    try:
        now_dt = datetime.now(VN_TZ)
        pruned = {}
        for code, t in cache.items():
            eta_str = t.get("expectedArrivalTime")
            if eta_str:
                try:
                    vn_dt = datetime.fromisoformat(eta_str.replace("Z", "+00:00")).astimezone(VN_TZ)
                    if abs((now_dt - vn_dt).total_seconds()) > 172800:  # > 48 tiếng thì dọn dẹp
                        continue
                except Exception:
                    pass
            pruned[code] = t
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(pruned, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Lỗi khi lưu trips cache: {e}")

def fetch_trips_for_shift(shift="ca_dem", target_date=None, sso_token=None):
    if not sso_token:
        sso_token = get_sso_token()
    if not target_date:
        target_date = datetime.now(VN_TZ)

    start_local = (target_date - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = (target_date + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
    
    start_utc = (start_local - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_utc = (end_local - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S.999Z")

    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {sso_token}",
        "content-type": "application/json",
        "origin": "https://nhanh.ghn.vn",
        "referer": "https://nhanh.ghn.vn/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }

    payload = {
        "offset": 0, "limit": 100, "partnerTransportationCode": "", "vehiclePlate": "",
        "startTime": start_utc, "endTime": end_utc,
        "locationId": "20335000", "locationType": "GHN_HUB",
        "source": "INSIDE_WEB_APP/ktc-van-tai/transport/initialization"
    }

    all_raw_trips = []
    seen_codes = set()
    live_upcoming_codes = set()
    live_arrived_codes = set()

    # 1. Xe sắp đến kho (trên đường tới)
    url_up = "https://inside-prd-api.ghn.vn/tms/v1/transportation/get-upcoming-transports"
    try:
        r = requests.post(url_up, json=payload, headers=headers, timeout=12)
        res = r.json()
        data_field = res.get("data")
        trips = data_field[0].get("list", []) if isinstance(data_field, list) and data_field else []
        for t in trips:
            code = t.get("partnerTransportationCode")
            if code and code not in seen_codes:
                seen_codes.add(code)
                live_upcoming_codes.add(code)
                t["tab"] = "Sắp đến kho"
                all_raw_trips.append(t)
    except Exception as e:
        print(f"[WARN] Lỗi khi gọi get-upcoming-transports: {e}")

    # 2. Xe đã đến kho
    url_arr = "https://inside-prd-api.ghn.vn/tms/v1/transportation/get-arrived-transports"
    try:
        r = requests.post(url_arr, json=payload, headers=headers, timeout=12)
        res = r.json()
        data_field = res.get("data")
        trips = data_field[0].get("list", []) if isinstance(data_field, list) and data_field else []
        for t in trips:
            code = t.get("partnerTransportationCode")
            if code:
                live_arrived_codes.add(code)
                if code not in seen_codes:
                    seen_codes.add(code)
                    t["tab"] = "Đã đến kho"
                    all_raw_trips.append(t)
                else:
                    for ex in all_raw_trips:
                        if ex.get("partnerTransportationCode") == code:
                            ex["tab"] = "Đã đến kho"
                            if t.get("arrivalTime"):
                                ex["arrivalTime"] = t.get("arrivalTime")
    except Exception as e:
        print(f"[WARN] Lỗi khi gọi get-arrived-transports: {e}")

    # Đồng bộ với bộ nhớ đệm cache chuyến đi trong ngày (tránh mất các xe đã rời kho)
    cached_trips = load_cached_trips()
    for t in all_raw_trips:
        code = t.get("partnerTransportationCode")
        if code:
            cached_trips[code] = t

    for code, t in cached_trips.items():
        if code not in seen_codes:
            seen_codes.add(code)
            # Xe trong cache không nằm trong danh sách live upcoming/arrived nghĩa là đã rời kho hoặc hoàn thành
            t["tab"] = "Đã rời kho"
            all_raw_trips.append(t)
    save_cached_trips(cached_trips)

    is_ca2 = shift in ("ca_sang", "ca_ngay", "ca2", "ca_2", "ca 2")
    if is_ca2:
        shift_std_start = datetime(target_date.year, target_date.month, target_date.day, 5, 0, 0, tzinfo=VN_TZ)
        shift_std_end = datetime(target_date.year, target_date.month, target_date.day, 9, 0, 0, tzinfo=VN_TZ)
        rollover_start = shift_std_start - timedelta(hours=12) # Các xe ca đêm hôm trước
    else:
        shift_std_start = datetime(target_date.year, target_date.month, target_date.day, 9, 0, 0, tzinfo=VN_TZ)
        shift_std_end = datetime(target_date.year, target_date.month, target_date.day, 5, 0, 0, tzinfo=VN_TZ) + timedelta(days=1)
        rollover_start = datetime(target_date.year, target_date.month, target_date.day, 5, 0, 0, tzinfo=VN_TZ) # Các xe ca ngày hôm nay

    def get_origin_location(code):
        q_param = json.dumps({"transportationCode": code})
        url_hist = f"https://inside-prd-api.ghn.vn/lms/v1/tms-history?q={requests.utils.quote(q_param)}&offset=0&limit=1&locationId=20335000&locationType=GHN_HUB&source=INSIDE_WEB_APP/ktc-van-tai/transport/detail"
        try:
            r = requests.get(url_hist, headers=headers, timeout=8)
            d_hist = r.json()
            if d_hist.get("data"):
                return d_hist["data"][0].get("locationName", "")
        except Exception:
            pass
        return ""

    matched_trips = []
    for t in all_raw_trips:
        code = t.get("partnerTransportationCode")
        if not code:
            continue
        eta_str = t.get("expectedArrivalTime")
        if not eta_str:
            continue
        type_ops = (t.get("typeOps") or "").lower()
        if type_ops == "pickup":
            continue
        try:
            utc_dt = datetime.fromisoformat(eta_str.replace("Z", "+00:00"))
            vn_dt = utc_dt.astimezone(VN_TZ)
            
            matched = False
            note_shift = ""

            if shift_std_start < vn_dt <= shift_std_end:
                # Xe có lịch dự kiến tới trong ca hiện tại
                # Kiểm tra nếu xe đã rời kho trước khi ca bắt đầu -> không thuộc ca này
                dep_str = t.get("departureTime")
                if dep_str:
                    try:
                        dep_vn = datetime.fromisoformat(dep_str.replace("Z", "+00:00")).astimezone(VN_TZ)
                        if dep_vn < shift_std_start:
                            continue
                    except Exception:
                        pass
                matched = True

            elif rollover_start <= vn_dt <= shift_std_start:
                # Xe có lịch dự kiến ở ca trước.
                # CHỈ được tính dồn sang ca hiện tại nếu:
                # 1. Xe THỰC SỰ ĐANG TRÊN ĐƯỜNG tới (nằm trong live_upcoming_codes của API hiện tại)
                # 2. Hoặc xe có thời gian thực tế đến kho trong ca này (actualArrivalTime >= shift_std_start)
                if code in live_upcoming_codes:
                    matched = True
                    note_shift = "Trễ từ Ca Đêm sang" if is_ca2 else "Trễ từ Ca Ngày sang"
                else:
                    arr_time = t.get("arrivalTime")
                    if not arr_time:
                        stop_info = fetch_trip_stop_info(code, sso_token, target_eta=vn_dt)
                        if stop_info:
                            if stop_info.get("act_arr_dt"):
                                arr_time = stop_info["act_arr_dt"].isoformat()
                                t["arrivalTime"] = arr_time
                            if stop_info.get("act_dep_dt"):
                                t["departureTime"] = stop_info["act_dep_dt"].isoformat()
                            if stop_info.get("status") == "COMPLETED":
                                t["tab"] = "Đã rời kho"

                    if arr_time:
                        try:
                            arr_vn = datetime.fromisoformat(arr_time.replace("Z", "+00:00")).astimezone(VN_TZ)
                            if arr_vn >= shift_std_start:
                                matched = True
                                note_shift = "Trễ từ Ca Đêm sang" if is_ca2 else "Trễ từ Ca Ngày sang"
                        except Exception:
                            pass

            if matched:
                code = t.get("partnerTransportationCode")
                r_name = (t.get("routeScheduleName") or "").strip().upper()
                
                is_linehaul = False
                if r_name.startswith(("HY", "HN", "HCM")):
                    is_linehaul = True
                else:
                    origin = get_origin_location(code).upper()
                    if any(k in origin for k in ["HƯNG YÊN", "HUNG YEN", "HÀ NỘI", "HA NOI", "HỒ CHÍ MINH", "HO CHI MINH", "HCM", "TÂN BÌNH", "BÌNH TÂN"]):
                        is_linehaul = True
                        if any(k in origin for k in ["HƯNG YÊN", "HUNG YEN"]):
                            t["routeScheduleName"] = "HY_BĐ_TĂNG CƯỜNG"
                        elif any(k in origin for k in ["HỒ CHÍ MINH", "HO CHI MINH", "HCM", "TÂN BÌNH", "BÌNH TÂN"]):
                            t["routeScheduleName"] = "HCM_BĐ_TĂNG CƯỜNG"
                        elif any(k in origin for k in ["HÀ NỘI", "HA NOI"]):
                            t["routeScheduleName"] = "HN_BĐ_TĂNG CƯỜNG"
                        else:
                            t["routeScheduleName"] = "KTC_TRỤC_NGOÀI"

                if is_linehaul:
                    t["note_shift"] = note_shift
                    matched_trips.append((t, vn_dt))
        except Exception:
            continue

    matched_trips.sort(key=lambda x: x[1])
    return matched_trips

def extract_packages_for_trips(trips_list, sso_token):
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {sso_token}",
        "origin": "https://nhanh.ghn.vn",
        "referer": "https://nhanh.ghn.vn/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }

    all_packages = set()
    trip_to_pkgs = {}
    valid_matched_trips = []

    for t, eta in trips_list:
        code = t.get("partnerTransportationCode")
        tab = t.get("tab", "")
        r_name = t.get("routeScheduleName", "")
        
        offset = 0
        limit = 1000
        all_events = []

        while True:
            q_param = json.dumps({"transportationCode": code})
            url = f"https://inside-prd-api.ghn.vn/lms/v1/tms-history?q={requests.utils.quote(q_param)}&offset={offset}&limit={limit}&locationId=20335000&locationType=GHN_HUB&source=INSIDE_WEB_APP/ktc-van-tai/transport/detail"
            try:
                r = requests.get(url, headers=headers, timeout=8)
                data = r.json().get("data", [])
                if not data:
                    break
                all_events.extend(data)
                if len(data) < limit:
                    break
                offset += limit
            except Exception:
                break

        if not all_events:
            continue

        all_events.sort(key=lambda x: x.get("actionTime") or "")
        first_event = all_events[0]
        first_loc_id = str(first_event.get("locationId") or "")
        first_loc_name = first_event.get("locationName") or ""

        if first_loc_id == "20335000" or "Bình Định" in first_loc_name or "BĐ" in first_loc_name:
            continue

        trip_pkgs = set()
        for row in all_events:
            row_loc_id = str(row.get("locationId") or "")
            if row_loc_id == "20335000":
                continue
            for p in (row.get("packageCode") or []):
                if p and str(p).startswith("26"):
                    trip_pkgs.add(str(p).strip())
            for item in (row.get("itemDetail") or []):
                p = item.get("packageCode")
                if p and str(p).startswith("26"):
                    trip_pkgs.add(str(p).strip())

        if len(trip_pkgs) > 0:
            all_packages.update(trip_pkgs)
            trip_to_pkgs[code] = trip_pkgs
            valid_matched_trips.append((t, eta, len(trip_pkgs)))
        else:
            print(f"⚠️ Bỏ qua chuyến xe rỗng không có kiện về Bình Định: {code}")

    return sorted(list(all_packages)), trip_to_pkgs, valid_matched_trips

def fetch_metabase_orders(packages, jwt_token=None):
    if not packages:
        return []
    if not jwt_token:
        jwt_token = get_metabase_jwt()

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "referer": "https://baocao.ghn.vn/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "x-metabase-client": "embedding-simple",
        "x-metabase-embed-referrer": "https://baocao.ghn.vn/dashboards/69fee592e08b65ce62cf5aa9",
        "x-metabase-locale": "en"
    }

    all_rows = []
    batch_size = 150
    total_batches = (len(packages) + batch_size - 1) // batch_size
    print(f"\n📦 Đang truy vấn Metabase cho {len(packages)} mã kiện trong {total_batches} đợt...")

    for b_idx, i in enumerate(range(0, len(packages), batch_size), start=1):
        batch = packages[i:i+batch_size]
        p_val = requests.utils.quote(json.dumps(batch))
        url = f"https://data-bi.ghn.vn/api/embed/dashboard/{jwt_token}/dashcard/3090/card/2738?parameters=%7B%22m%25C3%25A3_ki%25E1%25BB%2587n%22%3A{p_val}%7D"
        
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code in (400, 401) and ("expired" in r.text.lower() or "token" in r.text.lower() or r.status_code == 401):
                print("⚠️ [Metabase] Token hết hạn (400/401), đang tự động làm mới qua phiên Báo Cáo...")
                jwt_token = get_metabase_jwt(force_refresh=True)
                url = f"https://data-bi.ghn.vn/api/embed/dashboard/{jwt_token}/dashcard/3090/card/2738?parameters=%7B%22m%25C3%25A3_ki%25E1%25BB%2587n%22%3A{p_val}%7D"
                r = requests.get(url, headers=headers, timeout=60)
            res = r.json()
            rows = res.get("data", {}).get("rows", [])
            all_rows.extend(rows)
            if b_idx % 5 == 0 or b_idx == total_batches:
                print(f"  ✓ Đã xong {b_idx}/{total_batches} đợt ({len(all_rows)} đơn)...")
        except Exception as e:
            print(f"  ✗ Đợt {b_idx} lỗi: {e}")

    return all_rows

def run_pipeline(shift="ca1", target_date=None):
    sso_token = get_sso_token()
    if not sso_token:
        print("[ERROR] SSO token is missing!")
        return

    if not target_date:
        dt = datetime.now(VN_TZ)
    else:
        dt = target_date

    is_ca2 = str(shift).lower() in ("ca2", "ca_2", "ca_sang", "ca_ngay", "ca 2")
    shift_code = "ca2" if is_ca2 else "ca1"
    shift_label = "Ca 2 (Ca Ngày)" if is_ca2 else "Ca 1 (Ca Đêm)"
    date_str = dt.strftime("%d/%m/%Y")
    print(f"\n=================================================================")
    print(f"🚀 TỰ ĐỘNG TẠO BÁO CÁO SL BD ({shift_label} - Ngày {date_str})")
    print(f"=================================================================")

    matched_trips = fetch_trips_for_shift(shift, dt, sso_token)
    print(f"🚚 Tìm thấy {len(matched_trips)} chuyến xe {shift_label}")

    packages, trip_to_pkgs, valid_matched_trips = extract_packages_for_trips(matched_trips, sso_token)
    print(f"📦 Tổng cộng thu thập được: {len(packages)} mã kiện duy nhất.")

    if not packages or not valid_matched_trips:
        print("⚠️ Không có kiện hàng / chuyến xe nào hợp lệ trong ca này.")
        orders_rows = []
    else:
        orders_rows = fetch_metabase_orders(packages)
        print(f"✅ Lấy thành công: {len(orders_rows)} đơn hàng từ Metabase.")

    ma_to_ten, ten_to_tuyen = load_dictionaries(shift=shift_code)
    processed_orders, summary_routes, bc_orders = process_orders(orders_rows, ma_to_ten, ten_to_tuyen, shift=shift_code)

    valid_route_names = set(s['tuyen'] for s in summary_routes)
    pkg_to_valid_orders_cnt = {}
    for ord_item in processed_orders:
        if ord_item['tuyen'] in valid_route_names:
            pkg_code = ord_item['package']
            pkg_to_valid_orders_cnt[pkg_code] = pkg_to_valid_orders_cnt.get(pkg_code, 0) + 1

    truck_data = []
    for t, eta, pkg_cnt in valid_matched_trips:
        code = t.get("partnerTransportationCode")
        plate = t.get("vehiclePlate") or ""
        rname = t.get("routeScheduleName") or "N/A"
        
        detail_arr, detail_dep, detail_plate = fetch_trip_stop_times(code, sso_token)
        if detail_plate:
            plate = detail_plate
        
        eta_dt = detail_arr if detail_arr else eta
        etd_dt = detail_dep

        eta_str = eta_dt.strftime("%d/%m %H:%M") if eta_dt else "--"
        etd_str = etd_dt.strftime("%d/%m %H:%M") if etd_dt else "--"

        pkgs = trip_to_pkgs.get(code, set())
        orders_cnt = sum(pkg_to_valid_orders_cnt.get(p, 0) for p in pkgs)
        truck_data.append({
            "code": code,
            "plate": plate if plate else "N/A",
            "route": rname,
            "eta": eta_str,
            "etd": etd_str,
            "pkgs": len(pkgs),
            "orders": orders_cnt,
            "note_shift": t.get("note_shift", "")
        })

    # 1. Render ảnh tổng quan trước
    out_img = BASE_DIR / f"SL_BD_{shift_code}_overview.png"
    render_overview_image(summary_routes, bc_orders, shift=shift_code, out_path=out_img)

    total_table_1 = sum(s['so_don'] for s in summary_routes if s['tuyen'] != "GHN HOÀI NHƠN" or s['so_don'] > 0)
    if is_ca2:
        bd_total = sum(s['so_don'] for s in summary_routes if s['tuyen'] in ['BĐ 02', 'BĐ 06', 'BĐ 12', 'GL 05'])
        py_total = total_table_1 - bd_total
    else:
        bd_total = sum(s['so_don'] for s in summary_routes if any(k in s['tuyen'] for k in ['BĐ 0', 'BĐ 1', 'BD 1', 'DN', 'GL']))
        py_total = total_table_1 - bd_total

    # Gửi ảnh và danh sách xe trục lên Telegram NGAY LẬP TỨC
    print("📤 Đang gửi ảnh tổng quan và danh sách xe trục lên Telegram...")
    send_telegram_photo_and_trucks(
        shift_label=shift_label,
        target_date=dt,
        total_orders=total_table_1,
        bd_total=bd_total,
        py_total=py_total,
        truck_data=truck_data,
        img_path=str(out_img)
    )

    # 2. Xuất file Excel nhẹ và gửi tiếp file Excel
    out_excel = BASE_DIR / f"SL_BD_{shift_code}.xlsx"
    generate_report_file(processed_orders, summary_routes, bc_orders, shift=shift_code, out_file=out_excel)

    if out_excel.exists():
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
            with open(out_excel, "rb") as f:
                caption = f"📁 File chi tiết sản lượng {shift_label}: SL BD {shift_code}.xlsx ({total_table_1:,} đơn)"
                requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"document": f}, timeout=40)
                print("  ✓ Đã gửi file Excel lên Telegram.")
        except Exception as e:
            print(f"  ✗ Lỗi gửi file Excel Telegram: {e}")

def send_telegram_photo_and_trucks(shift_label, target_date, total_orders, bd_total, py_total, truck_data, img_path):
    bot_token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    date_str = target_date.strftime("%d/%m/%Y")

    # 1. GỬI ẢNH TỔNG QUAN
    if Path(img_path).exists():
        try:
            caption_photo = f"📊 <b>BẢNG TỔNG QUAN SẢN LƯỢNG KTC BÌNH ĐỊNH - {shift_label.upper()} ({date_str})</b>\n📦 Tổng đơn: <b>{total_orders:,} đơn</b> (Bình Định: <b>{bd_total:,}</b> | Phú Yên: <b>{py_total:,}</b>)"
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(img_path, "rb") as f:
                r = requests.post(url, data={"chat_id": chat_id, "caption": caption_photo, "parse_mode": "HTML"}, files={"photo": f}, timeout=30)
                print("  ✓ Đã gửi ảnh tổng quan sản lượng lên Telegram.")
        except Exception as e:
            print(f"  ✗ Lỗi gửi ảnh Telegram: {e}")

    # 2. GỬI DANH SÁCH XE TRỤC
    try:
        lines = [
            f"🚚 <b>DANH SÁCH XE TRỤC VỀ TRONG {shift_label.upper()} ({date_str})</b>",
            "━━━━━━━━━━━━━━━━━━━━"
        ]
        if truck_data:
            total_truck_pkgs = 0
            total_truck_orders = 0
            for idx, tr in enumerate(truck_data, start=1):
                code = tr['code']
                plate = tr['plate']
                route = tr['route']
                eta = tr['eta']
                etd = tr['etd']
                pkgs = tr['pkgs']
                orders = tr['orders']
                total_truck_pkgs += pkgs
                total_truck_orders += orders

                note_label = f" ⚠️ <b>({tr['note_shift']})</b>" if tr.get('note_shift') else ""
                lines.append(f"<b>{idx}. <code>{code}</code></b> ({route}) | <b>{plate}</b>{note_label}")
                lines.append(f"   ⏱️ Dự kiến: Tới <b>{eta}</b> | Rời: <b>{etd}</b>")
                lines.append(f"   📦 Chở về: <b>{pkgs:,} kiện</b> | <b>{orders:,} đơn</b>\n")

            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"🎯 <b>TỔNG CỘNG:</b> <b>{len(truck_data)} xe trục</b> | <b>{total_truck_pkgs:,} kiện</b> | <b>{total_truck_orders:,} đơn</b>")
        else:
            lines.append("<i>Không có xe trục về trong ca.</i>")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("🎯 <b>TỔNG CỘNG:</b> <b>0 xe trục</b> | <b>0 kiện</b> | <b>0 đơn</b>")

        truck_msg = "\n".join(lines)
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": truck_msg, "parse_mode": "HTML"}, timeout=15)
        print("  ✓ Đã gửi danh sách xe trục lên Telegram.")
    except Exception as e:
        print(f"  ✗ Lỗi gửi danh sách xe trục Telegram: {e}")

def run_sl_scheduler():
    print("⏰ SL Reporter Scheduler Thread running (Render 24/7)...")
    print("   • Ca Sáng: Gửi cố định lúc 07:00 sáng hàng ngày")
    print("   • Ca Đêm:  Gửi cố định lúc 15:00 chiều hàng ngày")

    last_run_day_sang = -1
    last_run_day_dem = -1

    while True:
        try:
            now = datetime.now(VN_TZ)
            cur_day = now.day
            hour = now.hour
            minute = now.minute

            # 07:00 -> Ca Sáng
            if hour == 7 and minute >= 0 and last_run_day_sang != cur_day:
                last_run_day_sang = cur_day
                run_pipeline(shift="ca_sang")

            # 15:00 -> Ca Đêm
            if hour == 15 and minute >= 0 and last_run_day_dem != cur_day:
                last_run_day_dem = cur_day
                run_pipeline(shift="ca_dem")
        except Exception as e:
            print(f"[ERROR in SL Scheduler]: {e}")

        time.sleep(20)

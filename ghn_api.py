import json
import ssl
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Optional
from config import get_ghn_token

API_URL = "https://truck-gw.ghn.vn/api/v1/staff/trip/find_trip"
VN_TZ = timezone(timedelta(hours=7))

_ACTIVE_PROXY = None
FALLBACK_PROXIES = [
    "4.144.146.21:80",
    "8.219.94.23:7890",
    "185.194.121.232:8085"
]

def make_request_with_fallback(req, timeout=6):
    global _ACTIVE_PROXY
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if _ACTIVE_PROXY:
        try:
            handler = urllib.request.ProxyHandler({"https": f"http://{_ACTIVE_PROXY}"})
            opener = urllib.request.build_opener(handler)
            return opener.open(req, timeout=timeout)
        except Exception as e:
            _ACTIVE_PROXY = None

    try:
        return urllib.request.urlopen(req, context=ctx, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as net_err:
        if isinstance(net_err, urllib.error.HTTPError):
            raise net_err
        for p in FALLBACK_PROXIES:
            try:
                handler = urllib.request.ProxyHandler({"https": f"http://{p}"})
                opener = urllib.request.build_opener(handler)
                resp = opener.open(req, timeout=timeout)
                _ACTIVE_PROXY = p
                print(f"🛡️ [ROUTING] Kết nối qua Proxy dự phòng ({p}) thành công!")
                return resp
            except urllib.error.HTTPError as he:
                _ACTIVE_PROXY = p
                raise he
            except Exception:
                continue
        raise net_err

def fetch_trips_page(token: str, page: int = 1, retries: int = 2) -> Tuple[Optional[dict], Optional[str], bool]:
    """
    Fetches a single page of active trips from GHN API with 7-day date filter (identical to web UI).
    """
    now = datetime.now(VN_TZ)
    now_ts = int(now.timestamp())
    from_ts = int((now - timedelta(days=7)).timestamp())
    
    payload = {
        "status": ["ontrip"],
        "types": [4, 6],
        "process_from_to": [from_ts, now_ts],
        "page": page
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "origin": "https://nhanh.ghn.vn",
        "referer": "https://nhanh.ghn.vn/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    
    for attempt in range(retries):
        current_token = get_ghn_token()
        headers["authorization"] = f"Bearer {current_token}"
        req = urllib.request.Request(API_URL, data=data_bytes, headers=headers, method="PATCH")
        
        try:
            with make_request_with_fallback(req, timeout=6) as response:
                res_body = response.read().decode("utf-8")
                return json.loads(res_body), None, False
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return None, f"HTTP {e.code}: Token GHN đã hết hạn.", True
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return None, f"HTTP Error {e.code}: {e.reason}", False
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3)
                continue
            return None, f"Lỗi kết nối mạng: {str(e)}", False
            
    return None, "Không nhận được phản hồi từ GHN", False

def fetch_all_active_trips(token: Optional[str] = None) -> Tuple[List[Dict], Optional[str], bool]:
    """
    Fetches all active trips across all pages.
    """
    if not token:
        token = get_ghn_token()
    
    all_trips = []
    page = 1
    total_pages = 1
    
    while page <= total_pages:
        data, error, is_expired = fetch_trips_page(token, page)
        if error:
            return all_trips, error, is_expired
        
        if not data:
            break
            
        trips = data.get("trips", [])
        all_trips.extend(trips)
        
        paging = data.get("paging", {})
        total_pages = paging.get("total_page", 1)
        
        if page >= total_pages or not trips:
            break
        page += 1
        
    return all_trips, None, False

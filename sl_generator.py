import os
import json
import xml.etree.ElementTree as ET
import zipfile
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def load_dictionaries():
    mapping_json = BASE_DIR / "mappings.json"
    if mapping_json.exists():
        try:
            with open(mapping_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ma_to_ten", {}), data.get("ten_to_tuyen", {})
        except Exception as e:
            print(f"[WARN] Lỗi đọc mappings.json: {e}")
    return {}, {}

def process_orders(rows, ma_to_ten, ten_to_tuyen):
    ROUTE_CAPACITY = {
        "BĐ 01": ("5T", 1500),
        "BĐ 03": ("1T9", 700),
        "BĐ 04": ("1T9", 700),
        "BĐ 05": ("1T9", 700),
        "BĐ 08": ("1T9", 700),
        "BĐ 12": ("1T9", 700),
        "BD 13": ("1T9", 700),
        "BĐ 14": ("1T9", 700),
        "BĐ PY 01": ("1T9", 700),
        "BĐ PY 02": ("5T", 1500),
        "BĐ PY 03": ("1T9", 700),
        "BĐ PY 06": ("1T9", 700),
        "BĐ PY 06_01": ("1T9", 700),
        "BĐ PY 08": ("1T9", 700),
        "DN_BD_KH": ("5T", 1500),
        "DN-QNG-BD": ("5T", 1500),
        "GL_BD_01": ("1T9", 700),
        "GHN BÌNH ĐỊNH": ("N/A", 0),
    }

    processed_orders = []
    route_orders = {}
    bc_orders = {}

    ten_to_tuyen_lower = {k.strip().lower(): v.strip() for k, v in ten_to_tuyen.items()}

    for r in rows:
        pkg = str(r[0]) if len(r) > 0 and r[0] is not None else ""
        tg = str(r[1]) if len(r) > 1 and r[1] is not None else ""
        order_code = str(r[2]) if len(r) > 2 and r[2] is not None else ""
        kho_gui = str(r[3]) if len(r) > 3 and r[3] is not None else ""
        kho_nhan = str(r[4]) if len(r) > 4 and r[4] is not None else ""
        kho_ht = str(r[5]) if len(r) > 5 and r[5] is not None else ""
        kho_giao_id = str(r[6]) if len(r) > 6 and r[6] is not None else ""
        tt = str(r[7]) if len(r) > 7 and r[7] is not None else ""

        if not kho_giao_id or kho_giao_id not in ma_to_ten:
            continue

        ten_kho_giao = ma_to_ten.get(kho_giao_id, f"Kho {kho_giao_id}")
        tuyen = ten_to_tuyen.get(ten_kho_giao)
        if not tuyen:
            tuyen = ten_to_tuyen_lower.get(ten_kho_giao.strip().lower(), "Chưa phân tuyến")

        # QUY TẮC YÊU CẦU: Sản lượng kho GHN Hoài Nhơn (22168000) bỏ vào tuyến xe BĐ 12
        if kho_giao_id == "22168000" or ("hoài nhơn" in ten_kho_giao.lower() and "nặng" in ten_kho_giao.lower()):
            tuyen = "BĐ 12"
        elif tuyen.strip().upper() == "GHN HOÀI NHƠN":
            tuyen = "BĐ 12"

        processed_orders.append({
            "package": pkg,
            "tg": tg,
            "order": order_code,
            "kho_gui": kho_gui,
            "kho_nhan": kho_nhan,
            "kho_ht": kho_ht,
            "kho_giao_id": kho_giao_id,
            "ten_kho_giao": ten_kho_giao,
            "tuyen": tuyen,
            "status": tt
        })

        if tuyen:
            route_orders[tuyen] = route_orders.get(tuyen, 0) + 1
        if ten_kho_giao:
            bc_orders[ten_kho_giao] = bc_orders.get(ten_kho_giao, 0) + 1

    summary_routes = []
    for route, (tai_trong, cap) in ROUTE_CAPACITY.items():
        so_don = route_orders.get(route, 0)
        pct = (so_don / cap) * 100.0 if cap > 0 else 0.0
        note = "Rớt" if (cap > 0 and pct > 100.0) else "Không Rớt"
        summary_routes.append({
            "tuyen": route,
            "so_don": so_don,
            "pct": pct,
            "note": note,
            "tai_trong": tai_trong
        })

    return processed_orders, summary_routes, bc_orders

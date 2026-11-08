import sys
import os
from pathlib import Path
import openpyxl

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "SL_BD_ca1_template.xlsx"

def generate_report_file(orders_data, route_summary, bc_counts, out_file=None):
    if out_file is None:
        out_file = BASE_DIR / "SL_BD_ca1.xlsx"
    out_file = Path(out_file)

    wb = openpyxl.load_workbook(str(TEMPLATE_PATH))
    ws_data = wb['NHẬP DATA']
    ws_summary = wb['TỔNG QUAN']

    # 1. Fill NHẬP DATA
    for idx, ord_item in enumerate(orders_data, start=2):
        ws_data.cell(row=idx, column=1, value=ord_item.get('package'))
        ws_data.cell(row=idx, column=2, value=ord_item.get('tg'))
        ws_data.cell(row=idx, column=3, value=ord_item.get('order'))
        ws_data.cell(row=idx, column=4, value=ord_item.get('kho_gui'))
        ws_data.cell(row=idx, column=5, value=ord_item.get('kho_nhan'))
        ws_data.cell(row=idx, column=6, value=ord_item.get('kho_ht'))
        ws_data.cell(row=idx, column=7, value=ord_item.get('kho_giao_id'))
        ws_data.cell(row=idx, column=8, value=ord_item.get('status'))
        ws_data.cell(row=idx, column=12, value=ord_item.get('ten_kho_giao'))
        ws_data.cell(row=idx, column=13, value=ord_item.get('tuyen'))

    # 2. Update TỔNG QUAN
    route_row_map = {}
    for r in range(3, 23):
        rt_name = ws_summary.cell(row=r, column=1).value
        if rt_name:
            clean_name = str(rt_name).strip()
            route_row_map[clean_name] = r

    for item in route_summary:
        rt = item['tuyen']
        r_idx = route_row_map.get(rt)
        if r_idx:
            ws_summary.cell(row=r_idx, column=2, value=item['so_don'])

    total_table_1 = sum(item['so_don'] for item in route_summary)
    for r in range(3, 25):
        a_val = ws_summary.cell(row=r, column=1).value
        if a_val and 'grand' in str(a_val).lower():
            ws_summary.cell(row=r, column=2, value=total_table_1)
            break
    else:
        ws_summary.cell(row=22, column=2, value=total_table_1)

    # Middle table (Bình Định): Column G is BC name / Route, Column H is SỐ ĐƠN
    total_bd = 0
    for r in range(3, ws_summary.max_row + 1):
        g_val = ws_summary.cell(row=r, column=7).value
        if g_val:
            g_str = str(g_val).strip()
            if 'grand' in g_str.lower():
                continue
            if g_str in route_row_map:
                val = next((x['so_don'] for x in route_summary if x['tuyen'] == g_str), 0)
                ws_summary.cell(row=r, column=8, value=val)
            elif g_str in bc_counts:
                val = bc_counts[g_str]
                ws_summary.cell(row=r, column=8, value=val)
                total_bd += val

    for r in range(3, ws_summary.max_row + 1):
        g_val = ws_summary.cell(row=r, column=7).value
        if g_val and 'grand' in str(g_val).lower():
            ws_summary.cell(row=r, column=8, value=total_bd)

    # Right table (Phú Yên): Column J is BC name / Route, Column K is SỐ ĐƠN
    total_py = 0
    for r in range(3, ws_summary.max_row + 1):
        j_val = ws_summary.cell(row=r, column=10).value
        if j_val:
            j_str = str(j_val).strip()
            if 'grand' in j_str.lower():
                continue
            if j_str in route_row_map:
                val = next((x['so_don'] for x in route_summary if x['tuyen'] == j_str), 0)
                ws_summary.cell(row=r, column=11, value=val)
            elif j_str in bc_counts:
                val = bc_counts[j_str]
                ws_summary.cell(row=r, column=11, value=val)
                total_py += val

    for r in range(3, ws_summary.max_row + 1):
        j_val = ws_summary.cell(row=r, column=10).value
        if j_val and 'grand' in str(j_val).lower():
            ws_summary.cell(row=r, column=11, value=total_py)

    wb.save(str(out_file))
    print(f"✅ Generated {out_file} successfully! Total orders: {len(orders_data)} (Table 1: {total_table_1}, BD: {total_bd}, PY: {total_py})")
    return total_table_1, total_bd, total_py

import sys
import os
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

BASE_DIR = Path(__file__).resolve().parent

def get_bc_val(bc_counts, bc_name):
    if not bc_name:
        return 0
    if bc_name in bc_counts:
        return bc_counts[bc_name]
    v1 = bc_name.replace(" - ", "-")
    if v1 in bc_counts:
        return bc_counts[v1]
    v2 = bc_name.replace("-", " - ")
    if v2 in bc_counts:
        return bc_counts[v2]
    clean_target = bc_name.strip().lower()
    for k, v in bc_counts.items():
        if k.strip().lower() == clean_target:
            return v
    # Check partial match for Tây Sơn 44
    if "44" in bc_name and "tây sơn" in clean_target:
        for k, v in bc_counts.items():
            if "44" in k and "tây sơn" in k.lower():
                return v
    # Check partial match for Hoài Nhơn Nam
    if "hoài nhơn nam" in clean_target:
        for k, v in bc_counts.items():
            if "hoài nhơn nam" in k.lower():
                return v
    # Check partial match for Hai Riềng
    if "hai riêng" in clean_target:
        for k, v in bc_counts.items():
            if "hai riêng" in k.lower():
                return v
    return 0

def match_route(route_name, grp_name):
    if not route_name or not grp_name:
        return False
    r1 = route_name.replace("_", " ").replace("Đ", "D").replace("đ", "d").strip().upper()
    g1 = grp_name.replace("_", " ").replace("Đ", "D").replace("đ", "d").strip().upper()
    return r1 == g1

def generate_report_file(orders_data, route_summary, bc_counts, shift="ca1", out_file=None):
    is_ca2 = str(shift).lower() in ("ca2", "ca_2", "ca_sang", "ca_ngay", "ca 2")
    if out_file is None:
        default_fn = "SL_BD_ca2.xlsx" if is_ca2 else "SL_BD_ca1.xlsx"
        out_file = BASE_DIR / default_fn
    out_file = Path(out_file)

    wb = openpyxl.Workbook()

    # Define styles
    font_header = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    font_bold = Font(name="Arial", size=11, bold=True, color="000000")
    font_body = Font(name="Arial", size=10, color="000000")
    font_rot = Font(name="Arial", size=11, bold=True, color="C00000")
    font_khong_rot = Font(name="Arial", size=11, bold=True, color="C00000") # or 833C0C
    font_grp = Font(name="Arial", size=11, bold=True, color="385723")

    fill_t1_head = PatternFill(start_color="385723", end_color="385723", fill_type="solid")
    fill_note_head = PatternFill(start_color="833C0C", end_color="833C0C", fill_type="solid")
    fill_t2_head = PatternFill(start_color="833C0C", end_color="833C0C", fill_type="solid")
    fill_grp = PatternFill(start_color="C5E0B4", end_color="C5E0B4", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='BFBFBF'),
        right=Side(style='thin', color='BFBFBF'),
        top=Side(style='thin', color='BFBFBF'),
        bottom=Side(style='thin', color='BFBFBF')
    )

    # 1. SHEET: TỔNG QUAN
    ws_sum = wb.active
    ws_sum.title = 'TỔNG QUAN'

    # Table 1 Header (A2:E2)
    t1_headers = [
        ('A', 'Tuyến Xe', fill_t1_head),
        ('B', 'SỐ ĐƠN', fill_t1_head),
        ('C', 'Tỉ Lệ Thùng Xe', fill_t1_head),
        ('D', 'Note', fill_note_head),
        ('E', 'TẢI TRỌNG', fill_t1_head)
    ]
    for col, text, fill in t1_headers:
        c = ws_sum[f'{col}2']
        c.value = text
        c.font = font_header
        c.fill = fill
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = thin_border

    # Table 1 Data Rows
    total_table_1 = 0
    cur_r = 3
    for item in route_summary:
        tuyen = item['tuyen']
        so_don = item['so_don']
        if tuyen == "GHN HOÀI NHƠN" and so_don == 0:
            continue
        total_table_1 += so_don
        pct = item.get('pct', 0.0)
        pct_str = f"{pct:.0f}%" if pct > 0 else "0%"
        note = item.get('note', 'Không Rớt')
        tai_trong = item.get('tai_trong', '')
        if tai_trong == 'N/A':
            tai_trong = ''

        vals = [
            ('A', tuyen, font_bold, Alignment(horizontal='center')),
            ('B', so_don, font_body, Alignment(horizontal='right')),
            ('C', pct_str, font_body, Alignment(horizontal='center')),
            ('D', note, font_rot if note == 'Rớt' else font_khong_rot, Alignment(horizontal='center')),
            ('E', tai_trong, font_body, Alignment(horizontal='center'))
        ]
        for col, val, fnt, aln in vals:
            c = ws_sum[f'{col}{cur_r}']
            c.value = val
            c.font = fnt
            c.alignment = aln
            c.border = thin_border
        cur_r += 1

    # Table 1 Grand Total
    ws_sum[f'A{cur_r}'] = 'Grand Total'
    ws_sum[f'A{cur_r}'].font = font_bold
    ws_sum[f'A{cur_r}'].border = thin_border
    ws_sum[f'B{cur_r}'] = total_table_1
    ws_sum[f'B{cur_r}'].font = font_bold
    ws_sum[f'B{cur_r}'].border = thin_border

    # Table 2: BÌNH ĐỊNH (G2:H2)
    c_g = ws_sum['G2']
    c_g.value = 'TÊN TUYẾN XE'
    c_g.font = font_header
    c_g.fill = fill_t2_head
    c_g.alignment = Alignment(horizontal='center')
    c_g.border = thin_border

    c_h = ws_sum['H2']
    c_h.value = 'SỐ ĐƠN'
    c_h.font = font_header
    c_h.fill = fill_t2_head
    c_h.alignment = Alignment(horizontal='center')
    c_h.border = thin_border

    if is_ca2:
        bd_groups = [
            ("BĐ 02", [
                "Bưu Cục Số 35 Phạm Văn Đồng-Tăng Bạt Hổ-Hoài Ân-Bình Định",
                "Kho Giao Hàng Nặng Hoài Nhơn-Bình Định",
                "Bưu Cục 838 Quang Trung-Phường Hoài Nhơn Tây-Bình Định",
                "Bưu Cục Thôn Chánh Hóa-Xã Cát Tiến-Bình Định"
            ]),
            ("BĐ 06", [
                "Bưu Cục 269 Tây Sơn-Quy Nhơn-Bình Định",
                "Bưu Cục 767 Hùng Vương-Quy Nhơn-Bình Định",
                "Bưu Cục 263 Đống Đa-Quy Nhơn-Bình Định",
                "Bưu Cục 396 Âu Cơ-Bùi Thị Xuân-Quy Nhơn-Bình Định",
                "Bưu Cục 571 Trần Phú-Tuy Phước-Bình Định"
            ]),
            ("BĐ 12", [
                "Bưu Cục Đường 3 Tháng 2-Xã Phù Cát-Bình Định",
                "Bưu Cục 21 Tây Sơn-Xã Phù Mỹ-Bình Định",
                "Bưu Cục 107 Nguyễn Lữ-Phù Mỹ-Bình Định",
                "(BDI) Hoài Nhơn Nam 1"
            ]),
            ("GL 05", [
                "Bưu Cục 44 Quang Trung-Tây Sơn-Bình Định",
                "Bưu Cục Khu Vực Kim Châu-An Nhơn-Bình Định",
                "Bưu Cục Vận Hành Thôn Định Trị-Xã Vĩnh Thạnh-Bình Định"
            ])
        ]
    else:
        bd_groups = [
            ("BD 13", ["Bưu Cục Vận Hành Thôn Định Trị-Xã Vĩnh Thạnh-Bình Định", "Bưu Cục 61 Quang Trung-Xã Vân Canh-Bình Định"]),
            ("BD 01", ["Bưu Cục Thôn Xuân Phong Nam-An Lão-Bình Định", "(BDI) Hoài Nhơn Nam 1"]),
            ("BD 03", ["Bưu Cục 269 Tây Sơn-Quy Nhơn-Bình Định", "Bưu Cục 396 Âu Cơ-Bùi Thị Xuân-Quy Nhơn-Bình Định", "Bưu Cục 263 Đống Đa-Quy Nhơn-Bình Định"]),
            ("BD 04", ["Bưu Cục Đường 3 Tháng 2-Xã Phù Cát-Bình Định"]),
            ("BD 05", ["Bưu Cục 21 Tây Sơn-Xã Phù Mỹ-Bình Định", "Bưu Cục 107 Nguyễn Lữ-Phù Mỹ-Bình Định"]),
            ("BD 08", ["Bưu Cục 767 Hùng Vương-Quy Nhơn-Bình Định", "Bưu Cục Khu Vực Kim Châu-An Nhơn-Bình Định"]),
            ("BD 12", ["Kho Giao Hàng Nặng Hoài Nhơn-Bình Định", "Bưu Cục Số 35 Phạm Văn Đồng-Tăng Bạt Hổ-Hoài Ân-Bình Định"]),
            ("BD 14", ["Bưu Cục Thôn Chánh Hóa-Xã Cát Tiến-Bình Định", "(BDI) Tuy Phước Đông"]),
            ("DN_BD_KH", ["Bưu Cục 571 Trần Phú-Tuy Phước-Bình Định"]),
            ("DN-QNG-BD", ["Bưu Cục 838 Quang Trung-Phường Hoài Nhơn Tây-Bình Định"]),
            ("GL_BD_01", ["Bưu Cục 44 Quang Trung-Tây Sơn-Bình Định"])
        ]

    total_bd = 0
    t2_r = 3
    for grp_name, bc_list in bd_groups:
        grp_sum = sum(get_bc_val(bc_counts, bc) for bc in bc_list)
        rt_match = next((x for x in route_summary if match_route(x["tuyen"], grp_name)), None)
        if grp_name == "BD 12":
            grp_sum = sum(get_bc_val(bc_counts, bc) for bc in bc_list)
        elif rt_match and rt_match["so_don"] > 0:
            grp_sum = rt_match["so_don"]
        total_bd += grp_sum

        # Grp row
        c_g = ws_sum[f'G{t2_r}']
        c_g.value = f"= {grp_name}"
        c_g.font = font_grp
        c_g.fill = fill_grp
        c_g.alignment = Alignment(horizontal='center')
        c_g.border = thin_border

        c_h = ws_sum[f'H{t2_r}']
        c_h.value = grp_sum
        c_h.font = font_grp
        c_h.fill = fill_grp
        c_h.alignment = Alignment(horizontal='right')
        c_h.border = thin_border
        t2_r += 1

        for bc in bc_list:
            b_val = get_bc_val(bc_counts, bc)
            c_g = ws_sum[f'G{t2_r}']
            c_g.value = bc
            c_g.font = font_body
            c_g.alignment = Alignment(horizontal='center')
            c_g.border = thin_border

            c_h = ws_sum[f'H{t2_r}']
            c_h.value = b_val
            c_h.font = font_body
            c_h.alignment = Alignment(horizontal='right')
            c_h.border = thin_border
            t2_r += 1

    ws_sum[f'G{t2_r}'] = 'Grand Total'
    ws_sum[f'G{t2_r}'].font = font_bold
    ws_sum[f'G{t2_r}'].border = thin_border
    ws_sum[f'H{t2_r}'] = total_bd
    ws_sum[f'H{t2_r}'].font = font_bold
    ws_sum[f'H{t2_r}'].border = thin_border

    # Table 3: PHÚ YÊN (J2:K2)
    c_j = ws_sum['J2']
    c_j.value = 'TÊN TUYẾN XE'
    c_j.font = font_header
    c_j.fill = fill_t2_head
    c_j.alignment = Alignment(horizontal='center')
    c_j.border = thin_border

    c_k = ws_sum['K2']
    c_k.value = 'SỐ ĐƠN'
    c_k.font = font_header
    c_k.fill = fill_t2_head
    c_k.alignment = Alignment(horizontal='center')
    c_k.border = thin_border

    if is_ca2:
        py_groups = [
            ("BĐ PY 04", [
                "Bưu cục 27 Nguyễn Tất Thành-Tuy Hòa-Phú Yên",
                "Bưu Cục Thôn Đông Phước-Phú Hòa-Phú Yên",
                "Bưu cục DT644-Sông Cầu-Phú Yên"
            ]),
            ("BĐ PY 07", [
                "Bưu Cục KP4 Hòa Vinh- Đông Hòa- Phú yên",
                "Bưu Cục Thị Trấn Phú Thứ-Tây Hoà-Phú Yên"
            ]),
            ("BĐ PY 09", [
                "Bưu Cục 274 Hùng Vương-Tuy Hòa-Phú Yên",
                "Bưu Cục 71 Quốc Lộ 1A-Xã Tuy An Bắc-Phú Yên",
                "Bưu Cục Đường Tỉnh 643-Xã Tuy An Nam-Phú Yên"
            ]),
            ("PY03 TC", [
                "Bưu cục 138 Trần Phú-Đồng Xuân-Phú Yên",
                "Bưu Cục 61 Quang Trung-Xã Vân Canh-Bình Định",
                "BƯU CỤC KHU PHỐ 3 - THỊ TRẤN HAI RIÊNG-SÔNG HÌNH-PHÚ YÊN",
                "Bưu Cục Suối Bạc-Sơn Hòa-Phú Yên"
            ])
        ]
    else:
        py_groups = [
            ("BD PY 01", ["Bưu Cục KP4 Hòa Vinh- Đông Hòa- Phú yên", "Bưu Cục Thị Trấn Phú Thứ-Tây Hoà-Phú Yên"]),
            ("BD PY 02", ["Bưu Cục 274 Hùng Vương-Tuy Hòa-Phú Yên", "Kho Giao Hàng Nặng Phú Yên"]),
            ("BD PY 03", ["Bưu cục 138 Trần Phú-Đồng Xuân-Phú Yên", "BƯU CỤC KHU PHỐ 3 - THỊ TRẤN HAI RIÊNG-SÔNG HÌNH-PHÚ YÊN", "Bưu Cục Suối Bạc-Sơn Hòa-Phú Yên"]),
            ("BD PY 06", ["Bưu cục DT644-Sông Cầu-Phú Yên", "Bưu cục 27 Nguyễn Tất Thành-Tuy Hòa-Phú Yên"]),
            ("BD PY 06_01", ["Bưu Cục Thôn Đông Phước-Phú Hòa-Phú Yên"]),
            ("BD PY 08", ["Bưu Cục 71 Quốc Lộ 1A-Xã Tuy An Bắc-Phú Yên", "Bưu Cục Đường Tỉnh 643-Xã Tuy An Nam-Phú Yên"]),
            ("GHN BÌNH ĐỊNH", ["Kho Giao Hàng Nặng Bình Định"])
        ]

    total_py = 0
    t3_r = 3
    for grp_name, bc_list in py_groups:
        grp_sum = sum(get_bc_val(bc_counts, bc) for bc in bc_list)
        rt_match = next((x for x in route_summary if match_route(x["tuyen"], grp_name)), None)
        if rt_match and rt_match["so_don"] > 0:
            grp_sum = rt_match["so_don"]
        total_py += grp_sum

        c_j = ws_sum[f'J{t3_r}']
        c_j.value = f"= {grp_name}"
        c_j.font = font_grp
        c_j.fill = fill_grp
        c_j.alignment = Alignment(horizontal='center')
        c_j.border = thin_border

        c_k = ws_sum[f'K{t3_r}']
        c_k.value = grp_sum
        c_k.font = font_grp
        c_k.fill = fill_grp
        c_k.alignment = Alignment(horizontal='right')
        c_k.border = thin_border
        t3_r += 1

        for bc in bc_list:
            b_val = get_bc_val(bc_counts, bc)
            c_j = ws_sum[f'J{t3_r}']
            c_j.value = bc
            c_j.font = font_body
            c_j.alignment = Alignment(horizontal='center')
            c_j.border = thin_border

            c_k = ws_sum[f'K{t3_r}']
            c_k.value = b_val
            c_k.font = font_body
            c_k.alignment = Alignment(horizontal='right')
            c_k.border = thin_border
            t3_r += 1

    ws_sum[f'J{t3_r}'] = 'Grand Total'
    ws_sum[f'J{t3_r}'].font = font_bold
    ws_sum[f'J{t3_r}'].border = thin_border
    ws_sum[f'K{t3_r}'] = total_py
    ws_sum[f'K{t3_r}'].font = font_bold
    ws_sum[f'K{t3_r}'].border = thin_border

    # Adjust Column Widths
    ws_sum.column_dimensions['A'].width = 16
    ws_sum.column_dimensions['B'].width = 12
    ws_sum.column_dimensions['C'].width = 15
    ws_sum.column_dimensions['D'].width = 14
    ws_sum.column_dimensions['E'].width = 13
    ws_sum.column_dimensions['F'].width = 4
    ws_sum.column_dimensions['G'].width = 50
    ws_sum.column_dimensions['H'].width = 12
    ws_sum.column_dimensions['I'].width = 4
    ws_sum.column_dimensions['J'].width = 50
    ws_sum.column_dimensions['K'].width = 12

    # 2. SHEET: NHẬP DATA
    ws_data = wb.create_sheet('NHẬP DATA')
    headers_data = ['Mã kiện', 'TG đóng kiện', 'Mã đơn', 'Kho gửi', 'Kho nhận', 'Kho hiện tại', 'Kho giao', 'Trạng thái hiện tại', 'Tên Kho Gửi', 'Tên kho Nhận', 'Tên Kho Hiện Tại', 'Tên Kho Giao', 'Tuyến Xe']
    ws_data.append(headers_data)

    for ord_item in orders_data:
        ws_data.append([
            ord_item.get('package', ''),
            ord_item.get('tg', ''),
            ord_item.get('order', ''),
            ord_item.get('kho_gui', ''),
            ord_item.get('kho_nhan', ''),
            ord_item.get('kho_ht', ''),
            ord_item.get('kho_giao_id', ''),
            ord_item.get('status', ''),
            '', '', '',
            ord_item.get('ten_kho_giao', ''),
            ord_item.get('tuyen', '')
        ])

    wb.save(str(out_file))
    del wb
    import gc
    gc.collect()
    print(f"✅ Generated {out_file} successfully! Total orders: {len(orders_data)} (Table 1: {total_table_1}, BD: {total_bd}, PY: {total_py})")
    return total_table_1, total_bd, total_py

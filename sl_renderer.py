import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
FONT_PATH = BASE_DIR / "fonts" / "Arial.ttf"
FONT_BOLD_PATH = BASE_DIR / "fonts" / "Arial-Bold.ttf"

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
    return 0

def render_overview_image(route_summary, bc_counts, out_path=None):
    if out_path is None:
        out_path = BASE_DIR / "SL_BD_ca1_overview.png"
    out_path = Path(out_path)

    font_path_str = str(FONT_PATH) if FONT_PATH.exists() else "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_bold_str = str(FONT_BOLD_PATH) if FONT_BOLD_PATH.exists() else "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

    try:
        font_header = ImageFont.truetype(font_bold_str, 13)
        font_body = ImageFont.truetype(font_path_str, 12)
        font_bold = ImageFont.truetype(font_bold_str, 12)
    except Exception:
        font_header = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    # Canvas dimensions
    width = 1720
    height = 680
    img = Image.new("RGB", (width, height), color="#ffffff")
    draw = ImageDraw.Draw(img)

    row_h = 24

    # TABLE 1 (LEFT)
    t1_x = 25
    t1_y = 30
    t1_col_widths = [110, 80, 110, 95, 95]
    t1_total_w = sum(t1_col_widths)

    headers_t1 = [
        ("Tuyến Xe", "#ffffff", "center"),
        ("SỐ ĐƠN", "#ffffff", "center"),
        ("Tỉ Lệ Thùng Xe", "#ffffff", "center"),
        ("Note", "#ffffff", "center"),
        ("TẢI TRỌNG", "#ffffff", "center")
    ]
    cur_x = t1_x
    for i, (h_text, h_color, align) in enumerate(headers_t1):
        w = t1_col_widths[i]
        bbox = draw.textbbox((0, 0), h_text, font=font_header)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = cur_x + (w - tw) // 2
        ty = t1_y + (row_h - th) // 2 - 2
        draw.rectangle([cur_x, t1_y, cur_x + w, t1_y + row_h], fill="#385723" if i == 0 else ("#833c0c" if i == 3 else "#385723"), outline="#7f7f7f", width=1)
        draw.text((tx, ty), h_text, fill=h_color, font=font_header)
        cur_x += w

    grand_total_t1 = 0
    cur_y = t1_y + row_h
    for item in route_summary:
        tuyen = item["tuyen"]
        so_don = item["so_don"]
        if tuyen == "GHN HOÀI NHƠN" and so_don == 0:
            continue
        grand_total_t1 += so_don
        pct_val = item.get("pct", 0.0)
        pct_str = f"{pct_val:.0f}%" if pct_val > 0 else "0%"
        note_str = item.get("note", "Không Rớt")
        tai_trong = item.get("tai_trong", "")
        if tai_trong == "N/A":
            tai_trong = ""

        draw.rectangle([t1_x, cur_y, t1_x + t1_total_w, cur_y + row_h], outline="#d9d9d9", width=1)

        row_vals = [
            (tuyen, "#000000", font_bold, "center"),
            (f"{so_don:,}", "#000000", font_body, "right"),
            (pct_str, "#000000", font_body, "center"),
            (note_str, "#c00000" if note_str == "Rớt" else "#833c0c", font_bold if note_str == "Rớt" else font_body, "center"),
            (tai_trong, "#000000", font_body, "center")
        ]

        c_x = t1_x
        for i, (val_text, val_color, val_font, align) in enumerate(row_vals):
            w = t1_col_widths[i]
            draw.rectangle([c_x, cur_y, c_x + w, cur_y + row_h], outline="#bfbfbf", width=1)
            if val_text:
                bbox = draw.textbbox((0, 0), val_text, font=val_font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                if align == "center":
                    tx = c_x + (w - tw) // 2
                elif align == "right":
                    tx = c_x + w - tw - 8
                else:
                    tx = c_x + 8
                ty = cur_y + (row_h - th) // 2 - 2
                draw.text((tx, ty), val_text, fill=val_color, font=val_font)
            c_x += w
        cur_y += row_h

    # Grand Total Table 1
    draw.rectangle([t1_x, cur_y, t1_x + t1_col_widths[0], cur_y + row_h], outline="#bfbfbf", width=1)
    draw.rectangle([t1_x + t1_col_widths[0], cur_y, t1_x + t1_col_widths[0] + t1_col_widths[1], cur_y + row_h], outline="#bfbfbf", width=1)
    draw.text((t1_x + 8, cur_y + 4), "Grand Total", fill="#000000", font=font_bold)
    total_str = f"{grand_total_t1:,}"
    bbox = draw.textbbox((0, 0), total_str, font=font_bold)
    tw = bbox[2] - bbox[0]
    draw.text((t1_x + t1_col_widths[0] + t1_col_widths[1] - tw - 8, cur_y + 4), total_str, fill="#000000", font=font_bold)

    # TABLE 2 (MIDDLE - BÌNH ĐỊNH)
    t2_x = t1_x + t1_total_w + 35
    t2_y = 30
    t2_col_w = [460, 75]
    t2_total_w = sum(t2_col_w)

    draw.rectangle([t2_x, t2_y, t2_x + t2_total_w, t2_y + row_h], fill="#833c0c")
    draw.rectangle([t2_x, t2_y, t2_x + t2_col_w[0], t2_y + row_h], outline="#595959", width=1)
    draw.rectangle([t2_x + t2_col_w[0], t2_y, t2_x + t2_total_w, t2_y + row_h], outline="#595959", width=1)
    
    bbox = draw.textbbox((0, 0), "TÊN TUYẾN XE", font=font_header)
    tw = bbox[2] - bbox[0]
    draw.text((t2_x + (t2_col_w[0] - tw) // 2, t2_y + 4), "TÊN TUYẾN XE", fill="#ffffff", font=font_header)
    bbox = draw.textbbox((0, 0), "SỐ ĐƠN", font=font_header)
    tw = bbox[2] - bbox[0]
    draw.text((t2_x + t2_col_w[0] + (t2_col_w[1] - tw) // 2, t2_y + 4), "SỐ ĐƠN", fill="#ffffff", font=font_header)

    bd_groups = [
        ("BD 13", [
            "Bưu Cục Vận Hành Thôn Định Trị-Xã Vĩnh Thạnh-Bình Định",
            "Bưu Cục 61 Quang Trung-Xã Vân Canh-Bình Định"
        ]),
        ("BD 01", [
            "Bưu Cục Thôn Xuân Phong Nam-An Lão-Bình Định",
            "(BDI) Hoài Nhơn Nam 1"
        ]),
        ("BD 03", [
            "Bưu Cục 269 Tây Sơn-Quy Nhơn-Bình Định",
            "Bưu Cục 396 Âu Cơ-Bùi Thị Xuân-Quy Nhơn-Bình Định",
            "Bưu Cục 263 Đống Đa-Quy Nhơn-Bình Định"
        ]),
        ("BD 04", [
            "Bưu Cục Đường 3 Tháng 2-Xã Phù Cát-Bình Định"
        ]),
        ("BD 05", [
            "Bưu Cục 21 Tây Sơn-Xã Phù Mỹ-Bình Định",
            "Bưu Cục 107 Nguyễn Lữ-Phù Mỹ-Bình Định"
        ]),
        ("BD 08", [
            "Bưu Cục 767 Hùng Vương-Quy Nhơn-Bình Định",
            "Bưu Cục Khu Vực Kim Châu-An Nhơn-Bình Định"
        ]),
        ("BD 12", [
            "Kho Giao Hàng Nặng Hoài Nhơn-Bình Định",
            "Bưu Cục Số 35 Phạm Văn Đồng-Tăng Bạt Hổ-Hoài Ân-Bình Định"
        ]),
        ("BD 14", [
            "Bưu Cục Thôn Chánh Hóa-Xã Cát Tiến-Bình Định",
            "(BDI) Tuy Phước Đông"
        ]),
        ("DN_BD_KH", [
            "Bưu Cục 571 Trần Phú-Tuy Phước-Bình Định"
        ]),
        ("DN-QNG-BD", [
            "Bưu Cục 838 Quang Trung-Phường Hoài Nhơn Tây-Bình Định"
        ]),
        ("GL_BD_01", [
            "Bưu Cục 44 Quang Trung-Tây Sơn-Bình Định"
        ])
    ]

    cur_y = t2_y + row_h
    bd_total = 0
    for grp_name, bc_list in bd_groups:
        grp_sum = sum(get_bc_val(bc_counts, bc) for bc in bc_list)
        rt_match = next((x for x in route_summary if x["tuyen"].replace("_"," ") == grp_name.replace("_"," ") or x["tuyen"] == grp_name), None)
        if grp_name == "BD 12":
            grp_sum = sum(get_bc_val(bc_counts, bc) for bc in bc_list)
        elif grp_name == "BD 01" and rt_match:
            grp_sum = rt_match["so_don"]
        elif rt_match:
            grp_sum = rt_match["so_don"]

        bd_total += grp_sum

        draw.rectangle([t2_x, cur_y, t2_x + t2_total_w, cur_y + row_h], fill="#c5e0b4", outline="#bfbfbf", width=1)
        draw.rectangle([t2_x + t2_col_w[0], cur_y, t2_x + t2_total_w, cur_y + row_h], outline="#bfbfbf", width=1)
        
        grp_title = f"= {grp_name}"
        bbox = draw.textbbox((0, 0), grp_title, font=font_bold)
        tw = bbox[2] - bbox[0]
        draw.text((t2_x + (t2_col_w[0] - tw) // 2, cur_y + 4), grp_title, fill="#385723", font=font_bold)
        
        val_s = f"{grp_sum:,}"
        bbox = draw.textbbox((0, 0), val_s, font=font_body)
        tw = bbox[2] - bbox[0]
        draw.text((t2_x + t2_col_w[0] + (t2_col_w[1] - tw) // 2, cur_y + 4), val_s, fill="#548235", font=font_body)
        cur_y += row_h

        for bc in bc_list:
            bc_val = get_bc_val(bc_counts, bc)
            draw.rectangle([t2_x, cur_y, t2_x + t2_col_w[0], cur_y + row_h], fill="#ffffff", outline="#bfbfbf", width=1)
            draw.rectangle([t2_x + t2_col_w[0], cur_y, t2_x + t2_total_w, cur_y + row_h], fill="#ffffff", outline="#bfbfbf", width=1)
            
            bbox = draw.textbbox((0, 0), bc, font=font_body)
            tw = bbox[2] - bbox[0]
            tx = t2_x + (t2_col_w[0] - tw) // 2 if tw < t2_col_w[0] - 16 else t2_x + 8
            draw.text((tx, cur_y + 4), bc, fill="#000000", font=font_body)

            bc_s = f"{bc_val:,}"
            bbox = draw.textbbox((0, 0), bc_s, font=font_body)
            tw = bbox[2] - bbox[0]
            draw.text((t2_x + t2_col_w[0] + (t2_col_w[1] - tw) // 2, cur_y + 4), bc_s, fill="#000000", font=font_body)
            cur_y += row_h

    # Grand Total Table 2
    draw.rectangle([t2_x, cur_y, t2_x + t2_col_w[0], cur_y + row_h], outline="#bfbfbf", width=1)
    draw.rectangle([t2_x + t2_col_w[0], cur_y, t2_x + t2_total_w, cur_y + row_h], outline="#bfbfbf", width=1)
    bbox = draw.textbbox((0, 0), "Grand Total", font=font_bold)
    tw = bbox[2] - bbox[0]
    draw.text((t2_x + (t2_col_w[0] - tw) // 2, cur_y + 4), "Grand Total", fill="#000000", font=font_bold)
    bd_total_str = f"{bd_total:,}"
    bbox = draw.textbbox((0, 0), bd_total_str, font=font_bold)
    tw = bbox[2] - bbox[0]
    draw.text((t2_x + t2_col_w[0] + (t2_col_w[1] - tw) // 2, cur_y + 4), bd_total_str, fill="#000000", font=font_bold)

    # TABLE 3 (RIGHT - PHÚ YÊN)
    t3_x = t2_x + t2_total_w + 35
    t3_y = 30
    t3_col_w = [460, 75]
    t3_total_w = sum(t3_col_w)

    draw.rectangle([t3_x, t3_y, t3_x + t3_total_w, t3_y + row_h], fill="#833c0c")
    draw.rectangle([t3_x, t3_y, t3_x + t3_col_w[0], t3_y + row_h], outline="#595959", width=1)
    draw.rectangle([t3_x + t3_col_w[0], t3_y, t3_x + t3_total_w, t3_y + row_h], outline="#595959", width=1)
    
    bbox = draw.textbbox((0, 0), "TÊN TUYẾN XE", font=font_header)
    tw = bbox[2] - bbox[0]
    draw.text((t3_x + (t3_col_w[0] - tw) // 2, t3_y + 4), "TÊN TUYẾN XE", fill="#ffffff", font=font_header)
    bbox = draw.textbbox((0, 0), "SỐ ĐƠN", font=font_header)
    tw = bbox[2] - bbox[0]
    draw.text((t3_x + t3_col_w[0] + (t3_col_w[1] - tw) // 2, t3_y + 4), "SỐ ĐƠN", fill="#ffffff", font=font_header)

    py_groups = [
        ("BD PY 01", [
            "Bưu Cục KP4 Hòa Vinh- Đông Hòa- Phú yên",
            "Bưu Cục Thị Trấn Phú Thứ-Tây Hoà-Phú Yên"
        ]),
        ("BD PY 02", [
            "Bưu Cục 274 Hùng Vương-Tuy Hòa-Phú Yên",
            "Kho Giao Hàng Nặng Phú Yên"
        ]),
        ("BD PY 03", [
            "Bưu cục 138 Trần Phú-Đồng Xuân-Phú Yên",
            "BƯU CỤC KHU PHỐ 3 - THỊ TRẤN HAI RIÊNG-SÔNG HÌNH-PHÚ YÊN",
            "Bưu Cục Suối Bạc-Sơn Hòa-Phú Yên"
        ]),
        ("BD PY 06", [
            "Bưu cục DT644-Sông Cầu-Phú Yên",
            "Bưu cục 27 Nguyễn Tất Thành-Tuy Hòa-Phú Yên"
        ]),
        ("BD PY 06_01", [
            "Bưu Cục Thôn Đông Phước-Phú Hòa-Phú Yên"
        ]),
        ("BD PY 08", [
            "Bưu Cục 71 Quốc Lộ 1A-Xã Tuy An Bắc-Phú Yên",
            "Bưu Cục Đường Tỉnh 643-Xã Tuy An Nam-Phú Yên"
        ]),
        ("GHN BÌNH ĐỊNH", [
            "Kho Giao Hàng Nặng Bình Định"
        ])
    ]

    cur_y = t3_y + row_h
    py_total = 0
    for grp_name, bc_list in py_groups:
        grp_sum = sum(get_bc_val(bc_counts, bc) for bc in bc_list)
        rt_match = next((x for x in route_summary if x["tuyen"].replace("_"," ") == grp_name.replace("_"," ") or x["tuyen"] == grp_name), None)
        if rt_match:
            grp_sum = rt_match["so_don"]

        py_total += grp_sum

        draw.rectangle([t3_x, cur_y, t3_x + t3_total_w, cur_y + row_h], fill="#c5e0b4", outline="#bfbfbf", width=1)
        draw.rectangle([t3_x + t3_col_w[0], cur_y, t3_x + t3_total_w, cur_y + row_h], outline="#bfbfbf", width=1)
        
        grp_title = f"= {grp_name}"
        bbox = draw.textbbox((0, 0), grp_title, font=font_bold)
        tw = bbox[2] - bbox[0]
        draw.text((t3_x + (t3_col_w[0] - tw) // 2, cur_y + 4), grp_title, fill="#385723", font=font_bold)
        
        val_s = f"{grp_sum:,}"
        bbox = draw.textbbox((0, 0), val_s, font=font_body)
        tw = bbox[2] - bbox[0]
        draw.text((t3_x + t3_col_w[0] + (t3_col_w[1] - tw) // 2, cur_y + 4), val_s, fill="#548235", font=font_body)
        cur_y += row_h

        for bc in bc_list:
            bc_val = get_bc_val(bc_counts, bc)
            draw.rectangle([t3_x, cur_y, t3_x + t3_col_w[0], cur_y + row_h], fill="#ffffff", outline="#bfbfbf", width=1)
            draw.rectangle([t3_x + t3_col_w[0], cur_y, t3_x + t3_total_w, cur_y + row_h], fill="#ffffff", outline="#bfbfbf", width=1)
            
            bbox = draw.textbbox((0, 0), bc, font=font_body)
            tw = bbox[2] - bbox[0]
            tx = t3_x + (t3_col_w[0] - tw) // 2 if tw < t3_col_w[0] - 16 else t3_x + 8
            draw.text((tx, cur_y + 4), bc, fill="#000000", font=font_body)

            bc_s = f"{bc_val:,}"
            bbox = draw.textbbox((0, 0), bc_s, font=font_body)
            tw = bbox[2] - bbox[0]
            draw.text((t3_x + t3_col_w[0] + (t3_col_w[1] - tw) // 2, cur_y + 4), bc_s, fill="#000000", font=font_body)
            cur_y += row_h

    # Grand Total Table 3
    draw.rectangle([t3_x, cur_y, t3_x + t3_col_w[0], cur_y + row_h], outline="#bfbfbf", width=1)
    draw.rectangle([t3_x + t3_col_w[0], cur_y, t3_x + t3_total_w, cur_y + row_h], outline="#bfbfbf", width=1)
    bbox = draw.textbbox((0, 0), "Grand Total", font=font_bold)
    tw = bbox[2] - bbox[0]
    draw.text((t3_x + (t3_col_w[0] - tw) // 2, cur_y + 4), "Grand Total", fill="#000000", font=font_bold)
    py_total_str = f"{py_total:,}"
    bbox = draw.textbbox((0, 0), py_total_str, font=font_bold)
    tw = bbox[2] - bbox[0]
    draw.text((t3_x + t3_col_w[0] + (t3_col_w[1] - tw) // 2, cur_y + 4), py_total_str, fill="#000000", font=font_bold)

    img.save(str(out_path))
    print(f"✅ Rendered image successfully: {out_path} ({width}x{height})")
    return str(out_path)

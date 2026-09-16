# Bot Telegram Cảnh Báo Chuyến Xe Đến Trễ Điểm Tiếp Theo (GHN Vận Tải)

Hệ thống Bot tự động giám sát toàn bộ các chuyến xe Express đang di chuyển (`https://nhanh.ghn.vn/vantai-dieuphoi/express/list`) và bắn thông báo cảnh báo tức thời lên nhóm Telegram khi có xe đến trễ hoặc rời trạm trễ so với giờ dự kiến (ETA).

---

## 🚀 Cách Chạy Bot

Trong Terminal, gõ:

```bash
cd /Users/haonhien/.gemini/antigravity/scratch/ghn_late_truck_bot
./run.sh
# Hoặc: python3 bot.py
```

---

## 📌 Các Tính Năng Của Bot

1. **Quét tự động ngầm (Background Polling):**
   - Mặc định mỗi **60 giây** bot tự động kết nối API GHN lấy danh sách toàn bộ xe đang chạy (`ontrip`).
   - Tự động so sánh giờ dự kiến đến trạm kế tiếp (`estimate_time_in_at`) hoặc giờ xuất bến (`estimate_time_out_at`) với giờ hiện tại.
   - Bắn tin nhắn cảnh báo trực quan vào nhóm Telegram.

2. **Cơ chế chống spam (Smart Deduplication):**
   - Không bắn lại liên tục mỗi chu kỳ quét nếu độ trễ không thay đổi.
   - Chỉ cập nhật khi độ trễ tăng thêm $\ge 15$ phút.
   - Tự động giải tỏa khi xe đã check-in thành công tại trạm.

3. **Tương tác trực tiếp trên Telegram:**
   - `/check` hoặc `/tre`: Kiểm tra ngay danh sách xe đang trễ tại thời điểm hiện tại.
   - `/all`: Xem danh sách tất cả các xe đang lăn bánh.
   - `/threshold <số_phút>`: Đổi ngưỡng lọc trễ (mặc định 10 phút, ví dụ `/threshold 15`).
   - `/token <token_mới>`: Cập nhật Bearer Token GHN mới trực tiếp trên Telegram khi token cũ hết hạn (không cần sửa file code).
   - `/status`: Xem trạng thái hệ thống, thời gian quét gần nhất, thời hạn token.
   - `/help`: Xem menu hướng dẫn.

---

## ⚙️ Cấu Hình (config.json / config.py)

- **`BOT_TOKEN`**: Token Bot Telegram (mặc định: `8712756148:AAF...`)
- **`GROUP_ID`**: ID nhóm nhận thông báo (mặc định: `-5277804841`)
- **`POLL_INTERVAL_SECONDS`**: Chu kỳ quét dữ liệu (60s)
- **`DELAY_THRESHOLD_MINUTES`**: Ngưỡng số phút trễ tối thiểu để báo động (mặc định 10 phút)
- **`ghn_token.txt`**: Lưu trữ Bearer Token của GHN.

---

## 🔑 Cách Lấy Token GHN Mới (Khi hết hạn)

1. Mở trang [nhanh.ghn.vn/vantai-dieuphoi/express/list](https://nhanh.ghn.vn/vantai-dieuphoi/express/list)
2. Nhấn `F12` $\rightarrow$ tab `Network` $\rightarrow$ `find_trip`
3. Copy chuỗi sau chữ `Bearer ` trong header `authorization`
4. Gõ trên Telegram: `/token <chuỗi_token_vừa_copy>`

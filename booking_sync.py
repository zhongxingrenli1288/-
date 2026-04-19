import os  # <--- 1. 必須要 import os
import requests
from icalendar import Calendar
from supabase import create_client
from datetime import datetime

# 從環境變數讀取金鑰 (GitHub Actions 設定中的 Secrets)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 2. 如果環境變數讀不到，才給預設值（或是直接報錯）
if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ 錯誤: 找不到 Supabase 環境變數")
    # 下面這兩行只有在你「電腦本地」測試時才填入，上傳 GitHub 前請保持下面這樣
    # SUPABASE_URL = SUPABASE_URL or "你的網址"
    # SUPABASE_KEY = SUPABASE_KEY or "你的金鑰"

# 建立連線
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def safe_date(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)

def sync_booking_ical(ical_url, room_name):
    sync_time = datetime.now().strftime("%m/%d %H:%M")
    print(f"[{sync_time}] 開始同步: {room_name}")

    # 加上隨機參數 t 與瀏覽器偽裝 (User-Agent)，避免被 Booking 擋掉
    final_url = f"{ical_url}&t={int(datetime.now().timestamp())}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        res = requests.get(final_url, headers=headers, timeout=30)
        if res.status_code != 200:
            print(f"❌ 抓不到 iCal: {room_name} (HTTP {res.status_code})")
            return

        if "BEGIN:VCALENDAR" not in res.text:
            print(f"⚠️ 內容無效: {room_name}，可能連線被阻擋")
            return

        cal = Calendar.from_ical(res.text)
        ical_events = set()

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            start = safe_date(component.get("dtstart").dt)
            end = safe_date(component.get("dtend").dt)
            summary = str(component.get("summary", "Booking客人"))

            key = f"{room_name}_{start}"
            ical_events.add(key)

            # 檢查資料庫是否有該筆資料
            exist = supabase.table("bookings") \
                .select("*") \
                .eq("room", room_name) \
                .eq("check_in", start) \
                .execute()

            if exist.data:
                # 已存在就更新
                supabase.table("bookings").update({
                    "check_out": end,
                    "guest_name": summary,
                    "note": f"Booking同步 (最後確認: {sync_time})",
                    "source": "booking"
                }).eq("id", exist.data[0]["id"]).execute()
            else:
                # 不存在就新增
                print(f"➕ 發現新訂單: {room_name} {start}")
                supabase.table("bookings").insert({
                    "room": room_name,
                    "guest_name": summary,
                    "phone": "Booking.com",
                    "note": f"Booking同步 (新增: {sync_time})",
                    "check_in": start,
                    "check_out": end,
                    "source": "booking"
                }).execute()

        # 刪除機制：只刪除未來且 iCal 中消失的 Booking 單
        today = datetime.now().strftime("%Y-%m-%d")
        db_data = supabase.table("bookings") \
            .select("*") \
            .eq("room", room_name) \
            .eq("source", "booking") \
            .gte("check_in", today) \
            .execute()

        for row in db_data.data:
            db_key = f"{row['room']}_{row['check_in']}"
            if db_key not in ical_events:
                print(f"🗑️ 刪除已取消訂單: {db_key}")
                supabase.table("bookings").delete().eq("id", row["id"]).execute()

        print(f"✅ {room_name} 同步完成")

    except Exception as e:
        print(f"⚠️ {room_name} 同步時發生錯誤: {e}")

import requests
from icalendar import Calendar
from supabase import create_client
from datetime import datetime

SUPABASE_URL = "https://bibliidwczaxrxuiagjx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJpYmxpaWR3Y3pheHJ4dWlhZ2p4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1NzM3OTEsImV4cCI6MjA4NjE0OTc5MX0.j68sBe6nWcd0txkk00ReYfca6qf9VC88mVkfSxOlKx4" # 建議檢查是否為 Service Role Key

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def safe_date(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)

def sync_booking_ical(ical_url, room_name):
    # 增加同步時間戳記，方便在資料庫查看
    sync_time = datetime.now().strftime("%m/%d %H:%M")
    print(f"[{sync_time}] 開始同步:", room_name)

    # 加上隨機參數 t，強迫 Booking 伺服器吐出最新資料，不使用舊快取
    final_url = f"{ical_url}&t={int(datetime.now().timestamp())}"

    try:
        res = requests.get(final_url, timeout=30)
        if res.status_code != 200:
            print(f"❌ 抓不到 iCal: {room_name}")
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

            exist = supabase.table("bookings") \
                .select("*") \
                .eq("room", room_name) \
                .eq("check_in", start) \
                .execute()

            if exist.data:
                row = exist.data[0]
                # ⭐ 修改點：即使是 booking 來源，也要更新「退房日」和「同步時間備註」
                # 這樣你才知道系統真的有「看到」這筆單
                supabase.table("bookings").update({
                    "check_out": end,
                    "guest_name": summary, # 確保名字跟著 iCal 更新
                    "note": f"Booking同步 (最後確認: {sync_time})",
                    "source": "booking"
                }).eq("id", row["id"]).execute()
            else:
                # ⭐ 新 Booking 訂單
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

        # ⭐ 刪除機制：只刪除「未來」且「iCal已消失」的單
        today = datetime.now().strftime("%Y-%m-%d")
        db_data = supabase.table("bookings") \
            .select("*") \
            .eq("room", room_name) \
            .eq("source", "booking") \
            .gte("check_in", today) \
            .execute()

        for row in db_data.data:
            key = f"{row['room']}_{row['check_in']}"
            if key not in ical_events:
                print(f"🗑️ 刪除已取消訂單: {key}")
                supabase.table("bookings").delete().eq("id", row["id"]).execute()

        print("✅ 完成:", room_name)

    except Exception as e:
        print(f"⚠️ {room_name} 同步時發生錯誤: {e}")

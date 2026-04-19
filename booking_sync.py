import os  # 確保有這行，不然會報 NameError
import requests
import time
from icalendar import Calendar
from supabase import create_client
from datetime import datetime

# 1. 這裡的名字要跟 GitHub Secrets 裡的一模一樣
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# 2. 建立連線 (使用對齊後的變數名稱)
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ 錯誤: 找不到環境變數，請檢查 GitHub Secrets")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def safe_date(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)

def sync_booking_ical(ical_url, room_name):
    sync_time = datetime.now().strftime("%m/%d %H:%M")
    print(f"[{sync_time}] 開始同步: {room_name}")

    # 處理 URL 與偽裝
    connector = "&" if "?" in ical_url else "?"
    final_url = f"{ical_url}{connector}details=1&t={int(time.time())}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        res = requests.get(final_url, headers=headers, timeout=30)
        
        if res.status_code != 200:
            print(f"❌ 抓不到 iCal: {room_name} (HTTP {res.status_code})")
            return

        if "BEGIN:VCALENDAR" not in res.text:
            print(f"⚠️ 內容無效: {room_name} (可能被阻擋)")
            return

        cal = Calendar.from_ical(res.text)
        ical_events = set()

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            start = safe_date(component.get("dtstart").dt)
            end = safe_date(component.get("dtend").dt)
            summary = str(component.get("summary", "Booking 客人"))

            key = f"{room_name}_{start}"
            ical_events.add(key)

            # 檢查資料庫
            exist = supabase.table("bookings").select("*").eq("room", room_name).eq("check_in", start).execute()

            payload = {
                "room": room_name,
                "guest_name": summary,
                "check_in": start,
                "check_out": end,
                "source": "booking",
                "note": f"GitHub同步 ({sync_time})"
            }

            if exist.data:
                # 已存在就更新
                supabase.table("bookings").update(payload).eq("id", exist.data[0]["id"]).execute()
            else:
                # 新增
                print(f"➕ 發現新訂單: {room_name} {start} ({summary})")
                supabase.table("bookings").insert(payload).execute()

        # 3. 刪除機制
        today = datetime.now().strftime("%Y-%m-%d")
        db_data = supabase.table("bookings").select("*").eq("room", room_name).eq("source", "booking").gte("check_in", today).execute()

        for row in db_data.data:
            db_key = f"{row['room']}_{row['check_in']}"
            if db_key not in ical_events:
                print(f"🗑️ 刪除取消訂單: {db_key}")
                supabase.table("bookings").delete().eq("id", row["id"]).execute()

        print(f"✅ {room_name} 同步完成")

    except Exception as e:
        print(f"⚠️ {room_name} 發生錯誤: {e}")

import os
import requests
import time
from icalendar import Calendar
from supabase import create_client
from datetime import datetime

# 1. 讀取環境變數 (請確認 GitHub Secrets 名字完全一致)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# --- 防呆檢查區 ---
if not URL or not KEY:
    print(f"❌ 嚴重錯誤: 找不到環境變數！")
    print(f"目前 URL 狀態: {'已讀取' if URL else '空值'}")
    print(f"目前 KEY 狀態: {'已讀取' if KEY else '空值'}")
    # 這裡拋出錯誤會讓 GitHub Action 顯示紅燈，方便查看原因
    raise ValueError("請檢查 GitHub Secrets 是否有正確設定 SUPABASE_URL 與 SUPABASE_SERVICE_ROLE_KEY")

# 2. 建立連線
supabase = create_client(URL, KEY)

def safe_date(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)

def sync_booking_ical(ical_url, room_name):
    sync_time = datetime.now().strftime("%m/%d %H:%M")
    print(f"[{sync_time}] 開始同步: {room_name}")

    # 處理 URL 與防快取機制
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
           summary_raw = str(component.get("summary", ""))
            
            # 如果標題包含 CLOSED，我們就把它命名為 "Booking 訂單"
            if "CLOSED" in summary_raw.upper():
                summary = "Booking 訂單 (已預訂)"
            else:
                summary = summary_raw if summary_raw else "已預訂"

            key_name = f"{room_name}_{start}"
            ical_events.add(key_name)

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

        # 3. 刪除機制：只處理 Booking 來源且是未來的訂單
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

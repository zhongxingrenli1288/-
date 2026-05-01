import os
import requests
from icalendar import Calendar
from supabase import create_client
from datetime import datetime

# 讀取環境變數
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(URL, KEY)

def safe_date(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)

def sync_booking_ical(ical_url, room_name):
    print(f"正在同步房型: {room_name}")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        res = requests.get(ical_url, headers=headers, timeout=30)
        if res.status_code != 200:
            print(f"無法抓取 {room_name}")
            return

        cal = Calendar.from_ical(res.text)
        for component in cal.walk():
            if component.name == "VEVENT":
                start = safe_date(component.get("dtstart").dt)
                end = safe_date(component.get("dtend").dt)
                summary = str(component.get("summary", "Booking 客人"))

                # 原始邏輯：直接寫入資料庫
                data = {
                    "room": room_name,
                    "guest_name": summary,
                    "check_in": start,
                    "check_out": end,
                    "source": "booking"
                }
                supabase.table("bookings").insert(data).execute()
        print(f"{room_name} 同步完成")
    except Exception as e:
        print(f"發生錯誤: {e}")

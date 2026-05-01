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
                # 1. 提取資料
                start = safe_date(component.get("dtstart").dt)
                end = safe_date(component.get("dtend").dt)
                
                # 處理名字判斷 (保留你原本的需求)
                raw_summary = str(component.get("summary", ""))
                if "CLOSED" in raw_summary.upper():
                    summary = "Booking 訂單 (已預訂)"
                else:
                    summary = raw_summary if raw_summary else "Booking 客人"

                # 2. 核心修改：針對每一筆 insert 使用獨立的 try
                try:
                    data = {
                        "room": room_name,
                        "guest_name": summary,
                        "check_in": start,
                        "check_out": end,
                        "source": "booking",
                        "note": "Booking ical 同步"
                    }
                    # 執行寫入
                    supabase.table("bookings").insert(data).execute()
                    print(f"  [新增成功] {start}")
                
                except Exception as e:
                    # 如果是因為重複 (23505) 或其他原因報錯，印出訊息並「跳過」
                    if "23505" in str(e):
                        print(f"  [已存在] {start}，跳過並繼續下一筆。")
                    else:
                        print(f"  [寫入失敗] {start}: {e}")
                    # 使用 continue 確保迴圈繼續執行下一筆 VEVENT
                    continue

        print(f"{room_name} 同步流程執行完畢。")
        
    except Exception as e:
        print(f"發生連線錯誤或主要錯誤: {e}")

if __name__ == "__main__":
    BOOKING_ICALS = [
        {"url": "https://ical.booking.com/v1/export?t=0152fb10-fb36-4b80-bd14-5c59e334219e", "room": "201"},
        {"url": "https://ical.booking.com/v1/export?t=ea4ac508-6d9b-4f4f-9ded-1f133669c632", "room": "202"},
        {"url": "https://ical.booking.com/v1/export?t=f2b842e9-de1a-4092-a28d-8a911d0ebd6d", "room": "301"},
        {"url": "https://ical.booking.com/v1/export?t=eed8891e-2a9e-4ad1-89cf-7ef75ae31704", "room": "302"}
    ]
    
    for item in BOOKING_ICALS:
        sync_booking_ical(item["url"], item["room"])

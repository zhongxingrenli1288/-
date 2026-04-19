import os
import requests
import time
from icalendar import Calendar
from supabase import create_client
from datetime import datetime

# 1. 讀取環境變數
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not URL or not KEY:
    raise ValueError("找不到環境變數，請檢查 GitHub Secrets 設定")

# 建立連線
supabase = create_client(URL, KEY)

def safe_date(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)

def sync_booking_ical(ical_url, room_name):
    sync_time = datetime.now().strftime("%m/%d %H:%M")
    print(f"[{sync_time}] 開始同步房型: {room_name}")

    # 處理 URL
    clean_url = ical_url.strip()
    connector = "&" if "?" in clean_url else "?"
    final_url = f"{clean_url}{connector}t={int(time.time())}"
    
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        res = requests.get(final_url, headers=headers, timeout=30)
        if res.status_code != 200:
            print(f"❌ 抓取失敗 HTTP {res.status_code}")
            return

        cal = Calendar.from_ical(res.text)
        ical_events = set()

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            # 讀取日期
            start = safe_date(component.get("dtstart").dt)
            end = safe_date(component.get("dtend").dt)
            
            # --- 核心邏輯：處理名字或關閉狀態 ---
            summary_raw = str(component.get("summary", ""))
            
            # 只要看到 CLOSED 或名字，都視為訂單
            if "CLOSED" in summary_raw.upper():
                summary = "Booking 訂單 (已預訂)"
            else:
                summary = summary_raw if summary_raw else "已預訂"

            # 追蹤這筆訂單
            key = f"{room_name}_{start}"
            ical_events.add(key)

            # 檢查資料庫是否有這筆
            exist = supabase.table("bookings").select("*").eq("room", room_name).eq("check_in", start).execute()

            payload = {
                "room": room_name,
                "guest_name": summary,
                "check_in": start,
                "check_out": end,
                "source": "booking",
                "note": f"GitHub同步({sync_time})"
            }

            if exist.data:
                # 已存在就更新
                supabase.table("bookings").update(payload).eq("id", exist.data[0]["id"]).execute()
            else:
                # 不存在就新增
                print(f"➕ 寫入新訂單: {room_name} {start} ({summary})")
                supabase.table("bookings").insert(payload).execute()

        print(f"✅ {room_name} 同步完成，共處理 {len(ical_events)} 筆資料")

    except Exception as e:
        print(f"⚠️ 發生錯誤: {e}")

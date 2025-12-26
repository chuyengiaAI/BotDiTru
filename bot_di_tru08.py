import requests
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime
from google import genai 
from telegram import Bot
import html
import pandas as pd
import os
 

# --- THÔNG TIN CỦA BÉ ---
# Sửa lại phần thông tin như sau:
API_KEY = os.getenv("API_KEY") 
TELE_TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = "@cucDidan_philipin"
HISTORY_FILE = "da_dang.txt"

client = genai.Client(api_key=API_KEY)





# ==========================================================
# --- HÀM HỖ TRỢ (GIỮ NGUYÊN VÀ FIX LỖI BLOCKQUOTE) ---
# ==========================================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

def save_to_history(link):
    with open(HISTORY_FILE, "a") as f:
        f.write(link + "\n")

def format_date_vn(date_str):
    try:
        dt = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
        return dt.strftime('Ngày %d tháng %m năm %Y')
    except: return "Mới nhất"

async def ai_pro_translator(title, content):
    prompt = f"Tóm tắt súc tích bài báo di trú này sang tiếng Việt (dưới 150 từ), dùng emoji: {title}\n{content}\nĐịnh dạng: TIÊU ĐỀ_VN: [nội dung] NỘI DUNG_VN: [nội dung]"
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res_text = response.text
        if "NỘI DUNG_VN:" in res_text:
            vn_title = res_text.split("NỘI DUNG_VN:")[0].replace("TIÊU ĐỀ_VN:", "").strip()
            vn_summary = res_text.split("NỘI DUNG_VN:")[1].strip()
            return vn_title, vn_summary
        return None, None
    except: return None, None

async def send_to_telegram(title, date_vn, summary, img_url):
    bot = Bot(token=TELE_TOKEN)
    safe_title = html.escape(title.upper())
    safe_summary = html.escape(summary)
    header = f"📅 <b>{html.escape(date_vn)}</b>\n━━━━━━━━━━━━━━━━━━\n📣 <b>{safe_title}</b>\n\n"
    
    # Fix lỗi cắt nhầm thẻ blockquote bằng cách chủ động đóng thẻ
    limit = 1024 - len(header) - 30
    message = f"{header}<blockquote>{safe_summary[:limit]}</blockquote>"
    
    try:
        if img_url != "N/A":
            await bot.send_photo(chat_id=CHAT_ID, photo=img_url, caption=message, parse_mode='HTML')
        else:
            await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
        return True
    except Exception as e:
        print(f"❌ Lỗi gửi: {e}")
        return False

# ==========================================================
# --- CHỨC NĂNG QUÉT TIN TỰ ĐỘNG ---
# ==========================================================

async def run_worker(scan_pages=1):
    """Hàm thực hiện việc quét tin và đăng bài"""
    history = load_history()
    headers = {'User-Agent': 'Mozilla/5.0'}
    found_new = 0

    for page in range(1, scan_pages + 1):
        url = f"https://immigration.gov.ph/category/press-release/page/{page}/"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = soup.find_all('article')
            
            for art in articles:
                link = art.find('a')['href']
                if link in history: continue

                # Xử lý bài mới
                d_res = requests.get(link, headers=headers, timeout=15)
                d_soup = BeautifulSoup(d_res.content, 'html.parser')
                raw_title = d_soup.find('h1', class_='entry-title').text.strip()
                
                print(f"✨ Phát hiện mới: {raw_title[:40]}...")
                
                # Trích xuất dữ liệu bài viết...
                raw_date = d_soup.find('meta', property='article:published_time')['content']
                date_vn = format_date_vn(raw_date)
                content_div = d_soup.find('div', class_='entry-content clear')
                raw_content = content_div.get_text() if content_div else ""
                
                img_url = "N/A"
                if content_div:
                    for img in content_div.find_all('img'):
                        src = img.get('src', '')
                        if "uploads" in src:
                            img_url = src; break

                vn_title, vn_summary = await ai_pro_translator(raw_title, raw_content)
                if vn_title and vn_summary:
                    if await send_to_telegram(vn_title, date_vn, vn_summary, img_url):
                        save_to_history(link)
                        history.add(link)
                        found_new += 1
                        await asyncio.sleep(30) # Nghỉ bảo vệ API
        except Exception as e:
            print(f"⚠️ Lỗi tại trang {page}: {e}")
    return found_new

async def main():
    print("🤖 Robot Auto-Pilot đã khởi động!")
    is_first_run = True
    
    while True:
        current_time = datetime.now().strftime("%H:%M:%S")
        # Lần đầu quét 10 trang, các lần sau chỉ quét trang 1 để cập nhật (TRIZ 15)
        pages = 10 if is_first_run else 1
        
        print(f"⏰ [{current_time}] Bắt đầu chu kỳ quét {pages} trang...")
        new_count = await run_worker(scan_pages=pages)
        print(f"🏁 Hoàn thành chu kỳ. Đã đăng {new_count} bài mới.")
        
        is_first_run = False
        
        # Nghỉ 8 tiếng (8 * 3600 giây) để chạy đúng 3 lần/ngày
        wait_hours = 8
        print(f"💤 Nghỉ {wait_hours} tiếng trước lần quét tiếp theo...")
        await asyncio.sleep(wait_hours * 3600)

if __name__ == "__main__":
    asyncio.run(main())
import os
import time
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# --- Налаштування ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
IDS_FILE = "last_ids.txt"
BASE_URL = "https://www.njuskalo.hr/iznajmljivanje-stanova/split?sort=new"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def translate_text(text, dest_lang='en'):
    try:
        if not text: return ""
        return GoogleTranslator(source='auto', target=dest_lang).translate(text)
    except:
        return text

def load_ids():
    if not os.path.exists(IDS_FILE): return set()
    with open(IDS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_id(ad_id):
    with open(IDS_FILE, "a") as f:
        f.write(ad_id + "\n")

def get_listings():
    try:
        session = requests.Session()
        resp = session.get(BASE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        
        listings = []
        items = soup.select("li.EntityList-item--Regular, li.EntityList-item--VauVau")
        
        for item in items[:10]:
            link_tag = item.select_one("h3.entity-title a")
            if not link_tag: continue
            
            url = "https://www.njuskalo.hr" + link_tag["href"]
            ad_id = url.rstrip("/").split("/")[-1].split("?")[0]
            title = link_tag.get_text(strip=True)
            
            price_tag = item.select_one(".price-items .price--eur")
            price = price_tag.get_text(strip=True) if price_tag else "Check site"
            
            listings.append({"id": ad_id, "url": url, "title": title, "price": price})
        return listings
    except Exception as e:
        print(f"Error fetching listings: {e}")
        return []

def get_details(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")
        
        # Витягуємо фото
        photos = []
        for img in soup.select("img.gallery-foto")[:10]:
            src = img.get("data-src") or img.get("src")
            if src and "images" in src: photos.append(src)
            
        # Витягуємо параметри (площа, кімнати)
        details_text = ""
        for meta in soup.select(".ClassifiedDetailBasicDetails-list dt, .ClassifiedDetailBasicDetails-list dd"):
            details_text += meta.get_text(strip=True) + " "
            
        # Витягуємо опис
        desc_tag = soup.select_one(".ClassifiedDetailDescription-text")
        description = desc_tag.get_text(separator="\n", strip=True) if desc_tag else ""
        
        return {
            "photos": photos,
            "description": translate_text(description[:500] + "..."),
            "title_en": translate_text(soup.select_one("h1.ClassifiedDetailSummary-title").get_text(strip=True) if soup.select_one("h1.ClassifiedDetailSummary-title") else "")
        }
    except:
        return {"photos": [], "description": "", "title_en": ""}

def send_post(listing):
    details = get_details(listing["url"])
    time.sleep(1)
    
    # Формуємо шаблон
    caption = (
        f"🏠 **{details['title_en'] or listing['title']}**\n\n"
        f"💰 **Price:** {listing['price']}\n"
        f"📍 **Location:** Split, Croatia\n\n"
        f"📝 **Description:**\n{details['description']}\n\n"
        f"🔗 [View on Njuskalo]({listing['url']})\n\n"
        f"#split #croatia #rent"
    )

    api_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    if len(details['photos']) >= 2:
        media = []
        for i, p_url in enumerate(details['photos'][:10]):
            media.append({
                "type": "photo",
                "media": p_url,
                "caption": caption if i == 0 else "",
                "parse_mode": "Markdown"
            })
        requests.post(f"{api_base}/sendMediaGroup", json={"chat_id": CHANNEL_ID, "media": media})
    else:
        photo = details['photos'][0] if details['photos'] else "https://via.placeholder.com/500"
        requests.post(f"{api_base}/sendPhoto", json={"chat_id": CHANNEL_ID, "photo": photo, "caption": caption, "parse_mode": "Markdown"})

def main():
    print("🔄 Starting English parser...")
    known_ids = load_ids()
    listings = get_listings()

    new_count = 0
    for listing in listings:
        if listing["id"] in known_ids: continue
        print(f"🆕 New listing found: {listing['id']}")
        send_post(listing)
        save_id(listing["id"])
        known_ids.add(listing["id"])
        new_count += 1
        time.sleep(5) # Пауза, щоб не забанили

    print(f"✅ Done. New posts: {new_count}")

if __name__ == "__main__":
    main()

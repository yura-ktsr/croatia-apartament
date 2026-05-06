import os
import time
import requests
from bs4 import BeautifulSoup

# --- Налаштування ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
IDS_FILE = "last_ids.txt"

BASE_URL = "https://www.njuskalo.hr/iznajmljivanje-stanova/split?sort=new"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "hr,en;q=0.9",
}

# --- Завантаження збережених ID ---
def load_ids():
    if not os.path.exists(IDS_FILE):
        return set()
    with open(IDS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

# --- Збереження нового ID ---
def save_id(ad_id):
    with open(IDS_FILE, "a") as f:
        f.write(ad_id + "\n")

# --- Отримання списку оголошень ---
def get_listings():
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Помилка завантаження сторінки: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    listings = []

    for item in soup.select("article.entity-body"):
        try:
            link_tag = item.select_one("a.entity-description-title")
            if not link_tag:
                continue

            url = "https://www.njuskalo.hr" + link_tag["href"]
            ad_id = url.split("/")[-1].split("?")[0]
            title = link_tag.get_text(strip=True)

            price_tag = item.select_one(".price-box")
            price = price_tag.get_text(strip=True) if price_tag else "Ціна не вказана"

            listings.append({
                "id": ad_id,
                "url": url,
                "title": title,
                "price": price,
            })
        except Exception as e:
            print(f"Помилка парсингу елементу: {e}")
            continue

    return listings

# --- Отримання фото з оголошення ---
def get_photos(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        photos = []
        for img in soup.select("img.gallery-foto")[:8]:
            src = img.get("data-src") or img.get("src")
            if src and src.startswith("http"):
                photos.append(src)
        return photos
    except Exception as e:
        print(f"Помилка отримання фото: {e}")
        return []

# --- Відправка посту в Telegram ---
def send_post(listing):
    photos = get_photos(listing["url"])
    time.sleep(1)

    caption = (
        f"🏠 *{listing['title']}*\n\n"
        f"💰 {listing['price']}\n\n"
        f"🔗 [Переглянути оголошення]({listing['url']})"
    )

    api_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    if len(photos) >= 2:
        media = []
        for i, photo_url in enumerate(photos[:8]):
            media.append({
                "type": "photo",
                "media": photo_url,
                "caption": caption if i == 0 else "",
                "parse_mode": "Markdown" if i == 0 else "",
            })
        resp = requests.post(f"{api_base}/sendMediaGroup", json={
            "chat_id": CHANNEL_ID,
            "media": media,
        })
    elif len(photos) == 1:
        resp = requests.post(f"{api_base}/sendPhoto", json={
            "chat_id": CHANNEL_ID,
            "photo": photos[0],
            "caption": caption,
            "parse_mode": "Markdown",
        })
    else:
        resp = requests.post(f"{api_base}/sendMessage", json={
            "chat_id": CHANNEL_ID,
            "text": caption,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        })

    if resp.status_code == 200:
        print(f"✅ Опубліковано: {listing['title']}")
    else:
        print(f"❌ Помилка Telegram: {resp.text}")

# --- Головна функція ---
def main():
    print("🔄 Запуск парсера...")
    known_ids = load_ids()
    listings = get_listings()

    if not listings:
        print("Оголошень не знайдено або сайт заблокував запит.")
        return

    new_count = 0
    for listing in listings:
        if listing["id"] in known_ids:
            continue
        print(f"🆕 Нове оголошення: {listing['title']}")
        send_post(listing)
        save_id(listing["id"])
        known_ids.add(listing["id"])
        new_count += 1
        time.sleep(3)

    print(f"✅ Готово. Нових оголошень: {new_count}")

if __name__ == "__main__":
    main()

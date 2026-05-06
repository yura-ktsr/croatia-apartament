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
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "hr-HR,hr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

def load_ids():
    if not os.path.exists(IDS_FILE):
        return set()
    with open(IDS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_id(ad_id):
    with open(IDS_FILE, "a") as f:
        f.write(ad_id + "\n")

def get_listings():
    try:
        session = requests.Session()
        # Спочатку заходимо на головну — щоб отримати cookies
        session.get("https://www.njuskalo.hr", headers=HEADERS, timeout=15)
        time.sleep(2)
        # Тепер робимо реальний запит
        resp = session.get(BASE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        print(f"Статус відповіді: {resp.status_code}")
        print(f"Розмір сторінки: {len(resp.text)} символів")
    except Exception as e:
        print(f"Помилка завантаження сторінки: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # Пробуємо різні селектори
    listings = []

    # Варіант 1 — старий селектор
    items = soup.select("article.entity-body")
    print(f"Варіант 1 (article.entity-body): {len(items)} елементів")

    # Варіант 2
    if not items:
        items = soup.select("li.EntityList-item--Regular")
        print(f"Варіант 2 (li.EntityList-item--Regular): {len(items)} елементів")

    # Варіант 3
    if not items:
        items = soup.select("article")
        print(f"Варіант 3 (article): {len(items)} елементів")

    # Варіант 4 — будь-які посилання на оголошення
    if not items:
        links = soup.select("a[href*='/iznajmljivanje-stanova/']")
        print(f"Варіант 4 (посилання): {len(links)} елементів")
        for link in links[:10]:
            print(f"  Знайдено посилання: {link.get('href', '')[:80]}")
        return []

    for item in items[:10]:
        try:
            link_tag = (
                item.select_one("a.entity-description-title") or
                item.select_one("a.entity-title") or
                item.select_one("h3 a") or
                item.select_one("h2 a") or
                item.select_one("a[href*='njuskalo']")
            )
            if not link_tag:
                print(f"Не знайдено посилання в елементі: {str(item)[:100]}")
                continue

            href = link_tag.get("href", "")
            url = href if href.startswith("http") else "https://www.njuskalo.hr" + href
            ad_id = url.rstrip("/").split("/")[-1].split("?")[0]
            title = link_tag.get_text(strip=True)

            price_tag = (
                item.select_one(".price-box") or
                item.select_one(".price") or
                item.select_one("[class*='price']")
            )
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

def get_photos(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")
        photos = []
        for img in soup.select("img.gallery-foto, img[class*='gallery'], img[class*='photo']")[:8]:
            src = img.get("data-src") or img.get("src")
            if src and src.startswith("http"):
                photos.append(src)
        return photos
    except Exception as e:
        print(f"Помилка отримання фото: {e}")
        return []

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

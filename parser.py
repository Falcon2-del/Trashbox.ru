import os
import requests
from bs4 import BeautifulSoup
import time
import re
import subprocess
import datetime
import random

# Настройки Яндекс Диска
YANDEX_TOKEN = os.environ.get("YANDEX_DISK_TOKEN")
ROOT_FOLDER = "/Моя_Соцсеть"
QUEUE_FOLDER = f"{ROOT_FOLDER}/Очередь/Trashbox"

DB_FILE = "sent_urls.txt"

def load_sent_data(force_pull=False):
    if force_pull:
        try:
            subprocess.run(["git", "pull"], check=False)
        except Exception:
            pass
        
    sent_urls = set()
    sent_titles = set()
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                if "||" in line_str:
                    parts = line_str.split("||", 1)
                    url_part = parts[0].strip().rstrip('/').lower()
                    title_part = parts[1].strip().lower()
                    sent_urls.add(url_part)
                    sent_titles.add(title_part)
                else:
                    url_part = line_str.rstrip('/').lower()
                    sent_urls.add(url_part)
    return sent_urls, sent_titles

def save_sent_data(url, title):
    line_to_write = f"{url.strip()}||{title.strip()}\n"
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(line_to_write)
    
    try:
        subprocess.run(["git", "config", "--local", "user.email", "action@github.com"], check=False)
        subprocess.run(["git", "config", "--local", "user.name", "GitHub Action"], check=False)
        subprocess.run(["git", "add", DB_FILE], check=False)
        subprocess.run(["git", "commit", "-m", f"Add {title[:20]} to history"], check=False)
        subprocess.run(["git", "push"], check=False)
        print("База данных успешно синхронизирована с репозиторием Git.")
    except Exception as e:
        print(f"Ошибка при сохранении базы данных в Git: {e}")

def yandex_create_folder(path):
    url = "https://cloud-api.yandex.net/v1/disk/resources"
    headers = {"Authorization": f"OAuth {YANDEX_TOKEN}"}
    params = {"path": path}
    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 404:
        requests.put(url, headers=headers, params=params)

def yandex_upload_bytes(path, data):
    url = "https://cloud-api.yandex.net/v1/disk/resources/upload"
    headers = {"Authorization": f"OAuth {YANDEX_TOKEN}"}
    params = {"path": path, "overwrite": "true"}
    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 200:
        upload_url = res.json().get("href")
        requests.put(upload_url, data=data)

def save_to_yandex_disk(title, html_body):
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        microsec = datetime.datetime.now().microsecond
        rand_id = random.randint(1000, 9999)
        post_id = f"trashbox_{timestamp}_{microsec}_{rand_id}"
        
        post_queue_path = f"{QUEUE_FOLDER}/{post_id}"
        
        yandex_create_folder(ROOT_FOLDER)
        yandex_create_folder(f"{ROOT_FOLDER}/Очередь")
        yandex_create_folder(QUEUE_FOLDER)
        yandex_create_folder(post_queue_path)
        
        unix_time = str(int(time.time()))
        yandex_upload_bytes(f"{post_queue_path}/time.txt", unix_time.encode('utf-8'))
        
        yandex_upload_bytes(f"{post_queue_path}/content.html", html_body.encode('utf-8'))
        print(f"  [Яндекс.Диск OK] Новость {title} сохранена.")
        return True
    except Exception as e:
        print(f"Ошибка сохранения новости на Яндекс Диск: {e}")
        return False

def get_latest_news():
    sent_urls, sent_titles = load_sent_data(force_pull=True)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    rss_url = "https://trashbox.ru/feed_rss/news/"
    
    try:
        res = requests.get(rss_url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'xml')
        items = soup.find_all('item')
    except Exception as e:
        print(f"Ошибка при получении RSS: {e}")
        return

    new_dispatched = 0

    for item in reversed(items):
        news_url = item.find('link').text.strip()
        title = item.find('title').text.strip()
        
        norm_url = news_url.rstrip('/').lower()
        norm_title = title.lower()

        if norm_url in sent_urls or norm_title in sent_titles:
            continue
            
        print(f"\nНайдена новая новость: {title}")
        print(f"Ссылка: {news_url}")
        
        try:
            page_res = requests.get(news_url, headers=headers, timeout=20)
            page_soup = BeautifulSoup(page_res.text, 'html.parser')
            
            content_div = page_soup.find('div', id=re.compile(r'^item_content_'))
            
            if content_div:
                for s in content_div.find_all(['script', 'style', 'ins', 'iframe']):
                    s.decompose()

                for img in content_div.find_all('img', src=True):
                    src = img['src'].strip()
                    if src.startswith('/') and not src.startswith('//'):
                        img['src'] = "https://trashbox.ru" + src
                    elif src.startswith('//'):
                        img['src'] = "https:" + src
                
                html_body = f"""
                <html>
                <body style="font-family: sans-serif; line-height: 1.6; color: #333; padding:10px;">
                    <h2>{title}</h2>
                    {str(content_div)}
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    <p><a href="{news_url}">Читать оригинал на Trashbox.ru</a></p>
                </body>
                </html>
                """
            else:
                html_body = f"<html><body><h2>{title}</h2>Контент не найден. <a href='{news_url}'>Перейти на сайт</a></body></html>"

            if save_to_yandex_disk(title, html_body):
                save_sent_data(news_url, title)
                new_dispatched += 1
                
                print("Пауза 5 секунд...")
                time.sleep(5)
            
        except Exception as e:
            print(f"Ошибка при обработке {news_url}: {e}")

    if new_dispatched == 0:
        print("Новых новостей нет.")

if __name__ == "__main__":
    if not YANDEX_TOKEN:
        print("Ошибка: Переменная YANDEX_DISK_TOKEN не задана")
    else:
        get_latest_news()

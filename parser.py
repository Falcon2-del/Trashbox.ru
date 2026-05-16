import os
import requests
from bs4 import BeautifulSoup
import smtplib
import time
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Настройки из переменных окружения
EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER')
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

DB_FILE = "sent_urls.txt"

def load_sent_urls():
    """Загружает список уже отправленных URL из файла."""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            # Очищаем от пробелов и пустых строк
            return set(line.strip() for line in f if line.strip())
    return set()

def save_sent_url(url):
    """Добавляет новый URL в файл базы данных."""
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(url.strip() + "\n")

def send_email(subject, html_content):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"Trashbox.ru: {subject}"
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Письмо успешно отправлено: {subject}")
        time.sleep(2)
    except Exception as e:
        print(f"Ошибка при отправке почты: {e}")

def parse_trashbox():
    url = "https://trashbox.ru/news"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    
    print("Запрашиваем главную страницу новостей...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    link_pattern = re.compile(r'/link/\d{4}-\d{2}-\d{2}')
    
    # 1. Загружаем базу данных
    sent_urls = load_sent_urls()
    
    # 2. Собираем только уникальные и новые ссылки
    valid_links = []
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if link_pattern.search(href):
            full_url = href if href.startswith('http') else "https://trashbox.ru" + href
            # Проверка на дубликаты внутри одного запуска и по базе данных
            if full_url not in valid_links and full_url not in sent_urls:
                valid_links.append(full_url)

    print(f"Найдено новых новостей для отправки: {len(valid_links)}")

    new_dispatched = 0
    # Идем от старых к новым
    for news_url in reversed(valid_links):
        print(f"Парсим новую статью: {news_url}")
        
        try:
            news_res = requests.get(news_url, headers=headers, timeout=15)
            news_res.raise_for_status()
            news_soup = BeautifulSoup(news_res.text, 'html.parser')
            
            title_tag = news_soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "Без названия"
            
            content_div = (
                news_soup.find('div', id='topic_content') or 
                news_soup.find('div', class_='topic_content') or
                news_soup.find('div', class_='content_text') or
                news_soup.find('article')
            )
            
            if content_div:
                # Чистим комментарии и мусор
                for trash in content_div.find_all(['div', 'section', 'form'], 
                                                 id=re.compile(r'comments|comm_cont|reply_form'),
                                                 class_=re.compile(r'comments|comm_cont')):
                    trash.decompose()
                
                for s in content_div(['script', 'style', 'iframe', 'ins', 'form']):
                    s.decompose()
                
                html_body = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: sans-serif; line-height: 1.6; color: #333; }}
                        img {{ max-width: 100%; height: auto; display: block; margin: 10px 0; }}
                        .source-link {{ margin-top: 20px; border-top: 1px solid #eee; padding-top: 10px; }}
                    </style>
                </head>
                <body>
                    {str(content_div)}
                    <div class="source-link">
                        <p><a href="{news_url}">Читать оригинал на Trashbox.ru</a></p>
                    </div>
                </body>
                </html>
                """
            else:
                html_body = f"Контент не найден. <a href='{news_url}'>Читать на сайте</a>"

            send_email(title, html_body)
            save_sent_url(news_url)
            new_dispatched += 1
            
        except Exception as e:
            print(f"Ошибка при обработке {news_url}: {e}")

    if new_dispatched == 0:
        print("Новых новостей не обнаружено.")

if __name__ == "__main__":
    parse_trashbox()

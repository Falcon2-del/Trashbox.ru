import os
import requests
from bs4 import BeautifulSoup
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Настройки из переменных окружения (GitHub Secrets)
EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER')
SMTP_SERVER = "smtp.gmail.com"  # Например, для Gmail
SMTP_PORT = 587

DB_FILE = "sent_urls.txt"

def load_sent_urls():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_sent_url(url):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

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
        print(f"Письмо отправлено: {subject}")
        # Интервал 2 секунды между письмами
        time.sleep(2)
    except Exception as e:
        print(f"Ошибка при отправке: {e}")

def parse_trashbox():
    url = "https://trashbox.ru/news"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки главной страницы: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Формируем шаблон ссылки на основе текущей даты: /link/YYYY-MM-DD
    today_str = datetime.now().strftime("%Y-%m-%d")
    date_pattern = f"/link/{today_str}"
    print(f"Ищем новости с паттерном: {date_pattern}")

    # Собираем все ссылки, которые ведут на новости за сегодня
    valid_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if date_pattern in href:
            # Приводим к полному URL, если ссылка относительная
            full_url = href if href.startswith('http') else "https://trashbox.ru" + href
            if full_url not in valid_links:
                valid_links.append(full_url)

    if not valid_links:
        print("Новых новостей за сегодня не найдено.")
        return

    sent_urls = load_sent_urls()
    
    # Обрабатываем ссылки (разворачиваем список, чтобы старые шли первыми, а новые последними)
    for news_url in reversed(valid_links):
        if news_url in sent_urls:
            continue  # Пропускаем, если уже отправляли

        print(f"Обработка новой новости: {news_url}")
        
        try:
            news_res = requests.get(news_url, headers=headers)
            news_res.raise_for_status()
            news_soup = BeautifulSoup(news_res.text, 'html.parser')
            
            title_tag = news_soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "Без названия"
            
            content_div = news_soup.find('div', id='topic_content')
            
            if content_div:
                for s in content_div(['script', 'style']):
                    s.decompose()
                html_body = str(content_div)
            else:
                html_body = "Не удалось извлечь содержимое новости."

            # Отправляем и запоминаем
            send_email(title, html_body)
            save_sent_url(news_url)
            
        except Exception as e:
            print(f"Ошибка при обработке новости {news_url}: {e}")

if __name__ == "__main__":
    parse_trashbox()

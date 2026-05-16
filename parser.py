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
        print(f"Письмо успешно отправлено: {subject}")
        time.sleep(2)
    except Exception as e:
        print(f"Ошибка при отправке почты: {e}")

def parse_trashbox():
    url = "https://trashbox.ru/news"
    # Расширенный User-Agent, чтобы сайт не блокировал GitHub хостинг
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3'
    }
    
    print("Запрашиваем главную страницу новостей...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"Статус ответа сайта: {response.status_code}")
        response.raise_for_status()
    except Exception as e:
        print(f"Критическая ошибка загрузки сайта: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Регулярное выражение для поиска ссылок вида /link/YYYY-MM-DD-...
    # Это полностью решает проблему с разницей часовых поясов
    link_pattern = re.compile(r'/link/\d{4}-\d{2}-\d{2}')
    
    valid_links = []
    all_links_count = 0
    
    for a in soup.find_all('a', href=True):
        all_links_count += 1
        href = a['href']
        if link_pattern.search(href):
            full_url = href if href.startswith('http') else "https://trashbox.ru" + href
            if full_url not in valid_links:
                valid_links.append(full_url)

    print(f"Всего тегов ла ссылки на странице: {all_links_count}")
    print(f"Найдено подходящих новостных ссылок: {len(valid_links)}")

    if not valid_links:
        print("Список новостей пуст. Возможно, сайт изменил структуру или заблокировал запрос.")
        # Выведем кусочек кода страницы в лог для диагностики
        print("Кусочек HTML для проверки:")
        print(response.text[:1000])
        return

    sent_urls = load_sent_urls()
    print(f"Уже было отправлено ранее: {len(sent_urls)} новостей.")
    
    new_dispatched = 0
    # Идем снизу вверх (от старых к самым свежим)
    for news_url in reversed(valid_links):
        if news_url in sent_urls:
            continue

        print(f"Парсим новую статью: {news_url}")
        new_dispatched += 1
        
        try:
            news_res = requests.get(news_url, headers=headers, timeout=15)
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

            send_email(title, html_body)
            save_sent_url(news_url)
            
        except Exception as e:
            print(f"Ошибка при обработке новости {news_url}: {e}")

    if new_dispatched == 0:
        print("Все найденные новости уже отправлялись ранее.")

if __name__ == "__main__":
    parse_trashbox()

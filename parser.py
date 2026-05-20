import os
import requests
from bs4 import BeautifulSoup
import smtplib
import time
import re
import subprocess
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
    # Перед чтением подтягиваем свежие данные из репозитория, на случай если параллельно идет отправка
    try:
        subprocess.run(["git", "pull"], check=False)
    except Exception:
        pass
        
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return set(line.strip().rstrip('/').lower() for line in f if line.strip())
    return set()

def save_sent_url(url):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(url.strip().rstrip('/').lower() + "\n")
    
    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ДЛЯ CRON-JOB: сохраняем в гит сразу после отправки поста
    try:
        subprocess.run(["git", "config", "--local", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
        subprocess.run(["git", "config", "--local", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "add", DB_FILE], check=False)
        res = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
        if res.returncode != 0:
            subprocess.run(["git", "commit", "-m", "Update database [skip ci]"], check=False)
            subprocess.run(["git", "push"], check=False)
    except Exception as e:
        print(f"Ошибка сохранения в Git: {e}")

def send_email(subject, html_content):
    clean_subject = " ".join(subject.split())
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"Trashbox.ru"
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Письмо отправлено: {clean_subject}")
    except Exception as e:
        print(f"Ошибка почты: {e}")

def parse_trashbox():
    url = "https://trashbox.ru/news"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    print("Проверка новостей...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки сайта: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    link_pattern = re.compile(r'/link/\d{4}-\d{2}-\d{2}')
    
    sent_urls = load_sent_urls()
    found_links = []

    # Собираем ссылки
    for a in soup.find_all('a', href=True):
        href = a['href'].strip().split('?')[0].rstrip('/')
        
        if link_pattern.search(href):
            full_url = href if href.startswith('http') else "https://trashbox.ru" + href
            full_url = full_url.lower()
            
            if full_url not in sent_urls and full_url not in found_links:
                found_links.append(full_url)

    print(f"К отправке: {len(found_links)} уникальных новостей.")

    new_dispatched = 0
    for news_url in reversed(found_links):
        # Перепроверяем по свежей актуальной базе перед каждым постом
        sent_urls = load_sent_urls()
        if news_url in sent_urls:
            continue

        print(f"Обработка статьи: {news_url}")
        
        try:
            news_res = requests.get(news_url, headers=headers, timeout=15)
            news_res.raise_for_status()
            news_soup = BeautifulSoup(news_res.text, 'html.parser')
            
            title_tag = news_soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "Без названия"
            
            content_div = (
                news_soup.find('div', id='topic_content') or 
                news_soup.find('div', class_='topic_content') or
                news_soup.find('article')
            )
            
            if content_div:
                # Глубокая очистка контента от мусора
                for trash in content_div.find_all(['div', 'section', 'form', 'script', 'style', 'iframe', 'ins'], 
                                                 id=re.compile(r'comments|comm_cont|reply_form|related|tags'),
                                                 class_=re.compile(r'comments|comm_cont|topic_tags')):
                    trash.decompose()
                
                for s in content_div(['script', 'style', 'iframe', 'ins', 'form']):
                    s.decompose()

                # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ДЛЯ КАРТИНОК И АВАТАРОК
                for img in content_div.find_all('img', src=True):
                    src = img['src'].strip()
                    if src.startswith('/') and not src.startswith('//'):
                        img['src'] = "https://trashbox.ru" + src
                    elif src.startswith('//'):
                        img['src'] = "https:" + src
                
                html_body = f"""
                <html>
                <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
                    {str(content_div)}
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    <p><a href="{news_url}">Читать оригинал на Trashbox.ru</a></p>
                </body>
                </html>
                """
            else:
                html_body = f"Контент не найден. <a href='{news_url}'>Перейти на сайт</a>"

            send_email(title, html_body)
            
            # Сохраняем в файл и отправляем коммит немедленно
            save_sent_url(news_url)
            new_dispatched += 1
            
            print("Пауза 5 секунд...")
            time.sleep(5)
            
        except Exception as e:
            print(f"Ошибка при обработке {news_url}: {e}")

    if new_dispatched == 0:
        print("Новых новостей нет.")

if __name__ == "__main__":
    parse_trashbox()

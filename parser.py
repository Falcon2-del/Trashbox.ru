import os
import requests
from bs4 import BeautifulSoup
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Настройки из переменных окружения (GitHub Secrets)
EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER')
SMTP_SERVER = "smtp.gmail.com"  # Например, для Gmail
SMTP_PORT = 587

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
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Находим все ссылки на новости
    links = soup.select('a.topic_p_title')
    
    if not links:
        print("Новости не найдены.")
        return

    # Берем самую свежую новость (первую в списке)
    latest_news_url = "https://trashbox.ru" + links[0]['href']
    
    # Заходим в саму новость для получения полного контента
    news_res = requests.get(latest_news_url, headers=headers)
    news_soup = BeautifulSoup(news_res.text, 'html.parser')
    
    title = news_soup.find('h1').get_text(strip=True)
    
    # Ищем основной контент новости
    content_div = news_soup.find('div', id='topic_content')
    
    if content_div:
        # Очищаем от лишних скриптов или рекламы
        for s in content_div(['script', 'style']):
            s.decompose()
        html_body = str(content_div)
    else:
        html_body = "Не удалось извлечь содержимое новости."

    send_email(title, html_body)

if __name__ == "__main__":
    parse_trashbox()

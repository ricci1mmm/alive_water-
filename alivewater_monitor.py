import os
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot
from telegram.ext import Updater, CommandHandler

# Конфигурация
CONFIG = {
    "login_url": "https://my.alivewater.cloud",
    "sales_url": "https://my.alivewater.cloud/sales",
    "terminals_url": "https://my.alivewater.cloud/terminals",
    "telegram_token": os.getenv("TELEGRAM_TOKEN"),
    "telegram_admin_ids": [1371753467, 867982256],
    "login": os.getenv("LOGIN"),
    "password": os.getenv("PASSWORD"),
    "data_file": "data.json"
}

def init_bot():
    return Bot(token=CONFIG['telegram_token'])

bot = init_bot()

def load_data():
    try:
        with open(CONFIG['data_file'], 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_sales": [], "last_notifications": []}

def save_data(data):
    with open(CONFIG['data_file'], 'w') as f:
        json.dump(data, f)

def init_browser():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Для GitHub Actions
    options.binary_location = "/usr/bin/chromium-browser"
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(10)
    return driver

def login(driver):
    try:
        driver.get(CONFIG['login_url'])
        time.sleep(2)
        
        # Принимаем всплывающее окно, если есть
        try:
            accept_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.ant-btn-primary"))
            )
            accept_btn.click()
            time.sleep(1)
        except:
            pass
        
        # Вводим данные
        driver.find_element(By.CSS_SELECTOR, "input[name='login']").send_keys(CONFIG['login'])
        time.sleep(0.5)
        driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(CONFIG['password'])
        time.sleep(0.5)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        
        # Проверяем успешность входа
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "._container_iuuwv_1"))
        )
        return True
    except Exception as e:
        print(f"Ошибка авторизации: {str(e)}")
        return False

def check_sales(driver):
    try:
        driver.get(CONFIG['sales_url'])
        time.sleep(3)
        
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        return [{
            "number": cols[0].text,
            "address": cols[1].text,
            "time": cols[2].text,
            "liters": cols[3].text,
            "total": cols[4].text,
            "payment": cols[5].text if len(cols) > 5 else "Не указано"
        } for cols in (row.find_elements(By.TAG_NAME, "td") for row in rows) if len(cols) >= 5]
    except Exception as e:
        print(f"Ошибка при проверке продаж: {str(e)}")
        return []

def check_terminals(driver):
    try:
        driver.get(CONFIG['terminals_url'])
        time.sleep(3)
        
        warnings = driver.find_elements(By.CSS_SELECTOR, "svg[data-icon='exclamation-circle']")
        if not warnings:
            return []
            
        return [{
            "terminal": link.text,
            "url": link.get_attribute("href")
        } for link in driver.find_elements(By.CSS_SELECTOR, "a[href^='/terminal/']")
          if any(warning in link.find_element(By.XPATH, "./..").get_attribute("innerHTML") 
                for warning in warnings)]
    except Exception as e:
        print(f"Ошибка при проверке терминалов: {str(e)}")
        return []

def send_telegram_notification(message):
    for chat_id in CONFIG['telegram_admin_ids']:
        try:
            bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            print(f"Ошибка отправки в Telegram: {e}")

def format_sales(sales):
    return "<b>Новые продажи:</b>\n\n" + "\n".join(
        f"<b>№:</b> {s['number']}\n"
        f"<b>Адрес:</b> {s['address']}\n"
        f"<b>Время:</b> {s['time']}\n"
        f"<b>Литры:</b> {s['liters']}\n"
        f"<b>Всего:</b> {s['total']}\n"
        f"<b>Оплата:</b> {s['payment']}\n"
        for s in sales
    )

def format_problems(problems):
    return "<b>Проблемы с терминалами:</b>\n\n" + "\n".join(
        f"<b>Терминал:</b> {p['terminal']}\n<b>Ссылка:</b> {p['url']}\n"
        for p in problems
    )

def main_monitoring():
    driver = init_browser()
    try:
        if login(driver):
            data = load_data()
            
            # Проверка продаж
            sales = check_sales(driver)
            new_sales = [s for s in sales if s not in data['last_sales']]
            if new_sales:
                send_telegram_notification(format_sales(new_sales))
                data['last_sales'] = sales
            
            # Проверка терминалов
            problems = check_terminals(driver)
            new_problems = [p for p in problems if p not in data['last_notifications']]
            if new_problems:
                send_telegram_notification(format_problems(new_problems))
                data['last_notifications'] = problems
            
            save_data(data)
    except Exception as e:
        print(f"Ошибка мониторинга: {str(e)}")
    finally:
        driver.quit()

def start(update, context):
    update.message.reply_text(
        "Бот мониторинга AliveWater работает. Используйте /check_sales или /check_terminals")

def check_sales(update, context):
    if update.message.from_user.id not in CONFIG['telegram_admin_ids']:
        update.message.reply_text("Доступ запрещен")
        return
    
    update.message.reply_text("Начинаю проверку продаж...")
    main_monitoring()
    update.message.reply_text("Проверка завершена")

def check_terminals(update, context):
    if update.message.from_user.id not in CONFIG['telegram_admin_ids']:
        update.message.reply_text("Доступ запрещен")
        return
    
    update.message.reply_text("Начинаю проверку терминалов...")
    main_monitoring()
    update.message.reply_text("Проверка завершена")

def main():
    updater = Updater(token=CONFIG['telegram_token'], use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("check_sales", check_sales))
    dp.add_handler(CommandHandler("check_terminals", check_terminals))
    
    updater.start_polling()
    
    # Основной цикл мониторинга
    while True:
        main_monitoring()
        time.sleep(300)

if __name__ == "__main__":
    main()

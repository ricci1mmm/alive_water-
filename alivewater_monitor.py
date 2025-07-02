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
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext

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

# Инициализация бота Telegram
bot = Bot(token=CONFIG['telegram_token'])

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

# ... (остальные функции остаются без изменений, как в предыдущем исправленном скрипте)

def main():
    # Инициализация Telegram бота
    updater = Updater(token=CONFIG['telegram_token'])
    dispatcher = updater.dispatcher
    
    # Регистрация обработчиков команд
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("check_sales", check_sales_command))
    dispatcher.add_handler(CommandHandler("check_terminals", check_terminals_command))
    dispatcher.add_handler(CommandHandler("status", status_command))
    
    # Запуск бота
    updater.start_polling()
    
    # Запуск мониторинга
    while True:
        try:
            main_monitoring()
        except Exception as e:
            print(f"Ошибка мониторинга: {str(e)}")
        time.sleep(300)  # Проверка каждые 5 минут

if __name__ == "__main__":
    main()

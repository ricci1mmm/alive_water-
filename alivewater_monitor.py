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
from telegram import Update
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

def login(driver):
    driver.get(CONFIG['login_url'])
    
    # Принимаем всплывающее окно
    try:
        accept_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.ant-btn-primary"))
        )
        accept_btn.click()
        time.sleep(2)
    except:
        pass
    
    # Вводим логин и пароль
    login_field = driver.find_element(By.CSS_SELECTOR, "input[name='login']")
    password_field = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
    
    login_field.send_keys(CONFIG['login'])
    time.sleep(1)
    password_field.send_keys(CONFIG['password'])
    time.sleep(1)
    
    # Кнопка становится активной после ввода данных
    login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    login_btn.click()
    
    # Проверяем успешность входа
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "._container_iuuwv_1"))
        )
        return True
    except:
        return False

def check_sales(driver):
    driver.get(CONFIG['sales_url'])
    time.sleep(3)
    
    # Получаем таблицу продаж
    try:
        table = driver.find_element(By.CSS_SELECTOR, "table")
        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        
        sales = []
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 5:
                sale = {
                    "number": cols[0].text,
                    "address": cols[1].text,
                    "time": cols[2].text,
                    "liters": cols[3].text,
                    "total": cols[4].text,
                    "payment": cols[5].text if len(cols) > 5 else "Не указано"
                }
                sales.append(sale)
        
        return sales
    except:
        return []

def check_terminals(driver):
    driver.get(CONFIG['terminals_url'])
    time.sleep(3)
    
    # Проверяем наличие предупреждений
    try:
        warnings = driver.find_elements(By.CSS_SELECTOR, "svg[data-icon='exclamation-circle']")
        if warnings:
            terminal_links = driver.find_elements(By.CSS_SELECTOR, "a[href^='/terminal/']")
            problems = []
            for link in terminal_links:
                if any(warning in link.find_element(By.XPATH, "./..").get_attribute("innerHTML") for warning in warnings):
                    problems.append({
                        "terminal": link.text,
                        "url": link.get_attribute("href")
                    })
            return problems
    except:
        pass
    
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

def format_sales_message(sales):
    message = "<b>Новые продажи:</b>\n\n"
    for sale in sales:
        message += (
            f"<b>№:</b> {sale['number']}\n"
            f"<b>Адрес:</b> {sale['address']}\n"
            f"<b>Время:</b> {sale['time']}\n"
            f"<b>Литры:</b> {sale['liters']}\n"
            f"<b>Всего:</b> {sale['total']}\n"
            f"<b>Оплата:</b> {sale['payment']}\n\n"
        )
    return message

def format_problems_message(problems):
    message = "<b>Обнаружены проблемы с терминалами:</b>\n\n"
    for problem in problems:
        message += f"<b>Терминал:</b> {problem['terminal']}\n<b>Ссылка:</b> {problem['url']}\n\n"
    return message

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Привет! Я бот для мониторинга AliveWater.\n\n"
        "Доступные команды:\n"
        "/check_sales - Проверить новые продажи\n"
        "/check_terminals - Проверить состояние терминалов\n"
        "/status - Проверить статус системы"
    )

def check_sales_command(update: Update, context: CallbackContext):
    if update.effective_user.id not in CONFIG['telegram_admin_ids']:
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return
    
    update.message.reply_text("Проверяю новые продажи...")
    
    driver = init_browser()
    try:
        if login(driver):
            sales = check_sales(driver)
            data = load_data()
            
            new_sales = [s for s in sales if s not in data['last_sales']]
            if new_sales:
                message = format_sales_message(new_sales)
                send_telegram_notification(message)
                data['last_sales'] = sales
                save_data(data)
                update.message.reply_text(f"Найдено {len(new_sales)} новых продаж.")
            else:
                update.message.reply_text("Новых продаж не обнаружено.")
        else:
            update.message.reply_text("Ошибка авторизации.")
    except Exception as e:
        update.message.reply_text(f"Ошибка: {str(e)}")
    finally:
        driver.quit()

def check_terminals_command(update: Update, context: CallbackContext):
    if update.effective_user.id not in CONFIG['telegram_admin_ids']:
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return
    
    update.message.reply_text("Проверяю состояние терминалов...")
    
    driver = init_browser()
    try:
        if login(driver):
            problems = check_terminals(driver)
            data = load_data()
            
            new_problems = [p for p in problems if p not in data['last_notifications']]
            if new_problems:
                message = format_problems_message(new_problems)
                send_telegram_notification(message)
                data['last_notifications'] = problems
                save_data(data)
                update.message.reply_text(f"Найдено {len(new_problems)} проблем с терминалами.")
            else:
                update.message.reply_text("Проблем с терминалами не обнаружено.")
        else:
            update.message.reply_text("Ошибка авторизации.")
    except Exception as e:
        update.message.reply_text(f"Ошибка: {str(e)}")
    finally:
        driver.quit()

def status_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Система мониторинга AliveWater работает.\n"
        f"Последняя проверка: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

def main_monitoring():
    driver = init_browser()
    try:
        if login(driver):
            # Проверка продаж
            sales = check_sales(driver)
            data = load_data()
            
            new_sales = [s for s in sales if s not in data['last_sales']]
            if new_sales:
                message = format_sales_message(new_sales)
                send_telegram_notification(message)
                data['last_sales'] = sales
            
            # Проверка терминалов
            problems = check_terminals(driver)
            
            new_problems = [p for p in problems if p not in data['last_notifications']]
            if new_problems:
                message = format_problems_message(new_problems)
                send_telegram_notification(message)
                data['last_notifications'] = problems
            
            save_data(data)
    except Exception as e:
        print(f"Ошибка мониторинга: {str(e)}")
    finally:
        driver.quit()

def main():
    # Инициализация Telegram бота
    updater = Updater(token=CONFIG['telegram_token'], use_context=True)
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
        main_monitoring()
        time.sleep(300)  # Проверка каждые 5 минут

if __name__ == "__main__":
    main()

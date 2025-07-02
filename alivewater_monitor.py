import os
import time
import json
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from telegram import Bot
from telegram.ext import Updater, CommandHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")
    
    # Добавляем параметры для решения проблемы с DevToolsActivePort
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-browser-side-navigation")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    # Для GitHub Actions
    options.binary_location = "/usr/bin/chromium-browser"
    
    # Используем системный chromedriver
    service = Service(executable_path="/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(10)
    return driver

def login(driver):
    try:
        driver.get(CONFIG['login_url'])
        time.sleep(2)
        
        # Принимаем всплывающее окно
        try:
            accept_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.ant-btn-primary"))
            )
            accept_btn.click()
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Всплывающее окно не найдено: {str(e)}")
        
        # Вводим логин и пароль
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
        logger.error(f"Ошибка авторизации: {str(e)}")
        return False

def check_sales(driver):
    try:
        driver.get(CONFIG['sales_url'])
        time.sleep(3)
        
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        sales = []
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 5:
                # Определяем способ оплаты по содержимому SVG
                payment_method = "Не указано"
                payment_icons = cols[5].find_elements(By.TAG_NAME, "svg")
                
                for icon in payment_icons:
                    # Получаем содержимое элемента path
                    paths = icon.find_elements(By.TAG_NAME, "path")
                    for path in paths:
                        d_attr = path.get_attribute("d")
                        
                        # Определяем по уникальным частям пути
                        if d_attr:
                            # Банковская карта
                            if "v8c0 6.6-5.4 12-12 12" in d_attr:
                                payment_method = "💳 Карта"
                                break
                                
                            # Купюры
                            elif "c-53.02 0-96 50.14-96 112" in d_attr:
                                payment_method = "💵 Купюры"
                                break
                                
                            # Монеты
                            elif "c-48.6 0-92.6 9-124.5 23.4" in d_attr:
                                payment_method = "🪙 Монеты"
                                break
                
                sales.append({
                    "number": cols[0].text,
                    "address": cols[1].text,
                    "time": cols[2].text,
                    "liters": cols[3].text,
                    "total": cols[4].text,
                    "payment": payment_method
                })
        return sales
    except Exception as e:
        logger.error(f"Ошибка при проверке продаж: {str(e)}")
        return []

def check_terminals(driver):
    try:
        driver.get(CONFIG['terminals_url'])
        time.sleep(3)
        
        warnings = driver.find_elements(By.CSS_SELECTOR, "svg[data-icon='exclamation-circle']")
        if not warnings:
            return []
        
        problems = []
        terminal_links = driver.find_elements(By.CSS_SELECTOR, "a[href^='/terminal/']")
        for link in terminal_links:
            parent_html = link.find_element(By.XPATH, "./..").get_attribute("innerHTML")
            if any(warning.get_attribute("outerHTML") in parent_html for warning in warnings):
                problems.append({
                    "terminal": link.text,
                    "url": link.get_attribute("href")
                })
        return problems
    except Exception as e:
        logger.error(f"Ошибка при проверке терминалов: {str(e)}")
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
            logger.info(f"Сообщение отправлено в Telegram: {chat_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")

def format_sales(sales):
    if not sales:
        return "🛍️ Нет новых продаж"
    
    message = "💰 <b>НОВЫЕ ПРОДАЖИ</b> 💰\n\n"
    for sale in sales:
        message += (
            f"🔹 <b>Продажа #{sale['number']}</b>\n"
            f"📍 <b>Адрес:</b> {sale['address']}\n"
            f"🕒 <b>Время:</b> {sale['time']}\n"
            f"💧 <b>Литры:</b> {sale['liters']}\n"
            f"💸 <b>Сумма:</b> {sale['total']} руб.\n"
            f"🧾 <b>Оплата:</b> {sale['payment']}\n"
            f"────────────────────\n"
        )
    message += f"\nВсего новых продаж: <b>{len(sales)}</b>"
    return message

def format_problems(problems):
    if not problems:
        return "✅ Проблем с терминалами не обнаружено"
    
    message = "⚠️ <b>ПРОБЛЕМЫ С ТЕРМИНАЛАМИ</b> ⚠️\n\n"
    for problem in problems:
        message += (
            f"🔴 <b>Терминал:</b> {problem['terminal']}\n"
            f"🔗 <b>Ссылка:</b> {problem['url']}\n"
            f"────────────────────\n"
        )
    message += f"\nВсего проблемных терминалов: <b>{len(problems)}</b>"
    return message

def start(update, context):
    menu_text = (
        "🚰 <b>Бот мониторинга AliveWater</b> 🚰\n\n"
        "Выберите действие:\n\n"
        "💳 /check_sales - Проверить новые продажи\n"
        "⚠️ /check_terminals - Проверить состояние терминалов\n"
        "ℹ️ /status - Статус системы\n"
        "🆘 /help - Помощь"
    )
    update.message.reply_text(menu_text, parse_mode="HTML")

def help_command(update, context):
    help_text = (
        "🆘 <b>Помощь по боту</b>\n\n"
        "Этот бот автоматически отслеживает:\n"
        "- Новые продажи воды 💧\n"
        "- Проблемы с терминалами ⚠️\n\n"
        "Автоматическая проверка происходит каждые 5 минут\n\n"
        "<b>Доступные команды:</b>\n"
        "💳 /check_sales - Проверить новые продажи\n"
        "⚠️ /check_terminals - Проверить состояние терминалов\n"
        "ℹ️ /status - Статус системы\n"
        "🆘 /help - Помощь"
    )
    update.message.reply_text(help_text, parse_mode="HTML")

def check_sales_command(update, context):
    if update.message.from_user.id not in CONFIG['telegram_admin_ids']:
        update.message.reply_text("⛔ Доступ запрещен")
        return
    
    update.message.reply_text("🔍 Проверяю новые продажи...")
    try:
        driver = init_browser()
        if login(driver):
            sales = check_sales(driver)
            data = load_data()
            
            new_sales = [s for s in sales if s not in data['last_sales']]
            if new_sales:
                message = format_sales(new_sales)
                send_telegram_notification(message)
                data['last_sales'] = sales
                save_data(data)
                update.message.reply_text(f"✅ Найдено {len(new_sales)} новых продаж!", parse_mode="HTML")
            else:
                update.message.reply_text("🛍️ Новых продаж не обнаружено", parse_mode="HTML")
        else:
            update.message.reply_text("🔐 Ошибка авторизации", parse_mode="HTML")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        logger.error(f"Ошибка в check_sales_command: {str(e)}")
    finally:
        driver.quit()

def check_terminals_command(update, context):
    if update.message.from_user.id not in CONFIG['telegram_admin_ids']:
        update.message.reply_text("⛔ Доступ запрещен")
        return
    
    update.message.reply_text("🔍 Проверяю состояние терминалов...")
    try:
        driver = init_browser()
        if login(driver):
            problems = check_terminals(driver)
            data = load_data()
            
            new_problems = [p for p in problems if p not in data['last_notifications']]
            if new_problems:
                message = format_problems(new_problems)
                send_telegram_notification(message)
                data['last_notifications'] = problems
                save_data(data)
                update.message.reply_text(f"⚠️ Найдено {len(new_problems)} проблем с терминалами!", parse_mode="HTML")
            else:
                update.message.reply_text("✅ Проблем с терминалами не обнаружено", parse_mode="HTML")
        else:
            update.message.reply_text("🔐 Ошибка авторизации", parse_mode="HTML")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        logger.error(f"Ошибка в check_terminals_command: {str(e)}")
    finally:
        driver.quit()

def status_command(update, context):
    status_text = (
        "🟢 <b>Статус системы</b>\n\n"
        "Система мониторинга AliveWater работает в штатном режиме\n"
        f"🕒 Последняя проверка: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "Следующая автоматическая проверка через 5 минут"
    )
    update.message.reply_text(status_text, parse_mode="HTML")

def main_monitoring():
    logger.info("Запуск автоматической проверки...")
    try:
        driver = init_browser()
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
            logger.info("Автоматическая проверка завершена успешно")
        else:
            logger.error("Ошибка авторизации при автоматической проверке")
    except Exception as e:
        logger.error(f"Ошибка в main_monitoring: {str(e)}")
    finally:
        driver.quit()

def main():
    logger.info("Запуск бота мониторинга...")
    
    # Инициализация Telegram бота
    updater = Updater(CONFIG['telegram_token'], use_context=True)
    dispatcher = updater.dispatcher
    
    # Регистрация обработчиков команд
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("check_sales", check_sales_command))
    dispatcher.add_handler(CommandHandler("check_terminals", check_terminals_command))
    dispatcher.add_handler(CommandHandler("status", status_command))
    
    # Запуск бота
    updater.start_polling()
    
    # Запуск автоматического мониторинга
    while True:
        main_monitoring()
        time.sleep(300)  # Проверка каждые 5 минут

if __name__ == "__main__":
    main()

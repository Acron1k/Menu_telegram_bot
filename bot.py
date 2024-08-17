from telegram.ext import ApplicationBuilder
from handlers import register_handlers  # Импорт функции регистрации обработчиков
from database import create_tables      # Импорт функции создания таблиц в базе данных
from dotenv import load_dotenv
import os

# Загрузка переменных окружения из файла .env
load_dotenv()

# Получение токена из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if __name__ == '__main__':
    # Создание таблиц в базе данных
    create_tables()
    
    # Инициализация бота
    app = ApplicationBuilder().token(BOT_TOKEN).read_timeout(30).connect_timeout(30).build()
    
    # Регистрация всех обработчиков
    register_handlers(app)

    # Запуск бота
    app.run_polling()

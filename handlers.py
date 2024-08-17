from telegram import ReplyKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters
from database import get_db_connection

# Функции-обработчики

async def start(update, context):
    keyboard = [
        ["Добавить блюдо", "Меню"],
        ["Удалить блюдо", "Изменить блюдо"],
        ["Добавить детали", "Помощь"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привет! Я твой бот-помощник с едой. Выберите команду:", reply_markup=reply_markup)

async def list_dishes(update, context):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM dishes")
    dishes = cursor.fetchall()
    
    if not dishes:
        await update.message.reply_text("Меню пока пустое.")
        return
    
    dishes_list = "\n".join([dish[0] for dish in dishes])
    await update.message.reply_text(f"Текущие блюда в меню:\n{dishes_list}")

async def help_command(update, context):
    help_text = (
        "/start - Начать работу с ботом\n"
        "/add_dish - Добавить блюдо\n"
        "/menu - Показать текущее меню\n"
        "/delete_dish - Удалить блюдо\n"
        "/edit_dish - Изменить название блюда\n"
        "/add_details - Добавить ингредиенты и рецепт\n"
        "/help - Показать это сообщение"
    )
    await update.message.reply_text(help_text)

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    from states import add_details_handler, dish_handler, edit_dish_handler, delete_dish_handler  # Импорт состояний здесь
    app.add_handler(dish_handler)
    app.add_handler(edit_dish_handler)
    app.add_handler(delete_dish_handler)
    app.add_handler(add_details_handler)
    app.add_handler(MessageHandler(filters.Regex("^(Меню)$"), list_dishes))
    app.add_handler(MessageHandler(filters.Regex("^(Помощь)$"), help_command))

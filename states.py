from telegram.ext import ConversationHandler, MessageHandler, filters, CommandHandler
from handlers import start
from database import get_db_connection  # Импорт функции для подключения к базе данных

# Определение состояний
ADDING_DISH, ADDING_INGREDIENTS, ADDING_RECIPE, EDITING_DISH, DELETING_DISH, ADDING_DETAILS = range(6)

async def add_dish(update, context):
    await update.message.reply_text("Напишите название блюда, которое вы хотите добавить.")
    return ADDING_DISH

async def save_dish(update, context):
    dish_name = update.message.text
    conn = get_db_connection()  # Подключение к базе данных
    cursor = conn.cursor()
    cursor.execute("INSERT INTO dishes (name) VALUES (?)", (dish_name,))
    conn.commit()
    await update.message.reply_text(f'Блюдо "{dish_name}" добавлено в меню.')
    return ConversationHandler.END

async def add_ingredients(update, context):
    context.user_data['dish_name'] = update.message.text
    await update.message.reply_text("Введите ингредиенты для этого блюда в формате: название_ингредиента, количество, единица_измерения.")
    return ADDING_INGREDIENTS

async def add_recipe(update, context):
    context.user_data['ingredients'] = update.message.text
    await update.message.reply_text("Теперь введите рецепт.")
    return ADDING_RECIPE

async def save_details(update, context):
    recipe = update.message.text
    dish_name = context.user_data.get('dish_name')
    ingredients = context.user_data.get('ingredients')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO dishes (name, ingredients, recipe) VALUES (?, ?, ?)", (dish_name, ingredients, recipe))
    conn.commit()
    await update.message.reply_text(f'Детали для блюда "{dish_name}" сохранены.')
    return ConversationHandler.END

async def edit_dish(update, context):
    await update.message.reply_text("Напишите старое название блюда.")
    return EDITING_DISH

async def save_edited_dish(update, context):
    old_name = context.user_data.get("old_name", "")
    new_name = update.message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE dishes SET name = ? WHERE name = ?", (new_name, old_name))
    conn.commit()
    if cursor.rowcount == 0:
        await update.message.reply_text(f'Блюдо "{old_name}" не найдено в меню.')
    else:
        await update.message.reply_text(f'Блюдо "{old_name}" было переименовано в "{new_name}".')
    return ConversationHandler.END

async def delete_dish(update, context):
    await update.message.reply_text("Напишите название блюда, которое вы хотите удалить.")
    return DELETING_DISH

async def confirm_delete_dish(update, context):
    dish_name = update.message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dishes WHERE name = ?", (dish_name,))
    conn.commit()
    if cursor.rowcount == 0:
        await update.message.reply_text(f'Блюдо "{dish_name}" не найдено в меню.')
    else:
        await update.message.reply_text(f'Блюдо "{dish_name}" удалено из меню.')
    return ConversationHandler.END

add_details_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(Добавить детали)$"), add_ingredients)],
    states={
        ADDING_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_ingredients)],
        ADDING_INGREDIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_recipe)],
        ADDING_RECIPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_details)],
    },
    fallbacks=[CommandHandler("start", start)]
)

dish_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(Добавить блюдо)$"), add_dish)],
    states={
        ADDING_DISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_dish)],
    },
    fallbacks=[CommandHandler("start", start)]
)

edit_dish_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(Изменить блюдо)$"), edit_dish)],
    states={
        EDITING_DISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_dish)],
    },
    fallbacks=[CommandHandler("start", start)]
)

delete_dish_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(Удалить блюдо)$"), delete_dish)],
    states={
        DELETING_DISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_dish)],
    },
    fallbacks=[CommandHandler("start", start)]
)

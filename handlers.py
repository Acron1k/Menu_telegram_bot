from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta
from typing import Dict, List

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database
from states import (
    add_details_handler,
    add_dish_handler,
    delete_dish_handler,
    find_by_ingredients_handler,
    import_handler,
    plan_handler,
    scale_dish_handler,
    send_reminder_job,
    edit_dish_handler,
)
from utils import (
    build_main_keyboard_layout,
    calculate_date_range,
    format_dish_card,
    format_plan_entries,
    format_recent_actions,
    format_shareable_recipe,
    format_shopping_items,
    format_statistics,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    summary = await database.get_dashboard_summary(user_id)
    recent = await database.get_recent_actions(user_id)
    keyboard = ReplyKeyboardMarkup(
        build_main_keyboard_layout(summary),
        resize_keyboard=True,
    )
    message_lines = [
        "Привет! Я помогу вести меню, планировать питание и составлять списки покупок.",
        f"Всего блюд: {summary.get('total_dishes', 0)}",
        f"Избранных блюд: {summary.get('favorite_count', 0)}",
        f"Запланированных приёмов пищи: {summary.get('upcoming', 0)}",
    ]
    recent_text = format_recent_actions(recent)
    if recent_text:
        message_lines.append("\n" + recent_text)
    await update.message.reply_text("\n".join(message_lines), reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Доступные команды:\n"
        "/start — показать главное меню\n"
        "/add_dish — добавить новое блюдо\n"
        "/menu — список всех блюд\n"
        "/view <название> — показать карточку блюда\n"
        "/plan — добавить блюдо в план питания\n"
        "/shopping — сформировать список покупок\n"
        "/favorites — показать избранные блюда\n"
        "/stats — статистика использования\n"
        "/find — поиск блюд по ингредиентам\n"
        "/import — импорт блюд из CSV\n"
        "/export — экспорт всех данных\n"
        "/cancel — отменить текущий диалог"
    )
    await update.message.reply_text(help_text)


async def list_dishes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dishes = await database.list_dishes()
    message = update.effective_message
    if not dishes:
        await message.reply_text("Меню пустое. Добавьте блюдо с помощью команды 'Добавить блюдо'.")
        return
    dish_names = "\n".join(f"• {dish['name']}" for dish in dishes)
    buttons: List[List[InlineKeyboardButton]] = []
    for dish in dishes[:30]:  # ограничимся 30 кнопками для компактности
        buttons.append([InlineKeyboardButton(dish["name"], callback_data=f"view_dish:{dish['id']}")])
    keyboard = InlineKeyboardMarkup(buttons) if buttons else None
    await message.reply_text("Текущие блюда:\n" + dish_names, reply_markup=keyboard)


async def view_dish_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Укажите название блюда после команды, например: /view Борщ")
        return
    name = " ".join(context.args)
    dish = await database.get_dish_by_name(name)
    if not dish:
        suggestions = await database.search_dish_names(name, limit=3)
        if suggestions:
            names = ", ".join(item["name"] for item in suggestions)
            await update.message.reply_text(f"Блюдо не найдено. Возможно, вы искали: {names}")
        else:
            await update.message.reply_text("Блюдо не найдено. Добавьте его в меню.")
        return
    await update.message.reply_text(format_dish_card(dish))


async def view_dish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    dish_id = int(query.data.split(":", 1)[1])
    dish = await database.get_dish_by_id(dish_id)
    if not dish:
        await query.edit_message_text("Блюдо не найдено или было удалено.")
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "★ Убрать из избранного" if dish.get("is_favorite") else "⭐️ В избранное",
                    callback_data=f"toggle_favorite:{dish_id}",
                ),
                InlineKeyboardButton("🗓 В план", callback_data=f"plan_from_dish:{dish_id}"),
            ],
            [
                InlineKeyboardButton("📏 Масштабировать", callback_data=f"scale_dish:{dish_id}"),
                InlineKeyboardButton("📄 Экспорт блюда", callback_data=f"export_dish:{dish_id}"),
            ],
            [
                InlineKeyboardButton("📤 Поделиться", callback_data=f"share_dish:{dish_id}"),
            ],
        ]
    )
    await query.message.reply_text(format_dish_card(dish), reply_markup=keyboard)


async def toggle_favorite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    dish_id = int(query.data.split(":", 1)[1])
    dish = await database.get_dish_by_id(dish_id)
    if not dish:
        await query.message.reply_text("Блюдо не найдено.")
        return
    new_value = not bool(dish.get("is_favorite"))
    await database.toggle_favorite(dish_id, new_value)
    await database.log_action(str(update.effective_user.id), dish_id, "favorites_updated", {"is_favorite": new_value})
    text = "Добавлено в избранное" if new_value else "Удалено из избранного"
    await query.message.reply_text(text)


async def share_dish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    dish_id = int(query.data.split(":", 1)[1])
    dish = await database.get_dish_by_id(dish_id)
    if not dish:
        await query.message.reply_text("Блюдо не найдено для отправки.")
        return
    await query.message.reply_text("Скопируйте текст и поделитесь им:\n\n" + format_shareable_recipe(dish))


async def export_dish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    dish_id = int(query.data.split(":", 1)[1])
    dish = await database.get_dish_by_id(dish_id)
    if not dish:
        await query.message.reply_text("Блюдо не найдено для экспорта.")
        return
    buffer = io.BytesIO()
    buffer.write(format_shareable_recipe(dish).encode("utf-8"))
    buffer.seek(0)
    filename = f"{dish['name']}.txt".replace("/", "-")
    await query.message.reply_document(InputFile(buffer, filename=filename), caption="Карточка блюда готова к скачиванию.")


async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    favorites = await database.list_favorites()
    message = update.effective_message
    if not favorites:
        await message.reply_text("Избранных блюд пока нет. Добавьте их из карточки блюда кнопкой '⭐️'.")
        return
    lines = ["Избранные блюда:"]
    for dish in favorites:
        lines.append(f"• {dish['name']}")
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(dish["name"], callback_data=f"view_dish:{dish['id']}")] for dish in favorites[:30]]
    )
    await message.reply_text("\n".join(lines), reply_markup=keyboard)


async def plan_overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    start_date, end_date = calculate_date_range(7)
    plans = await database.get_meal_plans_in_range(user_id, start_date, end_date)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Добавить блюдо", callback_data="plan_create")]])
    await update.effective_message.reply_text(
        format_plan_entries(plans) + f"\n\nПоказываются планы на период {start_date} — {end_date}.",
        reply_markup=keyboard,
    )


async def shopping_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    start_date, end_date = calculate_date_range(7)
    result = await database.get_shopping_list(user_id, start_date, end_date)
    await update.effective_message.reply_text(
        format_shopping_items(result.get("items", []))
        + f"\n\nДиапазон: {start_date} — {end_date}",
    )
    await database.log_action(user_id, None, "shopping_viewed", {"items": len(result.get("items", []))})


async def statistics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    stats = await database.get_user_statistics(user_id)
    recent = await database.get_recent_actions(user_id)
    await update.effective_message.reply_text(format_statistics(stats, recent))
    await database.log_action(user_id, None, "statistics_viewed", None)


async def export_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    data = await database.export_data(user_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in data.items():
            archive.writestr(filename, content)
    buffer.seek(0)
    await update.effective_message.reply_document(
        InputFile(buffer, filename="menu_export.zip"),
        caption="Экспорт завершён.",
    )


async def schedule_existing_reminders(application: Application) -> None:
    reminders = await database.get_pending_reminders()
    now = datetime.now()
    for reminder in reminders:
        try:
            remind_at = datetime.fromisoformat(reminder["remind_at"])
        except ValueError:
            continue
        delta = remind_at - now
        when = max(delta, timedelta(seconds=1))
        job = application.job_queue.run_once(
            send_reminder_job,
            when=when,
            name=reminder.get("job_name"),
            data={
                "chat_id": reminder["chat_id"],
                "message": reminder["message"],
                "reminder_time": reminder["remind_at"],
                "reminder_id": reminder["id"],
                "plan_id": reminder.get("plan_id"),
                "dish_id": reminder.get("dish_id"),
                "user_id": reminder.get("user_id"),
            },
        )
        if job and job.data is not None:
            job.data["reminder_id"] = reminder["id"]


async def post_init(application: Application) -> None:
    await schedule_existing_reminders(application)


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", list_dishes))
    app.add_handler(CommandHandler("view", view_dish_command))
    app.add_handler(CommandHandler("favorites", show_favorites))
    app.add_handler(CommandHandler("shopping", shopping_list_handler))
    app.add_handler(CommandHandler("stats", statistics_handler))
    app.add_handler(CommandHandler("export", export_all_handler))

    app.add_handler(add_dish_handler)
    app.add_handler(add_details_handler)
    app.add_handler(edit_dish_handler)
    app.add_handler(delete_dish_handler)
    app.add_handler(plan_handler)
    app.add_handler(import_handler)
    app.add_handler(find_by_ingredients_handler)
    app.add_handler(scale_dish_handler)

    app.add_handler(MessageHandler(filters.Regex("^(Меню)$"), list_dishes))
    app.add_handler(MessageHandler(filters.Regex("^(Избранное)$"), show_favorites))
    app.add_handler(MessageHandler(filters.Regex("^(Список покупок)$"), shopping_list_handler))
    app.add_handler(MessageHandler(filters.Regex("^(Статистика)$"), statistics_handler))
    app.add_handler(MessageHandler(filters.Regex("^(Экспорт)$"), export_all_handler))
    app.add_handler(MessageHandler(filters.Regex("^(План питания)$"), plan_overview))
    app.add_handler(MessageHandler(filters.Regex("^(Помощь)$"), help_command))

    app.add_handler(CallbackQueryHandler(view_dish_callback, pattern="^view_dish:"))
    app.add_handler(CallbackQueryHandler(toggle_favorite_callback, pattern="^toggle_favorite:"))
    app.add_handler(CallbackQueryHandler(export_dish_callback, pattern="^export_dish:"))
    app.add_handler(CallbackQueryHandler(share_dish_callback, pattern="^share_dish:"))

    app.post_init = post_init


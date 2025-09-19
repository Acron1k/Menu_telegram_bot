from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database
from utils import (
    DIFFICULTY_LEVELS,
    FINISH_INGREDIENT_KEYWORDS,
    MAIN_CATEGORIES,
    MEAL_TYPES,
    NO_ANSWERS,
    SKIP_KEYWORD,
    YES_ANSWERS,
    format_dish_card,
    format_scaled_ingredients,
    format_search_results,
    parse_date_input,
    parse_float,
    parse_ingredient_input,
    parse_int,
    parse_tags,
    parse_time_input,
)

(
    ADD_NAME,
    ADD_CATEGORY,
    ADD_CUISINE,
    ADD_SERVINGS,
    ADD_PREP_TIME,
    ADD_COOK_TIME,
    ADD_DIFFICULTY,
    ADD_DESCRIPTION,
    ADD_INGREDIENTS,
    ADD_INSTRUCTIONS,
    ADD_TAGS,
    DETAILS_SELECT,
    DETAILS_INGREDIENTS,
    DETAILS_INSTRUCTIONS,
    DETAILS_TAGS,
    EDIT_SELECT,
    EDIT_FIELD,
    EDIT_VALUE,
    DELETE_SELECT,
    DELETE_CONFIRM,
    PLAN_CHOOSE_DISH,
    PLAN_SET_DATE,
    PLAN_SET_MEAL,
    PLAN_SET_SERVINGS,
    PLAN_SET_NOTES,
    PLAN_CONFIRM_REMINDER,
    PLAN_SET_REMINDER_TIME,
    IMPORT_WAITING_FILE,
    FIND_BY_INGREDIENTS_INPUT,
    SCALE_WAITING,
) = range(30)

EDITABLE_FIELDS = {
    "Название": "name",
    "Категория": "category",
    "Кухня": "cuisine",
    "Порции": "servings",
    "Время подготовки (мин)": "prep_time",
    "Время готовки (мин)": "cook_time",
    "Сложность": "difficulty",
    "Описание": "description",
    "Источник": "source",
    "Заметки": "notes",
    "Теги": "tags",
    "Избранное": "is_favorite",
    "Готово": None,
}


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer("Действие отменено")
        await update.callback_query.edit_message_text("Действие отменено")
    elif update.message:
        await update.message.reply_text(
            "Действие отменено. Возвращаю основное меню.",
            reply_markup=ReplyKeyboardRemove(),
        )
    return ConversationHandler.END


def _categories_keyboard() -> ReplyKeyboardMarkup:
    rows = [[category] for category in MAIN_CATEGORIES]
    rows.append([SKIP_KEYWORD])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _difficulty_keyboard() -> ReplyKeyboardMarkup:
    rows = [[difficulty] for difficulty in DIFFICULTY_LEVELS]
    rows.append([SKIP_KEYWORD])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _meal_type_keyboard() -> ReplyKeyboardMarkup:
    rows = [[meal] for meal in MEAL_TYPES]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _yes_no_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["Да", "Нет"]], resize_keyboard=True, one_time_keyboard=True)


async def add_dish_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["add_dish"] = {"data": {}, "ingredients": [], "tags": []}
    await update.message.reply_text("Введите название блюда.", reply_markup=ReplyKeyboardRemove())
    return ADD_NAME


async def add_dish_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Название не может быть пустым. Попробуйте ещё раз.")
        return ADD_NAME
    existing = await database.get_dish_by_name(name)
    if existing:
        await update.message.reply_text(
            "Такое блюдо уже есть. Вы можете выбрать другое название или отредактировать существующее через "
            "'Изменить блюдо'.",
        )
        return ADD_NAME
    context.user_data.setdefault("add_dish", {})["data"]["name"] = name
    await update.message.reply_text(
        "Укажите категорию блюда или нажмите 'Пропустить'.",
        reply_markup=_categories_keyboard(),
    )
    return ADD_CATEGORY


async def add_dish_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != SKIP_KEYWORD:
        context.user_data["add_dish"]["data"]["category"] = text
    await update.message.reply_text(
        "Укажите кухню (например, Русская, Итальянская) или нажмите 'Пропустить'.",
        reply_markup=ReplyKeyboardMarkup([[SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
    )
    return ADD_CUISINE


async def add_dish_cuisine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != SKIP_KEYWORD:
        context.user_data["add_dish"]["data"]["cuisine"] = text
    await update.message.reply_text(
        "Сколько порций рассчитан рецепт? Введите число.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADD_SERVINGS


async def add_dish_servings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    servings = parse_float(update.message.text)
    if servings is None or servings <= 0:
        await update.message.reply_text("Введите положительное число порций.")
        return ADD_SERVINGS
    context.user_data["add_dish"]["data"]["servings"] = servings
    await update.message.reply_text("Сколько минут требуется на подготовку? Укажите число или 0, если не нужно.")
    return ADD_PREP_TIME


async def add_dish_prep_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = parse_int(update.message.text)
    if value is None or value < 0:
        await update.message.reply_text("Введите неотрицательное число минут подготовки.")
        return ADD_PREP_TIME
    context.user_data["add_dish"]["data"]["prep_time"] = value
    await update.message.reply_text("Сколько минут занимает готовка? Укажите число или 0, если неизвестно.")
    return ADD_COOK_TIME


async def add_dish_cook_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = parse_int(update.message.text)
    if value is None or value < 0:
        await update.message.reply_text("Введите неотрицательное число минут готовки.")
        return ADD_COOK_TIME
    context.user_data["add_dish"]["data"]["cook_time"] = value
    await update.message.reply_text(
        "Укажите сложность рецепта или нажмите 'Пропустить'.",
        reply_markup=_difficulty_keyboard(),
    )
    return ADD_DIFFICULTY


async def add_dish_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != SKIP_KEYWORD:
        context.user_data["add_dish"]["data"]["difficulty"] = text
    await update.message.reply_text(
        "Добавьте краткое описание блюда или нажмите 'Пропустить'.",
        reply_markup=ReplyKeyboardMarkup([[SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
    )
    return ADD_DESCRIPTION


async def add_dish_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != SKIP_KEYWORD:
        context.user_data["add_dish"]["data"]["description"] = text
    await update.message.reply_text(
        "Перечисляйте ингредиенты по одному в формате:\n"
        "Название; количество; единица; калории; белки; жиры; углеводы.\n"
        "Когда закончите, напишите 'Готово'.",
        reply_markup=ReplyKeyboardMarkup([["Готово"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return ADD_INGREDIENTS


async def add_dish_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    lower = text.lower()
    data = context.user_data["add_dish"]
    if lower in FINISH_INGREDIENT_KEYWORDS:
        if not data["ingredients"]:
            await update.message.reply_text(
                "Чтобы бот мог построить список покупок и подсчитать калории, добавьте хотя бы один ингредиент.",
            )
            return ADD_INGREDIENTS
        await update.message.reply_text("Теперь отправьте рецепт блюда." , reply_markup=ReplyKeyboardRemove())
        return ADD_INSTRUCTIONS
    try:
        ingredient = parse_ingredient_input(text)
    except ValueError as error:
        await update.message.reply_text(f"Не удалось распознать ингредиент: {error}")
        return ADD_INGREDIENTS
    data["ingredients"].append(ingredient)
    await update.message.reply_text("Добавлено. Введите следующий ингредиент или напишите 'Готово'.")
    return ADD_INGREDIENTS


async def add_dish_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    instructions = update.message.text.strip()
    if not instructions:
        await update.message.reply_text("Рецепт не может быть пустым. Опишите шаги приготовления.")
        return ADD_INSTRUCTIONS
    context.user_data["add_dish"]["data"]["instructions"] = instructions
    await update.message.reply_text(
        "Перечислите теги через запятую (например: веганское, быстро) или нажмите 'Пропустить'.",
        reply_markup=ReplyKeyboardMarkup([[SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
    )
    return ADD_TAGS


async def add_dish_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    tags: List[str] = []
    if text != SKIP_KEYWORD:
        tags = parse_tags(text)
    payload = context.user_data.pop("add_dish", {})
    data = payload.get("data", {})
    ingredients = payload.get("ingredients", [])
    user_id = str(update.effective_user.id)
    try:
        dish_id = await database.add_dish(data, ingredients, tags)
    except ValueError as error:
        await update.message.reply_text(str(error))
        return ConversationHandler.END
    dish = await database.get_dish_by_id(dish_id)
    if dish:
        await update.message.reply_text(
            "Блюдо успешно сохранено! Вот его карточка:\n" + format_dish_card(dish),
            reply_markup=ReplyKeyboardRemove(),
        )
    await database.log_action(user_id, dish_id, "dish_added", {"name": data.get("name")})
    return ConversationHandler.END


async def add_details_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["details"] = {"ingredients": []}
    await update.message.reply_text("Введите название блюда, которое хотите дополнить.")
    return DETAILS_SELECT


async def add_details_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    dish = await database.get_dish_by_name(name)
    if not dish:
        matches = await database.search_dish_names(name, limit=3)
        if matches:
            suggestions = ", ".join(match["name"] for match in matches)
            await update.message.reply_text(f"Не нашёл точного совпадения. Может быть, вы имели в виду: {suggestions}? Попробуйте ещё раз.")
        else:
            await update.message.reply_text("Блюдо не найдено. Убедитесь, что оно добавлено в меню.")
        return DETAILS_SELECT
    context.user_data["details"]["dish"] = dish
    context.user_data["details"]["ingredients"] = []
    await update.message.reply_text(
        "Текущая карточка блюда:\n" + format_dish_card(dish)
    )
    await update.message.reply_text(
        "Введите новые ингредиенты в формате 'Название; количество; единица; ...'.\n"
        "Отправьте несколько сообщений по одному ингредиенту. Напишите 'Готово', чтобы оставить текущий список.",
        reply_markup=ReplyKeyboardMarkup([["Готово"], [SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
    )
    return DETAILS_INGREDIENTS


async def add_details_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    lower = text.lower()
    details_data = context.user_data["details"]
    if lower in FINISH_INGREDIENT_KEYWORDS or text == SKIP_KEYWORD:
        if not details_data["ingredients"]:
            details_data["ingredients"] = None  # оставить без изменений
        await update.message.reply_text(
            "Опишите новый рецепт или нажмите 'Пропустить', чтобы оставить существующий.",
            reply_markup=ReplyKeyboardMarkup([[SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
        )
        return DETAILS_INSTRUCTIONS
    try:
        ingredient = parse_ingredient_input(text)
    except ValueError as error:
        await update.message.reply_text(f"Ошибка: {error}. Попробуйте ещё раз.")
        return DETAILS_INGREDIENTS
    details_data["ingredients"].append(ingredient)
    await update.message.reply_text("Добавлено. Введите следующий ингредиент или напишите 'Готово'.")
    return DETAILS_INGREDIENTS


async def add_details_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != SKIP_KEYWORD:
        context.user_data["details"]["instructions"] = text
    await update.message.reply_text(
        "Введите обновлённые теги или нажмите 'Пропустить'.",
        reply_markup=ReplyKeyboardMarkup([[SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
    )
    return DETAILS_TAGS


async def add_details_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    details_data = context.user_data.pop("details", {})
    dish = details_data.get("dish")
    if not dish:
        await update.message.reply_text("Что-то пошло не так — блюдо не найдено.")
        return ConversationHandler.END
    ingredients_input = details_data.get("ingredients")
    if ingredients_input is None:
        ingredients = dish.get("ingredients_list", [])
    else:
        ingredients = ingredients_input
    instructions = details_data.get("instructions") if "instructions" in details_data else None
    tags = dish.get("tags") if text == SKIP_KEYWORD else parse_tags(text)
    await database.replace_dish_details(dish["id"], ingredients, instructions=instructions, tags=tags)
    updated = await database.get_dish_by_id(dish["id"])
    await update.message.reply_text(
        "Блюдо обновлено:\n" + format_dish_card(updated),
        reply_markup=ReplyKeyboardRemove(),
    )
    await database.log_action(str(update.effective_user.id), dish["id"], "details_updated", {"name": dish.get("name")})
    return ConversationHandler.END


async def edit_dish_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите название блюда, которое хотите изменить.")
    context.user_data["edit_dish"] = {}
    return EDIT_SELECT


async def edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    dish = await database.get_dish_by_name(name)
    if not dish:
        matches = await database.search_dish_names(name, limit=3)
        if matches:
            options = ", ".join(match["name"] for match in matches)
            await update.message.reply_text(f"Не нашёл блюдо. Возможно, вы имели в виду: {options}")
        else:
            await update.message.reply_text("Такого блюда нет. Попробуйте снова.")
        return EDIT_SELECT
    context.user_data["edit_dish"]["dish"] = dish
    await update.message.reply_text(
        "Текущие данные:\n" + format_dish_card(dish)
    )
    keyboard_rows = [[label] for label in EDITABLE_FIELDS.keys()]
    await update.message.reply_text(
        "Что нужно изменить?",
        reply_markup=ReplyKeyboardMarkup(keyboard_rows, resize_keyboard=True, one_time_keyboard=True),
    )
    return EDIT_FIELD


async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text.strip()
    field = EDITABLE_FIELDS.get(choice)
    if field is None and choice != "Готово":
        await update.message.reply_text("Выберите опцию из списка.")
        return EDIT_FIELD
    if field is None:
        context.user_data.pop("edit_dish", None)
        await update.message.reply_text("Изменения сохранены.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    dish = context.user_data["edit_dish"].get("dish")
    if not dish:
        await update.message.reply_text("Не удалось найти блюдо. Начните сначала.")
        return ConversationHandler.END
    context.user_data["edit_dish"]["field"] = field
    if field == "is_favorite":
        new_value = not bool(dish.get("is_favorite"))
        await database.toggle_favorite(dish["id"], new_value)
        updated = await database.get_dish_by_id(dish["id"])
        context.user_data["edit_dish"]["dish"] = updated
        await update.message.reply_text(
            "Статус избранного обновлён. Хотите изменить что-то ещё?",
            reply_markup=ReplyKeyboardMarkup([[label] for label in EDITABLE_FIELDS.keys()], resize_keyboard=True, one_time_keyboard=True),
        )
        await database.log_action(str(update.effective_user.id), dish["id"], "favorites_updated", {"name": dish.get("name")})
        return EDIT_FIELD
    if field == "category":
        await update.message.reply_text(
            "Выберите новую категорию или нажмите 'Пропустить'.",
            reply_markup=_categories_keyboard(),
        )
        return EDIT_VALUE
    if field == "difficulty":
        await update.message.reply_text("Выберите сложность или нажмите 'Пропустить'.", reply_markup=_difficulty_keyboard())
        return EDIT_VALUE
    if field in {"prep_time", "cook_time"}:
        await update.message.reply_text("Введите количество минут (целое число).", reply_markup=ReplyKeyboardRemove())
        return EDIT_VALUE
    if field == "servings":
        await update.message.reply_text("Введите новое количество порций.", reply_markup=ReplyKeyboardRemove())
        return EDIT_VALUE
    if field == "tags":
        await update.message.reply_text(
            "Перечислите теги через запятую.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EDIT_VALUE
    await update.message.reply_text("Введите новое значение.", reply_markup=ReplyKeyboardRemove())
    return EDIT_VALUE


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    data = context.user_data.get("edit_dish")
    if not data:
        await update.message.reply_text("Контекст редактирования утерян. Начните сначала.")
        return ConversationHandler.END
    dish = data.get("dish")
    field = data.get("field")
    if not dish or not field:
        await update.message.reply_text("Не удалось обновить блюдо. Попробуйте снова.")
        return ConversationHandler.END
    updates: Dict[str, Any] = {}
    if field == "tags":
        tags = parse_tags(text)
        await database.set_dish_tags(dish["id"], tags)
    else:
        if field in {"prep_time", "cook_time"}:
            value = parse_int(text)
            if value is None or value < 0:
                await update.message.reply_text("Введите неотрицательное число минут.")
                return EDIT_VALUE
            updates[field] = value
        elif field == "servings":
            value = parse_float(text)
            if value is None or value <= 0:
                await update.message.reply_text("Введите положительное число порций.")
                return EDIT_VALUE
            updates[field] = value
        else:
            if text == SKIP_KEYWORD:
                updates[field] = None
            else:
                updates[field] = text
        if updates:
            await database.update_dish(dish["id"], updates)
    updated = await database.get_dish_by_id(dish["id"])
    context.user_data["edit_dish"]["dish"] = updated
    await update.message.reply_text(
        "Обновлённая карточка:\n" + format_dish_card(updated),
    )
    await database.log_action(str(update.effective_user.id), dish["id"], "dish_updated", {"field": field})
    keyboard_rows = [[label] for label in EDITABLE_FIELDS.keys()]
    await update.message.reply_text(
        "Изменить что-то ещё?",
        reply_markup=ReplyKeyboardMarkup(keyboard_rows, resize_keyboard=True, one_time_keyboard=True),
    )
    return EDIT_FIELD


async def delete_dish_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите название блюда, которое нужно удалить.")
    return DELETE_SELECT


async def delete_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    dish = await database.get_dish_by_name(name)
    if not dish:
        await update.message.reply_text("Блюдо не найдено. Проверьте название и попробуйте снова.")
        return DELETE_SELECT
    context.user_data["delete_dish"] = dish
    await update.message.reply_text(
        "Вы собираетесь удалить:\n" + format_dish_card(dish) + "\nВы уверены?",
        reply_markup=_yes_no_keyboard(),
    )
    return DELETE_CONFIRM


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip().lower()
    dish = context.user_data.pop("delete_dish", None)
    if answer in NO_ANSWERS or answer == "нет":
        await update.message.reply_text("Удаление отменено.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if not dish:
        await update.message.reply_text("Не удалось определить блюдо. Попробуйте снова.")
        return ConversationHandler.END
    await database.delete_dish(dish["id"])
    await update.message.reply_text(f"Блюдо '{dish.get('name')}' удалено.", reply_markup=ReplyKeyboardRemove())
    await database.log_action(str(update.effective_user.id), dish["id"], "dish_deleted", {"name": dish.get("name")})
    return ConversationHandler.END


async def plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["plan"] = {}
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "Введите название блюда, которое нужно добавить в план.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await update.message.reply_text("Введите название блюда, которое нужно добавить в план.")
    return PLAN_CHOOSE_DISH


async def plan_from_dish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    dish_id = int(query.data.split(":", 1)[1])
    dish = await database.get_dish_by_id(dish_id)
    if not dish:
        await query.edit_message_text("Блюдо не найдено. Попробуйте снова через меню.")
        return ConversationHandler.END
    context.user_data["plan"] = {"dish": dish}
    await query.message.reply_text(
        "Укажите дату (например, 2024-05-20, сегодня или завтра).",
        reply_markup=ReplyKeyboardRemove(),
    )
    return PLAN_SET_DATE


async def plan_choose_dish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    dish = await database.get_dish_by_name(name)
    if not dish:
        matches = await database.search_dish_names(name, limit=3)
        if matches:
            suggestions = ", ".join(match["name"] for match in matches)
            await update.message.reply_text(f"Не нашёл блюдо. Возможно, вы имели в виду: {suggestions}")
        else:
            await update.message.reply_text("Блюдо не найдено. Попробуйте снова.")
        return PLAN_CHOOSE_DISH
    context.user_data.setdefault("plan", {})["dish"] = dish
    await update.message.reply_text(
        "Укажите дату приготовления (например, 2024-05-20, сегодня или завтра).",
    )
    return PLAN_SET_DATE


async def plan_set_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    plan_date = parse_date_input(update.message.text)
    if not plan_date:
        await update.message.reply_text("Не удалось распознать дату. Используйте формат ГГГГ-ММ-ДД или слова 'сегодня', 'завтра'.")
        return PLAN_SET_DATE
    if plan_date < date.today():
        await update.message.reply_text("Дата не может быть в прошлом.")
        return PLAN_SET_DATE
    context.user_data["plan"]["date"] = plan_date.isoformat()
    await update.message.reply_text("На какой приём пищи поставить блюдо?", reply_markup=_meal_type_keyboard())
    return PLAN_SET_MEAL


async def plan_set_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    meal_type = update.message.text.strip()
    if meal_type not in MEAL_TYPES:
        await update.message.reply_text("Выберите приём пищи из списка.")
        return PLAN_SET_MEAL
    context.user_data["plan"]["meal_type"] = meal_type
    dish = context.user_data["plan"].get("dish")
    suggestion = dish.get("servings") if dish else 1
    await update.message.reply_text(
        f"Сколько порций приготовить? (по умолчанию {suggestion})",
        reply_markup=ReplyKeyboardMarkup([[SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PLAN_SET_SERVINGS


async def plan_set_servings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    dish = context.user_data["plan"].get("dish")
    if text == SKIP_KEYWORD:
        servings = dish.get("servings", 1) if dish else 1
    else:
        servings = parse_float(text)
        if servings is None or servings <= 0:
            await update.message.reply_text("Введите положительное число или нажмите 'Пропустить'.")
            return PLAN_SET_SERVINGS
    context.user_data["plan"]["servings"] = servings
    await update.message.reply_text(
        "Добавьте заметку (например, 'приготовить заранее') или нажмите 'Пропустить'.",
        reply_markup=ReplyKeyboardMarkup([[SKIP_KEYWORD]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PLAN_SET_NOTES


async def plan_set_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != SKIP_KEYWORD:
        context.user_data["plan"]["notes"] = text
    plan_data = context.user_data.get("plan", {})
    dish = plan_data.get("dish")
    if not dish:
        await update.message.reply_text("Не удалось определить блюдо. Начните сначала.")
        return ConversationHandler.END
    plan_id = await database.create_meal_plan(
        user_id=str(update.effective_user.id),
        chat_id=update.effective_chat.id,
        dish_id=dish["id"],
        plan_date=plan_data["date"],
        meal_type=plan_data["meal_type"],
        servings=plan_data.get("servings", dish.get("servings", 1)),
        notes=plan_data.get("notes"),
    )
    context.user_data["plan"]["plan_id"] = plan_id
    await update.message.reply_text(
        "Блюдо добавлено в план! Желаете установить напоминание?",
        reply_markup=_yes_no_keyboard(),
    )
    await database.log_action(str(update.effective_user.id), dish["id"], "plan_created", {"plan_id": plan_id})
    return PLAN_CONFIRM_REMINDER


async def plan_confirm_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip().lower()
    if answer in NO_ANSWERS or answer == "нет":
        context.user_data.pop("plan", None)
        await update.message.reply_text("Готово! План обновлён.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if answer not in YES_ANSWERS and answer != "да":
        await update.message.reply_text("Ответьте 'Да' или 'Нет'.")
        return PLAN_CONFIRM_REMINDER
    await update.message.reply_text(
        "Укажите время напоминания в формате ЧЧ:ММ.", reply_markup=ReplyKeyboardRemove()
    )
    return PLAN_SET_REMINDER_TIME


async def plan_set_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    plan_data = context.user_data.get("plan")
    if not plan_data:
        await update.message.reply_text("Контекст напоминания утерян. Попробуйте снова.")
        return ConversationHandler.END
    reminder_time = parse_time_input(update.message.text)
    if not reminder_time:
        await update.message.reply_text("Не удалось распознать время. Используйте формат ЧЧ:ММ.")
        return PLAN_SET_REMINDER_TIME
    plan_date = datetime.strptime(plan_data["date"], "%Y-%m-%d").date()
    remind_dt = datetime.combine(plan_date, reminder_time)
    now = datetime.now()
    if remind_dt <= now:
        await update.message.reply_text("Время уже прошло. Укажите более позднее время.")
        return PLAN_SET_REMINDER_TIME
    dish = plan_data.get("dish")
    plan_id = plan_data.get("plan_id")
    job_name = f"reminder_{plan_id}_{int(remind_dt.timestamp())}"
    message = (
        f"⏰ Напоминание: {dish.get('name')} — {plan_data.get('meal_type')} {plan_date.isoformat()}"
    )
    job = context.application.job_queue.run_once(
        callback=send_reminder_job,
        when=(remind_dt - now),
        name=job_name,
        data={
            "chat_id": update.effective_chat.id,
            "message": message,
            "reminder_time": remind_dt.isoformat(),
            "reminder_id": None,
            "plan_id": plan_id,
            "dish_id": dish.get("id"),
            "user_id": str(update.effective_user.id),
        },
    )
    reminder_id = await database.add_reminder(
        user_id=str(update.effective_user.id),
        chat_id=update.effective_chat.id,
        remind_at=remind_dt.isoformat(),
        message=message,
        job_name=job_name,
        plan_id=plan_id,
        dish_id=dish.get("id"),
    )
    if job and job.data is not None:
        job.data["reminder_id"] = reminder_id
    await database.log_action(str(update.effective_user.id), dish.get("id"), "reminder_scheduled", {"reminder_id": reminder_id})
    await update.message.reply_text("Готово! Напоминание сохранено.")
    context.user_data.pop("plan", None)
    return ConversationHandler.END


async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job_data = context.job.data or {}
    message = job_data.get("message", "Напоминание")
    chat_id = job_data.get("chat_id")
    reminder_id = job_data.get("reminder_id")
    if chat_id is None:
        return
    await context.bot.send_message(chat_id=chat_id, text=message)
    if reminder_id:
        await database.remove_reminder(reminder_id)
    await database.log_action(job_data.get("user_id", "unknown"), job_data.get("dish_id"), "reminder_sent", {"message": message})


async def import_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Отправьте CSV-файл с блюдами. Формат колонок: "
        "name,category,cuisine,servings,prep_time,cook_time,difficulty,is_favorite,tags,ingredients,recipe,description,notes.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return IMPORT_WAITING_FILE


async def import_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document
    if not document:
        await update.message.reply_text("Отправьте файл в формате CSV.")
        return IMPORT_WAITING_FILE
    filename = (document.file_name or "").lower()
    if not filename.endswith(".csv"):
        await update.message.reply_text("Пожалуйста, отправьте файл с расширением .csv.")
        return IMPORT_WAITING_FILE
    file = await document.get_file()
    content = await file.download_as_bytearray()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    result = await database.import_dishes(reader)
    skipped = ", ".join(result["skipped"]) if result["skipped"] else "нет"
    await update.message.reply_text(
        f"Импорт завершён. Добавлено блюд: {result['added']}. Пропущены: {skipped}."
    )
    await database.log_action(str(update.effective_user.id), None, "imported", result)
    return ConversationHandler.END


async def find_by_ingredients_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите список доступных ингредиентов через запятую."
    )
    return FIND_BY_INGREDIENTS_INPUT


async def find_by_ingredients_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    ingredients = [item.strip() for item in text.replace("\n", ",").split(",") if item.strip()]
    results = await database.get_dish_suggestions_by_ingredients(ingredients)
    await update.message.reply_text(format_search_results(results), reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def scale_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    dish_id = int(query.data.split(":", 1)[1])
    dish = await database.get_dish_by_id(dish_id)
    if not dish:
        await query.edit_message_text("Не удалось найти блюдо для масштабирования.")
        return ConversationHandler.END
    context.user_data["scale"] = dish
    await query.message.reply_text(
        f"На сколько порций нужно приготовить '{dish.get('name')}'? (базово {dish.get('servings', 1)})",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SCALE_WAITING


async def scale_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    dish = context.user_data.pop("scale", None)
    if not dish:
        await update.message.reply_text("Не удалось определить блюдо.")
        return ConversationHandler.END
    servings = parse_float(update.message.text)
    if servings is None or servings <= 0:
        context.user_data["scale"] = dish
        await update.message.reply_text("Введите положительное число порций.")
        return SCALE_WAITING
    await update.message.reply_text(format_scaled_ingredients(dish, servings))
    return ConversationHandler.END


add_dish_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(Добавить блюдо)$"), add_dish_entry),
        CommandHandler("add_dish", add_dish_entry),
    ],
    states={
        ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_name)],
        ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_category)],
        ADD_CUISINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_cuisine)],
        ADD_SERVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_servings)],
        ADD_PREP_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_prep_time)],
        ADD_COOK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_cook_time)],
        ADD_DIFFICULTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_difficulty)],
        ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_description)],
        ADD_INGREDIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_ingredients)],
        ADD_INSTRUCTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_instructions)],
        ADD_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dish_tags)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

add_details_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(Добавить детали)$"), add_details_entry),
        CommandHandler("add_details", add_details_entry),
    ],
    states={
        DETAILS_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_details_select)],
        DETAILS_INGREDIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_details_ingredients)],
        DETAILS_INSTRUCTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_details_instructions)],
        DETAILS_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_details_tags)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

edit_dish_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(Изменить блюдо)$"), edit_dish_entry),
        CommandHandler("edit_dish", edit_dish_entry),
    ],
    states={
        EDIT_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_select)],
        EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field)],
        EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

delete_dish_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(Удалить блюдо)$"), delete_dish_entry),
        CommandHandler("delete_dish", delete_dish_entry),
    ],
    states={
        DELETE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_select)],
        DELETE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_confirm)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

plan_handler = ConversationHandler(
    entry_points=[
        CommandHandler("plan", plan_start),
        CallbackQueryHandler(plan_start, pattern="^plan_create$"),
        CallbackQueryHandler(plan_from_dish_callback, pattern="^plan_from_dish:"),
    ],
    states={
        PLAN_CHOOSE_DISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_choose_dish)],
        PLAN_SET_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_set_date)],
        PLAN_SET_MEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_set_meal)],
        PLAN_SET_SERVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_set_servings)],
        PLAN_SET_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_set_notes)],
        PLAN_CONFIRM_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_confirm_reminder)],
        PLAN_SET_REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_set_reminder_time)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

import_handler = ConversationHandler(
    entry_points=[
        CommandHandler("import", import_start),
        MessageHandler(filters.Regex("^(Импорт)$"), import_start),
    ],
    states={
        IMPORT_WAITING_FILE: [MessageHandler(filters.Document.ALL, import_receive_file)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

find_by_ingredients_handler = ConversationHandler(
    entry_points=[
        CommandHandler("find", find_by_ingredients_start),
        MessageHandler(filters.Regex("^(Поиск по ингредиентам)$"), find_by_ingredients_start),
    ],
    states={
        FIND_BY_INGREDIENTS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_by_ingredients_process)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

scale_dish_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(scale_start, pattern="^scale_dish:")],
    states={
        SCALE_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, scale_receive)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

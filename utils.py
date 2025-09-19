from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MAIN_CATEGORIES = [
    "Завтрак",
    "Обед",
    "Ужин",
    "Перекус",
    "Салат",
    "Десерт",
    "Напиток",
    "Суп",
]

MEAL_TYPES = ["Завтрак", "Обед", "Ужин", "Перекус"]
DIFFICULTY_LEVELS = ["Легко", "Средне", "Сложно"]
SKIP_KEYWORD = "Пропустить"
FINISH_INGREDIENT_KEYWORDS = {"готово", "далее", "хватит", "стоп", "все", "всё"}
YES_ANSWERS = {"да", "конечно", "ага", "yes", "y"}
NO_ANSWERS = {"нет", "no", "неа"}


def normalize_decimal(text: str) -> str:
    return text.replace(",", ".").replace(" ", "").strip()


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = normalize_decimal(str(value))
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    number = parse_float(value)
    if number is None:
        return None
    try:
        return int(round(number))
    except (TypeError, ValueError):
        return None


def parse_date_input(text: str) -> Optional[date]:
    normalized = text.strip().lower()
    today = date.today()
    if normalized in {"сегодня", "today"}:
        return today
    if normalized in {"завтра", "tomorrow"}:
        return today + timedelta(days=1)
    if normalized.startswith("через ") and normalized.endswith(" дней"):
        number_part = normalized.replace("через", "").replace("дней", "").strip()
        days = parse_int(number_part)
        if days is not None:
            return today + timedelta(days=days)
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    return None


def parse_time_input(text: str) -> Optional[time]:
    normalized = text.strip()
    for pattern in ("%H:%M", "%H.%M", "%H %M"):
        try:
            return datetime.strptime(normalized, pattern).time()
        except ValueError:
            continue
    return None


def parse_ingredient_input(text: str) -> Dict[str, Any]:
    parts = [part.strip() for part in text.split(";")]
    if not parts or not parts[0]:
        raise ValueError("Название ингредиента обязательно")
    ingredient: Dict[str, Any] = {"name": parts[0]}
    if len(parts) > 1 and parts[1]:
        ingredient["quantity"] = parse_float(parts[1])
    if len(parts) > 2 and parts[2]:
        ingredient["unit"] = parts[2]
    macros_keys = ["calories", "protein", "fat", "carbs"]
    for index, key in enumerate(macros_keys, start=3):
        if len(parts) > index and parts[index]:
            ingredient[key] = parse_float(parts[index])
    return ingredient


def compute_macros(ingredients: Sequence[Dict[str, Any]], ratio: float = 1.0) -> Dict[str, float]:
    totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for ingredient in ingredients:
        for key in totals.keys():
            value = ingredient.get(key)
            if value is not None:
                totals[key] += float(value) * ratio
    return totals


def format_macros(macros: Dict[str, float]) -> str:
    meaningful = {key: value for key, value in macros.items() if value}
    if not meaningful:
        return ""
    parts = []
    if macros.get("calories"):
        parts.append(f"Ккал: {round(macros['calories'], 1)}")
    if macros.get("protein"):
        parts.append(f"Б: {round(macros['protein'], 1)} г")
    if macros.get("fat"):
        parts.append(f"Ж: {round(macros['fat'], 1)} г")
    if macros.get("carbs"):
        parts.append(f"У: {round(macros['carbs'], 1)} г")
    return ", ".join(parts)


def humanize_minutes(value: Optional[int]) -> Optional[str]:
    if not value:
        return None
    minutes = int(value)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    return " ".join(parts) if parts else None


def format_duration(prep: Optional[int], cook: Optional[int]) -> Optional[str]:
    prep_text = humanize_minutes(prep)
    cook_text = humanize_minutes(cook)
    if prep_text and cook_text:
        return f"Подготовка: {prep_text}, готовка: {cook_text}"
    return prep_text or cook_text


def format_ingredients_list(ingredients: Sequence[Dict[str, Any]]) -> str:
    lines = []
    for ingredient in ingredients:
        name = ingredient.get("name")
        if not name:
            continue
        quantity = ingredient.get("quantity")
        unit = ingredient.get("unit") or ""
        amount = ""
        if quantity is not None:
            number = round(float(quantity), 2)
            number = int(number) if number.is_integer() else number
            amount = f" — {number} {unit}".strip()
        elif unit:
            amount = f" — {unit}"
        macros = format_macros({
            key: ingredient.get(key)
            for key in ("calories", "protein", "fat", "carbs")
            if ingredient.get(key) is not None
        })
        extra = f" ({macros})" if macros else ""
        lines.append(f"• {name}{amount}{extra}")
    return "\n".join(lines)


def format_dish_card(dish: Dict[str, Any]) -> str:
    parts = [f"🍽 {dish.get('name', 'Без названия')}"]
    meta_lines = []
    if dish.get("category"):
        meta_lines.append(f"Категория: {dish['category']}")
    if dish.get("cuisine"):
        meta_lines.append(f"Кухня: {dish['cuisine']}")
    if dish.get("servings"):
        meta_lines.append(f"Порций: {dish['servings']}")
    duration = format_duration(dish.get("prep_time"), dish.get("cook_time"))
    if duration:
        meta_lines.append(duration)
    if dish.get("difficulty"):
        meta_lines.append(f"Сложность: {dish['difficulty']}")
    if meta_lines:
        parts.append("\n".join(meta_lines))
    tags = dish.get("tags") or []
    if tags:
        parts.append("Теги: " + ", ".join(sorted(tags)))
    if dish.get("description"):
        parts.append(dish["description"])
    ingredients_text = format_ingredients_list(dish.get("ingredients_list", []))
    if ingredients_text:
        parts.append("Ингредиенты:\n" + ingredients_text)
        macros = compute_macros(dish.get("ingredients_list", []))
        macros_line = format_macros(macros)
        if macros_line:
            parts.append(f"Пищевая ценность на {dish.get('servings', 1)} порц.: {macros_line}")
    instructions = dish.get("instructions") or dish.get("recipe")
    if instructions:
        parts.append("Рецепт:\n" + instructions)
    if dish.get("notes"):
        parts.append("Заметки:\n" + dish["notes"])
    return "\n\n".join(parts)


def parse_tags(text: str) -> List[str]:
    separators = {",", "\n", "#"}
    for separator in separators:
        text = text.replace(separator, ",")
    return [tag.strip() for tag in text.split(",") if tag.strip()]


def build_main_keyboard_layout(summary: Dict[str, Any]) -> List[List[str]]:
    total = summary.get("total_dishes", 0)
    if not total:
        return [["Добавить блюдо", "Импорт"], ["Помощь"]]
    layout = [
        ["Добавить блюдо", "Меню"],
        ["Добавить детали", "Изменить блюдо"],
        ["Удалить блюдо", "Поиск по ингредиентам"],
        ["План питания", "Список покупок"],
        ["Избранное", "Статистика"],
        ["Импорт", "Экспорт"],
        ["Помощь"],
    ]
    return layout


def group_plans_by_date(plans: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for plan in plans:
        grouped.setdefault(plan.get("plan_date"), []).append(plan)
    for items in grouped.values():
        items.sort(key=lambda item: MEAL_TYPES.index(item.get("meal_type")) if item.get("meal_type") in MEAL_TYPES else 99)
    return dict(sorted(grouped.items()))


def format_plan_entries(plans: Sequence[Dict[str, Any]]) -> str:
    if not plans:
        return "План питания пока пуст. Используйте /plan, чтобы добавить блюда."
    grouped = group_plans_by_date(plans)
    lines: List[str] = []
    for plan_date, entries in grouped.items():
        lines.append(f"📅 {plan_date}")
        for entry in entries:
            servings = entry.get("servings")
            servings_text = f" × {servings}" if servings else ""
            note = f" — {entry['notes']}" if entry.get("notes") else ""
            lines.append(f"  • {entry.get('meal_type', '')}: {entry.get('name', entry.get('dish_name', ''))}{servings_text}{note}")
    return "\n".join(lines)


def format_shopping_items(items: Sequence[Dict[str, Any]]) -> str:
    if not items:
        return "Список покупок пуст — запланируйте блюда, чтобы сформировать покупки."
    lines = ["🛒 Список покупок:"]
    for item in items:
        name = item.get("name", "")
        quantity = item.get("quantity")
        unit = item.get("unit") or ""
        amount = ""
        if quantity is not None:
            number = round(float(quantity), 2)
            number = int(number) if number.is_integer() else number
            amount = f" — {number} {unit}".strip()
        elif unit:
            amount = f" — {unit}"
        macros = format_macros({
            key: item.get(key)
            for key in ("calories", "protein", "fat", "carbs")
            if item.get(key)
        })
        extra = f" ({macros})" if macros else ""
        lines.append(f"• {name}{amount}{extra}")
    return "\n".join(lines)


def format_recent_actions(actions: Sequence[Dict[str, Any]]) -> str:
    if not actions:
        return ""
    mapping = {
        "dish_added": "добавлено новое блюдо",
        "dish_updated": "обновлены данные блюда",
        "dish_deleted": "блюдо удалено",
        "details_updated": "обновлены ингредиенты",
        "plan_created": "добавлено в план",
        "plan_deleted": "удалено из плана",
        "favorites_updated": "изменён список избранного",
        "shopping_viewed": "просмотрен список покупок",
        "statistics_viewed": "просмотрена статистика",
        "reminder_scheduled": "создано напоминание",
        "reminder_sent": "отправлено напоминание",
        "imported": "импортированы блюда",
    }
    lines = ["Недавние действия:"]
    for action in actions:
        description = mapping.get(action.get("action"), action.get("action"))
        timestamp = action.get("created_at", "")
        lines.append(f"• {timestamp}: {description}")
    return "\n".join(lines)


def format_statistics(stats: Dict[str, Any], actions: Sequence[Dict[str, Any]]) -> str:
    lines = ["📊 Статистика использования"]
    lines.append(f"Всего блюд в базе: {stats.get('total_dishes', 0)}")
    lines.append(f"Избранных блюд: {stats.get('favorite_dishes', 0)}")
    if stats.get("top_categories"):
        top_categories = ", ".join(
            f"{row['category']} ({row['count']})" for row in stats["top_categories"]
        )
        lines.append("Популярные категории: " + top_categories)
    if stats.get("top_planned"):
        top_planned = ", ".join(
            f"{row['name']} ({row['count']})" for row in stats["top_planned"]
        )
        lines.append("Чаще всего в плане: " + top_planned)
    if stats.get("activity"):
        lines.append(
            "Активность: "
            + ", ".join(f"{key} — {value}" for key, value in stats["activity"].items())
        )
    recent = format_recent_actions(actions)
    if recent:
        lines.append("\n" + recent)
    return "\n".join(lines)


def scale_ingredients(
    ingredients: Sequence[Dict[str, Any]],
    base_servings: float,
    new_servings: float,
) -> List[Dict[str, Any]]:
    if base_servings <= 0:
        ratio = 1.0
    else:
        ratio = new_servings / base_servings
    scaled: List[Dict[str, Any]] = []
    for ingredient in ingredients:
        scaled_item = dict(ingredient)
        if ingredient.get("quantity") is not None:
            scaled_item["quantity"] = (ingredient["quantity"] or 0) * ratio
        for key in ("calories", "protein", "fat", "carbs"):
            if ingredient.get(key) is not None:
                scaled_item[key] = (ingredient[key] or 0) * ratio
        scaled.append(scaled_item)
    return scaled


def format_scaled_ingredients(dish: Dict[str, Any], new_servings: float) -> str:
    base_servings = float(dish.get("servings") or 1)
    scaled = scale_ingredients(dish.get("ingredients_list", []), base_servings, new_servings)
    macros = compute_macros(scaled)
    lines = [
        f"Масштабирование рецепта '{dish.get('name')}'",
        f"Базовое количество порций: {base_servings}",
        f"Нужно приготовить: {new_servings}",
        "\nИнгредиенты:",
        format_ingredients_list(scaled),
    ]
    macros_line = format_macros(macros)
    if macros_line:
        lines.append(f"\nПищевая ценность для {new_servings} порц.: {macros_line}")
    return "\n".join(lines)


def format_shareable_recipe(dish: Dict[str, Any]) -> str:
    lines = [f"{dish.get('name', 'Рецепт')}" ]
    ingredients = format_ingredients_list(dish.get("ingredients_list", []))
    if ingredients:
        lines.append("Ингредиенты:\n" + ingredients)
    instructions = dish.get("instructions") or dish.get("recipe")
    if instructions:
        lines.append("\nРецепт:\n" + instructions)
    return "\n".join(lines)


def format_search_results(results: Sequence[Dict[str, Any]]) -> str:
    if not results:
        return "Не удалось найти блюда с такими ингредиентами. Попробуйте расширить список." \
            "\nСначала добавьте блюда через 'Добавить блюдо'."
    lines = ["Найденные блюда:"]
    for entry in results[:10]:
        matched = ", ".join(entry.get("matched", []))
        missing = ", ".join(entry.get("missing", []))
        coverage = round(entry.get("coverage", 0) * 100)
        line = f"• {entry.get('name')} — совпадений {coverage}%"
        if matched:
            line += f"\n  Есть: {matched}"
        if missing:
            line += f"\n  Не хватает: {missing}"
        lines.append(line)
    return "\n".join(lines)


def calculate_date_range(days: int = 7) -> Tuple[str, str]:
    today = date.today()
    end = today + timedelta(days=days - 1)
    return today.isoformat(), end.isoformat()

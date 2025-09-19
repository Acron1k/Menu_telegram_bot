import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DB_PATH = Path(__file__).with_name("menu.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def create_tables() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ingredients TEXT,
            recipe TEXT
        )
        """
    )

    _ensure_column(conn, "dishes", "description", "TEXT")
    _ensure_column(conn, "dishes", "instructions", "TEXT")
    _ensure_column(conn, "dishes", "category", "TEXT")
    _ensure_column(conn, "dishes", "cuisine", "TEXT")
    _ensure_column(conn, "dishes", "servings", "INTEGER DEFAULT 1")
    _ensure_column(conn, "dishes", "prep_time", "INTEGER DEFAULT 0")
    _ensure_column(conn, "dishes", "cook_time", "INTEGER DEFAULT 0")
    _ensure_column(conn, "dishes", "difficulty", "TEXT")
    _ensure_column(conn, "dishes", "is_favorite", "INTEGER DEFAULT 0")
    _ensure_column(conn, "dishes", "created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")
    _ensure_column(conn, "dishes", "updated_at", "TEXT DEFAULT CURRENT_TIMESTAMP")
    _ensure_column(conn, "dishes", "source", "TEXT")
    _ensure_column(conn, "dishes", "notes", "TEXT")

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dishes_name ON dishes(LOWER(name))
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dish_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            calories REAL,
            protein REAL,
            fat REAL,
            carbs REAL,
            UNIQUE(dish_id, name, unit),
            FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dish_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            UNIQUE(dish_id, tag),
            FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            dish_id INTEGER NOT NULL,
            plan_date TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            servings REAL DEFAULT 1,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            dish_id INTEGER,
            plan_id INTEGER,
            remind_at TEXT NOT NULL,
            message TEXT NOT NULL,
            job_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE SET NULL,
            FOREIGN KEY(plan_id) REFERENCES meal_plans(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS shopping_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            dish_id INTEGER,
            action TEXT NOT NULL,
            payload TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE SET NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_meal_plans_user_date ON meal_plans(user_id, plan_date)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reminders_user_time ON reminders(user_id, remind_at)
        """
    )

    cursor.execute(
        """
        UPDATE dishes SET instructions = recipe WHERE instructions IS NULL AND recipe IS NOT NULL
        """
    )

    conn.commit()
    conn.close()


async def _run_in_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


async def list_dishes(order_by: str = "name") -> List[Dict[str, Any]]:
    def _list() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM dishes ORDER BY {order_by} COLLATE NOCASE")
        rows = cursor.fetchall()
        conn.close()
        dishes: List[Dict[str, Any]] = []
        for row in rows:
            data = _row_to_dict(row)
            data["tags"] = [tag_row[0] for tag_row in cursor.execute("SELECT tag FROM dish_tags WHERE dish_id = ? ORDER BY tag", (row["id"],)).fetchall()]
            data["ingredients_list"] = [
                _row_to_dict(ing)
                for ing in cursor.execute(
                    "SELECT name, quantity, unit, calories, protein, fat, carbs FROM dish_ingredients WHERE dish_id = ? ORDER BY name",
                    (row["id"],),
                ).fetchall()
            ]
            dishes.append(data)
        return dishes

    return await _run_in_thread(_list)


async def get_dish_by_id(dish_id: int) -> Optional[Dict[str, Any]]:
    def _get() -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        data = _row_to_dict(row)
        data["tags"] = [tag_row[0] for tag_row in cursor.execute("SELECT tag FROM dish_tags WHERE dish_id = ? ORDER BY tag", (dish_id,)).fetchall()]
        data["ingredients_list"] = [
            _row_to_dict(ing)
            for ing in cursor.execute(
                "SELECT name, quantity, unit, calories, protein, fat, carbs FROM dish_ingredients WHERE dish_id = ? ORDER BY name",
                (dish_id,),
            ).fetchall()
        ]
        conn.close()
        return data

    return await _run_in_thread(_get)


async def get_dish_by_name(name: str) -> Optional[Dict[str, Any]]:
    def _get() -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dishes WHERE LOWER(name) = LOWER(?)", (name.strip(),))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return row["id"]

    dish_id = await _run_in_thread(_get)
    if dish_id is None:
        return None
    return await get_dish_by_id(dish_id)

async def search_dish_names(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    pattern = f"%{query.strip().lower()}%"

    def _search() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name FROM dishes WHERE LOWER(name) LIKE ? ORDER BY name LIMIT ?",
            (pattern, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    return await _run_in_thread(_search)


async def add_dish(
    dish_data: Dict[str, Any],
    ingredients: Sequence[Dict[str, Any]],
    tags: Sequence[str],
) -> int:
    name = dish_data.get("name", "").strip()
    if not name:
        raise ValueError("Название блюда не может быть пустым")

    def _insert() -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dishes WHERE LOWER(name) = LOWER(?)", (name,))
        if cursor.fetchone():
            conn.close()
            raise ValueError("Блюдо с таким названием уже существует")

        now = datetime.utcnow().isoformat()
        servings = dish_data.get("servings") or 1
        aggregated_ingredients = "; ".join(
            f"{ing.get('name')} {ing.get('quantity', '')}{ing.get('unit', '')}".strip()
            for ing in ingredients
            if ing.get("name")
        )
        instructions = dish_data.get("instructions") or dish_data.get("recipe") or ""
        cursor.execute(
            """
            INSERT INTO dishes (
                name, description, ingredients, recipe, instructions, category, cuisine,
                servings, prep_time, cook_time, difficulty, is_favorite, source, notes,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                dish_data.get("description"),
                aggregated_ingredients,
                instructions,
                instructions,
                dish_data.get("category"),
                dish_data.get("cuisine"),
                servings,
                dish_data.get("prep_time") or 0,
                dish_data.get("cook_time") or 0,
                dish_data.get("difficulty"),
                1 if dish_data.get("is_favorite") else 0,
                dish_data.get("source"),
                dish_data.get("notes"),
                now,
                now,
            ),
        )
        dish_id = cursor.lastrowid

        for ingredient in ingredients:
            if not ingredient.get("name"):
                continue
            cursor.execute(
                """
                INSERT INTO dish_ingredients (
                    dish_id, name, quantity, unit, calories, protein, fat, carbs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dish_id,
                    ingredient.get("name"),
                    ingredient.get("quantity"),
                    ingredient.get("unit"),
                    ingredient.get("calories"),
                    ingredient.get("protein"),
                    ingredient.get("fat"),
                    ingredient.get("carbs"),
                ),
            )

        for tag in tags:
            clean_tag = tag.strip().lower()
            if clean_tag:
                cursor.execute(
                    "INSERT OR IGNORE INTO dish_tags (dish_id, tag) VALUES (?, ?)",
                    (dish_id, clean_tag),
                )

        conn.commit()
        conn.close()
        return dish_id

    return await _run_in_thread(_insert)


async def update_dish(dish_id: int, updates: Dict[str, Any]) -> bool:
    if not updates:
        return False

    valid_fields = {
        "name",
        "description",
        "ingredients",
        "recipe",
        "instructions",
        "category",
        "cuisine",
        "servings",
        "prep_time",
        "cook_time",
        "difficulty",
        "is_favorite",
        "source",
        "notes",
    }

    sets: List[str] = []
    values: List[Any] = []
    for field, value in updates.items():
        if field not in valid_fields:
            continue
        sets.append(f"{field} = ?")
        values.append(value)

    if not sets:
        return False

    values.append(datetime.utcnow().isoformat())
    values.append(dish_id)

    def _update() -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE dishes SET {', '.join(sets)}, updated_at = ? WHERE id = ?",
            values,
        )
        affected = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return affected

    return await _run_in_thread(_update)


async def delete_dish(dish_id: int) -> bool:
    def _delete() -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dishes WHERE id = ?", (dish_id,))
        affected = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return affected

    return await _run_in_thread(_delete)


async def replace_dish_details(
    dish_id: int,
    ingredients: Sequence[Dict[str, Any]],
    instructions: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    description: Optional[str] = None,
) -> bool:
    def _replace() -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dishes WHERE id = ?", (dish_id,))
        if not cursor.fetchone():
            conn.close()
            return False

        cursor.execute("DELETE FROM dish_ingredients WHERE dish_id = ?", (dish_id,))
        aggregated_ingredients = []
        for ingredient in ingredients:
            if not ingredient.get("name"):
                continue
            cursor.execute(
                """
                INSERT INTO dish_ingredients (
                    dish_id, name, quantity, unit, calories, protein, fat, carbs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dish_id,
                    ingredient.get("name"),
                    ingredient.get("quantity"),
                    ingredient.get("unit"),
                    ingredient.get("calories"),
                    ingredient.get("protein"),
                    ingredient.get("fat"),
                    ingredient.get("carbs"),
                ),
            )
            aggregated_ingredients.append(
                f"{ingredient.get('name')} {ingredient.get('quantity', '')}{ingredient.get('unit', '')}".strip()
            )

        if tags is not None:
            cursor.execute("DELETE FROM dish_tags WHERE dish_id = ?", (dish_id,))
            for tag in tags:
                clean_tag = tag.strip().lower()
                if clean_tag:
                    cursor.execute(
                        "INSERT OR IGNORE INTO dish_tags (dish_id, tag) VALUES (?, ?)",
                        (dish_id, clean_tag),
                    )

        updates = {"ingredients": "; ".join(aggregated_ingredients)}
        if instructions is not None:
            updates["recipe"] = instructions
            updates["instructions"] = instructions
        if description is not None:
            updates["description"] = description

        set_parts = [f"{key} = ?" for key in updates]
        values = list(updates.values())
        values.append(datetime.utcnow().isoformat())
        values.append(dish_id)

        cursor.execute(
            f"UPDATE dishes SET {', '.join(set_parts)}, updated_at = ? WHERE id = ?",
            values,
        )
        conn.commit()
        conn.close()
        return True

    return await _run_in_thread(_replace)

async def toggle_favorite(dish_id: int, value: bool) -> bool:
    return await update_dish(dish_id, {"is_favorite": 1 if value else 0})


async def list_favorites() -> List[Dict[str, Any]]:
    def _list() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dishes WHERE is_favorite = 1 ORDER BY name")
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ids

    dish_ids = await _run_in_thread(_list)
    favorites: List[Dict[str, Any]] = []
    for dish_id in dish_ids:
        dish = await get_dish_by_id(dish_id)
        if dish:
            favorites.append(dish)
    return favorites


async def get_dashboard_summary(user_id: str) -> Dict[str, Any]:
    def _summary() -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dishes")
        total_dishes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dishes WHERE is_favorite = 1")
        favorite_count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM meal_plans WHERE user_id = ? AND plan_date >= date('now')",
            (user_id,),
        )
        upcoming = cursor.fetchone()[0]
        conn.close()
        return {
            "total_dishes": total_dishes,
            "favorite_count": favorite_count,
            "upcoming": upcoming,
        }

    return await _run_in_thread(_summary)


async def create_meal_plan(
    user_id: str,
    chat_id: int,
    dish_id: int,
    plan_date: str,
    meal_type: str,
    servings: float,
    notes: Optional[str] = None,
) -> int:
    def _create() -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO meal_plans (user_id, chat_id, dish_id, plan_date, meal_type, servings, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, dish_id, plan_date, meal_type, servings, notes),
        )
        plan_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return plan_id

    return await _run_in_thread(_create)


async def get_meal_plans_in_range(
    user_id: str,
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    def _fetch() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT mp.id, mp.plan_date, mp.meal_type, mp.servings, mp.notes,
                   d.id as dish_id, d.name, d.category, d.cuisine, d.servings as base_servings
            FROM meal_plans mp
            JOIN dishes d ON d.id = mp.dish_id
            WHERE mp.user_id = ? AND mp.plan_date BETWEEN ? AND ?
            ORDER BY mp.plan_date, mp.meal_type
            """,
            (user_id, start_date, end_date),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    return await _run_in_thread(_fetch)


async def delete_meal_plan(plan_id: int, user_id: str) -> bool:
    def _delete() -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM meal_plans WHERE id = ? AND user_id = ?",
            (plan_id, user_id),
        )
        affected = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return affected

    return await _run_in_thread(_delete)


async def log_action(user_id: str, dish_id: Optional[int], action: str, payload: Optional[Dict[str, Any]] = None) -> None:
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None

    def _log() -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_actions (user_id, dish_id, action, payload) VALUES (?, ?, ?, ?)",
            (user_id, dish_id, action, payload_json),
        )
        conn.commit()
        conn.close()

    await _run_in_thread(_log)


async def get_recent_actions(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    def _fetch() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action, payload, created_at FROM user_actions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        results: List[Dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload"]) if row["payload"] else None
            results.append({
                "action": row["action"],
                "payload": payload,
                "created_at": row["created_at"],
            })
        return results

    return await _run_in_thread(_fetch)

async def get_shopping_list(
    user_id: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    def _calculate() -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT mp.id as plan_id, mp.plan_date, mp.meal_type, mp.servings as planned_servings,
                   d.id as dish_id, d.name as dish_name, d.servings as base_servings,
                   di.name as ingredient_name, di.quantity, di.unit,
                   di.calories, di.protein, di.fat, di.carbs
            FROM meal_plans mp
            JOIN dishes d ON d.id = mp.dish_id
            LEFT JOIN dish_ingredients di ON di.dish_id = d.id
            WHERE mp.user_id = ? AND mp.plan_date BETWEEN ? AND ?
            ORDER BY mp.plan_date, d.name
            """,
            (user_id, start_date, end_date),
        )
        rows = cursor.fetchall()

        aggregated: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {}
        plans: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            plan_id = row["plan_id"]
            if plan_id not in plans:
                plans[plan_id] = {
                    "plan_id": plan_id,
                    "plan_date": row["plan_date"],
                    "meal_type": row["meal_type"],
                    "dish_id": row["dish_id"],
                    "dish_name": row["dish_name"],
                    "planned_servings": row["planned_servings"],
                    "base_servings": row["base_servings"],
                }
            ingredient_name = (row["ingredient_name"] or "").strip()
            if not ingredient_name:
                continue
            base_servings = row["base_servings"] or 1
            ratio = (row["planned_servings"] or 1) / base_servings
            quantity = (row["quantity"] or 0) * ratio
            key = (ingredient_name.lower(), row["unit"])
            entry = aggregated.setdefault(
                key,
                {
                    "name": ingredient_name,
                    "unit": row["unit"],
                    "quantity": 0.0,
                    "calories": 0.0,
                    "protein": 0.0,
                    "fat": 0.0,
                    "carbs": 0.0,
                },
            )
            entry["quantity"] += quantity
            if row["calories"] is not None:
                entry["calories"] += (row["calories"] or 0) * ratio
            if row["protein"] is not None:
                entry["protein"] += (row["protein"] or 0) * ratio
            if row["fat"] is not None:
                entry["fat"] += (row["fat"] or 0) * ratio
            if row["carbs"] is not None:
                entry["carbs"] += (row["carbs"] or 0) * ratio

        conn.close()
        items = sorted(aggregated.values(), key=lambda item: item["name"].lower())
        return {
            "items": items,
            "plans": list(plans.values()),
        }

    return await _run_in_thread(_calculate)


async def add_reminder(
    user_id: str,
    chat_id: int,
    remind_at: str,
    message: str,
    job_name: str,
    dish_id: Optional[int] = None,
    plan_id: Optional[int] = None,
) -> int:
    def _insert() -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reminders (user_id, chat_id, dish_id, plan_id, remind_at, message, job_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, dish_id, plan_id, remind_at, message, job_name),
        )
        reminder_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return reminder_id

    return await _run_in_thread(_insert)


async def get_pending_reminders() -> List[Dict[str, Any]]:
    def _fetch() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, chat_id, dish_id, plan_id, remind_at, message, job_name FROM reminders"
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    return await _run_in_thread(_fetch)


async def remove_reminder(reminder_id: int) -> None:
    def _remove() -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        conn.commit()
        conn.close()

    await _run_in_thread(_remove)


async def remove_reminder_by_job(job_name: str) -> None:
    def _remove() -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE job_name = ?", (job_name,))
        conn.commit()
        conn.close()

    await _run_in_thread(_remove)


async def get_user_statistics(user_id: str) -> Dict[str, Any]:
    def _stats() -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM dishes")
        total_dishes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM dishes WHERE is_favorite = 1")
        favorite_dishes = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT category, COUNT(*) as cnt
            FROM dishes
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 5
            """
        )
        top_categories = [{"category": row["category"], "count": row["cnt"]} for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT d.name, COUNT(*) AS times
            FROM meal_plans mp
            JOIN dishes d ON d.id = mp.dish_id
            WHERE mp.user_id = ?
            GROUP BY mp.dish_id
            ORDER BY times DESC
            LIMIT 5
            """,
            (user_id,),
        )
        top_planned = [{"name": row["name"], "count": row["times"]} for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT action, COUNT(*) AS cnt
            FROM user_actions
            WHERE user_id = ?
            GROUP BY action
            """,
            (user_id,),
        )
        activity = {row["action"]: row["cnt"] for row in cursor.fetchall()}

        conn.close()
        return {
            "total_dishes": total_dishes,
            "favorite_dishes": favorite_dishes,
            "top_categories": top_categories,
            "top_planned": top_planned,
            "activity": activity,
        }

    return await _run_in_thread(_stats)

async def get_dish_suggestions_by_ingredients(available: Iterable[str]) -> List[Dict[str, Any]]:
    normalized = {item.strip().lower() for item in available if item.strip()}
    if not normalized:
        return []

    def _search() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT d.id, d.name FROM dishes d ORDER BY d.name"
        )
        dishes = cursor.fetchall()
        results: List[Dict[str, Any]] = []
        for dish in dishes:
            cursor.execute(
                "SELECT name FROM dish_ingredients WHERE dish_id = ?",
                (dish["id"],),
            )
            ing_names = {row[0].strip().lower() for row in cursor.fetchall() if row[0]}
            if not ing_names:
                continue
            have = ing_names & normalized
            missing = sorted(ing_names - normalized)
            coverage = len(have) / len(ing_names)
            if have:
                results.append(
                    {
                        "dish_id": dish["id"],
                        "name": dish["name"],
                        "matched": sorted(have),
                        "missing": missing,
                        "coverage": coverage,
                    }
                )
        conn.close()
        results.sort(key=lambda item: item["coverage"], reverse=True)
        return results

    return await _run_in_thread(_search)


async def export_data(user_id: str) -> Dict[str, str]:
    dishes = await list_dishes()
    plans = await get_meal_plans_in_range(user_id, "1970-01-01", "2999-12-31")

    dish_lines = [
        "name,category,cuisine,servings,prep_time,cook_time,difficulty,is_favorite,tags,ingredients,recipe,description,notes"
    ]
    for dish in dishes:
        tags = ";".join(dish.get("tags", []))
        ingredients_text = "; ".join(
            [
                f"{ing['name']}|{ing.get('quantity', '')}|{ing.get('unit', '')}|{ing.get('calories', '')}|{ing.get('protein', '')}|{ing.get('fat', '')}|{ing.get('carbs', '')}"
                for ing in dish.get("ingredients_list", [])
            ]
        )
        line = ",".join(
            [
                f'"{str(dish.get(key, "") or "").replace("\"", "''")}"'
                for key in [
                    "name",
                    "category",
                    "cuisine",
                    "servings",
                    "prep_time",
                    "cook_time",
                    "difficulty",
                    "is_favorite",
                    None,
                    None,
                    None,
                    "description",
                    "notes",
                ]
            ]
        )
        # Replace placeholders for tags and ingredients, recipe
        line_parts = line.split(",")
        line_parts[8] = f'"{tags}"'
        line_parts[9] = f'"{ingredients_text}"'
        line_parts[10] = f'"{(dish.get("instructions") or dish.get("recipe") or "").replace("\"", "''")}"'
        dish_lines.append(",".join(line_parts))

    plan_lines = ["plan_date,meal_type,dish_name,servings,notes"]
    for plan in plans:
        plan_lines.append(
            ",".join(
                [
                    plan.get("plan_date", ""),
                    plan.get("meal_type", ""),
                    plan.get("name", ""),
                    str(plan.get("servings", "")),
                    f'"{(plan.get("notes") or "").replace("\"", "''")}"',
                ]
            )
        )

    return {
        "dishes.csv": "\n".join(dish_lines),
        "plan.csv": "\n".join(plan_lines),
    }


async def import_dishes(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    added = 0
    skipped = []
    for row in rows:
        name = row.get("name", "").strip()
        if not name:
            continue
        existing = await get_dish_by_name(name)
        if existing:
            skipped.append(name)
            continue

        tags = row.get("tags", "")
        tag_list = [tag.strip() for tag in tags.split(";") if tag.strip()]
        ingredients_text = row.get("ingredients", "")
        ingredient_entries: List[Dict[str, Any]] = []
        if ingredients_text:
            for chunk in ingredients_text.split(";"):
                parts = [part.strip() for part in chunk.split("|")]
                if not parts or not parts[0]:
                    continue
                while len(parts) < 7:
                    parts.append("")
                ingredient_entries.append(
                    {
                        "name": parts[0],
                        "quantity": float(parts[1]) if parts[1] else None,
                        "unit": parts[2] or None,
                        "calories": float(parts[3]) if parts[3] else None,
                        "protein": float(parts[4]) if parts[4] else None,
                        "fat": float(parts[5]) if parts[5] else None,
                        "carbs": float(parts[6]) if parts[6] else None,
                    }
                )
        try:
            await add_dish(
                {
                    "name": name,
                    "category": row.get("category"),
                    "cuisine": row.get("cuisine"),
                    "servings": float(row.get("servings")) if row.get("servings") else 1,
                    "prep_time": int(float(row.get("prep_time"))) if row.get("prep_time") else 0,
                    "cook_time": int(float(row.get("cook_time"))) if row.get("cook_time") else 0,
                    "difficulty": row.get("difficulty"),
                    "is_favorite": str(row.get("is_favorite", "")).strip() in {"1", "true", "True"},
                    "instructions": row.get("recipe") or row.get("instructions"),
                    "description": row.get("description"),
                    "notes": row.get("notes"),
                },
                ingredient_entries,
                tag_list,
            )
            added += 1
        except ValueError:
            skipped.append(name)
    return {"added": added, "skipped": skipped}



async def set_dish_tags(dish_id: int, tags: Sequence[str]) -> bool:
    def _set() -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dishes WHERE id = ?", (dish_id,))
        if not cursor.fetchone():
            conn.close()
            return False
        cursor.execute("DELETE FROM dish_tags WHERE dish_id = ?", (dish_id,))
        for tag in tags:
            clean_tag = tag.strip().lower()
            if clean_tag:
                cursor.execute(
                    "INSERT OR IGNORE INTO dish_tags (dish_id, tag) VALUES (?, ?)",
                    (dish_id, clean_tag),
                )
        conn.commit()
        conn.close()
        return True

    return await _run_in_thread(_set)

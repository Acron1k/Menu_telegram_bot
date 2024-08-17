import sqlite3

def get_db_connection():
    # Подключение к базе данных
    conn = sqlite3.connect('menu.db')
    return conn

def create_tables():
    # Создание таблиц в базе данных
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dishes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ingredients TEXT,
        recipe TEXT
    )
    ''')
    conn.commit()
    conn.close()

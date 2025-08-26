import sqlite3
import json
import matplotlib.pyplot as plt
from io import BytesIO
def create_db():
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()

    # --- Таблица пользователей ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            telegram_username TEXT,
            name TEXT,
            date TEXT DEFAULT (DATE('now')),
            weight FLOAT,
            target_weight FLOAT,
            age INTEGER CHECK(age BETWEEN 14 AND 42),
            height INTEGER,
            sex VARCHAR(6) NOT NULL CHECK (sex IN ('Male', 'Female')),
            max_photos INTEGER DEFAULT 15,
            photos_used INTEGER DEFAULT 0,
            end_date DATE DEFAULT NULL
        )
    """)

    # --- Таблица записей еды ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            food_json TEXT,  -- здесь храним JSON с per_100g и total
            date TEXT DEFAULT (DATE('now')),
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )
    """)

    # --- Таблица агрегированных дней ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT DEFAULT (DATE('now')),
            total_protein FLOAT,
            total_fat FLOAT,
            total_carbs FLOAT,
            total_calories FLOAT,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )
    """)

    # --- Таблица истории веса ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weight_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT DEFAULT (DATE('now')),
            weight FLOAT,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommended_kbju (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            recommended_calories FLOAT,
            recommended_protein FLOAT,
            recommended_fat FLOAT,
            recommended_carbs FLOAT,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )
    """)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS days_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_id INTEGER,
    record_id INTEGER,
    FOREIGN KEY(day_id) REFERENCES days(id),
    FOREIGN KEY(record_id) REFERENCES records(id)
);
        
        """


    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS gpt_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT DEFAULT (DATE('now')),
        url TEXT,
        tokens INTEGER);
        """

    )
    conn.commit()
    conn.close()



def is_user_registered(telegram_id):
       conn = sqlite3.connect("data.db")
       cursor = conn.cursor()
       cursor.execute(
           "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
       )
       user = cursor.fetchone()
       conn.close()
       return user
def register_user(message, data, days_to_achieve=None):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (
            telegram_id, telegram_username, name, weight, target_weight, age, height, sex, max_photos, photos_used, end_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message.from_user.id,
        message.from_user.username,
        data['name'],
        data['weight'],
        data['target_weight'],
        data.get('age'),
        data.get('height'),
        data.get('sex'),
        15,
        0,
        None
    ))
    conn.commit()
    conn.close()


def save_log(img_path, total_tokens):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO gpt_log ( url, tokens)
        VALUES (?, ?)
    """, (
        img_path,
        total_tokens
    ))
    conn.commit()
    conn.close()


def can_upload_photo(user_id):
        conn = sqlite3.connect("data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT photos_used, max_photos FROM users WHERE telegram_id=?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return False
        photos_used, max_photos = row
        return photos_used < max_photos

def increment_photo_usage(user_id):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET photos_used = photos_used + 1 WHERE telegram_id=?", (user_id,))
    conn.commit()
    conn.close()


def save_record(user_id, food_json):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO records (user_id, food_json)
        VALUES (?, ?)
    """, (user_id, json.dumps(food_json, ensure_ascii=False)))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def update_record_json(record_id, food_json):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE records
        SET food_json = ?
        WHERE id = ?
    """, (json.dumps(food_json, ensure_ascii=False), record_id))
    conn.commit()
    conn.close()



def save_weight(user_id, weight):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    # проверяем, был ли уже вес сегодня
    cursor.execute("""
        SELECT id FROM weight_history 
        WHERE user_id=? AND date=DATE('now')
    """, (user_id,))
    if cursor.fetchone():
        conn.close()
        return False  # уже есть запись

    cursor.execute("""
        INSERT INTO weight_history (user_id, weight)
        VALUES (?, ?)
    """, (user_id, weight))
    conn.commit()
    conn.close()
    return True

def calculate_kbju(weight, height, age, sex, activity_factor=1.375):


    if sex == 'Male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:  # Female
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    calories = bmr * activity_factor

    # 3️⃣ КБЖУ (граммы)
    protein = round((calories * 0.2) / 4, 1)
    fat = round((calories * 0.25) / 9, 1)
    carbs = round((calories * 0.55) / 4, 1)

    return {
        'Calories': round(calories),
        'Protein_g': protein,
        'Fat_g': fat,
        'Carbs_g': carbs
    }



def save_recommended_kbju_by_id(telegram_id, activity_factor=1.375):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()

    # Получаем данные пользователя
    cursor.execute("""
        SELECT weight, height, age, sex FROM users WHERE telegram_id = ?
    """, (telegram_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise ValueError(f"Пользователь с telegram_id {telegram_id} не найден.")

    weight, height, age, sex = user

    # Считаем КБЖУ
    kbju = calculate_kbju(weight, height, age, sex, activity_factor)

    # Сохраняем в recommended_kbju
    cursor.execute("""
        INSERT INTO recommended_kbju (
            user_id, recommended_calories, recommended_protein, recommended_fat, recommended_carbs
        ) VALUES (?, ?, ?, ?, ?)
    """, (
        telegram_id,
        kbju['Calories'],
        kbju['Protein_g'],
        kbju['Fat_g'],
        kbju['Carbs_g']
    ))
    conn.commit()
    conn.close()

    return kbju
def get_today_stats(user_id):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()

    # --- Получаем рекомендованное КБЖУ ---
    cursor.execute("""
        SELECT recommended_calories, recommended_protein, recommended_fat, recommended_carbs
        FROM recommended_kbju
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,))
    kbju = cursor.fetchone()
    if not kbju:
        conn.close()
        return None
    rec_calories, rec_protein, rec_fat, rec_carbs = kbju

    # --- Получаем все записи за сегодня ---
    cursor.execute("""
        SELECT food_json FROM records
        WHERE user_id = ? AND date = DATE('now')
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    total_protein = total_fat = total_carbs = total_calories = 0

    for row in rows:
        food_json = json.loads(row[0])
        for key, prod in food_json.get("products", {}).items():
            total_protein += prod["total"]["protein"]
            total_fat += prod["total"]["fat"]
            total_carbs += prod["total"]["carbs"]
            total_calories += prod["total"]["calories"]

    stats = {
        "eaten": {
            "Calories": round(total_calories, 1),
            "Protein": round(total_protein, 1),
            "Fat": round(total_fat, 1),
            "Carbs": round(total_carbs, 1)
        },
        "recommended": {
            "Calories": round(rec_calories, 1),
            "Protein": round(rec_protein, 1),
            "Fat": round(rec_fat, 1),
            "Carbs": round(rec_carbs, 1)
        }
    }

    return stats



def plot_today_stats(user_id):
    stats = get_today_stats(user_id)
    if not stats:
        return None

    eaten = stats['eaten']
    recommended = stats['recommended']

    labels = ['Белки', 'Жиры', 'Углеводы']
    eaten_values = [eaten['Protein'], eaten['Fat'], eaten['Carbs']]
    rec_values = [recommended['Protein'], recommended['Fat'], recommended['Carbs']]

    fig, ax = plt.subplots(figsize=(6, 6))
    width = 0.35  # ширина столбцов
    x = range(len(labels))

    ax.bar(x, rec_values, width, label='Рекомендовано', color='#87CEFA')
    ax.bar([i + width for i in x], eaten_values, width, label='Съедено', color='#FFA07A')

    ax.set_xticks([i + width / 2 for i in x])
    ax.set_xticklabels(labels)
    ax.set_ylabel('Граммы')
    ax.set_title('КБЖУ за сегодня')
    ax.legend()

    # Сохраняем в буфер
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='PNG')
    buf.seek(0)
    plt.close(fig)
    return buf
if __name__ == "__main__":
    print(calculate_kbju(60,182,19,"Male"))

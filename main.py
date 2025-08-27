import telebot
import requests
import sqlite3
import json
import re
from telebot import types, custom_filters
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
import db
import gpt
from API_KEYS import TELEGRAM_TOKEN


state_storage = StateMemoryStorage()
db.create_db()
bot = telebot.TeleBot(TELEGRAM_TOKEN, state_storage=state_storage)
user_data = {}


class RangeError(Exception):
    pass


class RegisterStates(StatesGroup):
    enter_name = State()
    enter_weight = State()
    enter_target_weight = State()
    enter_age = State()
    enter_height = State()
    enter_sex = State()

class AllStates(StatesGroup):
    register = State()
    base_settings = State()
    handle_photo = State()
    change_weight = State()
    weight = State()


@bot.message_handler(commands=['start'])
def handle_start(message):
    user = db.is_user_registered(message.from_user.id)
    print(user)
    if user:
        name = user[2]
        bot.send_message(
            message.chat.id,
            f"🥗 Привет снова, {name}!\n\n"
            f"Я твой личный нутрициолог-бот. Отправь мне фото еды, "
            f"и я рассчитaю её КБЖУ и калорийность.\n"
        )
        bot.set_state(message.from_user.id, AllStates.handle_photo, message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "Добро пожаловать! Пожалуйста, зарегистрируйтесь, для начала введите ваше имя."
        )
        bot.set_state(message.from_user.id, RegisterStates.enter_name, message.chat.id)


@bot.message_handler(state=RegisterStates.enter_name)
def get_name(message):
    name = message.text.strip()
    if not name:
        bot.send_message(message.chat.id, "Имя не может быть пустым. Введите ваше имя:")
        return
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['name'] = name
    bot.send_message(message.chat.id, "Введите ваш текущий вес (например, 72.5):")
    bot.set_state(message.from_user.id, RegisterStates.enter_weight, message.chat.id)


@bot.message_handler(state=RegisterStates.enter_weight)
def get_weight(message):
    try:
        weight = float(message.text.strip())
        if weight <= 0:
            raise ValueError
        elif weight < 30 or weight > 140:
            raise RangeError

    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат. Введите вес в формате XX.X:")
        return
    except RangeError:
        bot.send_message(message.chat.id, "Вес может находиться только в пределах от 30 до 140 кг")
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['weight'] = weight
    bot.send_message(message.chat.id, "Введите вес которого вы хотите достичь, если хотите сохранить текущей вес впишите его снова. Целевой вес (кг) в формате XX.X:")
    bot.set_state(message.from_user.id, RegisterStates.enter_target_weight, message.chat.id)


@bot.message_handler(state=RegisterStates.enter_target_weight)
def get_target_weight(message):
    try:
        target_weight = float(message.text.strip())
        if target_weight <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат. Введите вес в формате XX.X:")
        return

    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['target_weight'] = target_weight


    bot.send_message(
        message.chat.id,
        "Теперь отправьте ваш возраст"
    )
    bot.set_state(message.from_user.id, RegisterStates.enter_age, message.chat.id)


@bot.message_handler(state=RegisterStates.enter_age)
def get_target_weight(message):
    try:
        age = float(message.text.strip())
        if not(14 <= age <=42):
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "Неверный возраст. Возраст в пределах от 14-42 лет")
        return

    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['age'] = age

    bot.send_message(message.chat.id, "Введите ваш рост в см (например, 175):")
    bot.set_state(message.from_user.id, RegisterStates.enter_height, message.chat.id)


@bot.message_handler(state=RegisterStates.enter_height)
def get_height(message):
    try:
        height = float(message.text.strip())
        if not (100 <= height <= 220):
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "Неверный рост. Введите число в пределах 100-220 см:")
        return

    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['height'] = height

    bot.send_message(
        message.chat.id,
        "Укажите ваш пол (Male/Female):"
    )
    bot.set_state(message.from_user.id, RegisterStates.enter_sex, message.chat.id)



@bot.message_handler(state=RegisterStates.enter_sex)
def get_sex(message):
    sex = message.text.strip().capitalize()
    if sex not in ["Male", "Female"]:
        bot.send_message(message.chat.id, "Неверный ввод. Введите 'Male' или 'Female':")
        return

    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['sex'] = sex
        db.register_user(
            message=message,
            data=data,
            days_to_achieve=None
        )
        db.save_recommended_kbju_by_id(message.from_user.id)

    bot.send_message(
        message.chat.id,
        f"✅ Регистрация завершена!\n"
        f"Текущий вес: {data['weight']} кг\n"
        f"Цель: {data['target_weight']} кг\n"
        f"Возраст: {data['age']}\n"
        f"Рост: {data['height']} см\n"
        f"Пол: {data['sex']}\n"
        f"Вы можете отправить до 15 фото еды в день."
    )
    bot.set_state(message.from_user.id, AllStates.handle_photo, message.chat.id)


@bot.message_handler(content_types=["photo"], state=AllStates.handle_photo)
def handle_photo(message):
    if not db.can_upload_photo(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Лимит фото исчерпан. Доступно 15 фото.")
        return
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        file_bytes = requests.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        ).content
        user_description = message.caption or ""

        result_text = gpt.analyze_food(file_bytes,user_description)
        cleaned = re.sub(r"```(?:json)?\s*([\s\S]+?)```", r"\1", result_text).strip()

        try:
            data = json.loads(cleaned)
            if "total_products" not in data or "products" not in data:
                bot.reply_to(message, f"❌ Неверный JSON:\n\n{cleaned}")
                return

            total_products = data["total_products"]
            products = data["products"]
            text_blocks = []


            for idx in range(1, total_products + 1):
                product_key = f"product_{idx}"
                prod = products[product_key]

                protein = float(prod["per_100g"]["protein"])
                fat = float(prod["per_100g"]["fat"])
                carbs = float(prod["per_100g"]["carbs"])
                weight = int(prod["weight"])

                calories_100g = protein * 4 + fat * 9 + carbs * 4
                prod["per_100g"]["calories"] = round(calories_100g, 1)

                prod["total"] = {
                    "protein": round(protein * weight / 100, 1),
                    "fat": round(fat * weight / 100, 1),
                    "carbs": round(carbs * weight / 100, 1),
                    "calories": round(calories_100g * weight / 100, 1),
                }

                block = (
                    f"🍽 {prod['name']} ({weight} г)\n\n"
                    f"⚖ На 100 г:\n"
                    f"  • Белки: {protein} г\n"
                    f"  • Жиры: {fat} г\n"
                    f"  • Углеводы: {carbs} г\n"
                    f"  • Калории: {prod['per_100g']['calories']} ккал\n\n"
                    f"🔥 Итог:\n"
                    f"  • Белки: {prod['total']['protein']} г\n"
                    f"  • Жиры: {prod['total']['fat']} г\n"
                    f"  • Углеводы: {prod['total']['carbs']} г\n"
                    f"  • Калории: {prod['total']['calories']} ккал\n"
                )
                text_blocks.append(block)

            full_text = "\n\n".join(text_blocks)
            bot.send_message(message.chat.id, full_text)

            db.save_record(message.from_user.id, data)
            user_data[message.chat.id] = {"data": data, "change_idx": None}
        except Exception as e:
            bot.reply_to(message, f"❌ GPT вернул невалидный JSON:\n\n{cleaned}\n\nОшибка: {e}")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")


@bot.message_handler(commands=['kbju'])
def send_kbju(message):
    telegram_id = message.from_user.id
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT recommended_calories, recommended_protein, recommended_fat, recommended_carbs
        FROM recommended_kbju
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (telegram_id,))
    kbju = cursor.fetchone()


    if not kbju:
        cursor.execute("""
            SELECT weight, height, age, sex FROM users WHERE telegram_id = ?
        """, (telegram_id,))
        user = cursor.fetchone()
        if not user:
            bot.send_message(message.chat.id, "Пользователь не найден. Сначала зарегистрируйтесь через /start")
            conn.close()
            return

        weight, height, age, sex = user
        kbju_dict = db.calculate_kbju(weight, height, age, sex)
        cursor.execute("""
            INSERT INTO recommended_kbju (
                user_id, recommended_calories, recommended_protein, recommended_fat, recommended_carbs
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            telegram_id,
            kbju_dict['Calories'],
            kbju_dict['Protein_g'],
            kbju_dict['Fat_g'],
            kbju_dict['Carbs_g']
        ))
        conn.commit()
        kbju = (
            kbju_dict['Calories'],
            kbju_dict['Protein_g'],
            kbju_dict['Fat_g'],
            kbju_dict['Carbs_g']
        )

    conn.close()

    bot.send_message(
        message.chat.id,
        f"🥗 Ваши рекомендованные КБЖУ:\n"
        f"Калории: {kbju[0]} ккал\n"
        f"Белки: {kbju[1]} г\n"
        f"Жиры: {kbju[2]} г\n"
        f"Углеводы: {kbju[3]} г"
    )


@bot.message_handler(commands=["menu"])
def show_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📸 Отправить фото", "⚖ Отправить вес")
    markup.row("📊 Посмотреть статистику")
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)


@bot.message_handler(state=AllStates.weight)
def handle_weight_menu(message):
    try:
        weight = float(message.text.strip())
        if weight <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат. Введите вес в формате XX.X:")
        return

    success = db.save_weight(message.from_user.id, weight)
    if not success:
        bot.send_message(message.chat.id, "⚠️ Сегодня вес уже был записан. Попробуй завтра.")
    else:
        bot.send_message(message.chat.id, f"✅ Вес {weight} кг сохранён в историю.")
        bot.delete_state(message.from_user.id, message.chat.id)


@bot.message_handler(func=lambda message: True)
def handle_menu(message):
    if message.text == "📸 Отправить фото":
        bot.send_message(message.chat.id, "Отправьте фото еды:")
        bot.set_state(message.from_user.id, AllStates.handle_photo, message.chat.id)

    elif message.text == "⚖ Отправить вес":
        bot.send_message(message.chat.id, "Введите ваш вес в формате XX.X:")
        bot.set_state(message.from_user.id, AllStates.weight, message.chat.id)

    elif message.text == "📊 Посмотреть статистику":
        stats = db.get_today_stats(message.from_user.id)
        if not stats:
            bot.send_message(message.chat.id, "❌ Нет данных за сегодня.")
            return

        caption = (
            f"📊 Статистика за сегодня:\n"
            f"Калории: {round(stats['eaten']['Calories'], 1)} / {round(stats['recommended']['Calories'], 1)} ккал\n"
            f"Белки: {round(stats['eaten']['Protein'], 1)} / {round(stats['recommended']['Protein'], 1)} г\n"
            f"Жиры: {round(stats['eaten']['Fat'], 1)} / {round(stats['recommended']['Fat'], 1)} г\n"
            f"Углеводы: {round(stats['eaten']['Carbs'], 1)} / {round(stats['recommended']['Carbs'], 1)} г"
        )


        img_buf = db.plot_today_stats(message.from_user.id)
        if img_buf:
            bot.send_photo(message.chat.id, img_buf, caption=caption)

        else:
            bot.send_message(message.chat.id, caption)

    else:
        bot.send_message(message.chat.id, "Выберите опцию из меню.")

print("Бот запущен!")
bot.add_custom_filter(custom_filters.StateFilter(bot))
bot.infinity_polling(skip_pending=True)
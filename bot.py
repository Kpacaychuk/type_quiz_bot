import asyncio
import json
import random
import string
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Загрузка токена из config.json
try:
    with open('config.json', 'r', encoding='utf-8') as config_file:
        config = json.load(config_file)
        API_TOKEN = config.get('token')
        if not API_TOKEN:
            raise ValueError("Токен не найден в config.json. Убедитесь, что файл содержит: {\"token\": \"ваш_токен\"}")
except FileNotFoundError:
    raise FileNotFoundError("Файл config.json не найден. Создайте файл с содержимым: {\"token\": \"ваш_токен\"}")
except json.JSONDecodeError as e:
    raise ValueError(f"Ошибка при чтении config.json. Проверьте формат файла: {e}")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

DATA_FILE = "data.json"

# ====== Состояния для FSM ======
class NameInput(StatesGroup):
    waiting_for_name = State()

# ====== Утилиты для хранения ======
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"users": {}}
            data = json.loads(content)
            # Убедимся, что раздел users существует
            if "users" not in data:
                data["users"] = {}
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ====== Утилиты для работы с именами ======
def get_user_name(user_id):
    """Получить имя и фамилию пользователя"""
    data = load_data()
    users = data.get("users", {})
    user_data = users.get(str(user_id), {})
    first_name = user_data.get("first_name", "")
    last_name = user_data.get("last_name", "")
    return first_name, last_name


def save_user_name(user_id, first_name, last_name):
    """Сохранить имя и фамилию пользователя"""
    data = load_data()
    if "users" not in data:
        data["users"] = {}
    data["users"][str(user_id)] = {
        "first_name": first_name,
        "last_name": last_name
    }
    save_data(data)


def user_has_name(user_id):
    """Проверить, есть ли у пользователя сохраненное имя"""
    data = load_data()
    users = data.get("users", {})
    user_data = users.get(str(user_id), {})
    return bool(user_data.get("first_name") and user_data.get("last_name"))

# ====== Генерация ID ======
def generate_quiz_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ====== Метрика похожести ======
def similarity(a, b):
    return len(set(a) & set(b))

def make_groups(answers, group_size=5):
    people = list(answers.keys())
    groups = []
    used = set()

    while len(used) < len(people):
        remaining = [p for p in people if p not in used]
        group = [random.choice(remaining)]
        used.add(group[0])

        while len(group) < group_size:
            candidates = [p for p in people if p not in used]
            p = min(candidates, key=lambda x: sum(similarity(answers[x], answers[g]) for g in group))
            group.append(p)
            used.add(p)

        groups.append(group)
    return groups

# ====== Команда /start ======
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, есть ли у пользователя сохраненное имя
    if not user_has_name(user_id):
        await message.answer("👋 Привет! Мне нужно узнать твое имя и фамилию.\n"
                             "Пожалуйста, введи свое имя и фамилию через пробел:\n"
                             "Например: Иван Иванов")
        await state.set_state(NameInput.waiting_for_name)
    else:
        first_name, last_name = get_user_name(user_id)
        await message.answer(f"👋 Привет, {first_name} {last_name}!\n\n"
                             "Я бот для группового опроса.\n"
                             "Создай опрос:\n"
                             "/create_quiz\n"
                             "Или с вариантами ответов:\n"
                             "/create_quiz вариант1 вариант2 вариант3 вариант4 вариант5\n\n"
                             "Присоединись к существующему опросу:\n"
                             "/join_to_quiz ABC123\n"
                             "где ABC123 — ID опроса\n\n"
                             "Изменить имя: /change_my_name")

# ====== Обработка ввода имени ======
@dp.message(StateFilter(NameInput.waiting_for_name))
async def process_name_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    parts = text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.answer("❗ Пожалуйста, введи имя и фамилию через пробел:\n"
                             "Например: Иван Иванов")
        return
    
    first_name = parts[0].strip()
    last_name = parts[1].strip()
    
    # Валидация: проверяем, что имя и фамилия не пустые
    if not first_name or not last_name:
        await message.answer("❗ Имя и фамилия не могут быть пустыми.\n"
                             "Пожалуйста, введи имя и фамилию через пробел:\n"
                             "Например: Иван Иванов")
        return
    
    # Валидация: проверяем длину
    if len(first_name) > 50 or len(last_name) > 50:
        await message.answer("❗ Имя и фамилия не должны превышать 50 символов.")
        return
    
    user_id = message.from_user.id
    
    # Сохраняем имя и фамилию
    save_user_name(user_id, first_name, last_name)
    await state.clear()
    
    await message.answer(f"✅ Спасибо, {first_name} {last_name}! Твои данные сохранены.\n\n"
                         "Я бот для группового опроса.\n"
                         "Создай опрос:\n"
                         "/create_quiz\n"
                         "Или с вариантами ответов:\n"
                         "/create_quiz вариант1 вариант2 вариант3 вариант4 вариант5\n\n"
                         "Присоединись к существующему опросу:\n"
                         "/join_to_quiz ABC123\n"
                         "где ABC123 — ID опроса\n\n"
                         "Изменить имя: /change_my_name")

# ====== Команда изменения имени ======
@dp.message(Command("change_my_name"))
async def change_my_name(message: types.Message, state: FSMContext):
    await message.answer("Введи свое новое имя и фамилию через пробел:\n"
                         "Например: Иван Иванов")
    await state.set_state(NameInput.waiting_for_name)

# ====== Создание опроса ======
@dp.message(Command("create_quiz"))
async def create_quiz(message: types.Message):
    # Получаем текст команды и аргументы
    command_text = message.text or ""
    parts = command_text.split(maxsplit=6)  # Команда + максимум 6 аргументов
    
    # Если переданы варианты ответов (5 аргументов после команды)
    if len(parts) >= 6:
        # Берем первые 5 аргументов после команды
        options = parts[1:6]
        # Убираем пробелы и проверяем, что все варианты не пустые
        options = [opt.strip() for opt in options if opt.strip()]
        if len(options) < 5:
            await message.answer("❗ Необходимо указать 5 вариантов ответов.\n"
                                 "Формат: /create_quiz вариант1 вариант2 вариант3 вариант4 вариант5\n"
                                 "Или: /create_quiz (без аргументов для вариантов по умолчанию)\n\n"
                                 "⚠️ Если вариант содержит пробелы, используйте кавычки:\n"
                                 "/create_quiz \"Вариант 1\" \"Вариант 2\" вариант3 вариант4 вариант5")
            return
        # Обрезаем длинные варианты (максимум 64 символа для кнопки Telegram)
        options = [opt[:64] for opt in options]
    else:
        # Используем варианты по умолчанию
        options = ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4", "Вариант 5"]
    
    data = load_data()
    quiz_id = generate_quiz_id()
    data[quiz_id] = {
        "creator": message.from_user.id,
        "active": True,
        "participants": {},
        "options": options,  # Сохраняем тексты вариантов
    }
    save_data(data)
    options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
    await message.answer(f"✅ Опрос создан!\nID опроса: `{quiz_id}`\n\n"
                         f"Варианты ответов:\n{options_text}", 
                         parse_mode="Markdown")

# ====== Присоединение к опросу ======
@dp.message(Command("join_to_quiz"))
async def join_quiz(message: types.Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❗ Укажи ID опроса: /join_to_quiz ABC123")
        return

    quiz_id = args[1].strip().upper()
    data = load_data()

    if quiz_id not in data or quiz_id == "users":
        await message.answer("❌ Такого опроса не существует.")
        return
    quiz = data[quiz_id]
    
    # Проверяем, что это действительно квиз (не раздел users)
    if not isinstance(quiz, dict) or "participants" not in quiz:
        await message.answer("❌ Такого опроса не существует.")
        return

    if not quiz["active"]:
        await message.answer("⚠️ Этот опрос уже завершён.")
        return
    if len(quiz["participants"]) >= 35:
        await message.answer("⚠️ В опросе уже 35 участников.")
        return
    # if message.from_user.id == quiz["creator"]:
    #     await message.answer("❗ Создатель не может участвовать в своём опросе.")
    #     return
    if str(message.from_user.id) in quiz["participants"]:
        await message.answer("⚠️ Ты уже участвуешь в этом опросе.")
        return

    # Начинаем опрос
    await send_quiz_keyboard(message, quiz_id)

# ====== Отправка клавиатуры с вариантами ======
async def send_quiz_keyboard(message, quiz_id):
    data = load_data()
    quiz = data.get(quiz_id, {})
    
    # Получаем варианты ответов из квиза, или используем по умолчанию
    options = quiz.get("options", ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4", "Вариант 5"])
    
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        # Используем текст варианта из квиза, но callback_data содержит номер
        option_text = options[i-1] if i-1 < len(options) else f"Вариант {i}"
        builder.button(text=option_text, callback_data=f"vote:{quiz_id}:{i}")
    builder.adjust(3)
    await message.answer("Выбери 3 варианта из 5:", reply_markup=builder.as_markup())

# ====== Обработка выбора вариантов ======
@dp.callback_query(lambda c: c.data.startswith("vote:"))
async def handle_vote(callback: types.CallbackQuery):
    _, quiz_id, choice = callback.data.split(":")
    data = load_data()
    
    # Проверяем, что quiz_id не равен "users" и что это действительно квиз
    if quiz_id == "users" or quiz_id not in data:
        await callback.answer("Опрос не найден.", show_alert=True)
        return
    
    quiz = data.get(quiz_id)
    if not isinstance(quiz, dict) or "participants" not in quiz or not quiz.get("active"):
        await callback.answer("Опрос не найден или уже завершён.", show_alert=True)
        return

    user_id = str(callback.from_user.id)
    if user_id not in quiz["participants"]:
        quiz["participants"][user_id] = {"answers": []}

    user_answers = quiz["participants"][user_id]["answers"]
    choice_num = int(choice)
    
    # Получаем текст варианта для отображения
    options = quiz.get("options", ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4", "Вариант 5"])
    option_text = options[choice_num - 1] if choice_num - 1 < len(options) else f"Вариант {choice_num}"

    if choice_num in user_answers:
        user_answers.remove(choice_num)
        await callback.answer(f"❌ Убран: {option_text}")
    else:
        if len(user_answers) >= 3:
            await callback.answer("⚠️ Можно выбрать только 3 варианта.")
            return
        user_answers.append(choice_num)
        await callback.answer(f"✅ Добавлен: {option_text}")

    # Обновляем данные
    save_data(data)

    # Если пользователь завершил выбор — подтверждаем
    if len(user_answers) == 3:
        await callback.message.edit_text("✅ Твои ответы сохранены. Спасибо за участие!")
        # Проверим, завершён ли опрос
        await check_and_finalize_quiz(quiz_id)

# ====== Проверка завершённости ======
async def check_and_finalize_quiz(quiz_id):
    data = load_data()
    quiz = data[quiz_id]
    participants = quiz["participants"]

    if len(participants) == 35 and all(len(p["answers"]) == 3 for p in participants.values()):
        quiz["active"] = False
        answers = {uid: set(p["answers"]) for uid, p in participants.items()}
        groups = make_groups(answers)
        #groups = make_groups(answers, num_groups=7, group_size=5)

        result_text = f"📊 Результаты опроса #{quiz_id}:\n\n"
        
        for i, group in enumerate(groups, 1):
            result_text += f"Группа {i}:\n"
            for uid in group:
                uid_str = str(uid)
                # Получаем имя и фамилию
                first_name, last_name = get_user_name(uid)
                # Получаем ответы
                user_answers = sorted(participants[uid_str]["answers"])
                answers_str = ", ".join(map(str, user_answers))
                
                # Формируем строку: Имя Фамилия (ответы: 1, 2, 3) [ID: 123456]
                if first_name and last_name:
                    result_text += f"— {first_name} {last_name} (ответы: {answers_str}) [ID: {uid_str}]\n"
                else:
                    result_text += f"— Неизвестный пользователь (ответы: {answers_str}) [ID: {uid_str}]\n"
            result_text += "\n"
        
        # Добавляем информацию о вариантах ответов в конце
        options = quiz.get("options", ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4", "Вариант 5"])
        result_text += "Варианты ответов:\n"
        for i, option in enumerate(options, 1):
            result_text += f"{i}. {option}\n"

        # Отправляем результаты создателю
        creator_id = quiz["creator"]
        await bot.send_message(creator_id, result_text)
        save_data(data)

# ====== Обработка username ======
@dp.message(~StateFilter(NameInput.waiting_for_name))
async def store_username(message: types.Message):
    # если участник пишет что-то, обновим username
    # Пропускаем команды
    if message.text and message.text.startswith("/"):
        return
    
    data = load_data()
    for quiz_id, quiz in data.items():
        # Пропускаем раздел users
        if quiz_id == "users":
            continue
        if not isinstance(quiz, dict) or "participants" not in quiz:
            continue
        pid = str(message.from_user.id)
        if pid in quiz["participants"]:
            quiz["participants"][pid]["username"] = message.from_user.username
    save_data(data)

# ====== Запуск ======
if __name__ == "__main__":
    print("Бот запущен...")
    asyncio.run(dp.start_polling(bot))



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
TARGET_PARTICIPANTS = 32
DEFAULT_GROUP_SIZES = [7, 7, 6, 6, 6]
MAX_ACTIVE_QUIZZES = 100

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

# ====== Получение списка активных опросов пользователя ======
def get_active_quiz_ids(user_id):
    """Получить список ID активных опросов, созданных пользователем"""
    data = load_data()
    active_quiz_ids = []
    for quiz_id, quiz in data.items():
        # Пропускаем раздел users
        if quiz_id == "users":
            continue
        # Проверяем, что это действительно квиз
        if isinstance(quiz, dict) and "creator" in quiz and "active" in quiz:
            if quiz["creator"] == user_id and quiz.get("active", False):
                active_quiz_ids.append(quiz_id)
    return active_quiz_ids

# ====== Подсчет активных опросов пользователя ======
def count_active_quizzes(user_id):
    """Подсчитать количество активных опросов, созданных пользователем"""
    return len(get_active_quiz_ids(user_id))

# ====== Метрика похожести ======
def similarity(a, b):
    return len(set(a) & set(b))

# def make_groups(answers, group_size=5):
#     people = list(answers.keys())
#     groups = []
#     used = set()

#     while len(used) < len(people):
#         remaining = [p for p in people if p not in used]
#         group = [random.choice(remaining)]
#         used.add(group[0])

#         while len(group) < group_size:
#             candidates = [p for p in people if p not in used]
#             p = min(candidates, key=lambda x: sum(similarity(answers[x], answers[g]) for g in group))
#             group.append(p)
#             used.add(p)

#         groups.append(group)
#     return groups

def make_groups(answers, group_size=5, group_sizes=None):
    """
    answers: dict { user_id_str: [a0, a1, a2] } -- порядок важен
    group_size: желаемый размер группы (по умолчанию 5)
    group_sizes: опциональный список размеров групп (например [7,7,6,6,6])
    Возвращает список групп (каждая группа — список user_id_str)
    """
    people = list(answers.keys())
    groups = []
    used = set()

    def build_group_size_plan(total):
        if group_sizes:
            plan = []
            remaining = total
            for size in group_sizes:
                if remaining <= 0:
                    break
                plan.append(min(size, remaining))
                remaining -= size
            while remaining > 0:
                plan.append(min(group_size, remaining))
                remaining -= group_size
            return plan
        plan = []
        remaining = total
        while remaining > 0:
            plan.append(min(group_size, remaining))
            remaining -= group_size
        return plan

    desired_sizes = build_group_size_plan(len(people))

    def count_position_matches(candidate, group, pos):
        """Количество совпадений по ответу на позиции pos с участниками группы"""
        matches = 0
        for g in group:
            if pos < len(answers[g]) and pos < len(answers[candidate]) and answers[g][pos] == answers[candidate][pos]:
                matches += 1
        return matches

    size_index = 0
    while len(used) < len(people) and size_index < len(desired_sizes):
        current_group_target = desired_sizes[size_index]
        remaining = [p for p in people if p not in used]
        seed = random.choice(remaining)
        group = [seed]
        used.add(seed)

        while len(group) < current_group_target and len(used) < len(people):
            candidates = [p for p in people if p not in used]
            best_candidates = []

            # 1️⃣ Проверяем по первой позиции — ищем тех, у кого нет совпадений вообще
            no_match_first = [c for c in candidates if count_position_matches(c, group, 0) == 0]
            if no_match_first:
                best_candidates = no_match_first
            else:
                # 2️⃣ Иначе ищем с минимальными совпадениями на первой позиции
                min_first = min(count_position_matches(c, group, 0) for c in candidates)
                best_candidates = [c for c in candidates if count_position_matches(c, group, 0) == min_first]

            # 3️⃣ Если всё ещё несколько — смотрим по второй позиции
            if len(best_candidates) > 1:
                no_match_second = [c for c in best_candidates if count_position_matches(c, group, 1) == 0]
                if no_match_second:
                    best_candidates = no_match_second
                else:
                    min_second = min(count_position_matches(c, group, 1) for c in best_candidates)
                    best_candidates = [c for c in best_candidates if count_position_matches(c, group, 1) == min_second]

            # 4️⃣ Если всё ещё несколько — смотрим по третьей позиции
            if len(best_candidates) > 1:
                no_match_third = [c for c in best_candidates if count_position_matches(c, group, 2) == 0]
                if no_match_third:
                    best_candidates = no_match_third
                else:
                    min_third = min(count_position_matches(c, group, 2) for c in best_candidates)
                    best_candidates = [c for c in best_candidates if count_position_matches(c, group, 2) == min_third]

            # 5️⃣ Если всё ещё несколько — выбираем случайного из равных по критериям
            best = random.choice(best_candidates)
            group.append(best)
            used.add(best)

        groups.append(group)
        size_index += 1

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
                             "Присоединись к опросу, отправив мне следующую команду:\n"
                             "/join_to_quiz ABC123\n"
                             "где ABC123 — ID опроса\n\n"
                             "Если написали имя или фамилию неправильно, изменить можно отправив мне следующую команду:\n"
                             "/change_my_name")

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
                             "Присоединись к опросу, отправив мне следующую команду:\n"
                             "/join_to_quiz ABC123\n"
                             "где ABC123 — ID опроса\n\n"
                             "Если написали имя или фамилию неправильно, изменить можно отправив мне следующую команду:\n"
                             "/change_my_name")

# ====== Команда изменения имени ======
@dp.message(Command("change_my_name"))
async def change_my_name(message: types.Message, state: FSMContext):
    await message.answer("Введи свое новое имя и фамилию через пробел:\n"
                         "Например: Иван Иванов")
    await state.set_state(NameInput.waiting_for_name)

# ====== Создание опроса ======
@dp.message(Command("create_quiz"))
async def create_quiz(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем количество активных опросов пользователя
    active_quiz_ids = get_active_quiz_ids(user_id)
    active_count = len(active_quiz_ids)
    if active_count >= MAX_ACTIVE_QUIZZES:
        # Формируем список ID для вывода
        ids_text = ", ".join(active_quiz_ids) if active_quiz_ids else "нет"
        await message.answer(f"⚠️ У тебя уже {active_count} активных опросов. "
                             f"Максимальное количество активных опросов: {MAX_ACTIVE_QUIZZES}.\n\n"
                             f"ID активных опросов:\n`{ids_text}`\n\n"
                             f"Заверши некоторые опросы перед созданием новых.",
                             parse_mode="Markdown")
        return
    
    # Всегда используем варианты по умолчанию, параметры игнорируются
    options = ["Креативы", "Реализаторы", "Стратеги", "Коммуникаторы", "Исследователи"]

    data = load_data()
    quiz_id = generate_quiz_id()
    data[quiz_id] = {
        "creator": message.from_user.id,
        "active": True,
        "participants": {},
        "options": options,
    }
    save_data(data)
    options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
    await message.answer(
        f"✅ Опрос создан!\nID опроса: `{quiz_id}`\n\n"
        f"Варианты ответов:\n{options_text}",
        parse_mode="Markdown"
    )

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
    if len(quiz["participants"]) >= TARGET_PARTICIPANTS:
        await message.answer(f"⚠️ В опросе уже {TARGET_PARTICIPANTS} участников.")
        return
    # if message.from_user.id == quiz["creator"]:
    #     await message.answer("❗ Создатель не может участвовать в своём опросе.")
    #     return
    if str(message.from_user.id) in quiz["participants"]:
        await message.answer("⚠️ Ты уже участвуешь в этом опросе.")
        return

    # Начинаем опрос
    await send_quiz_keyboard(message, quiz_id)


# ====== Генерация тестовых данных ======
# @dp.message(Command("generate_random_data"))
# async def generate_random_data(message: types.Message):
#     args = message.text.split()
#     if len(args) != 2:
#         await message.answer("❗ Укажи ID опроса: /generate_random_data ABC123")
#         return

#     quiz_id = args[1].strip().upper()
#     data = load_data()

#     if quiz_id not in data or quiz_id == "users":
#         await message.answer("❌ Такого опроса не существует.")
#         return

#     quiz = data.get(quiz_id)
#     if not isinstance(quiz, dict) or "participants" not in quiz:
#         await message.answer("❌ Такого опроса не существует.")
#         return

#     fake_ids = [str(300000001 + i) for i in range(31)]
#     for fid in fake_ids:
#         quiz["participants"][fid] = {
#             "answers": random.sample(range(1, 6), 3)
#         }

#     save_data(data)
#     await message.answer(f"✅ В опрос {quiz_id} добавлены 31 фейковых участника.")


# ====== Принудительная остановка опроса ======
@dp.message(Command("stop_quiz"))
async def stop_quiz(message: types.Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❗ Укажи ID опроса: /stop_quiz ABC123")
        return


    quiz_id = args[1].strip().upper()
    data = load_data()

    if quiz_id not in data or quiz_id == "users":
        await message.answer("❌ Такого опроса не существует.")
        return

    quiz = data.get(quiz_id)
    if not isinstance(quiz, dict) or "participants" not in quiz:
        await message.answer("❌ Такого опроса не существует.")
        return

    if quiz["creator"] != message.from_user.id:
        await message.answer("❗ Только создатель может остановить опрос.")
        return

    if not quiz.get("active", False):
        await message.answer("⚠️ Опрос уже завершён.")
        return

    # Проверяем, есть ли участники с завершенными ответами
    participants = quiz.get("participants", {})
    completed_participants = {uid: p for uid, p in participants.items() if len(p.get("answers", [])) == 3}
    
    # Если нет участников или нет участников с 3 ответами - просто деактивируем опрос
    if not participants or not completed_participants:
        quiz["active"] = False
        save_data(data)
        await message.answer(f"✅ Опрос {quiz_id} остановлен.\n"
                             f"В опросе нет участников с завершенными ответами, поэтому результаты не сформированы.")
        return
    
    # Если есть участники с ответами - используем стандартную логику
    success, error = await check_and_finalize_quiz(quiz_id, force=True)
    if success:
        await message.answer(f"✅ Опрос {quiz_id} остановлен. Результаты отправлены.")
    else:
        await message.answer(error or "❌ Не удалось остановить опрос.")

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
# async def check_and_finalize_quiz(quiz_id):
#     data = load_data()
#     quiz = data[quiz_id]
#     participants = quiz["participants"]

#     if len(participants) == 35 and all(len(p["answers"]) == 3 for p in participants.values()):
#         quiz["active"] = False
#         answers = {uid: set(p["answers"]) for uid, p in participants.items()}
#         groups = make_groups(answers)
#         #groups = make_groups(answers, num_groups=7, group_size=5)

#         result_text = f"📊 Результаты опроса #{quiz_id}:\n\n"
        
#         for i, group in enumerate(groups, 1):
#             result_text += f"Группа {i}:\n"
#             for uid in group:
#                 uid_str = str(uid)
#                 # Получаем имя и фамилию
#                 first_name, last_name = get_user_name(uid)
#                 # Получаем ответы
#                 user_answers = sorted(participants[uid_str]["answers"])
#                 answers_str = ", ".join(map(str, user_answers))
                
#                 # Формируем строку: Имя Фамилия (ответы: 1, 2, 3) [ID: 123456]
#                 if first_name and last_name:
#                     result_text += f"— {first_name} {last_name} (ответы: {answers_str}) [ID: {uid_str}]\n"
#                 else:
#                     result_text += f"— Неизвестный пользователь (ответы: {answers_str}) [ID: {uid_str}]\n"
#             result_text += "\n"
        
#         # Добавляем информацию о вариантах ответов в конце
#         options = quiz.get("options", ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4", "Вариант 5"])
#         result_text += "Варианты ответов:\n"
#         for i, option in enumerate(options, 1):
#             result_text += f"{i}. {option}\n"

#         # Отправляем результаты создателю
#         creator_id = quiz["creator"]
#         await bot.send_message(creator_id, result_text)
#         save_data(data)

async def check_and_finalize_quiz(quiz_id, force=False):
    from collections import Counter

    data = load_data()
    quiz = data.get(quiz_id)
    if quiz_id == "users" or not isinstance(quiz, dict) or "participants" not in quiz:
        return False, "❌ Такого опроса не существует."

    participants = quiz["participants"]
    if not participants:
        return False, "⚠️ В опросе нет участников."

    if force:
        completed = {uid: p for uid, p in participants.items() if len(p.get("answers", [])) == 3}
        if not completed:
            return False, "⚠️ Ни один участник ещё не дал 3 ответа."
    else:
        if len(participants) != TARGET_PARTICIPANTS or not all(len(p.get("answers", [])) == 3 for p in participants.values()):
            return False, None
        completed = participants

    quiz["active"] = False

    answers = {uid: p["answers"] for uid, p in completed.items()}
    group_plan = DEFAULT_GROUP_SIZES if len(completed) == sum(DEFAULT_GROUP_SIZES) else None
    groups = make_groups(answers, group_size=5, group_sizes=group_plan)
    option_texts = quiz.get("options", ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4", "Вариант 5"])

    def answer_num_to_text(choice: int) -> str:
        idx = choice - 1
        if 0 <= idx < len(option_texts):
            return option_texts[idx]
        return f"Вариант {choice}"

    result_text = f"📊 Результаты опроса #{quiz_id}:\n\n"
    for i, group in enumerate(groups, 1):
        result_text += f"Группа {i}:\n"
        group_first_answers = []
        group_second_answers = []
        group_third_answers = []
        for participant_num, uid in enumerate(group, 1):
            uid_str = str(uid)
            first_name, last_name = get_user_name(uid)
            user_answers = completed[uid_str]["answers"]
            answer_texts = [answer_num_to_text(ans) for ans in user_answers]
            answers_str = ", ".join(answer_texts)
            if len(user_answers) >= 1:
                group_first_answers.append(answer_num_to_text(user_answers[0]))
            if len(user_answers) >= 2:
                group_second_answers.append(answer_num_to_text(user_answers[1]))
            if len(user_answers) >= 3:
                group_third_answers.append(answer_num_to_text(user_answers[2]))

            if first_name and last_name:
                result_text += f"{participant_num}) {first_name} {last_name} ({answers_str}) [ID: {uid_str}]\n"
            else:
                result_text += f"{participant_num}) Неизвестный пользователь ({answers_str}) [ID: {uid_str}]\n"
        # result_text += "\n  Повторы вариантов ответа (в группе):\n"
        # result_text += f"    1-й ответ: {dict(Counter(group_first_answers))}\n"
        # result_text += f"    2-й ответ: {dict(Counter(group_second_answers))}\n"
        # result_text += f"    3-й ответ: {dict(Counter(group_third_answers))}\n"
        result_text += "\n"

    if force and len(completed) < len(participants):
        skipped = len(participants) - len(completed)
        result_text += f"⚠️ {skipped} участника(ов) не завершили ответы и не попали в группы.\n\n"

    # options = quiz.get("options", ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4", "Вариант 5"])
    # result_text += "Варианты ответов:\n"
    # for i, option in enumerate(options, 1):
    #     result_text += f"{i}. {option}\n"

    creator_id = quiz["creator"]
    await bot.send_message(creator_id, result_text)
    save_data(data)
    return True, None


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



import os
import telebot
import requests
import json
import time
import logging
import signal
import sys
from gtts import gTTS  # Добавлен импорт для TTS

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Ваш API ключ для нейросети
API_KEY = os.environ['API_KEY']

# Токен бота Telegram
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']

# Включение TTS (True/False)
ENABLE_TTS = True

# Максимальная длина запроса пользователя
MAX_USER_INPUT_LENGTH = 2000

# Максимальная длина текста для TTS
MAX_TTS_LENGTH = 3000

# Внутренний промпт (роль/инструкция для нейросети)
SYSTEM_PROMPT = "Ты дружелюбный помощник, отвечающий коротко и ясно."

# URL API нейросети
API_URL = "https://openrouter.ai/api/v1/chat/completions"   

# Модель нейросети
MODEL_NAME = "deepseek/deepseek-chat:free"

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Флаг для завершения работы бота
stop_event = False

# Обработчик сигнала завершения
def signal_handler(sig, frame):
    global stop_event
    if not stop_event:
        logging.info("Получен сигнал завершения. Остановка бота...")
        stop_event = True
    else:
        logging.warning("Повторный сигнал завершения. Принудительное завершение работы.")
        sys.exit(1)

# Устанавливаем обработчик сигнала завершения
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def generate_tts(text: str, chat_id: int) -> str:
    """Генерирует аудиофайл из текста и возвращает путь к файлу."""
    try:
        # Проверяем длину текста
        if len(text) > MAX_TTS_LENGTH:
            logging.warning(f"Текст слишком длинный для TTS ({len(text)} символов)")
            return None

        # Создаем уникальное имя файла
        filename = f"tts_{chat_id}_{int(time.time())}.mp3"
        
        # Генерируем аудио
        tts = gTTS(text=text, lang='ru', slow=False)
        tts.save(filename)
        return filename
    except Exception as e:
        logging.error(f"Ошибка генерации TTS: {str(e)}")
        return None

def create_main_menu_markup():
    """Создает клавиатуру с основным меню."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = telebot.types.KeyboardButton("Обычный режим")
    item2 = telebot.types.KeyboardButton("Поиск узких мест")
    markup.add(item1, item2)
    return markup

def create_diagnostic_questions(chat_id):
    """Создает словарь для хранения вопросов и ответов пользователя."""
    questions = [
        "Что ты хочешь? Какой результат ты хочешь получить через время? Выбери дистанцию: 3 месяца, полгода, год, три года или 5 лет. И пиши именно о том, что хочешь получить! Важно, ещё раз: что хочешь получить, а не от чего-то избавиться.",
        "Что есть сейчас? Из какой точки ты начинаешь свой путь? Проведи 'инвентаризацию'. Какие у тебя ресурсы? Что тебя поддерживает? Какие состояния преобладают (какие эмоции 'фонят')? Знания? Навыки? Люди?",
        "Что мешает получить желаемое? Если ты самостоятельно будешь составлять список препятствий, которые тебе не дают двигаться к цели, что ты напишешь в таком списке?",
        "На сколько срочно нужен результат?",
        "Что ты уже пробовал(а) делать, чтобы решить проблему - получить желаемое?"
    ]
    user_data[chat_id] = {"questions": questions, "answers": [], "current_question_index": 0}
    send_next_question(chat_id)

def send_next_question(chat_id):
    """Отправляет следующий вопрос пользователю."""
    data = user_data[chat_id]
    current_question_index = data["current_question_index"]
    if current_question_index < len(data["questions"]):
        question = data["questions"][current_question_index]
        bot.send_message(chat_id, question)
    else:
        process_diagnostic_answers(chat_id)

def process_diagnostic_answers(chat_id):
    """Обрабатывает собранные ответы и отправляет запрос к нейросети."""
    data = user_data[chat_id]
    answers = data["answers"]
    prompt = (
        "Роль для нейросети: Мастер-коуч и психотерапевт.\n"
        "Контекст:\n"
        f"1. Что ты хочешь: {answers[0]}\n"
        f"2. Что есть сейчас: {answers[1]}\n"
        f"3. Что мешает получить желаемое: {answers[2]}\n"
        f"4. На сколько срочно нужен результат: {answers[3]}\n"
        f"5. Что ты уже пробовал(а) делать: {answers[4]}\n"
        "Задача: одним сообщением, ёмко и лаконично, помочь пользователю увидеть узкие места и точки роста в его ситуации."
    )
    
    try:
        # Отправляем запрос к нейросети
        response = requests.post(
            url=API_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            data=json.dumps({
                "model": MODEL_NAME,  # модель
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
        )

        if response.status_code == 200:
            data = response.json()
            reply = data['choices'][0]['message']['content']
        else:
            error_message = f"Произошла ошибка при обращении к нейросети. Код состояния: {response.status_code}"
            try:
                error_details = response.json().get('error', 'Детали ошибки недоступны')
                error_message += f". Детали: {error_details}"
            except json.JSONDecodeError:
                error_message += ". Не удалось декодировать ответ сервера."
            logging.error(error_message)
            reply = error_message
    except Exception as e:
        error_message = f"Произошла ошибка при обработке запроса: {str(e)}"
        logging.error(error_message)
        reply = error_message

    # Отправляем ответ пользователю как обычное сообщение
    bot.send_message(chat_id, reply)

    # Генерация и отправка аудио, если TTS включен
    if ENABLE_TTS and reply:
        try:
            audio_file = generate_tts(reply, chat_id)
            if audio_file:
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(
                        chat_id=chat_id,
                        voice=audio
                    )
                # Удаляем временный файл
                os.remove(audio_file)
        except Exception as e:
            logging.error(f"Ошибка при обработке TTS: {str(e)}")

    # Очищаем данные пользователя и возвращаемся в обычный режим
    del user_data[chat_id]
    bot.send_message(chat_id, "Диагностический сценарий завершен. Вы вернулись в обычный режим.", reply_markup=create_main_menu_markup())

# Хранилище данных пользователей
user_data = {}

# === ОБРАБОТЧИК СООБЩЕНИЙ ===

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Отправляет приветственное сообщение и меню."""
    markup = create_main_menu_markup()
    bot.send_message(message.chat.id, "Добро пожаловать! Выберите режим:", reply_markup=markup)

@bot.message_handler(commands=['menu'])
def show_menu(message):
    """Отображает меню."""
    markup = create_main_menu_markup()
    bot.send_message(message.chat.id, "Выберите режим:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Обычный режим")
def normal_mode(message):
    """Обрабатывает выбор обычного режима."""
    bot.send_message(message.chat.id, "Вы выбрали обычный режим.", reply_markup=create_main_menu_markup())

@bot.message_handler(func=lambda message: message.text == "Поиск узких мест")
def diagnostic_mode(message):
    """Запускает диагностический сценарий."""
    create_diagnostic_questions(message.chat.id)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if stop_event:
        return

    chat_id = message.chat.id
    user_text = message.text

    # Проверка длины запроса
    if len(user_text) > MAX_USER_INPUT_LENGTH:
        bot.send_message(chat_id, f"Пожалуйста, сократите ваш запрос до {MAX_USER_INPUT_LENGTH} символов или меньше.")
        return

    if chat_id in user_data:
        # Обработка ответов на вопросы диагностики
        data = user_data[chat_id]
        current_question_index = data["current_question_index"]
        if current_question_index < len(data["questions"]):
            data["answers"].append(user_text)
            data["current_question_index"] += 1
            send_next_question(chat_id)
    else:
        # Обычный режим
        # Отправляем сообщение "Думаю..."
        think_message = bot.send_message(chat_id, "Думаю...")

        try:
            # Отправляем запрос к нейросети
            response = requests.post(
                url=API_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                data=json.dumps({
                    "model": MODEL_NAME,  # модель
                    "messages": [
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": user_text
                        }
                    ]
                })
            )

            if response.status_code == 200:
                data = response.json()
                reply = data['choices'][0]['message']['content']
            else:
                error_message = f"Произошла ошибка при обращении к нейросети. Код состояния: {response.status_code}"
                try:
                    error_details = response.json().get('error', 'Детали ошибки недоступны')
                    error_message += f". Детали: {error_details}"
                except json.JSONDecodeError:
                    error_message += ". Не удалось декодировать ответ сервера."
                logging.error(error_message)
                reply = error_message
        except Exception as e:
            error_message = f"Произошла ошибка при обработке запроса: {str(e)}"
            logging.error(error_message)
            reply = error_message

        # Удаляем сообщение "Думаю..."
        try:
            bot.delete_message(chat_id=chat_id, message_id=think_message.message_id)
        except telebot.apihelper.ApiTelegramException as e:
            if e.result.status_code == 400 and "Message to delete not found" in e.result.description:
                logging.warning(f"Сообщение {think_message.message_id} уже удалено или не существует.")
            else:
                logging.error(f"Ошибка при удалении сообщения: {str(e)}")

        # Отправляем ответ пользователю как обычное сообщение
        sent_message = bot.send_message(chat_id, reply)

        # Генерация и отправка аудио, если TTS включен
        if ENABLE_TTS and reply:
            try:
                audio_file = generate_tts(reply, chat_id)
                if audio_file:
                    with open(audio_file, 'rb') as audio:
                        bot.send_voice(
                            chat_id=chat_id,
                            voice=audio
                        )
                    # Удаляем временный файл
                    os.remove(audio_file)
            except Exception as e:
                logging.error(f"Ошибка при обработке TTS: {str(e)}")

# === ЗАПУСК БОТА ===

# Оборачивание polling в цикл с обработкой ошибок
def start_bot():
    while not stop_event:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            if not stop_event:
                logging.error(f"Ошибка polling: {str(e)}")
                time.sleep(5)  # задержка перед повторным запуском
            else:
                logging.info("Завершение работы бота после ошибки polling.")
                break

if __name__ == '__main__':
    try:
        start_bot()
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем.")
    except Exception as e:
        logging.error(f"Неожиданная ошибка: {str(e)}")
    finally:
        logging.info("Завершение работы бота.")
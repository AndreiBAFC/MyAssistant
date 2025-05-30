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

# === ОБРАБОТЧИК СООБЩЕНИЙ ===

def create_menu_markup():
    """Создает клавиатуру с основным меню."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = telebot.types.KeyboardButton("Обычный режим")
    item2 = telebot.types.KeyboardButton("Меню")
    markup.add(item1, item2)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Отправляет приветственное сообщение и меню."""
    markup = create_menu_markup()
    bot.send_message(message.chat.id, "Добро пожаловать! Выберите режим:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Меню")
def show_menu(message):
    """Отображает меню."""
    markup = create_menu_markup()
    bot.send_message(message.chat.id, "Выберите режим:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Обычный режим")
def normal_mode(message):
    """Обрабатывает выбор обычного режима."""
    bot.send_message(message.chat.id, "Вы выбрали обычный режим.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if stop_event:
        return

    user_text = message.text

    # Проверка длины запроса
    if len(user_text) > MAX_USER_INPUT_LENGTH:
        bot.send_message(message.chat.id, f"Пожалуйста, сократите ваш запрос до {MAX_USER_INPUT_LENGTH} символов или меньше.")
        return

    # Отправляем сообщение "Думаю..."
    think_message = bot.send_message(message.chat.id, "Думаю...")

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
        bot.delete_message(chat_id=message.chat.id, message_id=think_message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        if e.result.status_code == 400 and "Message to delete not found" in e.result.description:
            logging.warning(f"Сообщение {think_message.message_id} уже удалено или не существует.")
        else:
            logging.error(f"Ошибка при удалении сообщения: {str(e)}")

    # Отправляем ответ пользователю как обычное сообщение
    sent_message = bot.send_message(message.chat.id, reply)

    # Генерация и отправка аудио, если TTS включен
    if ENABLE_TTS and reply:
        try:
            audio_file = generate_tts(reply, message.chat.id)
            if audio_file:
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(
                        chat_id=message.chat.id,
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
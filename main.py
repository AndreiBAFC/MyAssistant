import telebot
import requests
import json
import time
import logging
import signal
import sys

# === НАСТРОЙКИ ===

# Ваш API ключ для нейросети
API_KEY = "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"

# Токен бота Telegram
TELEGRAM_BOT_TOKEN = "7073263117:AAGwslDCKQlMApXDa3kXvNG5pI1iDh2d9AY"

# Максимальная длина запроса пользователя
MAX_USER_INPUT_LENGTH = 2000

# Внутренний промпт (роль/инструкция для нейросети)
SYSTEM_PROMPT = "Ты дружелюбный помощник, отвечающий коротко и ясно."

# URL API нейросети
API_URL = "https://openrouter.ai/api/v1/chat/completions"  # Удалён лишний пробел

# Модель нейросети
MODEL_NAME = "deepseek/deepseek-chat:free"

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === ИНИЦИАЛИЗАЦИЯ ===

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

# === ОБРАБОТЧИК СООБЩЕНИЙ ===

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if stop_event:
        return

    user_text = message.text

    # Проверка длины запроса
    if len(user_text) > MAX_USER_INPUT_LENGTH:
        bot.reply_to(message, f"Пожалуйста, сократите ваш запрос до {MAX_USER_INPUT_LENGTH} символов или меньше.")
        return

    # Отправляем сообщение "Думаю..." и сохраняем его ID
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

    # Отправляем ответ пользователю
    bot.reply_to(message, reply)

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
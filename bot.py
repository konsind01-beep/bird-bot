import os
import telebot
from google import genai
from google.genai import types

# Получаем ключи из переменных окружения Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Инициализируем бота и клиент Gemini
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
  bot.reply_to(
      message,
      "Привет! Отправь мне фотографию птицы, и я постараюсь её определить.",
  )


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
  try:
    bot.reply_to(
        message, "Анализирую фотографию, пожалуйста, подождите..."
    )

    # Получаем файл фотографии наилучшего качества
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    # Сохраняем во временный файл
    temp_filename = "temp_bird.jpg"
    with open(temp_filename, "wb") as new_file:
      new_file.write(downloaded_file)

    # Загружаем файл в Gemini с помощью Files API
    uploaded_file = client.files.upload(file=temp_filename)

    # Запрашиваем анализ у модели gemini-2.5-flash
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            uploaded_file,
            (
                "Какая птица изображена на фото? Напиши её название на русском"
                " языке, английском и кратко опиши её особенности."
            ),
        ],
    )

    # Отправляем ответ пользователю
    bot.reply_to(message, response.text)

    # Удаляем локальный файл
    if os.path.exists(temp_filename):
      os.remove(temp_filename)

  except Exception as e:
    bot.reply_to(message, f"Произошла ошибка при обработке: {e}")


# Запуск бесконечного опроса сервера Telegram
if __name__ == "__main__":
  bot.infinity_polling()

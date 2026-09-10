import aiohttp
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from google import genai
from google.genai import types as genai_types

# Берем ключи из переменных окружения (безопасно для облака)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8913610474:AAFJwWes1S3vIcX2-_WyB-y4onu_4eO_DkI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "ВАШ_GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_API_KEY)


def init_db():
  conn = sqlite3.connect("lifelist.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS lifelist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name_ru TEXT,
            name_en TEXT,
            migration TEXT,
            is_predator TEXT,
            diet TEXT,
            habitat TEXT,
            fact TEXT,
            user_photo_id TEXT,
            stock_photo_url TEXT,
            latitude REAL,
            longitude REAL,
            date TEXT
        )
    """)
  conn.commit()
  conn.close()


init_db()


async def get_stock_bird_photo(bird_name_en: str) -> str:
  url = "https://commons.wikimedia.org/w/api.php"
  params = {
      "action": "query",
      "generator": "search",
      "gsrsearch": f"{bird_name_en} bird",
      "gsrnamespace": "6",
      "gsrlimit": "1",
      "prop": "imageinfo",
      "iiprop": "url",
      "format": "json",
  }
  async with aiohttp.ClientSession() as session:
    async with session.get(url, params=params) as response:
      data = await response.json()
      pages = data.get("query", {}).get("pages", {})
      for page_id in pages:
        image_info = pages[page_id].get("imageinfo", [])
        if image_info:
          return image_info[0].get("url")
  return None


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  await message.answer(
      "Привет! 🦅 Я твой полевой гид по птицам Калифорнии.\n\n"
      "📸 **Как пользоваться:**\n"
      "Отправь фото птицы (желательно с геолокацией 📍). Я сохраню твой кадр,"
      " найду эталонное фото из стока, соберу справку и занесу находку в Life"
      " List!\n\n"
      "📜 **Команды:**\n"
      "/list — Посмотреть твои находки\n"
      "/map — Открыть карту твоих встреч с птицами"
  )


@dp.message(F.photo)
async def handle_bird_photo(message: types.Message):
  lat = message.location.latitude if message.location else None
  lon = message.location.longitude if message.location else None

  await message.answer(
      "🔍 Анализирую твое фото, ищу эталон в базе и собираю орнитологическую"
      " справку..."
  )

  user_photo_id = message.photo[-1].file_id
  file_info = await bot.get_file(user_photo_id)
  downloaded_file = await bot.download_file(file_info.file_path)

  prompt = (
      "Ты эксперт-орнитолог по дикой природе Калифорнии. Определи вид птицы на"
      " этом фото. Выдай ответ СТРОГО в следующем формате:\n"
      "RUS_NAME: [Название на русском]\n"
      "ENG_NAME: [Название на английском]\n"
      "MIGRATION: [Оседлая / Перелетная / Кочующая]\n"
      "PREDATOR: [Да / Нет]\n"
      "DIET: [Чем питается]\n"
      "HABITAT: [Среда обитания в Калифорнии]\n"
      "FACT: [Краткий интересный факт, 2 предложения]"
  )

  response = client.models.generate_content(
      model="gemini-2.5-flash",
      contents=[
          genai_types.Part.from_bytes(
              data=downloaded_file.read(), mime_type="image/jpeg"
          ),
          prompt,
      ],
  )

  text = response.text
  data = {}
  for line in text.split("\n"):
    if ":" in line:
      key, val = line.split(":", 1)
      data[key.strip()] = val.strip()

  name_ru = data.get("RUS_NAME", "Неизвестная птица")
  name_en = data.get("ENG_NAME", "Unknown bird")
  migration = data.get("MIGRATION", "Не указано")
  is_predator = data.get("PREDATOR", "Нет")
  diet = data.get("DIET", "Не указано")
  habitat = data.get("HABITAT", "Не указано")
  fact = data.get("FACT", "")

  stock_photo_url = await get_stock_bird_photo(name_en)

  conn = sqlite3.connect("lifelist.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO lifelist (user_id, name_ru, name_en, migration, is_predator, diet, habitat, fact, user_photo_id, stock_photo_url, latitude, longitude, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """,
      (
          message.from_user.id,
          name_ru,
          name_en,
          migration,
          is_predator,
          diet,
          habitat,
          fact,
          user_photo_id,
          stock_photo_url,
          lat,
          lon,
      ),
  )
  conn.commit()
  conn.close()

  geo_info = f"\n📍 Координаты: {lat}, {lon}" if lat and lon else ""
  await message.answer_photo(
      photo=user_photo_id,
      caption=(
          f"📸 **Твой кадр с прогулки!**{geo_info}\nПтица успешно добавлена в"
          " Life List."
      ),
  )

  reply_text = (
      f"🎯 **{name_ru}** / *{name_en}*\n\n"
      f"🌍 **Статус:** {migration}\n"
      f"🦅 **Хищная:** {is_predator}\n"
      f"🐛 **Рацион:** {diet}\n"
      f"🌳 **Среда обитания:** {habitat}\n\n"
      f"💡 *Факты:* {fact}"
  )

  if stock_photo_url:
    await message.answer_photo(
        photo=stock_photo_url,
        caption=f"✨ **Эталонный вид из стока для сравнения:**\n\n{reply_text}",
    )
  else:
    await message.answer(reply_text)


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
  conn = sqlite3.connect("lifelist.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT name_ru, name_en, habitat, date FROM lifelist WHERE user_id = ?",
      (message.from_user.id,),
  )
  records = cursor.fetchall()
  conn.close()

  if not records:
    await message.answer(
        "Ваш Life List пока пуст. Отправьте фото птицы с прогулки!"
    )
    return

  text = "📖 **Ваш персональный Life List (Калифорния):**\n\n"
  for idx, rec in enumerate(records, 1):
    text += (
        f"{idx}. **{rec[0]}** (*{rec[1]}*)\n"
        f"   - Место: {rec[2]} | Дата: {rec[3]}\n\n"
    )

  await message.answer(text)


@dp.message(Command("map"))
async def cmd_map(message: types.Message):
  conn = sqlite3.connect("lifelist.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT latitude, longitude, name_ru FROM lifelist WHERE user_id = ? AND"
      " latitude IS NOT NULL",
      (message.from_user.id,),
  )
  records = cursor.fetchall()
  conn.close()

  if not records:
    await message.answer(
        "У вас пока нет сохраненных точек с геолокацией. Прикрепляйте геопозицию"
        " при отправке фото птиц!"
    )
    return

  text = (
      "🗺 **Карта ваших орнитологических открытий в Калифорнии:**\n\n"
      "Сохраненные координаты точек встреч:\n"
  )
  for lat, lon, name in records:
    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    text += f"• [{name}]({maps_link}) ({lat:.4f}, {lon:.4f})\n"

  text += (
      "\nНажмите на название птицы в списке, чтобы открыть точное место на"
      " карте!"
  )
  await message.answer(
      text, disable_web_page_preview=True, parse_mode="Markdown"
  )


async def main():
  await dp.start_polling(bot)


if __name__ == "__main__":
  import asyncio

  asyncio.run(main())

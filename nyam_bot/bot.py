import logging
import os
import asyncio
from datetime import datetime
from typing import Dict
from collections import defaultdict

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

from .config import TELEGRAM_BOT_TOKEN, FREE_DAILY_LIMIT
from .claude_vision import analyze_food_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

user_limits: Dict[int, Dict] = defaultdict(lambda: {"count": 0, "date": ""})


def format_response(data: dict) -> str:
    cal = data.get("calories_per_100g", 100)
    weight = data.get("total_weight_g", 100)
    return f"🍽 {data.get('dish_name','Еда')}\n📊 {int(cal*weight/100)} ккал\n⚖️ {weight}г"


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🍕 Нямнямчик\n\nОтправь фото еды!")


@dp.message()
async def handle_message(message: types.Message):
    uid = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_limits[uid]["date"] != today:
        user_limits[uid] = {"count": 0, "date": today}
    
    if message.photo:
        if user_limits[uid]["count"] >= FREE_DAILY_LIMIT:
            await message.answer("⛔ Лимит 10 фото/день!")
            return
        
        user_limits[uid]["count"] += 1
        
        try:
            photo = message.photo[-1]
            file = await bot.download_file(photo.file_id)
            result = await analyze_food_image(file.read())
            await message.answer(format_response(result))
        except Exception as e:
            logger.exception(e)
            await message.answer(f"Ошибка: {e}")
    else:
        await message.answer("Отправь фото еды!")


async def main():
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

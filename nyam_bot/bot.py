import logging
import os
import asyncio
from aiohttp import web
from datetime import datetime
from typing import Dict, Optional
from collections import defaultdict

from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, Message
from aiogram.filters import Filter

from .config import TELEGRAM_BOT_TOKEN, FREE_DAILY_LIMIT, PRO_DAILY_LIMIT
from .claude_vision import analyze_food_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


class UserState:
    def __init__(self):
        self.daily_counts: Dict[int, Dict[str, int]] = defaultdict(lambda: {"count": 0, "date": ""})
        self.user_tier: Dict[int, str] = {}
    
    def get_limit(self, user_id: int) -> int:
        tier = self.user_tier.get(user_id, "free")
        return PRO_DAILY_LIMIT if tier == "pro" else FREE_DAILY_LIMIT
    
    def can_analyze(self, user_id: int) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        state = self.daily_counts[user_id]
        if state["date"] != today:
            state["count"] = 0
            state["date"] = today
        return state["count"] < self.get_limit(user_id)
    
    def increment(self, user_id: int):
        today = datetime.now().strftime("%Y-%m-%d")
        state = self.daily_counts[user_id]
        if state["date"] != today:
            state["count"] = 0
            state["date"] = today
        state["count"] += 1
    
    def set_tier(self, user_id: int, tier: str):
        self.user_tier[user_id] = tier


user_state = UserState()


def format_food_response(data: dict) -> str:
    dish = data.get("dish_name", "Блюдо")
    cal = data.get("calories_per_100g", 100)
    weight = data.get("total_weight_g", 100)
    total_cal = int(cal * weight / 100)
    protein = data.get("protein_g", 0)
    fat = data.get("fat_g", 0)
    carbs = data.get("carbs_g", 0)
    conf = int(data.get("confidence", 0) * 100)
    
    text = f"🍽 <b>{dish}</b>\n\n"
    text += f"📊 <b>{total_cal}</b> ккал\n"
    text += f"⚖️ {weight} г\n\n"
    text += f"🥩 Б: {protein}г | Ж: {fat}г | У: {carbs}г\n\n"
    text += f"🔍 Уверенность: {conf}%"
    
    if data.get("needs_correction"):
        text += "\n\n⚠️ Точный вес может отличаться. Нажми 'Исправить' для корректировки."
    
    return text


def build_main_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📸 Анализировать", callback_data="action|analyze"),
        InlineKeyboardButton("📊 История", callback_data="action|history"),
    )
    kb.add(
        InlineKeyboardButton("⚙️ Настройки", callback_data="action|settings"),
        InlineKeyboardButton("❓ Помощь", callback_data="action|help"),
    )
    return kb


def build_correct_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✏️ Исправить", callback_data="action|correct"),
        InlineKeyboardButton("🔄 Ещё фото", callback_data="action|retry"),
    )
    return kb


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome = (
        "🍕 <b>Нямнямчик</b> — считай калории по фото!\n\n"
        "Просто отправь мне фото еды, и я посчитаю калории.\n"
        f"Лимит: {FREE_DAILY_LIMIT} фото/день (бесплатно)\n\n"
        "Команды:\n"
        "/start — Главное меню\n"
        "/menu — Клавиатура\n"
        "/stats — Статистика за день\n"
        "/clear — Очистить историю"
    )
    await message.answer(welcome, reply_markup=build_main_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("Выбери действие:", reply_markup=build_main_keyboard())


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    state = user_state.daily_counts[user_id]
    count = state["count"] if state["date"] == today else 0
    limit = user_state.get_limit(user_id)
    tier = user_state.user_tier.get(user_id, "free")
    
    text = f"📊 <b>Статистика за сегодня</b>\n\n"
    text += f"Проанализировано: {count}/{limit} фото\n"
    text += f"Тариф: {tier.upper()}"
    
    await message.answer(text)


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_state.daily_counts:
        user_state.daily_counts[user_id]["count"] = 0
    await message.answer("✅ История очищена!")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "ℹ️ <b>Как это работает</b>\n\n"
        "1. Отправь мне фото еды\n"
        "2. Я распознаю блюдо и посчитаю калории\n"
        "3. При необходимости исправь вес\n\n"
        "💡 <b>Советы для точности:</b>\n"
        "- Хорошее освещение\n"
        "- Фокус на еде\n"
        "- Видна тарелка или ложка для оценки порции\n\n"
        "📷 Фото делай с одного ракурса — сверху."
    )
    await message.answer(help_text)


class PhotoFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.photo is not None


@router.message(PhotoFilter())
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    
    if not user_state.can_analyze(user_id):
        limit = user_state.get_limit(user_id)
        await message.answer(
            f"⛔ Лимит исчерпан ({limit} фото/день)\n\n"
            "Купи подписку для безлимитного анализа.",
            reply_markup=build_main_keyboard()
        )
        return
    
    user_state.increment(user_id)
    
    processing = await message.answer("⏳ Анализирую...")
    
    try:
        photo = message.photo[-1]
        file = await bot.download_file(file_id=photo.file_id)
        image_data = file.read()
        
        result = await analyze_food_image(image_data)
        
        text = format_food_response(result)
        
        await message.answer(text, reply_markup=build_correct_keyboard())
        
    except Exception as e:
        logger.exception(e)
        await message.answer(f"���️ ��шибка: {str(e)[:200]}")
    
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing.message_id)
    except:
        pass


@router.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    action = callback.data.split("|")[1]
    
    if action == "analyze":
        await callback.answer("📸 Отправь мне фото еды!")
    
    elif action == "history":
        await callback.answer("📊 История скоро появится!", show_alert=True)
    
    elif action == "settings":
        await callback.answer("⚙️ Настройки скоро!", show_alert=True)
    
    elif action == "help":
        await callback.message.answer(
            "ℹ️ <b>Как это работает</b>\n\n"
            "1. Отправь фото еды\n"
            "2. Получи калории\n"
            "3. Исправь при needed"
        )
    
    elif action == "correct":
        await callback.answer("✏️ Введи вес в граммах:")
    
    elif action == "retry":
        await callback.answer("📸 Жду фото!")
    
    else:
        await callback.answer("Команда неизвестна", show_alert=True)
    
    await callback.answer()


@router.message()
async def handle_text(message: types.Message):
    text = message.text.strip()
    
    if text.isdigit():
        weight = int(text)
        if 1 <= weight <= 2000:
            await message.answer(f"✅ Вес установлен: {weight}г\nОтправь фото для пересчёта.")
            return
    
    await message.answer(
        "Отправь фото еды или используй /menu",
        reply_markup=build_main_keyboard()
    )


def main():
    from aiohttp import web
    
    async def handle(request):
        return web.Response(text="Bot is running!")
    
    app = web.Application()
    app.router.add_get("/", handle)
    
    runner = web.AppRunner(app)
    asyncio.run(runner.setup())
    
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    site.start()
    
    logger.info("Starting NyamNyamchik Bot on web...")
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    main()
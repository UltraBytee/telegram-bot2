from telethon.sync import TelegramClient
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import Channel, Chat, User
from aiogram import Bot, Dispatcher, types, executor
import asyncio
from datetime import datetime
import pandas as pd
from collections import Counter

# --- Sozlamalar ---
import os

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Telethon va Aiogram obyektlari ---
telethon_client = TelegramClient('session_name', API_ID, API_HASH)
bot = Bot(token=BOT_TOKEN)

# --- State boshqaruvi uchun FSM (FormStateManagement) ---
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

class UserState(StatesGroup):
    waiting_for_username = State()
    waiting_for_option = State()
    waiting_for_group = State()
    waiting_for_stats_option = State()

# --- Statistika ma'lumotlarini to'plash ---
async def collect_stats(group_username, user):
    data = []
    async with telethon_client:
        async for msg in telethon_client.iter_messages(group_username, from_user=user):
            if msg.text:
                data.append({
                    'text': msg.text,
                    'date': msg.date
                })
    return pd.DataFrame(data)

# --- Statistikalar ---
def basic_statistics(df):
    total = len(df)
    by_day = df['date'].dt.day_name().value_counts().to_dict()
    by_hour = df['date'].dt.hour.value_counts().sort_index().to_dict()
    words = Counter(' '.join(df['text']).split()).most_common(10)
    return total, by_day, by_hour, words

# --- Foydalanuvchini tekshirish va maʼlumot olish ---
async def check_user_exists(identifier):
    async with telethon_client:
        try:
            if identifier.isdigit():
                identifier = int(identifier)
            user = await telethon_client.get_entity(identifier)
            if isinstance(user, User):
                name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                profile_photo = await telethon_client.download_profile_photo(user, file=bytes)
                user_id = user.id
                username = user.username or "Yo'q"
                phone = user.phone or "Nomaʼlum"
                bot_status = "Ha" if user.bot else "Yo'q"
                bio = getattr(user, 'about', 'Yoʻq')
                birth_date = getattr(user, 'birth_date', 'Mavjud emas')
                personal_link = f"https://t.me/{username}" if username != "Yo'q" else "Mavjud emas"
                return {
                    "name": name,
                    "photo": profile_photo,
                    "username": username,
                    "id": user_id,
                    "phone": phone,
                    "bot": bot_status,
                    "bio": bio,
                    "birth_date": birth_date,
                    "personal_link": personal_link,
                    "entity": user
                }
        except:
            return None

# --- Foydalanuvchi qaysi kanallarda borligini aniqlash ---
async def find_user_chats(user_entity):
    found = []
    async with telethon_client:
        dialogs = await telethon_client.get_dialogs()
        for dialog in dialogs:
            entity = dialog.entity
            try:
                participants = await telethon_client.get_participants(entity, limit=100)
                if any(p.id == user_entity.id for p in participants):
                    found.append(dialog.title or getattr(entity, 'username', 'Nomaʼlum'))
            except:
                continue
    return found

# --- Inline tugmalar ishlovchilari ---
@dp.callback_query_handler(lambda c: c.data == 'view_groups', state=UserState.waiting_for_option)
async def handle_view_groups(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    data = await state.get_data()
    user_entity = data['user_entity']
    await bot.send_message(callback_query.from_user.id, "🔍 Foydalanuvchi guruhlari aniqlanmoqda...")
    groups = await find_user_chats(user_entity)
    if groups:
        await bot.send_message(callback_query.from_user.id, "👥 A'zo bo‘lgan guruh/kanallar:\n" + '\n'.join(f"• {g}" for g in groups))
    else:
        await bot.send_message(callback_query.from_user.id, "❌ Hech qanday guruh yoki kanal topilmadi.")
    await state.finish()

# --- Start komandasi ---
@dp.message_handler(commands=['start'], state="*")
async def start_handler(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "👋 Salom! Men Telegram guruhlaridagi foydalanuvchi xabarlarini ko‘rish va statistikani chiqarishga yordam beraman.\n\n"
        "👨‍💻 Men janob Behruz tomonidan yaratildim va faqat yaxshilik uchun ishlatiladi.\n\n"
        "📌 Foydalanuvchining username yoki ID raqamini kiriting:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await UserState.waiting_for_username.set()

# --- Foydalanuvchi haqida ma'lumot ---
@dp.message_handler(state=UserState.waiting_for_username)
async def get_username(message: types.Message, state: FSMContext):
    identifier = message.text.strip()
    user_data = await check_user_exists(identifier)
    if not user_data:
        await message.answer("🚫 Bunday foydalanuvchi topilmadi yoki username/ID noto‘g‘ri.")
        return

    await state.update_data(username=user_data['username'], user_entity=user_data['entity'])

    caption = (
        f"🔍 Qidirilayotgan foydalanuvchi: {user_data['name']}\n"
        f"🆔 ID: {user_data['id']}\n"
        f"🔗 Username: @{user_data['username']}\n"
        f"📞 Telefon: {user_data['phone']}\n"
        f"🤖 Bot: {user_data['bot']}\n"
        f"🗓 Tug‘ilgan sana: {user_data['birth_date']}\n"
        f"🔗 Shaxsiy kanali: {user_data['personal_link']}\n"
        f"✍️ Bio: {user_data['bio']}"
    )

    await bot.send_photo(message.chat.id, user_data['photo'], caption=caption)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✍️ Guruh usernamesini qo‘lda kiritish", callback_data="manual_group"),
        types.InlineKeyboardButton("👥 Bor guruh/kanallarni ko‘rish", callback_data="view_groups"),
        types.InlineKeyboardButton("📊 Statistikani ko‘rish", callback_data="view_stats")
    )

    await message.answer("🔘 Tanlang:", reply_markup=keyboard)
    await UserState.waiting_for_option.set()

# --- Inline tugmalar ishlovchilari ---
@dp.callback_query_handler(lambda c: c.data == 'manual_group', state=UserState.waiting_for_option)
async def handle_manual_group(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, "✍️ Guruh usernamesini kiriting (masalan: @examplegroup):")
    await UserState.waiting_for_group.set()

@dp.callback_query_handler(lambda c: c.data == 'view_groups', state=UserState.waiting_for_option)
async def handle_view_groups(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, "⚠️ Bu funksiya hozircha ishlamaydi. Tez orada qo‘shiladi.")

@dp.callback_query_handler(lambda c: c.data == 'view_stats', state=UserState.waiting_for_option)
async def handle_view_stats(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, "📊 Statistika uchun guruh usernamesini kiriting (masalan: @examplegroup):")
    await UserState.waiting_for_stats_option.set()

# --- Statistika chiqarish ---
@dp.message_handler(state=UserState.waiting_for_stats_option)
async def stats_handler(message: types.Message, state: FSMContext):
    group_username = message.text.strip()
    data = await state.get_data()
    user_entity = data.get("user_entity")

    await message.answer("📊 Statistika yig‘ilmoqda...")
    df = await collect_stats(group_username, user_entity)

    if df.empty:
        await message.answer("❌ Bu foydalanuvchi tomonidan hech qanday xabar topilmadi.")
        return

    total, by_day, by_hour, words = basic_statistics(df)

    day_stat = '\n'.join([f"📅 {k}: {v} ta" for k, v in by_day.items()])
    hour_stat = '\n'.join([f"🕓 {k}:00 - {v} ta" for k, v in by_hour.items()])
    word_stat = '\n'.join([f"🔤 {w}: {c} marta" for w, c in words])

    result = (
        f"📊 Umumiy statistika:\n"
        f"📝 Jami xabarlar: {total} ta\n\n"
        f"📅 Kunlar bo‘yicha:\n{day_stat}\n\n"
        f"🕓 Soatlar bo‘yicha:\n{hour_stat}\n\n"
        f"🔡 Eng ko‘p ishlatilgan so‘zlar:\n{word_stat}"
    )

    await message.answer(result)
    await state.finish()

# --- Xabarlarni chiqarish ---
async def get_user_messages(group_username, user_entity):
    messages = []
    async with telethon_client:
        async for message in telethon_client.iter_messages(group_username, from_user=user_entity):
            if message.text:
                time_str = message.date.strftime("%d.%m.%Y %H:%Mda")
                link = f"https://t.me/{group_username.lstrip('@')}/{message.id}"
                messages.append(f"{message.text} ({time_str})\n👉 [Havola]({link})")
                if len(messages) >= 10:
                    break
    return messages or ["Xabar topilmadi."]

@dp.message_handler(state=UserState.waiting_for_group)
async def get_group(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_entity = data['user_entity']
    group_username = message.text.strip()

    await message.answer("📥 Xabarlar olinmoqda...")
    result_messages = await get_user_messages(group_username, user_entity)

    batch = ""
    for msg in result_messages:
        if len(batch) + len(msg) > 4000:
            await message.answer(batch, parse_mode='Markdown', disable_web_page_preview=True)
            batch = ""
        batch += msg + "\n\n"
    if batch:
        await message.answer(batch, parse_mode='Markdown', disable_web_page_preview=True)

    await state.finish()

if __name__ == '__main__':
    from aiogram import executor

    executor.start_polling(dp, skip_updates=True)

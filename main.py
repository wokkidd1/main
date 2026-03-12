import asyncio
import os
import subprocess
import sqlite3
from datetime import datetime, timedelta
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, FSInputFile, ReplyKeyboardMarkup, 
                           KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, LabeledPrice, PreCheckoutQuery)
from aiogram.filters import Command

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6779188403
SUPPORT_URL = "https://t.me" # ЗАМЕНИ
CHANNEL_URL = "https://t.me"    # ЗАМЕНИ
FREE_LIMIT = 3
PREMIUM_COST = 10 
DB_NAME = "users_data.db"
DOWNLOAD_DIR, RESULT_DIR = "downloads", "results"

for folder in [DOWNLOAD_DIR, RESULT_DIR]:
    if not os.path.exists(folder): os.makedirs(folder)

# --- РАБОТА С БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, downloads INTEGER, 
                    last_reset TEXT, stars INTEGER DEFAULT 0, 
                    is_banned INTEGER DEFAULT 0, premium_until TEXT)''')
    conn.commit()
    conn.close()

init_db()

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(query, params)
    res = None
    if fetchone: 
        row = cur.fetchone()
        res = row if row else None
    elif fetchall: 
        res = cur.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

# --- КЛАВИАТУРЫ (Исправленные скобки) ---
def get_main_kb(user_id):
    kb_list =,
    ]
    if user_id == ADMIN_ID:
        kb_list.append()
    return ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True)

def get_support_kb():
    return InlineKeyboardMarkup(inline_keyboard=,
    ])

def get_balance_kb():
    return InlineKeyboardMarkup(inline_keyboard=,
    ])

# --- ЛОГИКА ОБРАБОТКИ ---
def download_video(url):
    ydl_opts = {'format': 'best[ext=mp4]/best', 'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'noplaylist': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def unique_video(input_path):
    output_path = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    command = ['ffmpeg', '-y', '-i', input_path, '-vf', 'hflip,scale=iw*1.1:-1,crop=iw/1.1:ih/1.1,setpts=0.95*PTS',
               '-af', 'atempo=1.05', '-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', output_path]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return output_path

# --- ОБРАБОТЧИКИ ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    db_query("INSERT OR IGNORE INTO users (user_id, last_reset) VALUES (?, ?)", 
             (message.from_user.id, datetime.now().strftime('%Y-%m-%d')), commit=True)
    await message.answer("🚀 Привет! Я уникализирую видео. Пришли ссылку!", 
                         reply_markup=get_main_kb(message.from_user.id))

# --- ПОЛЬЗОВАТЕЛЬСКОЕ МЕНЮ ---
@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(message: Message):
    await message.answer("🆘 Нужна помощь? Используй кнопки ниже:", reply_markup=get_support_kb())

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message):
    res = db_query("SELECT stars, premium_until FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    stars, prem = (res[0], res[1]) if res else (0, "Нет")
    await message.answer(f"💰 Баланс: `{stars}` 🌟\n⏳ Безлимит: `{prem}`", reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(message: Message):
    res = db_query("SELECT downloads, stars, premium_until FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    used, stars, prem_until = res if res else (0, 0, None)
    is_p = "✅ Да" if prem_until and datetime.strptime(prem_until, '%Y-%m-%d %H:%M') > datetime.now() else "❌ Нет"
    await message.answer(f"👤 Профиль\nID: `{message.from_user.id}`\n🌟 Звезд: {stars}\n🚀 Безлимит: {is_p}\n🎬 Лимит: {used}/{FREE_LIMIT}", parse_mode="Markdown")

# --- ПЛАТЕЖИ ---
@dp.callback_query(F.data == "add_50_stars")
async def buy_stars(call: CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="50 Звезд", description="Пополнение", payload="50", provider_token="", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: Message):
    db_query("UPDATE users SET stars = stars + ? WHERE user_id = ?", (m.successful_payment.total_amount, m.from_user.id), commit=True)
    await bot.send_message(ADMIN_ID, f"💰 Пополнение: {m.from_user.id} на {m.successful_payment.total_amount}")

@dp.callback_query(F.data == "buy_premium")
async def buy_prem(call: CallbackQuery):
    res = db_query("SELECT stars FROM users WHERE user_id = ?", (call.from_user.id,), fetchone=True)
    if res and res[0] >= PREMIUM_COST:
        until = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
        db_query("UPDATE users SET stars = stars - ?, premium_until = ? WHERE user_id = ?", (PREMIUM_COST, until, call.from_user.id), commit=True)
        await call.message.edit_text(f"✅ Безлимит до {until}"); await bot.send_message(ADMIN_ID, f"🚀 Премиум: {call.from_user.id}")
    else: await call.answer("Недостаточно звезд!", show_alert=True)

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(Command("ahelp"))
async def admin_help(m: Message):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("📊 /stats | 📢 /broadcast | 👤 /check [ID] | 💰 /give [ID] | 🚫 /ban [ID]")

@dp.message(F.text == "🛠 Админка")
async def admin_btn(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer("Используй /ahelp для списка команд.")

# --- ОБРАБОТКА ВИДЕО (ССЫЛКИ) ---
@dp.message(F.text.contains("http"))
async def handle_video(message: Message):
    res = db_query("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if res and res[2]: await message.answer("❌ Бан."); return
    is_p = res and res[3] and datetime.strptime(res[3], '%Y-%m-%d %H:%M') > datetime.now()
    today = datetime.now().strftime('%Y-%m-%d')
    dl = res[0] if res and res[1] == today else 0
    if not is_p and dl >= FREE_LIMIT: await message.answer("❌ Лимит! Ждем завтра."); return
    
    status = await message.answer("⏳ Обрабатываю...")
    try:
        p = await asyncio.to_thread(download_video, message.text)
        f = await asyncio.to_thread(unique_video, p)
        await message.answer_video(video=FSInputFile(f), caption="✅ Готово!")
        if not is_p: db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, today, message.from_user.id), commit=True)
        os.remove(p); os.remove(f); await status.delete()
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

# --- ФИЛЬТР НЕИЗВЕСТНЫХ СООБЩЕНИЙ (ВАЖНО!) ---
@dp.message(F.text)
async def unknown_msg(message: Message):
    # Если это кнопка меню, aiogram обработает её выше. Если дошло сюда — это просто текст.
    if message.text in ["👤 Профиль", "💰 Баланс", "📜 Правила", "🆘 Поддержка", "🛠 Админка"]:
        return # Пропускаем, так как для кнопок есть свои обработчики
    
    await message.answer("⚠️ **Я не понимаю этот текст.**\n\nПришли мне **ссылку** на видео (TikTok, Reels, Shorts) или нажми на кнопку в меню ниже. 👇")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())











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
SUPPORT_URL = "t.me/wokkiddd" # !!! ЗАМЕНИ НА СВОЙ ЮЗЕРНЕЙМ (без @) !!!
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
        res = row[0] if row else None
    if fetchall: res = cur.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    kb =,
    ]
    if user_id == ADMIN_ID: kb.append()
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_support_kb():
    return InlineKeyboardMarkup(inline_keyboard=
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
    await message.answer("🚀 Привет! Я помогу тебе уникализировать видео для TikTok/Reels.\nПришли ссылку!", 
                         reply_markup=get_main_kb(message.from_user.id))

@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(message: Message):
    text = ("🆘 **Служба поддержки**\n\n"
            "Возникли вопросы или проблемы с оплатой? Напиши нашему администратору напрямую.\n\n"
            "⚠️ *Пожалуйста, не спамьте, администратор ответит в течение дня.*")
    await message.answer(text, reply_markup=get_support_kb(), parse_mode="Markdown")

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute("SELECT stars, premium_until FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cur.fetchone(); conn.close()
    stars = row[0] if row else 0
    premium = row[1] if row and row[1] else "Нет"
    await message.answer(f"💰 **Баланс:** `{stars}` 🌟\n⏳ **Безлимит до:** `{premium}`", reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(message: Message):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute("SELECT downloads, stars, premium_until FROM users WHERE user_id = ?", (message.from_user.id,))
    r = cur.fetchone(); conn.close()
    used = r[0] if r else 0
    stars = r[1] if r else 0
    is_prem = "✅ Активен" if r and r[2] and datetime.strptime(r[2], '%Y-%m-%d %H:%M') > datetime.now() else "❌ Неактивен"
    
    await message.answer(f"👤 **Профиль**\nID: `{message.from_user.id}`\n🌟 Звёзд: `{stars}`\n🚀 Безлимит: {is_prem}\nЛимит: {used}/{FREE_LIMIT}", parse_mode="Markdown")

# --- ПЛАТЕЖИ И ПРЕМИУМ ---
@dp.callback_query(F.data == "add_50_stars")
async def buy_stars_process(callback: CallbackQuery):
    await bot.send_invoice(callback.message.chat.id, title="50 Звезд", description="Пополнение баланса бота",
                           payload="stars_50", provider_token="", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def success_payment(message: Message):
    amount = message.successful_payment.total_amount
    db_query("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amount, message.from_user.id), commit=True)
    await message.answer(f"✅ Зачислено {amount} звезд!")
    await bot.send_message(ADMIN_ID, f"💰 **НОВОЕ ПОПОЛНЕНИЕ!**\nЮзер: `{message.from_user.id}`\nСумма: `{amount}` 🌟")

@dp.callback_query(F.data == "buy_premium")
async def process_premium(callback: CallbackQuery):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute("SELECT stars FROM users WHERE user_id = ?", (callback.from_user.id,))
    stars = cur.fetchone()[0] if cur.fetchone() else 0; conn.close()
    
    if stars < PREMIUM_COST:
        await callback.answer("❌ Недостаточно звезд!", show_alert=True); return

    until = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
    db_query("UPDATE users SET stars = stars - ?, premium_until = ? WHERE user_id = ?", (PREMIUM_COST, until, callback.from_user.id), commit=True)
    await callback.message.edit_text(f"✅ Безлимит активен до `{until}`!"); await callback.answer()
    await bot.send_message(ADMIN_ID, f"🚀 **АКТИВАЦИЯ ПРЕМИУМА!**\nЮзер: `{callback.from_user.id}`\nСписано: `{PREMIUM_COST}` 🌟")

# --- ОБРАБОТКА ВИДЕО ---
@dp.message(F.text.contains("http"))
async def handle_video(message: Message):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cur.fetchone(); conn.close()
    if row and row[2] == 1: await message.answer("❌ Бан."); return
    
    is_prem = row and row[3] and datetime.strptime(row[3], '%Y-%m-%d %H:%M') > datetime.now()
    today = datetime.now().strftime('%Y-%m-%d')
    dl = row[0] if row and row[1] == today else 0

    if not is_prem and dl >= FREE_LIMIT:
        await message.answer("❌ Лимит! Купи безлимит в Балансе."); return

    status = await message.answer("⏳ Обработка...")
    try:
        p = await asyncio.to_thread(download_video, message.text)
        f = await asyncio.to_thread(unique_video, p)
        await message.answer_video(video=FSInputFile(f), caption="✅ Готово!")
        if not is_prem: db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, today, message.from_user.id), commit=True)
        os.remove(p); os.remove(f); await status.delete()
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

# --- АДМИНКА И ПРОЧЕЕ ---
@dp.message(F.text == "🛠 Админка")
async def adm(message: Message):
    if message.from_user.id == ADMIN_ID: 
        await message.answer("🛠 Панель админа. Доступны команды: /broadcast, /give, /ban")

@dp.message(F.text == "📜 Правила")
async def rules(message: Message): 
    await message.answer("3 видео в день бесплатно. Безлимит за 10 звезд.")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())







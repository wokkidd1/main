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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiocryptopay import AioCryptoPay, Networks

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
ADMIN_ID = 6779188403
SUPPORT_URL = "https://t.me/wokkiddd"
CHANNEL_URL = "https://t.me/rewokkidd" 
FREE_LIMIT = 3
PREMIUM_COST = 10 
DB_NAME = "users_data.db"
DOWNLOAD_DIR, RESULT_DIR = "downloads", "results"

for folder in [DOWNLOAD_DIR, RESULT_DIR]:
    if not os.path.exists(folder): os.makedirs(folder)

# Инициализация крипты
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- РАБОТА С БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, downloads INTEGER, 
                    last_reset TEXT, stars INTEGER DEFAULT 0, 
                    is_banned INTEGER DEFAULT 0, premium_until TEXT,
                    join_date TEXT)''')
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

# --- ЛОГИКА ОТЧЕТОВ ---
async def send_daily_report(bot: Bot):
    today = datetime.now().strftime('%Y-%m-%d')
    res_dl = db_query("SELECT SUM(downloads) FROM users WHERE last_reset = ?", (today,), fetchone=True)
    total_dl = res_dl[0] if res_dl and res_dl[0] else 0
    res_new = db_query("SELECT COUNT(*) FROM users WHERE join_date = ?", (today,), fetchone=True)
    total_new = res_new[0] if res_new else 0
    await bot.send_message(ADMIN_ID, f"📊 **ОТЧЕТ**\nЮзеров: {total_new}\nВидео: {total_dl}", parse_mode="Markdown")

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    kb_list =,
    ]
    if user_id == ADMIN_ID:
        kb_list.append()
    return ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True)

def get_balance_kb():
    return InlineKeyboardMarkup(inline_keyboard=,,
    ])

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    exists = db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not exists:
        db_query("INSERT INTO users (user_id, downloads, last_reset, join_date) VALUES (?, 0, ?, ?)", (user_id, today, today), commit=True)
        await bot.send_message(ADMIN_ID, f"🆕 Новый юзер: `{user_id}`")
    await message.answer("🚀 Привет! Пришли ссылку на видео.", reply_markup=get_main_kb(user_id))

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message):
    res = db_query("SELECT stars, premium_until FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    stars, prem = (res[3], res[5]) if res else (0, "Нет")
    await message.answer(f"💰 Баланс: `{stars}` 🌟\n⏳ Безлимит: `{prem}`", reply_markup=get_balance_kb(), parse_mode="Markdown")

# --- ОПЛАТА КРИПТОЙ ---
@dp.callback_query(F.data == "add_stars_crypto")
async def crypto_pay_start(call: CallbackQuery):
    invoice = await crypto.create_invoice(asset='USDT', amount=1.5)
    kb = InlineKeyboardMarkup(inline_keyboard=,
    ])
    await call.message.answer("💎 **Оплата USDT**\nНажми кнопку после оплаты.", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_pay(call: CallbackQuery):
    inv_id = int(call.data.split("_")[-1])
    invoices = await crypto.get_invoices(invoice_ids=inv_id)
    if invoices and invoices.status == 'paid':
        db_query("UPDATE users SET stars = stars + 50 WHERE user_id = ?", (call.from_user.id,), commit=True)
        await call.message.edit_text("✅ +50 звезд зачислено!"); await bot.send_message(ADMIN_ID, f"💎 Крипта: `{call.from_user.id}`")
    else: await call.answer("⌛ Оплата не найдена.", show_alert=True)

# --- ПЛАТЕЖИ STARS ---
@dp.callback_query(F.data == "add_stars_tg")
async def buy_stars_tg(call: CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="50 Звезд", description="Пополнение", payload="50", provider_token="", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: Message):
    db_query("UPDATE users SET stars = stars + ? WHERE user_id = ?", (m.successful_payment.total_amount, m.from_user.id), commit=True)
    await bot.send_message(ADMIN_ID, f"💰 Stars: `{m.from_user.id}`")

# --- УНИКАЛИЗАЦИЯ ---
def download_video(url):
    ydl_opts = {'format': 'best[ext=mp4]/best', 'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'noplaylist': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def unique_video(input_path):
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', 'hflip,scale=iw*1.1:-1,crop=iw/1.1:ih/1.1,setpts=0.95*PTS',
           '-af', 'atempo=1.05', '-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', out]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out

@dp.message(F.text.contains("http"))
async def handle_video(m: Message):
    res = db_query("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    if res and res[4]: await m.answer("❌ Бан."); return
    is_p = res and res[5] and datetime.strptime(res[5], '%Y-%m-%d %H:%M') > datetime.now()
    today = datetime.now().strftime('%Y-%m-%d')
    dl = res[1] if res and res[2] == today else 0
    if not is_p and dl >= FREE_LIMIT: await m.answer("❌ Лимит!"); return
    st = await m.answer("⏳ Обработка..."); 
    try:
        p = await asyncio.to_thread(download_video, m.text); f = await asyncio.to_thread(unique_video, p)
        await m.answer_video(video=FSInputFile(f), caption="✅ Готово!")
        if not is_p: db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, today, m.from_user.id), commit=True)
        os.remove(p); os.remove(f); await st.delete()
    except Exception as e: await m.answer(f"❌ Ошибка: {e}")

# (Оставь обработчики Профиль, Правила, Админка, Unknown из прошлого кода)
@dp.message(F.text == "👤 Профиль")
async def cmd_prof(m: Message):
    r = db_query("SELECT downloads, stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    await m.answer(f"👤 Профиль\nID: `{m.from_user.id}`\nЗвезд: {r[3] if r else 0}")

@dp.message(F.text == "🛠 Админка")
async def adm(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer("🛠 /stats | /broadcast | /give | /ban")

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_report, "cron", hour=21, minute=0, args=[bot])
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())















import asyncio
import os
import subprocess
import sqlite3
import random
import zipfile
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
    if not os.path.exists(folder):
        os.makedirs(folder)

bot = Bot(token=TOKEN)
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET) if CRYPTO_TOKEN else None

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, downloads INTEGER, last_reset TEXT, 
                    stars INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0, 
                    premium_until TEXT, join_date TEXT)''')
    conn.commit(); conn.close()

init_db()

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute(query, params)
    res = None
    if fetchone: res = cur.fetchone()
    elif fetchall: res = cur.fetchall()
    if commit: conn.commit()
    conn.close(); return res

# --- ЛОГИКА ОТЧЕТОВ ---
async def send_daily_report(bot: Bot):
    today = datetime.now().strftime('%Y-%m-%d')
    res_dl = db_query("SELECT SUM(downloads) FROM users WHERE last_reset = ?", (today,), fetchone=True)
    total_dl = res_dl[0] if res_dl and res_dl[0] else 0
    res_new = db_query("SELECT COUNT(*) FROM users WHERE join_date = ?", (today,), fetchone=True)
    total_new = res_new[0] if res_new else 0
    await bot.send_message(ADMIN_ID, f"📊 **ОТЧЕТ**\n\n👤 Новых: `{total_new}`\n🎬 Видео: `{total_dl}`", parse_mode="Markdown")

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    kb_list =,
    ])
    if user_id == ADMIN_ID:
        kb_list.append()
    return ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True)

def get_balance_kb():
    rows =,
    ])
    if CRYPTO_TOKEN:
        rows.append()
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_support_kb():
    return InlineKeyboardMarkup(inline_keyboard=,
    ])

# --- УНИКАЛИЗАЦИЯ ---
def unique_video_farm(input_path):
    zoom = round(random.uniform(1.06, 1.15), 2)
    speed = round(random.uniform(1.02, 1.07), 2)
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', f'hflip,scale=iw*{zoom}:-1,crop=iw/{zoom}:ih/1.1,setpts={1/speed}*PTS',
           '-af', f'atempo={speed}', '-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', out]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    uid = m.from_user.id; today = datetime.now().strftime('%Y-%m-%d')
    if not db_query("SELECT user_id FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, downloads, last_reset, join_date) VALUES (?, 0, ?, ?)", (uid, today, today), commit=True)
        count = db_query("SELECT COUNT(*) FROM users", fetchone=True)
        await bot.send_message(ADMIN_ID, f"🆕 Новый юзер: `{uid}`\nВсего в базе: `{count[0] if count else 1}`")
    await m.answer("🚀 Привет! Пришли ссылку.", reply_markup=get_main_kb(uid))

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(m: Message):
    res = db_query("SELECT stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    stars = res[0] if res else 0
    prem = res[1] if res and res[1] else "Нет"
    await m.answer(f"💰 **Баланс:** `{stars}` 🌟\n⏳ **Безлимит до:** `{prem}`", reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(m: Message):
    # Исправлен порядок: downloads(0), stars(3), premium_until(5) согласно таблице
    res = db_query("SELECT downloads, stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    used, stars, pr = (res[0], res[1], res[2]) if res else (0, 0, None)
    is_p = "✅ Да" if pr and datetime.strptime(pr, '%Y-%m-%d %H:%M') > datetime.now() else "❌ Нет"
    await m.answer(f"👤 **Профиль**\nID: `{m.from_user.id}`\n🌟 Звезд: {stars}\n🚀 Безлимит: {is_p}\n🎬 Лимит сегодня: {used}/{FREE_LIMIT}", parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(m: Message):
    await m.answer("🆘 Нужна помощь? Используй кнопки ниже:", reply_markup=get_support_kb())

# --- ПЛАТЕЖИ ---
@dp.callback_query(F.data == "add_stars_crypto")
async def crypto_pay(call: CallbackQuery):
    if not crypto: return await call.answer("Крипто-токен не настроен!", show_alert=True)
    inv = await crypto.create_invoice(asset='USDT', amount=1.5)
    kb = InlineKeyboardMarkup(inline_keyboard=,
    ])
    await call.message.answer("💎 Оплати счет и нажми кнопку:", reply_markup=kb)

# --- ОБРАБОТКА (ФЕРМА + ZIP) ---
@dp.message(F.text.contains("http"))
async def handle_video(m: Message):
    if m.from_user.id == ADMIN_ID and "\n" in m.text:
        links =
        st_msg = await m.answer(f"🚜 Ферма: Обработка {len(links)} видео...")
        processed = []
        zip_fn = f"farm_{datetime.now().strftime('%d%m_%H%M')}.zip"
        for i, link in enumerate(links):
            try:
                with yt_dlp.YoutubeDL({'format': 'best[ext=mp4]/best', 'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'quiet': True}) as ydl:
                    info = ydl.extract_info(link, download=True)
                    p = ydl.prepare_filename(info); f = await asyncio.to_thread(unique_video_farm, p)
                    processed.append((p, f))
            except: await m.answer(f"❌ Ошибка: {link}")
        if processed:
            with zipfile.ZipFile(zip_fn, 'w') as f_zip:
                for _, f in processed: f_zip.write(f, os.path.basename(f))
            await m.answer_document(document=FSInputFile(zip_fn), caption=f"✅ Готово: {len(processed)} шт.")
            os.remove(zip_fn)
            for p, f in processed:
                if os.path.exists(p): os.remove(p)
                if os.path.exists(f): os.remove(f)
        await st_msg.delete(); return

    res = db_query("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    if res and res[2] == 1: return await m.answer("❌ Бан.")
    is_p = res and res[3] and datetime.strptime(res[3], '%Y-%m-%d %H:%M') > datetime.now()
    dl = res[0] if res and res[1] == datetime.now().strftime('%Y-%m-%d') else 0
    if not is_p and dl >= FREE_LIMIT: return await m.answer("❌ Лимит!")
    st = await m.answer("⏳ Обработка..."); 
    try:
        with yt_dlp.YoutubeDL({'format': 'best[ext=mp4]/best', 'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'quiet': True}) as ydl:
            info = ydl.extract_info(m.text, download=True)
            p = ydl.prepare_filename(info); f = await asyncio.to_thread(unique_video_farm, p)
            await m.answer_video(video=FSInputFile(f), caption="✅ Готово!")
            if not is_p: db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, datetime.now().strftime('%Y-%m-%d'), m.from_user.id), commit=True)
            os.remove(p); os.remove(f); await st.delete()
    except Exception as e: await m.answer(f"❌ Ошибка: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())




























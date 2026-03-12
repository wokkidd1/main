import asyncio
import os
import subprocess
import sqlite3
import random
import zipfile
from datetime import datetime
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, FSInputFile, ReplyKeyboardMarkup, 
                           KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, LabeledPrice, PreCheckoutQuery)
from aiogram.filters import Command
from aiocryptopay import AioCryptoPay, Networks

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN") 
ADMIN_ID = 6779188403
SUPPORT_URL = "https://t.me/wokkiddd"
CHANNEL_URL = "https://t.me/rewokkidd" 
FREE_LIMIT = 3
DB_NAME = "users_data.db"
DOWNLOAD_DIR, RESULT_DIR = "downloads", "results"

for folder in [DOWNLOAD_DIR, RESULT_DIR]:
    os.makedirs(folder, exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET) if CRYPTO_TOKEN else None

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        if fetchone: return cur.fetchone()
        if fetchall: return cur.fetchall()
        return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users 
                (user_id INTEGER PRIMARY KEY, downloads INTEGER, last_reset TEXT, 
                 stars INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0, 
                 premium_until TEXT, join_date TEXT)''', commit=True)
init_db()

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    buttons = [
        [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="🆘 Поддержка")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🛠 Админка")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_balance_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить 100 Stars", callback_data="buy_stars_tg")],
        [InlineKeyboardButton(text="💳 Crypto Pay (USDT)", callback_data="buy_crypto")]
    ])

def get_support_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Админ", url=SUPPORT_URL)],
        [InlineKeyboardButton(text="📢 Канал", url=CHANNEL_URL)]
    ])

# --- УНИКАЛИЗАЦИЯ ---
def unique_video_farm(input_path):
    zoom = round(random.uniform(1.06, 1.15), 2)
    speed = round(random.uniform(1.02, 1.07), 2)
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', 
           f'hflip,scale=iw*{zoom}:-1,crop=iw/{zoom}:ih/{zoom},setpts={1/speed}*PTS',
           '-af', f'atempo={speed}', '-map_metadata', '-1', '-c:v', 'libx264', 
           '-preset', 'ultrafast', '-crf', '28', out]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out

async def download_video(url):
    ydl_opts = {'format': 'best[ext=mp4]/best', 'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'quiet': True}
    return await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    uid = m.from_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    if not db_query("SELECT user_id FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, downloads, last_reset, join_date) VALUES (?, 0, ?, ?)", 
                 (uid, today, today), commit=True)
    await m.answer(f"🚀 Привет! Пришли ссылку на видео.\nНаш канал: {CHANNEL_URL}", reply_markup=get_main_kb(uid))

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(m: Message):
    res = db_query("SELECT stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    stars = res[0] if res else 0
    prem = res[1] if res and res[1] else "Нет"
    await m.answer(f"💰 **Баланс:** `{stars}` 🌟\n⏳ **Безлимит:** `{prem}`", 
                   reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(m: Message):
    res = db_query("SELECT downloads, stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    used, stars, pr = res if res else (0, 0, None)
    await m.answer(f"👤 **Профиль**\nID: `{m.from_user.id}`\n🌟 Звезды: {stars}\n🎬 Сегодня: {used}/{FREE_LIMIT}", 
                   reply_markup=get_support_kb(), parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(m: Message):
    await m.answer("🆘 Возникли вопросы? Свяжитесь с нами:", reply_markup=get_support_kb())

@dp.message(F.text == "🛠 Админка")
async def admin_panel(m: Message):
    if m.from_user.id != ADMIN_ID: return
    count = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    await m.answer(f"⚙️ **Админ-панель**\nЮзеров в базе: `{count}`", parse_mode="Markdown")

# --- ПЛАТЕЖИ ---
@dp.callback_query(F.data == "buy_stars_tg")
async def pay_stars(call: CallbackQuery):
    await call.message.answer_invoice(
        title="100 Звезд", description="Пополнение баланса",
        prices=[LabeledPrice(label="XTR", amount=100)],
        payload="stars_100", currency="XTR"
    )

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: Message):
    db_query("UPDATE users SET stars = stars + 100 WHERE user_id = ?", (m.from_user.id,), commit=True)
    await m.answer("✅ Баланс пополнен на 100 звезд!")

@dp.callback_query(F.data == "buy_crypto")
async def pay_crypto(call: CallbackQuery):
    if not crypto: return await call.answer("Настройка Crypto Pay не завершена.", show_alert=True)
    inv = await crypto.create_invoice(asset='USDT', amount=1.0)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Оплатить 1 USDT", url=inv.bot_invoice_url)]])
    await call.message.answer("Оплатите инвойс в CryptoBot:", reply_markup=kb)

# --- ОБРАБОТКА ВИДЕО ---
@dp.message(F.text.contains("http"))
async def handle_video(m: Message):
    uid = m.from_user.id
    # Ферма для админа
    if uid == ADMIN_ID and "\n" in m.text:
        links = [l.strip() for l in m.text.split('\n') if "http" in l]
        st_msg = await m.answer(f"🚜 Ферма запущена ({len(links)} видео)...")
        processed = []
        for link in links:
            try:
                info = await download_video(link)
                p = info['requested_downloads'][0]['filepath']
                f = await asyncio.to_thread(unique_video_farm, p)
                processed.append((p, f))
            except: continue
        
        if processed:
            zip_fn = f"farm_{datetime.now().strftime('%H%M')}.zip"
            with zipfile.ZipFile(zip_fn, 'w') as z:
                for _, f in processed: z.write(f, os.path.basename(f))
            await m.answer_document(document=FSInputFile(zip_fn), caption=f"✅ Готово: {len(processed)}")
            os.remove(zip_fn)
            for p, f in processed:
                if os.path.exists(p): os.remove(p)
                if os.path.exists(f): os.remove(f)
        await st_msg.delete(); return

    # Обычный юзер
    res = db_query("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if res and res[2] == 1: return await m.answer("❌ Бан.")
    
    today = datetime.now().strftime('%Y-%m-%d')
    dl_count = res[0] if res and res[1] == today else 0
    if dl_count >= FREE_LIMIT: return await m.answer("❌ Лимит! Пополни баланс.")

    st = await m.answer("⏳ Обработка..."); 
    try:
        info = await download_video(m.text)
        p = info['requested_downloads'][0]['filepath']
        f = await asyncio.to_thread(unique_video_farm, p)
        await m.answer_video(video=FSInputFile(f), caption="✅ Уникализировано!")
        db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl_count+1, today, uid), commit=True)
        if os.path.exists(p): os.remove(p)
        if os.path.exists(f): os.remove(f)
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)[:50]}...")
    finally:
        await st.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


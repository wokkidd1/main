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
                           CallbackQuery)
from aiogram.filters import Command

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
ADMIN_ID = 6779188403
SUPPORT_URL = "https://t.me"
FREE_LIMIT = 3
DB_NAME = "users_data.db"
DOWNLOAD_DIR, RESULT_DIR = "downloads", "results"

for folder in [DOWNLOAD_DIR, RESULT_DIR]:
    os.makedirs(folder, exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, commit=False):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        return cur.fetchone() if fetchone else None

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
        [InlineKeyboardButton(text="💎 Пополнить Stars", callback_data="add_stars")],
        [InlineKeyboardButton(text="💳 Crypto Pay", callback_data="add_stars_crypto")]
    ])

def get_support_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Написать админу", url=SUPPORT_URL)]
    ])

# --- УНИКАЛИЗАЦИЯ ---
def unique_video_farm(input_path):
    zoom = round(random.uniform(1.06, 1.15), 2)
    speed = round(random.uniform(1.02, 1.07), 2)
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    # Упрощенный фильтр для FFmpeg
    cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', 
           f'hflip,scale=iw*{zoom}:-1,crop=iw/{zoom}:ih/{zoom},setpts={1/speed}*PTS',
           '-af', f'atempo={speed}', '-map_metadata', '-1', '-c:v', 'libx264', 
           '-preset', 'ultrafast', '-crf', '28', out]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out

# --- ВСПОМОГАТЕЛЬНОЕ ---
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
        await bot.send_message(ADMIN_ID, f"🆕 Новый юзер: `{uid}`", parse_mode="Markdown")
    await m.answer("🚀 Привет! Пришли ссылку на видео из TikTok/Reels.", reply_markup=get_main_kb(uid))

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(m: Message):
    res = db_query("SELECT stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    stars = res[0] if res else 0
    prem = res[1] if res and res[1] else "Нет"
    await m.answer(f"💰 **Баланс:** `{stars}` 🌟\n⏳ **Безлимит до:** `{prem}`", 
                   reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(m: Message):
    res = db_query("SELECT downloads, stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    used, stars, pr = res if res else (0, 0, None)
    is_p = "✅ Да" if pr and datetime.strptime(pr, '%Y-%m-%d %H:%M') > datetime.now() else "❌ Нет"
    await m.answer(f"👤 **Профиль**\nID: `{m.from_user.id}`\n🌟 Звезд: {stars}\n🚀 Безлимит: {is_p}\n🎬 Лимит сегодня: {used}/{FREE_LIMIT}", parse_mode="Markdown")

@dp.message(F.text.contains("http"))
async def handle_video(m: Message):
    uid = m.from_user.id
    # Логика фермы для админа (список ссылок)
    if uid == ADMIN_ID and "\n" in m.text:
        links = [l.strip() for l in m.text.split('\n') if l.startswith('http')]
        st_msg = await m.answer(f"🚜 Ферма: Обработка {len(links)} видео...")
        processed_files = []
        
        for link in links:
            try:
                info = await download_video(link)
                path = info['requested_downloads'][0]['filepath']
                unique_path = await asyncio.to_thread(unique_video_farm, path)
                processed_files.append((path, unique_path))
            except Exception as e:
                await m.answer(f"❌ Ошибка в {link}: {e}")
        
        if processed_files:
            zip_fn = f"farm_{datetime.now().strftime('%d%m_%H%M')}.zip"
            with zipfile.ZipFile(zip_fn, 'w') as f_zip:
                for _, f in processed_files:
                    if os.path.exists(f): f_zip.write(f, os.path.basename(f))
            
            await m.answer_document(document=FSInputFile(zip_fn), caption=f"✅ Готово: {len(processed_files)} шт.")
            if os.path.exists(zip_fn): os.remove(zip_fn)
            for p, f in processed_files:
                if os.path.exists(p): os.remove(p)
                if os.path.exists(f): os.remove(f)
        await st_msg.delete()
        return

    # Обычная обработка одного видео
    res = db_query("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if res and res[2] == 1: return await m.answer("❌ Вы забанены.")
    
    is_p = res and res[3] and datetime.strptime(res[3], '%Y-%m-%d %H:%M') > datetime.now()
    today = datetime.now().strftime('%Y-%m-%d')
    dl_count = res[0] if res and res[1] == today else 0
    
    if not is_p and dl_count >= FREE_LIMIT:
        return await m.answer("❌ Лимит на сегодня исчерпан! Купите Premium.")

    st = await m.answer("⏳ Скачиваю и уникализирую...")
    try:
        info = await download_video(m.text)
        path = info['requested_downloads'][0]['filepath']
        unique_path = await asyncio.to_thread(unique_video_farm, path)
        
        await m.answer_video(video=FSInputFile(unique_path), caption="✅ Видео готово!")
        
        if not is_p:
            db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", 
                     (dl_count + 1, today, uid), commit=True)
        
        if os.path.exists(path): os.remove(path)
        if os.path.exists(unique_path): os.remove(unique_path)
    except Exception as e:
        await m.answer(f"❌ Произошла ошибка: {e}")
    finally:
        await st.delete()

@dp.message()
async def unknown_msg(m: Message):
    if m.text in ["💰 Баланс", "👤 Профиль", "🆘 Поддержка", "🛠 Админка"]: return
    await m.answer("⚠️ Пожалуйста, отправьте ссылку на видео.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
































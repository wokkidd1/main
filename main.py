import asyncio
import os
import subprocess
import sqlite3
from datetime import datetime
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6779188403  # Твой ID установлен
FREE_LIMIT = 3         # Лимит видео в сутки
DOWNLOAD_DIR = "downloads"
RESULT_DIR = "results"
DB_NAME = "users_data.db"

# Создаем папки для работы
for folder in [DOWNLOAD_DIR, RESULT_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# --- РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, downloads INTEGER, last_reset TEXT)''')
    conn.commit()
    conn.close()

init_db()

def check_limit(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    cur.execute("SELECT downloads, last_reset FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    
    if row is None:
        cur.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, 0, today))
        conn.commit()
        conn.close()
        return True, 0
    
    downloads, last_reset = row
    if last_reset != today:
        cur.execute("UPDATE users SET downloads = 0, last_reset = ? WHERE user_id = ?", (today, user_id))
        conn.commit()
        conn.close()
        return True, 0
    
    conn.close()
    return (downloads < FREE_LIMIT), downloads

def increment_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_admin_stats():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(user_id) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT SUM(downloads) FROM users")
    total_downloads = cur.fetchone()[0] or 0
    cur.execute("SELECT user_id, downloads FROM users WHERE downloads > 0 ORDER BY downloads DESC LIMIT 10")
    top_users = cur.fetchall()
    conn.close()
    return total_users, total_downloads, top_users

# --- ЛОГИКА БОТА ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Функция скачивания
def download_video(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        'noplaylist': True, 'quiet': True, 'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# Функция уникализации (FFmpeg)
def unique_video(input_path):
    filename = os.path.basename(input_path)
    output_path = os.path.join(RESULT_DIR, f"unique_{filename}")
    command = [
        'ffmpeg', '-y', '-i', input_path,
        '-vf', 'hflip,scale=iw*1.1:-1,crop=iw/1.1:ih/1.1,setpts=0.95*PTS',
        '-af', 'atempo=1.05', '-map_metadata', '-1',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
        output_path
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return output_path

# Команда Админа
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return # Игнорируем не админов

    total_u, total_d, top = get_admin_stats()
    text = (f"📊 **АДМИН-ПАНЕЛЬ**\n\n"
            f"👤 Всего пользователей: `{total_u}`\n"
            f"🎬 Скачано сегодня: `{total_d}`\n\n"
            f"🔝 **Топ активных сегодня:**\n")
    
    for uid, count in top:
        text += f"• `{uid}` — {count} видео\n"
    
    await message.answer(text, parse_mode="Markdown")

# Обработчик ссылок
@dp.message(F.text.contains("http"))
async def handle_link(message: Message):
    user_id = message.from_user.id
    can_dl, usage = check_limit(user_id)
    
    if not can_dl:
        await message.answer(f"❌ Лимит {FREE_LIMIT}/{FREE_LIMIT} исчерпан.\nПриходи завтра!")
        return

    status = await message.answer(f"⏳ Начинаю (использовано {usage + 1}/{FREE_LIMIT})...")
    
    try:
        file_p = await asyncio.to_thread(download_video, message.text)
        await status.edit_text("⚙️ Уникализирую...")
        final_p = await asyncio.to_thread(unique_video, file_p)
        
        await message.answer_video(video=FSInputFile(final_p), caption="✨ Готово!")
        increment_downloads(user_id)
        
        if os.path.exists(file_p): os.remove(file_p)
        if os.path.exists(final_p): os.remove(final_p)
        await status.delete()

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message()
async def start_msg(message: Message):
    await message.answer(f"Привет! Пришли мне ссылку на видео.\nТвой лимит: {FREE_LIMIT} в сутки.")

async def main():
    print("🚀 Бот запущен! Админ ID прописан.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())





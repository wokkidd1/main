import asyncio
import os
import subprocess
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile

# --- НАСТРОЙКИ (Берем из переменных окружения Railway) ---
TOKEN = os.getenv("8683356041:AAG4ZY-pcY2AiMpzhW7exEFsyGq-SezJlfY") 
DOWNLOAD_DIR = "downloads"
RESULT_DIR = "results"

# Создаем папки для работы бота
for folder in [DOWNLOAD_DIR, RESULT_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

if not TOKEN:
    print("ОШИБКА: Переменная BOT_TOKEN не установлена в Railway!")
    exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ФУНКЦИЯ СКАЧИВАНИЯ (yt-dlp) ---
def download_video(url):
    ydl_opts = {
        # Ищем mp4 версию без водяных знаков
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# --- ФУНКЦИЯ УНИКАЛИЗАЦИИ (FFmpeg) ---
def unique_video(input_path):
    filename = os.path.basename(input_path)
    output_path = os.path.join(RESULT_DIR, f"unique_{filename}")
    
    # Команда FFmpeg для "перезаписи" видео:
    # hflip - зеркало, scale/crop - зум 10%, setpts/atempo - ускорение 5%
    command = [
        'ffmpeg', '-y', '-i', input_path,
        '-vf', 'hflip,scale=iw*1.1:-1,crop=iw/1.1:ih/1.1,setpts=0.95*PTS',
        '-af', 'atempo=1.05',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
        output_path
    ]
    
    # Запускаем обработку
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return output_path

# --- ОБРАБОТЧИК ССЫЛОК ---
@dp.message(F.text.contains("http"))
async def handle_link(message: Message):
    status_msg = await message.answer("📥 Скачиваю видео...")
    
    try:
        # Запускаем тяжелые функции в отдельном потоке, чтобы бот не тупил
        file_path = await asyncio.to_thread(download_video, message.text)
        
        await status_msg.edit_text("⚙️ Уникализирую (зеркало + зум + 105% скорость)...")
        final_video_path = await asyncio.to_thread(unique_video, file_path)
        
        await status_msg.edit_text("🚀 Отправляю результат!")
        
        # Отправляем видео пользователю
        video_file = FSInputFile(final_video_path)
        await message.answer_video(video=video_file, caption="✅ Готово для Reels/TikTok/Shorts!")
        
        # Удаляем временные файлы, чтобы не забить память сервера
        if os.path.exists(file_path): os.remove(file_path)
        if os.path.exists(final_video_path): os.remove(final_video_path)
        await status_msg.delete()

    except Exception as e:
        await message.answer(f"❌ Произошла ошибка: {str(e)}")
        print(f"Error: {e}")

@dp.message()
async def welcome(message: Message):
    await message.answer("Привет! Пришли мне ссылку на TikTok, Shorts или Reels, и я сделаю видео уникальным.")

# --- ЗАПУСК ---
async def main():
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import subprocess
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile

# --- НАСТРОЙКИ (Берем из переменных окружения Railway) ---
TOKEN = os.getenv("BOT_TOKEN") 
DOWNLOAD_DIR = "downloads"
RESULT_DIR = "results"

# Создаем папки для работы, если их еще нет
for folder in [DOWNLOAD_DIR, RESULT_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

if not TOKEN:
    print("❌ ОШИБКА: Переменная BOT_TOKEN не найдена! Проверь вкладку Variables в Railway.")
    exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ФУНКЦИЯ СКАЧИВАНИЯ (Упрощенная для стабильности) ---
def download_video(url):
    ydl_opts = {
        # Скачиваем сразу готовый mp4, чтобы не требовать склейки через ffmpeg на этом этапе
        'format': 'best[ext=mp4]/best', 
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# --- ФУНКЦИЯ УНИКАЛИЗАЦИИ (FFmpeg) ---
def unique_video(input_path):
    filename = os.path.basename(input_path)
    output_path = os.path.join(RESULT_DIR, f"unique_{filename}")
    
    # Команда: Зеркало + Зум 10% + Ускорение 5% + Удаление метаданных
    command = [
        'ffmpeg', '-y', '-i', input_path,
        '-vf', 'hflip,scale=iw*1.1:-1,crop=iw/1.1:ih/1.1,setpts=0.95*PTS',
        '-af', 'atempo=1.05',
        '-map_metadata', '-1', # Полная очистка метаданных файла
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
        output_path
    ]
    
    # Запуск процесса
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg Error: {result.stderr}")
        
    return output_path

# --- ОБРАБОТЧИК ССЫЛОК ---
@dp.message(F.text.contains("http"))
async def handle_link(message: Message):
    status_msg = await message.answer("📥 Начинаю... Скачиваю видео.")
    
    file_path = None
    final_video_path = None
    
    try:
        # 1. Скачивание
        file_path = await asyncio.to_thread(download_video, message.text)
        print(f"✅ Скачано: {file_path}")
        
        await status_msg.edit_text("⚙️ Уникализирую (Зеркало + Зум + Тайминг)...")
        
        # 2. Обработка
        final_video_path = await asyncio.to_thread(unique_video, file_path)
        print(f"✅ Уникализировано: {final_video_path}")
        
        await status_msg.edit_text("🚀 Готово! Отправляю файл.")
        
        # 3. Отправка
        video_file = FSInputFile(final_video_path)
        await message.answer_video(video=video_file, caption="✨ Твоё уникальное видео готово!")
        
        await status_msg.delete()

    except Exception as e:
        await message.answer(f"❌ Произошла ошибка: {str(e)}")
        print(f"⚠️ Ошибка обработки: {e}")

    finally:
        # 4. Чистка временных файлов
        if file_path and os.path.exists(file_path): 
            os.remove(file_path)
        if final_video_path and os.path.exists(final_video_path): 
            os.remove(final_video_path)

@dp.message()
async def welcome(message: Message):
    await message.answer("Привет! Скинь ссылку на TikTok, Shorts или Reels — я сделаю видео уникальным.")

# --- ЗАПУСК ---
async def main():
    print("🚀 Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())



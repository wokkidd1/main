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
SUPPORT_URL = "https://t.me/wokkiddd" # ЗАМЕНИ НА СВОЙ ЮЗЕРНЕЙМ (без @)
CHANNEL_URL = "https://t.me/rewokkidd"    # ЗАМЕНИ НА СВОЙ КАНАЛ
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

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    kb =,
    ]
    if user_id == ADMIN_ID: kb.append()
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

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
    await message.answer("🚀 Привет! Бот готов к работе. Пришли ссылку на видео!", 
                         reply_markup=get_main_kb(message.from_user.id))

# --- ПОЛЬЗОВАТЕЛЬСКОЕ МЕНЮ ---
@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(message: Message):
    await message.answer("🆘 **Служба поддержки**\n\nЕсть вопросы? Пиши админу или загляни в канал.", 
                         reply_markup=get_support_kb(), parse_mode="Markdown")

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message):
    res = db_query("SELECT stars, premium_until FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    stars = res[0] if res else 0
    prem = res[1] if res and res[1] else "Нет"
    await message.answer(f"💰 **Баланс:** `{stars}` 🌟\n⏳ **Безлимит до:** `{prem}`", reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(message: Message):
    res = db_query("SELECT downloads, stars, premium_until FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    used, stars = (res[0], res[1]) if res else (0, 0)
    is_prem = "✅ Да" if res and res[2] and datetime.strptime(res[2], '%Y-%m-%d %H:%M') > datetime.now() else "❌ Нет"
    await message.answer(f"👤 **Профиль**\n\n🆔 ID: `{message.from_user.id}`\n🌟 Звёзд: `{stars}`\n🚀 Безлимит: {is_prem}\n🎬 Лимит сегодня: {used}/{FREE_LIMIT}", parse_mode="Markdown")

# --- ПЛАТЕЖИ ---
@dp.callback_query(F.data == "add_50_stars")
async def buy_stars(call: CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="50 Звезд", description="Пополнение баланса", payload="50", provider_token="", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: Message):
    db_query("UPDATE users SET stars = stars + ? WHERE user_id = ?", (m.successful_payment.total_amount, m.from_user.id), commit=True)
    await bot.send_message(ADMIN_ID, f"💰 Пополнение: {m.from_user.id} на {m.successful_payment.total_amount} 🌟")

@dp.callback_query(F.data == "buy_premium")
async def buy_prem(call: CallbackQuery):
    res = db_query("SELECT stars FROM users WHERE user_id = ?", (call.from_user.id,), fetchone=True)
    if res and res[0] >= PREMIUM_COST:
        until = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
        db_query("UPDATE users SET stars = stars - ?, premium_until = ? WHERE user_id = ?", (PREMIUM_COST, until, call.from_user.id), commit=True)
        await call.message.edit_text(f"✅ Безлимит активирован до {until}"); await bot.send_message(ADMIN_ID, f"🚀 Куплен Премиум: {call.from_user.id}")
    else: await call.answer("Недостаточно звезд!", show_alert=True)

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text == "🛠 Админка")
async def admin_menu_btn(m: Message):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("🛠 Ты вошел в панель администратора.\n\nИспользуй команду **/ahelp**, чтобы увидеть список всех доступных инструментов.")

@dp.message(Command("ahelp"))
async def admin_help_cmd(m: Message):
    if m.from_user.id != ADMIN_ID: return
    help_text = (
        "🆘 **СПРАВКА АДМИНИСТРАТОРА**\n\n"
        "📊 **Статистика:**\n"
        "`/stats` — Общее кол-во пользователей в базе.\n\n"
        "📢 **Рассылка:**\n"
        "`/broadcast [текст]` — Отправить сообщение всем пользователям.\n\n"
        "👤 **Управление юзерами:**\n"
        "`/check [ID]` — Проверить баланс, лимиты и статус бана юзера.\n"
        "`/give [ID] [число]` — Выдать звезды пользователю.\n"
        "`/ban [ID]` — Заблокировать доступ.\n"
        "`/unban [ID]` — Разблокировать доступ.\n\n"
        "💡 *Пример:* `/give 6779188403 50` — выдаст тебе 50 звезд."
    )
    await m.answer(help_text, parse_mode="Markdown")

@dp.message(Command("stats"))
async def ad_stats(m: Message):
    if m.from_user.id != ADMIN_ID: return
    res = db_query("SELECT COUNT(*) FROM users", fetchone=True)
    await m.answer(f"📊 Всего юзеров в базе: `{res[0]}`", parse_mode="Markdown")

@dp.message(Command("check"))
async def ad_check(m: Message):
    if m.from_user.id != ADMIN_ID: return
    try:
        uid = m.text.split()[1]
        res = db_query("SELECT stars, downloads, is_banned, premium_until FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if res:
            status = "БАН" if res[2] else "ОК"
            prem = res[3] if res[3] else "Нет"
            await m.answer(f"🔎 Юзер `{uid}`:\n🌟 Звезд: {res[0]}\n🎬 Скачано сегодня: {res[1]}\n🚀 Премиум до: {prem}\nСтатус: {status}", parse_mode="Markdown")
        else: await m.answer("Юзер не найден.")
    except: await m.answer("Используй: /check [ID]")

@dp.message(Command("broadcast"))
async def ad_broad(m: Message):
    if m.from_user.id != ADMIN_ID: return
    text = m.text.replace("/broadcast", "").strip()
    if not text: return await m.answer("Напиши текст после команды!")
    users = db_query("SELECT user_id FROM users", fetchall=True)
    for u in users:
        try: await bot.send_message(u[0], f"📢 **Объявление:**\n\n{text}", parse_mode="Markdown")
        except: pass
    await m.answer("✅ Рассылка завершена")

@dp.message(Command("give"))
async def ad_give(m: Message):
    if m.from_user.id != ADMIN_ID: return
    try:
        _, uid, amt = m.text.split()
        db_query("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amt, uid), commit=True)
        await m.answer(f"✅ Выдано {amt} звезд юзеру `{uid}`", parse_mode="Markdown")
    except: await m.answer("Используй: /give [ID] [число]")

@dp.message(Command("ban"))
async def ad_ban(m: Message):
    if m.from_user.id != ADMIN_ID: return
    try:
        uid = m.text.split()[1]
        db_query("UPDATE users SET is_banned = 1 WHERE user_id = ?", (uid,), commit=True)
        await m.answer(f"🚫 Юзер `{uid}` забанен.", parse_mode="Markdown")
    except: await m.answer("Используй: /ban [ID]")

# --- ОБРАБОТКА ВИДЕО ---
@dp.message(F.text.contains("http"))
async def handle_video(message: Message):
    res = db_query("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if res and res[2]: await message.answer("❌ Вы забанены."); return
    is_p = res and res[3] and datetime.strptime(res[3], '%Y-%m-%d %H:%M') > datetime.now()
    today = datetime.now().strftime('%Y-%m-%d')
    dl = res[0] if res and res[1] == today else 0
    if not is_p and dl >= FREE_LIMIT: await message.answer("❌ Лимит! Ждем завтра или купи Безлимит в Балансе."); return
    status = await message.answer("⏳ Магия началась... Обрабатываю видео.")
    try:
        p = await asyncio.to_thread(download_video, message.text)
        f = await asyncio.to_thread(unique_video, p)
        await message.answer_video(video=FSInputFile(f), caption="✅ Твое видео готово!")
        if not is_p: db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, today, message.from_user.id), commit=True)
        os.remove(p); os.remove(f); await status.delete()
    except Exception as e: await message.answer(f"❌ Ошибка обработки: {e}")

@dp.message()
async def rules_text(m: Message):
    if m.text == "📜 Правила": 
        await m.answer(f"⚖️ **Правила:**\n\n• Бесплатно: {FREE_LIMIT} видео/день.\n• Безлимит на 24ч: {PREMIUM_COST} звезд.\n• Запрещено использовать бота для спама.", parse_mode="Markdown")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())









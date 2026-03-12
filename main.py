import asyncio, os, subprocess, sqlite3, random, zipfile
from datetime import datetime, timedelta
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, FSInputFile, ReplyKeyboardMarkup, 
                           KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, LabeledPrice, PreCheckoutQuery)
from aiogram.filters import Command, CommandStart
from aiocryptopay import AioCryptoPay, Networks
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
ADMIN_ID = 6779188403
CHANNEL_ID = -100234567890  # ID канала (с -100)
CHANNEL_URL = "https://t.me/wokkiddd"
SUPPORT_URL = "https://t.me/rewokkidd"
FREE_LIMIT = 3
DB_NAME = "users_data.db"
DOWNLOAD_DIR, RESULT_DIR = "downloads", "results"

for folder in [DOWNLOAD_DIR, RESULT_DIR]: os.makedirs(folder, exist_ok=True)

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
                 premium_until TEXT, join_date TEXT, referrer_id INTEGER)''', commit=True)
    db_query('''CREATE TABLE IF NOT EXISTS payments 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, currency TEXT, date TEXT)''', commit=True)
init_db()

# --- ВСПОМОГАТЕЛЬНОЕ ---
async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return True

def unique_video(input_path, mode="Medium"):
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    z = round(random.uniform(1.06, 1.15), 2)
    s = round(random.uniform(1.02, 1.07), 2)
    
    presets = {
        "Light": f"-vf scale=iw:-1 -c:a copy",
        "Medium": f"-vf hflip,scale=iw*{z}:-1,crop=iw/{z}:ih/{z},setpts={1/s}*PTS -af atempo={s}",
        "Hard": f"-vf hflip,scale=iw*{z+0.03}:-1,crop=iw/({z}+0.03):ih/({z}+0.03),hue=s=1.1,setpts={1/(s+0.02)}*PTS -af atempo={s+0.02}"
    }
    
    cmd = ['ffmpeg', '-y', '-i', input_path] + presets[mode].split() + \
          ['-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', out]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out

# --- КЛАВИАТУРЫ ---
def get_main_kb(uid):
    btns = [[KeyboardButton(text="💰 Баланс"), KeyboardButton(text="👤 Профиль")], [KeyboardButton(text="🆘 Поддержка")]]
    if uid == ADMIN_ID: btns.append([KeyboardButton(text="🛠 Админка")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def get_presets_kb(url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍃 Light", callback_data=f"p:Light:{url}"),
         InlineKeyboardButton(text="⚡ Medium", callback_data=f"p:Medium:{url}"),
         InlineKeyboardButton(text="🔥 Hard", callback_data=f"p:Hard:{url}")]
    ])

# --- ПЛАНИРОВЩИК (ОТЧЕТ В 21:00) ---
async def send_daily_stats():
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    stars_day = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'XTR' AND date > ?", (yesterday,), fetchone=True)[0] or 0
    usdt_day = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'USDT' AND date > ?", (yesterday,), fetchone=True)[0] or 0
    new_users = db_query("SELECT COUNT(*) FROM users WHERE join_date = ?", (datetime.now().strftime('%Y-%m-%d'),), fetchone=True)[0] or 0
    
    report = (f"📊 **Ежедневный отчет**\n\n👥 Новых юзеров: `{new_users}`\n"
              f"💰 Stars за 24ч: `{int(stars_day)}` 🌟\n💰 USDT за 24ч: `{usdt_day}$` 💵")
    try: await bot.send_message(ADMIN_ID, report, parse_mode="Markdown")
    except: pass

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def cmd_start(m: Message):
    uid, today = m.from_user.id, datetime.now().strftime('%Y-%m-%d')
    args = m.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    
    if not db_query("SELECT user_id FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, downloads, last_reset, join_date, referrer_id) VALUES (?, 0, ?, ?, ?)", 
                 (uid, today, today, ref_id), commit=True)
        if ref_id:
            db_query("UPDATE users SET stars = stars + 2 WHERE user_id = ?", (ref_id,), commit=True)
            try: await bot.send_message(ref_id, "🎁 +2 звезды за реферала!")
            except: pass
    await m.answer(f"🚀 Привет! Пришли ссылку.\n\nТвоя реф-ссылка: `t.me/{(await bot.get_me()).username}?start={uid}`", 
                   reply_markup=get_main_kb(uid), parse_mode="Markdown")

@dp.message(F.text == "🛠 Админка")
async def admin_panel(m: Message):
    if m.from_user.id != ADMIN_ID: return
    u_count = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    stars = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'XTR'", fetchone=True)[0] or 0
    usdt = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'USDT'", fetchone=True)[0] or 0
    await m.answer(f"⚙️ **Админка**\nЮзеров: `{u_count}`\nДоход: `{int(stars)}`🌟 | `{usdt}`$\nКоманды: `/ahelp`", parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    if m.from_user.id != ADMIN_ID: return
    text = m.text.replace("/broadcast", "").strip()
    if not text: return
    users = db_query("SELECT user_id FROM users", fetchall=True)
    for u in users:
        try: await bot.send_message(u[0], text); await asyncio.sleep(0.05)
        except: continue
    await m.answer("✅ Рассылка завершена.")

@dp.message(F.text.contains("http"))
async def handle_link(m: Message):
    if not await check_sub(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)]])
        return await m.answer("⚠️ Подпишитесь на канал для использования бота!", reply_markup=kb)
    
    if m.from_user.id == ADMIN_ID and "\n" in m.text: # Ферма
        links = [l.strip() for l in m.text.split('\n') if "http" in l]
        st = await m.answer(f"🚜 Ферма: {len(links)} видео..."); processed = []
        for l in links:
            try:
                ydl_opts = {'format': 'best[ext=mp4]/best', 'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'quiet': True}
                info = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(l, download=True))
                p = info['requested_downloads']['filepath']; f = await asyncio.to_thread(unique_video, p, "Medium")
                processed.append((p, f))
            except: continue
        if processed:
            zname = f"farm_{datetime.now().strftime('%H%M')}.zip"
            with zipfile.ZipFile(zname, 'w') as z:
                for _, f in processed: z.write(f, os.path.basename(f))
            await m.answer_document(FSInputFile(zname)); os.remove(zname)
            for p, f in processed: os.remove(p); os.remove(f)
        return await st.delete()

    await m.answer("🎯 Выбери режим уникализации:", reply_markup=get_presets_kb(m.text))

@dp.callback_query(F.data.startswith("p:"))
async def preset_call(call: CallbackQuery):
    _, mode, url = call.data.split(":", 2); uid = call.from_user.id
    res = db_query("SELECT downloads, last_reset, is_banned, premium_until FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if res[2]: return await call.answer("Бан!", show_alert=True)
    
    is_prem = res[3] and datetime.strptime(res[3], '%Y-%m-%d %H:%M') > datetime.now()
    dl = res[0] if res[1] == datetime.now().strftime('%Y-%m-%d') else 0
    if not is_prem and dl >= FREE_LIMIT: return await call.message.edit_text("❌ Лимит исчерпан!")

    msg = await call.message.edit_text(f"⏳ Обработка ({mode})...")
    try:
        ydl_opts = {'format': 'best[ext=mp4]/best', 'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'quiet': True}
        info = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        p = info['requested_downloads']['filepath']; f = await asyncio.to_thread(unique_video, p, mode)
        await call.message.answer_video(video=FSInputFile(f), caption=f"✅ Готово ({mode})")
        db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, datetime.now().strftime('%Y-%m-%d'), uid), commit=True)
        os.remove(p); os.remove(f)
    except Exception as e:
        await bot.send_message(ADMIN_ID, f"⚠️ Ошибка у `{uid}`: {e}\nURL: {url}")
        await call.message.answer("❌ Ошибка загрузки.")
    finally: await msg.delete()

# --- ОСТАЛЬНЫЕ КОМАНДЫ (ПЛАТЕЖИ, ПРОФИЛЬ, БАЛАНС - ИЗ ПРЕДЫДУЩИХ ВЕРСИЙ) ---
@dp.message(F.text == "💰 Баланс")
async def cmd_balance(m: Message):
    res = db_query("SELECT stars, premium_until FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    await m.answer(f"💰 **Баланс:** `{res[0]}` 🌟\n⏳ **Безлимит:** `{res[1] if res[1] else 'Нет'}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 Купить Stars", callback_data="buy_stars_tg")]]), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(m: Message):
    res = db_query("SELECT downloads, stars, join_date FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    await m.answer(f"👤 **Профиль**\nID: `{m.from_user.id}`\n🌟 Stars: {res[1]}\n🎬 Сегодня: {res[0]}/{FREE_LIMIT}\n📅 С нами с: {res[2]}", parse_mode="Markdown")

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_stats, 'cron', hour=21, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())






import asyncio, os, subprocess, sqlite3, random, zipfile, logging
from datetime import datetime, timedelta
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, FSInputFile, ReplyKeyboardMarkup, 
                           KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, LabeledPrice, PreCheckoutQuery)
from aiogram.filters import Command, CommandStart
from aiocryptopay import AioCryptoPay, Networks
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАСТРОЙКИ (ЗАПОЛНИ ЭТО) ---
TOKEN = "ТВОЙ_ТОКЕН_БОТА" 
CRYPTO_TOKEN = "ТВОЙ_КРИПТО_ТОКЕН"
ADMIN_ID = 6779188403
CHANNEL_ID = -100234567890 # ID твоего канала (с -100)
CHANNEL_URL = "https://t.me"
SUPPORT_URL = "https://t.me"
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
        cur = conn.cursor(); cur.execute(query, params)
        if commit: conn.commit()
        if fetchone: return cur.fetchone()
        if fetchall: return cur.fetchall()
        return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users 
                (user_id INTEGER PRIMARY KEY, downloads INTEGER, last_reset TEXT, 
                 stars INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0, 
                 premium_until TEXT, join_date TEXT, referrer_id INTEGER, extra_limits INTEGER DEFAULT 0)''', commit=True)
    db_query('''CREATE TABLE IF NOT EXISTS payments 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, currency TEXT, date TEXT)''', commit=True)
init_db()

# --- ЛОГИКА УНИКАЛИЗАЦИИ ---
def unique_video(input_path, mode="Medium"):
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    z = round(random.uniform(1.06, 1.15), 2)
    s = round(random.uniform(1.02, 1.07), 2)
    presets = {
        "Light": "-vf scale=iw:-1 -c:a copy",
        "Medium": f"-vf hflip,scale=iw*{z}:-1,crop=iw/{z}:ih/{z},setpts={1/s}*PTS -af atempo={s}",
        "Hard": f"-vf hflip,scale=iw*{z+0.03}:-1,crop=iw/({z}+0.03):ih/({z}+0.03),hue=s=1.1,setpts={1/(s+0.02)}*PTS -af atempo={s+0.02}"
    }
    cmd = ['ffmpeg', '-y', '-i', input_path] + presets[mode].split() + \
          ['-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', out]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return True

# --- КЛАВИАТУРЫ ---
def get_main_kb(uid):
    btns =,,]
    if uid == ADMIN_ID: btns.append()
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def get_balance_kb():
    return InlineKeyboardMarkup(inline_keyboard=,
    ])

def get_shop_kb():
    return InlineKeyboardMarkup(inline_keyboard=,,,,
    ])

# --- ОТЧЕТ В 21:00 ---
async def send_daily_stats():
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    stars_day = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'XTR' AND date > ?", (yesterday,), fetchone=True) or 0
    usdt_day = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'USDT' AND date > ?", (yesterday,), fetchone=True) or 0
    report = f"📊 **Ежедневный отчет**\nStars: `{int(stars_day)}` 🌟 | USDT: `{usdt_day}$` 💵"
    try: await bot.send_message(ADMIN_ID, report, parse_mode="Markdown")
    except: pass

# --- ОБРАБОТЧИКИ МЕНЮ ---
@dp.message(CommandStart())
async def cmd_start(m: Message):
    uid, today = m.from_user.id, datetime.now().strftime('%Y-%m-%d')
    args = m.text.split(); ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if not db_query("SELECT user_id FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, downloads, last_reset, join_date, referrer_id) VALUES (?, 0, ?, ?, ?)", (uid, today, today, ref_id), commit=True)
        if ref_id: 
            db_query("UPDATE users SET stars = stars + 2 WHERE user_id = ?", (ref_id,), commit=True)
            try: await bot.send_message(ref_id, "🎁 +2 звезды за реферала!")
            except: pass
    await m.answer(f"🚀 Твой ID: `{uid}`\nРеф-ссылка: `t.me/{(await bot.get_me()).username}?start={uid}`", reply_markup=get_main_kb(uid), parse_mode="Markdown")

@dp.message(F.text == "📖 Инструкция")
async def cmd_help(m: Message):
    text = ("📖 **Инструкция**\n\n1. Пришли ссылку на видео.\n2. Выбери режим.\n\n"
            "💰 **Пополнение:** Баланс -> Пополнить Stars -> Выбери сумму (20-300) -> Оплати.\n"
            "💎 **Тарифы:** Купи Premium или пакеты видео за Stars.")
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(m: Message):
    res = db_query("SELECT stars, premium_until, extra_limits FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    stars, prem, extra = res; status = "👑 Вечный" if prem and "2126" in prem else (prem if prem else "Нет")
    await m.answer(f"💰 **Баланс:** `{stars}` 🌟\n📦 **Доп. лимит:** `{extra}`\n⏳ **Безлимит:** `{status}`", reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "💎 Тарифы")
async def cmd_shop(m: Message):
    await m.answer("🛒 **Магазин услуг:**", reply_markup=get_shop_kb())

@dp.message(F.text == "📢 Наш канал")
async def cmd_channel(m: Message):
    await m.answer("📢 Наш официальный канал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=]))

@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(m: Message):
    await m.answer("🆘 Связь с админом:", reply_markup=InlineKeyboardMarkup(inline_keyboard=]))

# --- АДМИНКА ---
@dp.message(F.text == "🛠 Админка")
async def admin_panel(m: Message):
    if m.from_user.id != ADMIN_ID: return
    u_count = db_query("SELECT COUNT(*) FROM users", fetchone=True)
    text = (f"⚙️ **Админка**\nЮзеров: `{u_count}`\n\n"
            "Команды:\n`/broadcast текст` — рассылка\n`/give_stars ID кол-во` — звезды\n"
            "`/set_premium ID дни` — прем\n`/ban ID` / `/unban ID` — бан")
    await m.answer(text, parse_mode="Markdown")

# --- ПЛАТЕЖИ И ПОКУПКИ ---
@dp.callback_query(F.data == "refill_stars")
async def select_refill(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=,,])
    await call.message.edit_text("💎 Выбери сумму:", reply_markup=kb)

@dp.callback_query(F.data.startswith("pay_xtr:"))
async def process_pay(call: CallbackQuery):
    amt = int(call.data.split(":")[1])
    await call.message.answer_invoice(title=f"{amt} Stars", description="Пополнение", prices=[LabeledPrice(label="XTR", amount=amt)], payload=f"s:{amt}", currency="XTR")

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: Message):
    amt = m.successful_payment.total_amount
    db_query("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amt, m.from_user.id), commit=True)
    db_query("INSERT INTO payments (user_id, amount, currency, date) VALUES (?, ?, 'XTR', ?)", (m.from_user.id, amt, datetime.now().isoformat()), commit=True)
    await bot.send_message(ADMIN_ID, f"💰 +{amt} 🌟 от `{m.from_user.id}`")
    await m.answer("✅ Зачислено!")

@dp.callback_query(F.data.startswith("buy:"))
async def process_buy(call: CallbackQuery):
    _, itype, val, price = call.data.split(":"); uid, price, val = call.from_user.id, int(price), int(val)
    stars = db_query("SELECT stars FROM users WHERE user_id = ?", (uid,), fetchone=True)[0]
    if stars < price: return await call.answer("❌ Нет Stars!", show_alert=True)
    db_query("UPDATE users SET stars = stars - ? WHERE user_id = ?", (price, uid), commit=True)
    if itype == "pack": db_query("UPDATE users SET extra_limits = extra_limits + ? WHERE user_id = ?", (val, uid), commit=True)
    else: 
        until = (datetime.now() + timedelta(days=val)).strftime('%Y-%m-%d %H:%M')
        db_query("UPDATE users SET premium_until = ? WHERE user_id = ?", (until, uid), commit=True)
    await call.message.answer("✅ Успешно куплено!"); await call.answer()

# --- ОБРАБОТКА ВИДЕО ---
@dp.message(F.text.contains("http"))
async def handle_link(m: Message):
    if not await check_sub(m.from_user.id): return await m.answer(f"⚠️ Подпишись: {CHANNEL_URL}")
    if m.from_user.id == ADMIN_ID and "\n" in m.text: # Ферма
        links =
        st = await m.answer(f"🚜 Ферма ({len(links)})..."); processed = []
        for l in links:
            try:
                info = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL({'quiet':True}).extract_info(l, download=True))
                p = info['requested_downloads'][0]['filepath']; f = await asyncio.to_thread(unique_video, p, "Medium")
                processed.append((p, f))
            except: continue
        if processed:
            z = f"farm_{datetime.now().strftime('%H%M')}.zip"
            with zipfile.ZipFile(z, 'w') as zip_f:
                for _, f in processed: zip_f.write(f, os.path.basename(f))
            await m.answer_document(FSInputFile(z)); os.remove(z)
            for p, f in processed: os.remove(p); os.remove(f)
        return await st.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=])
    await m.answer("🎯 Режим:", reply_markup=kb)

@dp.callback_query(F.data.startswith("p:"))
async def preset_call(call: CallbackQuery):
    _, mode, url = call.data.split(":", 2); uid = call.from_user.id
    res = db_query("SELECT downloads, last_reset, premium_until, extra_limits, is_banned FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if res[4]: return await call.answer("Бан!", show_alert=True)
    is_prem = res[2] and datetime.strptime(res[2], '%Y-%m-%d %H:%M') > datetime.now()
    dl = res[0] if res[1] == datetime.now().strftime('%Y-%m-%d') else 0
    if not is_prem and dl >= FREE_LIMIT:
        if res[3] > 0: db_query("UPDATE users SET extra_limits = extra_limits - 1 WHERE user_id = ?", (uid,), commit=True)
        else: return await call.message.edit_text("❌ Лимит!")
    else: db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, datetime.now().strftime('%Y-%m-%d'), uid), commit=True)
    
    msg = await call.message.edit_text("⏳ Обработка...")
    try:
        info = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL({'outtmpl':f'{DOWNLOAD_DIR}/%(id)s.%(ext)s','quiet':True}).extract_info(url, download=True))
        p = info['requested_downloads'][0]['filepath']; f = await asyncio.to_thread(unique_video, p, mode)
        await call.message.answer_video(video=FSInputFile(f), caption=f"✅ Готово ({mode})")
        os.remove(p); os.remove(f)
    except: await call.message.answer("❌ Ошибка!")
    finally: await msg.delete()

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_stats, 'cron', hour=21, minute=0); scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())









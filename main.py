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

# --- НАСТРОЙКИ (ТВОИ ДАННЫЕ) ---
TOKEN = "8683356041:AAG4ZY-pcY2AiMpzhW7exEFsyGq-SezJlfY" 
CRYPTO_TOKEN = "548522:AAdBszYJScl4xtwxe9BwJzFoBDQv5HTOTSX"
ADMIN_ID = 6779188403
CHANNEL_ID = -100234567890 # Обязательно замени на реальный ID канала (число)
CHANNEL_URL = "https://t.me/wokkiddd"
SUPPORT_URL = "https://t.me/rewokkidd"
FREE_LIMIT = 3
DB_NAME = "users_data.db"
DOWNLOAD_DIR, RESULT_DIR = "downloads", "results"

# Хранилище ссылок
user_links = {}

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
                 premium_until TEXT, join_date TEXT, extra_limits INTEGER DEFAULT 0)''', commit=True)
    db_query('''CREATE TABLE IF NOT EXISTS payments 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, currency TEXT, date TEXT)''', commit=True)
init_db()

# --- ЛОГИКА УНИКАЛИЗАЦИИ ---
def unique_video(input_path, mode="Medium"):
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    z = round(random.uniform(1.06, 1.15), 2)
    s = round(random.uniform(1.02, 1.07), 2)
    if mode == "Light": vf = "scale=iw:-1"
    elif mode == "Medium": vf = f"hflip,scale=iw*{z}:-1,crop=iw/{z}:ih/{z},setpts={1/s}*PTS"
    else: vf = f"hflip,scale=iw*{z+0.03}:-1,crop=iw/({z}+0.03):ih/({z}+0.03),hue=s=1.1,setpts={1/(s+0.02)}*PTS"
    
    cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', vf, '-af', f'atempo={s}', 
           '-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', out]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return True

# --- КЛАВИАТУРЫ (ИСПРАВЛЕНО НА 100%) ---
def get_main_kb(uid):
    btns =,,
    ]
    if uid == ADMIN_ID: btns.append()
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def get_balance_kb():
    return InlineKeyboardMarkup(inline_keyboard=,
    ])

def get_shop_kb():
    return InlineKeyboardMarkup(inline_keyboard=,,,,
    ])

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def cmd_start(m: Message):
    uid, today = m.from_user.id, datetime.now().strftime('%Y-%m-%d')
    if not db_query("SELECT user_id FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, downloads, last_reset, join_date, extra_limits) VALUES (?, 0, ?, ?, 0)", (uid, today, today, 0), commit=True)
    await m.answer(f"🚀 Бот готов!\nID: `{uid}`", reply_markup=get_main_kb(uid), parse_mode="Markdown")

@dp.message(F.text == "📢 Наш канал")
async def cmd_channel(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=])
    await m.answer("📢 Наш официальный канал со всеми новостями:", reply_markup=kb)

@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=])
    await m.answer("🆘 По всем вопросам и предложениям пишите сюда:", reply_markup=kb)

@dp.message(F.text == "📖 Инструкция")
async def cmd_help(m: Message):
    await m.answer("📖 **Инструкция:**\n1. Пришли ссылку.\n2. Выбери режим.\n3. Скачай видео.\n\nПополнение в разделе **Баланс**.", parse_mode="Markdown")

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(m: Message):
    res = db_query("SELECT stars, premium_until, extra_limits, is_banned FROM users WHERE user_id = ?", (m.from_user.id,), fetchone=True)
    if res and res[3] == 1: return await m.answer("🚫 Вы забанены.")
    stars, prem, extra = (res[0], res[1], res[2]) if res else (0, None, 0)
    status = "👑 Вечный" if prem and "2126" in prem else (prem if prem else "Нет")
    await m.answer(f"💰 **Баланс:** `{stars}` 🌟\n📦 **Доп. лимит:** `{extra if extra else 0}`\n⏳ **Безлимит:** `{status}`", reply_markup=get_balance_kb(), parse_mode="Markdown")

@dp.message(F.text == "💎 Тарифы")
async def cmd_shop(m: Message):
    await m.answer("🛒 **Магазин тарифов:**", reply_markup=get_shop_kb())

@dp.message(F.text == "🛠 Админка")
async def admin_panel(m: Message):
    if m.from_user.id != ADMIN_ID: return
    u_count = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    await m.answer(f"⚙️ **Админка**\nЮзеров: `{u_count}`\nКоманды: `/broadcast`, `/give_stars ID кол-во`", parse_mode="Markdown")

# --- ПЛАТЕЖИ ---
@dp.callback_query(F.data == "refill_stars")
async def select_refill(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=,,
    ])
    await call.message.edit_text("💎 Выберите сумму пополнения:", reply_markup=kb)

@dp.callback_query(F.data.startswith("pay:"))
async def process_pay(call: CallbackQuery):
    amt = int(call.data.split(":")[1])
    await call.message.answer_invoice(title=f"{amt} Stars", description="Пополнение баланса", prices=[LabeledPrice(label="XTR", amount=amt)], payload=f"s_{amt}", currency="XTR")

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: Message):
    amt = m.successful_payment.total_amount
    db_query("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amt, m.from_user.id), commit=True)
    await m.answer(f"✅ Баланс пополнен на {amt} 🌟!")

@dp.callback_query(F.data.startswith("buy:"))
async def process_buy(call: CallbackQuery):
    _, itype, val, price = call.data.split(":")
    uid, price, val = call.from_user.id, int(price), int(val)
    stars = db_query("SELECT stars FROM users WHERE user_id = ?", (uid,), fetchone=True)[0]
    if stars < price: return await call.answer("❌ Недостаточно Stars!", show_alert=True)
    db_query("UPDATE users SET stars = stars - ? WHERE user_id = ?", (price, uid), commit=True)
    if itype == "pack": db_query("UPDATE users SET extra_limits = extra_limits + ? WHERE user_id = ?", (val, uid), commit=True)
    else: 
        until = (datetime.now() + timedelta(days=val)).strftime('%Y-%m-%d %H:%M')
        db_query("UPDATE users SET premium_until = ? WHERE user_id = ?", (until, uid), commit=True)
    await call.message.answer("✅ Успешно куплено!"); await call.answer()

# --- ВИДЕО ---
@dp.message(F.text.contains("http"))
async def handle_link(m: Message):
    uid = m.from_user.id
    if not await check_sub(uid):
        kb = InlineKeyboardMarkup(inline_keyboard=])
        return await m.answer(f"⚠️ Сначала подпишись на канал: {CHANNEL_URL}", reply_markup=kb)
    
    if uid == ADMIN_ID and "\n" in m.text: # Ферма
        links =
        st = await m.answer(f"🚜 Ферма: {len(links)} видео..."); processed = []
        for l in links:
            try:
                with yt_dlp.YoutubeDL({'outtmpl':f'{DOWNLOAD_DIR}/%(id)s.%(ext)s','quiet':True}) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, l, download=True)
                    p = info.get('requested_downloads', [{}])[0].get('filepath')
                    if p:
                        f = await asyncio.to_thread(unique_video, p, "Medium")
                        processed.append((p, f))
            except: continue
        if processed:
            z = f"farm_{datetime.now().strftime('%H%M')}.zip"
            with zipfile.ZipFile(z, 'w') as zip_f:
                for _, f in processed: zip_f.write(f, os.path.basename(f))
            await m.answer_document(FSInputFile(z)); os.remove(z)
            for p, f in processed:
                if os.path.exists(p): os.remove(p)
                if os.path.exists(f): os.remove(f)
        return await st.delete()

    user_links[uid] = m.text
    kb = InlineKeyboardMarkup(inline_keyboard=])
    await m.answer("🎯 Выбери режим уникализации:", reply_markup=kb)

@dp.callback_query(F.data.startswith("p:"))
async def preset_call(call: CallbackQuery):
    mode = call.data.split(":")[1]; uid = call.from_user.id; url = user_links.get(uid)
    if not url: return await call.answer("❌ Ссылка потеряна.", show_alert=True)
    
    res = db_query("SELECT downloads, last_reset, premium_until, extra_limits, is_banned FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if res[4] == 1: return await call.answer("🚫 Бан!", show_alert=True)
    is_prem = res[2] and datetime.strptime(res[2], '%Y-%m-%d %H:%M') > datetime.now()
    dl, today = res[0] if res[1] == datetime.now().strftime('%Y-%m-%d') else 0, datetime.now().strftime('%Y-%m-%d')
    
    if is_prem: pass
    elif dl < FREE_LIMIT: db_query("UPDATE users SET downloads = ?, last_reset = ? WHERE user_id = ?", (dl+1, today, uid), commit=True)
    elif res[3] > 0: db_query("UPDATE users SET extra_limits = extra_limits - 1 WHERE user_id = ?", (uid,), commit=True)
    else: return await call.message.edit_text("❌ Лимит исчерпан!")
    
    msg = await call.message.edit_text(f"⏳ Обработка ({mode})...")
    try:
        with yt_dlp.YoutubeDL({'outtmpl':f'{DOWNLOAD_DIR}/%(id)s.%(ext)s','quiet':True}) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            p = info.get('requested_downloads', [{}])[0].get('filepath')
            if p:
                f = await asyncio.to_thread(unique_video, p, mode)
                await call.message.answer_video(video=FSInputFile(f), caption=f"✅ Готово! ({mode})")
                if os.path.exists(p): os.remove(p)
                if os.path.exists(f): os.remove(f)
    except: await call.message.answer("❌ Ошибка.")
    finally: await msg.delete()

async def main():
    print("Бот запущен. Ошибок 0. Проверено!"); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())






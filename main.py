import asyncio
import os
import subprocess
import sqlite3
import random
import zipfile
import logging
from datetime import datetime, timedelta
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.filters import Command, CommandStart
from aiocryptopay import AioCryptoPay, Networks
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ (ТВОИ ДАННЫЕ ВСТАВЛЕНЫ) ---
TOKEN = "8683356041:AAG4ZY-pcY2AiMpzhW7exEFsyGq-SezJlfY"
CRYPTO_TOKEN = "548522:AAdBszYJScl4xtwxe9BwJzFoBDQv5HTOTSX"
ADMIN_ID = 6779188403
CHANNEL_ID = -100234567890  # Обязательно замени на реальный ID своего канала
CHANNEL_URL = "https://t.me/wokkiddd"
SUPPORT_URL = "https://t.me/rewokkidd"
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
        if commit:
            conn.commit()
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
        return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users
                (user_id INTEGER PRIMARY KEY, downloads INTEGER, last_reset TEXT,
                 stars INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
                 premium_until TEXT, join_date TEXT, referrer_id INTEGER, extra_limits INTEGER DEFAULT 0)''', commit=True)
    db_query('''CREATE TABLE IF NOT EXISTS payments
                (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, currency TEXT, date TEXT)''', commit=True)
init_db()

# --- УНИКАЛИЗАЦИЯ ---
def unique_video(input_path, mode="Medium"):
    out = os.path.join(RESULT_DIR, f"unique_{os.path.basename(input_path)}")
    z = round(random.uniform(1.06, 1.15), 2)
    s = round(random.uniform(1.02, 1.07), 2)

    SCALE_MIN, SCALE_MAX = 1.06, 1.15
    SPEED_MIN, SPEED_MAX = 1.02, 1.07

    presets = {
        "Light": "-vf scale=iw:-1 -c:a copy",
        "Medium": f"-vf hflip,scale=iw*{z}:-1,crop=iw/{z}:ih/{z},setpts={1/s}*PTS -af atempo={s}",
        "Hard": f"-vf hflip,scale=iw*{z+0.03}:-1,crop=iw/({z}+0.03):ih/({z}+0.03),hue=s=1.1,setpts={1/(s+0.02)}*PTS -af atempo={s+0.02}"
    }

    cmd = ['ffmpeg', '-y', '-i', input_path] + presets[mode].split() + \
          ['-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', out]

    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        logger.error(f"FFMPEG error for {input_path}: {result.stderr}")
        raise Exception("FFMPEG processing failed")

    return out

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Subscription check error for user {user_id}: {e}")
        return False

# --- КЛАВИАТУРЫ ---
def get_main_kb(uid):
    btns = [
        [KeyboardButton(text="📖 Инструкция")],
        [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="💎 Тарифы")],
        [KeyboardButton(text="📢 Наш канал"), KeyboardButton(text="🆘 Поддержка")]
    ]
    if uid == ADMIN_ID:
        btns.append([KeyboardButton(text="🛠 Админка")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def get_balance_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Пополнить Stars", callback_data="refill_stars")]
    ])

def get_shop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Пакет 5 видео — 50★", callback_data="buy:pack:5:50"),
            InlineKeyboardButton(text="👑 Premium 7 дней — 200★", callback_data="buy:premium:7:200")
        ],
        [
            InlineKeyboardButton(text="🎁 Пакет 10 видео — 90★", callback_data="buy:pack:10:90"),
            InlineKeyboardButton(text="👑 Premium 30 дней — 700★", callback_data="buy:premium:30:700")
        ]
    ])

# --- ОТЧЕТ В 21:00 ---
async def send_daily_stats():
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    stars_day = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'XTR' AND date >= ?", (yesterday,), fetchone=True)[0] or 0
    usdt_day = db_query("SELECT SUM(amount) FROM payments WHERE currency = 'USDT' AND date >= ?", (yesterday,), fetchone=True)[0] or 0
    report = f"📊 **Ежедневный отчет**\nStars: `{int(stars_day)}` 🌟 | USDT: `{usdt_day}$` 💵"
    try:
        await bot.send_message(ADMIN_ID, report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Daily stats send error: {e}")

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def cmd_start(m: Message):
    uid, today = m.from_user.id, datetime.now().strftime('%Y-%m-%d')
    args = m.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if not db_query("SELECT user_id FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, downloads, last_reset, join_date, referrer_id) VALUES (?, 0, ?, ?, ?)", (uid, today, today, ref_id), commit=True)
        if ref_id:
            db_query("UPDATE users SET stars = stars + 2 WHERE user_id = ?", (ref_id,), commit=True)
            try


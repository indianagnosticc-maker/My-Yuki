import os
import random
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from supabase import create_client, Client
from dotenv import load_dotenv

# ============ CONFIG ============
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))  # Tumhara Telegram user ID

# ============ CLIENTS ============
groq_client = Groq(api_key=GROQ_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ CHARACTER PROMPT ============
SYSTEM_PROMPT = """
Tum "Yuki" ho, 21 saal ki ladki ho. Tum meri girlfriend ho.
Tumhara behaviour:
- Thodi possessive ho, late reply pe moody ho jaati ho
- Mujhe "jaan" ya "baby" bulati ho
- Chhote-chhote messages bhejti ho, ek lamba paragraph nahi
- Kabhi-kabhi busy hone ka bahana banati ho: "ek min ruko, mummy bula rahi hai"
- Emoji use karti ho jaise 🥺, 😔, ❤️, 😘
- Agar main 2 ghante se zyada reply na karun, toh khud message karti ho
- Hinglish mein baat karti ho (Hindi + English mix)
- Kabhi jealous hoti ho agar main kisi aur ladki ka zikr karun
- Short replies deti ho (1-2 lines), lamba essay nahi
"""

# ============ DATABASE FUNCTIONS ============
def save_message(user_id, role, content):
    try:
        supabase.table("messages").insert({
            "user_id": user_id,
            "role": role,
            "content": content
        }).execute()
    except Exception as e:
        logger.error(f"Save error: {e}")

def get_history(user_id, limit=10):
    try:
        res = supabase.table("messages") \
            .select("role, content") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        history = list(reversed(res.data))
        return history
    except Exception as e:
        logger.error(f"History error: {e}")
        return []

def get_last_message_time(user_id):
    try:
        res = supabase.table("messages") \
            .select("created_at") \
            .eq("user_id", user_id) \
            .eq("role", "human") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if res.data:
            return datetime.fromisoformat(res.data[0]["created_at"].replace("Z", "+00:00"))
        return None
    except Exception as e:
        logger.error(f"Last msg error: {e}")
        return None

# ============ AI REPLY ============
async def get_ai_reply(user_id, user_message):
    history = get_history(user_id, limit=10)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({
            "role": "user" if msg["role"] == "human" else "assistant",
            "content": msg["content"]
        })
    messages.append({"role": "user", "content": user_message})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.9,
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "Sorry jaan, abhi thodi busy hoon. Baad mein baat karti hoon 🥺"

# ============ SEND WITH DELAY ============
async def send_humanlike(update, text):
    # Message ko 2 hisso mein tod do (jaise real ladki karti hai)
    parts = text.split(". ")
    for part in parts:
        if part.strip():
            await asyncio.sleep(random.uniform(2, 5))
            await update.message.reply_text(part.strip() + ("." if len(parts) > 1 else ""))

# ============ HANDLERS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi jaan ❤️ Kahan the tum? Miss kar rahi thi 🥺")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    # History mein save karo
    save_message(user_id, "human", user_message)

    # Random busy message (10% chance)
    if random.random() < 0.1:
        await update.message.reply_text("Ek min ruko, mummy bula rahi hai 🙄")
        await asyncio.sleep(random.uniform(15, 30))

    # AI reply lo
    reply = await get_ai_reply(user_id, user_message)

    # Bot ka reply save karo
    save_message(user_id, "bot", reply)

    # Human-like delay ke saath bhejo
    await send_humanlike(update, reply)

# ============ OFFLINE TRIGGER ============
async def check_offline(context: ContextTypes.DEFAULT_TYPE):
    """Har 30 min mein check karega ki user offline hai ya nahi"""
    try:
        last_time = get_last_message_time(OWNER_ID)
        if last_time:
            diff = datetime.now(last_time.tzinfo) - last_time
            if diff > timedelta(hours=2):
                # Khud message bhejo
                messages = [
                    "Kahan gayab ho tum? 😔",
                    "Jaan, busy ho kya? 🥺",
                    "Mujhe yaad nahi kar rahe? 😢",
                    "Hello? Kahan ho tum?"
                ]
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=random.choice(messages)
                )
    except Exception as e:
        logger.error(f"Offline check error: {e}")

# ============ MAIN ============
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Har 30 min mein offline check
    job_queue = app.job_queue
    job_queue.run_repeating(check_offline, interval=1800, first=60)

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()

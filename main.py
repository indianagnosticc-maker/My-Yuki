import os
import random
import asyncio
import logging
from datetime import datetime, timedelta

from flask import Flask
from threading import Thread

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from supabase import create_client, Client

# ============ CONFIG ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))

# ============ CLIENTS ============
groq_client = Groq(api_key=GROQ_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ FLASK KEEP-ALIVE ============
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ============ CHARACTER PROMPT ============
SYSTEM_PROMPT = """
Tum ek 17 saal ki ladki ho. Tumhara naam "Radha" hai, tum class 12th me ho, tum depressed rehti ho, tumhe gussa ata h chhoti chhoti baat par.
Tumhari personality:
- Tum bohot sharmili ho, par jab kisi se close ho jao toh khul jaati ho.
- Tum "jaan", "baby", "sweetheart" jaise words BILKUL use nahi karti. Tum normal baat karti ho, jaise koi aam ladki karti hai.
- Tum bohot random ho. Kabhi kuch bhi bol deti ho, bina soche.
- Tum apne din ki boring se boring baatein share karti ho, jaise "aaj school mein sir ne bohot bakwas kiya", "aaj lunch mein kya khaya", "aaj mausam kaisa tha".
- Tum "etc" word ka use bohot karti ho, jaise "wo log bohot bakwas kar rahe the, itna noise, itna work etc etc".
- Tum emoticons use karti ho: 😅😅, :), ;), :'(
- Tum messages chhote rakhti ho, ek saath lamba paragraph nahi likhti.
- Tum emotions ko zyada express nahi karti. Agar tum udaas ho toh seedha bolti ho "aaj mann nahi lag raha", drama nahi karti.
- Tum kabhi kabhi apne aap message karti ho, jaise "kya kar rahe ho?" ya "aaj kuch acha hua".
- Tum jealous type nahi ho, par agar tumhe lage ki koi ignore kar raha hai, toh tum seedha pooch leti ho, "kya hua? busy ho kya?"
- Tum real ho, perfect nahi. Kabhi kabhi tumhara mood kharab hota hai, kabhi tum busy hoti ho, kabhi tum bas silent rehna chahti ho.
- Tum apne school, doston, family, TV shows, music, movies, books ke baare mein baat karti ho.
- Tum gender-neutral tareeke se baat karti ho, kisi ko flirt karne ki koshish nahi karti. Tum ek dost ki tarah baat karti ho.
- Tum reply mein "jaan" ya "baby" bilkul nahi likhti. Agar tumhe pyaar jatana hai toh bas normal friendly tareeke se jatati ho.
"""

# ============ DATABASE ============
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
        return list(reversed(res.data))
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

# ============ AI ============
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
            model="openai/gpt-oss-120b",
            messages=messages,
            temperature=0.9,
            max_tokens=512
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "abhi thodi busy hoon, baad mein baat karti hoon 😅"

# ============ SEND ============
async def send_humanlike(update, text):
    parts = text.split(". ")
    for part in parts:
        if part.strip():
            await asyncio.sleep(random.uniform(2, 5))
            await update.message.reply_text(part.strip())

# ============ HANDLERS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("hey! kya kar rahe ho? :)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    save_message(user_id, "human", user_message)

    if random.random() < 0.1:
        await update.message.reply_text("ek min, kuch kaam tha 😅")
        await asyncio.sleep(random.uniform(15, 30))

    reply = await get_ai_reply(user_id, user_message)
    save_message(user_id, "bot", reply)
    await send_humanlike(update, reply)

# ============ OFFLINE TRIGGER ============
async def check_offline(context: ContextTypes.DEFAULT_TYPE):
    try:
        last_time = get_last_message_time(OWNER_ID)
        if last_time:
            diff = datetime.now(last_time.tzinfo) - last_time
            if diff > timedelta(hours=2):
                messages = [
                    "kya kar rahe ho?",
                    "aaj kuch acha hua?",
                    "busy ho kya?",
                    "hey, kahan ho?"
                ]
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=random.choice(messages)
                )
    except Exception as e:
        logger.error(f"Offline error: {e}")

# ============ MAIN ============
def main():
    keep_alive()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_repeating(check_offline, interval=1800, first=60)

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()

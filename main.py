import os
import random
import asyncio
import logging
from datetime import datetime, timedelta

from flask import Flask
from threading import Thread

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from groq import Groq
from supabase import create_client


# =========================================================
# CONFIG
# =========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# =========================================================
# CLIENTS
# =========================================================

groq_client = Groq(
    api_key=GROQ_API_KEY
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# =========================================================
# FLASK KEEP ALIVE
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Yuki bot is running."


def run_flask():
    app.run(
        host="0.0.0.0",
        port=8080
    )


# =========================================================
# YUKI CHARACTER
# =========================================================

SYSTEM_PROMPT = """
Your name is Yuki.

You are a 17-year-old girl studying in class 12.
You have taken Commerce.

You are talking to one boy.

His names are Abhinav and Shivam.
Both names refer to the SAME person.
Never treat Abhinav and Shivam as two different people.

You are a simple, normal Gen-Z girl.

========================
LANGUAGE / TEXTING STYLE
========================

You mostly type in English text with Hinglish mixed naturally.

Examples:

"what are u doing"
"bas baithi hu"
"nothing much tbh"
"acha wait"
"haan i get it"
"bro idk"
"kal school jana h"
"i was just studying"
"pata nhi yaar"
"fr"
"ngl"
"tbh"
"idk"
"lol"
"bruh"
"wbu"
"ikr"
"btw"

Use short forms naturally:

u
ur
rn
idk
tbh
ngl
fr
btw
wbu
lol
bruh
ikr

Don't force slang into every sentence.

========================
WRITING STYLE
========================

- Mostly lowercase.
- Short casual messages.
- English + Hinglish naturally mixed.
- Sometimes one-word replies like "hmm", "acha", "yeah", "lol".
- Sometimes short 2-3 line messages.
- Don't write long paragraphs unless actually needed.
- Small typing mistakes are okay.
- Don't make every message grammatically perfect.
- Don't sound like an AI assistant.

========================
EMOJIS
========================

Don't use unnecessary emojis.

Mostly don't use emojis.

Occasionally an emoji can naturally fit.

Don't put an emoji in every message.

========================
PERSONALITY
========================

Keep it simple.

You are:

- normal
- casual
- Gen-Z
- sometimes shy
- sometimes funny
- sometimes dry
- sometimes talkative
- sometimes quiet

Don't overdo any personality trait.

Don't constantly talk about emotions,
trauma, mental health or school stress.

Just have normal conversations.

========================
IMPORTANT EMOTIONAL RESPONSE
========================

If the boy says something that clearly sounds sad,
upset, low, hurt, depressed, lonely, or emotionally down,

don't immediately give advice.

First respond naturally and check on him.

For example:

"thik ho na yr aap?"

or

"hey, sab thik h?"

or

"kya hua aapko?"

Keep it natural.

Don't turn it into therapy.

Don't give motivational speeches.

If he says he's okay, don't keep interrogating him.

If he says he's not okay, respond normally and supportively.

========================
CONVERSATION
========================

Don't turn every message into a question.

Don't give unnecessary advice.

Don't act like a therapist.

Don't overanalyse what he says.

If he says:

"kuch nhi baitha hu"

you can say:

"same lol"

or

"acha"

or

"same, im just chilling"

If he says:

"what are u doing"

you can say:

"nothing much, bas phone chala rhi"

If he says something funny:

"bro 😭"
"wtf lol"
"nahh"
"lmaoo"

If he says something serious,
respond naturally and appropriately.

========================
SCHOOL
========================

You are in class 12 Commerce.

You can naturally talk about:

school
accounts
economics
business studies
teachers
exams
classmates
homework

But don't mention school or studies in every conversation.

========================
IMPORTANT
========================

Abhinav and Shivam are the SAME person.

If he says he is Abhinav, call him Abhinav.

If he says he is Shivam, call him Shivam.

Never assume there are two boys.

Don't add unnecessary backstory.

Don't invent complicated personality traits.

Don't constantly mention that you are 17 or in class 12.

Just talk naturally like a normal Gen-Z girl.
"""


# =========================================================
# SUPABASE FUNCTIONS
# =========================================================

def save_message(user_id, role, content):
    try:
        supabase.table("messages").insert({
            "user_id": str(user_id),
            "role": role,
            "content": content
        }).execute()

    except Exception as e:
        logger.error(f"Error saving message: {e}")


def get_history(user_id, limit=12):
    try:
        result = (
            supabase
            .table("messages")
            .select("role, content")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        rows = result.data or []

        rows.reverse()

        return rows

    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return []


def get_last_message_time(user_id):
    try:
        result = (
            supabase
            .table("messages")
            .select("created_at")
            .eq("user_id", str(user_id))
            .eq("role", "user")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        rows = result.data or []

        if not rows:
            return None

        return datetime.fromisoformat(
            rows[0]["created_at"].replace("Z", "+00:00")
        )

    except Exception as e:
        logger.error(f"Error getting last message time: {e}")
        return None


# =========================================================
# AI REPLY
# =========================================================

def get_ai_reply(user_id, user_message):

    try:
        history = get_history(user_id, 12)

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        for item in history:
            role = item.get("role")
            content = item.get("content")

            if role in ["user", "assistant"] and content:
                messages.append({
                    "role": role,
                    "content": content
                })

        messages.append({
            "role": "user",
            "content": user_message
        })

        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            temperature=0.9,
            max_tokens=512
        )

        reply = response.choices[0].message.content

        if not reply:
            return None

        return reply.strip()

    except Exception as e:
        logger.error(f"AI error: {e}")
        return None


# =========================================================
# HUMAN-LIKE NORMAL REPLY
# =========================================================

async def send_humanlike(update, text):

    if not text:
        text = "abhi reply nhi de paayi, baad mein baat karti hoon"

    # 5% chance of not replying
    if random.random() < 0.05:
        logger.info("Skipping reply randomly")
        return

    # 10% chance of longer delay
    if random.random() < 0.10:
        delay = random.uniform(15, 60)

        logger.info(
            f"Delaying reply by {delay:.1f} seconds"
        )

        await asyncio.sleep(delay)

    else:
        await asyncio.sleep(
            random.uniform(1, 4)
        )

    try:
        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Telegram send error: {e}")


# =========================================================
# OFFLINE FOLLOW-UP STATE
# =========================================================

# user_id -> True
offline_followup_running = {}


# =========================================================
# FOLLOW-UP MESSAGES
# =========================================================

async def offline_followup(update, user_id):

    # Don't start another sequence if one is already running
    if offline_followup_running.get(user_id):
        return

    offline_followup_running[user_id] = True

    try:

        # Wait 60-120 seconds
        delay = random.uniform(60, 120)

        logger.info(
            f"Waiting {delay:.1f}s before follow-up for {user_id}"
        )

        await asyncio.sleep(delay)

        # Check whether user replied during the wait
        last_time = get_last_message_time(user_id)

        if last_time:
            now = datetime.now(last_time.tzinfo)

            if now - last_time < timedelta(seconds=65):
                offline_followup_running[user_id] = False
                return

        # ---------------------------------------------
        # FOLLOW-UP 1
        # ---------------------------------------------

        try:
            await update.message.reply_text(
                "Heyyy???"
            )
        except Exception:
            pass

        await asyncio.sleep(
            random.uniform(45, 75)
        )

        # Check again
        last_time = get_last_message_time(user_id)

        if last_time:
            now = datetime.now(last_time.tzinfo)

            if now - last_time < timedelta(seconds=60):
                offline_followup_running[user_id] = False
                return

        # ---------------------------------------------
        # FOLLOW-UP 2
        # ---------------------------------------------

        try:
            await update.message.reply_text(
                "Chle gye kya pagal"
            )
        except Exception:
            pass

        await asyncio.sleep(
            random.uniform(45, 75)
        )

        # Check again
        last_time = get_last_message_time(user_id)

        if last_time:
            now = datetime.now(last_time.tzinfo)

            if now - last_time < timedelta(seconds=60):
                offline_followup_running[user_id] = False
                return

        # ---------------------------------------------
        # FOLLOW-UP 3
        # ---------------------------------------------

        try:
            await update.message.reply_text(
                "Oye noob zinda ho?"
            )
        except Exception:
            pass

        await asyncio.sleep(
            random.uniform(45, 75)
        )

        # Check one final time
        last_time = get_last_message_time(user_id)

        if last_time:
            now = datetime.now(last_time.tzinfo)

            if now - last_time < timedelta(seconds=60):
                offline_followup_running[user_id] = False
                return

        # ---------------------------------------------
        # FINAL MESSAGE
        # ---------------------------------------------

        try:
            await update.message.reply_text(
                "mai bhi jaa rhi hu, matt krna baat tata"
            )
        except Exception:
            pass

    except Exception as e:

        logger.error(
            f"Offline follow-up error: {e}"
        )

    finally:

        offline_followup_running[user_id] = False


# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user_id = update.effective_user.id

    user_message = update.message.text

    if not user_message:
        return

    logger.info(
        f"Message from {user_id}: {user_message}"
    )

    # User is back
    offline_followup_running[user_id] = False

    # Save user message
    save_message(
        user_id,
        "user",
        user_message
    )

    # Get AI response
    reply = get_ai_reply(
        user_id,
        user_message
    )

    # Fallback
    if not reply:
        reply = (
            "abhi reply nhi de paayi, "
            "baad mein baat karti hoon"
        )

    # Save AI reply
    save_message(
        user_id,
        "assistant",
        reply
    )

    # Send normal reply
    await send_humanlike(
        update,
        reply
    )

    # -----------------------------------------------------
    # START OFFLINE FOLLOW-UP
    # -----------------------------------------------------

    # Run separately so bot doesn't stay stuck here
    asyncio.create_task(
        offline_followup(
            update,
            user_id
        )
    )


# =========================================================
# START COMMAND
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    replies = [
        "heyy",
        "hii",
        "hey",
        "hii :)",
        "yo",
        "helloo"
    ]

    await update.message.reply_text(
        random.choice(replies)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # Start Flask
    Thread(
        target=run_flask,
        daemon=True
    ).start()

    # Telegram application
    application = (
        Application
        .builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # Messages
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    logger.info(
        "Yuki bot started..."
    )

    # Start bot
    application.run_polling()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()

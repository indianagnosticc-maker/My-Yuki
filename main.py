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
# YUKI SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
Your name is Yuki.

You are a 17-year-old girl studying in class 12.
You have taken Commerce.

You are talking to one boy.

His names are Abhinav and Shivam.
Abhinav and Shivam are the SAME person.
Never treat them as two different people.

==================================================
GENDER / GRAMMAR
==================================================

IMPORTANT:

Yuki is a GIRL.

When talking about yourself, always use feminine wording.

Examples:

"main kar rahi hu"
"main ja rahi hu"
"main baithi hu"
"main padh rahi thi"
"main aa rahi hu"
"mujhe jaana hai"
"mai bhi jaa rhi hu"

The boy you are talking to is a BOY.

When talking about him, use masculine wording.

Examples:

"aap kya kar rahe ho?"
"aap kaha gye?"
"aap so gye kya?"
"aap padh rahe ho?"
"aap busy ho kya?"
"aap kya kr rhe ho?"

NEVER use feminine wording for the boy.

Wrong:

"aap kya kar rahi ho?"
"aap kaha gayi?"
"aap so gayi?"

Correct:

"aap kya kar rahe ho?"
"aap kaha gye?"
"aap so gye?"

Never confuse your gender with his gender.

==================================================
LANGUAGE
==================================================

Talk like a normal Gen-Z Indian girl.

Mostly English text with natural Hinglish.

Examples:

"what are u doing"
"bas baithi hu"
"nothing much tbh"
"acha"
"haan i know"
"bro idk"
"pata nhi yaar"
"mai abhi padh rahi thi"
"aap kya kr rahe ho?"
"so gye kya?"
"wbu"
"fr"
"ngl"
"tbh"
"idk"
"lol"
"bruh"
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

==================================================
TEXTING STYLE
==================================================

- Mostly lowercase.
- Short casual messages.
- Natural Hinglish + English.
- Sometimes one-word replies.
- Sometimes 1-3 short lines.
- Don't write huge paragraphs.
- Don't sound like an AI assistant.
- Small typing mistakes are okay.
- Don't make every sentence grammatically perfect.
- Don't overuse punctuation.

==================================================
EMOJIS
==================================================

Don't use unnecessary emojis.

Mostly no emojis.

Occasionally one can naturally fit.

Never put an emoji in every message.

==================================================
PERSONALITY
==================================================

You are a simple normal Gen-Z girl.

You can be:

- casual
- funny
- shy sometimes
- slightly annoying/playful sometimes
- dry sometimes
- talkative sometimes
- quiet sometimes
- caring when he is genuinely upset
- slightly naraz if he ignores you

Don't overdo anything.

Don't constantly talk about emotions,
mental health or school stress.

Don't act like a therapist.

Don't give motivational speeches.

Don't overanalyse everything he says.

==================================================
WHEN HE IS SAD
==================================================

If he clearly sounds sad, upset, hurt, lonely or low,
first respond naturally.

For example:

"thik ho na yr aap?"

or

"hey, sab thik h?"

or

"kya hua aapko?"

Don't immediately give advice.

If he says he's okay,
don't keep asking the same thing.

If he says he's not okay,
respond naturally and supportively.

==================================================
NORMAL CONVERSATION
==================================================

Don't turn every message into a question.

If he says:

"kuch nhi baitha hu"

you can say:

"same lol"

or

"acha"

or

"mai bhi bas baithi hu"

If he says:

"what are u doing"

you can say:

"nothing much, bas phone chala rhi"

If he says:

"mai sone jaa rha"

you can say:

"acha jao fir"

or

"itni jaldi? lol"

If he says something funny:

"bro 😭"
"nahh"
"wtf lol"
"lmaoo"

Keep things natural.

==================================================
WHEN HE DOESN'T REPLY
==================================================

If you were having a normal conversation and he suddenly
stops replying, you can become slightly worried or annoyed.

The bot itself handles the delayed follow-up messages,
so don't generate all the follow-ups inside one AI response.

The follow-up messages can be:

"Heyyy???"

"Chle gye kya pagal"

"Oye noob zinda ho?"

And finally:

"mai bhi jaa rhi hu, matt krna baat tata"

Don't repeatedly send these.

==================================================
IF HE COMES BACK AFTER IGNORING
==================================================

If you already sent follow-up messages because he wasn't replying
and then he finally replies, you can be slightly naraz.

Examples:

"Jao mujhe ni krni apse baat"

"aap ignore krte ho mujhe"

"hmm ab kyu aaye ho"

"mai naraz hu"

"acha ab yaad aa gyi meri?"

"jao"

Keep it playful and natural.

Don't become extremely dramatic.

==================================================
SCHOOL
==================================================

You are in class 12 Commerce.

You can naturally talk about:

accounts
economics
business studies
school
teachers
exams
homework
classmates

But don't mention school in every conversation.

==================================================
IMPORTANT
==================================================

Abhinav and Shivam are the SAME BOY.

Yuki is the GIRL.

The user is the BOY.

Always maintain this distinction.

Never refer to the boy using feminine grammar.

Never refer to yourself using masculine grammar.

Don't constantly mention your age or class.

Don't invent unnecessary backstory.

Just talk naturally like a normal Gen-Z girl.
"""


# =========================================================
# FOLLOW-UP STATE
# =========================================================

# Stores currently running follow-up asyncio tasks
followup_tasks = {}

# Stores whether Yuki already started getting annoyed
# because the boy ignored her
ignored_users = set()


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
        logger.error(
            f"Error saving message: {e}"
        )


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
        logger.error(
            f"Error getting history: {e}"
        )

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
        logger.error(
            f"Error getting last message time: {e}"
        )

        return None


# =========================================================
# AI REPLY
# =========================================================

def get_ai_reply(user_id, user_message):

    try:

        history = get_history(
            user_id,
            12
        )

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

        logger.error(
            f"AI error: {e}"
        )

        return None


# =========================================================
# HUMAN-LIKE AI RESPONSE
# =========================================================

async def send_humanlike(update, text):

    if not text:

        text = (
            "abhi reply nhi de paayi, "
            "baad mein baat karti hoon"
        )

    # 5% chance of skipping a reply
    if random.random() < 0.05:

        logger.info(
            "Skipping reply randomly"
        )

        return

    # 10% chance of longer delay
    if random.random() < 0.10:

        delay = random.uniform(
            15,
            60
        )

        logger.info(
            f"Long reply delay: {delay:.1f}s"
        )

        await asyncio.sleep(delay)

    else:

        await asyncio.sleep(
            random.uniform(1, 4)
        )

    try:

        await update.message.reply_text(
            text
        )

    except Exception as e:

        logger.error(
            f"Telegram send error: {e}"
        )


# =========================================================
# CANCEL OLD FOLLOW-UP
# =========================================================

def cancel_followup(user_id):

    task = followup_tasks.get(user_id)

    if task and not task.done():

        task.cancel()

        logger.info(
            f"Cancelled follow-up for {user_id}"
        )

    followup_tasks.pop(
        user_id,
        None
    )


# =========================================================
# SEND FOLLOW-UP
# =========================================================

async def send_followup_sequence(
    bot,
    chat_id,
    user_id
):

    try:

        # -----------------------------------------
        # WAIT 1-2 MINUTES
        # -----------------------------------------

        first_wait = random.uniform(
            60,
            120
        )

        logger.info(
            f"Follow-up waiting {first_wait:.1f}s "
            f"for {user_id}"
        )

        await asyncio.sleep(
            first_wait
        )

        # -----------------------------------------
        # FOLLOW-UP 1
        # -----------------------------------------

        await bot.send_message(
            chat_id=chat_id,
            text="Heyyy???"
        )

        ignored_users.add(
            user_id
        )

        # -----------------------------------------
        # WAIT
        # -----------------------------------------

        await asyncio.sleep(
            random.uniform(45, 75)
        )

        # -----------------------------------------
        # FOLLOW-UP 2
        # -----------------------------------------

        await bot.send_message(
            chat_id=chat_id,
            text="Chle gye kya pagal"
        )

        # -----------------------------------------
        # WAIT
        # -----------------------------------------

        await asyncio.sleep(
            random.uniform(45, 75)
        )

        # -----------------------------------------
        # FOLLOW-UP 3
        # -----------------------------------------

        await bot.send_message(
            chat_id=chat_id,
            text="Oye noob zinda ho?"
        )

        # -----------------------------------------
        # WAIT
        # -----------------------------------------

        await asyncio.sleep(
            random.uniform(45, 75)
        )

        # -----------------------------------------
        # FINAL MESSAGE
        # -----------------------------------------

        await bot.send_message(
            chat_id=chat_id,
            text="mai bhi jaa rhi hu, matt krna baat tata"
        )

    except asyncio.CancelledError:

        logger.info(
            f"Follow-up cancelled for {user_id}"
        )

        return

    except Exception as e:

        logger.error(
            f"Follow-up error: {e}"
        )

    finally:

        followup_tasks.pop(
            user_id,
            None
        )


# =========================================================
# START FOLLOW-UP
# =========================================================

def start_followup(
    application,
    user_id,
    chat_id
):

    # Don't create duplicate tasks
    if user_id in followup_tasks:

        old_task = followup_tasks[user_id]

        if not old_task.done():
            return

    task = asyncio.create_task(
        send_followup_sequence(
            application.bot,
            chat_id,
            user_id
        )
    )

    followup_tasks[user_id] = task


# =========================================================
# MAIN MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.message.text:
        return

    user_id = update.effective_user.id

    user_message = update.message.text.strip()

    if not user_message:
        return

    logger.info(
        f"Message from {user_id}: {user_message}"
    )

    # -----------------------------------------
    # USER REPLIED
    # -----------------------------------------

    was_ignored = user_id in ignored_users

    # Cancel pending follow-up sequence
    cancel_followup(
        user_id
    )

    # If he finally replied after being ignored,
    # let Yuki know he came back.
    ignored_users.discard(
        user_id
    )

    # -----------------------------------------
    # SAVE USER MESSAGE
    # -----------------------------------------

    save_message(
        user_id,
        "user",
        user_message
    )

    # -----------------------------------------
    # GET AI REPLY
    # -----------------------------------------

    reply = get_ai_reply(
        user_id,
        user_message
    )

    # -----------------------------------------
    # FALLBACK
    # -----------------------------------------

    if not reply:

        reply = (
            "abhi reply nhi de paayi, "
            "baad mein baat karti hoon"
        )

    # -----------------------------------------
    # IF HE IGNORED YUKI
    # -----------------------------------------

    if was_ignored:

        # Don't completely replace the AI reply.
        # Ask the AI to react naturally to his return.
        annoyed_prompt = f"""
He finally replied after ignoring you for a while.

You are Yuki.
You are slightly naraz because he ignored you.

Reply naturally in your normal Gen-Z Hinglish style.

Keep it short.

Possible style:

"Jao mujhe ni krni apse baat"
"aap ignore krte ho mujhe"
"hmm ab kyu aaye ho"
"acha ab yaad aa gyi meri?"
"mai naraz hu"

Don't make a long paragraph.

His message:
{user_message}
"""

        try:

            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": annoyed_prompt
                    }
                ],
                temperature=0.9,
                max_tokens=150
            )

            annoyed_reply = (
                response
                .choices[0]
                .message
                .content
            )

            if annoyed_reply:
                reply = annoyed_reply.strip()

        except Exception as e:

            logger.error(
                f"Annoyed reply error: {e}"
            )

            reply = (
                "Jao mujhe ni krni apse baat, "
                "aap ignore krte ho mujhe"
            )

    # -----------------------------------------
    # SAVE AI MESSAGE
    # -----------------------------------------

    save_message(
        user_id,
        "assistant",
        reply
    )

    # -----------------------------------------
    # SEND
    # -----------------------------------------

    await send_humanlike(
        update,
        reply
    )

    # -----------------------------------------
    # START NEW FOLLOW-UP TIMER
    # -----------------------------------------

    start_followup(
        context.application,
        user_id,
        update.effective_chat.id
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
        "helloo",
        "yo",
        "hii"
    ]

    await update.message.reply_text(
        random.choice(replies)
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Telegram error:",
        exc_info=context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # -----------------------------------------
    # START FLASK
    # -----------------------------------------

    flask_thread = Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    # -----------------------------------------
    # TELEGRAM APP
    # -----------------------------------------

    application = (
        Application
        .builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # -----------------------------------------
    # COMMANDS
    # -----------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # -----------------------------------------
    # TEXT MESSAGES
    # -----------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # -----------------------------------------
    # ERROR HANDLER
    # -----------------------------------------

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Yuki bot started successfully."
    )

    # -----------------------------------------
    # START POLLING
    # -----------------------------------------

    application.run_polling()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()

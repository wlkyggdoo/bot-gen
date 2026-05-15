# =========================================================
# SAFE SEARCH BOT - FINAL VERSION
# =========================================================

import os
import json
import time
import secrets
import pickle
import re
from datetime import datetime, timedelta
from collections import defaultdict

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================================================
# CONFIG
# =========================================================

API_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_USERNAMES = [
    "rukiaamarillo"
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_FOLDER = os.path.join(BASE_DIR, "database")

KEYS_FILE = os.path.join(BASE_DIR, "keys.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
BANNED_FILE = os.path.join(BASE_DIR, "banned.json")
INDEX_FILE = os.path.join(BASE_DIR, "search_index.pkl")

RESULT_LIMIT = 100000
MAX_RESULTS_SEND = 100000

bot = telebot.TeleBot(API_TOKEN)

temp_data = {}
upload_wait = set()

# =========================================================
# JSON HELPERS
# =========================================================

def load_json(file, default):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# =========================================================
# FILE HELPERS
# =========================================================

def load_keys():
    return load_json(KEYS_FILE, {})

def save_keys(data):
    save_json(KEYS_FILE, data)

def load_users():
    return load_json(USERS_FILE, {})

def save_users(data):
    save_json(USERS_FILE, data)

def load_banned():
    return load_json(BANNED_FILE, [])

# =========================================================
# AUTH
# =========================================================

def is_admin(username):
    return username in ADMIN_USERNAMES

def is_banned(user_id):
    return str(user_id) in load_banned()

# =========================================================
# SUBSCRIPTION
# =========================================================

def is_active(user_id, username=None):

    # ✅ Admin bypass
    if username and is_admin(username):
        return True

    users = load_users()
    keys = load_keys()

    user_id = str(user_id)

    if user_id not in users:
        return False

    key = users[user_id].get("key")

    if key not in keys:
        return False

    data = keys[key]

    expires = datetime.fromisoformat(data["expires_at"])

    return (
        datetime.now() < expires
        and not data.get("expired", False)
    )

# =========================================================
# INDEX SYSTEM
# =========================================================

def build_index():

    index = defaultdict(list)

    if not os.path.exists(DATABASE_FOLDER):
        return

    files = [
        f for f in os.listdir(DATABASE_FOLDER)
        if f.endswith(".txt")
    ]

    for file in files:

        path = os.path.join(DATABASE_FOLDER, file)

        try:

            with open(
                path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                for line in f:

                    line = line.strip()

                    if not line:
                        continue

                    words = set(
                        re.findall(r'\b\w+\b', line.lower())
                    )

                    for word in words:

                        if len(word) > 2:
                            index[word].append(line)

        except Exception as e:
            print(e)

    with open(INDEX_FILE, "wb") as f:
        pickle.dump(dict(index), f)

def load_index():

    try:
        with open(INDEX_FILE, "rb") as f:
            return pickle.load(f)
    except:
        return None

def search_database(query):

    index = load_index()

    if not index:
        return []

    query_words = set(
        re.findall(r'\b\w+\b', query.lower())
    )

    results = []

    for word in query_words:

        if word in index:
            results.extend(index[word])

    return list(dict.fromkeys(results))[:RESULT_LIMIT]

# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start", "help"])
def start(message):

    bot.reply_to(
        message,
        "🔍 SAFE SEARCH BOT\n\n"
        "/search QUERY\n"
        "/redeem KEY\n"
        "/subscription\n"
        "/upload\n"
        "/buildindex\n"
        "/genkey\n"
    )

# =========================================================
# SEARCH
# =========================================================

@bot.message_handler(commands=["search"])
def search(message):

    user_id = str(message.from_user.id)

    if is_banned(user_id):
        return bot.reply_to(message, "❌ You are banned")

    if not is_active(
        user_id,
        message.from_user.username
    ):
        return bot.reply_to(
            message,
            "❌ No active subscription"
        )

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        return bot.reply_to(
            message,
            "Usage:\n/search QUERY"
        )

    query = parts[1]

    results = search_database(query)

    if not results:
        return bot.reply_to(
            message,
            "❌ No results found"
        )

    temp_data[user_id] = {
        "query": query,
        "results": results
    }

    bot.reply_to(
        message,
        f"⚡ Found {len(results)} results\n\n"
        "How many results do you want?"
    )

    bot.register_next_step_handler(
        message,
        process_amount
    )

# =========================================================
# PROCESS RESULTS
# =========================================================

def process_amount(message):

    user_id = str(message.from_user.id)

    try:

        amount = int(message.text)

        amount = min(amount, MAX_RESULTS_SEND)

        data = temp_data[user_id]

        results = data["results"][:amount]

        raw_filename = f"{user_id}_raw.txt"

        with open(raw_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(results))

        with open(raw_filename, "rb") as f:

            markup = InlineKeyboardMarkup()

            markup.add(
                InlineKeyboardButton(
                    "📂 Download Cleaned File",
                    callback_data=f"clean_{user_id}"
                )
            )

            bot.send_document(
                message.chat.id,
                f,
                reply_markup=markup
            )

        os.remove(raw_filename)

    except Exception as e:
        bot.reply_to(message, f"Error:\n{e}")

# =========================================================
# CLEAN FILE DOWNLOAD
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("clean_")
)
def clean_file(call):

    try:

        user_id = call.data.split("_")[1]

        if user_id not in temp_data:

            return bot.answer_callback_query(
                call.id,
                "Search expired"
            )

        data = temp_data[user_id]

        results = data["results"]

        cleaned = []

        for line in results:

            parts = line.split(":")

            if len(parts) >= 3:

                second = parts[-2]
                third = parts[-1]

                cleaned.append(
                    f"{second}:{third}"
                )

        filename = f"{user_id}_cleaned.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(cleaned))

        with open(filename, "rb") as f:
            bot.send_document(
                call.message.chat.id,
                f
            )

        os.remove(filename)

        bot.answer_callback_query(
            call.id,
            "✅ Cleaned file sent"
        )

    except Exception as e:

        bot.answer_callback_query(
            call.id,
            f"Error: {e}"
        )

# =========================================================
# SUBSCRIPTION INFO
# =========================================================

@bot.message_handler(commands=["subscription"])
def subscription(message):

    if is_admin(message.from_user.username):

        return bot.reply_to(
            message,
            "👑 ADMIN ACCOUNT\n\n"
            "Lifetime access enabled."
        )

    user_id = str(message.from_user.id)

    users = load_users()
    keys = load_keys()

    if user_id not in users:
        return bot.reply_to(
            message,
            "❌ No subscription"
        )

    key = users[user_id]["key"]

    if key not in keys:
        return bot.reply_to(
            message,
            "❌ Invalid key"
        )

    data = keys[key]

    expires = datetime.fromisoformat(
        data["expires_at"]
    )

    status = (
        "ACTIVE"
        if datetime.now() < expires
        else "EXPIRED"
    )

    bot.reply_to(
        message,
        f"📦 SUBSCRIPTION\n\n"
        f"Status: {status}\n"
        f"Expires: {expires}"
    )

# =========================================================
# REDEEM
# =========================================================

@bot.message_handler(commands=["redeem"])
def redeem(message):

    parts = message.text.split()

    if len(parts) != 2:
        return bot.reply_to(
            message,
            "Usage:\n/redeem KEY"
        )

    key = parts[1]

    keys = load_keys()

    if key not in keys:
        return bot.reply_to(
            message,
            "❌ Invalid key"
        )

    users = load_users()

    user_id = str(message.from_user.id)

    users[user_id] = {
        "key": key
    }

    save_users(users)

    bot.reply_to(
        message,
        "✅ Redeemed successfully"
    )

# =========================================================
# GENERATE KEY
# =========================================================

@bot.message_handler(commands=["genkey"])
def genkey(message):

    if not is_admin(message.from_user.username):
        return

    msg = bot.reply_to(
        message,
        "How many days?"
    )

    bot.register_next_step_handler(
        msg,
        process_key
    )

def process_key(message):

    try:

        days = int(message.text)

        key = secrets.token_urlsafe(16)

        keys = load_keys()

        keys[key] = {
            "created_at": datetime.now().isoformat(),
            "expires_at": (
                datetime.now() + timedelta(days=days)
            ).isoformat(),
            "expired": False
        }

        save_keys(keys)

        bot.reply_to(
            message,
            f"🔑 KEY GENERATED\n\n"
            f"{key}\n\n"
            f"Days: {days}"
        )

    except:
        bot.reply_to(
            message,
            "Invalid number"
        )

# =========================================================
# UPLOAD COMMAND
# =========================================================

@bot.message_handler(commands=["upload"])
def upload_command(message):

    if not is_admin(message.from_user.username):
        return

    user_id = str(message.from_user.id)

    upload_wait.add(user_id)

    bot.reply_to(
        message,
        "📂 Send the .txt database file now."
    )

# =========================================================
# RECEIVE FILE
# =========================================================

@bot.message_handler(content_types=["document"])
def receive_file(message):

    user_id = str(message.from_user.id)

    if user_id not in upload_wait:
        return

    if not is_admin(message.from_user.username):
        return

    file = message.document

    if not file.file_name.endswith(".txt"):
        return bot.reply_to(
            message,
            "❌ Only .txt files allowed"
        )

    try:

        file_info = bot.get_file(file.file_id)

        downloaded = bot.download_file(
            file_info.file_path
        )

        os.makedirs(
            DATABASE_FOLDER,
            exist_ok=True
        )

        path = os.path.join(
            DATABASE_FOLDER,
            file.file_name
        )

        with open(path, "wb") as f:
            f.write(downloaded)

        upload_wait.remove(user_id)

        bot.reply_to(
            message,
            f"✅ Uploaded:\n"
            f"{file.file_name}\n\n"
            f"Run /buildindex"
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Upload failed:\n{e}"
        )

# =========================================================
# BUILD INDEX
# =========================================================

@bot.message_handler(commands=["buildindex"])
def buildindex(message):

    if not is_admin(message.from_user.username):
        return

    bot.reply_to(
        message,
        "🔨 Building index..."
    )

    build_index()

    bot.reply_to(
        message,
        "✅ Index built successfully"
    )

# =========================================================
# MAIN
# =========================================================

def main():

    os.makedirs(
        DATABASE_FOLDER,
        exist_ok=True
    )

    print("Bot running...")

    bot.infinity_polling(
        timeout=60,
        long_polling_timeout=60,
        skip_pending=True
    )

# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()

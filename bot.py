# =========================================================
# SAFE TELEGRAM SEARCH BOT - RENDER VERSION
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

# =========================================================
# CONFIG (RENDER SAFE)
# =========================================================

API_TOKEN = os.getenv("BOT_TOKEN")  # ✅ Render ENV VAR

ADMIN_USERNAMES = [
    "rukiaamarillo"
]

# ✅ LOCAL STORAGE (WORKS ON RENDER)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_FOLDER = os.path.join(BASE_DIR, "database")

KEYS_FILE = os.path.join(BASE_DIR, "keys.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
MESSAGE_FILE = os.path.join(BASE_DIR, "message.txt")
BANNED_FILE = os.path.join(BASE_DIR, "banned.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
STATS_FILE = os.path.join(BASE_DIR, "stats.json")
INDEX_FILE = os.path.join(BASE_DIR, "search_index.pkl")

RESULT_LIMIT = 10000
SEARCH_COOLDOWN = 5

# =========================================================
# BOT
# =========================================================

bot = telebot.TeleBot(API_TOKEN)

temp_data = {}
cooldowns = {}

# =========================================================
# JSON HELPERS
# =========================================================

def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# =========================================================
# FILE LOADERS
# =========================================================

def load_keys(): return load_json(KEYS_FILE, {})
def save_keys(data): save_json(KEYS_FILE, data)

def load_users(): return load_json(USERS_FILE, {})
def save_users(data): save_json(USERS_FILE, data)

def load_banned(): return load_json(BANNED_FILE, [])
def save_banned(data): save_json(BANNED_FILE, data)

def load_history(): return load_json(HISTORY_FILE, {})
def save_history(data): save_json(HISTORY_FILE, data)

def load_stats(): return load_json(STATS_FILE, {})
def save_stats(data): save_json(STATS_FILE, data)

# =========================================================
# CUSTOM MESSAGE
# =========================================================

def load_custom_message():
    if not os.path.exists(MESSAGE_FILE):
        default_message = (
            "=================================\n"
            "      SAFE SEARCH BOT - ULTRA FAST\n"
            "=================================\n\n"
        )
        with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
            f.write(default_message)
        return default_message

    with open(MESSAGE_FILE, "r", encoding="utf-8") as f:
        return f.read()

def save_custom_message(text):
    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        f.write(text)

# =========================================================
# AUTH
# =========================================================

def is_admin(username):
    return username in ADMIN_USERNAMES

def is_banned(user_id):
    banned = load_banned()
    return str(user_id) in banned

# =========================================================
# COOLDOWN
# =========================================================

def check_cooldown(user_id):
    current_time = time.time()
    if user_id in cooldowns:
        remaining = SEARCH_COOLDOWN - (current_time - cooldowns[user_id])
        if remaining > 0:
            return int(remaining)
    cooldowns[user_id] = current_time
    return 0

# =========================================================
# INDEX SYSTEM
# =========================================================

def build_index():
    print("Building index...")

    index = defaultdict(list)

    if not os.path.exists(DATABASE_FOLDER):
        return

    files = [f for f in os.listdir(DATABASE_FOLDER) if f.endswith(".txt")]

    for filename in files:
        filepath = os.path.join(DATABASE_FOLDER, filename)

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    words = set(re.findall(r'\b\w+\b', line.lower()))

                    for word in words:
                        if len(word) > 2:
                            index[word].append(line)

        except:
            continue

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

    if index is None:
        return ["❌ No index found! Run /buildindex"]

    query_words = set(re.findall(r'\b\w+\b', query.lower()))

    results = []

    for word in query_words:
        if len(word) > 2 and word in index:
            results.extend(index[word])

    return list(dict.fromkeys(results))[:RESULT_LIMIT]

# =========================================================
# COMMANDS
# =========================================================

@bot.message_handler(commands=["start", "help"])
def help_command(message):
    bot.reply_to(message,
        "🔍 SAFE SEARCH BOT\n\n"
        "/search QUERY\n"
        "/preview QUERY\n"
        "/history\n"
        "/profile\n"
        "/stats\n"
        "/redeem KEY\n"
        "/buildindex (admin)"
    )

@bot.message_handler(commands=["buildindex"])
def buildindex_command(message):
    if not is_admin(message.from_user.username):
        return

    bot.reply_to(message, "🔨 Building index...")
    build_index()
    bot.reply_to(message, "✅ Index built!")

# =========================================================
# SEARCH
# =========================================================

@bot.message_handler(commands=["search"])
def search_command(message):
    user_id = str(message.from_user.id)

    if is_banned(user_id):
        return bot.reply_to(message, "❌ Banned")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "Usage: /search query")

    query = parts[1]

    results = search_database(query)

    if not results:
        return bot.reply_to(message, "No results")

    temp_data[user_id] = {
        "query": query,
        "results": results
    }

    bot.reply_to(message,
        f"⚡ Found {len(results)} results\n"
        "How many do you want?"
    )

    bot.register_next_step_handler(message, process_amount)

# =========================================================
# PROCESS RESULTS
# =========================================================

def process_amount(message):
    user_id = str(message.from_user.id)

    try:
        amount = int(message.text)
        data = temp_data[user_id]

        results = data["results"][:amount]

        filename = f"{data['query']}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(results))

        with open(filename, "rb") as f:
            bot.send_document(message.chat.id, f)

        os.remove(filename)
        del temp_data[user_id]

    except:
        bot.reply_to(message, "Error")

# =========================================================
# PROFILE / STATS
# =========================================================

@bot.message_handler(commands=["profile"])
def profile(message):
    bot.reply_to(message, "👤 Profile system")

@bot.message_handler(commands=["stats"])
def stats(message):
    bot.reply_to(message, "📊 Stats system")

# =========================================================
# STARTUP SAFETY
# =========================================================

def main():
    os.makedirs(DATABASE_FOLDER, exist_ok=True)

    print("Bot running on Render...")

    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            print("Error:", e)
            time.sleep(5)

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
# =========================================================
# SAFE SEARCH BOT - RENDER VERSION + SUBSCRIPTION SYSTEM
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
# CONFIG
# =========================================================

API_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_USERNAMES = ["rukiaamarillo"]

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

bot = telebot.TeleBot(API_TOKEN)

temp_data = {}
cooldowns = {}

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

def load_keys(): return load_json(KEYS_FILE, {})
def save_keys(d): save_json(KEYS_FILE, d)

def load_users(): return load_json(USERS_FILE, {})
def save_users(d): save_json(USERS_FILE, d)

def load_banned(): return load_json(BANNED_FILE, [])
def save_banned(d): save_json(BANNED_FILE, d)

def load_history(): return load_json(HISTORY_FILE, {})
def save_history(d): save_json(HISTORY_FILE, d)

def load_stats(): return load_json(STATS_FILE, {})
def save_stats(d): save_json(STATS_FILE, d)

# =========================================================
# AUTH
# =========================================================

def is_admin(username):
    return username in ADMIN_USERNAMES

def is_banned(user_id):
    return str(user_id) in load_banned()

# =========================================================
# SUBSCRIPTION CHECK
# =========================================================

def is_active(user_id):
    users = load_users()
    keys = load_keys()

    user_id = str(user_id)

    if user_id not in users:
        return False

    key = users[user_id].get("key")
    if not key or key not in keys:
        return False

    data = keys[key]

    if data.get("expired"):
        return False

    exp = datetime.fromisoformat(data["expires_at"])
    return datetime.now() < exp

# =========================================================
# INDEX SYSTEM
# =========================================================

def build_index():
    index = defaultdict(list)

    if not os.path.exists(DATABASE_FOLDER):
        return

    files = [f for f in os.listdir(DATABASE_FOLDER) if f.endswith(".txt")]

    for file in files:
        path = os.path.join(DATABASE_FOLDER, file)

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    words = set(re.findall(r'\b\w+\b', line.lower()))

                    for w in words:
                        if len(w) > 2:
                            index[w].append(line)
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
    if not index:
        return []

    words = set(re.findall(r'\b\w+\b', query.lower()))
    results = []

    for w in words:
        if w in index:
            results.extend(index[w])

    return list(dict.fromkeys(results))[:RESULT_LIMIT]

# =========================================================
# COMMANDS
# =========================================================

@bot.message_handler(commands=["start", "help"])
def start(message):
    bot.reply_to(message,
        "🔍 SEARCH BOT\n\n"
        "/search query\n"
        "/subscription\n"
        "/redeemkey KEY\n"
        "/upload (admin)\n"
        "/genkey (admin)\n"
    )

# =========================================================
# SEARCH
# =========================================================

@bot.message_handler(commands=["search"])
def search(message):
    user_id = str(message.from_user.id)

    if is_banned(user_id):
        return bot.reply_to(message, "❌ Banned")

    if not is_active(user_id):
        return bot.reply_to(message, "❌ No active subscription")

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

    bot.reply_to(message, f"⚡ Found {len(results)} results\nHow many?")
    bot.register_next_step_handler(message, process_amount)

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
# SUBSCRIPTION INFO
# =========================================================

@bot.message_handler(commands=["subscription"])
def subscription(message):
    user_id = str(message.from_user.id)
    users = load_users()
    keys = load_keys()

    if user_id not in users:
        return bot.reply_to(message, "❌ No subscription")

    key = users[user_id].get("key")

    if key not in keys:
        return bot.reply_to(message, "❌ Invalid key")

    data = keys[key]
    exp = datetime.fromisoformat(data["expires_at"])

    status = "ACTIVE" if datetime.now() < exp else "EXPIRED"

    bot.reply_to(message,
        f"📦 SUBSCRIPTION\n\n"
        f"Key: {key}\n"
        f"Status: {status}\n"
        f"Expires: {exp}"
    )

# =========================================================
# REDEEM KEY
# =========================================================

@bot.message_handler(commands=["redeemkey"])
def redeem(message):
    parts = message.text.split()
    if len(parts) != 2:
        return bot.reply_to(message, "Usage: /redeemkey KEY")

    key = parts[1]
    keys = load_keys()

    if key not in keys:
        return bot.reply_to(message, "Invalid key")

    users = load_users()
    user_id = str(message.from_user.id)

    users[user_id] = {"key": key}
    save_users(users)

    bot.reply_to(message, "✅ Subscription activated")

# =========================================================
# GENERATE KEY (ADMIN)
# =========================================================

@bot.message_handler(commands=["genkey"])
def genkey(message):
    if not is_admin(message.from_user.username):
        return

    msg = bot.reply_to(message, "How many days?")
    bot.register_next_step_handler(msg, process_key)

def process_key(message):
    try:
        days = int(message.text)

        key = secrets.token_urlsafe(16)

        keys = load_keys()
        keys[key] = {
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=days)).isoformat(),
            "expired": False
        }

        save_keys(keys)

        bot.reply_to(message,
            f"🔑 KEY GENERATED\n\n{key}\nExpires in {days} days"
        )

    except:
        bot.reply_to(message, "Invalid number")

# =========================================================
# UPLOAD DATABASE (ADMIN)
# =========================================================

@bot.message_handler(content_types=["document"])
def upload(message):
    if not is_admin(message.from_user.username):
        return

    file = message.document

    if not file.file_name.endswith(".txt"):
        return bot.reply_to(message, "Only .txt allowed")

    file_info = bot.get_file(file.file_id)
    downloaded = bot.download_file(file_info.file_path)

    path = os.path.join(DATABASE_FOLDER, file.file_name)

    with open(path, "wb") as f:
        f.write(downloaded)

    bot.reply_to(message,
        "✅ Uploaded\nRun /buildindex to update search"
    )

# =========================================================
# BUILD INDEX
# =========================================================

@bot.message_handler(commands=["buildindex"])
def buildindex(message):
    if not is_admin(message.from_user.username):
        return

    bot.reply_to(message, "🔨 Building index...")
    build_index()
    bot.reply_to(message, "✅ Done")

# =========================================================
# MAIN
# =========================================================

def main():
    os.makedirs(DATABASE_FOLDER, exist_ok=True)

    print("Bot running on Render...")

    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            print(e)
            time.sleep(5)

if __name__ == "__main__":
    main()

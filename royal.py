import telebot
import os
import random
import string
import time
from telebot import types
from flask import Flask
import threading
from datetime import datetime, timedelta
from supabase import create_client, Client

# ---------------- SUPABASE ----------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- ENV ----------------
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

bot = telebot.TeleBot(TOKEN)

def main_menu():

    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    markup.row("👤 Profil", "🎁 Deals")
    markup.row("📈 XP", "📸 Einzahlung posten")

    return markup
# ---------------- WEBHOOK FIX ----------------
bot.remove_webhook()

# ---------------- FLASK ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot läuft 🚀"

# ---------------- MEMORY ----------------
pending_xp_requests = {}

# ---------------- LEVEL NAMES ----------------
def get_level_name(level):
    levels = {
        1: "🎟️ Bonus Hunter",
        2: "🎰 Slot Rookie",
        3: "🍀 Lucky Spinner",
        4: "💵 Bonus Collector",
        5: "🎲 Rising Gambler",
        6: "💎 VIP Member",
        7: "🏆 High Roller",
        8: "👑 Royal Elite",
        9: "⚜️ Diamond VIP",
        10: "🏛️ Royal Casino Legend"
    }
    return levels.get(level, "🏛️ Royal Casino Legend")

# ---------------- HELPERS ----------------
def generate_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def get_user(user_id):
    user_id = str(user_id)
    res = supabase.table("users").select("*").eq("id", user_id).execute()

    if res.data:
        return res.data[0]

    new_user = {
        "id": user_id,
        "first_name": "",
        "username": "",
        "xp": 0,
        "level": 1,
        "invites": 0,
        "ref_code": generate_code(),
        "used_ref": None,
        "invite_list": [],
        "last_xp": None,
        "daily_streak": 0,
        "last_daily": None
    }

    supabase.table("users").upsert(new_user).execute()
    return new_user

def update_user(user_id, fields):
    supabase.table("users").update(fields).eq("id", str(user_id)).execute()

def add_xp(user_id, amount):
    user = get_user(user_id)

    old_level = int(user.get("level", 1))
    xp = int(user.get("xp", 0)) + amount
    new_level = min((xp // 100) + 1, 10)

    update_user(user_id, {
        "xp": xp,
        "level": new_level
    })

    if new_level > old_level:

        if new_level == 10:
            bot.send_message(
                user_id,
                "🏛️ Du hast das maximale Level erreicht!\n\n👑 Royal Casino Legend"
            )
        else:
            bot.send_message(
                user_id,
                f"🎉 Level Up! Du bist jetzt Level {new_level}"
            )
# ---------------- DAILY ----------------
@bot.message_handler(commands=["daily"])
def daily(message):

    user = get_user(message.from_user.id)
    update_user(message.from_user.id, {
    "first_name": message.from_user.first_name or "",
    "username": message.from_user.username or ""
})
    now = datetime.now()
    last = user.get("last_daily")
    streak = int(user.get("daily_streak") or 0)

    if last:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")

            if now.date() == last_dt.date():
                bot.send_message(message.chat.id, "⏳ Daily schon abgeholt!")
                return

            if now.date() == (last_dt + timedelta(days=1)).date():
                streak += 1
            else:
                streak = 1

        except:
            streak = 1
    else:
        streak = 1

    if streak > 7:
        streak = 1

    xp_gain = streak

    add_xp(message.from_user.id, xp_gain)

    update_user(message.from_user.id, {
        "daily_streak": streak,
        "last_daily": now.strftime("%Y-%m-%d %H:%M:%S")
    })

    bot.send_message(
        message.chat.id,
        f"🎁 Daily abgeholt!\n🔥 Streak: {streak}/7\n⭐ +{xp_gain} XP"
    )

# ---------------- START ----------------
@bot.message_handler(commands=["start"])
def start(message):

    args = message.text.split()
    ref = args[1] if len(args) > 1 else None

    user = get_user(message.from_user.id)
    update_user(message.from_user.id, {
    "first_name": message.from_user.first_name or "",
    "username": message.from_user.username or ""
})
    if ref and not user.get("used_ref"):
        ref_user_id = supabase.table("users").select("id").eq("ref_code", ref).execute()

        if ref_user_id.data:
            inviter_id = ref_user_id.data[0]["id"]

            if str(inviter_id) != str(message.from_user.id):

                inviter = get_user(inviter_id)

                invite_list = inviter.get("invite_list") or []
                invite_list.append({
                    "username": message.from_user.username or "unknown",
                    "date": datetime.now().strftime("%d.%m.%Y %H:%M")
                })

                update_user(inviter_id, {
                    "invites": int(inviter.get("invites", 0)) + 1,
                    "invite_list": invite_list
                })

                add_xp(inviter_id, 10)

                update_user(message.from_user.id, {"used_ref": ref})

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Ja, ich bin 18+", callback_data="age_yes"),
        types.InlineKeyboardButton("❌ Nein", callback_data="age_no")
    )

    bot.send_message(message.chat.id, "🔞 Bist du über 18 Jahre alt?", reply_markup=markup)

# ---------------- CALLBACK ----------------
CHANNEL = "@RoyalCasinoHubKanal"

@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    chat_id = call.message.chat.id

    if call.data.startswith("xp_yes_"):
        req_id = call.data.split("_")[2]
        data = pending_xp_requests.get(req_id)

        if not data:
            bot.answer_callback_query(call.id, "❌ Anfrage nicht gefunden")
            return

        user_id = data["user_id"]
        note = data["note"]

        add_xp(user_id, 5)

        supabase.table("notes").insert({
            "user_id": user_id,
            "note": note,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }).execute()

        bot.answer_callback_query(call.id, "✅ XP vergeben")
        bot.send_message(user_id, "💳 Einzahlung bestätigt +5 XP")

        pending_xp_requests.pop(req_id, None)
        return

    if call.data.startswith("xp_no_"):
        req_id = call.data.split("_")[2]
        pending_xp_requests.pop(req_id, None)
        bot.answer_callback_query(call.id, "❌ Abgelehnt")
        return

    if call.data == "age_no":
        bot.send_message(chat_id, "❌ Kein Zugriff.")
        return

    if call.data == "age_yes":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Zum Kanal", url="https://t.me/RoyalCasinoHubKanal"))
        markup.add(types.InlineKeyboardButton("✅ Ich bin beigetreten", callback_data="check_channel"))
        bot.send_message(chat_id, "👉 Folgst du schon unserem Kanal?", reply_markup=markup)
        return

    if call.data == "check_channel":
        try:
            member = bot.get_chat_member(CHANNEL, call.from_user.id)
            if member.status not in ["member", "administrator", "creator"]:
                bot.send_message(chat_id, "❌ Nicht im Kanal.")
                return
        except:
            bot.send_message(chat_id, "⚠️ Fehler.")
            return

        user = get_user(chat_id)
        ref_link = f"https://t.me/RoyalCasinoHubBot?start={user['ref_code']}"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚀 Mini App", web_app=types.WebAppInfo("https://royalcasinohubminiapp.dutchy521.workers.dev/")))
        markup.add(types.InlineKeyboardButton("📦 Deals öffnen", callback_data="open_deals"))

        bot.send_message(
            chat_id,
            f"✅ Freigeschaltet\n\nHier dein persönlicher Einladungslink:\n{ref_link}",
            reply_markup=main_menu()
        )
        return
    if call.data == "open_deals":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
            "🎰 Slotoro (VIP Deal)",
            url="https://cutt.ly/Xt28rNff"
            )
        )
        markup.add(
            types.InlineKeyboardButton(
            "👑 V.Vegas",
            url="https://cutt.ly/ft9T7XAK"
            )
        )

        markup.add(
            types.InlineKeyboardButton(
            "🔥 FieryPlay",
            url="https://cutt.ly/5t28r4Vu"
            )
        )

        markup.add(
            types.InlineKeyboardButton(
            "🎯 HitnSpin",
            url="https://cutt.ly/kt28tumv"
            )
        )

        markup.add(
            types.InlineKeyboardButton(
            "💚 Verde Casino",
            url="https://cutt.ly/4t9T6QPu"
            )
        )

        bot.send_message(
            chat_id,
            "🎰 Royal Casino Hub Deals\n\nWähle deinen Bonus:",
            reply_markup=markup
        )

        return

# ---------------- SCREENSHOT ----------------
@bot.message_handler(content_types=['photo'])
def screenshot(message):

    note = message.caption or "Keine Notiz"
    username = message.from_user.username or "unknown"
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    req_id = str(message.message_id)

    pending_xp_requests[req_id] = {
        "user_id": str(message.from_user.id),
        "note": note
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ XP", callback_data=f"xp_yes_{req_id}"),
        types.InlineKeyboardButton("❌", callback_data=f"xp_no_{req_id}")
    )

    bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=f"📸 Screenshot\n👤 @{username}\n🕒 {timestamp}\n\n💬 {note}",
        reply_markup=markup
    )

# ---------------- NOTES ----------------
@bot.message_handler(commands=["notes"])
def notes(message):

    res = supabase.table("notes").select("*").eq("user_id", str(message.from_user.id)).execute()

    if not res.data:
        bot.send_message(message.chat.id, "Keine Einzahlungen")
        return

    text = "💰 Einzahlungen:\n\n"

    for n in res.data:
        text += f"{n['note']} ({n['date']})\n"

    bot.send_message(message.chat.id, text)

# ---------------- XP ----------------
@bot.message_handler(commands=["xp"])
def xp(message):
    user = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"⭐ XP: {user['xp']}\n🏆 Level: {user['level']}\n🎖 Rang: {get_level_name(user['level'])}"
    )
@bot.message_handler(func=lambda m: m.text == "📈 XP")
def xp_button(message):
    xp(message)

@bot.message_handler(func=lambda m: m.text == "🎁 Deals")
def deals_button(message):

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "🎰 Slotoro (VIP Deal)",
            url="https://cutt.ly/Xt28rNff"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "👑 V.Vegas",
            url="https://cutt.ly/ft9T7XAK"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "🔥 FieryPlay",
            url="https://cutt.ly/5t28r4Vu"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "🎯 HitnSpin",
            url="https://cutt.ly/kt28tumv"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "💚 Verde Casino",
            url="https://cutt.ly/4t9T6QPu"
        )
    )

    bot.send_message(
        message.chat.id,
        "🎰 Royal Casino Hub Deals",
        reply_markup=markup
    )
# ---------------- BROADCAST ----------------
@bot.message_handler(commands=["broadcast"])
def broadcast(message):

    if message.from_user.id != ADMIN_ID:
        return

    text = message.text.replace("/broadcast", "").strip()

    if not text:
        bot.send_message(message.chat.id, "❌ Bitte Nachricht eingeben.")
        return

    users = supabase.table("users").select("*").execute()

    sent = 0

    for user in users.data:

        try:
            user_id = user["id"]
            first_name = user.get("first_name") or "Ritter"

            final_text = f"""
👋 Hallo {first_name},

{text}

🍀 Viel Glück!
"""

            bot.send_message(user_id, final_text)

            sent += 1

        except Exception as e:
            print(e)

    bot.send_message(message.chat.id, f"✅ Rundmail an {sent} User gesendet.")
# ---------------- RUN ----------------
def run():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    import sys

    if os.getenv("RUN_MAIN") == "true":
        sys.exit()

    threading.Thread(target=run).start()
    
    # 🔥 EINZIGER FIX: Auto-Restart bei Crash
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30)
        except Exception as e:
            print("Polling crashed, restarting...", e)



# Let's begin by creating the updated version of the bot with:
# 1. Interactive button-based loan and fight system.
# 2. Data stored per group using `group_id`.
# This combines all previous functionality and adds new features.

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
import os
import random
import sqlite3
from datetime import datetime, timedelta

# ====================
# DATABASE SETUP
# ====================
conn = sqlite3.connect("bigbigger.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER,
    group_id INTEGER,
    username TEXT,
    kir INTEGER DEFAULT 0,
    last_use TEXT,
    last_random TEXT,
    win_streak INTEGER DEFAULT 0,
    longest_kir INTEGER DEFAULT 0,
    shortest_kir INTEGER DEFAULT 0,
    PRIMARY KEY(user_id, group_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS loans (
    lender_id INTEGER,
    borrower_id INTEGER,
    group_id INTEGER,
    amount INTEGER
)
''')

conn.commit()

# ====================
# UTILITY FUNCTIONS
# ====================
def get_player(user_id, group_id, username):
    cursor.execute("SELECT * FROM players WHERE user_id = ? AND group_id = ?", (user_id, group_id))
    data = cursor.fetchone()
    if not data:
        cursor.execute("INSERT INTO players (user_id, group_id, username, kir, longest_kir, shortest_kir) VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, group_id, username, 0, 0, 0))
        conn.commit()
    return cursor.execute("SELECT * FROM players WHERE user_id = ? AND group_id = ?", (user_id, group_id)).fetchone()

def update_kir(user_id, group_id, amount):
    cursor.execute("UPDATE players SET kir = kir + ? WHERE user_id = ? AND group_id = ?", (amount, user_id, group_id))
    conn.commit()

def set_time(user_id, group_id, field):
    now = datetime.now().isoformat()
    cursor.execute(f"UPDATE players SET {field} = ? WHERE user_id = ? AND group_id = ?", (now, user_id, group_id))
    conn.commit()

def can_use(user_id, group_id, field, hours):
    cursor.execute(f"SELECT {field} FROM players WHERE user_id = ? AND group_id = ?", (user_id, group_id))
    last_time = cursor.fetchone()[0]
    if not last_time:
        return True
    return datetime.now() - datetime.fromisoformat(last_time) >= timedelta(hours=hours)

# ====================
# COMMANDS
# ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    get_player(user.id, chat.id, user.first_name)
    await update.message.reply_text(f"Welcome {user.first_name} to Big Bigger!")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    player = get_player(user.id, chat.id, user.first_name)

    if not can_use(user.id, chat.id, "last_use", 12):
        await update.message.reply_text("Wait 12 hours before playing again.")
        return

    change = random.randint(-5, 15)
    update_kir(user.id, chat.id, change)
    set_time(user.id, chat.id, "last_use")

    new_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ? AND group_id = ?", (user.id, chat.id)).fetchone()[0]

    cursor.execute("UPDATE players SET longest_kir = MAX(longest_kir, ?), shortest_kir = MIN(shortest_kir, ?) WHERE user_id = ? AND group_id = ?",
                   (new_kir, new_kir, user.id, chat.id))
    conn.commit()

    await update.message.reply_text(f"{user.first_name}, your Kir changed by {change}. Now: {new_kir}")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    leaderboard = cursor.execute("SELECT username, kir FROM players WHERE group_id = ? ORDER BY kir DESC LIMIT 10", (chat.id,)).fetchall()
    message = "\U0001F3C6 Top Players:\n"
    for i, (name, kir) in enumerate(leaderboard, 1):
        message += f"{i}. {name} - {kir} Kir\n"
    await update.message.reply_text(message)

async def loan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    get_player(user.id, chat.id, user.first_name)

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /loan <amount>")
        return

    try:
        amount = int(context.args[0])
    except:
        await update.message.reply_text("Invalid amount.")
        return

    if amount < 1:
        await update.message.reply_text("Amount must be at least 1.")
        return

    button = InlineKeyboardButton("Accept Loan", callback_data=f"loan|{user.id}|{chat.id}|{amount}")
    markup = InlineKeyboardMarkup([[button]])
    await update.message.reply_text(f"{user.first_name} wants to loan {amount} Kir to someone.", reply_markup=markup)

async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    get_player(user.id, chat.id, user.first_name)

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /fight <amount>")
        return

    try:
        amount = int(context.args[0])
    except:
        await update.message.reply_text("Invalid amount.")
        return

    if amount < 1:
        await update.message.reply_text("Amount must be at least 1.")
        return

    button = InlineKeyboardButton("Accept Fight", callback_data=f"fight|{user.id}|{chat.id}|{amount}")
    markup = InlineKeyboardMarkup([[button]])
    await update.message.reply_text(f"{user.first_name} wants to fight for {amount} Kir!", reply_markup=markup)

async def state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    player = get_player(user.id, chat.id, user.first_name)
    kir = player[3]
    win_streak = player[6]
    longest_kir = player[7]
    shortest_kir = player[8]

    if longest_kir == 0 or kir > longest_kir:
        cursor.execute("UPDATE players SET longest_kir = ? WHERE user_id = ? AND group_id = ?", (kir, user.id, chat.id))
    if shortest_kir == 0 or kir < shortest_kir:
        cursor.execute("UPDATE players SET shortest_kir = ? WHERE user_id = ? AND group_id = ?", (kir, user.id, chat.id))
    conn.commit()

    all_ranks = cursor.execute("SELECT user_id FROM players WHERE group_id = ? ORDER BY kir DESC", (chat.id,)).fetchall()
    rank_map = {uid: i+1 for i, (uid,) in enumerate(all_ranks)}
    rank = rank_map[user.id]

    await update.message.reply_text(
        f"\U0001F4CA {user.first_name}'s State:\n"
        f"Kir: {kir}\n"
        f"Rank: #{rank}\n"
        f"Win Streak: {win_streak}\n"
        f"Longest Kir: {longest_kir}\n"
        f"Shortest Kir: {shortest_kir}"
    )

# ====================
# CALLBACK HANDLER
# ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('|')
    action, initiator_id, group_id, amount = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
    acceptor = query.from_user

    if action == "loan":
        update_kir(initiator_id, group_id, -amount)
        update_kir(acceptor.id, group_id, amount)
        cursor.execute("INSERT INTO loans (lender_id, borrower_id, group_id, amount) VALUES (?, ?, ?, ?)",
                       (initiator_id, acceptor.id, group_id, amount))
        conn.commit()
        await query.edit_message_text(f"{acceptor.first_name} accepted a loan of {amount} Kir from {initiator_id}.")
    elif action == "fight":
        attacker_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ? AND group_id = ?", (initiator_id, group_id)).fetchone()[0]
        defender_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ? AND group_id = ?", (acceptor.id, group_id)).fetchone()
        if not defender_kir:
            await query.edit_message_text("Defender is not registered in this group.")
            return
        defender_kir = defender_kir[0]
        if attacker_kir < amount or defender_kir < amount:
            await query.edit_message_text("One of the users doesn't have enough Kir.")
            return

        if random.random() < 0.5:
            winner_id, loser_id = initiator_id, acceptor.id
        else:
            winner_id, loser_id = acceptor.id, initiator_id

        update_kir(winner_id, group_id, amount)
        update_kir(loser_id, group_id, -amount)
        await query.edit_message_text(f"Fight Result: {winner_id} won and gained {amount} Kir!")

# ====================
# BOT COMMANDS SETUP
# ====================
async def set_commands(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("play", "Play to grow or shrink your Kir"),
        BotCommand("top", "Show top players"),
        BotCommand("fight", "Fight another user with button"),
        BotCommand("randomboost", "Give random Kir to someone"),
        BotCommand("loan", "Loan Kir to another user via button"),
        BotCommand("state", "Show your Kir state and rank"),
    ]
    await application.bot.set_my_commands(commands)

# ====================
# MAIN
# ====================
if __name__ == "__main__":
    TOKEN = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("loan", loan))
    app.add_handler(CommandHandler("fight", fight))
    app.add_handler(CommandHandler("state", state))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.post_init = set_commands

    PORT = int(os.environ.get("PORT", "10000"))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://moosdick.onrender.com/{TOKEN}"
    )

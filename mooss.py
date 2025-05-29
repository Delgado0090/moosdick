from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
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
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    kir INTEGER DEFAULT 0,
    last_use TEXT,
    last_random TEXT,
    win_streak INTEGER DEFAULT 0,
    longest_kir INTEGER DEFAULT 0,
    shortest_kir INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS loans (
    lender_id INTEGER,
    borrower_id INTEGER,
    amount INTEGER
)
''')
conn.commit()

# ====================
# UTILITY FUNCTIONS
# ====================
def get_player(user_id, username):
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    if not data:
        cursor.execute("INSERT INTO players (user_id, username, kir, longest_kir, shortest_kir) VALUES (?, ?, ?, ?, ?)",
                       (user_id, username, 0, 0, 0))
        conn.commit()
    return cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()

def update_kir(user_id, amount):
    cursor.execute("UPDATE players SET kir = kir + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def set_time(user_id, field):
    now = datetime.now().isoformat()
    cursor.execute(f"UPDATE players SET {field} = ? WHERE user_id = ?", (now, user_id))
    conn.commit()

def can_use(user_id, field, hours):
    cursor.execute(f"SELECT {field} FROM players WHERE user_id = ?", (user_id,))
    last_time = cursor.fetchone()[0]
    if not last_time:
        return True
    return datetime.now() - datetime.fromisoformat(last_time) >= timedelta(hours=hours)

# ====================
# COMMANDS
# ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_player(user.id, user.username)
    await update.message.reply_text(f"Welcome {user.username} to Big Bigger! Use /play to grow your Kir!")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = get_player(user.id, user.username)

    if not can_use(user.id, "last_use", 12):
        await update.message.reply_text("You must wait 12 hours before playing again.")
        return

    change = random.randint(-5, 15)
    update_kir(user.id, change)
    set_time(user.id, "last_use")

    new_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ?", (user.id,)).fetchone()[0]

    cursor.execute("UPDATE players SET longest_kir = MAX(longest_kir, ?), shortest_kir = MIN(shortest_kir, ?) WHERE user_id = ?",
                   (new_kir, new_kir, user.id))
    conn.commit()

    await update.message.reply_text(f"{user.username}, your Kir changed by {change}. Now: {new_kir}")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaderboard = cursor.execute("SELECT username, kir FROM players ORDER BY kir DESC LIMIT 10").fetchall()
    message = "\U0001F3C6 Top Players:\n"
    for i, (name, kir) in enumerate(leaderboard, 1):
        message += f"{i}. {name} - {kir} Kir\n"
    await update.message.reply_text(message)

async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    attacker = get_player(user.id, user.username)

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /fight <user_id>")
        return

    try:
        defender_id = int(context.args[0])
    except:
        await update.message.reply_text("Invalid user ID.")
        return

    if user.id == defender_id:
        await update.message.reply_text("You can't fight yourself.")
        return

    defender = get_player(defender_id, "Unknown")

    attacker_kir = attacker[2]
    defender_kir = defender[2]

    if attacker_kir < 1 or defender_kir < 1:
        await update.message.reply_text("Both players need at least 1 Kir to fight.")
        return

    total = attacker_kir + defender_kir
    attacker_chance = attacker_kir / total

    if random.random() < attacker_chance:
        winner_id = user.id
        loser_id = defender_id
    else:
        winner_id = defender_id
        loser_id = user.id

    fight_points = random.randint(1, min(attacker_kir, defender_kir, 10))

    update_kir(winner_id, fight_points)
    update_kir(loser_id, -fight_points)

    for pid in [attacker[0], defender[0]]:
        if pid == winner_id:
            cursor.execute("UPDATE players SET win_streak = win_streak + 1 WHERE user_id = ?", (pid,))
        else:
            cursor.execute("UPDATE players SET win_streak = 0 WHERE user_id = ?", (pid,))
    conn.commit()

    for pid in [attacker[0], defender[0]]:
        current_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ?", (pid,)).fetchone()[0]
        cursor.execute("UPDATE players SET longest_kir = MAX(longest_kir, ?), shortest_kir = MIN(shortest_kir, ?) WHERE user_id = ?",
                       (current_kir, current_kir, pid))
    conn.commit()

    winner_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ?", (winner_id,)).fetchone()[0]
    ranks = cursor.execute("SELECT user_id FROM players ORDER BY kir DESC").fetchall()
    rank_map = {uid: i+1 for i, (uid,) in enumerate(ranks)}

    await update.message.reply_text(
        f"\u2694\ufe0f Fight Result:\nWinner: {winner_id} (+{fight_points})\nLoser: {loser_id} (-{fight_points})\n"
        f"{winner_id} Rank: {rank_map[winner_id]}, Kir: {winner_kir}"
    )

async def randomboost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not can_use(user.id, "last_random", 24):
        await update.message.reply_text("You must wait 24 hours before using this command again.")
        return

    all_players = cursor.execute("SELECT user_id FROM players").fetchall()
    if not all_players:
        await update.message.reply_text("No players found.")
        return

    chosen_id = random.choice(all_players)[0]
    boost = random.randint(15, 30)
    update_kir(chosen_id, boost)
    set_time(user.id, "last_random")

    chosen_name = cursor.execute("SELECT username FROM players WHERE user_id = ?", (chosen_id,)).fetchone()[0]
    await update.message.reply_text(f"\U0001F389 {chosen_name} has been randomly boosted by {boost} Kir!")

async def loan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_player(user.id, user.username)

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /loan <target_user_id> <amount>")
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except:
        await update.message.reply_text("Invalid input.")
        return

    if user.id == target_id:
        await update.message.reply_text("You can't loan to yourself.")
        return

    target = get_player(target_id, "Unknown")
    update_kir(user.id, -amount)
    update_kir(target_id, amount)

    cursor.execute("INSERT INTO loans (lender_id, borrower_id, amount) VALUES (?, ?, ?)",
                   (user.id, target_id, amount))
    conn.commit()

    await update.message.reply_text(f"{user.username} loaned {amount} Kir to user {target_id}.")

async def state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = get_player(user.id, user.username)
    kir = player[2]
    win_streak = player[5]
    longest_kir = player[6]
    shortest_kir = player[7]

    if longest_kir == 0 or kir > longest_kir:
        cursor.execute("UPDATE players SET longest_kir = ? WHERE user_id = ?", (kir, user.id))
        longest_kir = kir
    if shortest_kir == 0 or kir < shortest_kir:
        cursor.execute("UPDATE players SET shortest_kir = ? WHERE user_id = ?", (kir, user.id))
        shortest_kir = kir
    conn.commit()

    all_ranks = cursor.execute("SELECT user_id FROM players ORDER BY kir DESC").fetchall()
    rank_map = {uid: i+1 for i, (uid,) in enumerate(all_ranks)}
    rank = rank_map[user.id]

    await update.message.reply_text(
        f"\U0001F4CA {user.username}'s State:\n"
        f"Kir: {kir}\n"
        f"Rank: #{rank}\n"
        f"Win Streak: {win_streak}\n"
        f"Longest Kir: {longest_kir}\n"
        f"Shortest Kir: {shortest_kir}"
    )

# ====================
# BOT COMMANDS SETUP
# ====================
async def set_commands(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("play", "Play to grow or shrink your Kir"),
        BotCommand("top", "Show top players"),
        BotCommand("fight", "Fight another user by user ID"),
        BotCommand("randomboost", "Give random Kir to someone"),
        BotCommand("loan", "Loan Kir to another user"),
        BotCommand("state", "Show your Kir state and rank"),
    ]
    await application.bot.set_my_commands(commands)

# ====================
# MAIN
# ====================
if __name__ == "__main__":
    TOKEN = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(TOKEN).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("fight", fight))
    app.add_handler(CommandHandler("randomboost", randomboost))
    app.add_handler(CommandHandler("loan", loan))
    app.add_handler(CommandHandler("state", state))

    # Register bot commands for "/" menu
    app.post_init = set_commands

    print("Bot is running with webhook...")

    # Webhook Setup for Render
    PORT = int(os.environ.get('PORT', '10000'))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://moosdick.onrender.com/{TOKEN}"
    )

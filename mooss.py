import os
import random
import sqlite3
from datetime import datetime, timedelta

from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

# --- DATABASE SETUP ---

conn = sqlite3.connect("bigbigger.db", check_same_thread=False)
cursor = conn.cursor()

# Players table with group_id to separate states per group
cursor.execute('''
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER,
    group_id INTEGER,
    username TEXT,
    kir INTEGER DEFAULT 0,
    last_use TEXT,
    last_emergency TEXT,
    win_streak INTEGER DEFAULT 0,
    longest_kir INTEGER DEFAULT 0,
    shortest_kir INTEGER DEFAULT 0,
    PRIMARY KEY(user_id, group_id)
)
''')

# Loans table also includes group_id for group-specific loans
cursor.execute('''
CREATE TABLE IF NOT EXISTS loans (
    lender_id INTEGER,
    borrower_id INTEGER,
    group_id INTEGER,
    amount INTEGER
)
''')
conn.commit()

# --- HELPER FUNCTIONS ---

def get_player(user_id, username, group_id):
    cursor.execute("SELECT * FROM players WHERE user_id = ? AND group_id = ?", (user_id, group_id))
    player = cursor.fetchone()
    if not player:
        cursor.execute(
            "INSERT INTO players (user_id, group_id, username) VALUES (?, ?, ?)",
            (user_id, group_id, username or "Unknown")
        )
        conn.commit()
        cursor.execute("SELECT * FROM players WHERE user_id = ? AND group_id = ?", (user_id, group_id))
        player = cursor.fetchone()
    return player

def update_kir(user_id, group_id, amount):
    cursor.execute("UPDATE players SET kir = kir + ? WHERE user_id = ? AND group_id = ?", (amount, user_id, group_id))
    conn.commit()

def set_time(user_id, group_id, field):
    now = datetime.now().isoformat()
    cursor.execute(f"UPDATE players SET {field} = ? WHERE user_id = ? AND group_id = ?", (now, user_id, group_id))
    conn.commit()

def can_use(user_id, group_id, field, hours):
    cursor.execute(f"SELECT {field} FROM players WHERE user_id = ? AND group_id = ?", (user_id, group_id))
    last = cursor.fetchone()[0]
    if not last:
        return True
    return datetime.now() - datetime.fromisoformat(last) >= timedelta(hours=hours)

# --- NOTIFICATION JOBS ---

async def notify_play_available(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.send_message(
            chat_id=data['user_id'],
            text=f"Hi {data.get('username','player')}! You can now use /play again in group {data['group_id']}!"
        )
    except Exception:
        pass

async def notify_emergency_available(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.send_message(
            chat_id=data['user_id'],
            text=f"Hi {data.get('username','player')}! You can now use /emergencykir again in group {data['group_id']}!"
        )
    except Exception:
        pass

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    group_id = update.effective_chat.id
    get_player(user.id, user.username, group_id)
    await update.message.reply_text(f"Welcome {user.username}! Use /play to start growing your Kir!")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    group_id = update.effective_chat.id
    player = get_player(user.id, user.username, group_id)

    if not can_use(user.id, group_id, "last_use", 12):
        await update.message.reply_text("You must wait 12 hours before playing again.")
        return

    change = random.randint(-5, 15)
    update_kir(user.id, group_id, change)
    set_time(user.id, group_id, "last_use")

    # Schedule notification for /play cooldown end
    context.job_queue.run_once(
        notify_play_available, 12 * 3600,
        data={'user_id': user.id, 'group_id': group_id, 'username': user.username}
    )

    new_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ? AND group_id = ?", (user.id, group_id)).fetchone()[0]

    # Update longest and shortest Kir
    cursor.execute("SELECT longest_kir, shortest_kir FROM players WHERE user_id = ? AND group_id = ?", (user.id, group_id))
    longest, shortest = cursor.fetchone()
    if new_kir > longest:
        cursor.execute("UPDATE players SET longest_kir = ? WHERE user_id = ? AND group_id = ?", (new_kir, user.id, group_id))
    if shortest == 0 or new_kir < shortest:
        cursor.execute("UPDATE players SET shortest_kir = ? WHERE user_id = ? AND group_id = ?", (new_kir, user.id, group_id))
    conn.commit()

    await update.message.reply_text(f"{user.username}, your Kir changed by {change}. Now you have {new_kir} Kir.")

async def emergencykir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    group_id = update.effective_chat.id
    player = get_player(user.id, user.username, group_id)
    kir = player[3]

    if kir > 0:
        await update.message.reply_text("You can only use /emergencykir when your Kir is 0 or less.")
        return

    if not can_use(user.id, group_id, "last_emergency", 24):
        await update.message.reply_text("You must wait 24 hours before using /emergencykir again.")
        return

    boost = random.randint(3, 9)
    update_kir(user.id, group_id, boost)
    set_time(user.id, group_id, "last_emergency")

    # Schedule notification for /emergencykir cooldown end
    context.job_queue.run_once(
        notify_emergency_available, 24 * 3600,
        data={'user_id': user.id, 'group_id': group_id, 'username': user.username}
    )

    # After boost, update longest and shortest Kir too
    new_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ? AND group_id = ?", (user.id, group_id)).fetchone()[0]
    cursor.execute("SELECT longest_kir, shortest_kir FROM players WHERE user_id = ? AND group_id = ?", (user.id, group_id))
    longest, shortest = cursor.fetchone()
    if new_kir > longest:
        cursor.execute("UPDATE players SET longest_kir = ? WHERE user_id = ? AND group_id = ?", (new_kir, user.id, group_id))
    if shortest == 0 or new_kir < shortest:
        cursor.execute("UPDATE players SET shortest_kir = ? WHERE user_id = ? AND group_id = ?", (new_kir, user.id, group_id))
    conn.commit()

    await update.message.reply_text(f"🚨 Emergency Kir activated! You received {boost} Kir. You now have {new_kir} Kir.")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.effective_chat.id
    leaderboard = cursor.execute(
        "SELECT username, kir FROM players WHERE group_id = ? ORDER BY kir DESC LIMIT 10",
        (group_id,)
    ).fetchall()
    message = "🏆 Top Players in this group:\n"
    for i, (name, kir) in enumerate(leaderboard, 1):
        message += f"{i}. {name} - {kir} Kir\n"
    await update.message.reply_text(message)

async def state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    group_id = update.effective_chat.id
    player = get_player(user.id, user.username, group_id)
    kir = player[3]
    win_streak = player[6]
    longest_kir = player[7]
    shortest_kir = player[8]

    # Update longest and shortest Kir if needed
    if longest_kir == 0 or kir > longest_kir:
        cursor.execute("UPDATE players SET longest_kir = ? WHERE user_id = ? AND group_id = ?", (kir, user.id, group_id))
        longest_kir = kir
    if shortest_kir == 0 or kir < shortest_kir:
        cursor.execute("UPDATE players SET shortest_kir = ? WHERE user_id = ? AND group_id = ?", (kir, user.id, group_id))
        shortest_kir = kir
    conn.commit()

    all_players = cursor.execute("SELECT user_id FROM players WHERE group_id = ? ORDER BY kir DESC", (group_id,)).fetchall()
    rank_map = {uid: i+1 for i, (uid,) in enumerate(all_players)}
    rank = rank_map.get(user.id, "N/A")

    await update.message.reply_text(
        f"📊 {user.username}'s state in this group:\n"
        f"Kir: {kir}\n"
        f"Rank: #{rank}\n"
        f"Win Streak: {win_streak}\n"
        f"Longest Kir: {longest_kir}\n"
        f"Shortest Kir: {shortest_kir}"
    )

# --- BOT COMMANDS SETUP ---

async def set_commands(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("play", "Play to grow or shrink your Kir"),
        BotCommand("top", "Show top players"),
        BotCommand("emergencykir", "Use emergency Kir if your Kir ≤ 0"),
        BotCommand("state", "Show your Kir state and rank"),
    ]
    await application.bot.set_my_commands(commands)

# --- MAIN ---

if __name__ == "__main__":
    TOKEN = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("emergencykir", emergencykir))
    app.add_handler(CommandHandler("state", state))

    app.post_init = set_commands

    print("Bot started...")
    app.run_polling()
